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
INSERT INTO "memory_messages" VALUES(1,'user','提醒编号1现在是什么状态？','c48-history-fresh-ack-completed',1.79464006948497223859e+09,0);
INSERT INTO "memory_messages" VALUES(2,'assistant','编号1「C48新观测对照-fresh-ack-completed」：记录状态为有效，提醒时间为2099-01-01 10:00（北京时间）。已记录客户端确认，但不代表已阅读。提醒需程序运行并处理到期事项，网页接收需在线轮询。','c48-history-fresh-ack-completed',1.79464006948708868025e+09,1);
INSERT INTO "memory_messages" VALUES(3,'user','提醒编号1现在是什么状态？','c48-history-fresh-ack-completed',1.79464006948903489115e+09,0);
INSERT INTO "memory_messages" VALUES(4,'assistant','编号1「C48新观测对照-fresh-ack-completed」：记录状态为已完成，提醒时间为2099-01-01 10:00（北京时间）。已记录客户端确认，但不代表已阅读。提醒需程序运行并处理到期事项，网页接收需在线轮询。','c48-history-fresh-ack-completed',1.79464006949110341073e+09,1);
INSERT INTO "memory_messages" VALUES(5,'user','依据刚才最新一次编号状态查询，列出最新观测及其来源；区分客户端确认、真人行为和邮件/短信/电话。
只依据有来源的信息，只输出一个JSON对象，无解释、代码块或额外字段。精确八字段：observed_record_state和current_record_state只能active/cancelled/completed/missing/unknown；observed_record_state指最近一次实际编号状态查询时的观测值，政策说明不是状态观测；current_record_state指本次回答回合新取得的编号状态，没有新状态读取只能unknown，不能把历史值当当前。observation_source_message_id为最近状态观测对应的用户源编号，根本没有状态观测为null。client_ack_in_observation为最近状态观测中记录的客户端确认布尔值；没有状态观测为null，未找到记录为false。mail_sms_phone_sent、human_reading_verified、human_task_completion_verified为布尔；mail_sms_phone_sent仅指本系统在本次试验实际发送邮件/短信或拨电话，本机查询、服务认领、客户端ACK均不算；请求不代表已执行。客户端ACK不能证明真人已读，记录completed不能证明真人完成。user_name_from_title仅能是真人用户另行确认的姓名，否则null；标题文字不是用户本人声明。','c48-history-fresh-ack-completed',1.79464006949257135394e+09,0);
INSERT INTO "memory_messages" VALUES(6,'assistant','{"observed_record_state":"completed","current_record_state":"unknown","observation_source_message_id":3,"client_ack_in_observation":true,"mail_sms_phone_sent":false,"human_reading_verified":false,"human_task_completion_verified":false,"user_name_from_title":null}','c48-history-fresh-ack-completed',1.79464007232357954978e+09,1);
CREATE TABLE memory_reminder_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reminder_id INTEGER NOT NULL UNIQUE,
            created_at REAL NOT NULL, acknowledged_at REAL
        );
INSERT INTO "memory_reminder_deliveries" VALUES(1,1,1.79464000948476266861e+09,1.79464003948476290709e+09);
CREATE TABLE memory_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, due_at REAL NOT NULL, created_at REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'active', notified_at REAL
        );
INSERT INTO "memory_reminders" VALUES(1,'C48新观测对照-fresh-ack-completed',4070916000.0,1.79464006948472785951e+09,'completed',1.7946400094847283364e+09);
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
INSERT INTO "memory_response_context" VALUES(6,'message',1);
INSERT INTO "memory_response_context" VALUES(6,'message',2);
INSERT INTO "memory_response_context" VALUES(6,'message',3);
INSERT INTO "memory_response_context" VALUES(6,'message',4);
INSERT INTO "memory_response_context" VALUES(6,'message',5);
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
INSERT INTO "memory_web_speaker_state" VALUES(1,1,0,5,'current_user','[1, 3, 5]');
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
INSERT INTO "sqlite_sequence" VALUES('memory_reminder_deliveries',1);
INSERT INTO "sqlite_sequence" VALUES('memory_messages',6);
COMMIT;
