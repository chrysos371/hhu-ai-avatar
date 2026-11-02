"""Real SQLite regressions for current/history, durable evidence and editing."""
import sqlite3

import pytest

from avatar.brain.memory import MemoryStore


@pytest.fixture
def store():
    memory = MemoryStore(':memory:')
    yield memory
    memory.close()


def legacy_database(path):
    """A pre-upgrade database, independent of the new schema/migration."""
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE memory_fragments ('
                     'id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT NOT NULL, '
                     "memory_type TEXT NOT NULL DEFAULT 'fact', "
                     "category TEXT NOT NULL DEFAULT 'general', "
                     'importance REAL NOT NULL DEFAULT .5, '
                     'last_accessed REAL NOT NULL DEFAULT 0, '
                     'created_at REAL NOT NULL DEFAULT 0, content_vector BLOB)')
        for idx, content in enumerate([
            '名字: 小明', '偏好: 喜欢喝咖啡', '爱好: 篮球',
            '名字: 小红', '偏好: 不喜欢咖啡', '爱好: 游泳',
            '偏好: 讨厌咖啡', '爱好: 篮球',
        ], 1):
            conn.execute('INSERT INTO memory_fragments '
                         '(content,memory_type,created_at) VALUES (?, ?, ?)',
                         (content, 'user_profile', idx))


def test_legacy_migration_is_additive_idempotent_and_never_resurrects(tmp_path):
    path = tmp_path / 'legacy.db'
    legacy_database(path)
    memory = MemoryStore(str(path))
    assert len(memory.list_memories(include_history=True)) == 8
    profile = memory.get_user_profile()
    assert profile['名字'] == '小红'
    assert profile['偏好'] == '讨厌咖啡'
    assert set(profile['爱好'].split('；')) == {'篮球', '游泳'}
    assert all(row['status'] == 'active' for row in memory.recall())
    assert memory.recall('咖啡')[0]['id'] == 7
    memory.close()
    memory = MemoryStore(str(path))
    assert len(memory.list_memories(include_history=True)) == 8
    memory.forget(7)
    memory.close()
    memory = MemoryStore(str(path))
    assert memory.recall('咖啡', include_history=True) == []
    assert memory.get_user_profile()['名字'] == '小红'
    memory.close()


@pytest.mark.parametrize('positive,negative', [
    ('喜欢咖啡', '不喜欢咖啡'), ('喜欢喝咖啡', '讨厌咖啡'),
    ('爱咖啡', '不爱喝咖啡'), ('喜欢吃苹果', '不喜欢苹果'),
])
def test_conflicting_preference_versions_share_canonical_object(store, positive, negative):
    old = store.remember_user('偏好', positive)
    current = store.remember_user('偏好', negative)
    assert old != current
    assert store.get_user_profile()['偏好'] == negative
    assert [row['id'] for row in store.recall()] == [current]
    previous = store.inspect(old)
    assert previous['status'] == 'superseded'
    assert previous['valid_to'] is not None
    assert store.inspect(current)['predecessor_id'] == old
    assert len(store.recall(include_history=True)) == 2


def test_distinct_hobbies_and_preference_objects_coexist(store):
    for value in ('吃苦', '苦', '打篮球', '游泳'):
        store.remember_user('爱好', value)
    store.remember_user('偏好', '喜欢咖啡')
    store.remember_user('偏好', '不喜欢奶茶')
    assert set(store.get_user_profile()['爱好'].split('；')) == {'吃苦', '苦', '打篮球', '游泳'}
    assert len(store.recall()) == 6


def test_repeated_facts_append_durable_message_evidence(tmp_path):
    path = tmp_path / 'evidence.db'
    memory = MemoryStore(str(path), embedder=None)
    msg1 = memory.add_message('user', '我喜欢咖啡', 'session-a')
    fact = memory.remember_user('偏好', '喜欢咖啡', source_message_id=msg1, evidence='喜欢咖啡')
    msg2 = memory.add_message('user', '我爱喝咖啡', 'session-b')
    assert memory.remember_user('偏好', '爱喝咖啡', source_message_id=msg2, evidence='爱喝咖啡') == fact
    memory.close()
    memory = MemoryStore(str(path))
    detail = memory.inspect(fact)
    assert len(memory.list_memories()) == 1
    assert {s['source_message_id'] for s in detail['sources']} == {msg1, msg2}
    assert {s['evidence'] for s in detail['sources']} == {'喜欢咖啡', '爱喝咖啡'}
    assert {s['session_id'] for s in detail['sources']} == {'session-a', 'session-b'}
    assert {s['message_content'] for s in detail['sources']} == {'我喜欢咖啡', '我爱喝咖啡'}
    memory.close()


def test_generic_fact_evidence_and_duplicate_detection(store):
    message = store.add_message('user', '我养猫', 'session')
    first = store.remember('用户养猫', source_message_id=message, evidence='我养猫')
    assert store.remember('用户养猫', evidence='manual confirmation') == first
    assert len(store.inspect(first)['sources']) == 2


def test_single_value_changes_do_not_reactivate_historical_rows(store):
    first = store.remember_user('名字', '小明')
    middle = store.remember_user('名字', '小红')
    last = store.remember_user('名字', '小明')
    assert len({first, middle, last}) == 3
    assert [r['id'] for r in store.recall()] == [last]
    assert store.inspect(last)['predecessor_id'] == middle
    store.touch(first)
    assert store.get_user_profile()['名字'] == '小明'


def test_correct_creates_manual_version_and_clears_context(store):
    old = store.remember_user('名字', '旧名字')
    store.add_short_term('user', '我叫旧名字')
    new = store.correct(old, '新名字')
    assert store.get_short_term() == []
    assert store.get_user_profile()['名字'] == '新名字'
    detail = store.inspect(new)
    assert detail['predecessor_id'] == old
    assert detail['sources'][0]['evidence'] == 'manual correction'
    assert store.inspect(old)['status'] == 'superseded'
    with pytest.raises(ValueError):
        store.correct(new, '  ')
    assert store.get_user_profile()['名字'] == '新名字'


def test_forget_any_version_removes_chain_and_redacts_shared_message(store):
    message = store.add_message('user', '我叫机密旧名，也喜欢篮球', 'session')
    old = store.remember_user('名字', '机密旧名', source_message_id=message, evidence='我叫机密旧名')
    hobby = store.remember_user('爱好', '篮球', source_message_id=message, evidence='我叫机密旧名，也喜欢篮球')
    current = store.correct(old, '机密新名')
    store.add_short_term('user', '机密新名')
    store.forget(old)
    assert store.inspect(old) is None and store.inspect(current) is None
    assert store.get_short_term() == []
    assert store.get_user_profile() == {'爱好': '篮球'}
    assert '机密' not in str(store.inspect(hobby))
    assert len(store.inspect(hobby)['sources']) == 1
    assert store.recall('机密', include_history=True) == []


def test_failed_fact_batch_rolls_back_messages_sources_and_supersession(store):
    old = store.remember_user('名字', '原名')
    with pytest.raises(RuntimeError):
        with store.transaction():
            message = store.add_message('user', '我叫新名', 'session')
            store.remember_user('名字', '新名', source_message_id=message)
            raise RuntimeError('interrupted round')
    assert store.get_user_profile()['名字'] == '原名'
    assert len(store.list_memories(include_history=True)) == 1
    assert store.inspect(old)['status'] == 'active'
    assert store._conn.execute('SELECT count(*) FROM memory_messages').fetchone()[0] == 0
    assert store._conn.execute('SELECT count(*) FROM memory_sources').fetchone()[0] == 0


def test_nested_rollback_does_not_commit_or_discard_outer_work(store):
    with store.transaction():
        outer = store.remember_user('名字', '外层')
        with pytest.raises(ValueError):
            with store.transaction():
                store.correct(outer, '内层')
                raise ValueError('undo nested correction')
        assert store.get_user_profile()['名字'] == '外层'
        store.remember_user('爱好', '游泳')
    assert len(store.list_memories(include_history=True)) == 2


def test_bad_source_cannot_leave_half_written_fact(store):
    old = store.remember_user('名字', '原名')
    with pytest.raises(ValueError):
        store.remember_user('名字', '坏数据', source_message_id=9999)
    assert [r['id'] for r in store.recall()] == [old]
    assert store.get_user_profile()['名字'] == '原名'


def test_correct_and_forget_rollback_restores_context_and_sources(store):
    message = store.add_message('user', '原名', 'session')
    old = store.remember_user('名字', '原名', source_message_id=message)
    store.add_short_term('user', '原名')
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.forget(old)
            raise RuntimeError('undo deletion')
    assert store.inspect(old)['sources'][0]['message_content'] == '原名'
    assert store.get_short_term() == [{'role': 'user', 'content': '原名'}]


def test_correction_merging_objects_keeps_all_old_versions_deletable(store):
    coffee_old = store.remember_user('偏好', '喜欢咖啡')
    coffee_now = store.remember_user('偏好', '不喜欢咖啡')
    tea_old = store.remember_user('偏好', '喜欢奶茶')
    tea_now = store.remember_user('偏好', '不喜欢奶茶')
    merged = store.correct(coffee_old, '喜欢奶茶')
    assert store.get_user_profile()['偏好'] == '喜欢奶茶'
    store.forget(merged)
    assert all(store.inspect(fid) is None for fid in (coffee_old, coffee_now, tea_old, tea_now, merged))
    assert store.list_memories(include_history=True) == []


def test_empty_profile_correction_is_rejected_without_version(store):
    old = store.remember_user('名字', '小明')
    with pytest.raises(ValueError):
        store.correct(old, '名字:   ')
    assert store.get_user_profile()['名字'] == '小明'
    assert len(store.list_memories(include_history=True)) == 1


def test_correct_generic_fact_preserves_tags_and_never_reuses_old_vector(store):
    old = store.remember('旧事实', tags=['tag'], embedding=b'old-vector')
    new = store.correct(old, '新事实', evidence='user verified')
    assert store.inspect(new)['tags'] == ['tag']
    assert store.inspect(new)['content_vector'] is None
    assert store.inspect(old)['content_vector'] == b'old-vector'
    assert [r['id'] for r in store.vector_search(b'query')] == [new]
    store.forget(new)
    assert store._conn.execute('SELECT count(*) FROM memory_tags').fetchone()[0] == 0


def test_sql_failure_rolls_back_partial_supersession(store):
    old = store.remember_user('名字', '原名')
    store._conn.execute("CREATE TRIGGER reject_source BEFORE INSERT ON memory_sources "
                        "BEGIN SELECT RAISE(ABORT, 'source write failed'); END")
    with pytest.raises(sqlite3.IntegrityError, match='source write failed'):
        store.remember_user('名字', '新名', evidence='new name')
    assert store.inspect(old)['status'] == 'active'
    assert len(store.list_memories(include_history=True)) == 1


def test_outer_failure_rolls_back_successful_inner_transaction(store):
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.remember('outer fact')
            with store.transaction():
                store.remember('inner fact', evidence='nested source')
            raise RuntimeError('outer failure')
    assert store.list_memories(include_history=True) == []
    assert store._conn.execute('SELECT count(*) FROM memory_sources').fetchone()[0] == 0


def test_legacy_preference_key_aliases_share_current_object_history(tmp_path):
    path = tmp_path / 'aliases.db'
    legacy_database(path)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO memory_fragments (content,memory_type,created_at) "
                     "VALUES ('爱好: 喜欢咖啡','user_profile',9)")
    memory = MemoryStore(str(path))
    current = memory.remember_user('偏好', '不喜欢咖啡')
    assert [r['id'] for r in memory.recall('咖啡')] == [current]
    assert set(memory.get_user_profile()['爱好'].split('；')) == {'篮球', '游泳'}
    memory.forget(current)
    memory.close()
    memory = MemoryStore(str(path))
    assert memory.recall('咖啡', include_history=True) == []
    assert set(memory.get_user_profile()['爱好'].split('；')) == {'篮球', '游泳'}
    memory.close()
