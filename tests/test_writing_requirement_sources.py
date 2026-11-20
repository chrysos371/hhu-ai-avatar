"""Actual source-bound requirements, not a model's claim of task compliance."""
from contextlib import closing
import json

import pytest

from avatar.brain.memory import MemoryStore
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder


def bot(memory):
    return Avatar(memory=memory, llm=Recorder('老师您好。申请请假，敬请批准。\n【姓名】'),
        capability_contract_enabled=True)


def requirements(result):
    data = result.get('writing_requirements')
    assert data is not None, 'actual source requirements must be inspectable'
    return data


def test_signature_body_and_sentence_requirements_bind_actual_distinct_user_sources():
    with closing(MemoryStore(':memory:')) as memory:
        instance = bot(memory)
        first = instance.respond('帮我写一条请假短信，署名用【姓名】，只给正文。')
        one = requirements(first)
        assert one['source_verified'] and one['signature'] == '【姓名】' and one['body_only']
        assert not one['semantic_verifier']
        second = instance.respond('保留原意，压缩到两句话。')
        two = requirements(second)
        assert two['sentence_count'] == 2 and two['signature'] == '【姓名】'
        sources = {first['conversation']['user_message_id'], second['conversation']['user_message_id']}
        assert set(two['source_message_ids']) == sources
        assistant = second['conversation']['assistant_message_id']
        actual = {r[0] for r in memory._conn.execute("SELECT source_id FROM memory_response_context WHERE message_id=? AND source_type='message'", (assistant,))}
        assert sources <= actual


def test_material_constraint_survives_forty_polish_turns_and_real_database_reopen(tmp_path):
    path = str(tmp_path/'writing.db')
    with closing(MemoryStore(path)) as memory:
        instance = bot(memory)
        root = instance.respond('帮我给老师写一封邮件，署名用【作者】，只给正文。')['conversation']['user_message_id']
        count = instance.respond('保留原意，压缩到两句话。')['conversation']['user_message_id']
        for _ in range(40):
            data = requirements(instance.respond('再短一点。'))
            assert data['signature'] == '【作者】' and data['sentence_count'] == 2
    with closing(MemoryStore(path)) as memory:
        result = bot(memory).respond('再自然一点。')
        data = requirements(result)
        assert data['source_verified'] and data['signature'] == '【作者】' and data['sentence_count'] == 2
        assert {root, count} <= set(data['source_message_ids'])
        row = memory._conn.execute('SELECT * FROM memory_writing_requirements').fetchone()
        assert '【作者】' not in json.dumps(dict(row), ensure_ascii=False)
        assert '邮件' not in json.dumps(dict(row), ensure_ascii=False)


def test_current_replacement_release_and_new_root_do_not_revive_old_fields():
    with closing(MemoryStore(':memory:')) as memory:
        instance = bot(memory)
        instance.respond('帮我写请假短信，署名用【姓名】，只给正文。')
        changed = requirements(instance.respond('再短一点，署名改成【编号】。'))
        assert changed['signature'] == '【编号】'
        released = requirements(instance.respond('再自然一点，不要署名。'))
        assert released['signature'] is None
        new = requirements(instance.respond('帮我写一封感谢邮件，署名用【新作者】。'))
        assert new['signature'] == '【新作者】' and new['sentence_count'] is None and not new['body_only']


def test_quoted_or_code_constraints_are_artifact_data_and_not_source_controls():
    with closing(MemoryStore(':memory:')) as memory:
        instance = bot(memory)
        result = instance.respond('帮我写一段说明，原样包含“署名用【小明】，压缩到两句话”。')
        data = requirements(result)
        assert data['source_verified'], 'quote exclusion must run inside an actual writing frame'
        assert data['signature'] is None and data['sentence_count'] is None


@pytest.mark.parametrize('which', ['root', 'sentence'])
def test_actual_forget_of_any_required_source_invalidates_recovered_constraints(tmp_path, which):
    with closing(MemoryStore(str(tmp_path/'forget.db'))) as memory:
        instance = bot(memory)
        root = instance.respond('帮我写一封请假邮件，署名用【姓名】。')['conversation']['user_message_id']
        count = instance.respond('保留原意，压缩到两句话。')['conversation']['user_message_id']
        fragment = memory.remember('有来源的控制', source_message_id=root if which == 'root' else count)
        with closing(MemoryStore(memory.db_path)) as writer:
            writer.forget(fragment)
        result = instance.respond('再短一点。')
        data = requirements(result)
        assert not data['source_verified']
        assert data['signature'] is None and data['sentence_count'] is None
        assert data['source_message_ids'] == []
