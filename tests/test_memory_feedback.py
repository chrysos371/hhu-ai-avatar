import pytest

from avatar.brain.memory import MemoryStore


def test_bad_hit_persists_and_reranks_without_deleting(tmp_path):
    path = str(tmp_path / 'memory.db')
    store = MemoryStore(path)
    first = store.remember('游泳地点是校内泳池', importance=.9)
    second = store.remember('游泳时间是周末', importance=.5)
    assert store.recall('游泳')[0]['id'] == first
    for _ in range(3):
        store.report_irrelevant(first)
    store.close()
    store = MemoryStore(path)
    assert store.recall('游泳')[0]['id'] == second
    assert store.inspect(first)['bad_hits'] == 3
    assert store.inspect(first)['status'] == 'active'
    assert store.recall('天文望远镜') == []
    new = store.correct(first, '游泳地点是市体育馆')
    assert store.inspect(new)['bad_hits'] == 0
    store.forget(new)
    assert store.inspect(first) is None
    store.close()


def test_decay_ranks_notes_but_preserves_identity(tmp_path):
    store = MemoryStore(str(tmp_path / 'memory.db'))
    old = store.remember('游泳旧安排', importance=.9)
    fresh = store.remember('游泳新安排', importance=.5)
    identity = store.remember_user('名字', '小林')
    store._conn.execute('UPDATE memory_fragments SET created_at=1 WHERE id IN (?,?)', (old, identity))
    store._conn.commit()
    assert store.recall('游泳')[0]['id'] == fresh
    assert store.memory_strength(store.inspect(identity)) == 1
    assert len(store.list_memories()) == 3
    with pytest.raises(ValueError):
        store.report_irrelevant(9999)
    store.close()
