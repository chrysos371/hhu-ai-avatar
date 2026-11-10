import json
import pytest
from avatar.brain.memory import MemoryStore
from avatar.brain.admin_store import AdminStore, canonical_json


def test_migration_reopen_and_seed_once(tmp_path):
    path = str(tmp_path / "admin.db")
    m = MemoryStore(path)
    fid = m.remember_user("名字", "小林")
    store = AdminStore(m)
    store.migrate({"name": "初始", "core_identity": "伙伴"})
    first = store.current_persona()
    assert first["data"]["name"] == "初始"
    store.migrate({"name": "替换", "core_identity": "不同"})
    assert store.current_persona() == first and m.inspect(fid)
    assert store.system_counts()["memories"] == 1
    m.close()
    m = MemoryStore(path)
    s = AdminStore(m)
    s.migrate({"name": "另一个"})
    assert s.current_persona() == first
    assert s.list_audit() == []
    m.close()


def test_canonical_json_rejects_nonfinite_and_unsupported():
    assert canonical_json({"b": 2, "a": "中"}) == '{"a":"中","b":2}'
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})
    with pytest.raises(TypeError):
        canonical_json({"x": object()})
