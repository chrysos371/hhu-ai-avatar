"""Align serial raw native calls with application turns; no semantic classifier."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path


def summarize(folder):
    lifecycle = json.loads((folder/'lifecycle.json').read_text())
    assert lifecycle['completed'] and lifecycle['failure'] is None and len(lifecycle['models']) == 1
    model = lifecycle['models'][0]; key = model['model_id']
    assert model['cleanup_passed'] and model['provider_exit'] == model['sampler_exit'] == 0
    source = folder/key/'sample/native-output.json'
    data = json.loads(source.read_text())
    assert data['execution_complete'] and data['engineering_passed'] and data['failure'] is None
    root = Path(__file__).resolve().parents[1]
    protocol_path = root/data['protocol']; protocol = json.loads(protocol_path.read_text())
    assert sha256(protocol_path.read_bytes()).hexdigest() == data['sourceSha256'][data['protocol']]
    expected = [case for case in protocol['cases'] if case['partition'] == 'development']
    assert [case['id'] for case in data['cases']] == [case['id'] for case in expected]
    trace = [json.loads(line) for line in (folder/key/'provider-trace.jsonl').read_text().splitlines()]
    assert len(data['warmups']) == 2 and all(not call['analysis'] for call in trace[:2])
    native = iter(call for call in trace[2:] if not call['analysis'])
    rows = []
    for case, specification in zip(data['cases'], expected):
        assert case['completed'] and case['error'] is None
        assert [turn['input'] for turn in case['turns']] == specification['turns']
        for index, turn in enumerate(case['turns']):
            result = turn['result']; mode = result['generation_mode']
            raw = next(native) if mode == 'llm' else None
            if raw: assert raw['messages'][-1] == {'role': 'user', 'content': turn['input']}
            assert turn['terminal'] == 'result' and not result['tool_calls']
            assert len(turn['reminders']) == turn['expected_reminder_count']
            assistants = [item for item in turn['conversation']['items'] if item['role'] == 'assistant']
            assert assistants[-1]['text'] == result['reply']
            if mode == 'llm': assert turn['visible'] == result['reply']
            rows.append({'id': case['id'], 'turn': index, 'protocol_frame': case['frame'], 'input': turn['input'],
                'generation_mode': mode, 'analysis_mode': result['analysis_mode'], 'reply': result['reply'],
                'visible': turn['visible'], 'raw_provider_reply': raw['response'] if raw else None,
                'raw_final_equal': raw['response'] == result['reply'] if raw else None,
                'provider_call_id': raw['id'] if raw else None,
                'speaker_attribution': result['speaker_attribution'], 'profile': turn['current_profile'],
                'reminder_count': len(turn['reminders']), 'reminder': result.get('reminder'),
                'tool_calls': result['tool_calls'], 'seconds': turn['seconds']})
    assert next(native, None) is None
    return {'model_id': key, 'sample_sha256': sha256(source.read_bytes()).hexdigest(),
        'protocol_sha256': sha256(protocol_path.read_bytes()).hexdigest(),
        'scope': 'Mechanical complete native/visible/final/stored alignment and actual side effects; agent span review separate, no semantic release approval',
        'source_sha256': {str(Path(__file__).resolve().relative_to(root)): sha256(Path(__file__).read_bytes()).hexdigest()},
        'turns': rows, 'generation_modes': dict(Counter(row['generation_mode'] for row in rows)),
        'provider_calls': len(trace), 'finish_reasons': dict(Counter(call['finish_reason'] for call in trace)),
        'outcomes': dict(Counter(call['outcome'] for call in trace)), 'elapsed_seconds': data['elapsedSeconds'],
        'semantic_approved': False, 'production_activation_approved': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    result = summarize(args.folder)
    with args.output.open('x') as stream: json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print(result['model_id'], len(result['turns']), 'turns;', result['provider_calls'], 'provider calls;', result['finish_reasons'])
