"""Rebuild the matched fake-method HTTP result from original SSE, API and SQL."""
import json
from pathlib import Path
from revision_common import BASE, ROOT, digest, verify_historical_binding
from verify_shared_affect import parse_events

WORK = BASE / '审计/工作目录/001-自动情绪版本失效'
result = {'scope': 'independent_raw_matched_controlled_http_reconstruction',
    'actual_native_model_or_gpu': False, 'new_app_or_http_calls': 0, 'phases': {}}
probe_sha = None
for phase in ('before', 'after'):
    evidence = WORK / ('controlled-http-' + phase + '.json')
    report = json.loads(evidence.read_text())
    version = json.loads((WORK / (phase + '-control-version.json')).read_text())
    verify_historical_binding({'source_ref': version['source_ref'], 'sha256': version['files_sha256']})
    assert digest(evidence) == version['evidence_sha256']
    current_probe = version['files_sha256'][str((BASE / '审计/probe_revision_http.py').relative_to(ROOT))]
    if probe_sha is not None:
        assert current_probe == probe_sha
    probe_sha = current_probe
    assert report['completed'] and report['failure'] is None and report['fake_model_methods']
    assert report['actual_loopback_app_http'] and not report['actual_llm_or_gpu']
    assert len(report['cases']) == 6
    submitted = completed = cancelled = forgotten = retained_cancel = 0
    for case in report['cases']:
        assert case['complete']
        kind = case['case']
        observed = [json.loads(call['raw_response'])['data'] for call in case['http'] if call['route'] == '/emotion']
        labels = ['initial_emotion'] + (['before_boundary_emotion'] if kind == 'forget_completed_source' else [])
        labels += ['after_boundary_emotion', 'after_neutral_emotion']
        assert observed == [case[label] for label in labels]
        assert all(call['status'] >= 200 and call['status'] < 300 for call in case['http'])
        for turn in case['turns']:
            submitted += 1
            events = parse_events(turn['raw_sse'])
            assert events[-1]['event'] == turn['terminal']
            if turn['terminal'] == 'result':
                completed += 1
                assert events[-1]['data'] == turn['result']
                assert ''.join(event['data']['text'] for event in events if event['event'] == 'text') == turn['result']['reply']
            else:
                assert turn['terminal'] == 'cancelled'
                cancelled += 1
        sql = case['sql_after_boundary']
        if kind == 'forget_completed_source':
            source = case['boundary_control']['source_message_id']
            assert sql['revision'] == 1
            assert next(row for row in sql['memory_messages'] if row['id'] == source)['content'] == '[redacted]'
            forgotten += 1
        else:
            assert kind == 'cancel_after_analysis' and sql['revision'] == 0
            assert not sql['memory_chat_results'] and not any(row['role'] == 'assistant' for row in sql['memory_messages'])
            retained_cancel += 1
        nonzero = lambda state: any(abs(state[axis]) > 1e-9 for axis in ('valence', 'arousal'))
        expected = phase == 'before' or kind == 'cancel_after_analysis'
        assert nonzero(case['after_boundary_emotion']['user_observation']) == expected
        assert nonzero(case['after_boundary_emotion']['automatic']) == expected
        assert nonzero(case['after_neutral_emotion']['automatic']) == expected
        assert not nonzero(case['after_neutral_emotion']['user_observation'])
    assert (submitted, completed, cancelled, forgotten, retained_cancel) == (12, 9, 3, 3, 3)
    result['phases'][phase] = {'evidence_sha256': digest(evidence), 'historical_sources_verified': True,
        'submitted': submitted, 'result': completed, 'cancelled': cancelled,
        'forget_cases': forgotten, 'cancel_positive_controls': retained_cancel,
        'forget_retained_old_state': 3 if phase == 'before' else 0}
result['same_probe_sha256'] = probe_sha
result['verified'] = True
with (WORK / 'controlled-http-independent.json').open('x') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print('Verified before/after raw matched HTTP: each12 submitted/9result/3cancelled; forget3 stale→0, cancel3 retained.')
