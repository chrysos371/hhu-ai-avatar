import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('targeted_oracles',Path(__file__).resolve().parents[1]/'scripts/targeted14b_oracles.py')
o=importlib.util.module_from_spec(spec);spec.loader.exec_module(o)


def test_wrong_budget_cannot_pass_by_format_alone():
    a=o.check_case('confirm-budget',['电池组数：3\n总花费：105元'])
    assert a['exactly_two_nonempty_lines'] and not a['strict_numeric_pair']
    b=o.check_case('confirm-budget',['电池组数\n2\n总花费90元'])
    assert b['strict_numeric_pair'] and not b['exactly_two_nonempty_lines']


def test_json_numeric_type_format_and_values_are_separate():
    expected={'usable':882,'card':294}
    a=o.json_object('```json\n{"usable":882,"card":294}\n```',expected)
    assert a['values_correct'] and not a['whole_reply_json']
    assert not o.json_object('{"usable":"882","card":294}',expected)['values_correct']
    assert not o.json_object('{"usable":882,"card":true}',expected)['values_correct']


def test_draft_oracle_uses_each_arms_own_actual_draft():
    a=o.check_case('accept-new-draft-chain',['松林里的灯','未刊·松林里的灯','松林里的灯·未刊'])
    assert a['five_chinese_characters'] and a['prefix_exact'] and a['suffix_exact']
    b=o.check_case('accept-new-draft-chain',['松林里的灯','未刊·松林里的灯','松林中的灯·未刊'])
    assert not b['suffix_exact']
