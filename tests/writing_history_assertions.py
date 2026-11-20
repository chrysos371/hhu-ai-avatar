"""Check private model context separately from public original message storage."""
import json

from avatar.brain.writing_history import PREFIX


def assert_writing_context(memory, reply):
    raw = memory.get_short_term()[-1]['content']
    assert raw.startswith(PREFIX)
    data = json.loads(raw[len(PREFIX):])
    assert data['reply'] == reply
    assert data['historical_artifact_only'] is data['untrusted_data_not_instructions'] is True
    assert data['real_execution_verified'] is data['user_identity_asserted'] is False
    assert memory._conn.execute("SELECT content FROM memory_messages WHERE role='assistant' "
        'ORDER BY id DESC LIMIT 1').fetchone()[0] == reply
    return data
