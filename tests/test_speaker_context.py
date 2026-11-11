from contextlib import closing
import json

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain.speaker_context import SpeakerContextStore


def observe(memory, text):
    with memory.transaction():
        ident = memory.add_message('user', text, 'test-session')
        return SpeakerContextStore(memory).observe(text, memory.context_revision, ident)


def test_real_context_and_sticky_role_restore_from_bounded_live_sources(tmp_path):
    path = str(tmp_path/'context.db')
    with closing(MemoryStore(path)) as memory:
        observe(memory, '我喜欢骑车。')
    with closing(MemoryStore(path)) as memory:
        scope = observe(memory, '现在不喜欢了。')
        assert scope.context == ['我喜欢骑车。']
        role = observe(memory, '我来扮演小说角色。')
        source = role.source_ids[0]
        for _ in range(24): observe(memory, '继续聊剧情。')
    with closing(MemoryStore(path)) as memory:
        scope = observe(memory, '我叫林悦。')
        assert not scope.allows_facts and not scope.allows_actions and scope.source_ids == [source]
        assert json.loads(memory._conn.execute('SELECT source_ids_json FROM memory_web_speaker_state').fetchone()[0]) == [source]


def test_privacy_invalidation_removes_all_old_control_and_real_context_sources(tmp_path):
    path = str(tmp_path/'context.db')
    with closing(MemoryStore(path)) as memory:
        fact = memory.remember_user('名字', '旧名')
        observe(memory, '我来扮演小说角色。')
    with closing(MemoryStore(path)) as other:
        other.forget(fact)
    with closing(MemoryStore(path)) as memory:
        scope = observe(memory, '现在不喜欢了。')
        assert scope.allows_facts and scope.context == []
        assert scope.revision == 1


@pytest.mark.parametrize('source', ['我来扮演小说角色。', '之前只是普通聊天。'])
def test_legacy_or_untracked_user_speech_requires_explicit_real_confirmation(tmp_path, source):
    with closing(MemoryStore(str(tmp_path/'context.db'))) as memory:
        memory.add_message('user', source, 'legacy-cli')
        scope = observe(memory, '我叫新名。')
        assert scope.scope == 'unverified' and not scope.allows_facts and not scope.allows_actions
        assert '无法核验' in scope.prompt()
        scope = observe(memory, '回到现实。')
        assert scope.allows_facts and not scope.allows_actions
        assert observe(memory, '提醒我明天9点带伞。').allows_actions


def test_other_writer_gap_cannot_be_skipped_by_a_previously_tracked_state(tmp_path):
    path = str(tmp_path/'context.db')
    with closing(MemoryStore(path)) as memory:
        observe(memory, '你好。')
        with closing(MemoryStore(path)) as other:
            other.add_message('user', '我来扮演小说角色。', 'cli')
        assert observe(memory, '提醒我明天9点带伞。').scope == 'unverified'


@pytest.mark.parametrize('change', ['json', 'missing', 'assistant', 'redacted', 'ordering', 'wrong_scope', 'format'])
def test_corrupt_or_missing_source_never_becomes_real_authority(tmp_path, change):
    with closing(MemoryStore(str(tmp_path/'context.db'))) as memory:
        source = observe(memory, '我来扮演小说角色。').source_ids[0]
        if change == 'json': memory._conn.execute("UPDATE memory_web_speaker_state SET source_ids_json='bad'")
        elif change == 'missing': memory._conn.execute('DELETE FROM memory_messages WHERE id=?', (source,))
        elif change == 'assistant': memory._conn.execute("UPDATE memory_messages SET role='assistant' WHERE id=?", (source,))
        elif change == 'redacted': memory._conn.execute("UPDATE memory_messages SET content='[redacted]' WHERE id=?", (source,))
        elif change == 'ordering': memory._conn.execute('UPDATE memory_web_speaker_state SET source_ids_json=?', (json.dumps([source,source]),))
        elif change == 'wrong_scope': memory._conn.execute("UPDATE memory_web_speaker_state SET scope='current_user'")
        elif change == 'format': memory._conn.execute('UPDATE memory_web_speaker_state SET format_version=99')
        memory._conn.commit()
        scope = observe(memory, '我叫新名。')
        assert scope.scope == 'unverified' and not scope.allows_facts and not scope.allows_actions
        assert observe(memory, '回到现实。').allows_facts


def test_source_and_control_commit_or_rollback_together(tmp_path):
    with closing(MemoryStore(str(tmp_path/'context.db'))) as memory:
        with pytest.raises(RuntimeError, match='abort transaction'):
            with memory.transaction():
                ident = memory.add_message('user', '我来扮演小说角色。', 'test')
                SpeakerContextStore(memory).observe('我来扮演小说角色。', 0, ident)
                raise RuntimeError('abort transaction')
        assert memory._conn.execute('SELECT COUNT(*) FROM memory_messages').fetchone()[0] == 0
        assert memory._conn.execute('SELECT COUNT(*) FROM memory_web_speaker_state').fetchone()[0] == 0
        assert observe(memory, '我叫陈宁。').allows_facts


def test_two_connections_always_read_latest_scope_in_the_source_transaction(tmp_path):
    path = str(tmp_path/'context.db')
    with closing(MemoryStore(path)) as first, closing(MemoryStore(path)) as second:
        observe(first, '你好。')
        observe(second, '我来扮演小说角色。')
        assert not observe(first, '提醒我明天9点带伞。').allows_actions
        observe(second, '回到现实。')
        assert observe(first, '提醒我明天9点带伞。').allows_actions


def test_source_identity_and_current_version_are_checked_before_persistence(tmp_path):
    from avatar.cancellation import Cancelled
    with closing(MemoryStore(str(tmp_path/'context.db'))) as memory:
        with memory.transaction():
            ident = memory.add_message('user', '我叫陈宁。', 'test')
            with pytest.raises(ValueError): SpeakerContextStore(memory).observe('different', 0, ident)
            with pytest.raises(Cancelled): SpeakerContextStore(memory).observe('我叫陈宁。', 1, ident)


def test_control_root_and_real_reference_window_stay_bounded_across_reopens(tmp_path):
    path = str(tmp_path/'context.db')
    with closing(MemoryStore(path)) as memory:
        root = observe(memory, '回到现实。').source_ids[0]
        for index in range(40): scope = observe(memory, f'这是现实聊天第{index}条。')
        assert len(scope.source_ids) == 4 and scope.source_ids[0] == root
    with closing(MemoryStore(path)) as memory:
        scope = observe(memory, '下一条现实消息。')
        assert len(scope.context) == 3 and len(scope.source_ids) == 4
        assert scope.context == [f'这是现实聊天第{index}条。' for index in [37,38,39]]
