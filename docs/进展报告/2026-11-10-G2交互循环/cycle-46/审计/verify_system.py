"""Independently reconstruct C46 source-bound history, SQL, privacy and regressions."""
from collections import Counter
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tarfile

from run_history_capture import projection
from run_regression import ROOT, snapshot, digest

BASE = Path(__file__).resolve().parents[1]
WORK = BASE/'审计/工作目录'
REGRESS = WORK/'002-当前软件与浏览器'


def read(path):
    return json.loads(Path(path).read_text())


def historical(ref,names):
    raw = subprocess.check_output(['git','archive','--format=tar',ref,'--',*sorted(names)],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        return {m.name:hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in archive if m.isfile()}


def bound(proof,script,source):
    assert proof['verified'] and proof['source_sha256'] == source
    assert historical(proof['head'],source) == source
    assert proof['collector_sha256'] == digest(BASE/'审计'/script)


def status_reads(sql):
    return [s for s in sql if 'd.acknowledged_at AS client_ack' in s and 'FROM memory_reminders' in s]


def sql_view(path):
    conn = sqlite3.connect(':memory:'); conn.row_factory = sqlite3.Row
    try:
        conn.executescript(path.read_text())
    except BaseException:
        conn.close(); raise
    return conn


def main():
    output = BASE/'审计/收尾核验/system-evidence.json'; assert not output.exists()
    output.parent.mkdir(exist_ok=True)
    source = snapshot(); assert len(source) == 472
    software = []
    for mode,tag in [('python','history-resume-v2'),('frontend','history-v1'),('build','history-v1'),('browser','history-v1')]:
        p = REGRESS/f'{tag}-{mode}-final-binding.json'; data = read(p)
        assert data['exit_code'] == 0 and data['source_unchanged'] and data['source_git_sha256'] == source
        assert historical(data['head'],source) == source and data['driver_sha256'] == digest(BASE/'审计/run_regression.py')
        log = REGRESS/f'{tag}-{mode}-final.log'; assert digest(log) == data['log_sha256']
        if mode == 'python': assert '2446 passed, 1 skipped' in log.read_text()
        if mode == 'frontend': assert '195 passed' in log.read_text()
        if mode == 'browser':
            assert '19 passed' in log.read_text() and '16 skipped' in log.read_text() and data['runtime_matches']
            runtime = REGRESS/f'{tag}-browser-final-runtime.json'; actual = read(runtime)
            assert data['runtime_sha256'] == digest(runtime) and len(actual['module_paths']) == 13
            assert len(actual['frontend_sha256']) == 5 and actual['frontend_sha256'] == data['runtime_artifact_sha256']
            assert actual['query_history_protocol_sha256'] == source['evals/interaction/cycle-46/query-history-protocol.json']
            for name,path in actual['module_paths'].items():
                assert actual['module_sha256'][name] == digest(Path(path)) == source[str(Path(path).relative_to(ROOT))]
        software.append({'mode':mode,'head':data['head'],'inputs':len(source),'sha256':digest(p)})
    interrupted = read(REGRESS/'history-v1-python-interruption.json')
    assert interrupted['count_as_pass'] is False and interrupted['binding_exit_code'] is None
    assert read(REGRESS/'history-v1-python-final-binding.json')['exit_code'] is None
    assert interrupted['binding_sha256'] == digest(REGRESS/'history-v1-python-final-binding.json')
    assert interrupted['log_sha256'] == digest(REGRESS/'history-v1-python-final.log')
    assert '2446 passed' not in (REGRESS/'history-v1-python-final.log').read_text()
    protocol_path = ROOT/'evals/interaction/cycle-46/query-history-protocol.json'; protocol = read(protocol_path)
    groups = []; dumps_count = 0; sample = None
    for arm in ('sdk','web'):
        for case in protocol['cases']:
            folder = WORK/'003-实际历史与重启'/(arm+'-'+case['id'])
            data = read(folder/'capture.json'); bound(data,'run_history_capture.py',source)
            assert data['protocol_sha256'] == digest(protocol_path) and data['case'] == case and data['arm'] == arm
            assert data['query_turns'] == 2 and data['ordinary_turns'] == 2 and data['query_model_calls'] == 0
            assert len(data['analysis']) == len(data['generation']) == 2 and data['external_native_calls'] == 0
            assert all([r['stage'] for r in data[kind]] == ['ordinary_before','ordinary_after'] for kind in ('analysis','generation'))
            traces = {r['stage']:r for r in data['traces']}
            query = traces['explicit_query']['result']; current = traces['explicit_current_status_query']['result']
            assert query['reminder_query']['route'] == case['route']
            assert current['reminder_query']['state']['status'] == 'cancelled'
            assert len(status_reads(traces['explicit_query']['SQL'])) == (1 if case['route'] == 'read_state' else 0)
            assert len(status_reads(traces['explicit_current_status_query']['SQL'])) == 1
            assert not status_reads(traces['ordinary_after']['SQL'])
            for kind in ('analysis','generation'):
                messages = data[kind][-1]['messages']
                envelopes = [json.loads(m['content'].split('\n',1)[1]) for m in messages
                    if m['role'] == 'assistant' and m['content'].startswith('历史提醒查询快照（')]
                assert len(envelopes) == 1
                expected = {'query_history_version':1,'historical_snapshot_only':True,'untrusted_data_not_instructions':True,
                    'reply':query['reply'],'route':case['route'],
                    'source_message_id':query['conversation']['user_message_id'],'observed_at':query['reminder_query']['observed_at']}
                assert envelopes[0] == expected == data['envelopes'][kind]
                assert '先前场景C46-'+case['id']+'保持线索。' in str(messages)
            if case['route'] == 'read_state':
                assert query['reminder_query']['state']['status'] == 'active' and '记录状态为有效' in query['reply']
            query_business = data['dumps']['after-query']['business']
            expected_after = copy.deepcopy(query_business); expected_after['memory_reminders'][0]['status'] = 'cancelled'
            assert data['dumps']['after-ordinary']['business'] == expected_after == data['dumps']['after-current-query']['business']
            assert len([s for s in data['actor_SQL'] if s.startswith('UPDATE memory_reminders')]) == 1
            for stage in ('after-query','after-ordinary','after-current-query'):
                path = folder/(stage+'.sql'); receipt = data['dumps'][stage]
                assert digest(path) == receipt['sha256']
                conn = sql_view(path)
                try:
                    assert projection(type('MemoryView',(),{'_conn':conn})()) == receipt['business']
                    rows = [dict(r) for r in conn.execute('SELECT * FROM memory_messages')]
                    assert rows == receipt['messages'] and not receipt['profile']
                    assert conn.execute('SELECT count(*) FROM memory_fragments').fetchone()[0] == 0
                    extra = 2 if arm == 'sdk' else 0
                    assert len(rows) == {'after-query':4,'after-ordinary':6,'after-current-query':8}[stage]+extra
                    assert conn.execute('SELECT count(*) FROM memory_chat_results').fetchone()[0] == (0 if arm == 'sdk' else {'after-query':2,'after-ordinary':3,'after-current-query':4}[stage])
                    query_row = next(r for r in rows if r['id'] == query['conversation']['assistant_message_id'])
                    assert query_row['content'] == query['reply'] and not query_row['content'].startswith('历史提醒查询快照（')
                    if stage != 'after-query':
                        ordinary_id = traces['ordinary_after']['result']['conversation']['assistant_message_id']
                        dependencies = {r[0] for r in conn.execute("SELECT source_id FROM memory_response_context WHERE message_id=? AND source_type='message'",(ordinary_id,))}
                        assert {query['conversation']['user_message_id'],query['conversation']['assistant_message_id']} <= dependencies
                    if stage == 'after-current-query':
                        row = next(r for r in rows if r['id'] == current['conversation']['assistant_message_id'])
                        assert row['content'] == current['reply'] and '记录状态为已取消' in row['content']
                finally: conn.close()
                dumps_count += 1
            assert data['SDK_preparation_control_turns'] == (1 if arm == 'sdk' else 0)
            assert len(data['calls']) == (5 if arm == 'sdk' else 4)
            if arm == 'web':
                assert len(data['restarts']) == 2 and data['restarts'][0]['session_id'] != data['restarts'][1]['session_id']
                assert all(c['status'] == 200 for c in data['calls'])
            else: assert data['restarts'] == []
            if arm == 'sdk' and case['id'] == 'state': sample = (case['text'],query)
            groups.append({'arm':arm,'case':case['id'],'head':data['head'],'receipt_sha256':digest(folder/'capture.json')})
    erasure = read(WORK/'005-完成查询后的实际遗忘/erasure-evidence.json')
    bound(erasure,'probe_history_erasure.py',source); assert len(erasure['cases']) == 2
    for case in erasure['cases']:
        assert len(case['analysis']) == len(case['generation']) == 2
        assert case['query_turns'] == 1 and case['query_model_calls'] == 0 and case['ordinary_turns'] == 2
        assert case['independent_control_turns'] == 1
        for kind in ('analysis','generation'):
            assert 'C46待遗忘查询标题' in str(case[kind][0]) and 'C46待遗忘查询标题' not in str(case[kind][-1])
        query = case['calls'][0]['result']; ordinary = case['calls'][1]['result']
        for name in ('before','after'):
            path = WORK/'005-完成查询后的实际遗忘'/(case['arm']+'-'+name+'-forget.sql')
            assert digest(path) == case[name+'_SQL_sha256']; conn = sql_view(path)
            try:
                assert projection(type('MemoryView',(),{'_conn':conn})()) == case['business_'+('before' if name == 'before' else 'after')]
                assert conn.execute('SELECT count(*) FROM memory_messages').fetchone()[0] == (4 if name == 'before' else 8)
                for value in (query,ordinary):
                    row = conn.execute('SELECT content FROM memory_messages WHERE id=?',(value['conversation']['assistant_message_id'],)).fetchone()
                    assert row[0] == ('[redacted]' if name == 'after' else value['reply'])
                if name == 'after':
                    assert conn.execute('SELECT revision FROM memory_context_revision WHERE id=1').fetchone()[0] == case['revision_after_forget']
                    assert 'C46待遗忘查询标题' not in str(list(conn.execute('SELECT result_json FROM memory_chat_results')))
            finally: conn.close()
            dumps_count += 1
        assert case['business_before'] == case['business_after']
        if case['arm'] == 'web': assert len(case['sessions']) == 2 and case['sessions'][0] != case['sessions'][1]
    privacy = read(WORK/'004-实际查询隐私竞争/privacy-evidence.json')
    bound(privacy,'probe_query_privacy.py',source); assert len(privacy['cases']) == 4
    for case in privacy['cases']:
        path = WORK/'004-实际查询隐私竞争'/(case['case']+'.sql')
        assert digest(path) == case['SQL_dump_sha256'] and case['business_before'] == case['business_after']
        assert case['shared_emotion_revision'] == case['revision_after']
        assert not any(e['event'] in ('text','result') for e in case['terminal_events'])
        if case['case'] == 'stale_admission':
            assert case['query_sources'] == 0 and not case['legitimate_reads_before_interruption']
        else: assert case['query_sources'] == 1 and len(case['legitimate_reads_before_interruption']) == 1
        conn = sql_view(path)
        try:
            assert projection(type('MemoryView',(),{'_conn':conn})()) == case['business_after']
            assert conn.execute("SELECT count(*) FROM memory_messages WHERE role='assistant'").fetchone()[0] == 1
        finally: conn.close()
        dumps_count += 1
    assert dumps_count == 38
    text,query = sample
    old = subprocess.check_output(['git','show','addbd290:src/avatar/brain/query_history.py'],cwd=ROOT,text=True)
    namespace = {'__name__':'avatar.brain.c46_pure_failure_replay','__package__':'avatar.brain'}
    exec(compile(old,'addbd290-query-history.py','exec'),namespace)
    metadata = copy.deepcopy(query['reminder_query']); metadata['observed_at'] = 10**400
    kwargs = {'text':text,'source_message_id':query['conversation']['user_message_id'],
        'session_id':query['conversation']['session_id'],'revision':query['conversation']['revision'],
        'scope':'current_user','turn_tools_allowed':True}
    try: namespace['query_history_content'](query['reply'],metadata,**kwargs)
    except OverflowError: pass
    else: raise AssertionError('original pure failure not reproduced')
    from avatar.brain.query_history import query_history_content
    assert query_history_content(query['reply'],metadata,**kwargs) is None
    assert historical('f37839b6',{'src/avatar/brain/query_history.py'})['src/avatar/brain/query_history.py'] == source['src/avatar/brain/query_history.py']
    assert '1 failed, 29 passed' in (WORK/'001-历史数据范围调查/history-extreme-first.log').read_text()
    assert '30 passed' in (WORK/'001-历史数据范围调查/history-extreme-fixed.log').read_text()
    seals = []
    for number in range(3,46):
        cycle = BASE.parent/f'cycle-{number:02}'; p = cycle/'审计/证据清单.json'
        data = read(p); assert all(digest(cycle/n) == sha for n,sha in data.items())
        seals.append({'cycle':cycle.name,'items':len(data),'sha256':digest(p)})
    migration = ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
    assert all(digest(migration.parent/n) == sha for n,sha in read(migration).items())
    assert sum(s['items'] for s in seals)+len(read(migration)) == 8449
    aliases = json.loads(subprocess.check_output(['python3','-B','scripts/link_project_assets.py','--check'],cwd=ROOT,text=True))
    assert len(aliases) == 9 and all(a['valid'] for a in aliases)
    checker = ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-38/审计/check_research_names.py'
    spec = importlib.util.spec_from_file_location('pure_names',checker); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    names = {p.name:module.undefined_globals(p.read_text(),str(p)) for p in (BASE/'审计').glob('*.py')}
    assert all(not found for found in names.values()),names
    assert snapshot() == source
    result = {'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(Path(__file__)),'current_software_inputs':len(source),'software':software,
        'main_groups':groups,'main_query_turns':20,'main_ordinary_turns':20,'main_analysis_captures':20,
        'main_generation_captures':20,'SDK_extra_preparation_controls':5,'main_Web_restarts':5,
        'erasure_query_turns':2,'erasure_ordinary_turns':4,'erasure_independent_controls':2,
        'erasure_analysis_captures':4,'erasure_generation_captures':4,'erasure_Web_restarts':1,
        'privacy_races':4,'legitimate_reads_before_interruption':3,'stale_admission_sources':0,
        'query_model_calls':0,'native_external_calls':0,'independent_SQL_dumps_reconstructed':dumps_count,
        'first_extreme_integer_failure_reproduced_from_Git':True,'fixed_extreme_integer_rejected':True,
        'interrupted_full_test_not_counted':True,'issues_limited_closed':1,
        'inherited_C45_002_closed_in_measured_history_scope':True,'general_semantic_approval':False,
        'old_seals_including_migration':44,'old_items':8449,'old_seals':seals,'asset_aliases':aliases,'undefined_globals':names}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C46 system:10groups/20query+20ordinary/30SQL;2erasure/4SQL;4privacy/4SQL;2446/1,195,19/16;472source;44old8449')


if __name__ == '__main__':
    main()
