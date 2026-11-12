"""Copy revision-bound automatic emotion under the shared conversation lock."""
from copy import deepcopy


def automatic_emotion_snapshot(server, memory):
    """Reject unknown/stale automatic values and diagnostics before a read.

    The engine owns its revision. The conversation window's revision may have
    advanced in a cancelled worker's finally without observing the new source.
    Manual expression overrides are independent and remain managed separately.
    """
    with server.state_lock:
        revision = memory.context_revision
        server.emotion.bind_context_revision(revision)
        server.chat_events[:] = [event for event in server.chat_events
            if type(event.get('context_revision')) is int
            and event['context_revision'] == revision]
        state = server.emotion.state
        user = server.emotion.user_state
        return {
            'context': {'instance_id': server.session_id, 'revision': revision},
            'automatic': {'valence': state.valence, 'arousal': state.arousal},
            'user_observation': {'valence': user.valence, 'arousal': user.arousal},
            'label': state.label(),
            'energy': server.emotion.energy,
            'events': deepcopy(server.chat_events),
        }
