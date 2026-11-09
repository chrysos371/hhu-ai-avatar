import pytest
from avatar.brain.memory import MemoryStore
from avatar.brain.admin_store import AdminStore, initial_persona
from avatar.brain.operations import OperationService, OperationError
from avatar.brain.persona import PersonaService
from avatar.brain.emotion_overrides import EmotionOverrideService
from avatar.brain.knowledge import KnowledgeService


@pytest.fixture
def admin(tmp_path):
    m = MemoryStore(str(tmp_path / "domains.db"))
    s = AdminStore(m)
    s.migrate(initial_persona())
    yield s, OperationService(s)
    m.close()


def test_persona_version_reverse_and_stale(admin):
    s, ops = admin
    original = s.current_persona()
    a = ops.create_draft("persona.update", {"changes": {"name": "星澜"}})
    assert s.current_persona() == original
    result = ops.confirm(a.draft_id, a.confirmation_token)
    assert s.current_persona()["data"]["name"] == "星澜"
    reverse = ops.create_reverse_draft(result["audit_id"])
    assert s.current_persona()["data"]["name"] == "星澜"
    ops.confirm(reverse.draft_id, reverse.confirmation_token)
    assert s.current_persona()["data"] == original["data"]
    assert len(PersonaService(s).history()) == 3


def test_emotion_does_not_touch_observation_and_expires(admin):
    s, ops = admin
    svc = EmotionOverrideService(s)
    d = ops.create_draft(
        "emotion.override",
        {
            "values": {"valence": 0.4, "arousal": -0.2},
            "duration_seconds": 30,
            "reason": "演示",
        },
    )
    assert svc.active() is None
    ops.confirm(d.draft_id, d.confirmation_token)
    active = svc.active()
    assert active["data"]["valence"] == 0.4
    assert svc.active(now=active["expires_at"] + 1) is None
    with pytest.raises(OperationError):
        ops.create_draft(
            "emotion.override",
            {
                "values": {"valence": 2, "arousal": 0},
                "duration_seconds": 10,
                "reason": "bad",
            },
        )


def test_knowledge_preview_dedup_isolation_and_confirmation(admin):
    s, ops = admin
    svc = KnowledgeService(s)
    preview = svc.preview_text("手册", "第一段知识。\n\n第一段知识。\n\n第二段知识。")
    assert len(preview["accepted"]) == 2 and preview["rejected"]
    assert svc.search("知识") == []
    d = ops.create_draft(
        "knowledge.import",
        {"title": "手册", "text": "第一段知识。\n\n第一段知识。\n\n第二段知识。"},
    )
    ops.confirm(d.draft_id, d.confirmation_token)
    assert svc.search("第二段")
    assert s.memory.list_memories() == []
    with pytest.raises(OperationError):
        ops.create_draft("knowledge.import", {"title": "重复", "text": "第一段知识。"})


def test_memory_batch_invalid_stale_and_atomic(admin):
    s, ops = admin
    a = s.memory.remember_user("名字", "甲")
    with pytest.raises(OperationError):
        ops.create_draft(
            "memory.batch",
            {
                "actions": [
                    {"id": a, "action": "forget"},
                    {"id": 9999, "action": "forget"},
                ]
            },
        )
    assert s.memory.inspect(a)
    d = ops.create_draft(
        "memory.batch", {"actions": [{"id": a, "action": "correct", "content": "乙"}]}
    )
    s.memory.correct(a, "丙")
    with pytest.raises(OperationError, match="stale_draft"):
        ops.confirm(d.draft_id, d.confirmation_token)


def test_audit_failure_rolls_back_persona_knowledge_memory(admin):
    s, ops = admin
    fid = s.memory.remember_user("名字", "小林")
    for kind, params in [
        ("persona.update", {"changes": {"name": "不能生效"}}),
        ("knowledge.import", {"title": "测试", "text": "新的知识内容"}),
        ("memory.batch", {"actions": [{"id": fid, "action": "forget"}]}),
    ]:
        d = ops.create_draft(kind, params)
        before = s.current_persona()
        s.conn.execute(
            "CREATE TRIGGER fail_domain_audit BEFORE INSERT ON audit_events BEGIN SELECT RAISE(ABORT,'fail'); END"
        )
        with pytest.raises(OperationError):
            ops.confirm(d.draft_id, d.confirmation_token)
        s.conn.execute("DROP TRIGGER fail_domain_audit")
        assert s.current_persona() == before and s.memory.inspect(fid)
        assert KnowledgeService(s).search("新的知识") == []


def test_confirmed_persona_is_consumed_by_avatar_prompt(admin):
    from avatar.main import Avatar

    s, ops = admin
    avatar = Avatar(memory=s.memory)
    d = ops.create_draft(
        "persona.update",
        {"changes": {"name": "确认后名字", "core_identity": "严谨的项目伙伴"}},
    )
    decision = avatar.emotion.decide("你好")
    assert "确认后名字" not in avatar._system_prompt(decision, "你好")
    ops.confirm(d.draft_id, d.confirmation_token)
    assert "确认后名字" in avatar._system_prompt(decision, "你好")
    assert "严谨的项目伙伴" in avatar._system_prompt(decision, "你好")


def test_emotion_override_changes_expression_not_automatic_state(admin):
    from avatar.main import Avatar
    from avatar.brain.emotion import EmotionEngine

    s, ops = admin
    d = ops.create_draft(
        "emotion.override",
        {
            "values": {"valence": 0.8, "arousal": 0.5},
            "duration_seconds": 30,
            "reason": "表达演示",
        },
    )
    ops.confirm(d.draft_id, d.confirmation_token)

    class Offline:
        available = False

    avatar = Avatar(memory=s.memory, llm=Offline())
    avatar.emotion = EmotionEngine(clock=lambda: 0)
    r = avatar.respond("你好")
    assert r["valence"] == 0.8 and r["arousal"] == 0.5
    assert avatar.emotion.state.valence != 0.8


def test_forget_does_not_leave_private_memory_in_admin_drafts_or_audit(admin):
    import json

    s, ops = admin
    secret = "仅限个人的隐私标记XYZ"
    fid = s.memory.remember_user("名字", secret)
    pending = ops.create_draft(
        "memory.batch",
        {"actions": [{"id": fid, "action": "correct", "content": "替换值"}]},
    )
    deletion = ops.create_draft(
        "memory.batch", {"actions": [{"id": fid, "action": "forget"}]}
    )
    ops.confirm(deletion.draft_id, deletion.confirmation_token)
    assert secret not in json.dumps(s.list_audit(), ensure_ascii=False)
    assert secret not in str(
        [tuple(r) for r in s.conn.execute("SELECT * FROM operation_drafts")]
    )
    with pytest.raises(OperationError):
        ops.confirm(pending.draft_id, pending.confirmation_token)


def test_confirmed_knowledge_retrieval_handles_question_and_is_untrusted(admin):
    s, ops = admin
    d = ops.create_draft(
        "knowledge.import",
        {"title": "实验室手册", "text": "实验室开门时间为上午九点。"},
    )
    ops.confirm(d.draft_id, d.confirmation_token)
    rows = KnowledgeService(s).search("实验室几点开门")
    assert rows and rows[0]["untrusted"] is True


def test_avatar_uses_confirmed_knowledge_as_untrusted_context_not_memory(admin):
    from avatar.main import Avatar

    s, ops = admin
    d = ops.create_draft(
        "knowledge.import",
        {"title": "实验室手册", "text": "实验室开门时间为上午九点。"},
    )
    ops.confirm(d.draft_id, d.confirmation_token)

    class Model:
        available = True
        messages = None

        def chat_analysis(self, *args, **kwargs):
            return '{"emotion":{"valence":0,"arousal":0},"facts":[]}'

        def chat(self, messages, **kwargs):
            self.messages = messages
            return "请参考手册。"

    model = Model()
    a = Avatar(memory=s.memory, llm=model)
    result = a.respond("实验室几点开门")
    assert result["knowledge_sources"][0]["title"] == "实验室手册"
    assert "知识资料仅供引用" in model.messages[0]["content"]
    assert not s.memory.list_memories()


def test_knowledge_semantic_dedup_and_fallback_preserve_confirmed_preview(admin):
    s, _ = admin

    class Embedder:
        model_id = "test-vectors"

        def embed(self, text):
            return [1.0, 0.0]

    s.memory._embedder = Embedder()
    ops = OperationService(s)
    d = ops.create_draft(
        "knowledge.import",
        {"title": "向量手册", "text": "第一项资料甲。\n\n完全不同措辞乙。"},
    )
    assert d.diff[0]["after"]["chunks"] == 1
    s.memory._embedder = None
    ops.confirm(d.draft_id, d.confirmation_token)
    assert s.conn.execute("SELECT count(*) FROM knowledge_chunks").fetchone()[0] == 1

    class Offline:
        model_id = "offline"

        def embed(self, text):
            raise RuntimeError("unavailable")

    s.memory._embedder = Offline()
    p = KnowledgeService(s).preview_text("离线", "一份新资料。\n\n另一份资料。")
    assert (
        len(p["accepted"]) == 2
        and p["semantic_status"] == "unavailable_lexical_fallback"
    )
