import pytest

from avatar.brain.analysis_routing import impersonal_knowledge_question
from avatar.brain.llm import LLMEngine
from avatar.cancellation import CancellationToken
from avatar.lab.transport_fixture import controlled_provider
from avatar.main import Avatar


@pytest.mark.parametrize('text', ['请简短解释云为什么会移动。', '什么是二进制？', '请介绍 Python 排序算法。'])
def test_impersonal_whitelisted_questions_are_eligible(text):
    assert impersonal_knowledge_question(text)


@pytest.mark.parametrize('text', ['我叫小林', '我喜欢云', '请解释我为什么难过', '请解释什么是情绪模型',
    '请解释朋友拒绝一起看云的原因', '请解释Python让人崩溃的地方', '你记得我喜欢下雨吗',
    '请解释我以前想自杀，现在又想死', '请说明同学的矩阵作业为什么让我焦虑', '提醒我明天看云',
    '请解释这句：我叫小林', '什么是陪伴', '请介绍一份规划', '我现在不开心', '请解释小海的情感',
    '请解释雨天失去家人的感觉', '什么是我喜欢的排序方法', '请简短解释为什么失恋', '请解释云。' * 50])
def test_personal_emotional_or_unknown_domains_keep_full_analysis(text):
    assert not impersonal_knowledge_question(text)


def test_fast_route_preserves_fixture_reply_strategy_and_memory_without_quality_claims():
    with controlled_provider(delay=0.001) as (_, url):
        engine = LLMEngine(base_url=url, api_key='local-fixture', model='fixture')
        avatars = [Avatar(db_path=':memory:', llm=engine, fast_analysis=enabled) for enabled in (False, True)]
        try:
            outputs = [avatar.respond('请简短解释云为什么会移动。', cancel=CancellationToken()) for avatar in avatars]
            assert outputs[0]['analysis_mode'] == 'llm'
            assert outputs[1]['analysis_mode'] == 'impersonal_knowledge_rules'
            assert {key: outputs[0][key] for key in ('reply', 'strategy', 'user_valence', 'user_arousal')} == {
                key: outputs[1][key] for key in ('reply', 'strategy', 'user_valence', 'user_arousal')}
            assert all(avatar.memory.get_user_profile() == {} for avatar in avatars)
        finally:
            for avatar in avatars:
                avatar.memory.close()
            engine.close()
