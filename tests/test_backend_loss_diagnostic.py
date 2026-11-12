import copy
import importlib.util
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('diagnostic',Path(__file__).resolve().parents[1]/'scripts/diagnose_backend_loss.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def probe(empty=True):
    hint='情绪提示。\n';boundary='固定安全边界'
    system=('你是小海。\n'+hint+boundary+'\n'+m.MEMORY_START+'{}\n来源摘要：[]\n'+m.MEMORY_END+m.STYLE_BLOCK+'直接给产物。')
    return {'messages':[{'role':'system','content':system},{'role':'user','content':'甲拒绝参加'},{'role':'assistant','content':'旧的错误回答'},{'role':'user','content':'纠正：甲也负责通知'}],'decision_hint':hint,'empty_memory':empty},boundary


def test_single_factor_variants_keep_exact_history_and_input_immutable():
    p,b=probe();before=copy.deepcopy(p);rows=m.variants(p,b)
    assert p==before and rows['full']==before['messages']
    for name in ['no_emotion_hint','no_general_style','no_empty_memory_scaffold','minimal_safe']:
        assert rows[name][1:]==before['messages'][1:]
        assert b in rows[name][0]['content']
    assert rows['no_emotion_hint'][0]['content']==before['messages'][0]['content'].replace(p['decision_hint'],'',1)
    assert rows['no_general_style'][0]['content']==before['messages'][0]['content'].replace(m.STYLE_BLOCK,'',1)
    assert rows['full_user_history_only'][0]==before['messages'][0]
    assert rows['full_user_history_only'][1:]==[before['messages'][1],before['messages'][3]]


def test_real_memory_is_not_removed_under_empty_scaffold_label():
    p,b=probe(False)
    assert 'no_empty_memory_scaffold' not in m.variants(p,b)


def test_boundary_removal_is_restricted_to_labeled_research_controls():
    p,b=probe();rows=m.variants(p,b)
    for name,messages in rows.items():
        assert (b not in messages[0]['content'])==('research' in name)
        assert messages[-1]==p['messages'][-1]


@pytest.mark.parametrize('remove',[m.STYLE_BLOCK,'固定安全边界','情绪提示。\n'])
def test_unknown_or_changed_prompt_blocks_fail_closed(remove):
    p,b=probe();p['messages'][0]['content']=p['messages'][0]['content'].replace(remove,'')
    with pytest.raises(ValueError):m.variants(p,b)


def test_new_confirmation_and_draft_control_inputs_are_reserved_from_training():
    from avatar.lab.data import evaluation_texts
    texts,hashes=evaluation_texts()
    assert 'evals/companion/backend-loss-reserved-20261111.json' in hashes
    assert any('第二个名字的最后两个字' in text for text in texts)
    assert any('潮汐相伴' in text for text in texts)


def test_reservation_file_cannot_be_mistaken_for_a_real_evaluation_suite(tmp_path):
    from avatar.lab.runner import evaluate
    path=Path(__file__).resolve().parents[1]/'evals/companion/backend-loss-reserved-20261111.json'
    with pytest.raises(ValueError,match='Fixture'):
        evaluate(path,tmp_path/'unused')
