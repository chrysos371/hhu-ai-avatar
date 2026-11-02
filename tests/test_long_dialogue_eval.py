import importlib.util
from pathlib import Path


def load_script():
    path = Path(__file__).resolve().parents[1] / 'scripts' / 'evaluate_long_dialogue.py'
    spec = importlib.util.spec_from_file_location('evaluate_long_dialogue', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scenario_covers_real_40_turn_dialogue_and_deletion():
    module = load_script()
    cases = module.SCENARIO
    assert len(cases) == 40
    assert len({c['id'] for c in cases}) == 40
    assert any(c.get('action') == 'restart' for c in cases)
    assert any(c.get('action') == 'correct' for c in cases)
    assert any(c.get('action') == 'forget' for c in cases)
    assert next(i for i,c in enumerate(cases) if c['id'] == 'context-probe') >= 20


def test_generated_answer_score_rejects_stale_fact_even_with_correct_keyword():
    module = load_script()
    assert not module.score('你叫小舟，以前叫小岚', [['小舟']], ['小岚'])['passed']
    assert module.score('你叫小舟', [['小舟']], ['小岚'])['passed']
    assert not module.score('你从未告诉过我名字', [], [], abstain=True)['passed']
    assert module.score('我目前不记得你的名字', [], [], abstain=True)['passed']
