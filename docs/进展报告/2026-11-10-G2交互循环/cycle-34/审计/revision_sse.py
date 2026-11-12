"""Audit delta validation for native LLM and canonical local control replies."""


def validate_result_delta(result,events):
    reply=result.get('reply');mode=result.get('generation_mode')
    if not isinstance(reply,str) or not reply.strip():raise ValueError('Empty or malformed final reply')
    parts=[event['data']['text'] for event in events if event['event']=='text']
    if any(not isinstance(part,str) for part in parts):raise ValueError('Malformed text delta')
    pieces=''.join(parts)
    if mode=='llm':
        if pieces!=reply:raise ValueError('Native LLM deltas do not match final result')
    elif mode=='rules_speaker_control':
        if pieces not in ('',reply):raise ValueError('Canonical rule deltas only partially match final result')
    else:raise ValueError('Unexpected generation mode in registered native workflow')
    return {'text_event_count':len(parts),'text_delivery':'text_and_result' if pieces else 'canonical_result_only','generation_mode':mode}
