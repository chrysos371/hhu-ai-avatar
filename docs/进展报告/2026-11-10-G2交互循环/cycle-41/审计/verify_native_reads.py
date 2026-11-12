"""Prewritten independent native/SQLite branch reconciliation and protected gate."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from native_common import ROOT,BASE,WORK,PROTOCOL,REGISTRY,RUNTIME,read,digest,historical,environment_python,environment
from avatar.brain.reminders import CHINA
from avatar.brain.speaker_scope import SpeakerScope
from avatar.lab.native_tool_wire import adapt_completion
from avatar.lab.trusted_local_read import parameter_basis, _POLICY
from sample_reads import canonical


def verify(output,partition,freeze,expected,proof_output=None):
    output=Path(output).resolve();freeze=Path(freeze)
    proof_output=Path(proof_output) if proof_output else WORK/(partition+'-verification.json')
    assert output.parent==BASE/'实验' and not proof_output.exists()
    frozen=read(freeze);protocol=read(PROTOCOL);report=read(output/'evaluation.json')
    assert digest(freeze)==expected==report['freeze_sha256'] and frozen['allowed_partition']==partition
    assert historical(frozen['source_ref'],frozen['sha256'])==frozen['sha256']
    assert all(digest(ROOT/n)==sha for n,sha in frozen['sha256'].items())
    assert report['completed'] and report['cleanup_passed'] and report['provider_exit_code']==0
    assert not Path('/proc/'+str(report['provider_pid'])).exists()
    assert all(digest(output/n)==sha for n,sha in report['artifacts_sha256'].items())
    ready=read(output/'provider-ready.json');kernel=read(output/'provider-kernel-proof.json')
    assert ready['backend']=='cuda' and ready['model_sha256']==read(REGISTRY)['models'][0]['sha256']
    assert ready['provider_source_sha256']==frozen['sha256']['scripts/serve_local_model_eval.py']
    assert ready['tool_adapter_source_sha256']==frozen['sha256']['src/avatar/lab/native_tool_wire.py']
    assert kernel['cmdline']==report['provider_command'] and kernel['pid']==ready['pid']==report['provider_pid']
    runtime=read(RUNTIME)
    assert all(runtime['files_sha256'][n]==sha==digest(Path(n)) for n,sha in kernel['mapped_frozen_libraries'].items())
    assert any('libggml-cuda.so' in n for n in kernel['mapped_frozen_libraries'])
    assert any(l.split(',')[0].strip()==str(ready['pid']) and ready['chosen_gpu']['uuid'] in l for l in kernel['gpu_processes'].splitlines())
    assert all(item['sha256']==frozen['sha256'][item['file']] for item in report['actual_project_modules'].values())
    rows=[json.loads(line) for line in (output/'provider-trace.jsonl').read_text().splitlines()]
    requests=[json.loads(line) for line in (output/'request-wire.jsonl').read_text().splitlines()]
    responses=[json.loads(line) for line in (output/'response-wire.jsonl').read_text().splitlines()]
    assert len(rows)==len(requests)==len(responses)==report['native_calls']
    assert all(r['outcome']=='completed' and r['finish_reason']=='stop' for r in rows)
    lookup={}
    for row,q,response in zip(rows,requests,responses):
        assert row['request_body_sha256']==q['request_body_sha256'] and row['messages']==q['request']['messages']
        assert row['tools']==q['request'].get('tools') and response['status']==200
        assert q['request']['temperature']==0 and q['request']['max_tokens'] in (32,256)
        key=(q['context']['phase'],q['context']['repetition'],q['context']['case'])
        assert key not in lookup;lookup[key]=(row,q,response)
        if not row['stream']:
            message,finish=adapt_completion(row['response'],row['finish_reason'],row['tools'],row['id'])
            assert response['body']['choices'][0]['message']==message==row['wire_message']
            assert response['body']['choices'][0]['finish_reason']==finish==row['wire_finish_reason']
    stream_events=report['warmups'][1]['SDK_stream_events']
    assert ''.join(c['delta'].get('content') or '' for e in stream_events for c in e['choices'])==rows[1]['response']==report['warmups'][1]['reply']
    template=ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-40/审计/工作目录/001-工具调用调查/embedded-chat-template.jinja'
    assert digest(template)==ready['template_sha256']
    code="""import json,sys,hashlib
from pathlib import Path
from jinja2 import Environment,StrictUndefined
from avatar.lab.native_tool_wire import template_messages
data=json.load(sys.stdin);env=Environment(undefined=StrictUndefined)
def fail(message):raise ValueError(message)
env.globals['raise_exception']=fail;t=env.from_string(Path(data['template']).read_text())
print(json.dumps([hashlib.sha256(t.render(messages=template_messages(r['messages']),tools=r['tools'],add_generation_prompt=True,enable_thinking=False,bos_token='',eos_token='').encode()).hexdigest() for r in data['rows']]))
"""
    python=environment_python(native=True)
    rendered=subprocess.run([str(python),'-c',code],input=json.dumps({'template':str(template),'rows':rows}),text=True,capture_output=True,env=environment(python),check=True)
    assert json.loads(rendered.stdout)==[r['prompt_sha256'] for r in rows]
    cases={c['id']:c for c in protocol[partition+'_cases']}
    sql_results=[];gate_score=repair_score=initial_exact=0;negative_attempts=0;source_gate=True;repair_count=0
    assert len(report['groups'])==(3 if partition=='development' else 1)
    for group in report['groups']:
        rep=group['repetition'];assert group['completed_cases']==len(cases)
        assert read(output/f'repetition-{rep}/evaluation.json')==group
        for case_record in group['cases']:
            case=cases[case_record['case']]
            directory=output/f'repetition-{rep}'/case['id']
            assert read(directory/'evaluation.json')==case_record
            first=case_record['initial_proposal']
            if case_record['case_source_denied']:
                assert not case['expected_scope_allowed'] and case_record['initial_model_calls']==0
                assert ('initial',rep,case['id']) not in lookup
            else:
                row,q,_=lookup['initial',rep,case['id']]
                assert q['request']['messages']==[{'role':'system','content':protocol['initial_system']},{'role':'user','content':case['text']}]
                assert first=={k:v for k,v in row['wire_message'].items() if v is not None}
                attempts=first.get('tool_calls',[])
                if case['tool'] is None:
                    negative_attempts+=bool(attempts);initial_exact+=not attempts
                elif len(attempts)==1:
                    function=attempts[0]['function']
                    initial_exact+=function['name']==case['tool'] and canonical(json.loads(function['arguments']))==canonical(case['args'])
            for mode,b in case_record['branches'].items():
                dump=directory/(mode+'.sql');assert digest(dump)==b['SQL_dump_sha256']
                conn=sqlite3.connect(':memory:');conn.row_factory=sqlite3.Row
                try:
                    conn.executescript(dump.read_text())
                    for table,values in b['business_before'].items():
                        assert [dict(r) for r in conn.execute('SELECT * FROM '+table+' ORDER BY id')]==values==b['business_after'][table]
                    source=conn.execute('SELECT * FROM memory_messages WHERE id=?',(b['source_message_id'],)).fetchone()
                    assert source['role']=='user' and source['content']==case['text'] and source['session_id']==b['session_id']
                    assert conn.execute('SELECT revision FROM memory_context_revision WHERE id=1').fetchone()[0]==b['source_revision']==0
                    scope=SpeakerScope()
                    for message in conn.execute("SELECT * FROM memory_messages WHERE role='user' ORDER BY id"):
                        scope.observe(message['content'],0,source_id=message['id'])
                    assert scope.scope==b['source_scope'] and scope.allows_actions==b['independent_turn_allowed']
                    assert b['business_unchanged'] and b['no_post_source_writes'] and b['total_changes_before']==b['total_changes_after']
                    for event in b['SQL_trace']:
                        if event['phase'] in ('first-execute','retry-execute','publication'):
                            assert not event['sql'].lstrip().upper().startswith(('INSERT','UPDATE','DELETE','REPLACE','CREATE','DROP','ALTER'))
                    for stage in ('first_read','retry_read'):
                        entry=b[stage]
                        if entry is None:continue
                        result=entry['result'];basis=parameter_basis(case['text'],entry['arguments'],entry['tool'])
                        assert result['source_message_id']==source['id'] and result['revision']==0
                        phase='first-execute' if stage=='first_read' else 'retry-execute'
                        selects=[e for e in b['SQL_trace'] if e['phase']==phase and 'FROM memory_reminders r' in e['sql']]
                        if basis:
                            assert not result['ok'] and result['error']['code']==basis and result['data'] is None and not selects
                        elif entry['tool']=='read_reminder_delivery_policy':
                            assert result['ok'] and result['reply']==_POLICY and not selects
                            assert result['data']=={'requires_running_server':True,'web_requires_active_client_polling':True,'external_delivery_channels':[],'human_reading_verified':False}
                        else:
                            assert result['ok'] and len(selects)==1 and type(entry['arguments']['reminder_id']) is int
                            ident=entry['arguments']['reminder_id'];stored=conn.execute('SELECT * FROM memory_reminders WHERE id=?',(ident,)).fetchone()
                            data=result['data'];assert data['id']==ident and data['exists']==(stored is not None) and not data['human_reading_verified']
                            if stored is None:
                                assert data['state'] is None and result['reply']==f'未找到编号{ident}的提醒记录。'
                            else:
                                state=data['state'];assert state=={'title':stored['title'],'status':stored['status'],'due_at':stored['due_at'],'service_claim_recorded':False,'client_ack_recorded':False}
                                label={'active':'有效','cancelled':'已取消','completed':'已完成'}[stored['status']]
                                due=datetime.fromtimestamp(stored['due_at'],CHINA).strftime('%Y-%m-%d %H:%M')
                                expected_reply=(f'编号{ident}，标题{json.dumps(stored["title"],ensure_ascii=False)}：记录状态为{label}，提醒时间为{due}（北京时间）。尚无客户端确认记录。'+_POLICY)
                                assert result['reply']==expected_reply
                    if b['reply_origin']=='trusted_read_fixed':
                        final=b['retry_read'] or b['first_read']
                        assert final['result']['ok'] and b['reply']==final['result']['reply']
                        exact=b['final_tool']==case['tool'] and canonical(b['final_arguments'])==canonical(case['args'])
                    elif not case['expected_scope_allowed']:
                        exact=b['source_cancelled'] and b['reply'] is None and case_record['initial_model_calls']==0
                    elif case['tool'] is None:
                        exact=not first.get('tool_calls') and not b['first_read'] and not b['retry_read']
                        assert b['reply']==first['content']
                    else:
                        exact=False
                    assert bool(exact)==b['final_exact_expected_route']
                    if mode=='gate_only':gate_score+=bool(exact)
                    else:repair_score+=bool(exact)
                    source_gate &= b['business_unchanged'] and b['no_post_source_writes']
                    sql_results.append({'repetition':rep,'case':case['id'],'arm':mode,'dump_sha256':digest(dump),'status_SELECTs':b['business_status_SELECTs'],'reply_origin':b['reply_origin'],'final_exact':bool(exact)})
                finally:conn.close()
                if b.get('retry_proposal') is not None or b.get('retry_error') is not None:
                    repair_count+=1
                    row,q,_=lookup['repair',rep,case['id']]
                    feedback=json.loads(next(m['content'] for m in q['request']['messages'] if m['role']=='tool'))
                    assert feedback=={'ok':False,'error':b['first_read']['result']['error']}
                    assert q['request']['messages'][-1]=={'role':'system','content':protocol['repair_system']}
                    if b['retry_proposal'] is not None:
                        assert b['retry_proposal']=={k:v for k,v in row['wire_message'].items() if v is not None}
            # Both branches share exactly the same model first proposal; no gold
            # is passed into execute. Scoring does not erase the wrong first call.
    assert len(sql_results)==report['lab_branch_outcomes']
    assert gate_score==report['gate_only_final_exact'] and repair_score==report['single_repair_final_exact']
    assert repair_count==report['repair_native_calls'] and report['native_calls']==2+report['initial_native_calls']+repair_count
    assert all(seed['title'] not in canonical(q['request']['messages']) for seed in protocol['seed_rows'] for q in requests)
    total=len(cases)*len(report['groups'])
    passed=(source_gate and report['engineering_passed'] and repair_score==total and negative_attempts==0
            and all(c['scope_matches_expected'] for g in report['groups'] for c in g['cases']))
    result={'verified':True,'selection_and_source_gate_passed':bool(passed),'allowed_partition':partition,
        'output_relative':str(output.relative_to(ROOT)),'freeze_sha256':expected,'source_ref':frozen['source_ref'],
        'verifier_sha256':digest(Path(__file__)),'native_calls':len(rows),'native_raw_stop_count':len(rows),
        'warmups':2,'initial_native_calls':report['initial_native_calls'],'repair_native_calls':repair_count,
        'lab_branch_outcomes':len(sql_results),'SQL_dumps_reconstructed':len(sql_results),'SQL_checks':sql_results,
        'actual_status_SELECTs':sum(r['status_SELECTs'] for r in sql_results),'initial_exact_routes':int(initial_exact),
        'gate_only_final_exact':gate_score,'single_repair_final_exact':repair_score,'cases_total':total,
        'negative_initial_attempts':negative_attempts,'source_and_readonly_gate_passed':bool(source_gate),
        'native_prompt_renders_verified':len(rows),'actual_project_modules':len(report['actual_project_modules']),
        'mapped_frozen_libraries':len(kernel['mapped_frozen_libraries']),'runtime_identity_files':54,
        'evaluation_sha256':digest(output/'evaluation.json'),'default_enabled':False,'physical_or_general_semantic_approval':False}
    proof_output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C41 '+partition+' verified: native='+str(len(rows))+';SQLdumps='+str(len(sql_results))+
          ';candidate='+str(repair_score)+'/'+str(total)+';gate='+str(bool(passed)))
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--partition',choices=('development','protected'),required=True)
    parser.add_argument('--freeze',type=Path,required=True)
    parser.add_argument('--expected-freeze-sha256',required=True)
    args=parser.parse_args()
    verify(args.output,args.partition,args.freeze,args.expected_freeze_sha256)
