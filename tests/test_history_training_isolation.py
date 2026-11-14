import json

from avatar.lab import data


def test_actual_history_cases_are_hashed_and_rejected_from_training():
    protected, hashes = data.evaluation_texts()
    names = {47: 'native-history-cases.json', 48: 'typed-history-cases.json',
        49: 'minimal-history-cases.json', 50: 'natural-history-cases.json'}
    for cycle, name in names.items():
        relative = f'evals/interaction/cycle-{cycle}/{name}'
        assert relative in hashes
        for case in json.loads((data.PROJECT / relative).read_text())['cases']:
            for field in ('query_text', 'followup_text'):
                text = case[field]
                assert text in protected
                row = data.normalize_dialogue('controlled', 'train', case['id'],
                    [text, '这是一段仅供验证训练隔离的受控参考回复。'])
                accepted, rejected = data.screen_candidates([row], protected,
                    source_policy={'controlled': {'use': 'experimental-sft', 'language': 'zh'}})
                assert not accepted and 'eval_overlap' in rejected[0]['reasons']


def test_named_inputs_do_not_collect_expected_answers_or_untyped_metadata(tmp_path):
    suite = {'cases': [{'turns': ['旧回合'], 'query_text': '新查询', 'followup_text': '新追问',
        'expected': '这是评分参考，不是模型输入', 'notes': '这是审阅备注'},
        {'query_text': None, 'followup_text': 5}, {'query_text': ' ', 'followup_text': ''}, 7]}
    (tmp_path / 'suite.json').write_text(json.dumps(suite, ensure_ascii=False))
    texts, hashes = data.evaluation_texts(tmp_path)
    assert texts == ['旧回合', '新查询', '新追问']
    assert len(hashes) == 1


def test_unrelated_message_draft_remains_eligible_and_old_fixture_stays_protected():
    protected, _ = data.evaluation_texts()
    policy = {'controlled': {'language': 'zh', 'use': 'experimental-sft'}}
    unrelated = data.normalize_dialogue('controlled', 'train', 'unrelated',
        ['帮我写一条短信文案，提醒同伴带上指南针去观察山顶的星座。',
         '请带上指南针，今晚一起去山顶观察星座。'])
    accepted, rejected = data.screen_candidates([unrelated], protected, source_policy=policy)
    assert accepted and not rejected
    old = data.normalize_dialogue('controlled', 'train', 'legacy',
        ['我喜欢喝可乐。请帮我写一封信。', '这是一段仅供验证训练隔离的受控参考回复。'])
    accepted, rejected = data.screen_candidates([old], protected, source_policy=policy)
    assert not accepted and 'eval_overlap' in rejected[0]['reasons']
