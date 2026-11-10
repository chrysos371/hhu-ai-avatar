"""Preregistered ownership-instruction ablation. Candidate remains off by default."""
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
from avatar.lab.checks import versioned_rules
from evaluate_real_interaction import sha, save, checks


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--provider',type=Path,required=True)
    parser.add_argument('--model-key',default='qwen3-4b-q4_k_m')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--policy',type=Path)
    parser.add_argument('--supplemental',type=Path)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Use a new output file')
    original_path=Path('evals/interaction/cycle-02/real-model-cases.json')
    extra_path=Path('evals/interaction/cycle-02/subject-ownership-dev16.json')
    original=json.loads(original_path.read_text());extra=json.loads(extra_path.read_text())
    policy=json.loads(args.policy.read_text()) if args.policy else None
    supplemental=json.loads(args.supplemental.read_text()) if args.supplemental else {'cases':[]}
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
        'source_sha256':{str(p):sha(p) for p in [Path(__file__),Path('src/avatar/main.py')]},
        'protocol':extra,'measurement_policy':policy,'supplemental_protocol':supplemental,
        'additional_spec_sha256':{str(p):sha(p) for p in [args.policy,args.supplemental] if p},'rows':[]}
    engine=LLMEngine(base_url=provider['url'],api_key='local-eval-only',model=args.model_key,timeout=180,max_retries=0)
    try:
        report['warmup_calls']=[]
        for streaming in [False,True]:
            started=time.perf_counter()
            messages=[{'role':'user','content':'请回答：你好。'}]
            reply=engine.stream_chat(messages,temperature=0,max_tokens=16) if streaming else engine.chat(messages,temperature=0,max_tokens=16)
            report['warmup_calls'].append({'streaming':streaming,'seconds':time.perf_counter()-started,'reply':reply})
        for index,case in enumerate(original['cases']+extra['cases']+supplemental['cases']):
            family='original' if index<len(original['cases']) else 'additional' if index<len(original['cases'])+len(extra['cases']) else 'supplemental'
            modes=['baseline','candidate'] if index%2==0 else ['candidate','baseline']
            for mode in modes:
                row={'id':case['id'],'family':family,'mode':mode,'turns':[],'error':None}
                with tempfile.TemporaryDirectory(prefix='avatar-subject-eval-') as folder:
                    avatar=Avatar(db_path=str(Path(folder)/'eval.db'),llm=engine,
                        fast_analysis=True,subject_prompt_enabled=mode=='candidate',session_id='paired-subject-eval')
                    try:
                        for text in case['turns']:
                            started=time.perf_counter()
                            result=avatar.respond(text,cancel=CancellationToken())
                            row['turns'].append({'input':text,'result':result,'seconds':time.perf_counter()-started})
                        row['v1_checks']=checks(row['turns'][-1]['result']['reply'],case['final_checks'])
                        row['checks']=checks(row['turns'][-1]['result']['reply'],versioned_rules(case['final_checks'],family,case['id'],policy))
                        row['all_turn_check']=not any(phrase in turn['result']['reply']
                            for phrase in case.get('all_turn_forbidden',[]) for turn in row['turns'])
                        row['profile']=avatar.memory.get_user_profile()
                        value=case.get('expected_profile_contains')
                        row['profile_check']=value is None or any(value in content for content in row['profile'].values())
                        row['name_profile_check']='expected_name' not in case or row['profile'].get('名字')==case['expected_name']
                        row['generation_valid']=all(turn['result'].get('generation_mode') not in [None,'rules_service_error','rules_unconfigured'] for turn in row['turns'])
                        row['v1_passed']=all(row['v1_checks'].values()) and row['profile_check'] and row['generation_valid'] and row['all_turn_check'] and row['name_profile_check']
                        row['passed']=all(row['checks'].values()) and row['profile_check'] and row['generation_valid'] and row['all_turn_check'] and row['name_profile_check']
                    except Exception as exc:row['error']=type(exc).__name__;row['passed']=False
                    finally:avatar.memory.close()
                report['rows'].append(row);save(args.output,report)
                print(family,case['id'],mode,row['passed'],row['error'],flush=True)
    finally:engine.close()
    summary={}
    for family in ['original','additional']+(['supplemental'] if supplemental['cases'] else []):
        summary[family]={mode:{'passed':sum(row['passed'] for row in report['rows'] if row['mode']==mode and row['family']==family),
            'v1_passed':sum(row.get('v1_passed',False) for row in report['rows'] if row['mode']==mode and row['family']==family),
            'failed_ids':[row['id'] for row in report['rows'] if row['mode']==mode and row['family']==family and not row['passed']]}
            for mode in ['baseline','candidate']}
    keyed={(row['family'],row['id'],row['mode']):row for row in report['rows']}
    regressions=[{'id':row['id'],'family':row['family']} for row in report['rows'] if row['mode']=='baseline'
        and row['passed'] and not keyed[row['family'],row['id'],'candidate']['passed']]
    report.update(summary=summary,new_failures=regressions,
        release_gate_passed=not regressions and all(row['passed'] for row in report['rows'] if row['mode']=='candidate'),
        semantic_quality_approved=False)
    save(args.output,report)
    print(json.dumps({'summary':summary,'new_failures':regressions,'release_gate_passed':report['release_gate_passed']},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
