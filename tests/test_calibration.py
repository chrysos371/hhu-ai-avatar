import pytest

from avatar.brain.calibration import evaluate_thresholds


class Encoder:
    model_id = 'fixture'
    def embed(self, text):
        return {'q': [1, 0], 'exact': [1, 0], 'near': [1, 1],
                'wrong': [.8, .6], 'unrelated': [0, 1]}[text]


def test_threshold_report_measures_false_positives_and_recall():
    pairs = [{'query': 'q', 'memory': text, 'relevant': label} for text, label in
             [('exact', True), ('near', True), ('wrong', False), ('unrelated', False)]]
    report = evaluate_thresholds(pairs, Encoder(), [.5, .75, .85])
    low, middle, high = report['thresholds']
    assert low['tp'] == 2 and low['fp'] == 1
    assert low['recall'] == 1
    assert low['false_positive_rate'] == .5
    assert middle['tp'] == 1 and middle['fp'] == 1
    assert high['precision'] == 1 and high['recall'] == .5
    assert report['recommended_threshold'] == .5


@pytest.mark.parametrize('pairs', [[], [{'query': 'q', 'memory': 'exact', 'relevant': 'false'}],
    [{'query': 'q', 'memory': 'exact', 'relevant': True}]])
def test_calibration_requires_valid_positive_and_negative_labels(pairs):
    with pytest.raises(ValueError):
        evaluate_thresholds(pairs, Encoder(), [.5])
