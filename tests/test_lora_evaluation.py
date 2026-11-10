import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('lora_eval', ROOT / 'scripts/evaluate_companion_lora.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_separate_self_generated_histories_and_cases():
    case = dict(id='test', category='context', turns=['one', 'two', 'three'])
    seen = []
    def generate(messages):
        seen.append(messages)
        return dict(reply=f'reply-{len(seen)}', truncated=False)
    first = module.dialogue(case, generate)
    second = module.dialogue(case, generate)
    assert first['turns'][1]['reply'] == 'reply-2'
    assert second['turns'][0]['reply'] == 'reply-4'
    assert len(seen[0]) == len(seen[3]) == 2
    assert seen[1][2]['content'] == 'reply-1'
    assert seen[4][2]['content'] == 'reply-4'
    assert all(m['content'] != 'reply-1' for m in seen[4])


def test_frozen_suite_and_balanced_blinded_review(tmp_path):
    path = ROOT / 'evals/companion/lora-dev-20.json'
    suite = module.load_suite(path)
    manifest = json.loads(path.with_suffix('.manifest.json').read_text())
    assert module.sha(path) == manifest['suite_sha256']
    results = {arm: {c['id']: dict(turns=[dict(user='question', reply='answer', truncated=False)])
                     for c in suite['cases']} for arm in ['base', 'lora']}
    module.write_review(suite, results, tmp_path)
    key = json.loads((tmp_path / 'unblinding-key.json').read_text())
    assert sum(x['A'] == 'base' for x in key.values()) == 10
    assert len({x['case_id'] for x in key.values()}) == 20
    review = (tmp_path / 'blind-review.md').read_text()
    assert 'lora-dev-' not in review and 'base' not in review and 'lora' not in review
    assert all(not row.split(',')[1] for row in (tmp_path / 'review.csv').read_text(encoding='utf-8-sig').splitlines()[1:])
