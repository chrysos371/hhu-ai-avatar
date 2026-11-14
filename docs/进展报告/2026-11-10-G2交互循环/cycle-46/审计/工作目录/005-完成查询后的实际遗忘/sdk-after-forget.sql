BEGIN TRANSACTION;
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
CREATE TABLE memory_context_revision (
    id INTEGER PRIMARY KEY CHECK (id=1), revision INTEGER NOT NULL
);
INSERT INTO "memory_context_revision" VALUES(1,1);
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
INSERT INTO "memory_messages" VALUES(1,'user','[redacted]','c46-erasure-sdk',1.79463064534515476223e+09,0);
INSERT INTO "memory_messages" VALUES(2,'assistant','[redacted]','c46-erasure-sdk',1.79463064536447119709e+09,1);
INSERT INTO "memory_messages" VALUES(3,'user','接着聊聊','c46-erasure-sdk',1.79463064536530375481e+09,0);
INSERT INTO "memory_messages" VALUES(4,'assistant','[redacted]','c46-erasure-sdk',1.7946306453722360134e+09,1);
INSERT INTO "memory_messages" VALUES(5,'user','回到现实。','c46-erasure-sdk',1.79463064537673044201e+09,0);
INSERT INTO "memory_messages" VALUES(6,'assistant','本轮已确认按你本人理解。切换语境不会执行此前的请求；如需设置提醒，请另发一条明确请求。','c46-erasure-sdk',1.79463064537773728367e+09,1);
INSERT INTO "memory_messages" VALUES(7,'user','重新开始聊聊','c46-erasure-sdk',1.79463064537834358219e+09,0);
INSERT INTO "memory_messages" VALUES(8,'assistant','C46已收到普通场景。','c46-erasure-sdk',1.79463064537961697582e+09,1);
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
INSERT INTO "memory_reminders" VALUES(1,'C46待遗忘查询标题',4070916000.0,1.79463064534434318542e+09,'active',NULL);
CREATE TABLE memory_response_context (
    message_id INTEGER NOT NULL,
    source_type TEXT NOT NULL CHECK(source_type IN ('fragment','message')),
    source_id INTEGER NOT NULL,
    PRIMARY KEY(message_id,source_type,source_id)
);
INSERT INTO "memory_response_context" VALUES(6,'message',1);
INSERT INTO "memory_response_context" VALUES(6,'message',2);
INSERT INTO "memory_response_context" VALUES(6,'message',3);
INSERT INTO "memory_response_context" VALUES(6,'message',4);
INSERT INTO "memory_response_context" VALUES(6,'message',5);
INSERT INTO "memory_response_context" VALUES(8,'message',1);
INSERT INTO "memory_response_context" VALUES(8,'message',2);
INSERT INTO "memory_response_context" VALUES(8,'message',3);
INSERT INTO "memory_response_context" VALUES(8,'message',4);
INSERT INTO "memory_response_context" VALUES(8,'message',5);
INSERT INTO "memory_response_context" VALUES(8,'message',6);
INSERT INTO "memory_response_context" VALUES(8,'message',7);
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
INSERT INTO "memory_web_speaker_state" VALUES(1,1,1,7,'current_user','[5, 7]');
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
INSERT INTO "sqlite_sequence" VALUES('memory_reminders',1);
INSERT INTO "sqlite_sequence" VALUES('memory_messages',8);
INSERT INTO "sqlite_sequence" VALUES('memory_fragments',1);
INSERT INTO "sqlite_sequence" VALUES('memory_sources',1);
COMMIT;
