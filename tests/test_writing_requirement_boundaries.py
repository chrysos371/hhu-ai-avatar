"""Actual source fencing and bounded persistence, separate from body quality."""
from contextlib import closing

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain.writing_requirements import compile_sources
from avatar.cancellation import Cancelled
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder


@pytest.mark.parametrize('text,expected', [
    ('署名用 【署名】。', ('【署名】', None, False)),
    ('署名用“小海”。', ('“小海”', None, False)),
    ('原样包含“署名用【甲】，压缩到两句话，只给正文”。', (None, None, False)),
    ('原样包含`署名用【甲】，压缩到两句话，只给正文`。', (None, None, False)),
    ('原样包含```署名用【甲】，压缩到两句话，只给正文', (None, None, False)),
    ('署名用【只给正文】，压缩到两句话。', ('【只给正文】', 2, False)),
    ('是不是不要署名？', (None, None, False)),
])
def test_literal_and_code_spans_do_not_control_other_fields(text, expected):
    assert compile_sources([(1, text)]) == expected


def test_bounded_material_sources_fail_closed_and_new_root_recovers():
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Recorder('正文。'), capability_contract_enabled=True)
        bot.respond('帮我写一封邮件，署名用【甲】。')
        for _ in range(33):
            result = bot.respond('再短一点，保留原意。')
        assert not result['writing_requirements']['source_verified']
        assert result['writing_requirements']['source_message_ids'] == []
        result = bot.respond('帮我写一条短信，署名用【乙】。')
        assert result['writing_requirements']['signature'] == '【乙】'
        assert len(result['writing_requirements']['source_message_ids']) == 1


@pytest.mark.parametrize('stage', ['prompt', 'after_model'])
def test_actual_second_connection_forget_stops_old_requirements_publication(tmp_path, monkeypatch, stage):
    with closing(MemoryStore(str(tmp_path/'privacy.db'))) as memory:
        engine = Recorder('正文。')
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        root = bot.respond('帮我写一封邮件，署名用【待删】。')['conversation']['user_message_id']
        fragment = memory.remember('有来源的控制', source_message_id=root)
        def forget():
            with closing(MemoryStore(memory.db_path)) as writer:
                writer.forget(fragment)
        if stage == 'prompt':
            original = bot._system_prompt
            def system(*args):
                text = original(*args)
                forget()
                return text
            monkeypatch.setattr(bot, '_system_prompt', system)
        else:
            original = engine.chat
            def generate(*args, **kwargs):
                text = original(*args, **kwargs)
                forget()
                return text
            monkeypatch.setattr(engine, 'chat', generate)
        before = memory._conn.execute("SELECT COUNT(*) FROM memory_messages WHERE role='assistant'").fetchone()[0]
        with pytest.raises(Cancelled):
            bot.respond('再短一点。')
        assert memory._conn.execute("SELECT COUNT(*) FROM memory_messages WHERE role='assistant'").fetchone()[0] == before


def test_in_memory_requirement_is_rejected_after_actual_newer_admission():
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Recorder('正文。'), capability_contract_enabled=True)
        bot.respond('帮我写一封邮件，署名用【甲】。')
        old, frame = bot._writing_requirements, bot._response_frame
        bot.respond('再短一点，署名改成【乙】。')
        with pytest.raises(Cancelled):
            bot.writing_requirement_store.ensure_current(old, frame)


@pytest.mark.parametrize('column,value', [('cursor', 'broken'), ('source_ids', '{}'),
    ('source_ids', '[true]'), ('format_version', 77)])
def test_corrupt_requirement_metadata_never_restores_values(column, value):
    with closing(MemoryStore(':memory:')) as memory:
        engine = Recorder('正文。')
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        bot.respond('帮我写一封邮件，署名用【甲】。')
        before = len(engine.native)
        with memory.transaction():
            memory._conn.execute('UPDATE memory_writing_requirements SET ' + column + '=?', (value,))
        result = bot.respond('再短一点。')
        assert not result['writing_requirements']['source_verified']
        assert len(engine.native) == before, 'incomplete writing sources must not be guessed by generation'
        assert result['generation_mode'] == 'rules_writing_source'
