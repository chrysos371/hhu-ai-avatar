"""Real in-process Web and SQLite clones, explicitly fake model, no HTTP/OS/GPU."""
from contextlib import closing
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
from shared_snapshot import ROOT,backup_pair,logical_dump
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(BASE.parent/'cycle-31/审计'))
import avatar.main as main_module
from avatar.main import Avatar
from avatar.config import config
from avatar.web import create_server,run_chat
from avatar.brain.memory import MemoryStore
from readonly_analysis_candidate import install
calls=[];explicit_assistant=False


class FakeModel:
    available=True
    def chat_analysis(self,messages,**kwargs):
        calls.append({'kind':'cognitive','messages':deepcopy(messages)})
        affect=any('泄了气' in m['content'] or '焦虑' in m['content'] for m in messages)
        return json.dumps({'emotion':{'valence':-.4 if affect else 0,'arousal':-.2 if affect else 0},'facts':[]})
    def chat(self,messages,**kwargs):
        calls.append({'kind':'generation','messages':deepcopy(messages)})
        if messages[-1]['content'].startswith('根据上文'):return 'AB-2738'
        return '有焦虑的感觉。' if explicit_assistant else 'CPU夹具确认。'
    def close(self):pass


def main():
    global explicit_assistant
    target=BASE/'审计/工作目录/001-共享历史隐含情绪/shared-cpu-controls.json';assert not target.exists()
    original_model=main_module.LLMEngine;original_analyze=Avatar._analyze;main_module.LLMEngine=FakeModel
    config.embedding.model='';config.avatar_name='CPU共享备份夹具';config.avatar_persona='明确假模型的CPU工程控制'
    rows=[];probe='根据上文，柜门标签的代号是什么？只回答代号。'
    try:
        for scenario in ('implicit_neutral_assistant','explicit_assistant_delegates','neutral','current_name_delegates'):
            Avatar._analyze=original_analyze;explicit_assistant=scenario=='explicit_assistant_delegates'
            directory=Path(tempfile.mkdtemp(prefix='c33-context-cpu-',dir=ROOT.parent/'runtime/tmp'));source=directory/'preparation.db'
            server=create_server(str(source),port=0);prep=[]
            try:
                prep.append(run_chat(server,'柜门标签写着AB-2738。这是本轮查询资料。'))
                prep.append(run_chat(server,'面试又没过，整个人像泄了气。' if scenario!='neutral' else '桌上有两本册子。'))
            finally:server.server_close()
            targets=[directory/'current.db',directory/'candidate.db'];backup=backup_pair(source,targets,preparation_worker_closed=True)
            pair=[];initial_source=logical_dump(source)
            for arm,path in zip(('current_analysis','lab_readonly_candidate'),targets,strict=True):
                Avatar._analyze=original_analyze;decisions=[];calls.clear()
                if arm=='lab_readonly_candidate':install(decisions)
                server=create_server(str(path),port=0)
                assert server.emotion.state.valence==server.emotion.state.arousal==server.emotion.user_state.valence==server.emotion.user_state.arousal==0
                try:result=run_chat(server,'我叫顾禾。' if scenario=='current_name_delegates' else probe)
                finally:server.server_close()
                generation=next(c for c in calls if c['kind']=='generation')
                assert len(generation['messages'][1:-1])==4
                with closing(MemoryStore(str(path))) as memory:
                    messages=[dict(r) for r in memory._conn.execute('SELECT * FROM memory_messages ORDER BY id')]
                    dependencies=[dict(r) for r in memory._conn.execute('SELECT * FROM memory_response_context WHERE message_id=6')]
                    assert len(messages)==6 and {1,2,3,4,5}<={r['source_id'] for r in dependencies if r['source_type']=='message'}
                    profile=memory.get_user_profile()
                    if scenario=='current_name_delegates':assert profile['名字']=='顾禾'
                skipped=result['analysis_mode']=='lab_readonly_context_rules'
                assert skipped==(arm=='lab_readonly_candidate' and scenario in ('implicit_neutral_assistant','neutral'))
                pair.append({'arm':arm,'result':result,'calls':deepcopy(calls),'decisions':decisions,'profile':profile,'messages':messages,'dependencies':dependencies,'history':generation['messages'][1:-1]})
            assert pair[0]['history']==pair[1]['history'] and logical_dump(source)==initial_source
            if scenario=='implicit_neutral_assistant':assert pair[0]['result']['user_valence']<0 and pair[1]['result']['user_valence']==0
            elif scenario!='current_name_delegates':assert pair[0]['result']['user_valence']==pair[1]['result']['user_valence']
            rows.append({'control':scenario,'backup':backup,'shared_preparation':prep,'arms':pair,'passed':True})
        # Independent deletion in one arm must not affect the sibling or original.
        sibling_before=logical_dump(targets[1]);source_before=logical_dump(source)
        with closing(MemoryStore(str(targets[0]))) as memory:
            fragment=memory.remember('柜门标签写着AB-2738。',source_message_id=1);memory.forget(fragment)
            redacted={r['id'] for r in memory._conn.execute('SELECT id FROM memory_messages WHERE content=?',('[redacted]',))}
            assert 1 in redacted and 6 in redacted and memory.context_revision==1
        assert logical_dump(targets[1])==sibling_before and logical_dump(source)==source_before
        rows.append({'control':'independent_arm_forget','redacted_message_ids':sorted(redacted),'sibling_and_preparation_unchanged':True,'passed':True})
        for name,owned_targets,closed in (('live_preparation',[directory/'fresh-a.db',directory/'fresh-b.db'],False),('existing_targets',targets,True),('unowned_target',[ROOT/'forbidden-c33.db',directory/'fresh-c.db'],True)):
            try:backup_pair(source,owned_targets,preparation_worker_closed=closed);raise AssertionError('Unsafe clone accepted')
            except ValueError:pass
            assert not (ROOT/'forbidden-c33.db').exists()
            rows.append({'control':name,'rejected_before_backup':True,'passed':True})
    finally:main_module.LLMEngine=original_model;Avatar._analyze=original_analyze
    with target.open('x') as out:json.dump({'passed':True,'actual_llm_or_gpu':False,'http_or_os_restart_claim':False,'fake_model_methods':True,'controls':rows},out,ensure_ascii=False,indent=2);out.write('\n')
    print('8 CPU controls passed:4 real in-process shared-history arm pairs, independent derived deletion and3 admission rejections; fake model only, no HTTP/OS/GPU claim.')


if __name__=='__main__':main()
