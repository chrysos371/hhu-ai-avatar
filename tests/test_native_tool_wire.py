"""Adversarial XML/JSON and opt-in controls without native inference or CUDA."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from avatar.lab.native_tool_wire import ToolWireError, request_tools, adapt_completion

PROTOCOL=Path(__file__).resolve().parents[1]/'evals/interaction/cycle-40/native-tool-wire-protocol.json'
TOOLS=json.loads(PROTOCOL.read_text())['tools']
RAW='<tool_call>\n{"name":"read_reminder_state","arguments":{"reminder_id":1}}\n</tool_call>'


def test_valid_call_keeps_native_stop_separate_from_adapter_finish():
    message,finish=adapt_completion(RAW,'stop',TOOLS,'eval-7')
    assert finish=='tool_calls' and message['content'] is None
    assert message['tool_calls']==[{'id':'call_eval-7','type':'function','function':{'name':'read_reminder_state','arguments':'{"reminder_id":1}'}}]


def test_policy_empty_object_and_outer_whitespace():
    raw=' \n<tool_call>{"name":"read_reminder_delivery_policy","arguments":{}}</tool_call>\t'
    msg,finish=adapt_completion(raw,'stop',TOOLS,'eval-8')
    assert finish=='tool_calls' and msg['tool_calls'][0]['function']['arguments']=='{}'


@pytest.mark.parametrize('text',[RAW[:-1],RAW+RAW,'我来查询。'+RAW,RAW+'\n完成了。',RAW.replace('</tool_call>',''),'</tool_call>',RAW.replace('read_reminder_state','send_email'),RAW.replace('"arguments"','"extra"'),RAW.replace('{"reminder_id":1}','"{\\"reminder_id\\":1}"'),RAW.replace('{"reminder_id":1}','[]'),RAW.replace('{"reminder_id":1}','null'),RAW.replace('"name":"read_reminder_state"','"name":"wrong","name":"read_reminder_state"'),RAW.replace('1}','NaN}'),RAW.replace('1}','Infinity}'),RAW.replace('1}','1,"reminder_id":2}'),RAW.replace('1}','1},"extra":0')])
def test_invalid_raw_never_adapts_to_executable_call(text):
    with pytest.raises(ToolWireError):adapt_completion(text,'stop',TOOLS,'eval-1')


@pytest.mark.parametrize('finish',['length',None,'error'])
def test_truncated_or_failed_native_call_never_adapts(finish):
    with pytest.raises(ToolWireError):adapt_completion(RAW,finish,TOOLS,'eval-1')


@pytest.mark.parametrize('finish',['stop','length'])
def test_plain_text_is_preserved_without_claiming_tool_execution(finish):
    assert adapt_completion('无法确定。',finish,TOOLS,'eval-1')==({'role':'assistant','content':'无法确定。'},finish)


def test_disabled_plain_wire_remains_raw_even_if_it_mentions_xml():
    assert adapt_completion(RAW,'stop',None,'eval-1')==({'role':'assistant','content':RAW},'stop')


def test_wire_syntax_does_not_validate_business_argument_semantics():
    raw=RAW.replace('1}','true,"unknown":"未授权"}')
    message,_=adapt_completion(raw,'stop',TOOLS,'eval-1')
    assert json.loads(message['tool_calls'][0]['function']['arguments'])=={'reminder_id':True,'unknown':'未授权'}
    # Deliberately no executor in this adapter: downstream must enforce schema,
    # original source, permissions and business snapshot independently.


def test_request_is_opt_in_and_does_not_mutate_caller_schemas():
    data={'tools':deepcopy(TOOLS),'messages':[{'role':'user','content':'查一下'}]};before=deepcopy(data)
    with pytest.raises(ToolWireError,match='not enabled'):request_tools(data)
    assert request_tools(data,enabled=True)==TOOLS and data==before


@pytest.mark.parametrize('change',[{'stream':True},{'response_format':{'type':'json_object'}},{'tool_choice':'none'},{'tool_choice':'required'},{'parallel_tool_calls':True},{'parallel_tool_calls':0},{'tools':{}},{'tools':TOOLS*5}])
def test_unsupported_tool_requests_rejected_before_inference(change):
    with pytest.raises(ToolWireError):request_tools({'tools':TOOLS}|change,enabled=True)


@pytest.mark.parametrize('mode',['duplicate','unknown-key','wrong-type','bad-name','no-schema','not-object'])
def test_bad_tool_declarations_are_rejected(mode):
    tools=deepcopy(TOOLS)
    if mode=='duplicate':tools.append(deepcopy(tools[0]))
    elif mode=='unknown-key':tools[0]['function']['unsupported']=True
    elif mode=='wrong-type':tools[0]['type']='custom'
    elif mode=='bad-name':tools[0]['function']['name']='../../escape'
    elif mode=='no-schema':tools[0]['function'].pop('parameters')
    else:tools[0]['function']['parameters']['type']='string'
    with pytest.raises(ToolWireError):request_tools({'tools':tools},enabled=True)


@pytest.mark.parametrize('tools',[None,[]])
def test_ordinary_requests_keep_tools_none(tools):
    assert request_tools({'tools':tools}) is None


@pytest.mark.parametrize('enabled',[False,True])
def test_tool_history_without_current_schemas_is_not_silently_accepted(enabled):
    with pytest.raises(ToolWireError):request_tools({'messages':[{'role':'tool','content':'fixture'}]},enabled=enabled)


def test_followup_requires_opt_in_and_current_registry():
    history=[{'role':'assistant','tool_calls':[{'id':'call_x'}]},{'role':'tool','tool_call_id':'call_x','content':'{}'}]
    with pytest.raises(ToolWireError):request_tools({'tools':TOOLS,'messages':history})
    assert request_tools({'tools':TOOLS,'messages':history},enabled=True)==TOOLS


@pytest.mark.parametrize('content',[{}, {'content':None}])
def test_sdk_omitted_or_null_tool_content_normalizes_without_mutating_wire(content):
    from avatar.lab.native_tool_wire import template_messages
    original={'role':'assistant','tool_calls':[{'id':'call_x'}]}|content
    before=deepcopy(original)
    assert template_messages([original])[0]['content']==''
    assert original==before


def test_existing_plain_template_text_and_defaults_are_unchanged():
    from avatar.lab.native_tool_wire import template_messages
    assert template_messages([{'role':'user','content':'原文。'}])==[{'role':'user','content':'原文。','tool_calls':[],'reasoning_content':None}]


@pytest.mark.parametrize('message',[{'role':'user'},{'role':'system','content':None},{'role':'tool','content':None},{'role':'user','content':{}},{'role':'assistant'}])
def test_missing_ordinary_content_is_not_silently_invented(message):
    from avatar.lab.native_tool_wire import template_messages
    with pytest.raises(ToolWireError):template_messages([message])
