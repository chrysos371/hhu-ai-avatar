import pytest
from avatar.cancellation import CancellationToken
from avatar.main import Avatar


class StreamingDraft:
    available=True
    def __init__(self):self.stream_calls=0
    def chat_analysis(self,messages,**kwargs):return '{}'
    def chat(self,messages,**kwargs):return '老师您好，我是【姓名】，申请明天请假。'
    def stream_chat(self,messages,*,on_delta=None,**kwargs):
        self.stream_calls+=1
        text='老师您好，我要请假。' if self.stream_calls==1 else '老师您好，我是【姓名】，申请明天请假。'
        if on_delta:on_delta(text)
        return text


def test_only_repaired_delivery_is_emitted_as_delta():
    avatar=Avatar(db_path=':memory:',llm=StreamingDraft(),task_contract_enabled=True,delivery_check_enabled=True)
    pieces=[]
    try:
        result=avatar.respond('给老师写一条请假消息，保留【姓名】。',cancel=CancellationToken(),on_delta=pieces.append)
        assert result['delivery_check']['repair_succeeded']
        assert pieces==[result['reply']]
        assert all('【姓名】' in piece for piece in pieces)
    finally:avatar.memory.close()


def test_cancelled_repair_propagates_and_never_emits_or_commits_draft():
    from avatar.cancellation import Cancelled
    class Model(StreamingDraft):
        def __init__(self):self.calls=0
        def chat(self,*args,**kwargs):raise Cancelled('repair transport cancelled')
        def stream_chat(self,messages,*,on_delta=None,**kwargs):
            self.calls+=1
            if self.calls>1:raise Cancelled('repair transport cancelled')
            if on_delta:on_delta('草稿未带占位符。')
            return '草稿未带占位符。'
    avatar=Avatar(db_path=':memory:',llm=Model(),task_contract_enabled=True,delivery_check_enabled=True)
    pieces=[]
    try:
        with pytest.raises(Cancelled):
            avatar.respond('给老师写一条消息，保留【姓名】。',cancel=CancellationToken(),on_delta=pieces.append)
        assert not pieces
        assert avatar.memory._conn.execute("SELECT COUNT(*) FROM memory_messages WHERE role='assistant'").fetchone()[0]==0
    finally:avatar.memory.close()


def test_real_sdk_repair_cancellation_closes_pending_headers_without_deltas(tmp_path):
    import threading
    from avatar.brain.llm import LLMEngine
    from avatar.cancellation import Cancelled
    from avatar.lab.transport_fixture import controlled_provider
    with controlled_provider(delay=.01) as (server,url):
        class Engine(LLMEngine):
            def __init__(self,**kwargs):super().__init__(**kwargs);self.repair_started=threading.Event()
            def stream_chat(self,messages,**kwargs):
                if messages[-1]['content'].startswith('请修正上一稿'):
                    server.started.clear()
                    self.repair_started.set()
                    messages=messages[:-1]+[{'role':'user','content':'delay-headers'}]
                return super().stream_chat(messages,**kwargs)
        engine=Engine(base_url=url,api_key='local-fixture',model='fixture')
        db_path=str(tmp_path/'repair.db')
        token,pieces,outcome=CancellationToken(),[],[]
        def work():
            avatar=Avatar(db_path=db_path,llm=engine,task_contract_enabled=True,delivery_check_enabled=True)
            try:avatar.respond('给老师写一条消息，保留【姓名】。',cancel=token,on_delta=pieces.append)
            except Cancelled:outcome.append('cancelled')
            finally:avatar.memory.close()
        thread=threading.Thread(target=work)
        thread.start()
        try:
            assert engine.repair_started.wait(3)
            assert server.started.wait(3)
            token.cancel();thread.join(2)
            assert outcome==['cancelled'] and not thread.is_alive()
            assert server.disconnected.wait(2)
            assert not pieces
            import sqlite3
            with sqlite3.connect(db_path) as db:
                assert db.execute("SELECT COUNT(*) FROM memory_messages WHERE role='assistant'").fetchone()[0]==0
        finally:
            token.cancel();thread.join(3);engine.close()


@pytest.mark.parametrize('operation',['forget','correct'])
def test_external_context_change_stops_later_unbuffered_sentences(tmp_path,operation):
    from avatar.brain.memory import MemoryStore
    from avatar.cancellation import Cancelled
    class Model(StreamingDraft):
        def stream_chat(self,messages,*,on_delta=None,**kwargs):
            on_delta('第一句。')
            if operation=='forget':writer.forget(fragment)
            else:writer.correct(fragment,'名字: 新名')
            on_delta('你叫旧名。')
            return '第一句。你叫旧名。'
    db_path=str(tmp_path/'external.db')
    avatar=Avatar(db_path=db_path,llm=Model())
    fragment=avatar.memory.remember_user('名字','旧名')
    writer=MemoryStore(db_path)
    pieces=[]
    try:
        with pytest.raises(Cancelled):
            avatar.respond('你好',cancel=CancellationToken(),on_delta=pieces.append)
        assert pieces==['第一句。']
        assert avatar.memory._conn.execute("SELECT COUNT(*) FROM memory_messages WHERE role='assistant'").fetchone()[0]==0
    finally:writer.close();avatar.memory.close()
