import importlib.util
import io
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('real_soak',ROOT/'scripts/evaluate_real_turn_soak.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_sse_terminal_and_visible_deltas_are_preserved_without_hidden_retries():
    stream=io.BytesIO(b'event: status\ndata: {"status":"running"}\n\nevent: text\ndata: {"text":"hello"}\n\nevent: result\ndata: {"reply":"hello"}\n\n')
    kind,result,types,pieces=module.read_events(stream)
    assert kind=='result' and result['reply']=='hello'
    assert types==['status','text','result'] and pieces==['hello']
    with pytest.raises(ValueError):module.read_events(io.BytesIO(b'event: status\ndata: {}\n\n'))


@pytest.mark.parametrize('change',[
    {'generation_mode':'rules_service_error'},
    {'task':None},
    {'reply':'缺少目标文字'},
    {'reply':'原文，测试用户00'},
    {'delivery_check':{'remaining_issues':['missing_literal:x'],'literal_plan_version':'v2'}},
    {'delivery_check':{'remaining_issues':[],'literal_plan_version':'v1'}}])
def test_endurance_rejects_fallback_scope_loss_stale_data_and_protocol_mismatch(change):
    result={'generation_mode':'llm','task':{'required_literals':['原文']},'reply':'原文',
        'delivery_check':{'remaining_issues':[],'literal_plan_version':'v2'},'trace':{'verifier':{'available':False}}}
    with pytest.raises(AssertionError):module.assert_result({'task':True,'all':['原文']},result|change,['测试用户00'])
