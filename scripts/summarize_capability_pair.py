"""Mechanical prompt pairs, preserving full text for separate source review."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from statistics import median


def summarize(folder, native_summary=None):
    lifecycle = json.loads((folder/'lifecycle.json').read_text())
    assert lifecycle['completed'] and lifecycle['failure'] is None and len(lifecycle['models']) == 1
    model = lifecycle['models'][0]; key = model['model_id']
    assert model['provider_exit'] == model['sampler_exit'] == 0 and model['cleanup_passed']
    source = folder/key/'sample/paired-output.json'; data = json.loads(source.read_text())
    assert data['execution_complete'] and data['engineering_passed'] and data['failure'] is None
    root = Path(__file__).resolve().parents[1]
    protocol = json.loads((root/'evals/interaction/cycle-19/capability-output-protocol.json').read_text())
    expected = {case['id']: case for case in protocol['cases'] if case['partition'] == data['partition']}
    baseline = 'baseline_current_defaults'; candidate = 'candidate_lab_capability_prompt'
    cases = {}
    for case in data['cases']:
        assert case['completed'] and case['error'] is None
        assert case['id'] in expected and [turn['input'] for turn in case['turns']] == expected[case['id']]['turns']
        assert case['arm'] not in cases.setdefault(case['id'], {})
        cases[case['id']][case['arm']] = case
    assert set(cases) == set(expected) and all(set(arms) == {baseline, candidate} for arms in cases.values())
    archive = json.loads(native_summary.read_text()) if native_summary else None
    if archive: assert archive['model_id'] == key
    previous = {(turn['id'], turn['turn']): turn for turn in archive['turns']} if archive else {}
    pairs = []
    for ident in expected:
        for index, (a, b) in enumerate(zip(cases[ident][baseline]['turns'], cases[ident][candidate]['turns'])):
            for turn in (a, b):
                assert turn['terminal'] == 'result' and turn['stored_assistants'][-1] == turn['result']['reply']
                assert not turn['result']['tool_calls'] and len(turn['reminders']) == turn['expected_reminder_count']
                if turn['result']['generation_mode'] == 'llm':
                    assert turn['visible'] == turn['result']['reply'] == turn['native_provider']['response']
            def reminders(turn):
                return [{key: row[key] for key in ('id', 'title', 'due_at', 'status')} for row in turn['reminders']]
            old = previous.get((ident, index))
            pairs.append({'id': ident, 'turn': index, 'protocol_frame': expected[ident]['frame'], 'input': a['input'],
                'baseline_reply': a['result']['reply'], 'candidate_reply': b['result']['reply'],
                'baseline_generation_mode': a['result']['generation_mode'], 'candidate_generation_mode': b['result']['generation_mode'],
                'baseline_native_call_id': a['native_provider']['id'] if a['native_provider'] else None,
                'candidate_native_call_id': b['native_provider']['id'] if b['native_provider'] else None,
                'same_reply': a['result']['reply'] == b['result']['reply'],
                'same_profile': a['current_profile'] == b['current_profile'],
                'baseline_profile': a['current_profile'], 'candidate_profile': b['current_profile'],
                'same_reminder_state': reminders(a) == reminders(b),
                'baseline_reminders': reminders(a), 'candidate_reminders': reminders(b),
                'baseline_same_as_prior_native': a['result']['reply'] == old['reply'] if old else None})
    trace = [json.loads(line) for line in (folder/key/'provider-trace.jsonl').read_text().splitlines()]
    arms = {}
    for arm in (baseline, candidate):
        turns = [turn for case in data['cases'] if case['arm'] == arm for turn in case['turns']]
        arms[arm] = {'turns': len(turns), 'generation_modes': dict(Counter(turn['result']['generation_mode'] for turn in turns)),
            'median_complete_seconds': median(turn['seconds'] for turn in turns)}
    return {'model_id': key, 'partition': data['partition'], 'sample_sha256': sha256(source.read_bytes()).hexdigest(),
        'candidate_freeze_sha256': data['candidateFreezeSha256'],
        'source_sha256': {str(Path(__file__).resolve().relative_to(root)): sha256(Path(__file__).read_bytes()).hexdigest()},
        'scope': 'Mechanical native/visible/final/stored and side-effect comparison, observational timing only; separate complete span review, no semantic approval',
        'pairs': pairs, 'arms': arms, 'provider_calls': len(trace),
        'finish_reasons': dict(Counter(call['finish_reason'] for call in trace)),
        'outcomes': dict(Counter(call['outcome'] for call in trace)),
        'elapsed_seconds': data['elapsedSeconds'], 'prior_summary_sha256': sha256(native_summary.read_bytes()).hexdigest() if native_summary else None,
        'semantic_approved': False, 'production_activation_approved': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--native-summary', type=Path); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); result = summarize(args.folder, args.native_summary)
    with args.output.open('x') as stream: json.dump(result, stream, ensure_ascii=False, indent=2); stream.write('\n')
    print(result['model_id'], len(result['pairs']), 'pairs;', result['provider_calls'], 'provider calls;', result['finish_reasons'])
