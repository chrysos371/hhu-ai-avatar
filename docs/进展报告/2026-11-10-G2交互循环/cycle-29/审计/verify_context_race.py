"""Independent binding of explicit scheduler, SQL lock intent and actual SSE."""
from collections import Counter
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import subprocess
import time
from context_baseline_common import ROOT,BASE,digest
from run_context_baseline import events
from verify_context_baseline import normalized
EXPECTED='2faa09cd43a5ba8838a55a40277b11d7869a9e960f7ff55c7c06b91796924043'


def read(path):return json.loads(path.read_text())
def verify():
    folder=BASE/'实验/context-transaction-interleaving';data=read(folder/'race.json');case=data['cases'][0]
    fp=ROOT/'evals/interaction/cycle-29/context-transaction-interleaving-freeze.json';frozen=read(fp)
    assert digest(fp)==EXPECTED==data['freeze_sha256'] and frozen==data['frozen_inputs']
    assert data['completed'] and case['complete'] and data['failure'] is None and not data['cleanup_errors']
    assert data['explicit_delegated_timing_wrappers'] is True and data['actual_llm_or_gpu'] is False
    assert not any(data['thread_cleanup'].values())
    git=lambda ref,name:subprocess.check_output(['git','show',ref+':'+name],cwd=ROOT)
    for name,value in frozen['sha256'].items():assert sha256(git(frozen['source_ref'],name)).hexdigest()==value
    assert sha256(git(data['head'],str(fp.relative_to(ROOT)))).hexdigest()==EXPECTED
    workers=data['workers'];assert len(workers)==2 and workers[0]['pid']!=workers[1]['pid'];modules=[]
    for number,worker in enumerate(workers):
        assert worker['exit_code']==0 and not worker['forced_cleanup'] and worker['timing_hooks']==bool(number)
        runtime=read(folder/worker['runtime_file']);assert runtime['pid']==worker['pid'] and runtime['failure'] is None
        assert runtime['audit_timing_hooks']==bool(number) and runtime['recover_context'] is True and runtime['actual_llm_or_gpu'] is False
        for source in runtime['module_sources'].values():assert frozen['sha256'][str(Path(source['path']).relative_to(ROOT))]==source['sha256']
        assert len(runtime['module_sources'])==worker['runtime_modules_bound'];modules.append(len(runtime['module_sources']))
        if number:
            for row in runtime['timing_hook_events']:assert data['timing_evidence'][row['event']+'.json']==row
    turns=case['turns'];assert len(turns)==2 and [t['terminal'] for t in turns]==['result','cancelled']
    for turn,worker in zip(turns,workers,strict=True):
        assert turn['app_pid']==worker['pid']
        kind,result,observed,raw=events(BytesIO(turn['raw_sse'].encode()),time.perf_counter());assert kind==turn['terminal'] and result==turn['result'] and raw==turn['raw_sse']
        assert [(e['event'],e['id'],e['data']) for e in observed]==[(e['event'],e['id'],e['data']) for e in turn['events']]
    ids=turns[0]['result']['conversation'];uid=ids['user_message_id'];aid=ids['assistant_message_id'];timing=data['timing_evidence']
    assert not any('ready' in name or 'token' in row for name,row in timing.items())
    schedule=['read-held','stream-subscribed','writer-begin-intent','release-read','read-released','boundary-wait-after-source-commit','writer-done','boundary-released-after-forget']
    # Writer may commit before the boundary enters its wait; only causally
    # required order is asserted. The callback is before SQLite acquires its lock.
    n=lambda event:timing[event+'.json']['monotonic_ns']
    assert n('read-held')<n('stream-subscribed')<n('writer-begin-intent')<n('release-read')<n('read-released')<n('writer-done')<n('boundary-released-after-forget')
    assert n('read-released')<n('boundary-wait-after-source-commit')<n('boundary-released-after-forget')
    held=timing['read-held.json'];assert held['transaction_held'] and set(held['source_ids'])=={uid,aid} and held['current_user_id']==3
    assert timing['read-released.json']['transaction_held'] and timing['writer-begin-intent.json']['statement'].strip().upper()=='BEGIN IMMEDIATE'
    assert not timing['writer-done.json'].get('cleanup_release') and not timing['release-read.json'].get('cleanup_release')
    checks={r['name']:r for r in case['checks']};assert len(checks)==5 and all(r['passed'] for r in checks.values())
    assert checks['writer_waits_while_source_lock_held']['evidence']['writer_finished'] is False
    snapshots={}
    for ref in case['snapshots']:
        path=folder/ref['file'];assert digest(path)==ref['sha256'];snapshots[ref['label']]=read(path)
    before=snapshots['before-interleaving'];after=snapshots['after-interleaving'];final=snapshots['final']
    assert before['memory_context_revision'][0]['revision']==held['revision']==0
    assert after['memory_context_revision'][0]['revision']==timing['writer-done.json']['revision']==1
    assert {uid,aid}<={r['id'] for r in after['memory_messages'] if r['content']=='[redacted]'}
    assert len(after['memory_messages'])==3 and after['memory_messages'][-1]['role']=='user' and not after['memory_chat_results']
    assert not after['memory_reminders'] and not after['memory_action_receipts']
    rows=case['model_requests'];assert len(rows)==2 and Counter(r['kind'] for r in rows)=={'cognitive':1,'generation':1}
    for row in rows:
        assert row['outcome']=='completed' and row['actual_llm_or_gpu'] is False
        assert json.loads(row['raw_request_json'])==row['request'] and sha256(row['raw_request_json'].encode()).hexdigest()==row['request_sha256']
        assert row['request']['messages'][-1]['content']==turns[0]['input']
        chunks=[json.loads(line[6:]) for line in row['raw_http_body'].splitlines() if line.startswith('data: ') and line!='data: [DONE]']
        assert ''.join(c['choices'][0]['delta'].get('content','') for c in chunks)==row['reply']
        if row['kind']=='generation':assert row['reply']==turns[0]['result']['reply']
    conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
    try:
        conn.executescript((folder/case['id']/'database_dump.sql').read_text())
        for name,expected in final.items():
            actual=[dict(r) for r in conn.execute('SELECT * FROM "'+name.replace('"','""')+'"')]
            assert Counter(normalized(r) for r in actual)==Counter(normalized(r) for r in expected)
    finally:conn.close()
    result={'verified':True,'raw_sha256':digest(folder/'race.json'),'verifier_sha256':digest(Path(__file__)),'freeze_sha256':EXPECTED,
        'historical_inputs':len(frozen['sha256']),'current_inputs_match':all(digest(ROOT/n)==v for n,v in frozen['sha256'].items()),
        'explicit_instrumentation':True,'actual_app_processes':2,'actual_modules_bound_each':modules,'submitted':2,'results':1,'cancelled':1,
        'controlled_model_http_calls':2,'race_turn_model_http_calls':0,'revision_before':0,'revision_after':1,'schedule':[{'event':s,'ns':n(s)} for s in schedule],
        'source_write_lock_and_writer_begin_intent_bound':True,'sql_export_roundtrip':True,'actual_llm_or_gpu':False,'natural_race_frequency_claim':False}
    out=BASE/'审计/工作目录/004-上下文读取隐私事务交错/独立事务交错核验.json';assert not out.exists();out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('Verified actual2-app delegated schedule/source write lock,revision0->1,source redaction,SSE cancellation and0 race-turn model calls.')


if __name__=='__main__':verify()
