import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('companion_eval', ROOT / 'scripts/evaluate_companion.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


def test_pilot_coverage_and_isolated_deletion(tmp_path):
    suite = runner.load_suite(ROOT / 'evals/companion/pilot.json')
    assert len(suite['cases']) == 15
    assert all(sum(c['category'] == cat for c in suite['cases']) == 5
               for cat in ('memory', 'emotion', 'boundary'))
    model = runner.TracedModel(None, 'http://localhost:11434/v1', 'unused', 1, smoke=True)
    rows = runner.run(suite, 'smoke', model, tmp_path)
    deleted = next(r for r in rows if r['id'] == 'memory-05')
    assert all(deleted['backend_checks'].values())
    assert len(rows) == 15 and all(len(r['turns']) == 3 for r in rows)
    assert list(tmp_path.iterdir()) == []


def test_model_errors_are_not_scored_as_success(tmp_path):
    class Broken:
        available = True
        def __init__(self):
            self.calls = []
        def chat(self, messages, **kwargs):
            self.calls.append({'error': 'ConnectionError'})
            raise ConnectionError('fixture')
    suite = runner.load_suite(ROOT / 'evals/companion/pilot.json')
    suite['cases'] = suite['cases'][:1]
    row = runner.run(suite, 'avatar', Broken(), tmp_path)[0]
    assert row['status'] == 'error'
    assert all(t['degraded'] for t in row['turns'])


def test_direct_model_marks_management_case_not_applicable(tmp_path):
    suite = runner.load_suite(ROOT / 'evals/companion/pilot.json')
    suite['cases'] = [next(c for c in suite['cases'] if c.get('before_last_action'))]
    model = runner.TracedModel(None, 'http://localhost:11434/v1', 'unused', 1, smoke=True)
    assert runner.run(suite, 'model', model, tmp_path)[0]['status'] == 'not_applicable'
    assert model.calls == []


def test_candidate_preserves_pilot_and_covers_100_distinct_scenarios():
    pilot = runner.load_suite(ROOT / 'evals/companion/pilot.json')
    suite = runner.load_suite(ROOT / 'evals/companion/candidate-100.json')
    assert len(suite['cases']) == 100
    assert suite['frozen'] is False
    assert suite['pilot_rubric_approved'] is True
    assert {category: sum(c['category'] == category for c in suite['cases'])
            for category in ('memory', 'emotion', 'boundary')} == {
                'memory': 35, 'emotion': 35, 'boundary': 30}
    indexed = {c['id']: c for c in suite['cases']}
    for case in pilot['cases']:
        assert all(indexed[case['id']][key] == value for key, value in case.items())
    assert len({tuple(c['turns']) for c in suite['cases']}) == 100
    assert max(len(c['turns']) for c in suite['cases']) > 10
    assert all(c['family'] and c['difficulty'] for c in suite['cases'])


def test_real_transport_records_length_limit_without_hiding_it():
    from types import SimpleNamespace
    model = runner.TracedModel(None, 'http://localhost:11434/v1', 'unused', 1, smoke=True)
    class Response:
        choices = [SimpleNamespace(finish_reason='length', message=SimpleNamespace(content='未完成'))]
        def model_dump(self, **kwargs):
            return {'choices': [{'finish_reason': 'length'}]}
    model.smoke = False
    model.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kwargs: Response())))
    assert model.chat([{'role': 'user', 'content': '测试'}]) == '未完成'
    assert model.calls[0]['truncated'] is True


def test_checkpoint_receives_completed_cases(tmp_path):
    suite = runner.load_suite(ROOT / 'evals/companion/pilot.json')
    suite['cases'] = suite['cases'][:2]
    model = runner.TracedModel(None, 'http://localhost:11434/v1', 'unused', 1, smoke=True)
    snapshots = []
    runner.run(suite, 'model', model, tmp_path,
               on_case=lambda cases: snapshots.append([c['id'] for c in cases]))
    assert snapshots == [['memory-01'], ['memory-01', 'memory-02']]


def test_override_records_requested_and_actual_temperature():
    model = runner.TracedModel(None, 'http://localhost:11434/v1', 'unused', 1,
                               smoke=True, temperature_override=0)
    model.chat([{'role': 'user', 'content': '你好'}], temperature=0.9)
    assert model.calls[0]['requested_temperature'] == 0.9
    assert model.calls[0]['temperature'] == 0


def test_invalid_analysis_is_recorded_as_fallback(tmp_path):
    class InvalidAnalysis:
        available = True
        def __init__(self):
            self.calls = []
        def chat(self, messages, **kwargs):
            self.calls.append({'reply': '非JSON'})
            return '非JSON'
    suite = runner.load_suite(ROOT / 'evals/companion/pilot.json')
    suite['cases'] = suite['cases'][:1]
    row = runner.run(suite, 'avatar', InvalidAnalysis(), tmp_path)[0]
    assert row['status'] == 'error'
    assert all(t['degraded'] and '认知分析失败，回退规则分析' in t['fallback_events']
               for t in row['turns'])
