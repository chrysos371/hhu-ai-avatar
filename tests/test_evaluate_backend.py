"""Exercise the evaluation runner with real Avatar/storage and a local transport double."""
import importlib.util
import json
from pathlib import Path

import pytest

from avatar.main import Avatar

SPEC = importlib.util.spec_from_file_location(
    'evaluate_backend', Path(__file__).resolve().parents[1] / 'scripts' / 'evaluate_backend.py')
evaluation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(evaluation)


class LocalTransport:
    available = True

    def __init__(self, model, base_url, timeout):
        self.calls = []

    def chat(self, messages, temperature=.8, max_tokens=768):
        content = (json.dumps({'emotion': {}, 'facts': []}) if temperature == 0
                   else '你叫小岚。')
        self.calls.append(dict(stage='analysis' if temperature == 0 else 'reply',
                               content=content, seconds=0.001))
        return content


def test_eval_separates_raw_model_completeness_and_admitted_abstention(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation, 'LocalChat', LocalTransport)
    report = evaluation.evaluate('transport-fixture', '', 'unused', tmp_path / 'report.json', 1)
    metrics = report['summary']['fact_extraction']
    assert metrics['positive_cases'] >= 2
    assert metrics['abstention_cases'] >= 3
    assert metrics['raw_model']['completeness'] == 0
    assert metrics['admitted']['completeness'] == 1
    assert metrics['admitted']['abstention_false_writes'] == 0
    assert metrics['admitted']['expected_abstention_successes'] == metrics['abstention_cases']
    assert all('raw_model_facts' in row and 'admitted_facts' in row for row in report['fact_cases'])
    assert report['checks']['forgotten_reply_has_no_stale_name'] is False
    assert report['summary']['answers']['expected_abstention_successes'] == 0
    assert report['summary']['answers']['false_name_answers'] == 1
    assert report['summary']['passed'] < report['summary']['total']
    assert (tmp_path / 'report.md').exists()


def test_eval_records_missing_forgetting_prerequisite_as_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluation, 'LocalChat', LocalTransport)
    original = Avatar._store_fact

    def skip_names(self, fact):
        if fact['type'] != '名字':
            original(self, fact)

    monkeypatch.setattr(Avatar, '_store_fact', skip_names)
    report = evaluation.evaluate('transport-fixture', '', 'unused', tmp_path / 'missing.json', 1)
    for key in ('manual_correction', 'forgotten_versions_removed',
                'forgotten_context_cleared', 'forgotten_reply_has_no_stale_name'):
        assert report['checks'][key] is False
    assert any(row['scenario'] == 'after-forgetting' and row['prerequisite_met'] is False
               for row in report['answer_cases'])


@pytest.mark.parametrize('reply,success', [
    ('当前记忆里没有你的名字，我不知道。', True),
    ('我不记得你的名字了。', True),
    ('你叫小舟吧，我不确定。', False),
    ('你好呀。', False),
    ('你之前从未告诉过我名字。', False),
])
def test_abstention_requires_uncertainty_without_stale_name_or_false_history(reply, success):
    score = evaluation.score_answer(reply, expected=[], forbidden=['阿岚', '小岚', '小舟'],
                                    abstention=True)
    assert score['correct'] is success


def test_latency_medians_separate_conversation_and_labeled_extraction_workloads():
    rows = [dict(scenario='memory-evolution', seconds=10),
            dict(scenario='after-forgetting', seconds=20),
            dict(scenario='labeled-extraction/explicit', seconds=1),
            dict(scenario='labeled-extraction/hypothesis', seconds=2)]
    score = evaluation.summarize_latencies(rows)
    assert score['median_turn_seconds'] == 6
    assert score['conversation_median_seconds'] == 15
    assert score['extraction_case_median_seconds'] == 1.5
