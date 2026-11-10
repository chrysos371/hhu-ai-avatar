import pytest
from avatar.cancellation import CancellationToken
from avatar.main import Avatar


class StreamingDraft:
    available=True
    def chat_analysis(self,messages,**kwargs):return '{}'
    def chat(self,messages,**kwargs):return '老师您好，我是【姓名】，申请明天请假。'
    def stream_chat(self,messages,*,on_delta=None,**kwargs):
        text='老师您好，我要请假。'
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
