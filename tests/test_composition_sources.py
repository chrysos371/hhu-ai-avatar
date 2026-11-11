import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import Cancelled
from avatar.lab.composition_sources import CompositionSources, advance_frame


@pytest.mark.parametrize('text,writing,expected', [
    ('替我回复朋友，原样写出“周六我陪你去游泳”，不要加解释。', False, True),
    ('请原样写出“我明天陪你去散步”。', False, True),
    ('分析“替我回复朋友”这句话。', False, False),
    ('再短一点。', True, True), ('不写了。', True, False),
    ('帮我写一条短信。不写了，现在聊现实。', False, None),
])
def test_source_parser_contract(text, writing, expected):
    assert advance_frame(text, writing)[0] is expected


def test_bounded_root_survives_window_and_new_memory_instance(tmp_path):
    path = str(tmp_path/'state.db')
    memory = MemoryStore(path); state = CompositionSources(memory)
    root = memory.add_message('user', '帮我给朋友写一条短信。', 's')
    first = state.observe('帮我给朋友写一条短信。', memory.context_revision, root)
    assert first.frame == 'writing' and first.root_id == root
    for _ in range(40):
        ident = memory.add_message('user', '再短一点。', 's')
        assert state.observe('再短一点。', memory.context_revision, ident).root_id == root
    memory.close()
    memory = MemoryStore(path); state = CompositionSources(memory)
    try:
        ident = memory.add_message('user', '再自然一点。', 'new-s')
        frame = state.observe('再自然一点。', memory.context_revision, ident)
        assert frame.frame == 'writing' and frame.root_id == root and frame.parsed_sources == 1
        record = dict(memory._conn.execute('SELECT * FROM lab_body_composition_state').fetchone())
        assert set(record) == {'id', 'format_version', 'context_revision', 'cursor', 'frame', 'root_id'}
    finally: memory.close()


@pytest.mark.parametrize('invalid', ['revision', 'redacted', 'cursor', 'pending'])
def test_invalid_state_does_not_replay_old_writing_or_invent_ordinary(invalid):
    memory = MemoryStore(':memory:'); state = CompositionSources(memory)
    try:
        root = memory.add_message('user', '帮我写一条短信。', 's')
        state.observe('帮我写一条短信。', memory.context_revision, root)
        if invalid == 'revision':
            with memory.transaction(): memory._invalidate_context()
        elif invalid == 'redacted': memory._conn.execute("UPDATE memory_messages SET content='[redacted]' WHERE id=?", (root,)); memory._conn.commit()
        elif invalid == 'cursor': memory._conn.execute('UPDATE lab_body_composition_state SET cursor=-1'); memory._conn.commit()
        else:
            for _ in range(65): memory.add_message('user', '再短一点。', 'other')
        ident = memory.add_message('user', '再短一点。', 's')
        result = state.observe('再短一点。', memory.context_revision, ident)
        assert result.frame == 'unverified' and result.root_id is None and result.parsed_sources <= 1
    finally: memory.close()


def test_pending_user_end_applies_but_assistant_gap_cannot_change_frame():
    memory = MemoryStore(':memory:'); state = CompositionSources(memory)
    try:
        root = memory.add_message('user', '帮我写一条短信。', 's')
        state.observe('帮我写一条短信。', memory.context_revision, root)
        for _ in range(100): memory.add_message('assistant', '不写了。', 'other')
        ident = memory.add_message('user', '再短一点。', 's')
        assert state.observe('再短一点。', memory.context_revision, ident).frame == 'writing'
        memory.add_message('user', '不写了。', 'other')
        ident = memory.add_message('user', '今天想聊现实。', 's')
        assert state.observe('今天想聊现实。', memory.context_revision, ident).frame == 'ordinary'
    finally: memory.close()


def test_old_completion_does_not_roll_cursor_back_and_current_source_must_match():
    memory = MemoryStore(':memory:'); state = CompositionSources(memory)
    try:
        a = memory.add_message('user', '帮我写一条短信。', 'a')
        b = memory.add_message('user', '不写了。', 'b')
        state.observe('不写了。', memory.context_revision, b)
        assert state.observe('帮我写一条短信。', memory.context_revision, a).reason == 'state_ahead'
        assert memory._conn.execute('SELECT cursor FROM lab_body_composition_state').fetchone()[0] == b
        with pytest.raises(Cancelled): state.observe('伪造源', memory.context_revision, b)
    finally: memory.close()
