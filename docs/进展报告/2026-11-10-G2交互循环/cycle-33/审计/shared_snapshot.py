"""SQLite backup of closed owned synthetic preparation into independent arms."""
from contextlib import closing
from hashlib import sha256
from pathlib import Path
import sqlite3
ROOT=Path(__file__).resolve().parents[5]


def owned(path):
    path=Path(path).resolve();temporary=(ROOT.parent/'runtime/tmp').resolve()
    if not path.is_relative_to(temporary) or not path.parent.name.startswith('c33-context-'):
        raise ValueError('Use owned C33 temporary DB only')
    return path


def logical_dump(path):
    with closing(sqlite3.connect('file:'+str(owned(path))+'?mode=ro',uri=True)) as conn:
        assert conn.execute('PRAGMA integrity_check').fetchall()==[('ok',)]
        return '\n'.join(conn.iterdump())+'\n'


def backup_pair(source,targets,*,preparation_worker_closed):
    source=owned(source);targets=[owned(path) for path in targets]
    if preparation_worker_closed is not True:raise ValueError('Close owned preparation worker before backup')
    if len(targets)!=2 or len(set([source,*targets]))!=3 or not source.is_file() or any(path.exists() for path in targets):
        raise ValueError('Require one existing source and two distinct fresh arm DBs')
    before=logical_dump(source)
    with closing(sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True)) as conn:
        for target in targets:
            with closing(sqlite3.connect(str(target))) as destination:conn.backup(destination)
    assert all(logical_dump(target)==before for target in targets) and logical_dump(source)==before
    return {'source':str(source),'targets':[str(path) for path in targets],
        'initial_logical_dump_sha256':sha256(before.encode()).hexdigest(),
        'initial_file_sha256':{str(path):sha256(path.read_bytes()).hexdigest() for path in [source,*targets]},
        'integrity_check':True,'initial_logical_data_equal':True,'preparation_worker_closed':True,
        'sqlite_backup_not_shared_writable_file':True}
