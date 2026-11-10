import pytest
from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar


class Model:
    available=True
    def chat_analysis(self,*args,**kwargs):return '{}'
    def chat(self,*args,**kwargs):return '消息里保留旧名。'


def test_source_deleted_before_repair_never_sends_obsolete_draft_to_model(tmp_path):
    class Streaming(Model):
        def __init__(self):self.calls=0;self.repairs=[]
        def stream_chat(self,messages,**kwargs):
            self.calls+=1
            if self.calls==1:
                writer.forget(fragment)
                return '老师，我是旧名。'
            self.repairs.append(messages)
            return '老师，我是【姓名】。'
    path=str(tmp_path/'source.db');model=Streaming()
    avatar=Avatar(db_path=path,llm=model,task_contract_enabled=True,delivery_check_enabled=True)
    fragment=avatar.memory.remember_user('名字','旧名');writer=MemoryStore(path)
    try:
        with pytest.raises(Cancelled):
            avatar.respond('给老师写一条消息，保留【姓名】。',cancel=CancellationToken())
        assert not model.repairs
        assert avatar.tasks.current is None
    finally:writer.close();avatar.memory.close()


@pytest.mark.parametrize('operation',['forget','correct'])
def test_explicit_memory_change_clears_derived_task_source(operation):
    avatar=Avatar(db_path=':memory:',llm=Model(),task_contract_enabled=True,delivery_check_enabled=True)
    fragment=avatar.memory.remember_user('名字','旧名')
    try:
        avatar.respond('给老师写一条消息，保留“旧名”。')
        assert avatar.tasks.current is not None
        if operation=='forget':avatar.forget_memory(fragment)
        else:avatar.correct_memory(fragment,'名字: 新名')
        assert avatar.tasks.current is None
    finally:avatar.memory.close()


def test_external_revision_does_not_reuse_old_task_on_followup(tmp_path):
    path=str(tmp_path/'external.db')
    avatar=Avatar(db_path=path,llm=Model(),task_contract_enabled=True,delivery_check_enabled=True)
    fragment=avatar.memory.remember_user('名字','旧名');writer=MemoryStore(path)
    try:
        avatar.respond('给老师写一条消息，保留“旧名”。')
        writer.forget(fragment)
        result=avatar.respond('再短一点。')
        assert result['task'] is None
    finally:writer.close();avatar.memory.close()
