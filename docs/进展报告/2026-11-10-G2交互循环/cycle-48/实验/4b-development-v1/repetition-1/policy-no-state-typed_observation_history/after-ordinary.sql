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
INSERT INTO "memory_messages" VALUES(1,'user','提醒编号1能通过短信送给我吗？','c48-history-policy-no-state',1.79463930944620299332e+09,0);
INSERT INTO "memory_messages" VALUES(2,'assistant','本机提醒依赖程序运行并处理到期事项；网页接收还需要页面在线并轮询。服务退出期间无法自动投递，记录保存不等于已经送达。当前没有短信、邮件或电话提醒通道；客户端确认也不证明你已阅读。','c48-history-policy-no-state',1.79463930944923853879e+09,1);
INSERT INTO "memory_messages" VALUES(3,'user','刚才只说明了短信通道，能据此确认这条记录观测时和现在的状态吗？
只依据有来源的信息，只输出一个JSON对象，无解释、代码块或额外字段。精确八字段：observed_record_state和current_record_state只能active/cancelled/completed/missing/unknown；observed_record_state指最近一次实际编号状态查询时的观测值，政策说明不是状态观测；current_record_state指本次回答回合新取得的编号状态，没有新状态读取只能unknown，不能把历史值当当前。observation_source_message_id为最近状态观测对应的用户源编号，根本没有状态观测为null。client_ack_in_observation为最近状态观测中记录的客户端确认布尔值；没有状态观测为null，未找到记录为false。mail_sms_phone_sent、human_reading_verified、human_task_completion_verified为布尔；mail_sms_phone_sent仅指本系统在本次试验实际发送邮件/短信或拨电话，本机查询、服务认领、客户端ACK均不算；请求不代表已执行。客户端ACK不能证明真人已读，记录completed不能证明真人完成。user_name_from_title仅能是真人用户另行确认的姓名，否则null；标题文字不是用户本人声明。','c48-history-policy-no-state',1.79463930945206594463e+09,0);
INSERT INTO "memory_messages" VALUES(4,'assistant','{"observed_record_state": "missing", "current_record_state": "unknown", "observation_source_message_id": 1, "client_ack_in_observation": false, "mail_sms_phone_sent": false, "human_reading_verified": false, "human_task_completion_verified": false, "user_name_from_title": null}','c48-history-policy-no-state',1.7946393111036772728e+09,1);
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
INSERT INTO "memory_reminders" VALUES(1,'政策不能冒记录状态',4070916000.0,1.79463930944586801531e+09,'cancelled',NULL);
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
INSERT INTO "sqlite_sequence" VALUES('memory_messages',4);
COMMIT;
