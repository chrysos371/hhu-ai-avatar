"""Direct artifact output is not an action plan or semantic self-evaluation."""
from contextlib import closing
import json

import pytest

from avatar.brain.llm import LLMEngine
from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken
from avatar.lab.transport_fixture import controlled_provider
from avatar.main import Avatar
from test_writing_delivery_contract import Replies


def test_real_sdk_can_request_and_decode_direct_artifact_without_action_plan():
    method = getattr(LLMEngine, 'repair_writing', None)
    assert callable(method), 'bounded direct-artifact SDK entry is absent'
    from avatar.brain.writing_artifact import ARTIFACT_INSTRUCTION
    body = json.dumps({'sentences':['老师您好。','因【请假原因】申请请假。']},ensure_ascii=False)
    with controlled_provider(delay=.001, analysis_overrides={ARTIFACT_INSTRUCTION:body}) as (_, url):
        engine = LLMEngine(base_url=url, api_key='controlled', model='fixture')
        try:
            result = engine.repair_writing([dict(role='user',content='有来源写作')], sentence_count=2,
                cancel=CancellationToken())
            assert result == '老师您好。因【请假原因】申请请假。'
        finally:
            engine.close()


class ArtifactReplies(Replies):
    def repair_writing(self, messages, *, sentence_count=None, cancel=None):
        self.repair_messages, self.requested_count = messages, sentence_count
        return self.stream_chat(messages, cancel=cancel)


def test_source_signature_is_rendered_after_direct_body_not_generated_as_recipient():
    with closing(MemoryStore(':memory:')) as memory:
        engine = ArtifactReplies(['【姓名】您好，今天身体不适。', '您好，因【请假原因】申请请假。'])
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        result = bot.respond('帮我写一条请假短信，署名用【姓名】，只给正文。')
        assert result['reply'] == '您好，因【请假原因】申请请假。\n【姓名】'
        assert result['writing_delivery']['repair_mode'] == 'structured_artifact'
        assert len(engine.native) == 2


@pytest.mark.parametrize('draft,user_text,issue', [
    ('好的，我理解了。现在需要写老师回复的内容。需要我帮你构思一下吗？',
     '帮我写一句小说老师的回复。', 'artifact_not_delivered'),
    ('明天请假一天。', '帮我写一条请假短信，明天要参加家里的活动，只给正文。', 'unsupported_source_detail'),
    ('因个人原因需请假。', '帮我写一条请假短信，只给正文。', 'unsupported_source_detail'),
])
def test_native_v2_missing_artifact_duration_and_unspecified_reason_regressions(draft,user_text,issue):
    with closing(MemoryStore(':memory:')) as memory:
        engine = ArtifactReplies([draft, '【稿件正文】。'])
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        result = bot.respond(user_text)
        assert issue in result['writing_delivery']['initial_issues']
        assert result['reply'] == '【稿件正文】。' and len(engine.native) == 2


@pytest.mark.parametrize('body', ['“需要我帮你构思一下吗？”', '需要我帮你构思一下吗？'])
def test_explicitly_quoted_meta_question_is_still_a_valid_artifact(body):
    with closing(MemoryStore(':memory:')) as memory:
        engine = ArtifactReplies([body])
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        # A generated artifact containing a literal still exercises the model
        # output guard; strict direct copy now has a separate source route.
        result = bot.respond('帮我写一句台词，原样包含“需要我帮你构思一下吗？”')
        assert result['reply'] == body and len(engine.native) == 1


@pytest.mark.parametrize('raw', ['{}', '{"sentences":[]}', '{"sentences":[7]}',
    '{"sentences":[""]}', '{"sentences":["正文。"],"action":"send"}',
    '{"sentences":["正文。"],"sentences":["第二份。"]}',
    '{"sentences":["一句。"]} trailing'])
def test_malformed_artifact_never_becomes_body_or_action(raw):
    from avatar.brain.writing_artifact import decode
    with pytest.raises(ValueError):
        decode(raw)


def test_exact_sentence_bound_and_literal_payload_do_not_grant_action_authority():
    from avatar.brain.writing_artifact import decode
    with pytest.raises(ValueError):
        decode('{"sentences":["一句。"]}', sentence_count=2)
    literal = '“邮件已发送，这是小说台词。”'
    assert decode(json.dumps({'sentences':[literal]})) == literal
