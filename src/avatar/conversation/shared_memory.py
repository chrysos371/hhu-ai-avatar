"""Explicit owner-managed facts. No inference, relationship or transcript sharing."""
from contextlib import contextmanager
import json
import sqlite3
import time
import uuid
from pathlib import Path


class SharedFacts:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.is_symlink():
            raise ValueError('Invalid shared facts database')
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS shared_facts (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, key TEXT NOT NULL,
                    value TEXT NOT NULL, source TEXT NOT NULL, active INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS shared_grants (
                    fact_id TEXT NOT NULL, character TEXT NOT NULL,
                    PRIMARY KEY(fact_id, character));
                CREATE TABLE IF NOT EXISTS shared_revisions (
                    owner TEXT PRIMARY KEY, revision INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS shared_audit (
                    id INTEGER PRIMARY KEY, owner TEXT NOT NULL, fact_id TEXT NOT NULL,
                    action TEXT NOT NULL, created_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS shared_versions (
                    id INTEGER PRIMARY KEY, owner TEXT NOT NULL, fact_id TEXT NOT NULL,
                    previous TEXT NOT NULL, undone INTEGER NOT NULL DEFAULT 0);
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def revision(self, owner):
        with self.connect() as db:
            row = db.execute('SELECT revision FROM shared_revisions WHERE owner=?', (owner,)).fetchone()
            return row[0] if row else 0

    def list(self, owner):
        with self.connect() as db:
            rows = db.execute('SELECT * FROM shared_facts WHERE owner=? AND active=1', (owner,)).fetchall()
            return [dict(row, characters=[r[0] for r in db.execute(
                'SELECT character FROM shared_grants WHERE fact_id=? ORDER BY character', (row['id'],))]) for row in rows]

    def visible(self, owner, character):
        return [{'id': r['id'], 'key': r['key'], 'value': r['value'], 'source': r['source']}
                for r in self.list(owner) if character in r['characters']]

    def update(self, owner, *, key=None, value=None, characters=(), fact_id=None, revoke=False):
        from ..characters.library import CARD_MAP
        if (not isinstance(owner,str) or not owner or not isinstance(characters, (list, tuple))
                or any(not isinstance(c,str) or c not in CARD_MAP for c in characters)
                or (fact_id is not None and not isinstance(fact_id,str))):
            raise ValueError('Invalid sharing scope')
        if not revoke and (key not in ('name', 'diet', 'preference') or not isinstance(value, str)
                           or not 1 <= len(value.strip()) <= 300):
            raise ValueError('Only explicit name, diet or preference facts may be shared')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = None
            if fact_id:
                row = db.execute('SELECT * FROM shared_facts WHERE id=? AND owner=? AND active=1', (fact_id,owner)).fetchone()
                if not row:
                    raise ValueError('Fact unavailable')
                previous = dict(row, characters=[r[0] for r in db.execute('SELECT character FROM shared_grants WHERE fact_id=?', (fact_id,))])
            elif revoke:
                raise ValueError('Fact required')
            else:
                fact_id = uuid.uuid4().hex
            db.execute('INSERT INTO shared_versions(owner,fact_id,previous) VALUES(?,?,?)',
                       (owner,fact_id,json.dumps(previous,ensure_ascii=False)))
            if revoke:
                db.execute('UPDATE shared_facts SET active=0 WHERE id=?', (fact_id,))
            else:
                db.execute('INSERT OR REPLACE INTO shared_facts VALUES(?,?,?,?,?,1)',
                           (fact_id,owner,key,value.strip(),'owner_explicit'))
            db.execute('DELETE FROM shared_grants WHERE fact_id=?', (fact_id,))
            if not revoke:
                db.executemany('INSERT INTO shared_grants VALUES(?,?)', [(fact_id,c) for c in set(characters)])
            db.execute('INSERT INTO shared_revisions VALUES(?,1) ON CONFLICT(owner) DO UPDATE SET revision=revision+1', (owner,))
            db.execute('INSERT INTO shared_audit(owner,fact_id,action,created_at) VALUES(?,?,?,?)',
                       (owner,fact_id,'revoke' if revoke else 'set',time.time()))
        return fact_id

    def undo(self, owner, fact_id):
        if not isinstance(fact_id,str): raise ValueError('Invalid fact')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM shared_versions WHERE owner=? AND fact_id=? AND undone=0 ORDER BY id DESC LIMIT 1', (owner,fact_id)).fetchone()
            if not row:
                raise ValueError('No change to undo')
            previous = json.loads(row['previous'])
            db.execute('DELETE FROM shared_grants WHERE fact_id=?', (fact_id,))
            if previous is None:
                db.execute('UPDATE shared_facts SET active=0 WHERE id=? AND owner=?', (fact_id,owner))
            else:
                db.execute('INSERT OR REPLACE INTO shared_facts VALUES(?,?,?,?,?,?)',
                           (fact_id,owner,previous['key'],previous['value'],previous['source'],previous['active']))
                db.executemany('INSERT INTO shared_grants VALUES(?,?)', [(fact_id,c) for c in previous['characters']])
            db.execute('UPDATE shared_versions SET undone=1 WHERE id=?', (row['id'],))
            db.execute('INSERT INTO shared_revisions VALUES(?,1) ON CONFLICT(owner) DO UPDATE SET revision=revision+1', (owner,))
            db.execute('INSERT INTO shared_audit(owner,fact_id,action,created_at) VALUES(?,?,?,?)', (owner,fact_id,'undo',time.time()))

    def audit(self, owner):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM shared_audit WHERE owner=? ORDER BY id DESC LIMIT 200', (owner,))]
