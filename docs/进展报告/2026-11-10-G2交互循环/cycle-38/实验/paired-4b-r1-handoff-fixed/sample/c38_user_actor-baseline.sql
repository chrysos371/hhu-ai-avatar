BEGIN TRANSACTION;
CREATE TABLE admin_state (key TEXT PRIMARY KEY,value TEXT NOT NULL);
INSERT INTO "admin_state" VALUES('persona','1');
CREATE TABLE audit_events (id INTEGER PRIMARY KEY AUTOINCREMENT,draft_id INTEGER,operation_type TEXT NOT NULL,actor TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('success','failed')),before_json TEXT NOT NULL,after_json TEXT NOT NULL,created_at REAL NOT NULL,error TEXT);
CREATE TABLE emotion_overrides (id INTEGER PRIMARY KEY AUTOINCREMENT,data_json TEXT NOT NULL,starts_at REAL NOT NULL,expires_at REAL NOT NULL,status TEXT NOT NULL CHECK(status IN ('active','replaced','cleared')));
CREATE TABLE knowledge_chunks (id INTEGER PRIMARY KEY AUTOINCREMENT,source_id INTEGER NOT NULL REFERENCES knowledge_sources(id),content TEXT NOT NULL,sha256 TEXT NOT NULL UNIQUE, content_vector BLOB, embedding_model TEXT);
CREATE TABLE knowledge_sources (id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,sha256 TEXT NOT NULL UNIQUE,created_at REAL NOT NULL);
CREATE TABLE memory_action_receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_message_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    context_revision INTEGER NOT NULL,
    action TEXT NOT NULL CHECK(action IN
        ('reminder.created','reminder.cancelled','reminder.completed','reminder.claimed_due')),
    reminder_id INTEGER NOT NULL,
    recorded_at REAL NOT NULL
);
CREATE TABLE memory_chat_results (
    message_id INTEGER PRIMARY KEY,
    context_revision INTEGER NOT NULL,
    result_json TEXT NOT NULL
);
INSERT INTO "memory_chat_results" VALUES(2,0,'{"conversation": {"session_id": "a5860432d3cb027b9f1aa408b2925f30", "revision": 0, "user_message_id": 1, "assistant_message_id": 2}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "好的，你已经把会议链接发进小组群了，是你自己发的对吗？", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.525, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "a5860432d3cb027b9f1aa408b2925f30", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "a5860432d3cb027b9f1aa408b2925f30", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(4,0,'{"conversation": {"session_id": "a5860432d3cb027b9f1aa408b2925f30", "revision": 0, "user_message_id": 3, "assistant_message_id": 4}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "是你自己发的，你已经把会议链接发进小组群了。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "清晰耐心", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.7, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.55, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "a5860432d3cb027b9f1aa408b2925f30", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "a5860432d3cb027b9f1aa408b2925f30", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "清晰耐心", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
CREATE TABLE memory_context_revision (
    id INTEGER PRIMARY KEY CHECK (id=1), revision INTEGER NOT NULL
);
INSERT INTO "memory_context_revision" VALUES(1,0);
CREATE TABLE memory_episodic (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type   TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    participants TEXT,
    created_at   REAL    NOT NULL DEFAULT 0
);
CREATE TABLE memory_fragments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    content       TEXT    NOT NULL,
    memory_type   TEXT    NOT NULL DEFAULT 'fact',   -- fact/episode/user_profile/preference/goal
    category      TEXT    NOT NULL DEFAULT 'general',
    importance    REAL    NOT NULL DEFAULT 0.5,       -- 0~1
    last_accessed REAL    NOT NULL DEFAULT 0,
    created_at    REAL    NOT NULL DEFAULT 0,
    content_vector BLOB                                -- 预留：embedding 向量
, status TEXT NOT NULL DEFAULT 'active', valid_from REAL, valid_to REAL, predecessor_id INTEGER, profile_key TEXT, preference_object TEXT, preference_polarity INTEGER, embedding_model TEXT, embedding_dim INTEGER, bad_hits INTEGER NOT NULL DEFAULT 0);
CREATE TABLE memory_long_term_goals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    description TEXT,
    priority    INTEGER NOT NULL DEFAULT 3,           -- 1~5
    progress    REAL    NOT NULL DEFAULT 0,           -- 0~1
    deadline    TEXT,
    status      TEXT    NOT NULL DEFAULT 'active'
);
CREATE TABLE memory_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    session_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    context_tracked INTEGER NOT NULL DEFAULT 0
);
INSERT INTO "memory_messages" VALUES(1,'user','我已经把会议链接发进小组群，是我自己发的。','a5860432d3cb027b9f1aa408b2925f30',1.79450225014433717724e+09,0);
INSERT INTO "memory_messages" VALUES(2,'assistant','好的，你已经把会议链接发进小组群了，是你自己发的对吗？','a5860432d3cb027b9f1aa408b2925f30',1.79450225254458236691e+09,1);
INSERT INTO "memory_messages" VALUES(3,'user','是谁发了链接？','a5860432d3cb027b9f1aa408b2925f30',1.7945022529420015812e+09,0);
INSERT INTO "memory_messages" VALUES(4,'assistant','是你自己发的，你已经把会议链接发进小组群了。','a5860432d3cb027b9f1aa408b2925f30',1.79450225382291126251e+09,1);
CREATE TABLE memory_reminder_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reminder_id INTEGER NOT NULL UNIQUE,
            created_at REAL NOT NULL, acknowledged_at REAL
        );
CREATE TABLE memory_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, due_at REAL NOT NULL, created_at REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'active', notified_at REAL
        );
CREATE TABLE memory_response_context (
    message_id INTEGER NOT NULL,
    source_type TEXT NOT NULL CHECK(source_type IN ('fragment','message')),
    source_id INTEGER NOT NULL,
    PRIMARY KEY(message_id,source_type,source_id)
);
INSERT INTO "memory_response_context" VALUES(2,'message',1);
INSERT INTO "memory_response_context" VALUES(4,'message',1);
INSERT INTO "memory_response_context" VALUES(4,'message',2);
INSERT INTO "memory_response_context" VALUES(4,'message',3);
CREATE TABLE memory_short_term_ideas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    content     TEXT    NOT NULL,
    source_type TEXT    NOT NULL DEFAULT 'chat',
    status      TEXT    NOT NULL DEFAULT 'open',
    excitement  INTEGER NOT NULL DEFAULT 5,           -- 1~10 情绪强度
    created_at  REAL    NOT NULL DEFAULT 0
);
CREATE TABLE memory_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fragment_id INTEGER NOT NULL,
    source_message_id INTEGER,
    evidence TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE memory_summary_items (
    session_id TEXT NOT NULL,
    source_message_id INTEGER NOT NULL,
    PRIMARY KEY (session_id, source_message_id)
);
CREATE TABLE memory_tags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fragment_id INTEGER NOT NULL,
    tag         TEXT    NOT NULL
);
CREATE TABLE memory_version_links (
    fragment_id INTEGER NOT NULL,
    related_fragment_id INTEGER NOT NULL,
    PRIMARY KEY (fragment_id, related_fragment_id)
);
CREATE TABLE memory_web_speaker_state (
    id INTEGER PRIMARY KEY CHECK(id=1),
    format_version INTEGER NOT NULL,
    context_revision INTEGER NOT NULL,
    cursor INTEGER NOT NULL,
    scope TEXT NOT NULL,
    source_ids_json TEXT NOT NULL
);
INSERT INTO "memory_web_speaker_state" VALUES(1,1,0,3,'current_user','[1, 3]');
CREATE TABLE operation_drafts (id INTEGER PRIMARY KEY AUTOINCREMENT,operation_type TEXT NOT NULL CHECK(operation_type IN ('persona.update','emotion.override','knowledge.import','memory.batch')),parameters_json TEXT NOT NULL,baseline_json TEXT NOT NULL,diff_json TEXT NOT NULL,warnings_json TEXT NOT NULL,token_hash TEXT NOT NULL,expires_at REAL NOT NULL,status TEXT NOT NULL CHECK(status IN ('draft','confirmed','expired','failed')),actor TEXT NOT NULL,created_at REAL NOT NULL);
CREATE TABLE persona_versions (id INTEGER PRIMARY KEY AUTOINCREMENT,parent_id INTEGER,data_json TEXT NOT NULL,created_at REAL NOT NULL);
INSERT INTO "persona_versions" VALUES(1,NULL,'{"core_identity":"一个温柔又有点好奇心的AI伙伴","expression_principles":"自然、清晰，先完成用户任务","immutable_rules":"事实须有来源；不得编造身体或共同经历；危险情绪优先现实安全","initiative":0.5,"name":"小海","relationship_boundaries":"支持现实关系，不鼓励排他依赖","temperature_bias":0.0}',1.79450225013253760342e+09);
CREATE TABLE runtime_turn_ledger (
                request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                status TEXT NOT NULL, created_at REAL NOT NULL);
INSERT INTO "runtime_turn_ledger" VALUES('c38_pair_8a39fc50e7f34662a3e083a1221a3845','861a5616919768c7beaf3372da78daebb9e0794d6ceb550c1b9e0823da340d07','completed',1.79450225013423418996e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c38_pair_6a4ca10e174e42eb9421f68016937bce','0eef406f67b42f28131ef63532df62395a13b4d5bf99c4dc2b815045edbd9880','completed',1.79450225293275618552e+09);
CREATE INDEX idx_fragments_type       ON memory_fragments(memory_type);
CREATE INDEX idx_fragments_importance ON memory_fragments(importance);
CREATE INDEX idx_tags_tag ON memory_tags(tag);
CREATE INDEX idx_action_receipts_context
    ON memory_action_receipts(context_revision,source_message_id,id);
CREATE INDEX idx_sources_fragment ON memory_sources(fragment_id);
CREATE INDEX idx_sources_message ON memory_sources(source_message_id);
CREATE INDEX idx_response_context_source ON memory_response_context(source_type,source_id);
CREATE INDEX idx_fragments_current ON memory_fragments(status, memory_type);
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('persona_versions',1);
INSERT INTO "sqlite_sequence" VALUES('memory_messages',4);
COMMIT;
