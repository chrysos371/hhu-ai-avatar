"""Transport/text description only; these fields never award semantic credit."""
import json


def text_shape(text):
    is_text = isinstance(text, str)
    try:
        parsed = json.loads(text) if is_text else None
        json_object = isinstance(parsed, dict)
    except (ValueError, TypeError, RecursionError):
        json_object = False
    return {'is_text': is_text, 'nonempty': is_text and bool(text.strip()),
        'characters': len(text) if is_text else 0, 'JSON_object': json_object,
        'semantic_correctness': None}
