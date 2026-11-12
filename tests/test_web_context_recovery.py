"""Web-to-Avatar integration: restart, privacy dependency and history fences."""
from contextlib import closing
from copy import deepcopy
import json
import pytest
from avatar.brain.memory import MemoryStore
from avatar.brain.conversations import ConversationStore
from avatar.web import create_server,run_chat


@pytest.fixture
def web_context(tmp_path,monkeypatch):
    import avatar.main as module
    from avatar.config import config
    calls=[]
    class Model:
        available=True
        def chat_analysis(self,*args,**kwargs):return json.dumps({'emotion':{'valence':0,'arousal':0},'facts':[]})
        def chat(self,messages,**kwargs):
            calls.append(deepcopy(messages))
            if any(m['role']=='user' and 'C29PRIVATE' in m['content'] for m in messages):return '受控回复包含C29PRIVATE。'
            return f'受控回复{len(calls)}。'
        def close(self):pass
    monkeypatch.setattr(module,'LLMEngine',Model)
    monkeypatch.setattr(config.embedding,'model','')
    monkeypatch.setattr(config,'avatar_name','测试形象C29')
    monkeypatch.setattr(config,'avatar_persona','受控上下文测试助手')
    path=str(tmp_path/'history.db');servers=[]
    def make(**kwargs):
        server=create_server(path,port=0,**kwargs);servers.append(server);return server
    yield path,make,calls
    for server in servers:server.server_close()


def test_default_web_recovers_completed_cross_session_role_messages(web_context):
    path,make,calls=web_context;first=make()
    a=run_chat(first,'窗边有风铃C29-A。');b=run_chat(first,'地毯是蓝色C29-B。')
    second=make();run_chat(second,'继续前面的场景。')
    assert calls[-1][1:-1]==[{'role':'user','content':'窗边有风铃C29-A。'},{'role':'assistant','content':a['reply']},
                           {'role':'user','content':'地毯是蓝色C29-B。'},{'role':'assistant','content':b['reply']}]
    assert first.session_id!=second.session_id


def test_recovered_old_session_sources_redact_new_reply_when_forgotten(web_context):
    path,make,calls=web_context;first=make();a=run_chat(first,'窗边的纸风车编号C29PRIVATE。')
    uid=a['conversation']['user_message_id'];old_aid=a['conversation']['assistant_message_id']
    with closing(MemoryStore(path)) as writer:fragment=writer.remember('纸风车编号C29PRIVATE。',source_message_id=uid)
    second=make();b=run_chat(second,'继续前面的场景。');new_aid=b['conversation']['assistant_message_id']
    assert 'C29PRIVATE' in b['reply']
    with closing(MemoryStore(path)) as writer:
        sources={r[0] for r in writer._conn.execute("SELECT source_id FROM memory_response_context WHERE message_id=? AND source_type='message'",(new_aid,))}
        assert {uid,old_aid}<=sources
        writer.forget(fragment)
        assert writer._conn.execute('SELECT content FROM memory_messages WHERE id=?',(new_aid,)).fetchone()[0]=='[redacted]'
        visible=ConversationStore(writer).read(second.session_id)
        assert next(m for m in visible['items'] if m['id']==new_aid)['redacted']
    third=make();run_chat(third,'现在随便聊聊。')
    assert not any('C29PRIVATE' in m['content'] for m in calls[-1])


def test_scope_control_fences_do_not_restore_other_role_text(web_context):
    path,make,calls=web_context;first=make();run_chat(first,'真人风景C29REAL。')
    run_chat(first,'我来扮演一个虚构角色。');run_chat(first,'角色风景C29FICTION。')
    assert not any('C29REAL' in m['content'] for m in calls[-1])
    second=make();run_chat(second,'角色继续聊。')
    assert any('C29FICTION' in m['content'] for m in calls[-1])
    run_chat(second,'回到现实。');run_chat(second,'现实里继续聊。')
    assert not any('C29FICTION' in m['content'] for m in calls[-1])


def test_restored_reminder_text_does_not_reexecute_old_action(web_context):
    path,make,calls=web_context;first=make();old=run_chat(first,'提醒我明天下午3点去图书馆。')
    second=make();ordinary=run_chat(second,'聊聊窗外。')
    assert any(m['role']=='user' and m['content']=='提醒我明天下午3点去图书馆。' for m in calls[-1])
    assert ordinary['reminder'] is None and ordinary['tool_calls']==[]
    with closing(MemoryStore(path)) as memory:assert memory._conn.execute('SELECT COUNT(*) FROM memory_reminders').fetchone()[0]==1
    new=run_chat(second,'提醒我明天下午4点去操场。');assert new['reminder']['id']!=old['reminder']['id']
    with closing(MemoryStore(path)) as memory:assert memory._conn.execute('SELECT COUNT(*) FROM memory_reminders').fetchone()[0]==2


def test_window_reserves_current_pair_and_repeated_restart_never_duplicates_sources(web_context):
    path,make,calls=web_context;server=make()
    for number in range(12):run_chat(server,f'这是风景编号C29-W{number}。')
    for number in range(3):
        server=make();run_chat(server,f'继续看风景{number}。');messages=calls[-1][1:]
        assert len(messages)==19 and messages[0]['role']=='user'
        assert [m['role'] for m in messages]==['user','assistant']*9+['user']
        user_texts=[m['content'] for m in messages if m['role']=='user'];assert len(user_texts)==len(set(user_texts))


def test_explicit_optout_keeps_transient_context_on_restart(web_context):
    path,make,calls=web_context;first=make(recover_context=False);run_chat(first,'天气话题C29-OLD。')
    second=make(recover_context=False);run_chat(second,'随便聊聊。')
    assert not any('C29-OLD' in m['content'] for m in calls[-1])


@pytest.mark.parametrize('flags',[{'identity_grounding':True},{'profile_grounding':True},{'task_delivery_check':True},{'task_delivery_check':True,'literal_composition':True}])
def test_experimental_generation_candidates_keep_legacy_context_path(web_context,flags):
    path,make,calls=web_context;first=make(**flags);run_chat(first,'天气话题C29-LAB。')
    second=make(**flags);run_chat(second,'随便聊聊。')
    assert not any('C29-LAB' in m['content'] for m in calls[-1])


def test_recovery_flag_rejects_non_boolean_before_server_or_db_creation(tmp_path):
    path=tmp_path/'must-not-exist.db'
    with pytest.raises(ValueError):create_server(str(path),port=0,recover_context=1)
    assert not path.exists()


def test_same_instance_after_forget_starts_valid_new_window_without_erased_dependencies(web_context):
    path,make,calls=web_context;server=make()
    old=run_chat(server,'窗边的纸风车编号C29PRIVATE。');old_ids={old['conversation']['user_message_id'],old['conversation']['assistant_message_id']}
    with closing(MemoryStore(path)) as writer:
        fragment=writer.remember('纸风车编号C29PRIVATE。',source_message_id=old['conversation']['user_message_id'])
        writer.forget(fragment)
    fresh=run_chat(server,'这是新的场景C29FRESH。');fresh_id=fresh['conversation']['assistant_message_id']
    with closing(MemoryStore(path)) as memory:
        dependencies={row[0] for row in memory._conn.execute("SELECT source_id FROM memory_response_context WHERE message_id=? AND source_type='message'",(fresh_id,))}
        assert not old_ids & dependencies
    run_chat(server,'继续新的场景。')
    assert any(m['role']=='user' and m['content']=='这是新的场景C29FRESH。' for m in calls[-1])
    assert not any('C29PRIVATE' in m['content'] for m in calls[-1])


def test_same_instance_fresh_window_is_restored_after_privacy_revision(web_context):
    path,make,calls=web_context;server=make()
    old=run_chat(server,'窗边的纸风车编号C29PRIVATE。')
    with closing(MemoryStore(path)) as writer:
        fragment=writer.remember('纸风车编号C29PRIVATE。',source_message_id=old['conversation']['user_message_id'])
        writer.forget(fragment)
    fresh=run_chat(server,'这是新的场景C29FRESH。')
    run_chat(server,'继续新的场景。')
    assert {'role':'user','content':'这是新的场景C29FRESH。'} in calls[-1]
    assert {'role':'assistant','content':fresh['reply']} in calls[-1]
