"""Mechanical paired evidence; no semantic classifier or automatic release."""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from statistics import median


def summarize(folder):
    lifecycle = json.loads((folder/'lifecycle.json').read_text())
    assert lifecycle['completed'] and lifecycle['failure'] is None
    model = lifecycle['models'][0]; key = model['model_id']
    assert model['provider_exit'] == model['sampler_exit'] == 0 and model['cleanup_passed']
    source = folder/key/'sample/paired-output.json'
    data = json.loads(source.read_text())
    assert data['engineering_passed'] and data['execution_complete'] and data['failure'] is None
    cases = {}
    for row in data['cases']:
        assert row['completed'] and row['error'] is None
        cases.setdefault(row['id'], {})[row['arm']] = row
    assert len(cases) == 12
    pairs = []; arms = {}
    for arm in ['baseline_current_defaults', 'candidate_lab_buffered_review']:
        turns = [t for r in data['cases'] if r['arm'] == arm for t in r['turns']]
        assert len(turns) == 15
        arms[arm] = {'turns': len(turns), 'generation_modes': dict(Counter(t['result']['generation_mode'] for t in turns)),
            'median_first_visible_seconds': median(t['firstVisibleSeconds'] for t in turns),
            'median_complete_seconds': median(t['seconds'] for t in turns),
            'total_final_codepoints': sum(len(t['result']['reply']) for t in turns)}
    for identifier, rows in cases.items():
        baseline, candidate = rows['baseline_current_defaults'], rows['candidate_lab_buffered_review']
        assert len(baseline['turns']) == len(candidate['turns'])
        for index, (a, b) in enumerate(zip(baseline['turns'], candidate['turns'])):
            assert a['input'] == b['input']
            for t in [a, b]:
                assert t['terminal'] == 'result' and t['visible'] == t['result']['reply']
                assert t['result']['trace']['verifier']['available'] is False
                assert not t['reminders'] and not t['result']['tool_calls']
                assert t['stored_assistants'][-1] == t['result']['reply']
            pairs.append({'id': identifier, 'turn': index, 'frame_protocol_label': baseline['frame'],
                'input': a['input'], 'baseline_reply': a['result']['reply'],
                'candidate_native': b.get('native_reply'), 'candidate_final': b['result']['reply'],
                'same_native_bytes': a.get('native_reply') == b.get('native_reply'),
                'same_profile': a['current_profile'] == b['current_profile'],
                'profile': a['current_profile'], 'review': b['result'].get('response_review'),
                'changed': b['result']['generation_mode'] == 'reviewed_response'})
    trace = [json.loads(line) for line in (folder/key/'provider-trace.jsonl').read_text().splitlines()]
    return {'model_id': key, 'sample_sha256': sha256(source.read_bytes()).hexdigest(),
        'candidateFreezeSha256': data['candidateFreezeSha256'], 'engineering_passed': True,
        'scope': 'Mechanical replay and observational timings; separate agent review required. No semantic or production approval.',
        'pairs': pairs, 'arms': arms, 'same_native_pairs': sum(p['same_native_bytes'] for p in pairs),
        'same_profile_pairs': sum(p['same_profile'] for p in pairs),
        'provider_calls': len(trace), 'finish_reasons': dict(Counter(t['finish_reason'] for t in trace)),
        'outcomes': dict(Counter(t['outcome'] for t in trace)),
        'semantic_approved': False, 'production_activation_approved': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True); args = parser.parse_args()
    result = summarize(args.folder)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(result['model_id'], result['same_native_pairs'], 'same native pairs;', result['same_profile_pairs'], 'same profiles')
