"""Paired objective development checks using the same real local model in both modes."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import tempfile
import time

from avatar.brain.llm import LLMEngine
from avatar.cancellation import CancellationToken
from avatar.main import Avatar
from avatar.config import config


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path,data):
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(path)


def checks(text,rules):
    return {'all':all(value in text for value in rules.get('all',[])),
        'any':not rules.get('any') or any(value in text for value in rules['any']),
        'none':all(value not in text for value in rules.get('none',[]))}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--provider',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Use a new output file')
    spec_path=Path('evals/interaction/cycle-02/real-model-cases.json')
    spec=json.loads(spec_path.read_text());provider=json.loads(args.provider.read_text())
    report={'source_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'created_utc':datetime.now(timezone.utc).isoformat(),'scope':spec['scope'],
        'spec_sha256':sha(spec_path),'provider':provider,'rows':[],
        'source_sha256':{str(p):sha(p) for p in [Path(__file__),Path('src/avatar/main.py'),
            Path('src/avatar/brain/llm.py'),Path('src/avatar/brain/analysis_routing.py')]}}
    # Keep evaluation local even if a user's .env enables a remote embedder.
    config.embedding.model=''
    engine=LLMEngine(base_url=provider['url'],api_key='local-eval-only',model='qwen3-4b-q4_k_m',
        timeout=180,max_retries=0)
    # Warm up both transports before recording, without scenario-specific inputs.
    engine.chat([{'role':'user','content':'请回答：你好。'}],temperature=0,max_tokens=16)
    engine.stream_chat([{'role':'user','content':'请回答：你好。'}],temperature=0,max_tokens=16)
    try:
        for index,case in enumerate(spec['cases']):
            modes=['baseline','g2'] if index%2==0 else ['g2','baseline']
            for mode in modes:
                row={'id':case['id'],'mode':mode,'turns':[],'error':None}
                with tempfile.TemporaryDirectory(prefix='avatar-real-eval-') as folder:
                    avatar=Avatar(db_path=str(Path(folder)/'eval.db'),llm=engine,embedder=None,
                        fast_analysis=mode=='g2',session_id='paired-evaluation-session')
                    try:
                        for text in case['turns']:
                            first=[];deltas=[];start=time.perf_counter()
                            def on_delta(value):
                                if not first:first.append(time.perf_counter()-start)
                                deltas.append(value)
                            result=avatar.respond(text,**({'cancel':CancellationToken(),'on_delta':on_delta} if mode=='g2' else {}))
                            elapsed=time.perf_counter()-start
                            row['turns'].append({'input':text,'result':result,'first_seconds':first[0] if first else elapsed,
                                'complete_seconds':elapsed,'draft_deltas':deltas})
                        row['checks']=checks(row['turns'][-1]['result']['reply'],case['final_checks'])
                        row['passed']=all(row['checks'].values())
                        row['profile']=avatar.memory.get_user_profile()
                        row['memory_records']=avatar.memory.list_memories(include_history=True)
                    except Exception as exc:
                        row['error']=type(exc).__name__;row['passed']=False
                    finally:avatar.memory.close()
                report['rows'].append(row);save(args.output,report)
                print(case['id'],mode,'pass' if row['passed'] else 'FAIL',row['error'],flush=True)
    finally:engine.close()
    summary={}
    for mode in ['baseline','g2']:
        rows=[r for r in report['rows'] if r['mode']==mode]
        turns=[turn for r in rows for turn in r['turns']]
        summary[mode]={'scenarios':len(rows),'passed_objective_checks':sum(r['passed'] for r in rows),
            'errors':sum(bool(r['error']) for r in rows),'failed_ids':[r['id'] for r in rows if not r['passed']],
            'median_first_seconds':statistics.median(t['first_seconds'] for t in turns),
            'median_complete_seconds':statistics.median(t['complete_seconds'] for t in turns)}
    by_id={(r['id'],r['mode']):r for r in report['rows']}
    regressions=[c['id'] for c in spec['cases'] if by_id[c['id'],'baseline']['passed'] and not by_id[c['id'],'g2']['passed']]
    report['summary']=summary;report['new_g2_failures']=regressions
    report['passes_objective_nonregression_gate']=not regressions
    report['semantic_quality_approved']=False
    save(args.output,report)
    print(json.dumps({'summary':summary,'new_g2_failures':regressions},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
