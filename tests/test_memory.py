"""记忆模块测试。"""
import os
import tempfile

from avatar.brain.memory import MemoryStore


def _tmp_store(**kw) -> MemoryStore:
    return MemoryStore(db_path=os.path.join(tempfile.mkdtemp(), "test.db"), **kw)


def test_remember_and_recall():
    store = _tmp_store()
    fid = store.remember("用户喜欢猫", memory_type="user_profile", importance=0.9)
    assert any(r["id"] == fid for r in store.recall(query="猫"))
    store.close()


def test_user_profile_roundtrip():
    store = _tmp_store()
    store.remember_user("名字", "小明")
    store.remember_user("爱好", "打篮球")
    profile = store.get_user_profile()
    assert profile["名字"] == "小明"
    assert profile["爱好"] == "打篮球"
    store.close()


def test_short_term_window_limited():
    store = _tmp_store(short_term_limit=3)
    for role, content in [("user", "a"), ("assistant", "b"), ("user", "c"), ("assistant", "d")]:
        store.add_short_term(role, content)
    assert len(store.get_short_term()) == 3  # 只保留最近 3 轮
    store.close()


def test_forget():
    store = _tmp_store()
    fid = store.remember("要忘记的内容")
    store.forget(fid)
    assert all(r["id"] != fid for r in store.recall(query="忘记"))
    store.close()
