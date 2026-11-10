import json
import sqlite3
import pytest
from avatar.brain.memory import MemoryStore
from avatar.brain.admin_store import AdminStore
from avatar.brain.operations import OperationService, OperationError


class Counter:
    def __init__(self, store):
        self.s = store

    def snapshot(self, p):
        row = self.s.conn.execute(
            "SELECT value FROM admin_state WHERE key='counter'"
        ).fetchone()
        return {"value": int(row[0]) if row else 0}

    def prepare(self, p):
        if set(p) != {"value"} or type(p["value"]) is not int:
            raise ValueError("invalid value")
        b = self.snapshot(p)
        return b, [{"field": "value", "before": b["value"], "after": p["value"]}], []

    def execute(self, p):
        self.s.conn.execute(
            "INSERT OR REPLACE INTO admin_state(key,value) VALUES('counter',?)",
            (str(p["value"]),),
        )
        return self.snapshot(p)


@pytest.fixture
def service(tmp_path):
    memory = MemoryStore(str(tmp_path / "ops.db"))
    store = AdminStore(memory)
    store.migrate({"name": "小海"})
    now = [1000.0]
    s = OperationService(
        store, executors={"persona.update": Counter(store)}, clock=lambda: now[0]
    )
    yield s, store, now
    memory.close()


def test_draft_requires_token_then_confirm_once(service):
    s, store, _ = service
    d = s.create_draft("persona.update", {"value": 3})
    assert Counter(store).snapshot({})["value"] == 0
    db = store.conn.execute("SELECT token_hash FROM operation_drafts").fetchone()[0]
    assert d.confirmation_token not in db
    with pytest.raises(OperationError):
        s.confirm(d.draft_id, "wrong")
    result = s.confirm(d.draft_id, d.confirmation_token)
    assert result["result"]["value"] == 3 and len(store.list_audit()) == 1
    assert d.confirmation_token not in json.dumps(store.list_audit())
    with pytest.raises(OperationError):
        s.confirm(d.draft_id, d.confirmation_token)


def test_cross_draft_stale_and_expired(service):
    s, store, now = service
    a = s.create_draft("persona.update", {"value": 2})
    b = s.create_draft("persona.update", {"value": 4})
    with pytest.raises(OperationError):
        s.confirm(a.draft_id, b.confirmation_token)
    s.confirm(a.draft_id, a.confirmation_token)
    with pytest.raises(OperationError, match="stale_draft"):
        s.confirm(b.draft_id, b.confirmation_token)
    c = s.create_draft("persona.update", {"value": 5})
    now[0] += 601
    with pytest.raises(OperationError, match="expired_draft"):
        s.confirm(c.draft_id, c.confirmation_token)
    assert Counter(store).snapshot({})["value"] == 2


def test_audit_failure_rolls_back_domain(service):
    s, store, _ = service
    d = s.create_draft("persona.update", {"value": 8})
    store.conn.execute(
        "CREATE TRIGGER fail_audit BEFORE INSERT ON audit_events BEGIN SELECT RAISE(ABORT,'test'); END"
    )
    with pytest.raises(OperationError):
        s.confirm(d.draft_id, d.confirmation_token)
    assert Counter(store).snapshot({})["value"] == 0
    assert store.list_audit() == []
    store.conn.execute("DROP TRIGGER fail_audit")
    with pytest.raises(OperationError, match="draft_not_pending"):
        s.confirm(d.draft_id, d.confirmation_token)


def test_unknown_operation_and_invalid_payload(service):
    s, _, _ = service
    with pytest.raises(OperationError):
        s.create_draft("sql.execute", {"query": "DROP TABLE"})
    with pytest.raises(OperationError):
        s.create_draft("persona.update", {"value": True})


def test_concurrent_confirmation_has_one_winner(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = str(tmp_path / "concurrent.db")
    m = MemoryStore(path)
    store = AdminStore(m)
    store.migrate({"name": "初始"})
    service = OperationService(store, executors={"persona.update": Counter(store)})
    d = service.create_draft("persona.update", {"value": 9})
    m.close()

    def confirm():
        memory = MemoryStore(path)
        s = AdminStore(memory)
        try:
            OperationService(s, executors={"persona.update": Counter(s)}).confirm(
                d.draft_id, d.confirmation_token
            )
            return "success"
        except OperationError as e:
            return e.code
        finally:
            memory.close()

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: confirm(), range(2)))
    assert results.count("success") == 1
    m = MemoryStore(path)
    s = AdminStore(m)
    assert len(s.list_audit()) == 1 and Counter(s).snapshot({})["value"] == 9
    m.close()
