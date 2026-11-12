"""One turn execution boundary for web and transport adapters."""
import time
import uuid
import json


def make_trace(avatar, result, *, channel, character_id=None, elapsed_ms=0):
    llm = avatar.llm
    store = avatar._persona_store()
    persona = store.current_persona() if store else None
    return {
        'schema_version': 1, 'turn_id': uuid.uuid4().hex,
        'channel': channel, 'character_id': character_id,
        'model': getattr(llm, 'model', None),
        'model_profile': getattr(llm, 'profile_id', 'default'),
        'persona_version': persona['id'] if persona else None,
        'recalled_ids': result.get('recalled_ids', []),
        'reply_context': result.get('reply_context'),
        'context_check': result.get('context_check'),
        'generation_mode': result.get('generation_mode'),
        'knowledge_sources': result.get('knowledge_sources', []),
        'strategy': result.get('strategy'), 'boundary': result.get('boundary'),
        'skills': getattr(avatar,'skills_audit',None),
        'tool_calls': result.get('tool_calls', []),
        'protocol_fallbacks': list(getattr(llm, 'protocol_fallbacks', [])),
        'analysis_status': getattr(avatar, 'analysis_status', 'unknown'),
        'reply_degraded': getattr(avatar, 'reply_degraded', False),
        'total_ms': round(elapsed_ms, 2),
    }


def execute_turn(avatar, text, *, channel='web', character_id=None, **options):
    started = time.monotonic()
    fallbacks = getattr(avatar.llm, 'protocol_fallbacks', None)
    if fallbacks is not None:
        fallbacks.clear()
    result = avatar.respond(text, **options)
    result['trace'] = make_trace(avatar, result, channel=channel,
                               character_id=character_id,
                               elapsed_ms=(time.monotonic()-started)*1000)
    with avatar.memory.transaction():
        db = avatar.memory._conn
        db.execute('CREATE TABLE IF NOT EXISTS conversation_turn_traces (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, created_at REAL NOT NULL, data TEXT NOT NULL)')
        db.execute('INSERT INTO conversation_turn_traces VALUES(?,?,?,?)',
                   (result['trace']['turn_id'],avatar.session_id,time.time(),json.dumps(result['trace'],ensure_ascii=False)))
        db.execute('DELETE FROM conversation_turn_traces WHERE id NOT IN (SELECT id FROM conversation_turn_traces ORDER BY created_at DESC LIMIT 200)')
    return result
