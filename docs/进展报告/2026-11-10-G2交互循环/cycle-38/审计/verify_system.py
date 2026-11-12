"""Reconstruct retired C38 native and scripted evidence without model calls.

Wire parsing and plan validation reuse their frozen pure implementations; this
is an independent archival cross-check, not an independent semantic judge or a
second wire parser. The completed native source set is historical, never renewed.
"""
from contextlib import closing
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
WORK = BASE/'审计/工作目录/003-原生开发配对'
ENGINEERING = BASE/'审计/工作目录/002-工程全量'
sys.path.insert(0, str(ROOT/'scripts'))
from native_wire_relay import parse_wire
from evaluate_native_output_audit import validate_provider_identity
from avatar.brain.reminders import CHINA
from avatar.lab.typed_capability_gate import SourceSnapshot, UserSource, parse_plan, render_unavailable, PLAN_RESPONSE_FORMAT
from check_research_names import undefined_globals


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def history(ref, names):
    raw = subprocess.check_output(['git','archive','--format=tar',ref,'--',*sorted(names)],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        return {m.name:hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in archive if m.isfile()}


def parse_events(raw):
    result=[]
    for block in raw.split('\n\n'):
        lines=block.splitlines()
        kind=next((line[6:].strip() for line in lines if line.startswith('event:')),'message')
        text='\n'.join(line[5:].lstrip() for line in lines if line.startswith('data:'))
        if text:
            result.append((kind,json.loads(text)))
    return result


def reconstruct_group(n, frozen):
    folder=BASE/'实验'/f'paired-4b-r{n}-handoff-fixed'
    report=read(folder/'evaluation.json')
    assert report['completed'] and report['engineering_passed'] and report['cleanup_passed'] and report['failure'] is None
    assert report['provider_exit']==report['sampler_exit']==0 and report['relay_closed'] and not report['forced_sampler_cleanup']
    assert report['frozen_inputs']==frozen and report['freeze_sha256']==digest(WORK/'execution-freeze-handoff-fixed.json')
    assert history(report['source_ref'],frozen['sha256'])==frozen['sha256']
    assert report['native_finish_counts']=={'stop':99} and not report['quality_truncations']
    ready=read(folder/'provider-ready.json')
    validate_provider_identity(ready,read(ROOT/frozen['protocol']))
    assert ready['pid']==report['provider_pid'] and ready['chosen_gpu']==report['chosen_gpu']
    assert digest(folder/'provider-ready.json')==report['provider_ready_sha256']
    runtime=read(WORK/'native-runtime.json')
    assert len(runtime['files_sha256'])==54
    assert report['runtime_before']['files_sha256']==report['runtime_after']['files_sha256']==runtime['files_sha256']
    assert not Path('/proc',str(report['provider_pid'])).exists() and not Path('/proc',str(report['sampler_pid'])).exists()
    wire=[json.loads(line) for line in (folder/'wire.jsonl').read_text().splitlines()]
    trace=[json.loads(line) for line in (folder/'provider-trace.jsonl').read_text().splitlines()]
    assert len(wire)==len(trace)==report['native_calls']==99
    parsed=[]
    for index,(row,native) in enumerate(zip(wire,trace,strict=True)):
        assert row['ordinal']==index+1 and row['actual_native'] is True
        assert json.loads(row['raw_request_json'])==row['request']
        assert hashlib.sha256(row['raw_request_json'].encode()).hexdigest()==row['request_body_sha256']==native['request_body_sha256']
        assert hashlib.sha256(row['raw_http_body'].encode()).hexdigest()==row['response_body_sha256']
        value=parse_wire(row)
        parsed.append(value)
        assert value['reply']==native['response'] and value['id']==native['id'] and value['finish_reason']==native['finish_reason']=='stop'
        assert native['messages']==row['request']['messages'] and native['outcome']=='completed'
        fmt=row['request'].get('response_format')
        canonical=lambda value:hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest() if value is not None else None
        assert native['response_format']==fmt and native['response_format_sha256']==canonical(fmt)
        assert native['response_schema_sha256']==canonical(fmt['json_schema']['schema'] if fmt else None)
        assert native['grammar_enabled']==bool(fmt)
    sample=read(folder/'sample/sample.json')
    assert sample['completed'] and sample['engineering_passed'] and sample['failure'] is None
    assert sample['freeze_sha256']==report['freeze_sha256'] and sample['frozen_inputs']==frozen
    assert history(sample['head'],frozen['sha256'])==frozen['sha256']
    protocol=read(ROOT/frozen['protocol'])
    expected_order=[]
    for index,case in enumerate(protocol['development_cases']):
        expected_order.extend((case['id'],arm) for arm in (['baseline','candidate'] if (index+n)%2 else ['candidate','baseline']))
    assert [(a['id'],a['arm']) for a in sample['arms']]==expected_order
    review=read(BASE/f'审计/工作目录/004-原生语义审阅/r{n}-span-review.json')
    assert review['source_sample_sha256']==digest(folder/'sample/sample.json')
    assert review['source_evaluation_sha256']==digest(folder/'evaluation.json')
    assert review['source_wire_sha256']==digest(folder/'wire.jsonl')
    annotations={(r['case'],r['arm'],r['turn']):r for r in review['rows']}
    assert len(annotations)==44 and review['candidate_development_conjunction_passed'] is False
    ordinals=[]
    counts={'warmup':2,'cognitive':0,'generation':0,'plan':0}
    parsed_plans=invalid_plans=exemptions=fixed=0
    actual={}
    for arm in sample['arms']:
        assert arm['completed'] and not arm['failure'] and arm['server_closed']
        case=next(c for c in protocol['development_cases'] if c['id']==arm['id'])
        assert [t['input'] for t in arm['turns']]==case['turns']
        for module in arm['runtime_modules'].values():
            path=Path(module['path'])
            assert path.is_relative_to(ROOT/'src') and module['sha256']==frozen['sha256'][str(path.relative_to(ROOT))]
        dump=folder/'sample'/(arm['id']+'-'+arm['arm']+'.sql')
        assert digest(dump)==arm['sql_dump_sha256']
        with closing(sqlite3.connect(':memory:')) as conn:
            conn.row_factory=sqlite3.Row
            conn.executescript(dump.read_text())
            stored=[dict(r) for r in conn.execute("SELECT id,content FROM memory_messages WHERE role='assistant' ORDER BY id")]
            assert stored==arm['turns'][-1]['stored_assistants']
            assert [dict(r) for r in conn.execute('SELECT * FROM memory_reminders')]==arm['turns'][-1]['reminders']
            assert [dict(r) for r in conn.execute('SELECT * FROM memory_action_receipts')]==arm['turns'][-1]['actual_local_receipts']
        for index,turn in enumerate(arm['turns']):
            key=(arm['id'],arm['arm'],index+1)
            annotation=annotations[key]
            result=turn['result']
            assert turn['terminal']=='result' and not result['tool_calls']
            assert annotation['input']==turn['input'] and annotation['reply']==result['reply']
            assert annotation['generation_mode']==result['generation_mode']
            assert annotation['actual_reminder_count']==len(turn['reminders'])
            span=annotation['span']
            if span:
                assert result['reply'][span['start_codepoint']:span['end_codepoint']]==span['text']
            events=parse_events(turn['raw_sse'])
            assert [r for kind,r in events if kind=='result']==[result]
            assert ''.join(r['text'] for kind,r in events if kind=='text')==turn['visible']
            assert turn['final_display_reply']==result['reply']==turn['stored_assistants'][-1]['content']
            if result['generation_mode'] in ('llm','reviewed_response'):
                assert turn['visible']==result['reply']
            else:
                assert turn['visible'] in ('',result['reply'])
            expected=1 if arm['id']=='c38_reminder' else 0
            assert len(turn['reminders'])==expected
            if expected:
                reminder=turn['reminders'][0]
                assert reminder['title']=='整理观测记录' and datetime.fromtimestamp(reminder['due_at'],CHINA).hour==10
                assert len(turn['actual_local_receipts'])==1 and turn['actual_local_receipts'][0]['action']=='reminder.created'
            requests=[]
            for ordinal in turn['native_ordinals']:
                ordinals.append(ordinal)
                request=wire[ordinal-1]['request']
                schema=request.get('response_format',{}).get('json_schema',{}).get('name')
                kind='plan' if schema=='avatar_lab_action_plan_v1' else 'cognitive' if schema=='avatar_cognitive_analysis' else 'generation'
                counts[kind]+=1
                requests.append((kind,ordinal))
                if kind!='plan':
                    assert request['messages'][-1]['content']==turn['input']
            gens=[i for kind,i in requests if kind=='generation']
            plans=[i for kind,i in requests if kind=='plan']
            metadata=result.get('response_review')
            if result['generation_mode'] in ('llm','reviewed_response'):
                assert len(gens)==1
                if metadata:
                    assert metadata['original_draft']==parsed[gens[0]-1]['reply']
            else:
                assert not gens
            if arm['arm']=='baseline':
                assert metadata is None and not plans
            elif metadata:
                assert metadata['current_source_id']==result['conversation']['user_message_id']
                assert metadata['revision']==result['conversation']['revision']==0
                assert not metadata['native_model_improvement_claim']
                if metadata['plan_raw'] is None:
                    exemptions+=1
                    assert not plans and metadata['plan_error']=='out_of_bounded_real_source_scope'
                else:
                    assert len(plans)==1 and parsed[plans[0]-1]['reply']==metadata['plan_raw']
                    request=wire[plans[0]-1]['request']
                    assert request['response_format']==PLAN_RESPONSE_FORMAT
                    payload=json.loads(request['messages'][-1]['content'])
                    assert payload['current_message_id']==metadata['current_source_id'] and payload['current_question']==turn['input']
                    sources={r['id']:r for r in turn['user_sources']}
                    assert all(p['text']==sources[p['id']]['content'] for p in payload['user_sources'])
                    assert all(hashlib.sha256(sources[p['id']]['content'].encode()).hexdigest()==p['sha256'] for p in metadata['sources'])
                    snapshot=SourceSnapshot(metadata['revision'],metadata['current_source_id'],result['conversation']['session_id'],
                        tuple(UserSource(p['id'],p['text']) for p in payload['user_sources']),
                        result['speaker_attribution']['scope'],result['speaker_attribution']['turn_tools_allowed'],payload['source_window_has_more'])
                    try:
                        plan=parse_plan(metadata['plan_raw'],snapshot)
                    except ValueError as error:
                        invalid_plans+=1
                        assert metadata['plan'] is None and metadata['plan_error']=='ValueError: '+str(error)
                        assert result['reply']==metadata['original_draft'] and not metadata['fixed_renderer_used']
                    else:
                        parsed_plans+=1
                        assert metadata['plan']==plan and metadata['plan_error'] is None
                        if plan['route']!='ordinary':
                            fixed+=1
                            assert metadata['fixed_renderer_used'] and result['reply']==render_unavailable(plan)
                            assert metadata['source_message_ids']==sorted({metadata['current_source_id'],plan['source_message_id']})
            actual[key]={'reply':result['reply'],'original_draft':metadata['original_draft'] if metadata else None,
                'plan_raw':metadata['plan_raw'] if metadata else None,'plan_error':metadata['plan_error'] if metadata else None,
                'generation_mode':result['generation_mode'],'requests':[wire[i-1]['request_body_sha256'] for _,i in requests],
                'native_text':[parsed[i-1]['reply'] for _,i in requests]}
    assert sorted(ordinals)==list(range(3,100)) and len(actual)==44
    assert counts==report['native_kind_counts']=={'warmup':2,'cognitive':42,'generation':38,'plan':17}
    assert (parsed_plans,invalid_plans,exemptions,fixed)==(8,9,2,8)
    assert digest(folder/'sample/sample.json')==report['sample_sha256']
    assert digest(folder/'wire.jsonl')==report['wire_sha256'] and digest(folder/'provider-trace.jsonl')==report['native_trace_sha256']
    return {'repetition':n,'evaluation_sha256':digest(folder/'evaluation.json'),'application_results':44,
        'native_calls':99,'kind_counts':counts,'valid_plans':8,'rejected_plans':9,'scope_exemptions_no_plan':2,
        'fixed_final_responses':8,'sql_dumps_reconstructed':24,'actual_runtime_modules_per_arm':57,
        'gpu':report['chosen_gpu'],'provider_pid':report['provider_pid'],'sampler_pid':report['sampler_pid'],
        'review_sha256':digest(BASE/f'审计/工作目录/004-原生语义审阅/r{n}-span-review.json'),'findings':review['findings']},actual


def main():
    out=BASE/'审计/收尾核验/system-evidence.json'
    assert not out.exists()
    freeze=WORK/'execution-freeze-handoff-fixed.json'
    assert digest(freeze)=='e831a36568b7e47c55ab7f7477c51640187597fa98df87974a6638a066e58a76'
    frozen=read(freeze)
    assert len(frozen['sha256'])==336 and history(frozen['source_ref'],frozen['sha256'])==frozen['sha256']
    assert all(digest(ROOT/n)==sha for n,sha in frozen['sha256'].items())
    retirement=read(WORK/'execution-freeze-handoff-fixed-retirement.json')
    assert retirement['actual_app_results']==132 and retirement['actual_native_calls']==297 and not retirement['candidate_promotion']
    rows=[]
    aligned={}
    for n in (1,2,3):
        row,actual=reconstruct_group(n,frozen)
        rows.append(row)
        aligned[n]=actual
    repeatability=[]
    for n in (2,3):
        assert aligned[n]==aligned[1]
        repeatability.append({'reference':1,'compared':n,'case_arm_turns':44,'identical_final_draft_plan_and_errors':44,
            'aligned_quality_request_sha_equal':97,'aligned_quality_native_text_equal':97,
            'whole_global_order_same':n==3,'independent_sample_or_physical_state_identity_claim':False})
    binding_rows=[]
    for tag in ('typed-gate','admission'):
        p=ENGINEERING/(tag+'-python-final-binding.json')
        d=read(p)
        assert d['exit_code']==0 and d['source_unchanged'] and len(d['source_git_sha256'])==434
        assert history(d['head'],d['source_git_sha256'])==d['source_git_sha256']
        assert digest(ENGINEERING/(tag+'-python-final.log'))==d['log_sha256']
        driver=str((BASE/'审计/run_regression.py').relative_to(ROOT))
        assert history(d['head'],[driver])[driver]==d['driver_sha256']
        if tag=='admission':
            assert all(digest(ROOT/n)==sha for n,sha in d['source_git_sha256'].items())
        binding_rows.append({'tag':tag,'sha256':digest(p),'head':d['head'],'source_count':434})
    # First prototype's historical source identity is preserved rather than
    # rewritten to the repaired controller or its later 336-input freeze.
    old=read(WORK/'execution-freeze.json')
    assert digest(WORK/'execution-freeze.json')=='d82548fa3e87c6ba120769e84da43add7c837b68c23a7ace87d9a5f40f9b76f0'
    assert len(old['sha256'])==333 and history(old['source_ref'],old['sha256'])==old['sha256']
    failed=read(BASE/'实验/paired-4b-r1/evaluation.json')
    assert failed['native_calls']==failed['application_results']==0 and failed['sampler_pid'] is None
    assert failed['cleanup_passed'] and failed['provider_exit']==0 and 'relay_metadata' in failed['failure']
    assert not Path('/proc',str(failed['provider_pid'])).exists()
    scripted=[]
    for suffix,app,calls in [('',29,70),('-framework-fixed',44,97),('-scope-label',44,97)]:
        p=ENGINEERING/('controlled-sampler-preflight'+suffix)/'evaluation.json'
        d=read(p)
        assert d['provider_closed'] and d['native_or_gpu_calls']==0
        assert sum(len(a['turns']) for a in d['arms'])==app and len(d['fixture_requests'])==calls
        assert bool(d['failure'])==(suffix=='')
        assert all(a['server_closed'] for a in d['arms'])
        wire=[json.loads(line) for line in (p.parent/'wire.jsonl').read_text().splitlines()]
        assert len(wire)==calls and all(not r['actual_native'] for r in wire)
        for r in wire:
            assert parse_wire(r)['finish_reason']=='stop'
        scripted.append({'namespace':p.parent.name,'sha256':digest(p),'actual_app_results':app,'controlled_HTTP_calls':calls,'completed':d['completed']})
    kernel=[]
    for n in (1,3):
        p=WORK/f'native-r{n}-handoff-fixed-kernel-launch.json'
        d=read(p)
        report=read(BASE/f'实验/paired-4b-r{n}-handoff-fixed/evaluation.json')
        assert d['actual_argv']==report['sampler_argv'] and d['sampler_pid']==report['sampler_pid']
        assert digest(Path(d['provider_metadata_path']))==d['provider_metadata_sha256']
        kernel.append({'repetition':n,'sha256':digest(p),'actual_kernel_capture':True})
    assert read(WORK/'native-r2-handoff-fixed-kernel-observation.json')['additional_kernel_cmdline_capture_available'] is False
    seals=[]
    for p in sorted(BASE.parent.glob('cycle-*/审计/证据清单.json')):
        if int(p.parents[1].name[6:])>=38:
            continue
        assert all(digest(p.parents[1]/n)==sha for n,sha in read(p).items())
        seals.append({'cycle':p.parents[1].name,'items':len(read(p)),'sha256':digest(p)})
    assert len(seals)==35 and sum(r['items'] for r in seals)==6124
    assert seals[-1]['sha256']=='f76e5bb390b80aff83a5ef4f43ea5a017acb14cc427e36a87542eff50d0c3416'
    migration=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/证据清单.json'
    assert digest(migration)=='717af4a7f8b0aaf95ea129171fc7d5a2300c58f66b58e0ea9db2cc7617302392'
    assert all(digest(migration.parent/n)==sha for n,sha in read(migration).items())
    links=json.loads(subprocess.check_output(['python3','-B','scripts/link_project_assets.py','--check'],cwd=ROOT,text=True))
    assert len(links)==9 and all(r['valid'] for r in links)
    assert not undefined_globals(Path(__file__).read_text(),str(Path(__file__)))
    result={'verified':True,'source_ref':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(Path(__file__)),'scope':'historical native/current software reconstruction; reused frozen pure parser/plan validation, not independent semantics',
        'retired_native_frozen_inputs':336,'current_software_selected_inputs':434,'native_groups':rows,
        'actual_app_results':132,'actual_native_calls':297,'kind_counts':{'warmup':6,'cognitive':126,'generation':114,'plan':51},
        'actual_GPU_provider_loads':4,'zero_request_failed_loads':1,'failed_group_native_calls':0,
        'repeatability':repeatability,'python_bindings':binding_rows,'scripted_preflights':scripted,
        'scripted_app_results_including_failure':117,'scripted_HTTP_calls':264,'kernel_observations':kernel,
        'kernel_observation_missing_repetition':2,'old_cycle_seals':seals,'old_seals_including_migration':36,
        'old_entries_including_migration':6212,'data_links':links,'closed_issues':['C38-001','C38-002','C38-003'],
        'open_issues':['C38-004','C38-005','C38-006'],'candidate_development_conjunction_passed':False,
        'protected_executed':False,'candidate_or_production_promotion':False,'new_native_calls_during_reconstruction':0}
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C38 system reconstruction:132app/297native;72SQLdumps;434current/336historical;117scripted/264HTTP;36oldseals;candidate REJECTED')


if __name__=='__main__':
    main()
