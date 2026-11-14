"""Independent C45 software/source, typed actual SDK/HTTP/DOM and SQL audit."""
from collections import Counter
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tarfile

from probe_sdk_mode import projection
from run_regression import ROOT, snapshot, digest

BASE = Path(__file__).resolve().parents[1]
WORK = BASE/'审计/工作目录'
REGRESS = WORK/'002-当前软件与浏览器'


def read(path):
    return json.loads(path.read_text())


def historical(ref, names):
    raw = subprocess.check_output(['git','archive','--format=tar',ref,'--',*sorted(names)],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        return {m.name:hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in archive if m.isfile()}


def current_and_historical(receipt, source_key, script):
    source = receipt[source_key]
    assert historical(receipt['head'], source) == source
    assert all(digest(ROOT/n) == sha for n,sha in source.items())
    assert receipt['collector_sha256'] == digest(BASE/'审计'/script)


def check_typed(text, result, expected, sql):
    metadata = result['reminder_query']
    assert metadata['version'] == 2 and metadata['mode'] == 'reminder_query'
    assert metadata['route'] == expected and metadata['model_calls'] == 0
    assert metadata['business_mutations'] is False and metadata['semantic_intent_verified'] is False
    assert metadata['source_message_id'] == result['conversation']['user_message_id']
    assert metadata['revision'] == result['conversation']['revision']
    assert metadata['session_id'] == result['conversation']['session_id']
    assert result['analysis_mode'] == result['generation_mode'] == 'rules_reminder_query'
    assert not result['due_reminders'] and not result['tool_calls'] and not result['reminder']
    assert len([s for s in sql if 'FROM memory_reminders' in s]) == (1 if expected == 'read_state' else 0)
    if expected == 'read_policy':
        assert metadata['external_delivery_channels'] == []
        assert '当前没有短信、邮件或电话提醒通道' in result['reply']
    if expected == 'read_state':
        assert metadata['state']['status'] == 'active' and metadata['state']['id'] == 1
        assert not metadata['state']['service_claim_recorded'] and not metadata['state']['client_ack_recorded']


def main():
    output = BASE/'审计/收尾核验/system-evidence.json'
    assert not output.exists(); output.parent.mkdir(exist_ok=True)
    source = snapshot(); assert len(source) == 468
    software = []
    for mode, tag in [('python','product-mode-v1'),('frontend','product-mode-v1'),('build','product-mode-v1'),
                      ('browser','product-mode-v1'),('browser_targeted','product-mode-first')]:
        path = REGRESS/f'{tag}-{mode}-final-binding.json'; proof = read(path)
        assert proof['exit_code'] == 0 and proof['source_unchanged']
        assert proof['source_git_sha256'] == source and historical(proof['head'], source) == source
        assert proof['driver_sha256'] == digest(BASE/'审计/run_regression.py')
        log = REGRESS/f'{tag}-{mode}-final.log'
        assert proof['log_sha256'] == digest(log)
        if mode == 'python': assert '2396 passed, 1 skipped' in log.read_text()
        if mode == 'frontend': assert '195 passed' in log.read_text()
        if mode.startswith('browser'):
            assert proof['runtime_matches'] and proof['optional_e2e_flags_cleared']
            runtime = REGRESS/f'{tag}-browser-final-runtime.json'; actual = read(runtime)
            assert proof['runtime_sha256'] == digest(runtime)
            assert len(actual['module_paths']) == 12 and len(actual['frontend_sha256']) == 5
            assert actual['query_mode_protocol_sha256'] == source['evals/interaction/cycle-45/product-query-protocol.json']
            for name, path in actual['module_paths'].items():
                assert digest(Path(path)) == actual['module_sha256'][name] == source[str(Path(path).relative_to(ROOT))]
            assert actual['frontend_sha256'] == proof['runtime_artifact_sha256']
        if mode == 'browser': assert '19 passed' in log.read_text() and '16 skipped' in log.read_text()
        software.append({'mode':mode,'head':proof['head'],'inputs':len(source),'binding_sha256':digest(REGRESS/f'{tag}-{mode}-final-binding.json')})
    sdk = read(WORK/'001-真实入口调查/sdk-mode-evidence.json')
    current_and_historical(sdk, 'source_sha256', 'probe_sdk_mode.py')
    assert sdk['verified'] and sdk['actual_query_SDK_turns'] == len(sdk['cases']) == 7
    sdk_expected = ['read_state','read_policy','clarify_reference','clarify_intent','no_read','no_read','no_read']
    for case, expected in zip(sdk['cases'], sdk_expected):
        check_typed(case['input'],case['result'],expected,case['SQL'])
        assert case['business_before'] == case['business_after']
        assert [r['role'] for r in case['messages']] == ['user','assistant']
        assert not case['model_analysis'] and not case['model_generation']
    assert len(sdk['later_ordinary_context']['analysis']) == len(sdk['later_ordinary_context']['generation']) == 1
    assert sdk['cases'][0]['result']['reply'] in str(sdk['later_ordinary_context']['generation'][0])
    http = read(WORK/'003-真实HTTP与上下文/v2/http-evidence.json')
    current_and_historical(http, 'source_sha256', 'probe_http_mode.py')
    assert http['verified'] and http['actual_query_HTTP_turns'] == 10 and http['query_model_calls'] == 0
    assert http['query_business_before'] == http['query_business_after']
    protocol = read(ROOT/'evals/interaction/cycle-45/product-query-protocol.json')
    expected = [case['route'] for case in protocol['browser_cases'] for _ in range(2)]
    assert len(http['traces']) == 11
    for case, route in zip(http['traces'][:10],expected): check_typed(case['input'],case['result'],route,case['SQL'])
    assert len(http['messages_after_queries']) == 20
    streams = [call['response'] for call in http['calls'] if call['path'].endswith('/events')]
    assert len(streams) == 5 and all('event: result\n' in raw for raw in streams)
    for raw, entry in zip(streams, protocol['browser_cases']):
        results = [json.loads(line[6:]) for block in raw.split('\n\n') if 'event: result\n' in block
                   for line in block.splitlines() if line.startswith('data: ')]
        assert len(results) == 1 and results[0]['reminder_query']['route'] == entry['route']
    later = http['subsequent_ordinary_model']
    assert later['recover_context'] is True and len(later['analysis']) == len(later['generation']) == 1
    assert 'C45HTTP合成私密标题' not in str(later['generation'][0])
    sql_dump = WORK/'003-真实HTTP与上下文/v2/after-query.sql'
    assert digest(sql_dump) == http['query_SQL_dump_sha256']
    with sqlite3.connect(':memory:') as conn:
        conn.row_factory = sqlite3.Row; conn.executescript(sql_dump.read_text())
        assert projection(type('MemoryView',(),{'_conn':conn})()) == http['query_business_after']
        assert conn.execute('SELECT count(*) FROM memory_messages').fetchone()[0] == 20
        assert conn.execute('SELECT count(*) FROM memory_chat_results').fetchone()[0] == 10
    privacy = read(WORK/'004-实际查询隐私竞争/privacy-evidence.json')
    current_and_historical(privacy,'source_sha256','probe_query_privacy.py')
    assert privacy['verified'] and len(privacy['cases']) == 4
    for case in privacy['cases']:
        dump = WORK/'004-实际查询隐私竞争'/(case['case']+'.sql')
        assert digest(dump) == case['SQL_dump_sha256'] and case['business_before'] == case['business_after']
        assert case['shared_emotion_revision'] == case['revision_after']
        assert not any(e['event'] in ('text','result') for e in case['terminal_events'])
        if case['case'] == 'stale_admission':
            assert case['query_sources'] == 0 and not case['legitimate_reads_before_interruption']
            assert case['terminal_status_before_replay'] == 'failed'
        else:
            assert case['query_sources'] == 1 and len(case['legitimate_reads_before_interruption']) == 1
            assert case['terminal_status_before_replay'] == 'cancelled'
        with sqlite3.connect(':memory:') as conn:
            conn.row_factory = sqlite3.Row; conn.executescript(dump.read_text())
            assert projection(type('MemoryView',(),{'_conn':conn})()) == case['business_after']
            assert conn.execute("SELECT count(*) FROM memory_messages WHERE role='assistant'").fetchone()[0] == 1
    browser = read(REGRESS/'targeted-browser-records/query-mode-evidence.json')
    assert browser['completed'] and not browser['errors'] and len(browser['turns']) == 5
    assert browser['before'] == browser['after']
    assert [c['result']['reminder_query']['route'] for c in browser['turns']] == [c['route'] for c in protocol['browser_cases']]
    assert [v['width'] for v in browser['views']] == [1440,390] and not any(v['overflow'] for v in browser['views'])
    full = list((REGRESS/'full-browser-records').glob('*query-mode-evidence.json'))
    assert len(full) == 1 and read(full[0])['completed']
    failure = read(WORK/'003-真实HTTP与上下文/first-failure.json')
    old = historical('4f81bb74', {str((BASE/'审计/probe_http_mode.py').relative_to(ROOT)):None})
    assert failure['collector_sha256'] == next(iter(old.values())) and failure['actual_query_turns'] == 0
    assert 'no such table: memory_reminders' in (WORK/'001-真实入口调查/http-probe-first.log').read_text()
    seals = []
    for number in range(3,45):
        cycle = BASE.parent/f'cycle-{number:02}'; manifest = cycle/'审计/证据清单.json'
        data = read(manifest); assert all(digest(cycle/n) == sha for n,sha in data.items())
        seals.append({'cycle':cycle.name,'items':len(data),'sha256':digest(manifest)})
    migration = ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
    assert all(digest(migration.parent/n) == sha for n,sha in read(migration).items())
    assert sum(s['items'] for s in seals)+len(read(migration)) == 8381
    aliases = json.loads(subprocess.check_output(['python3','-B','scripts/link_project_assets.py','--check'],cwd=ROOT,text=True))
    assert len(aliases) == 9 and all(a['valid'] for a in aliases)
    checker = ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-38/审计/check_research_names.py'
    spec = importlib.util.spec_from_file_location('pure_names',checker); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    names = {p.name:module.undefined_globals(p.read_text(),str(p)) for p in (BASE/'审计').glob('*.py')}
    assert all(not found for found in names.values()), names
    result = {'verified':True,'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(Path(__file__)),'current_software_inputs':len(source),'software':software,
        'actual_SDK_query_turns':7,'actual_HTTP_query_turns':10,'actual_HTTP_query_SSE':5,
        'actual_targeted_query_DOM_turns':5,'actual_full_suite_query_DOM_turns':5,
        'query_model_calls':0,'native_inference_calls':0,'independent_SQL_dumps_reconstructed':5,
        'privacy_races':4,'legitimate_reads_before_interruption':3,'stale_admission_sources':0,
        'SDK_later_query_history_present':True,'default_Web_later_query_history_present':False,
        'issues_limited_closed':1,'issues_open_context':1,'old_seals_including_migration':43,'old_items':8381,
        'old_seals':seals,'asset_aliases':aliases,'undefined_globals':names}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C45 system:7SDK/10HTTP+5SSE/5+5DOM;4privacy/5SQL;2396/1,195,19/16;468source;43old8381;1closed/1contextopen')


if __name__ == '__main__':
    main()
