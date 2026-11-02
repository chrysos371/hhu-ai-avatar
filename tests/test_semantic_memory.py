import numpy as np
import pytest

from avatar.brain.memory import MemoryStore


class SemanticStub:
    model_id = 'test-v1'

    def embed(self, text):
        if '猫' in text or '宠物' in text:
            return [1., 0., 0.]
        if '咖啡' in text:
            return [0., 1., 0.]
        return [0., 0., 1.]


def test_paraphrase_retrieval_and_no_obsolete_or_deleted_results():
    store = MemoryStore(':memory:', embedder=SemanticStub())
    cat = store.remember('我养了一只猫')
    coffee = store.remember_user('偏好', '喜欢咖啡')
    assert store.recall('我的宠物')[0]['id'] == cat
    assert store.inspect(cat)['embedding_model'] == 'test-v1'
    replacement = store.remember_user('偏好', '不喜欢咖啡')
    assert [r['id'] for r in store.recall('咖啡')] == [replacement]
    store.forget(cat)
    assert store.recall('我的宠物') == []
    assert store.inspect(coffee)['status'] == 'superseded'
    store.close()


def test_type_filter_applies_to_semantic_candidates():
    store = MemoryStore(':memory:', embedder=SemanticStub())
    store.remember('猫', memory_type='episode')
    wanted = store.remember('养猫', memory_type='fact')
    assert [r['id'] for r in store.recall('宠物', memory_type='fact')] == [wanted]
    store.close()


def test_embedding_failure_keeps_lexical_recall_and_unmodified_index():
    class Broken:
        model_id = 'broken'
        def embed(self, text):
            raise OSError('offline')
    store = MemoryStore(':memory:', embedder=Broken())
    fid = store.remember('猫喜欢吃鱼')
    assert store.recall('猫')[0]['id'] == fid
    assert store.inspect(fid)['content_vector'] is None
    store.close()


def test_changed_model_and_dimensions_reindex_without_mixing_spaces():
    class TwoDims:
        model_id = 'test-v2'
        def embed(self, text):
            return [1., 0.]
    store = MemoryStore(':memory:', embedder=SemanticStub())
    fid = store.remember('猫')
    assert store.reindex() == 1
    assert store.inspect(fid)['embedding_dim'] == 3
    store._embedder = TwoDims()
    assert store.recall('宠物')[0]['id'] == fid
    row = store.inspect(fid)
    assert row['embedding_model'] == 'test-v2'
    assert row['embedding_dim'] == 2
    store.close()


def test_inconsistent_provider_dimensions_roll_back_batch():
    class Inconsistent:
        model_id = 'bad-dim'
        def embed(self, text):
            return [1., 0.] if text == '查询' else [1., 0., 0.]
    store = MemoryStore(':memory:', embedder=Inconsistent())
    fid = store.remember('猫')
    assert store.recall('查询') == []
    assert store.inspect(fid)['content_vector'] is None
    store.close()


def test_embedding_index_participates_in_outer_transaction_rollback():
    store = MemoryStore(':memory:', embedder=SemanticStub())
    fid = store.remember('猫')
    with pytest.raises(RuntimeError):
        with store.transaction():
            store.reindex()
            raise RuntimeError('cancel')
    assert store.inspect(fid)['content_vector'] is None
    store.close()


def test_invalid_cached_vector_is_rebuilt_instead_of_served():
    store = MemoryStore(':memory:', embedder=SemanticStub())
    fid = store.remember('猫')
    store.reindex()
    store._conn.execute('UPDATE memory_fragments SET content_vector=? WHERE id=?',
                        (np.zeros(3, dtype=np.float32).tobytes(), fid))
    assert store.recall('宠物')[0]['id'] == fid
    store.close()


def test_weak_semantic_neighbors_do_not_fill_context_with_unrelated_facts():
    class Graded:
        model_id = 'graded'
        def embed(self, text):
            if text == '宠物':
                return [1., 0.]
            return [.8, .6] if text == '猫' else [.5, 0.8660254]
    store = MemoryStore(':memory:', embedder=Graded())
    cat = store.remember('猫')
    store.remember('篮球')
    assert [r['id'] for r in store.recall('宠物')] == [cat]
    store.close()
