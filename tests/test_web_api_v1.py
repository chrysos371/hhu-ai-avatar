import json
import threading
import urllib.error
import urllib.request
from urllib.parse import quote
import pytest
from avatar.web import create_server


@pytest.fixture
def api_v1(tmp_path, monkeypatch):
    from avatar.config import config

    monkeypatch.setattr(config.llm, "api_key", "")
    monkeypatch.setattr(config.embedding, "model", "")
    server = create_server(str(tmp_path / "v1.db"), port=0)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    def request(path, data=None, token=True):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["X-Avatar-Token"] = server.token
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}" + path,
            data=None if data is None else json.dumps(data).encode(),
            headers=headers,
        )
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as r:
            return r.code, json.loads(r.read())

    yield request, server
    server.shutdown()
    t.join()
    server.server_close()


def test_system_audit_envelope_and_legacy_compat(api_v1):
    r, _ = api_v1
    code, body = r("/api/v1/system")
    assert code == 200 and set(body) == {"data", "error", "request_id"}
    assert body["data"]["mode"] == "single-user-local" and body["request_id"]
    assert "api_key" not in json.dumps(body)
    assert r("/api/v1/audit?limit=0")[0] == 422
    assert r("/api/v1/system", token=False)[0] == 403
    assert r("/api/state")[0] == 200


def test_persona_draft_confirm_and_reverse_api(api_v1):
    r, _ = api_v1
    old = r("/api/v1/persona")[1]["data"]
    code, body = r("/api/v1/persona/draft", {"changes": {"name": "星澜"}})
    assert code == 201
    d = body["data"]
    assert r("/api/v1/persona")[1]["data"] == old
    assert (
        r(f"/api/v1/operations/{d['draft_id']}/confirm", {"confirmation_token": "bad"})[
            0
        ]
        == 403
    )
    code, applied = r(
        f"/api/v1/operations/{d['draft_id']}/confirm",
        {"confirmation_token": d["confirmation_token"]},
    )
    assert code == 200
    assert r("/api/v1/persona")[1]["data"]["data"]["name"] == "星澜"
    assert (
        r(
            f"/api/v1/operations/{d['draft_id']}/confirm",
            {"confirmation_token": d["confirmation_token"]},
        )[0]
        == 409
    )
    aid = applied["data"]["audit_id"]
    assert r(f"/api/v1/audit/{aid}/reverse-draft", {})[0] == 201


def test_chat_trace_does_not_expose_prompts(api_v1):
    r, _ = api_v1
    code, body = r("/api/v1/chat", {"text": "我喜欢游泳"})
    assert code == 200
    result = body["data"]
    assert result["reply"] and result["trace"]["recalled_memories"]
    assert "system_prompt" not in json.dumps(result)
    assert result["trace"]["verifier"]["available"] is False


def test_knowledge_import_requires_confirmation(api_v1):
    r, _ = api_v1
    code, body = r(
        "/api/v1/knowledge/preview-text",
        {"title": "手册", "text": "实验室开门时间为上午九点。"},
    )
    assert code == 201
    assert r("/api/v1/knowledge/sources")[1]["data"] == []
    d = body["data"]["draft"]
    assert (
        r(
            f"/api/v1/operations/{d['draft_id']}/confirm",
            {"confirmation_token": d["confirmation_token"]},
        )[0]
        == 200
    )
    assert r("/api/v1/knowledge/search?q=" + quote("实验室"))[1]["data"]


def test_persona_preview_never_activates_or_writes_history(api_v1, monkeypatch):
    from avatar.brain.admin_agent import ManagementTransport

    r, _ = api_v1
    before = r("/api/v1/persona")[1]["data"]
    monkeypatch.setattr(
        ManagementTransport, "chat", lambda self, messages: '{"reply":"我会仔细听。"}'
    )
    code, body = r(
        "/api/v1/persona/preview-chat",
        {"changes": {"name": "仅预览"}, "text": "今天好累"},
    )
    assert code == 200 and body["data"]["reply"] == "我会仔细听。"
    assert r("/api/v1/persona")[1]["data"] == before
    assert len(r("/api/v1/persona/history")[1]["data"]) == 1
    assert r("/api/v1/audit")[1]["data"] == []


def test_production_legacy_writes_disabled_but_reads_preserved(api_v1):
    r, server = api_v1
    server.legacy_writes = False
    assert r("/api/state")[0] == 200
    assert r("/api/reminders", {"text": "提醒我明天下午3点答辩"})[0] == 410
    assert r("/api/v1/reminders")[1]["data"] == []
    code, body = r("/api/v1/reminders", {"text": "提醒我明天下午3点答辩"})
    assert code == 201
    assert r("/api/v1/reminders")[1]["data"] == []
    draft = body["data"]
    assert (
        r(
            f"/api/v1/operations/{draft['draft_id']}/confirm",
            {"confirmation_token": draft["confirmation_token"]},
        )[0]
        == 200
    )
    rows = r("/api/v1/reminders")[1]["data"]
    assert len(rows) == 1
    d = r(f"/api/v1/reminders/{rows[0]['id']}/status-draft", {"status": "completed"})[
        1
    ]["data"]
    assert r("/api/v1/reminders")[1]["data"][0]["status"] == "active"
    assert (
        r(
            f"/api/v1/operations/{d['draft_id']}/confirm",
            {"confirmation_token": d["confirmation_token"]},
        )[0]
        == 200
    )
    assert r("/api/v1/reminders")[1]["data"][0]["status"] == "completed"


def test_memory_correction_and_filter_api(api_v1):
    from avatar.brain.memory import MemoryStore

    r, server = api_v1
    memory = MemoryStore(server.db_path)
    try:
        fid = memory.remember_user("名字", "小林")
    finally:
        memory.close()
    d = r(
        "/api/v1/memory/batch-draft",
        {"actions": [{"id": fid, "action": "correct", "content": "小张"}]},
    )[1]["data"]
    assert r(f"/api/v1/memory/{fid}")[1]["data"]["status"] == "active"
    assert (
        r(
            f"/api/v1/operations/{d['draft_id']}/confirm",
            {"confirmation_token": d["confirmation_token"]},
        )[0]
        == 200
    )
    rows = r("/api/v1/memory?confirmation=manual_correction")[1]["data"]
    assert len(rows) == 1 and "小张" in rows[0]["content"]
    assert len(r("/api/v1/memory?history=1")[1]["data"]) == 2
    assert r("/api/v1/memory?since=NaN")[0] == 422


def test_improvement_report_is_authenticated_readonly_and_has_no_raw_chat(api_v1, monkeypatch):
    import avatar.lab.improvement as patrol
    monkeypatch.setattr(patrol,'summary',lambda: {'available':True,'runs':[], 'issues':[], 'automatic_release':False})
    request,_=api_v1
    assert request('/api/v1/improvement',token=False)[0]==403
    code,body=request('/api/v1/improvement')
    assert code==200 and body['data']['automatic_release'] is False
    assert 'reply' not in json.dumps(body)
    assert request('/api/v1/improvement',{})[0]==404


def test_skill_catalog_requires_auth_and_cannot_execute_or_edit_packs(api_v1):
    request,_=api_v1
    assert request('/api/v1/skills',token=False)[0]==403
    code,body=request('/api/v1/skills')
    assert code==200 and body['data']['automatic_execution'] is False
    assert {s['id'] for s in body['data']['skills']}=={'study-coach','writing-editor','banter-coach'}
    assert all(s['capabilities']==['context.read'] for s in body['data']['skills'])
    assert request('/api/v1/skills',{'command':'run'})[0]==404
