import importlib.util
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
SPEC = importlib.util.spec_from_file_location('three_arm', ROOT / 'scripts/evaluate_companion_three_arms.py')
module = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(module)


def test_backend_memory_and_calls_are_isolated(tmp_path):
    def generate(messages, limit):
        return dict(reply='{"emotion":{"valence":0,"arousal":0},"facts":[]}' if limit == 512 else '收到。', truncated=False)
    first = tmp_path / 'a'; second = tmp_path / 'b'; first.mkdir(); second.mkdir()
    one = module.backend_dialogue(dict(id='one', category='memory', turns=['我叫南栀。']), module.LocalTrace(generate), first)
    two = module.backend_dialogue(dict(id='two', category='memory', turns=['你好。']), module.LocalTrace(generate), second)
    assert any('南栀' in str(m) for m in one['turns'][0]['memories'])
    assert not two['turns'][0]['memories']
    assert [c['kind'] for c in two['turns'][0]['calls']] == ['analysis', 'reply']
    assert not two['turns'][0]['analysis_fallback']
    assert all('南栀' not in str(c['messages']) for c in two['turns'][0]['calls'])


def test_blind_triples_have_all_arms_and_blank_human_scores(tmp_path):
    suite = module.load_suite(ROOT / 'evals/companion/lora-dev-20.json')
    results = {arm: {c['id']: dict(turns=[dict(user='test', reply='reply', truncated=False)]) for c in suite['cases']} for arm in module.ARMS}
    module.write_blind(suite, results, tmp_path)
    key = json.loads((tmp_path / 'unblinding-key.json').read_text())
    assert len(key) == 20
    for row in key.values(): assert {row[s] for s in 'XYZ'} == set(module.ARMS)
    text = (tmp_path / 'blind-review.md').read_text()
    assert all(arm not in text for arm in module.ARMS)
    assert all(not row.split(',')[1] for row in (tmp_path / 'review.csv').read_text(encoding='utf-8-sig').splitlines()[1:])


@pytest.mark.parametrize('change', [None, 'dtype', 'user', 'truncated'])
def test_raw_cache_accepts_only_matching_complete_reference(tmp_path, change):
    suite = dict(cases=[dict(id='test', turns=['hello'])])
    manifest = dict(suite_sha256='frozen', model={'revision': 'fixed'}, raw_system=module.SYSTEM,
                    reply_max_new_tokens=256, do_sample=False, enable_thinking=False,
                    dtype='bfloat16', attention='sdpa')
    rows = dict(raw_base={'test': dict(turns=[dict(user='hello', reply='reply', truncated=False)])})
    if change == 'dtype': manifest['dtype'] = 'float32'
    if change == 'user': rows['raw_base']['test']['turns'][0]['user'] = 'different'
    if change == 'truncated': rows['raw_base']['test']['turns'][0]['truncated'] = True
    (tmp_path / 'manifest.json').write_text(json.dumps(manifest))
    path = tmp_path / 'raw-results.json'; path.write_text(json.dumps(rows))
    if change:
        with pytest.raises(ValueError): module.load_raw_reference(path, suite, {'revision':'fixed'}, 'frozen')
    else:
        assert module.load_raw_reference(path, suite, {'revision':'fixed'}, 'frozen') == rows['raw_base']
