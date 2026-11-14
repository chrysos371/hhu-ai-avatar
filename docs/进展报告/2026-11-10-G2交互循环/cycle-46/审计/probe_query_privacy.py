"""Barrier-controlled actual async HTTP cancellation/erasure/source races."""
from contextlib import closing
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request

from avatar.brain.memory import MemoryStore
from avatar.brain.reminders import ReminderStore
from avatar.brain.reminder_query_mode import ReminderQueryReader
from avatar.config import config
from avatar.paths import temporary_dir
from avatar.web import create_server
from run_history_capture import projection
from run_regression import ROOT, snapshot, digest

BASE = Path(__file__).resolve().parents[1]
WORK = BASE/'审计/工作目录/004-实际查询隐私竞争'


def main():
    assert not WORK.exists(); WORK.mkdir()
    source = snapshot(); cases = []
    original = ReminderQueryReader.resolve
    old_key, old_embedding = config.llm.api_key, config.embedding.model
    config.llm.api_key, config.embedding.model = '', ''
    try:
        for case in ('cancel_after_read', 'forget_after_read', 'new_source_after_read', 'stale_admission'):
            entered, release = threading.Event(), threading.Event()
            observations = []
            def blocked(reader):
                value = original(reader)
                observations.append({'route': value.metadata['route'], 'source_message_id': value.metadata['source_message_id'],
                    'observed_at': value.metadata['observed_at'], 'snapshot_released': not reader.store.conn.in_transaction})
                entered.set()
                if not release.wait(10):
                    raise RuntimeError('probe barrier cleanup bound exceeded')
                return value
            ReminderQueryReader.resolve = blocked
            with tempfile.TemporaryDirectory(prefix='c46-query-race-',dir=temporary_dir()) as directory:
                server = create_server(str(Path(directory)/'actual.db'), port=0)
                thread = threading.Thread(target=server.serve_forever,daemon=True); thread.start()
                calls = []
                def request(path, data=None, *, stream=False, expected_status=200):
                    req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/v1'+path,
                        data=None if data is None else json.dumps(data).encode(),
                        headers={'Content-Type': 'application/json','X-Avatar-Token':server.token})
                    try:
                        response = urllib.request.urlopen(req,timeout=15)
                    except urllib.error.HTTPError as error:
                        response = error
                    with response:
                        assert response.status == expected_status
                        raw = response.read().decode()
                        calls.append({'path':path,'input':data,'status':response.status,
                            'response': raw if stream else json.loads(raw)})
                    return raw if stream else json.loads(raw)['data']
                try:
                    control = request('/chat', {'text':'回到现实。'})
                    with closing(MemoryStore(server.db_path)) as writer:
                        ReminderStore(writer).create('提醒我2099年1月1日上午十点，C46竞争合成标题。')
                        fragment = writer.remember('C46隐私竞争合成事实')
                        before = projection(writer)
                        assistants_before = writer._conn.execute("SELECT count(*) FROM memory_messages WHERE role='assistant'").fetchone()[0]
                    context = request('/conversation/speaker')
                    expected = {k:context[k] for k in ('instance_id','revision','context_cursor')}
                    ident = 'c46_actual_privacy_'+case+'_123456'
                    if case == 'stale_admission':
                        with closing(MemoryStore(server.db_path)) as writer:
                            writer.add_message('user','并发先行来源','external')
                    request('/turns', {'request_id':ident,'text':'提醒编号1状态？','mode':'reminder_query','expected_context':expected}, expected_status=202)
                    job = server.turns.get(ident)
                    if case != 'stale_admission':
                        assert entered.wait(5)
                        if case == 'cancel_after_read':
                            request('/turns/'+ident+'/cancel', {})
                        else:
                            with closing(MemoryStore(server.db_path)) as writer:
                                if case == 'forget_after_read': writer.forget(fragment)
                                else: writer.add_message('user','新的并发来源','external')
                        release.set()
                    with job.changed:
                        assert job.changed.wait_for(lambda: job.status in ('cancelled','failed','completed'),timeout=10)
                    terminal_status = job.status
                    terminal_events = json.loads(json.dumps(job.events))
                    raw = request('/turns/'+ident+'/events', stream=True,
                        expected_status=404 if case == 'forget_after_read' else 200)
                    assert 'event: result\n' not in raw and 'C46竞争合成标题' not in raw
                    assert not any(e['event'] in ('text','result') for e in job.events)
                    if case == 'stale_admission':
                        assert terminal_status == 'failed' and terminal_events[-1]['data']['code'] == 'speaker_context_changed'
                        assert not entered.is_set() and not observations
                    else:
                        assert terminal_status == 'cancelled' and len(observations) == 1
                        assert observations[0]['snapshot_released']
                    if case == 'forget_after_read':
                        assert job.redacted and job.status == 'redacted' and job.result is None and not job.events
                    with closing(MemoryStore(server.db_path)) as writer:
                        assert projection(writer) == before
                        assert writer._conn.execute("SELECT count(*) FROM memory_messages WHERE role='assistant'").fetchone()[0] == assistants_before
                        query_sources = writer._conn.execute("SELECT count(*) FROM memory_messages WHERE role='user' AND content='提醒编号1状态？'").fetchone()[0]
                        assert query_sources == (0 if case == 'stale_admission' else 1)
                        sql_file = WORK/(case+'.sql')
                        sql_file.write_text('\n'.join(writer._conn.iterdump())+'\n')
                        cases.append({'case':case,'terminal_status_before_replay':terminal_status,
                            'status_after_replay':job.status,'calls':calls,'terminal_events':terminal_events,'events_after_replay':job.events,
                            'legitimate_reads_before_interruption':observations,'query_sources':query_sources,
                            'business_before':before,'business_after':projection(writer),
                            'SQL_dump_sha256':digest(sql_file),'revision_after':writer.context_revision,
                            'shared_emotion_revision':server.emotion._context_revision})
                finally:
                    release.set(); server.shutdown(); thread.join(); server.server_close()
        assert source == snapshot()
        (WORK/'privacy-evidence.json').write_text(json.dumps({'verified':True,
            'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'collector_sha256':digest(Path(__file__)),'source_sha256':source,'cases':cases,
            'external_native_calls':0,'scope':'actual HTTP/disk SQLite with explicit after-read barrier; valid earlier reads are not undone'},
            ensure_ascii=False,indent=2)+'\n')
        print('C46 privacy:3 legitimate reads followed by cancellation/no publication; stale admission 0 sources/0 reads;4 SQL dumps')
    finally:
        ReminderQueryReader.resolve = original
        config.llm.api_key, config.embedding.model = old_key, old_embedding


if __name__ == '__main__':
    main()
