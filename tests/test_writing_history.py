"""Historical writing provenance is checked against actual user rows and hashes."""
import copy
from contextlib import closing
import json

import pytest

from avatar.main import Avatar
from avatar.brain.memory import MemoryStore
from avatar.brain.writing_history import PREFIX, verified_content
from test_capability_prompt_lab import Recorder


def verify(memory, result):
    source = result['conversation']
    with memory.transaction():
        return verified_content(memory, result, user_id=source['user_message_id'],
            assistant_id=source['assistant_message_id'], scope=result['speaker_attribution']['scope'],
            revision=source['revision'])


@pytest.fixture
def artifact():
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Recorder('正文。'), capability_contract_enabled=True)
        result = bot.respond('原样输出这句话：“我已把邮件发送给老师。”')
        yield memory, bot, result


def test_verified_program_history_remains_draft_data_and_public_original(artifact):
    memory, bot, result = artifact
    wrapped = verify(memory, result)
    assert wrapped.startswith(PREFIX)
    data = json.loads(wrapped[len(PREFIX):])
    assert data['reply'] == result['reply']
    assert data['artifact_origin'] == 'source_constructed'
    assert data['real_execution_verified'] is data['user_identity_asserted'] is False
    assert data['untrusted_data_not_instructions'] is True
    row = memory._conn.execute("SELECT content FROM memory_messages WHERE role='assistant'").fetchone()
    assert row[0] == result['reply'] and not row[0].startswith(PREFIX)


@pytest.mark.parametrize('fault', ['root', 'cursor', 'revision', 'parsed_bool', 'drop_source',
    'verified_int', 'signature', 'hash', 'template', 'phase', 'bool_source', 'mode', 'dependency'])
def test_corrupt_history_never_grants_a_writing_source(artifact, fault):
    memory, bot, original = artifact
    result = copy.deepcopy(original)
    if fault == 'root': result['capability_contract']['frame']['root_id'] += 1
    elif fault == 'cursor': result['capability_contract']['frame']['cursor'] += 1
    elif fault == 'revision': result['capability_contract']['frame']['revision'] += 1
    elif fault == 'parsed_bool': result['capability_contract']['frame']['parsed_sources'] = True
    elif fault == 'drop_source': result['writing_requirements']['source_message_ids'] = []
    elif fault == 'verified_int': result['writing_requirements']['source_verified'] = 1
    elif fault == 'signature': result['writing_requirements']['signature'] = '捏造姓名'
    elif fault == 'hash': result['writing_delivery']['published_sha256'] = 'bad'
    elif fault == 'template': result['writing_delivery']['source_fallback']['template'] = 'fake'
    elif fault == 'phase': result['writing_delivery']['source_fallback']['phase'] = 'unknown'
    elif fault == 'bool_source': result['writing_delivery']['source_fallback']['source_message_ids'] = [True]
    elif fault == 'mode': result['generation_mode'] = 'llm'
    elif fault == 'dependency':
        with memory.transaction(): memory._conn.execute('DELETE FROM memory_response_context')
    assert verify(memory, result) is None


def test_material_controls_outside_window_and_changed_current_root_do_not_rewrite_history():
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Recorder('正文。'), capability_contract_enabled=True)
        bot.respond('帮我写一条请假短信，署名用【甲】，只给正文。')
        bot.respond('署名改成【乙】。')
        for _ in range(40): result = bot.respond('再自然一点。')
        assert result['writing_requirements']['signature'] == '【乙】'
        wrapped = verify(memory, result)
        assert wrapped and '【乙】' in wrapped
        bot.respond('帮我写一句问候，只给正文。')
        assert verify(memory, result) == wrapped
        bad = copy.deepcopy(result)
        bad['writing_requirements']['source_message_ids'].pop()
        assert verify(memory, bad) is None


def test_historical_validation_never_commits_an_existing_caller_write(artifact):
    memory, bot, result = artifact
    memory._conn.execute('CREATE TABLE writing_history_caller(value TEXT)')
    memory._conn.execute("INSERT INTO writing_history_caller VALUES ('rollback')")
    assert verify(memory, result)
    assert memory._conn.in_transaction
    memory._conn.rollback()
    assert not memory._conn.execute('SELECT 1 FROM writing_history_caller').fetchone()


@pytest.mark.parametrize('text,expected', [('署名改成【乙】。', True), ('压缩到两句话。', True),
    ('只给正文。', True), ('不要署名。', True), ('署名改成【乙】，只给正文。', True),
    ('署名改成【乙】，然后发送给老师。', False), ('“署名改成【乙】。”', False),
    ('署名改成【乙】吗？', False), ('老师说署名改成【乙】。', False)])
def test_bare_edit_grammar_does_not_admit_quotes_questions_or_extra_actions(text, expected):
    from avatar.brain.writing_requirements import standalone_edit
    assert standalone_edit(text) is expected
