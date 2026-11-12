"""C40 independent archival/current/HTTP-SDK-template and native counter audit."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from native_common import ROOT,BASE,WORK,PROTOCOL,REGISTRY,RUNTIME,read,digest,historical,environment_python,environment,capture_runtime
from avatar.lab.native_tool_wire import adapt_completion

OUT=BASE/'审计/收尾核验/system-evidence.json'


def main():
    assert not OUT.exists()
    protocol=read(PROTOCOL);runtime=read(RUNTIME)
    assert capture_runtime()==runtime
    sources=[];native=[];all_rows=[];native_runtime=[]
    for suffix,label,count,changed in [('', 'native-wire-4b',2,{'run_wire.py','native_common.py'}),('-sse-fixed','native-wire-4b-sse-fixed',38,set())]:
        descriptor=WORK/('execution-freeze'+suffix+'.json');frozen=read(descriptor)
        expected='c97dbb02ddca0cd84682ac2033d6a36521b4d254c16e0973715afb108130566c' if not suffix else '1c7181a512d1591e1917d7d7c47e5b76f8bae74e3af91b4e4a945bfaee2fb02e'
        assert digest(descriptor)==expected and len(frozen['sha256'])==(352 if not suffix else 354)
        assert historical(frozen['source_ref'],frozen['sha256'])==frozen['sha256']
        delta={Path(n).name for n,sha in frozen['sha256'].items() if digest(ROOT/n)!=sha}
        assert delta==changed,delta
        retire=read(WORK/('execution-freeze'+suffix+'-retirement.json'))
        assert retire['freeze_sha256']==expected
        group=BASE/'实验'/label;evaluation=read(group/'evaluation.json');ready=read(group/'provider-ready.json')
        assert retire['evaluation_sha256']==digest(group/'evaluation.json') and retire['trace_sha256']==digest(group/'provider-trace.jsonl')
        assert evaluation['source_current_after_execution'] and evaluation['cleanup_passed'] and evaluation['provider_exit_code']==0
        assert evaluation['native_calls']==count and evaluation['native_raw_stop_count']==count
        assert not Path('/proc/'+str(evaluation['provider_pid'])).exists()
        assert all(digest(group/n)==sha for n,sha in evaluation['artifacts_sha256'].items())
        assert ready['model_sha256']==read(REGISTRY)['models'][0]['sha256'] and ready['registry_sha256']==digest(REGISTRY)
        assert ready['backend']=='cuda' and ready['tool_adapter_enabled'] and ready['process_gpu_mib_after_load']==[4096]
        assert ready['effective_visible_devices']==ready['chosen_gpu']['uuid']
        assert ready['provider_source_sha256']==frozen['sha256']['scripts/serve_local_model_eval.py']
        assert ready['tool_adapter_source_sha256']==frozen['sha256']['src/avatar/lab/native_tool_wire.py']
        kernel=read(group/'provider-kernel-proof.json')
        assert kernel['cmdline']==evaluation['provider_command'] and kernel['pid']==ready['pid']==evaluation['provider_pid']
        assert any(str(ready['pid'])==l.split(',')[0].strip() and ready['chosen_gpu']['uuid'] in l for l in kernel['gpu_processes'].splitlines())
        assert any('libggml-cuda.so' in n for n in kernel['mapped_frozen_libraries'])
        assert all(runtime['files_sha256'][n]==sha==digest(Path(n)) for n,sha in kernel['mapped_frozen_libraries'].items())
        actual_modules=evaluation['actual_project_modules']
        assert all(row['sha256']==frozen['sha256'][row['file']] for row in actual_modules.values())
        rows=[json.loads(line) for line in (group/'provider-trace.jsonl').read_text().splitlines()]
        assert len(rows)==count and all(r['finish_reason']=='stop' and r['outcome']=='completed' for r in rows)
        all_rows+=rows
        wire=[json.loads(line) for line in (group/'request-wire.jsonl').read_text().splitlines()]
        responses=[json.loads(line) for line in (group/'response-wire.jsonl').read_text().splitlines()]
        assert len(wire)==len(responses)==(1 if not suffix else 38)
        for q,r,response in zip(wire,rows,responses):
            assert q['request_body_sha256']==r['request_body_sha256']
            assert q['request']['messages']==r['messages'] and q['request'].get('tools')==r['tools']
            assert q['request']['temperature']==0 and q['request']['max_tokens'] in (32,256)
            assert response['status']==200
            if not r['stream']:
                message,finish=adapt_completion(r['response'],r['finish_reason'],r['tools'],r['id'])
                choice=response['body']['choices'][0]
                assert choice['message']==message==r['wire_message']
                assert choice['finish_reason']==finish==r['wire_finish_reason']
        if not suffix:
            assert not evaluation['completed'] and not evaluation['groups']
            assert 'SDK retry/missing request' in evaluation['failure'] and len(evaluation['warmups'])==1
            assert rows[1]['stream'] and rows[1]['response']=='预热完成。'
        else:
            assert evaluation['completed'] and evaluation['engineering_passed'] and not evaluation['wire_expected_gate_passed']
            assert evaluation['wire_selection_exact_count']==21 and evaluation['wire_selection_total']==24 and evaluation['synthetic_fixture_followups']==9
            assert len(evaluation['groups'])==3 and len(evaluation['warmups'])==2
            stream=evaluation['warmups'][1];events=stream['sdk_stream_events']
            assert ''.join(c['delta'].get('content') or '' for e in events for c in e['choices'])==rows[1]['response']==stream['result']['content']
            assert [c['finish_reason'] for e in events for c in e['choices'] if c['finish_reason'] is not None]==['stop']
            for repeated in evaluation['groups']:
                rep=repeated['repetition'];assert read(group/f'repetition-{rep}.json')==repeated
                assert len(repeated['cases'])==8 and sum(c['exact_expected_selection'] for c in repeated['cases'])==7
                for case,actual_case in zip(protocol['cases'],repeated['cases']):
                    q=wire[actual_case['request_ordinal']-1];r=rows[actual_case['request_ordinal']-1]
                    assert q['context']=={'phase':'selection','repetition':rep,'case':case['id']}
                    assert q['request']['messages']==[{'role':'system','content':protocol['system']},{'role':'user','content':case['text']}]
                    assert q['request']['tools']==protocol['tools']
                    assert actual_case['result'].get('tool_calls',[])==r['wire_message'].get('tool_calls',[])
                    if case['id']=='policy-exit':
                        call=actual_case['result']['tool_calls'][0]['function']
                        assert call['name']=='read_reminder_state' and json.loads(call['arguments'])=={'reminder_id':12345}
                        assert '12345' not in case['text'] and actual_case['followup'] is None
                    if actual_case['followup']:
                        follow=actual_case['followup'];fq=wire[follow['request_ordinal']-1]
                        assert fq['context']=={'phase':'fixture-followup','repetition':rep,'case':case['id']}
                        assert json.loads(fq['request']['messages'][-1]['content'])==case['fixture']|{'synthetic_fixture':True}
                        assert follow['result']['content']==rows[follow['request_ordinal']-1]['response'] and not follow['result'].get('tool_calls')
            # Exact repeated output/selected calls: compare content and function,
            # excluding transport call IDs, durations and ordinals.
            normalize=lambda g:[{'result':{'content':c['result'].get('content'),'functions':[x['function'] for x in c['result'].get('tool_calls',[])]},'followup':c['followup']['result'] if c['followup'] else None} for c in g['cases']]
            assert normalize(evaluation['groups'][0])==normalize(evaluation['groups'][1])==normalize(evaluation['groups'][2])
        native.append({'label':label,'native_calls':count,'formal_selections':0 if not suffix else 24,'wire_captured':len(wire),'cleanup_passed':True,'sha256':digest(group/'evaluation.json')})
        native_runtime.append({'label':label,'pid':ready['pid'],'gpu':ready['chosen_gpu'],'actual_project_modules':len(actual_modules),'mapped_frozen_libraries':len(kernel['mapped_frozen_libraries'])})
        sources.append({'descriptor':descriptor.name,'sha256':expected,'inputs':len(frozen['sha256']),'source_ref':frozen['source_ref'],'current_historical_delta':sorted(delta),'retired':True})
    # Independently render all 40 real prompts using the actual embedded template,
    # native Jinja and prepared message bytes; this subprocess loads no model.
    code="""import json,sys,hashlib\nfrom pathlib import Path\nfrom jinja2 import Environment,StrictUndefined\nfrom avatar.lab.native_tool_wire import template_messages\ndata=json.load(sys.stdin);env=Environment(undefined=StrictUndefined)\ndef fail(message):raise ValueError(message)\nenv.globals['raise_exception']=fail;t=env.from_string(Path(data['template']).read_text())\nprint(json.dumps([hashlib.sha256(t.render(messages=template_messages(r['messages']),tools=r['tools'],add_generation_prompt=True,enable_thinking=False,bos_token='',eos_token='').encode()).hexdigest() for r in data['rows']]))"""
    python=environment_python(native=True)
    rendered=subprocess.run([str(python),'-c',code],input=json.dumps({'template':str(BASE/'审计/工作目录/001-工具调用调查/embedded-chat-template.jinja'),'rows':all_rows}),text=True,capture_output=True,env=environment(python),check=True)
    assert json.loads(rendered.stdout)==[r['prompt_sha256'] for r in all_rows]
    regress=BASE/'审计/工作目录/004-当前软件与浏览器';bindings=[]
    for mode in ('python','frontend','build','browser'):
        p=regress/f'wire-{mode}-final-binding.json';d=read(p);inputs=d['source_git_sha256']
        assert d['source_unchanged'] and d['exit_code']==0 and len(inputs)==440
        assert historical(d['head'],inputs)==inputs and all(digest(ROOT/n)==sha for n,sha in inputs.items())
        assert d['driver_sha256']==digest(BASE/'审计/run_regression.py') and digest(regress/f'wire-{mode}-final.log')==d['log_sha256']
        bindings.append({'mode':mode,'sha256':digest(p),'head':d['head'],'inputs':440})
    assert '2070 passed, 1 skipped' in (regress/'wire-python-final.log').read_text()
    assert '192 passed (192)' in (regress/'wire-frontend-final.log').read_text()
    assert '18 passed' in (regress/'wire-browser-final.log').read_text() and '16 skipped' in (regress/'wire-browser-final.log').read_text()
    browser=read(regress/'wire-browser-final-runtime.json');current=read(regress/'wire-browser-final-binding.json')['source_git_sha256']
    assert len(browser['module_sha256'])==9
    for name,p in browser['module_paths'].items():assert browser['module_sha256'][name]==current[str(Path(p).relative_to(ROOT))]
    assert browser['state_privacy_protocol_sha256']==current['evals/interaction/cycle-36/maintained-state-privacy-protocol.json']
    assert browser['reminder_query_protocol_sha256']==current['evals/interaction/cycle-39/explicit-reminder-query-protocol.json']
    assert browser['frontend_sha256']==read(regress/'wire-build-final-binding.json')['runtime_artifact_sha256']
    query=read(regress/'full-browser-records/query.json');assert query['completed'] and query['before']==query['after'] and len(query['turns'])==2
    for turn in query['turns']:assert turn['visible']==turn['result']['reply'] and turn['result']['generation_mode']=='rules_reminder_query'
    for which in ('emotion','dashboard'):
        p=read(regress/('full-browser-records/'+which+'.json'));assert p['completed'] and p['sampleMs']>=1000 and p['sourceAfter']['redacted']
        assert p['afterApi']['context']['revision']==p['beforeApi']['context']['revision']+1
    old=read(BASE/'审计/工作目录/005-系统复核/旧证据与数据布局.json')
    for row in old['cycle_seals']:
        p=BASE.parent/row['cycle']/'审计/证据清单.json';assert digest(p)==row['sha256']
        assert all(digest(p.parents[1]/n)==sha for n,sha in read(p).items())
    assert old['old_seals_including_migration']==38 and old['old_items_including_migration']==6531
    red=read(BASE/'审计/工作目录/002-受控HTTP交接/template-followup-red-source.json')
    assert historical('46b8e91c',red['source_sha256'])==red['source_sha256']
    controlled=[]
    for directory,expected in [('default',1),('opt-in',1),('content-fixed/default',1),('content-fixed/opt-in',5)]:
        group=BASE/'审计/工作目录/002-受控HTTP交接'/directory
        rows=[json.loads(line) for line in (group/'provider-trace.jsonl').read_text().splitlines()]
        calls=[r for r in rows if r.get('id')];assert len(calls)==expected
        controlled.append({'group':directory,'scripted_completions':len(calls),'native_or_GPU_calls':0})
    assert read(WORK/'sse-controlled.json')['native_or_GPU_calls']==0 and read(WORK/'sse-controlled.json')['scripted_HTTP_streams']==1
    result={'verified':True,'source_ref':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'verifier_sha256':digest(Path(__file__)),
        'scope':'native tool-wire diagnostic only; synthetic fixtures; no Avatar/business read or semantic promotion',
        'retired_source_descriptors':sources,'native_groups':native,'native_total':40,'native_raw_stop_total':40,'formal_selections':24,'expected_exact_selections':21,'synthetic_fixture_followups':9,
        'native_wire_adapter_tool_calls':12,'native_warmed_complete_group_calls':38,'all_native_prompts_independently_rendered':40,'runtime_identity_files':54,'native_runtime':native_runtime,
        'repeated_outputs_identical':True,'semantic_gate_approved':False,'Avatar_application_turns':0,'business_reads_or_writes':0,
        'controlled_groups':controlled,'scripted_completions_total':8,'scripted_SSE_streams_extra':1,'current_software_bindings':bindings,'current_source_count':440,
        'full_python':'2070 passed/1 skipped','frontend':'192 passed','browser':'18 passed/16 optional skipped','browser_modules':9,'current_maintained_browser_results':5,
        'old_cycle_seals':old['cycle_seals'],'old_seals_including_migration':38,'old_entries_including_migration':6531,
        'closed_issues':['C40-001','C40-002','C40-003','C40-004'],'open_issues':['C40-005'],'protected_execution':False,'goal_remains_active':True}
    OUT.parent.mkdir(exist_ok=True);OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C40 system verified:40native/40stop,40prompt renders,21/24routegate FAILED;440current;2070/1,192,18/16;38oldseals')


if __name__=='__main__':main()
