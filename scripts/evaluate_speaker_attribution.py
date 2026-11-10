"""Pinned local-model source ownership; keep conversational checks separate."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import tempfile
import time
from urllib.parse import urlsplit

from avatar.main import Avatar
from avatar.brain.llm import LLMEngine
from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken
from avatar.config import config
from avatar.web import create_server, run_chat
from evaluate_real_interaction import sha, save, checks


def evaluate(provider_path, output):
    if output.exists():raise FileExistsError('Use a fresh evidence output path')
    path=Path('evals/interaction/cycle-04/speaker-real-protocol.json')
    protocol=json.loads(path.read_text());suite=Path(protocol['regression_suite'])
    provider=json.loads(provider_path.read_text())
    registry=json.loads(Path('evals/interaction/cycle-02/model-scale-protocol.json').read_text())
    model=next(m for m in registry['models'] if m['model_id']==provider['model_id'])
    url=urlsplit(provider['url'])
    if (url.scheme!='http' or url.hostname!='127.0.0.1' or url.path!='/v1'
            or provider['model_id']!='qwen3-4b-q4_k_m'
            or provider['model_sha256']!=model['sha256'] or provider['model_revision']!=model['revision']):
        raise ValueError('Only the pinned loopback provider is supported')
    config.llm.base_url=provider['url'];config.llm.api_key='local-eval-only';config.llm.model=provider['model_id']
    config.embedding.model=''
    report={'source_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'created_utc':datetime.now(timezone.utc).isoformat(),'protocol':protocol,'provider':provider,
        'spec_sha256':{str(p):sha(p) for p in [path,suite]},
        'source_sha256':{str(p):sha(p) for p in [Path(__file__),Path('src/avatar/main.py'),
            Path('src/avatar/brain/speaker_scope.py'),Path('src/avatar/web.py')]},
        'rows':[],'execution_complete':False,'engineering_passed':False,'semantic_approved':False,
        'application_http_tested':False,'failure':None}
    save(output,report)
    cases=json.loads(suite.read_text())['cases']+protocol['additional_cases']
    started=time.perf_counter()
    for case in cases:
        for arm in protocol['arms']:
            row={'id':case['id'],'arm':arm,'turns':[],'error':None,'engineering_passed':False}
            with tempfile.TemporaryDirectory(prefix='speaker-',dir='data/g2-cycle-04') as folder:
                database=str(Path(folder)/'memory.db')
                bot=None;server=None
                try:
                    if arm=='native_stream':
                        bot=Avatar(db_path=database,llm=LLMEngine(),subject_prompt_enabled=True,profile_grounding_enabled=True)
                    else:
                        reader=MemoryStore(database);reader.close()
                        server=create_server(database,port=0,identity_grounding=True,profile_grounding=True)
                    for text in case['turns']:
                        before=time.perf_counter();visible=[]
                        if bot:
                            result=bot.respond(text,cancel=CancellationToken(),on_delta=visible.append)
                        else:result=run_chat(server,text,False)
                        reader=MemoryStore(database)
                        try:profile=reader.get_user_profile();facts=reader.list_memories()
                        finally:reader.close()
                        row['turns'].append({'input':text,'seconds':time.perf_counter()-before,
                            'result':result,'profile':profile,'visible':''.join(visible) if bot else None})
                        if result['generation_mode'] not in {'llm','profile_grounded','profile_lookup'}:
                            raise AssertionError('Unexpected rule/model fallback')
                        if result['analysis_mode']!='llm':raise AssertionError('Native cognitive analysis did not complete')
                        if bot and result['generation_mode']=='llm' and ''.join(visible)!=result['reply']:
                            raise AssertionError('Native visible/final mismatch')
                        if result['speaker_attribution']['scope']=='fictional_character':
                            if result['profile_grounding']['action'] is not None:
                                raise AssertionError('Fictional speaker took a real-profile shortcut')
                    row['profile_check']=profile==case['profile']
                    row['fact_count_check']='facts' not in case or len(facts)==case['facts']
                    row['engineering_passed']=row['profile_check'] and row['fact_count_check']
                    if 'response_check' in case:
                        row['conversational_checks']=checks(result['reply'],case['response_check'])
                    if not row['engineering_passed']:raise AssertionError('Final profile/fact ownership mismatch')
                except Exception as exc:
                    row['error']=type(exc).__name__+': '+str(exc)
                finally:
                    if bot:bot.memory.close();bot.llm.close()
                    if server:server.server_close()
            report['rows'].append(row);report['seconds']=time.perf_counter()-started
            if row['error']:report['failure']={'id':case['id'],'arm':arm,'error':row['error']}
            save(output,report)
            print(case['id'],arm,row['engineering_passed'],row['error'],flush=True)
            if row['error']:return report
    report['execution_complete']=True
    report['engineering_passed']=all(row['engineering_passed'] for row in report['rows'])
    report['conversational_checks']=[{'id':r['id'],'arm':r['arm'],'checks':r['conversational_checks']}
        for r in report['rows'] if 'conversational_checks' in r]
    save(output,report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--provider',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    result=evaluate(args.provider,args.output)
    print(json.dumps({key:result[key] for key in ['execution_complete','engineering_passed','failure']},ensure_ascii=False))
    if not result['engineering_passed']:raise SystemExit(1)
