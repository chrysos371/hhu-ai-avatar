import io
import json
from test_web_api_v1 import api_v1


def test_optional_model_failure_is_redacted_and_other_services_remain_available(
    api_v1, monkeypatch
):
    from avatar.config import config

    secret = "unit-test-secret-not-for-client"
    monkeypatch.setattr(config.llm, "api_key", secret)

    def fail(*args, **kwargs):
        raise RuntimeError(secret)

    monkeypatch.setattr("avatar.web_api.urllib.request.urlopen", fail)
    # Patch only the backend probe; the fixture uses the same urllib module.
    from avatar.web_api import V1API
    from avatar.brain.memory import MemoryStore

    memory = MemoryStore(api_v1[1].db_path)
    try:
        api = V1API(api_v1[1], memory, None)
        rows = api.health()
    finally:
        memory.close()
    assert secret not in json.dumps(rows)
    assert next(r for r in rows if r["name"] == "本地管理模型")["available"] is False
    assert next(r for r in rows if r["name"] == "SQLite")["available"] is True


def test_health_recognizes_installed_local_model_and_never_probes_cloud(
    api_v1, monkeypatch
):
    from avatar.web_api import V1API
    from avatar.brain.memory import MemoryStore

    calls = []

    def probe(url, timeout):
        calls.append((url, timeout))
        return io.BytesIO(b'{"models":[{"name":"qwen3:4b"}]}')

    monkeypatch.setenv("AVATAR_ADMIN_LOCAL_MODEL", "qwen3:4b")
    monkeypatch.setattr("avatar.web_api.urllib.request.urlopen", probe)
    memory = MemoryStore(api_v1[1].db_path)
    try:
        rows = V1API(api_v1[1], memory, None).health()
    finally:
        memory.close()
    assert next(r for r in rows if r["name"] == "本地管理模型")["available"] is True
    assert calls == [("http://127.0.0.1:11434/api/tags", 0.7)]
