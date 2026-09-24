"""记忆模块测试。"""
import os
import tempfile

from avatar.brain.memory import MemoryStore, _tokenize


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


def test_tokenize_stopwords():
    assert _tokenize("我喜欢打篮球") == ["打篮球"]
    assert _tokenize("我叫王小明") == ["王小明"]
    assert _tokenize("你还记得我叫什么吗") == []  # 纯功能词，无实词


def test_recall_by_keyword_related():
    store = _tmp_store()
    store.remember("我喜欢打篮球", importance=0.5)
    store.remember("我养了一只猫", importance=0.5)
    store.remember("我下周要考试", importance=0.5)
    results = store.recall(query="篮球", limit=3)
    assert any("篮球" in r["content"] for r in results)
    store.close()


def test_recall_sentence_extracts_keywords():
    store = _tmp_store()
    store.remember("我喜欢打篮球", importance=0.5)
    store.remember("我养了一只猫", importance=0.9)
    results = store.recall(query="我平时喜欢打篮球吗", limit=3)
    assert "篮球" in results[0]["content"]  # 相关命中排最前，即使「猫」重要度更高
    store.close()


def test_recall_scores_by_hit_count():
    store = _tmp_store()
    fid_multi = store.remember("我喜欢打篮球和踢足球", importance=0.3)
    store.remember("我喜欢猫", importance=0.9)
    results = store.recall(query="篮球 足球", limit=2)
    assert results[0]["id"] == fid_multi  # 命中两个关键词的排最前
    store.close()


def test_recall_no_query_returns_by_importance():
    store = _tmp_store()
    store.remember("不重要的事", importance=0.1)
    fid_imp = store.remember("很重要的事", importance=0.9)
    results = store.recall(limit=5)
    assert results[0]["id"] == fid_imp
    store.close()
