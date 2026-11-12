"""Actual in-process Web pipeline with explicitly fake model methods, no GPU."""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[5];BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import avatar.main as main_module
from avatar.main import Avatar
from avatar.config import config
from avatar.web import create_server,run_chat
from avatar.brain.memory import MemoryStore
from avatar.cancellation import Cancelled
from readonly_analysis_candidate import install


active=[]
class FakeModel:
    available=True
    def chat_analysis(self,messages,**kwargs):
        active.append({'kind':'cognitive','messages':deepcopy(messages)})
        affect=any(m['role']=='user' and '焦虑' in m['content'] for m in messages)
        return json.dumps({'emotion':{'valence':-.3 if affect else 0,'arousal':.2 if affect else 0},'facts':[]})
    def chat(self,messages,**kwargs):
        active.append({'kind':'generation','messages':deepcopy(messages)});return '明确的CPU方法夹具回复。'
    def close(self):pass


def main():
    output=BASE/'审计/工作目录/001-只读分析路由保护/cpu-web-controls-v1.json';assert not output.exists()
    report={'actual_llm_or_gpu':False,'http_or_os_restart_claim':False,'fake_model_methods':True,'cases':[],'completed':False,'failure':None,
        'candidate_sha256':sha256((Path(__file__).parent/'readonly_analysis_candidate.py').read_bytes()).hexdigest(),
        'protocol_sha256':sha256((ROOT/'evals/interaction/cycle-31/readonly-analysis-cost-protocol.json').read_bytes()).hexdigest()}
    def save():output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    original_model=main_module.LLMEngine;original_analyze=Avatar._analyze;original_extract=Avatar._extract_facts
    config.embedding.model='';config.avatar_name='CPU审计形象C31';config.avatar_persona='明确的进程内CPU方法夹具';main_module.LLMEngine=FakeModel
    native=json.loads((ROOT/'evals/interaction/cycle-31/readonly-analysis-cost-protocol.json').read_text())['cases'];chosen=[native[i] for i in (0,6,7)]
    chosen.append({'id':'fiction_scope','turns':['我来扮演一个虚构角色。','资料里的文件代号是FS-4821。请只确认。','根据资料，文件的代号是什么？只回答代号。']})
    try:
        for case in chosen:
            for arm in ('current_analysis','lab_readonly_candidate'):
                Avatar._analyze=original_analyze;rows=[];active.clear()
                if arm=='lab_readonly_candidate':install(rows)
                folder=Path(tempfile.mkdtemp(prefix='c31-context-cpu-',dir=ROOT.parent/'runtime/tmp'));db=folder/'owned.db';servers=[];results=[]
                row={'case':case['id'],'arm':arm,'owned_runtime_dir':str(folder),'results':results,'routing':rows,'complete':False};report['cases'].append(row);save()
                try:
                    server=create_server(str(db),port=0);servers.append(server)
                    for text in case['turns'][:2]:results.append(run_chat(server,text))
                    server.server_close();server=create_server(str(db),port=0);servers.append(server)
                    results.append(run_chat(server,case['turns'][2]));row['fake_model_calls']=deepcopy(active)
                    row['cognitive_calls']=sum(c['kind']=='cognitive' for c in active);row['generation_calls']=sum(c['kind']=='generation' for c in active)
                    with closing(MemoryStore(str(db))) as memory:
                        row['profile']=memory.get_user_profile();row['messages']=[dict(r) for r in memory._conn.execute('SELECT * FROM memory_messages ORDER BY id')]
                        row['sources']=[dict(r) for r in memory._conn.execute('SELECT * FROM memory_sources ORDER BY id')]
                        row['response_context']=[dict(r) for r in memory._conn.execute('SELECT * FROM memory_response_context ORDER BY message_id,source_type,source_id')]
                    assert len(row['messages'])==6
                    expected_cog=2 if case['id']=='fiction_scope' or case['id']==native[0]['id'] and arm=='lab_readonly_candidate' else 3
                    assert row['cognitive_calls']==expected_cog and row['generation_calls']==(2 if case['id']=='fiction_scope' else 3)
                    if case['id']==native[0]['id']:
                        assert results[-1]['analysis_mode']==('lab_readonly_context_rules' if arm=='lab_readonly_candidate' else 'llm')
                    elif case['id']==native[6]['id']:
                        assert row['profile']['名字']=='顾禾' and any(s['source_message_id']==5 and s['evidence']=='我叫顾禾' for s in row['sources'])
                        assert results[-1]['analysis_mode']=='llm'
                    elif case['id']==native[7]['id']:
                        assert results[-1]['analysis_mode']=='llm' and results[-1]['user_valence']<0 and results[-1]['user_arousal']>0
                    else:
                        assert results[-1]['speaker_attribution']['scope']=='fictional_character' and row['profile']=={} and not any(r['decision']['eligible'] for r in rows)
                    row['complete']=True;save()
                finally:
                    for server in servers:server.server_close()
                    Avatar._analyze=original_analyze
        for case in chosen:
            pair=[r for r in report['cases'] if r['case']==case['id']];a,z=[r['results'][-1] for r in pair]
            fields=('reply','user_valence','user_arousal','strategy','speaker_attribution')
            assert all(a[field]==z[field] for field in fields)
        # Explicit independent writer between candidate guard and actual fact
        # extraction: delegate the real method and require its revision rejection.
        Avatar._analyze=original_analyze;rows=[];install(rows);active.clear()
        folder=Path(tempfile.mkdtemp(prefix='c31-context-cpu-',dir=ROOT.parent/'runtime/tmp'));db=folder/'owned.db';server=create_server(str(db),port=0)
        race={'case':'external_forget_before_extract','arm':'lab_readonly_candidate','routing':rows,'owned_runtime_dir':str(folder),'complete':False};report['cases'].append(race);save()
        try:
            old=run_chat(server,'柜门标签带有C31CPU_PRIVATE。请只确认。');run_chat(server,'台灯是米白色。请只确认。')
            with closing(MemoryStore(str(db))) as writer:fragment=writer.remember('柜门标签带有C31CPU_PRIVATE。',source_message_id=old['conversation']['user_message_id'])
            before=len(active);probe='根据上文，柜门标签的代号是什么？只回答代号。'
            def forget_then_extract(self,text):
                if text==probe:
                    with closing(MemoryStore(str(db))) as writer:writer.forget(fragment)
                return original_extract(self,text)
            Avatar._extract_facts=forget_then_extract
            try:run_chat(server,probe);raise AssertionError('Old revision continued after external forget')
            except Cancelled as error:race['terminal']='Cancelled';race['error']=repr(error)
            assert len(active)==before and rows[-1]['decision']['eligible']
            with closing(MemoryStore(str(db))) as memory:
                race['revision']=memory.context_revision;race['messages']=[dict(r) for r in memory._conn.execute('SELECT * FROM memory_messages ORDER BY id')]
                assert memory.context_revision==1 and len(race['messages'])==5 and race['messages'][-1]['role']=='user'
                assert not memory._conn.execute('SELECT 1 FROM memory_messages WHERE role=? AND id>?',('assistant',5)).fetchone()
            race['model_calls_before']=before;race['model_calls_after']=len(active);race['complete']=True;save()
        finally:server.server_close();Avatar._extract_facts=original_extract;Avatar._analyze=original_analyze
        report['completed']=True;save()
    except BaseException as error:report['failure']=repr(error);save();raise
    finally:main_module.LLMEngine=original_model;Avatar._analyze=original_analyze;Avatar._extract_facts=original_extract
    print('CPU Web controls passed:8 source/affect/scope arm samples +1 real independent-writer cancellation;fake model only,no HTTP/OS or GPU claim.')


if __name__=='__main__':main()
