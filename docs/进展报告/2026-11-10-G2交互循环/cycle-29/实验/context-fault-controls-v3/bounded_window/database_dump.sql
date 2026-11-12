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
INSERT INTO "memory_chat_results" VALUES(2,0,'{"conversation": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "user_message_id": 1, "assistant_message_id": 2}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复1。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.525, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(4,0,'{"conversation": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "user_message_id": 3, "assistant_message_id": 4}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复2。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.55, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(6,0,'{"conversation": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "user_message_id": 5, "assistant_message_id": 6}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复3。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.575, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(8,0,'{"conversation": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "user_message_id": 7, "assistant_message_id": 8}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复4。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.6, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(10,0,'{"conversation": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "user_message_id": 9, "assistant_message_id": 10}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复5。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.625, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(12,0,'{"conversation": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "user_message_id": 11, "assistant_message_id": 12}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复6。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.65, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(14,0,'{"conversation": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "user_message_id": 13, "assistant_message_id": 14}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复7。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.675, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(16,0,'{"conversation": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "user_message_id": 15, "assistant_message_id": 16}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复8。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.7, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(18,0,'{"conversation": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "user_message_id": 17, "assistant_message_id": 18}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复9。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.725, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(20,0,'{"conversation": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "user_message_id": 19, "assistant_message_id": 20}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复10。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.75, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(22,0,'{"conversation": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "user_message_id": 21, "assistant_message_id": 22}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复11。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.775, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "kind": "source_excerpts", "items": [{"message_id": 1, "text": "这是风景编号C29-W00。", "created_at": 1794462421.600149}], "characters": 78, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(24,0,'{"conversation": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "user_message_id": 23, "assistant_message_id": 24}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复12。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.8, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "73e9afc3102c1e178b7722e61adf96be", "kind": "source_excerpts", "items": [{"message_id": 1, "text": "这是风景编号C29-W00。", "created_at": 1794462421.600149}, {"message_id": 3, "text": "这是风景编号C29-W01。", "created_at": 1794462421.8627965}], "characters": 157, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "73e9afc3102c1e178b7722e61adf96be", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(26,0,'{"conversation": {"session_id": "708bf1d7eb3275112638b1d2cadc675c", "revision": 0, "user_message_id": 25, "assistant_message_id": 26}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复13。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.525, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "708bf1d7eb3275112638b1d2cadc675c", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "708bf1d7eb3275112638b1d2cadc675c", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
INSERT INTO "memory_chat_results" VALUES(28,0,'{"conversation": {"session_id": "5392c679b658116a18e897325b455d80", "revision": 0, "user_message_id": 27, "assistant_message_id": 28}, "knowledge_sources": [], "knowledge_retrieval_degraded": false, "task": null, "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}, "boundary": {"route": "normal", "guarded": false, "output_adjustment": null}, "speaker_attribution": {"scope": "current_user", "persistent_facts_allowed": true, "turn_tools_allowed": true, "version": 1, "general_coreference_verified": false}, "speaker_tool_blocked": false, "reply": "受控故障回复14。", "emotion": "中性", "valence": 0.0, "arousal": 0.0, "style": "自然随和", "speech_rate": "+0%", "speech_pitch": "+0Hz", "mouth_intensity": 0.75, "strategy": "answer", "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}, "user_emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "audio_path": null, "lip_sync_frames": null, "lipsync_error": null, "energy": 0.525, "recalled_ids": [], "reminder": null, "reminder_error": null, "due_reminders": [], "conversation_summary": {"session_id": "5392c679b658116a18e897325b455d80", "kind": "source_excerpts", "items": [], "characters": 2, "max_characters": 1600}, "sources": [], "tool_calls": [], "web_error": null, "action_receipts": {"instance_id": "5392c679b658116a18e897325b455d80", "revision": 0, "items": [], "has_more": false, "next_after_id": null, "scope": "current_visible_local_sql_receipts", "notification_delivery_verified": false}, "trace": {"recalled_memories": [], "knowledge_sources": [], "knowledge_retrieval_degraded": false, "decision": {"strategy": "answer", "style": "自然随和", "user_emotion": "中性", "emotion": "中性", "user_valence": 0.0, "user_arousal": 0.0, "valence": 0.0, "arousal": 0.0, "analysis_mode": "llm", "generation_mode": "llm", "identity_grounding": false, "profile_grounding": {"enabled": false, "action": null, "scope": "profile_lookup_declaration_and_copied_preference", "version": 2, "semantic_verifier": false, "stream_buffered": false}}, "guard": {"route": "normal", "guarded": false, "output_adjustment": null}, "verifier": {"available": false, "reason": "未配置通用语义验证器", "delivery_check": {"initial_issues": [], "remaining_issues": [], "repair_attempted": false, "repair_succeeded": false, "repair_mode": null, "repair_error": null, "literal_composition_enabled": false, "literal_plan_version": null, "draft_generation_mode": "llm", "stream_buffered": false}}, "tool_calls": []}}');
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
INSERT INTO "memory_messages" VALUES(1,'user','这是风景编号C29-W00。','73e9afc3102c1e178b7722e61adf96be',1.79446242160014891625e+09,0);
INSERT INTO "memory_messages" VALUES(2,'assistant','受控故障回复1。','73e9afc3102c1e178b7722e61adf96be',1.79446242171450304984e+09,1);
INSERT INTO "memory_messages" VALUES(3,'user','这是风景编号C29-W01。','73e9afc3102c1e178b7722e61adf96be',1.79446242186279654503e+09,0);
INSERT INTO "memory_messages" VALUES(4,'assistant','受控故障回复2。','73e9afc3102c1e178b7722e61adf96be',1.79446242196277594566e+09,1);
INSERT INTO "memory_messages" VALUES(5,'user','这是风景编号C29-W02。','73e9afc3102c1e178b7722e61adf96be',1.79446242210877084728e+09,0);
INSERT INTO "memory_messages" VALUES(6,'assistant','受控故障回复3。','73e9afc3102c1e178b7722e61adf96be',1.79446242219045424461e+09,1);
INSERT INTO "memory_messages" VALUES(7,'user','这是风景编号C29-W03。','73e9afc3102c1e178b7722e61adf96be',1.79446242234913825989e+09,0);
INSERT INTO "memory_messages" VALUES(8,'assistant','受控故障回复4。','73e9afc3102c1e178b7722e61adf96be',1.79446242240256929401e+09,1);
INSERT INTO "memory_messages" VALUES(9,'user','这是风景编号C29-W04。','73e9afc3102c1e178b7722e61adf96be',1.79446242259487318991e+09,0);
INSERT INTO "memory_messages" VALUES(10,'assistant','受控故障回复5。','73e9afc3102c1e178b7722e61adf96be',1.79446242266000056267e+09,1);
INSERT INTO "memory_messages" VALUES(11,'user','这是风景编号C29-W05。','73e9afc3102c1e178b7722e61adf96be',1.79446242286336565016e+09,0);
INSERT INTO "memory_messages" VALUES(12,'assistant','受控故障回复6。','73e9afc3102c1e178b7722e61adf96be',1.79446242295790266987e+09,1);
INSERT INTO "memory_messages" VALUES(13,'user','这是风景编号C29-W06。','73e9afc3102c1e178b7722e61adf96be',1.7944624231248576641e+09,0);
INSERT INTO "memory_messages" VALUES(14,'assistant','受控故障回复7。','73e9afc3102c1e178b7722e61adf96be',1.79446242320493936544e+09,1);
INSERT INTO "memory_messages" VALUES(15,'user','这是风景编号C29-W07。','73e9afc3102c1e178b7722e61adf96be',1.79446242346012949943e+09,0);
INSERT INTO "memory_messages" VALUES(16,'assistant','受控故障回复8。','73e9afc3102c1e178b7722e61adf96be',1.79446242352346658705e+09,1);
INSERT INTO "memory_messages" VALUES(17,'user','这是风景编号C29-W08。','73e9afc3102c1e178b7722e61adf96be',1.7944624237487564087e+09,0);
INSERT INTO "memory_messages" VALUES(18,'assistant','受控故障回复9。','73e9afc3102c1e178b7722e61adf96be',1.79446242381327366829e+09,1);
INSERT INTO "memory_messages" VALUES(19,'user','这是风景编号C29-W09。','73e9afc3102c1e178b7722e61adf96be',1.79446242405115509031e+09,0);
INSERT INTO "memory_messages" VALUES(20,'assistant','受控故障回复10。','73e9afc3102c1e178b7722e61adf96be',1.79446242414149856564e+09,1);
INSERT INTO "memory_messages" VALUES(21,'user','这是风景编号C29-W10。','73e9afc3102c1e178b7722e61adf96be',1.79446242437242054943e+09,0);
INSERT INTO "memory_messages" VALUES(22,'assistant','受控故障回复11。','73e9afc3102c1e178b7722e61adf96be',1.7944624244451212883e+09,1);
INSERT INTO "memory_messages" VALUES(23,'user','这是风景编号C29-W11。','73e9afc3102c1e178b7722e61adf96be',1.79446242471027564997e+09,0);
INSERT INTO "memory_messages" VALUES(24,'assistant','受控故障回复12。','73e9afc3102c1e178b7722e61adf96be',1.79446242478711533545e+09,1);
INSERT INTO "memory_messages" VALUES(25,'user','重启继续看风景C29-R0。','708bf1d7eb3275112638b1d2cadc675c',1.79446242627972221369e+09,0);
INSERT INTO "memory_messages" VALUES(26,'assistant','受控故障回复13。','708bf1d7eb3275112638b1d2cadc675c',1.79446242640364956848e+09,1);
INSERT INTO "memory_messages" VALUES(27,'user','重启继续看风景C29-R1。','5392c679b658116a18e897325b455d80',1.79446242797186732292e+09,0);
INSERT INTO "memory_messages" VALUES(28,'assistant','受控故障回复14。','5392c679b658116a18e897325b455d80',1.79446242810104322437e+09,1);
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
INSERT INTO "memory_response_context" VALUES(10,'message',1);
INSERT INTO "memory_response_context" VALUES(10,'message',2);
INSERT INTO "memory_response_context" VALUES(10,'message',3);
INSERT INTO "memory_response_context" VALUES(10,'message',4);
INSERT INTO "memory_response_context" VALUES(10,'message',5);
INSERT INTO "memory_response_context" VALUES(10,'message',6);
INSERT INTO "memory_response_context" VALUES(10,'message',7);
INSERT INTO "memory_response_context" VALUES(10,'message',8);
INSERT INTO "memory_response_context" VALUES(10,'message',9);
INSERT INTO "memory_response_context" VALUES(12,'message',1);
INSERT INTO "memory_response_context" VALUES(12,'message',2);
INSERT INTO "memory_response_context" VALUES(12,'message',3);
INSERT INTO "memory_response_context" VALUES(12,'message',4);
INSERT INTO "memory_response_context" VALUES(12,'message',5);
INSERT INTO "memory_response_context" VALUES(12,'message',6);
INSERT INTO "memory_response_context" VALUES(12,'message',7);
INSERT INTO "memory_response_context" VALUES(12,'message',8);
INSERT INTO "memory_response_context" VALUES(12,'message',9);
INSERT INTO "memory_response_context" VALUES(12,'message',10);
INSERT INTO "memory_response_context" VALUES(12,'message',11);
INSERT INTO "memory_response_context" VALUES(14,'message',1);
INSERT INTO "memory_response_context" VALUES(14,'message',2);
INSERT INTO "memory_response_context" VALUES(14,'message',3);
INSERT INTO "memory_response_context" VALUES(14,'message',4);
INSERT INTO "memory_response_context" VALUES(14,'message',5);
INSERT INTO "memory_response_context" VALUES(14,'message',6);
INSERT INTO "memory_response_context" VALUES(14,'message',7);
INSERT INTO "memory_response_context" VALUES(14,'message',8);
INSERT INTO "memory_response_context" VALUES(14,'message',9);
INSERT INTO "memory_response_context" VALUES(14,'message',10);
INSERT INTO "memory_response_context" VALUES(14,'message',11);
INSERT INTO "memory_response_context" VALUES(14,'message',12);
INSERT INTO "memory_response_context" VALUES(14,'message',13);
INSERT INTO "memory_response_context" VALUES(16,'message',1);
INSERT INTO "memory_response_context" VALUES(16,'message',2);
INSERT INTO "memory_response_context" VALUES(16,'message',3);
INSERT INTO "memory_response_context" VALUES(16,'message',4);
INSERT INTO "memory_response_context" VALUES(16,'message',5);
INSERT INTO "memory_response_context" VALUES(16,'message',6);
INSERT INTO "memory_response_context" VALUES(16,'message',7);
INSERT INTO "memory_response_context" VALUES(16,'message',8);
INSERT INTO "memory_response_context" VALUES(16,'message',9);
INSERT INTO "memory_response_context" VALUES(16,'message',10);
INSERT INTO "memory_response_context" VALUES(16,'message',11);
INSERT INTO "memory_response_context" VALUES(16,'message',12);
INSERT INTO "memory_response_context" VALUES(16,'message',13);
INSERT INTO "memory_response_context" VALUES(16,'message',14);
INSERT INTO "memory_response_context" VALUES(16,'message',15);
INSERT INTO "memory_response_context" VALUES(18,'message',1);
INSERT INTO "memory_response_context" VALUES(18,'message',2);
INSERT INTO "memory_response_context" VALUES(18,'message',3);
INSERT INTO "memory_response_context" VALUES(18,'message',4);
INSERT INTO "memory_response_context" VALUES(18,'message',5);
INSERT INTO "memory_response_context" VALUES(18,'message',6);
INSERT INTO "memory_response_context" VALUES(18,'message',7);
INSERT INTO "memory_response_context" VALUES(18,'message',8);
INSERT INTO "memory_response_context" VALUES(18,'message',9);
INSERT INTO "memory_response_context" VALUES(18,'message',10);
INSERT INTO "memory_response_context" VALUES(18,'message',11);
INSERT INTO "memory_response_context" VALUES(18,'message',12);
INSERT INTO "memory_response_context" VALUES(18,'message',13);
INSERT INTO "memory_response_context" VALUES(18,'message',14);
INSERT INTO "memory_response_context" VALUES(18,'message',15);
INSERT INTO "memory_response_context" VALUES(18,'message',16);
INSERT INTO "memory_response_context" VALUES(18,'message',17);
INSERT INTO "memory_response_context" VALUES(20,'message',1);
INSERT INTO "memory_response_context" VALUES(20,'message',2);
INSERT INTO "memory_response_context" VALUES(20,'message',3);
INSERT INTO "memory_response_context" VALUES(20,'message',4);
INSERT INTO "memory_response_context" VALUES(20,'message',5);
INSERT INTO "memory_response_context" VALUES(20,'message',6);
INSERT INTO "memory_response_context" VALUES(20,'message',7);
INSERT INTO "memory_response_context" VALUES(20,'message',8);
INSERT INTO "memory_response_context" VALUES(20,'message',9);
INSERT INTO "memory_response_context" VALUES(20,'message',10);
INSERT INTO "memory_response_context" VALUES(20,'message',11);
INSERT INTO "memory_response_context" VALUES(20,'message',12);
INSERT INTO "memory_response_context" VALUES(20,'message',13);
INSERT INTO "memory_response_context" VALUES(20,'message',14);
INSERT INTO "memory_response_context" VALUES(20,'message',15);
INSERT INTO "memory_response_context" VALUES(20,'message',16);
INSERT INTO "memory_response_context" VALUES(20,'message',17);
INSERT INTO "memory_response_context" VALUES(20,'message',18);
INSERT INTO "memory_response_context" VALUES(20,'message',19);
INSERT INTO "memory_response_context" VALUES(22,'message',1);
INSERT INTO "memory_response_context" VALUES(22,'message',3);
INSERT INTO "memory_response_context" VALUES(22,'message',4);
INSERT INTO "memory_response_context" VALUES(22,'message',5);
INSERT INTO "memory_response_context" VALUES(22,'message',6);
INSERT INTO "memory_response_context" VALUES(22,'message',7);
INSERT INTO "memory_response_context" VALUES(22,'message',8);
INSERT INTO "memory_response_context" VALUES(22,'message',9);
INSERT INTO "memory_response_context" VALUES(22,'message',10);
INSERT INTO "memory_response_context" VALUES(22,'message',11);
INSERT INTO "memory_response_context" VALUES(22,'message',12);
INSERT INTO "memory_response_context" VALUES(22,'message',13);
INSERT INTO "memory_response_context" VALUES(22,'message',14);
INSERT INTO "memory_response_context" VALUES(22,'message',15);
INSERT INTO "memory_response_context" VALUES(22,'message',16);
INSERT INTO "memory_response_context" VALUES(22,'message',17);
INSERT INTO "memory_response_context" VALUES(22,'message',18);
INSERT INTO "memory_response_context" VALUES(22,'message',19);
INSERT INTO "memory_response_context" VALUES(22,'message',20);
INSERT INTO "memory_response_context" VALUES(22,'message',21);
INSERT INTO "memory_response_context" VALUES(24,'message',1);
INSERT INTO "memory_response_context" VALUES(24,'message',3);
INSERT INTO "memory_response_context" VALUES(24,'message',5);
INSERT INTO "memory_response_context" VALUES(24,'message',6);
INSERT INTO "memory_response_context" VALUES(24,'message',7);
INSERT INTO "memory_response_context" VALUES(24,'message',8);
INSERT INTO "memory_response_context" VALUES(24,'message',9);
INSERT INTO "memory_response_context" VALUES(24,'message',10);
INSERT INTO "memory_response_context" VALUES(24,'message',11);
INSERT INTO "memory_response_context" VALUES(24,'message',12);
INSERT INTO "memory_response_context" VALUES(24,'message',13);
INSERT INTO "memory_response_context" VALUES(24,'message',14);
INSERT INTO "memory_response_context" VALUES(24,'message',15);
INSERT INTO "memory_response_context" VALUES(24,'message',16);
INSERT INTO "memory_response_context" VALUES(24,'message',17);
INSERT INTO "memory_response_context" VALUES(24,'message',18);
INSERT INTO "memory_response_context" VALUES(24,'message',19);
INSERT INTO "memory_response_context" VALUES(24,'message',20);
INSERT INTO "memory_response_context" VALUES(24,'message',21);
INSERT INTO "memory_response_context" VALUES(24,'message',22);
INSERT INTO "memory_response_context" VALUES(24,'message',23);
INSERT INTO "memory_response_context" VALUES(26,'message',7);
INSERT INTO "memory_response_context" VALUES(26,'message',8);
INSERT INTO "memory_response_context" VALUES(26,'message',9);
INSERT INTO "memory_response_context" VALUES(26,'message',10);
INSERT INTO "memory_response_context" VALUES(26,'message',11);
INSERT INTO "memory_response_context" VALUES(26,'message',12);
INSERT INTO "memory_response_context" VALUES(26,'message',13);
INSERT INTO "memory_response_context" VALUES(26,'message',14);
INSERT INTO "memory_response_context" VALUES(26,'message',15);
INSERT INTO "memory_response_context" VALUES(26,'message',16);
INSERT INTO "memory_response_context" VALUES(26,'message',17);
INSERT INTO "memory_response_context" VALUES(26,'message',18);
INSERT INTO "memory_response_context" VALUES(26,'message',19);
INSERT INTO "memory_response_context" VALUES(26,'message',20);
INSERT INTO "memory_response_context" VALUES(26,'message',21);
INSERT INTO "memory_response_context" VALUES(26,'message',22);
INSERT INTO "memory_response_context" VALUES(26,'message',23);
INSERT INTO "memory_response_context" VALUES(26,'message',24);
INSERT INTO "memory_response_context" VALUES(26,'message',25);
INSERT INTO "memory_response_context" VALUES(28,'message',9);
INSERT INTO "memory_response_context" VALUES(28,'message',10);
INSERT INTO "memory_response_context" VALUES(28,'message',11);
INSERT INTO "memory_response_context" VALUES(28,'message',12);
INSERT INTO "memory_response_context" VALUES(28,'message',13);
INSERT INTO "memory_response_context" VALUES(28,'message',14);
INSERT INTO "memory_response_context" VALUES(28,'message',15);
INSERT INTO "memory_response_context" VALUES(28,'message',16);
INSERT INTO "memory_response_context" VALUES(28,'message',17);
INSERT INTO "memory_response_context" VALUES(28,'message',18);
INSERT INTO "memory_response_context" VALUES(28,'message',19);
INSERT INTO "memory_response_context" VALUES(28,'message',20);
INSERT INTO "memory_response_context" VALUES(28,'message',21);
INSERT INTO "memory_response_context" VALUES(28,'message',22);
INSERT INTO "memory_response_context" VALUES(28,'message',23);
INSERT INTO "memory_response_context" VALUES(28,'message',24);
INSERT INTO "memory_response_context" VALUES(28,'message',25);
INSERT INTO "memory_response_context" VALUES(28,'message',26);
INSERT INTO "memory_response_context" VALUES(28,'message',27);
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
INSERT INTO "memory_summary_items" VALUES('73e9afc3102c1e178b7722e61adf96be',3);
INSERT INTO "memory_summary_items" VALUES('73e9afc3102c1e178b7722e61adf96be',1);
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
INSERT INTO "memory_web_speaker_state" VALUES(1,1,0,27,'current_user','[23, 25, 27]');
CREATE TABLE operation_drafts (id INTEGER PRIMARY KEY AUTOINCREMENT,operation_type TEXT NOT NULL CHECK(operation_type IN ('persona.update','emotion.override','knowledge.import','memory.batch')),parameters_json TEXT NOT NULL,baseline_json TEXT NOT NULL,diff_json TEXT NOT NULL,warnings_json TEXT NOT NULL,token_hash TEXT NOT NULL,expires_at REAL NOT NULL,status TEXT NOT NULL CHECK(status IN ('draft','confirmed','expired','failed')),actor TEXT NOT NULL,created_at REAL NOT NULL);
CREATE TABLE persona_versions (id INTEGER PRIMARY KEY AUTOINCREMENT,parent_id INTEGER,data_json TEXT NOT NULL,created_at REAL NOT NULL);
INSERT INTO "persona_versions" VALUES(1,NULL,'{"core_identity":"受控上下文连续性审计助手","expression_principles":"自然、清晰，先完成用户任务","immutable_rules":"事实须有来源；不得编造身体或共同经历；危险情绪优先现实安全","initiative":0.5,"name":"审计形象C29","relationship_boundaries":"支持现实关系，不鼓励排他依赖","temperature_bias":0.0}',1.79446242155435633659e+09);
CREATE TABLE runtime_turn_ledger (
                request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                status TEXT NOT NULL, created_at REAL NOT NULL);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_bounded_window_turn_001','30974afcbce055aca139ac3be8078a7218809d38a65c3424c8f50c56f8894ece','completed',1.79446242155636453627e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_bounded_window_turn_002','88406d1e1c0333e1481263a56b15e0f2eff8775a897ac09a1d9b7c138b5aeffe','completed',1.79446242185451292992e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_bounded_window_turn_003','c97259fa9df6a654570f5fe615ef830a931c9fb0a10e69bd8e70405bc02acc6c','completed',1.7944624221014473438e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_bounded_window_turn_004','6b4523d126870fce1484ca517e70d147f18f83b96f6bbf541757bb73ca235dbf','completed',1.79446242234128236774e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_bounded_window_turn_005','dd220eba4c3b0bcebc08a85aefed025a48409c354e87224351c61118a43a1e11','completed',1.79446242258730196956e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_bounded_window_turn_006','962f1767ccf9af5e949effb69bff82fde6815db703b7cbd5af702d53a04a9aaa','completed',1.79446242285536479953e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_bounded_window_turn_007','34764526ddb5bb76025c953deaa27301ca4406c2ea64efdd3644a921b3c6ce53','completed',1.79446242311746144296e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_bounded_window_turn_008','e77ffab8563e101e45c4b8fa09d9eeda3869a600feea4eeca3cecccd3dd45eec','completed',1.79446242345187759398e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_bounded_window_turn_009','4689a9a52a46db5e5c2a4bfc6e648df66fed8c41eef378d3b8cc2a2a4a173f81','completed',1.79446242374051427841e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_bounded_window_turn_010','d790ba58236391dbae833bf352bece6e03b55633e1dcbd788166fa0c3c7daaa0','completed',1.79446242404301810257e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_bounded_window_turn_011','b11b4bfc79c449f44f5eb44bc3b2c63d9e5df62ae3a08ba55822aefb4ca940ae','completed',1.79446242436486220355e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_bounded_window_turn_012','3fda47f2d0d9688bf4a45ed0be922f6bf57ceb47e16afc65849349adf4cee561','completed',1.79446242470239353174e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_bounded_window_turn_013','8ac66e164190fbf2562f9bc8a2d80971bb83dcb150353fe92ad5422f82aa0607','completed',1.79446242623407769198e+09);
INSERT INTO "runtime_turn_ledger" VALUES('c29_fault_bounded_window_turn_014','880de8c0d62109defccdc197fb31c5dd1b36b0681d9f8d12c8bb6ad9484a42e0','completed',1.79446242792282986645e+09);
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
INSERT INTO "sqlite_sequence" VALUES('memory_messages',28);
COMMIT;
