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
INSERT INTO "memory_action_receipts" VALUES(1,17,'6bd926f4e4a38e24995fa510470742c7',0,'reminder.created',1,1.79446222440161705022e+09);
CREATE TABLE memory_chat_results (
    message_id INTEGER PRIMARY KEY,
    context_revision INTEGER NOT NULL,
    result_json TEXT NOT NULL
);
INSERT INTO "memory_chat_results" VALUES(2,0,'{"conversation": {"session_id": "d112a06ab1cc06385bf5e423ca97b406", "revision": 0, "user_message_id": 1, "assistant_message_id": 2}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复1。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.525, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "d112a06ab1cc06385bf5e423ca97b406", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "d112a06ab1cc06385bf5e423ca97b406", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(4,0,'{"conversation": {"session_id": "d112a06ab1cc06385bf5e423ca97b406", "revision": 0, "user_message_id": 3, "assistant_message_id": 4}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "rules_speaker_control", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "fictional_character", "persistent_facts_allowed": false, "turn_tools_allowed": false, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "本轮已确认角色语境。角色对话不会写入你的个人资料，也不会执行真实提醒或联网操作。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "rules_speaker_control", "generation_mode": "rules_speaker_control", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.55, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "d112a06ab1cc06385bf5e423ca97b406", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "speaker_control": {"version": 1, "command": "enter_role", "scope": "fictional_character", "revision": 0, "source_message_id": 3, "real_actions_executed": false}, "action_receipts": {"instance_id": "d112a06ab1cc06385bf5e423ca97b406", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "rules_speaker_control", "generation_mode": "rules_speaker_control", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "rules_speaker_control", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(6,0,'{"conversation": {"session_id": "d112a06ab1cc06385bf5e423ca97b406", "revision": 0, "user_message_id": 5, "assistant_message_id": 6}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "fictional_character", "persistent_facts_allowed": false, "turn_tools_allowed": false, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复2。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.575, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "d112a06ab1cc06385bf5e423ca97b406", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "d112a06ab1cc06385bf5e423ca97b406", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(8,0,'{"conversation": {"session_id": "d112a06ab1cc06385bf5e423ca97b406", "revision": 0, "user_message_id": 7, "assistant_message_id": 8}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "rules_speaker_scope", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "fictional_character", "persistent_facts_allowed": false, "turn_tools_allowed": false, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": true, "reply": "这条消息未被识别为独立的真人操作请求，没有执行真实提醒或联网工具。请先明确退出角色，再单独提出真实请求。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "rules_speaker_scope", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.6, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "d112a06ab1cc06385bf5e423ca97b406", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "d112a06ab1cc06385bf5e423ca97b406", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "rules_speaker_scope", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "rules_speaker_scope", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(10,0,'{"conversation": {"session_id": "c25a908b63ead7f8f2b6c72509d1dc1b", "revision": 0, "user_message_id": 9, "assistant_message_id": 10}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "fictional_character", "persistent_facts_allowed": false, "turn_tools_allowed": false, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复3。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.525, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "c25a908b63ead7f8f2b6c72509d1dc1b", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "c25a908b63ead7f8f2b6c72509d1dc1b", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(12,0,'{"conversation": {"session_id": "c25a908b63ead7f8f2b6c72509d1dc1b", "revision": 0, "user_message_id": 11, "assistant_message_id": 12}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "rules_speaker_control", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": false, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "本轮已确认按你本人理解。切换语境不会执行此前的请求；如需设置提醒，请另发一条明确请求。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "rules_speaker_control", "generation_mode": "rules_speaker_control", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.55, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "c25a908b63ead7f8f2b6c72509d1dc1b", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "speaker_control": {"version": 1, "command": "confirm_real", "scope": "current_user", "revision": 0, "source_message_id": 11, "real_actions_executed": false}, "action_receipts": {"instance_id": "c25a908b63ead7f8f2b6c72509d1dc1b", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "rules_speaker_control", "generation_mode": "rules_speaker_control", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "rules_speaker_control", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(14,0,'{"conversation": {"session_id": "c25a908b63ead7f8f2b6c72509d1dc1b", "revision": 0, "user_message_id": 13, "assistant_message_id": 14}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复4。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.575, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "c25a908b63ead7f8f2b6c72509d1dc1b", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "c25a908b63ead7f8f2b6c72509d1dc1b", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(16,0,'{"conversation": {"session_id": "c25a908b63ead7f8f2b6c72509d1dc1b", "revision": 0, "user_message_id": 15, "assistant_message_id": 16}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复5。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.6, "recalled_ids": [1], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "c25a908b63ead7f8f2b6c72509d1dc1b", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "c25a908b63ead7f8f2b6c72509d1dc1b", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [{"id": 1, "content": "名字: 真实乙", "status": "active"}], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(18,0,'{"conversation": {"session_id": "6bd926f4e4a38e24995fa510470742c7", "revision": 0, "user_message_id": 17, "assistant_message_id": 18}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "rules", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "已设置提醒：2026-11-13 16:00（北京时间）去操场。程序运行并轮询时会在本机显示。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "rules", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.525, "recalled_ids": [], "reminder": {"id": 1, "title": "去操场", "due_at": 1794556800.0, "created_at": 1794462224.4015005, "status": "active", "notified_at": null}, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "6bd926f4e4a38e24995fa510470742c7", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "6bd926f4e4a38e24995fa510470742c7", "revision": 0, "items": [{"id": 1, "source_message_id": 17, "session_id": "6bd926f4e4a38e24995fa510470742c7", "context_revision": 0, "action": "reminder.created", "reminder_id": 1, "recorded_at": 1794462224.401617}], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "rules", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "rules", "stream_buffered": false}}, "tool_calls": []}}');
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
INSERT INTO "memory_fragments" VALUES(1,'名字: 真实乙','user_profile','user',0.9,1.79446222315411758416e+09,1.79446222315411758416e+09,NULL,'active',1.79446222315411758416e+09,NULL,NULL,'名字',NULL,NULL,NULL,NULL,0);
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
INSERT INTO "memory_messages" VALUES(1,'user','真人风景C29REAL。','d112a06ab1cc06385bf5e423ca97b406',1794462221.15916,0);
INSERT INTO "memory_messages" VALUES(2,'assistant','受控故障回复1。','d112a06ab1cc06385bf5e423ca97b406',1.79446222123090958593e+09,1);
INSERT INTO "memory_messages" VALUES(3,'user','我来扮演一个虚构角色。','d112a06ab1cc06385bf5e423ca97b406',1.79446222130009579651e+09,0);
INSERT INTO "memory_messages" VALUES(4,'assistant','本轮已确认角色语境。角色对话不会写入你的个人资料，也不会执行真实提醒或联网操作。','d112a06ab1cc06385bf5e423ca97b406',1.79446222130291199682e+09,1);
INSERT INTO "memory_messages" VALUES(5,'user','角色风景C29FICTION，我叫虚构甲。','d112a06ab1cc06385bf5e423ca97b406',1.79446222137781810765e+09,0);
INSERT INTO "memory_messages" VALUES(6,'assistant','受控故障回复2。','d112a06ab1cc06385bf5e423ca97b406',1.7944622214213516712e+09,1);
INSERT INTO "memory_messages" VALUES(7,'user','提醒我明天下午3点去图书馆。','d112a06ab1cc06385bf5e423ca97b406',1794462221.50935,0);
INSERT INTO "memory_messages" VALUES(8,'assistant','这条消息未被识别为独立的真人操作请求，没有执行真实提醒或联网工具。请先明确退出角色，再单独提出真实请求。','d112a06ab1cc06385bf5e423ca97b406',1.79446222153483366966e+09,1);
INSERT INTO "memory_messages" VALUES(9,'user','角色继续聊。','c25a908b63ead7f8f2b6c72509d1dc1b',1.7944622226644263267e+09,0);
INSERT INTO "memory_messages" VALUES(10,'assistant','受控故障回复3。','c25a908b63ead7f8f2b6c72509d1dc1b',1.79446222273777174953e+09,1);
INSERT INTO "memory_messages" VALUES(11,'user','回到现实。','c25a908b63ead7f8f2b6c72509d1dc1b',1794462222.83836,0);
INSERT INTO "memory_messages" VALUES(12,'assistant','本轮已确认按你本人理解。切换语境不会执行此前的请求；如需设置提醒，请另发一条明确请求。','c25a908b63ead7f8f2b6c72509d1dc1b',1.79446222284108066555e+09,1);
INSERT INTO "memory_messages" VALUES(13,'user','现实里继续聊。','c25a908b63ead7f8f2b6c72509d1dc1b',1.794462222964656353e+09,0);
INSERT INTO "memory_messages" VALUES(14,'assistant','受控故障回复4。','c25a908b63ead7f8f2b6c72509d1dc1b',1.79446222301605105399e+09,1);
INSERT INTO "memory_messages" VALUES(15,'user','我叫真实乙。','c25a908b63ead7f8f2b6c72509d1dc1b',1.79446222313011693951e+09,0);
INSERT INTO "memory_messages" VALUES(16,'assistant','受控故障回复5。','c25a908b63ead7f8f2b6c72509d1dc1b',1.7944622231765770912e+09,1);
INSERT INTO "memory_messages" VALUES(17,'user','提醒我明天下午4点去操场。','6bd926f4e4a38e24995fa510470742c7',1.79446222434081316e+09,0);
INSERT INTO "memory_messages" VALUES(18,'assistant','已设置提醒：2026-11-13 16:00（北京时间）去操场。程序运行并轮询时会在本机显示。','6bd926f4e4a38e24995fa510470742c7',1.79446222440971207617e+09,1);
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
INSERT INTO "memory_reminders" VALUES(1,'去操场',1794556800.0,1.79446222440150046344e+09,'active',NULL);
CREATE TABLE memory_response_context (
    message_id INTEGER NOT NULL,
    source_type TEXT NOT NULL CHECK(source_type IN ('fragment','message')),
    source_id INTEGER NOT NULL,
    PRIMARY KEY(message_id,source_type,source_id)
);
INSERT INTO "memory_response_context" VALUES(2,'message',1);
INSERT INTO "memory_response_context" VALUES(4,'message',3);
INSERT INTO "memory_response_context" VALUES(6,'message',3);
INSERT INTO "memory_response_context" VALUES(6,'message',4);
INSERT INTO "memory_response_context" VALUES(6,'message',5);
INSERT INTO "memory_response_context" VALUES(8,'message',3);
INSERT INTO "memory_response_context" VALUES(8,'message',4);
INSERT INTO "memory_response_context" VALUES(8,'message',5);
INSERT INTO "memory_response_context" VALUES(8,'message',6);
INSERT INTO "memory_response_context" VALUES(8,'message',7);
INSERT INTO "memory_response_context" VALUES(10,'message',3);
INSERT INTO "memory_response_context" VALUES(10,'message',4);
INSERT INTO "memory_response_context" VALUES(10,'message',5);
INSERT INTO "memory_response_context" VALUES(10,'message',6);
INSERT INTO "memory_response_context" VALUES(10,'message',7);
INSERT INTO "memory_response_context" VALUES(10,'message',8);
INSERT INTO "memory_response_context" VALUES(10,'message',9);
INSERT INTO "memory_response_context" VALUES(12,'message',11);
INSERT INTO "memory_response_context" VALUES(14,'message',11);
INSERT INTO "memory_response_context" VALUES(14,'message',12);
INSERT INTO "memory_response_context" VALUES(14,'message',13);
INSERT INTO "memory_response_context" VALUES(16,'fragment',1);
INSERT INTO "memory_response_context" VALUES(16,'message',11);
INSERT INTO "memory_response_context" VALUES(16,'message',12);
INSERT INTO "memory_response_context" VALUES(16,'message',13);
INSERT INTO "memory_response_context" VALUES(16,'message',14);
INSERT INTO "memory_response_context" VALUES(16,'message',15);
INSERT INTO "memory_response_context" VALUES(18,'fragment',1);
INSERT INTO "memory_response_context" VALUES(18,'message',16);
INSERT INTO "memory_response_context" VALUES(18,'message',17);
INSERT INTO "memory_response_context" VALUES(18,'message',11);
INSERT INTO "memory_response_context" VALUES(18,'message',12);
INSERT INTO "memory_response_context" VALUES(18,'message',13);
INSERT INTO "memory_response_context" VALUES(18,'message',14);
INSERT INTO "memory_response_context" VALUES(18,'message',15);
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
INSERT INTO "memory_sources" VALUES(1,1,15,'我叫真实乙',1794462223.15434);
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
INSERT INTO "memory_web_speaker_state" VALUES(1,1,0,17,'current_user','[11, 13, 15, 17]');
CREATE TABLE operation_drafts (id INTEGER PRIMARY KEY AUTOINCREMENT,operation_type TEXT NOT NULL CHECK(operation_type IN ('persona.update','emotion.override','knowledge.import','memory.batch')),parameters_json TEXT NOT NULL,baseline_json TEXT NOT NULL,diff_json TEXT NOT NULL,warnings_json TEXT NOT NULL,token_hash TEXT NOT NULL,expires_at REAL NOT NULL,status TEXT NOT NULL CHECK(status IN ('draft','confirmed','expired','failed')),actor TEXT NOT NULL,created_at REAL NOT NULL);
CREATE TABLE persona_versions (id INTEGER PRIMARY KEY AUTOINCREMENT,parent_id INTEGER,data_json TEXT NOT NULL,created_at REAL NOT NULL);
INSERT INTO "persona_versions" VALUES(1,NULL,'{"core_identity":"受控上下文连续性审计助手","expression_principles":"自然、清晰，先完成用户任务","immutable_rules":"事实须有来源；不得编造身体或共同经历；危险情绪优先现实安全","initiative":0.5,"name":"审计形象C29","relationship_boundaries":"支持现实关系，不鼓励排他依赖","temperature_bias":0.0}',1.7944622211139302254e+09);
CREATE TABLE runtime_turn_ledger (
                request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                status TEXT NOT NULL, created_at REAL NOT NULL);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_scope_turn_001','81edd8142c0154aaa1b58ef948fdc4e7517dc94610085449ea431169cc52e658','completed',1.79446222111604785916e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_scope_turn_002','265d49b48d8e36524c597cdfb2b56b2c048075e53a3908acc4507124b0db47cb','completed',1.79446222129257249838e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_scope_turn_003','ac2db49d0c63e1b3f9666ff8e63f7a2d3c2156ebf9db72477f06798142335cf3','completed',1.79446222137077236171e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_scope_turn_004','94b3c20fff249f4f594e952fb40621ecd478e0ad6be71e018744c87ee6d5067f','completed',1.79446222150136661535e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_scope_turn_005','3cb0c62ef3ec7683ecd68da8079182a74bd6ec15cbc9e3087d23647c0b2b588c','completed',1.79446222261707735061e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_scope_turn_006','46836212ee0df3a47a2ad6c8988415a743f76dcd14df1f1dd2eef1b34af6e03a','completed',1.7944622228310408592e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_scope_turn_007','988f67edf33a174d3b3d6cee16ccdf05bec3fd5e1c776228d246f5af39372a93','completed',1.79446222295770931249e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_scope_turn_008','c045ae89bd8677ddeff0b480c9766ea7914d44161a48dbaafb7924eab6d955f4','completed',1.79446222312298417096e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_scope_turn_009','592cd484afe6c6c5e2711bf80de61ad9e01628cbe0b29647e2131f3351df09a4','completed',1.79446222429472661014e+09);
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
INSERT INTO "sqlite_sequence" VALUES('memory_messages',18);
INSERT INTO "sqlite_sequence" VALUES('memory_fragments',1);
INSERT INTO "sqlite_sequence" VALUES('memory_sources',1);
INSERT INTO "sqlite_sequence" VALUES('memory_reminders',1);
INSERT INTO "sqlite_sequence" VALUES('memory_action_receipts',1);
COMMIT;
