"""Real restart, dependency tampering and late changes in profile reply paths."""
from contextlib import closing
import json

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import Cancelled, CancellationToken
from avatar.main import Avatar
from avatar.web import create_server, run_chat
from test_capability_prompt_lab import Recorder


@pytest.mark.parametrize('fault',[None,'source_hash','bool_id','reply_hash','extra_field'])
def test_actual_web_restart_recovers_only_source_checked_profile_reply(tmp_path,monkeypatch,fault):
    engines=[]
    def factory():
        engine=Recorder('普通回复');engines.append(engine);return engine
    monkeypatch.setattr('avatar.main.LLMEngine',factory)
    db=str(tmp_path/'profile.db')
    with closing(MemoryStore(db)) as memory:memory.remember_user('名字','陆遥')
    def make():return create_server(db,port=0,capability_contract_enabled=True,role_state_enabled=True)
    first=make()
    try:result=run_chat(first,'我叫什么名字？')
    finally:first.server_close()
    if fault:
        proof=result['profile_contract']
        if fault=='source_hash':proof['sources'][0]['content_sha256']='0'*64
        elif fault=='bool_id':proof['sources'][0]['fragment_id']=True
        elif fault=='reply_hash':proof['reply_sha256']='0'*64
        else:proof['hidden_claimed']=True
        with closing(MemoryStore(db)) as memory:
            with memory.transaction():memory._conn.execute('UPDATE memory_chat_results SET result_json=? WHERE message_id=?',
                (json.dumps(result),result['conversation']['assistant_message_id']))
    second=make()
    try:
        run_chat(second,'聊聊窗外。')
        histories=[m['content'] for m in engines[-1].native[-1] if m['role']=='assistant']
        assert any('rules_profile_source' in s for s in histories) is (fault is None)
    finally:second.server_close()


@pytest.mark.parametrize('change',['cancel','foreign_forget','foreign_profile_write'])
def test_late_actual_changes_cannot_publish_a_copied_profile_replacement(tmp_path,change):
    with closing(MemoryStore(str(tmp_path/'late-profile.db'))) as memory:
        fid=memory.remember_user('偏好','喜欢网球')
        token=CancellationToken();pieces=[]
        class Changed(Recorder):
            def stream_chat(self,messages,*,on_delta=None,**kwargs):
                if on_delta:on_delta(self.reply)
                if change=='cancel':token.cancel()
                else:
                    with closing(MemoryStore(memory.db_path)) as actor:
                        if change=='foreign_forget':actor.forget(fid)
                        else:actor.remember_user('偏好','喜欢跑步')
                return self.reply
        bot=Avatar(memory=memory,llm=Changed('我喜欢网球。'),capability_contract_enabled=True,role_state_enabled=True)
        with pytest.raises(Cancelled):bot.respond('今天聊聊。',cancel=token,on_delta=pieces.append)
        assert not pieces
        assert not memory._conn.execute("SELECT 1 FROM memory_messages WHERE role='assistant'").fetchone()


def test_new_name_does_not_rewrite_old_historical_name_reply(tmp_path,monkeypatch):
    engines=[]
    def factory():
        engine=Recorder('普通回复');engines.append(engine);return engine
    monkeypatch.setattr('avatar.main.LLMEngine',factory)
    db=str(tmp_path/'new-name.db')
    first=create_server(db,port=0,capability_contract_enabled=True,role_state_enabled=True)
    try:
        old=run_chat(first,'我叫什么名字？')
        assert '没有足够记录' in old['reply']
        with closing(MemoryStore(db)) as memory:memory.remember_user('名字','陆遥')
    finally:first.server_close()
    second=create_server(db,port=0,capability_contract_enabled=True,role_state_enabled=True)
    try:
        run_chat(second,'聊聊窗外。')
        old_text=[m['content'] for m in engines[-1].native[-1] if m['role']=='assistant']
        assert any(old['reply'] in s for s in old_text)
        assert not any('目前记录你使用的名字是陆遥' in s for s in old_text)
        current=run_chat(second,'我叫什么名字？')
        assert '陆遥' in current['reply']
    finally:second.server_close()
