import json
import pytest
from avatar.brain.memory import MemoryStore
from avatar.web import create_server, run_chat


@pytest.fixture
def experimental_server(tmp_path,monkeypatch):
    import avatar.main as main_module
    from avatar.config import config
    class Model:
        available=True
        def chat_analysis(self,*args,**kwargs):return '{}'
        def chat(self,*args,**kwargs):return '这是没有指定原文的初稿。'
        def compose_literal_slots(self,messages,layout,**kwargs):
            if hasattr(layout,'markers'):
                return json.dumps({'text':''.join(layout.markers)})
            return json.dumps({key:'' for key in layout.keys})
        def close(self):pass
    monkeypatch.setattr(main_module,'LLMEngine',Model)
    monkeypatch.setattr(config.embedding,'model','')
    path=str(tmp_path/'web-task.db')
    memory=MemoryStore(path);memory.close()
    server=create_server(path,port=0,task_delivery_check=True,literal_composition=True)
    yield server
    server.server_close()


def test_web_reconstructs_current_task_between_ephemeral_avatar_instances(experimental_server):
    server=experimental_server
    first=run_chat(server,'写一句台词，包含“原句”。',False)
    second=run_chat(server,'再短一点。',False)
    assert first['reply']==second['reply']=='原句'
    assert second['task']['required_literals']==['原句']
    third=run_chat(server,'换个话题。',False)
    assert third['task'] is None


def test_web_source_invalidation_drops_prior_task_before_replay(experimental_server):
    server=experimental_server
    writer=MemoryStore(server.db_path)
    try:
        fragment=writer.remember_user('名字','原名')
        run_chat(server,'写一句台词，包含“原句”。',False)
        writer.forget(fragment)
        result=run_chat(server,'再短一点。',False)
        assert result['task'] is None
    finally:writer.close()


def test_pure_task_replay_never_reexecutes_old_reminder(experimental_server):
    server=experimental_server
    run_chat(server,'提醒我明天9点带伞。',False)
    run_chat(server,'请写一条提醒，包含“带伞”。',False)
    reader=MemoryStore(server.db_path)
    try:
        assert reader._conn.execute('SELECT COUNT(*) FROM memory_reminders').fetchone()[0]==1
    finally:reader.close()


def test_composition_dependency_is_checked_before_creating_listener(tmp_path):
    with pytest.raises(ValueError):create_server(str(tmp_path/'unused.db'),port=0,literal_composition=True)


def test_new_question_releases_old_web_delivery_contract(experimental_server):
    server=experimental_server
    run_chat(server,'写一句台词，包含“原句”。',False)
    result=run_chat(server,'再问个问题，什么是二进制？',False)
    assert result['task'] is None
    assert result['delivery_check']['repair_attempted'] is False
