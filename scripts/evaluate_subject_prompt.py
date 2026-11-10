"""Preregistered same-provider reply ablations. Candidates remain off by default."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import time

from avatar.brain.llm import LLMEngine
from avatar.cancellation import CancellationToken
from avatar.config import config
from avatar.main import Avatar
from avatar.lab.checks import versioned_rules, check_dialogue_turns
from evaluate_real_interaction import sha, save, checks


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--provider',type=Path,required=True)
    parser.add_argument('--model-key',default='qwen3-4b-q4_k_m')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--policy',type=Path)
    parser.add_argument('--supplemental',type=Path)
    parser.add_argument('--turn-suite',type=Path,help='Run only this prospective per-turn suite')
    parser.add_argument('--regression-suite',type=Path,help='Include a frozen related regression suite before the prospective suite')
    parser.add_argument('--task-delivery',action='store_true',help='Profile/identity fixed on in both arms; task contract and repair only in candidate')
    parser.add_argument('--literal-composition',action='store_true',help='Task checks fixed on in both arms; only candidate uses immutable literal slot repair')
    parser.add_argument('--literal-template',action='store_true',help='Both arms compose literals; baseline v1slots versus candidate v2source-only template')
    parser.add_argument('--profile-grounding',action='store_true',
        help='Compare fixed subject prompt in both arms; candidate also enables narrow profile grounding')
    args=parser.parse_args()
    if sum([args.task_delivery,args.profile_grounding,args.literal_composition,args.literal_template])>1:
        parser.error('Use one comparison mode')
    literal_mode = args.literal_composition or args.literal_template
    task_mode = args.task_delivery or literal_mode
    if args.regression_suite and not args.turn_suite:
        parser.error('Regression companion requires a prospective suite')
    if args.output.exists():raise ValueError('Use a new output file')
    original_path=Path('evals/interaction/cycle-02/real-model-cases.json')
    extra_path=Path('evals/interaction/cycle-02/subject-ownership-dev16.json')
    original=json.loads(original_path.read_text());extra=json.loads(extra_path.read_text())
    policy=json.loads(args.policy.read_text()) if args.policy else None
    supplemental=json.loads(args.supplemental.read_text()) if args.supplemental else {'cases':[]}
    prospective=json.loads(args.turn_suite.read_text()) if args.turn_suite else None
    groups=[('prospective',case) for case in prospective['cases']] if prospective else (
        [('original',case) for case in original['cases']] + [('additional',case) for case in extra['cases']]
        + [('supplemental',case) for case in supplemental['cases']])
    regression=json.loads(args.regression_suite.read_text()) if args.regression_suite else None
    if regression:
        groups=[('regression',case) for case in regression['cases']] + groups
    provider=json.loads(args.provider.read_text())
    registry=json.loads(Path('evals/interaction/cycle-02/model-scale-protocol.json').read_text())
    selected=next(item for item in registry['models'] if item['model_id']==args.model_key)
    assert provider['model_revision']==selected['revision'] and provider['model_sha256']==selected['sha256']
    assert provider.get('model_id','qwen3-4b-q4_k_m')==args.model_key
    assert all(provider['configuration'][key]==original['inference'][key] for key in ['temperature','seed','max_tokens_cap','thinking'])
    config.embedding.model=''
    report={'source_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'created_utc':datetime.now(timezone.utc).isoformat(),'provider':provider,
        'spec_sha256':{str(p):sha(p) for p in [original_path,extra_path]},
        'source_sha256':{str(p):sha(p) for p in [Path(__file__),Path('src/avatar/main.py'),Path('src/avatar/brain/profile_grounding.py'),Path('src/avatar/brain/tasks.py'),Path('src/avatar/brain/literal_layout.py')]},
        'comparison': 'literal_v1_slots_vs_v2_source_template' if args.literal_template else 'task_checks_both_arms_literal_composition_candidate' if args.literal_composition else 'profile_and_identity_both_arms_task_delivery_candidate' if args.task_delivery else 'subject_prompt_both_arms_profile_grounding_candidate' if args.profile_grounding else 'subject_prompt_candidate_only',
        'literal_composition_protocol':json.loads(Path('evals/interaction/cycle-03/'+('literal-template-protocol.json' if args.literal_template else 'literal-slots-protocol.json')).read_text()) if literal_mode else None,
        'regression_protocol':regression,
        'grounding_protocol':json.loads(Path('evals/interaction/cycle-02/profile-grounding-protocol.json').read_text()) if args.profile_grounding else None,
        'disclosure_protocol':json.loads(Path('evals/interaction/cycle-02/disclosure-grounding-v2.json').read_text()) if args.profile_grounding else None,
        'protocol':extra,'prospective_protocol':prospective,'measurement_policy':policy,'supplemental_protocol':supplemental,
        'additional_spec_sha256':{str(p):sha(p) for p in [args.policy,args.supplemental,args.turn_suite,args.regression_suite] if p},'rows':[]}
    engine=LLMEngine(base_url=provider['url'],api_key='local-eval-only',model=args.model_key,timeout=180,max_retries=0)
    try:
        report['warmup_calls']=[]
        for streaming in [False,True]:
            started=time.perf_counter()
            messages=[{'role':'user','content':'请回答：你好。'}]
            reply=engine.stream_chat(messages,temperature=0,max_tokens=16) if streaming else engine.chat(messages,temperature=0,max_tokens=16)
            report['warmup_calls'].append({'streaming':streaming,'seconds':time.perf_counter()-started,'reply':reply})
        for index,(family,case) in enumerate(groups):
            modes=['baseline','candidate'] if index%2==0 else ['candidate','baseline']
            for mode in modes:
                row={'id':case['id'],'family':family,'mode':mode,'turns':[],'error':None}
                with tempfile.TemporaryDirectory(prefix='avatar-subject-eval-') as folder:
                    avatar=Avatar(db_path=str(Path(folder)/'eval.db'),llm=engine,
                        fast_analysis=True,subject_prompt_enabled=task_mode or args.profile_grounding or mode=='candidate',
                        profile_grounding_enabled=task_mode or (args.profile_grounding and mode=='candidate'),
                        task_contract_enabled=literal_mode or (args.task_delivery and mode=='candidate'),
                        delivery_check_enabled=literal_mode or (args.task_delivery and mode=='candidate'),
                        literal_composition_enabled=args.literal_template or (args.literal_composition and mode=='candidate'),
                        literal_plan_version='v2' if args.literal_template and mode=='candidate' else 'v1',session_id='paired-subject-eval')
                    try:
                        for text in case['turns']:
                            started=time.perf_counter()
                            visible=[]
                            options={'on_delta':lambda piece:visible.append({'text':piece,'seconds':time.perf_counter()-started})} if task_mode else {}
                            result=avatar.respond(text,cancel=CancellationToken(),**options)
                            row['turns'].append({'input':text,'result':result,'seconds':time.perf_counter()-started,
                                'profile_at_turn':avatar.memory.get_user_profile(),'visible':visible})
                        row['v1_checks']=checks(row['turns'][-1]['result']['reply'],case['final_checks'])
                        row['checks']=checks(row['turns'][-1]['result']['reply'],versioned_rules(case['final_checks'],family,case['id'],policy))
                        row['all_turn_check']=not any(phrase in turn['result']['reply']
                            for phrase in case.get('all_turn_forbidden',[]) for turn in row['turns'])
                        if 'turn_checks' in case:
                            row['turn_checks']=check_dialogue_turns([t['result']['reply'] for t in row['turns']],case['turn_checks'])
                            row['all_turn_check'] = row['all_turn_check'] and row['turn_checks']['passed']
                        row['visible_final_check']=all(not t['result'].get('delivery_check',{}).get('stream_buffered')
                            or ''.join(p['text'] for p in t['visible'])==t['result']['reply'] for t in row['turns'])
                        row['all_turn_check']=row['all_turn_check'] and row['visible_final_check']
                        row['profile']=avatar.memory.get_user_profile()
                        value=case.get('expected_profile_contains')
                        row['profile_check']=value is None or any(value in content for content in row['profile'].values())
                        row['name_profile_check']='expected_name' not in case or row['profile'].get('名字')==case['expected_name']
                        row['task_scope_check']='expected_contract_active' not in case or bool(row['turns'][-1]['result'].get('task'))==case['expected_contract_active']
                        row['side_effect_check']='expected_reminder_count' not in case or len(avatar.reminders.list())==case['expected_reminder_count']
                        row['generation_valid']=all(turn['result'].get('generation_mode') not in [None,'rules_service_error','rules_unconfigured'] for turn in row['turns'])
                        row['v1_passed']=all(row['v1_checks'].values()) and row['profile_check'] and row['generation_valid'] and row['all_turn_check'] and row['name_profile_check'] and row['task_scope_check'] and row['side_effect_check']
                        row['passed']=all(row['checks'].values()) and row['profile_check'] and row['generation_valid'] and row['all_turn_check'] and row['name_profile_check'] and row['task_scope_check'] and row['side_effect_check']
                    except Exception as exc:row['error']=type(exc).__name__;row['passed']=False
                    finally:avatar.memory.close()
                report['rows'].append(row);save(args.output,report)
                print(family,case['id'],mode,row['passed'],row['error'],flush=True)
    finally:engine.close()
    summary={}
    for family in dict.fromkeys(family for family,_ in groups):
        summary[family]={mode:{'passed':sum(row['passed'] for row in report['rows'] if row['mode']==mode and row['family']==family),
            'v1_passed':sum(row.get('v1_passed',False) for row in report['rows'] if row['mode']==mode and row['family']==family),
            'failed_ids':[row['id'] for row in report['rows'] if row['mode']==mode and row['family']==family and not row['passed']]}
            for mode in ['baseline','candidate']}
    keyed={(row['family'],row['id'],row['mode']):row for row in report['rows']}
    regressions=[{'id':row['id'],'family':row['family']} for row in report['rows'] if row['mode']=='baseline'
        and row['passed'] and not keyed[row['family'],row['id'],'candidate']['passed']]
    report.update(summary=summary,new_failures=regressions,
        release_gate_passed=not regressions and all(row['passed'] for row in report['rows'] if row['mode']=='candidate'),
        semantic_quality_approved=False,production_activation_approved=False)
    save(args.output,report)
    print(json.dumps({'summary':summary,'new_failures':regressions,'release_gate_passed':report['release_gate_passed']},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
