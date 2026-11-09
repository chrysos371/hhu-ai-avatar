"""JSON schema for cognitive analysis; source evidence is still checked separately."""

ANALYSIS_RESPONSE_FORMAT = {
    'type': 'json_schema',
    'json_schema': {
        'name': 'avatar_cognitive_analysis', 'strict': True,
        'schema': {
            'type': 'object', 'additionalProperties': False,
            'required': ['emotion', 'facts'],
            'properties': {
                'emotion': {
                    'type': 'object', 'additionalProperties': False,
                    'required': ['valence', 'arousal'],
                    'properties': {key: {'type': 'number'} for key in ('valence', 'arousal')},
                },
                'facts': {
                    'type': 'array', 'items': {
                        'type': 'object', 'additionalProperties': False,
                        'required': ['type', 'content', 'evidence', 'subject', 'modality', 'temporal'],
                        'properties': {key: {'type': 'string'} for key in
                                       ('type', 'content', 'evidence', 'subject', 'modality', 'temporal')},
                    },
                },
            },
        },
    },
}
