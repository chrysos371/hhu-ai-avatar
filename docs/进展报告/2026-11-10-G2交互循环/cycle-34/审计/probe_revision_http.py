"""Actual loopback application HTTP, fake model methods and controlled state faults."""
import argparse
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from urllib.request import Request,build_opener,ProxyHandler
ROOT=Path(__file__).resolve().parents[5];BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(BASE.parent/'cycle-29/审计'))
import avatar.main as main_module
from avatar.config import config
from avatar.web import create_server
from avatar.brain.memory import MemoryStore
from run_context_baseline import events
calls=[];held=threading.Event();release=threading.Event()


class FakeModel:
    available=True
    def chat_analysis(self,messages,**kwargs):
        affect='泄了气' in messages[-1]['content'];value={'emotion':{'valence':-.4 if affect else 0,'arousal':.3 if affect else 0},'facts':[]}
        calls.append({'kind':'cognitive','messages':deepcopy(messages),'controlled_response':value});return json.dumps(value)
    def chat(self,messages,**kwargs):
        calls.append({'kind':'generation','messages':deepcopy(messages)})
        if 'C34_CANCEL_AFFECT' in messages[-1]['content']:
            held.set()
            if not release.wait(25):raise TimeoutError('Controlled generation release missing')
        return '明确的HTTP CPU方法夹具回复。'
    def close(self):pass


def snapshot(db):
    with closing(MemoryStore(str(db))) as memory:
        return {'revision':memory.context_revision,**{name:[dict(row) for row in memory._conn.execute('SELECT * FROM '+name)] for name in ('memory_messages','memory_chat_results','memory_response_context','memory_sources')}}


def main(args):
    work=BASE/'审计/工作目录/001-自动情绪版本失效';output=work/('controlled-http-'+args.phase+'.json');assert not output.exists()
    report={'scope':'matched_controlled_http_automatic_emotion_revision_regression','phase':args.phase,'actual_loopback_app_http':True,'fake_model_methods':True,'actual_llm_or_gpu':False,'os_restart_claim':False,'cases':[],'completed':False,'failure':None}
    def save():output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    original=main_module.LLMEngine;main_module.LLMEngine=FakeModel;config.embedding.model='';config.avatar_name='HTTP CPU状态夹具';config.avatar_persona='明确假模型的来源与取消工程审计';opener=build_opener(ProxyHandler({}))
    save()
    try:
        for rep in (1,2,3):
            for kind in ('forget_completed_source','cancel_after_analysis'):
                calls.clear();held.clear();release.clear();directory=Path(tempfile.mkdtemp(prefix='c34-context-live-cpu-',dir=ROOT.parent/'runtime/tmp'));db=directory/'owned.db'
                server=create_server(str(db),port=0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}/api/v1'
                row={'case':kind,'repetition':rep,'owned_runtime_dir':str(directory),'http':[],'turns':[],'complete':False};report['cases'].append(row);save()
                def query(route,payload=None):
                    request=Request(base+route,data=None if payload is None else json.dumps(payload,ensure_ascii=False).encode(),headers={'X-Avatar-Token':server.token,'Content-Type':'application/json'})
                    with opener.open(request,timeout=15) as response:raw=response.read().decode();status=response.status
                    row['http'].append({'route':route,'payload':payload,'status':status,'raw_response':raw});save();assert 200<=status<300;return json.loads(raw)['data']
                def begin(text):
                    admitted=query('/turns',{'request_id':f'c34_{args.phase}_cpu_{kind}_{rep}_{len(row["turns"])}','text':text,'use_web':False})
                    turn={'input':text,'admitted':admitted};row['turns'].append(turn);save();return turn
                def finish(turn):
                    request=Request(base+'/turns/'+turn['admitted']['job_id']+'/events',headers={'X-Avatar-Token':server.token})
                    with opener.open(request,timeout=15) as response:terminal,result,observed,raw=events(response,time.perf_counter())
                    turn.update(terminal=terminal,result=result,events=observed,raw_sse=raw);save();return terminal,result
                try:
                    row['initial_emotion']=query('/emotion');assert row['initial_emotion']['automatic']=={'valence':0,'arousal':0}
                    if kind=='forget_completed_source':
                        terminal,result=finish(begin('面试又没过，整个人像泄了气。'));assert terminal=='result'
                        row['before_boundary_emotion']=query('/emotion');assert row['before_boundary_emotion']['user_observation']['valence']==-.4
                        with closing(MemoryStore(str(db))) as memory:
                            source=result['conversation']['user_message_id'];fragment=memory.remember('受控情绪来源标识。',source_message_id=source);memory.forget(fragment)
                        row['sql_after_boundary']=snapshot(db);assert row['sql_after_boundary']['revision']==1 and next(m for m in row['sql_after_boundary']['memory_messages'] if m['id']==source)['content']=='[redacted]'
                        row['boundary_control']={'independent_writer_forget':True,'source_message_id':source,'fragment_id':fragment,'source_redacted':True}
                    else:
                        turn=begin('面试又没过，整个人像泄了气。C34_CANCEL_AFFECT')
                        if not held.wait(10):raise TimeoutError('Generation barrier not reached after analysis')
                        row['boundary_control']={'held_in_fake_generation_after_analysis':True,'cancel_response':query('/turns/'+turn['admitted']['job_id']+'/cancel',{})}
                        release.set();terminal,result=finish(turn);assert terminal=='cancelled'
                        row['sql_after_boundary']=snapshot(db);assert not row['sql_after_boundary']['memory_chat_results'] and not any(m['role']=='assistant' for m in row['sql_after_boundary']['memory_messages'])
                    row['after_boundary_emotion']=query('/emotion')
                    retained=lambda value:any(abs(value[axis])>1e-9 for axis in ('valence','arousal'))
                    row['user_observation_nonzero_after_boundary']=retained(row['after_boundary_emotion']['user_observation'])
                    row['character_pad_nonzero_after_boundary']=retained(row['after_boundary_emotion']['automatic'])
                    terminal,result=finish(begin('这是一条中性的新请求。'));assert terminal=='result'
                    row['after_neutral_emotion']=query('/emotion');row['sql_after_neutral']=snapshot(db)
                    row['neutral_user_observation_zero']=not retained(row['after_neutral_emotion']['user_observation'])
                    row['character_pad_nonzero_after_neutral']=retained(row['after_neutral_emotion']['automatic'])
                    row['fake_model_calls']=deepcopy(calls);row['complete']=True;save()
                finally:release.set();server.shutdown();server.server_close();thread.join(10)
        report['completed']=True;save()
    except BaseException as error:report['failure']=repr(error);save();raise
    finally:main_module.LLMEngine=original
    print('Completed6 controlled real HTTP cases with fake methods; retained user observation after boundary',sum(c['user_observation_nonzero_after_boundary'] for c in report['cases']),'/6; retained character PAD after neutral',sum(c['character_pad_nonzero_after_neutral'] for c in report['cases']),'/6. Source redaction/cancel terminals verified; no native model/GPU/OS claim.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--phase',required=True,choices=('before','after'));main(parser.parse_args())
