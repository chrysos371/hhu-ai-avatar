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
from evaluate_real_interaction import sha, save, checks


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--provider',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Use a new output file')
    original_path=Path('evals/interaction/cycle-02/real-model-cases.json')
    extra_path=Path('evals/interaction/cycle-02/subject-ownership-dev16.json')
    original=json.loads(original_path.read_text());extra=json.loads(extra_path.read_text())
    provider=json.loads(args.provider.read_text())
    assert provider['model_revision']==original['revision']
    assert all(provider['configuration'][key]==original['inference'][key] for key in ['temperature','seed','max_tokens_cap','thinking'])
    config.embedding.model=''
    report={'source_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'created_utc':datetime.now(timezone.utc).isoformat(),'provider':provider,
        'spec_sha256':{str(p):sha(p) for p in [original_path,extra_path]},
        'source_sha256':{str(p):sha(p) for p in [Path(__file__),Path('src/avatar/main.py')]},
        'protocol':extra,'rows':[]}
    engine=LLMEngine(base_url=provider['url'],api_key='local-eval-only',model='qwen3-4b-q4_k_m',timeout=180,max_retries=0)
    try:
        for index,case in enumerate(original['cases']+extra['cases']):
            family='original' if index<len(original['cases']) else 'additional'
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
                        row['checks']=checks(row['turns'][-1]['result']['reply'],case['final_checks'])
                        row['profile']=avatar.memory.get_user_profile()
                        value=case.get('expected_profile_contains')
                        row['profile_check']=value is None or any(value in content for content in row['profile'].values())
                        row['generation_valid']=all(turn['result'].get('generation_mode') not in [None,'rules_service_error','rules_unconfigured'] for turn in row['turns'])
                        row['passed']=all(row['checks'].values()) and row['profile_check'] and row['generation_valid']
                    except Exception as exc:row['error']=type(exc).__name__;row['passed']=False
                    finally:avatar.memory.close()
                report['rows'].append(row);save(args.output,report)
                print(family,case['id'],mode,row['passed'],row['error'],flush=True)
    finally:engine.close()
    summary={}
    for family in ['original','additional']:
        summary[family]={mode:{'passed':sum(row['passed'] for row in report['rows'] if row['mode']==mode and row['family']==family),
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
