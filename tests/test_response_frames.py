"""Source roots survive long editing and restart, but not redaction or lost state."""
from contextlib import closing

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain.response_frames import ResponseFrames, _advance_frame
from avatar.cancellation import Cancelled


@pytest.mark.parametrize('text,writing,expected', [
    ('请把“我明天陪你去骑车”改得更客气。', False, True),
    ('替我回复朋友，原样写出“周六我陪你去游泳”。', False, True),
    ('请原样写出“我已经把材料发给老师了”。', False, True),
    ('分析“替我回复朋友”这句话。', False, False),
    ('帮我发短信给朋友。', False, False),
    ('等我把消息写好，你能替我发送吗？', False, False),
    ('我已经写好一条短信了。', False, False),
    ('我已经写好一条短信了。', True, False),
    ('请解释怎么写一条短信。', False, False),
    ('请提醒我明天下午3点写一条短信。', False, False),
    ('再短一点。', True, True), ('再短一点。', False, False),
    ('你刚才真的发出去了吗？', True, False),
    ('不写了。', True, False),
    ('帮我写一条短信。不写了，现在聊现实。', False, None),
])
def test_explicit_grammar_does_not_treat_quote_as_instruction(text, writing, expected):
    assert _advance_frame(text, writing)[0] is expected


def observe(memory, frames, text, session='s'):
    ident = memory.add_message('user', text, session)
    return frames.observe(text, memory.context_revision, ident, session_id=session)


def test_long_edits_and_real_reopen_keep_only_root_id_not_a_private_copy(tmp_path):
    path = str(tmp_path/'frames.db')
    with closing(MemoryStore(path)) as memory:
        frames = ResponseFrames(memory)
        root = observe(memory, frames, '请把“我明天陪你去骑车”改得更客气。').root_id
        for _ in range(40):
            assert observe(memory, frames, '再短一点。').root_id == root
    with closing(MemoryStore(path)) as memory:
        frames = ResponseFrames(memory)
        current = observe(memory, frames, '再自然一点。', 'after-restart')
        assert current.frame == 'writing' and current.root_id == root and current.parsed_sources == 1
        row = dict(memory._conn.execute('SELECT * FROM memory_response_frames').fetchone())
        assert set(row) == {'id', 'format_version', 'context_revision', 'cursor', 'frame', 'root_id'}


@pytest.mark.parametrize('damage', ['revision', 'redacted_root', 'bad_cursor', 'pending_limit'])
def test_missing_provenance_never_becomes_a_creative_exemption(damage):
    with closing(MemoryStore(':memory:')) as memory:
        frames = ResponseFrames(memory)
        root = observe(memory, frames, '帮我写一条短信。').root_id
        if damage == 'revision':
            with memory.transaction():
                memory._invalidate_context()
        elif damage == 'redacted_root':
            memory._conn.execute("UPDATE memory_messages SET content='[redacted]' WHERE id=?", (root,))
            memory._conn.commit()
        elif damage == 'bad_cursor':
            memory._conn.execute('UPDATE memory_response_frames SET cursor=-1')
            memory._conn.commit()
        else:
            for _ in range(65):
                memory.add_message('user', '再短一点。', 'other')
        result = observe(memory, frames, '再短一点。')
        assert result.frame == 'unverified' and result.root_id is None and result.parsed_sources <= 1


def test_assistant_words_do_not_end_writing_but_real_user_end_does():
    with closing(MemoryStore(':memory:')) as memory:
        frames = ResponseFrames(memory)
        root = observe(memory, frames, '帮我写一条短信。').root_id
        for _ in range(100):
            memory.add_message('assistant', '不写了。', 's')
        assert observe(memory, frames, '再短一点。').root_id == root
        memory.add_message('user', '不写了。', 'other')
        assert observe(memory, frames, '今天想聊现实。').frame == 'ordinary'


def test_wrong_session_source_and_late_turn_cannot_rewrite_control():
    with closing(MemoryStore(':memory:')) as memory:
        frames = ResponseFrames(memory)
        first = memory.add_message('user', '帮我写一条短信。', 's')
        last = memory.add_message('user', '不写了。', 's')
        frames.observe('不写了。', memory.context_revision, last, session_id='s')
        stale = frames.observe('帮我写一条短信。', memory.context_revision, first, session_id='s')
        assert stale.frame == 'unverified' and stale.reason == 'state_ahead'
        assert memory._conn.execute('SELECT cursor FROM memory_response_frames').fetchone()[0] == last
        with pytest.raises(Cancelled):
            frames.observe('不写了。', memory.context_revision, last, session_id='wrong')
