from avatar.brain.memory import MemoryStore
import pytest


def test_external_forget_invalidates_another_connections_short_term(tmp_path):
    path = str(tmp_path / 'memory.db')
    a, b = MemoryStore(path), MemoryStore(path)
    fid = a.remember_user('名字', '小林')
    b.add_short_term('user', '我叫小林')
    a.forget(fid)
    b.add_short_term('user', '你记得我吗')
    assert b.get_short_term() == [{'role': 'user', 'content': '你记得我吗'}]
    a.close()
    b.close()


def test_rolled_back_correction_keeps_other_context(tmp_path):
    path = str(tmp_path / 'memory.db')
    a, b = MemoryStore(path), MemoryStore(path)
    fid = a.remember_user('名字', '小林')
    b.add_short_term('user', '我叫小林')
    try:
        with a.transaction():
            a.correct(fid, '阿岚')
            raise RuntimeError('rollback')
    except RuntimeError:
        pass
    assert b.get_short_term() == [{'role': 'user', 'content': '我叫小林'}]
    a.close()
    b.close()


def test_failed_transaction_cannot_restore_externally_deleted_context(tmp_path):
    path = str(tmp_path / 'memory.db')
    a, b = MemoryStore(path), MemoryStore(path)
    fid = a.remember_user('名字', '秘密名字')
    a.add_short_term('user', '我叫秘密名字')
    b.forget(fid)
    with pytest.raises(ValueError):
        a.correct(999, '替代名字')
    assert a.get_short_term() == []
    a.close()
    b.close()
