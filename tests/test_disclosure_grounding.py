import json
from pathlib import Path

import pytest

from avatar.brain.profile_grounding import acknowledge_disclosure
from avatar.main import Avatar

SPEC = json.loads((Path(__file__).resolve().parents[1] /
    'evals/interaction/cycle-02/disclosure-grounding-v2.json').read_text())


@pytest.mark.parametrize('case', SPEC['positive_fixtures'])
def test_source_confirmed_declarations(case):
    reply, action = acknowledge_disclosure(case['input'], case['profile'])
    assert action == case['action']
    assert not any(s in reply for s in ['我喜欢', '我也喜欢', '我陪你去', '我们一起'])
    if action == 'third_party_introduction':
        assert reply == '谢谢你介绍身边的人。'


@pytest.mark.parametrize('case', SPEC['negative_fixtures'])
def test_mixed_tasks_emotional_talk_and_unconfirmed_records_remain_unrouted(case):
    assert acknowledge_disclosure(case['input'], case['profile']) == (None, None)


class ShouldNotGenerate:
    available = True
    def chat_analysis(self, messages, **kwargs):
        return '{}'
    def chat(self, messages, **kwargs):
        raise AssertionError('Deterministic acknowledgement should not call generation')


def test_real_pipeline_binds_current_source_and_cleans_derived_acknowledgement():
    avatar = Avatar(db_path=':memory:', llm=ShouldNotGenerate(), profile_grounding_enabled=True)
    try:
        first = avatar.respond('我不喜欢游泳，我喜欢爬山。')
        assert first['generation_mode'] == 'profile_grounded'
        assert first['profile_grounding']['action'] == 'profile_disclosure'
        assert '不喜欢游泳' in first['reply']
        fragment = next(row for row in avatar.list_memories() if '喜欢爬山' in row['content'])
        avatar.forget_memory(fragment['id'])
        assert all('爬山' not in row[0] for row in avatar.memory._conn.execute(
            "SELECT content FROM memory_messages WHERE role='assistant'"))
        friend = avatar.respond('我的朋友叫顾清，我们刚认识。')
        assert friend['profile_grounding']['action'] == 'third_party_introduction'
        assert avatar.memory.get_user_profile().get('名字') is None
    finally:
        avatar.memory.close()
