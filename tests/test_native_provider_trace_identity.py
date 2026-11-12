"""Native provider trace provenance without loading llama or allocating a GPU."""
from hashlib import sha256
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import serve_local_model_eval as provider


def encode(data):return json.dumps(data,ensure_ascii=False).encode()
def formatted(name='reply_plan'):
    return {'type':'json_schema','json_schema':{'name':name,'strict':True,'schema':{'type':'object','properties':{'draft':{'type':'string'}},'required':['draft'],'additionalProperties':False}}}


def test_actual_wire_digest_and_canonical_schema_are_distinct_evidence():
    data={'messages':[{'role':'user','content':'审计'}],'response_format':formatted()}
    raw=encode(data);pretty=json.dumps(data,ensure_ascii=False,indent=2).encode()
    a=provider.trace_request_metadata(data,raw,grammar_enabled=True)
    b=provider.trace_request_metadata(data,pretty,grammar_enabled=True)
    assert a['request_body_sha256']==sha256(raw).hexdigest()
    assert a['request_body_sha256']!=b['request_body_sha256']
    assert a['response_schema_sha256']==b['response_schema_sha256']
    assert a['response_format']==data['response_format'] and a['grammar_enabled'] is True


def test_schema_order_does_not_change_canonical_identity():
    fmt=formatted();other=json.loads(json.dumps(fmt));schema=other['json_schema']['schema'];other['json_schema']['schema']=dict(reversed(list(schema.items())))
    a=provider.trace_request_metadata({'response_format':fmt},encode(fmt),grammar_enabled=True)
    b=provider.trace_request_metadata({'response_format':other},encode(other),grammar_enabled=True)
    assert a['response_schema_sha256']==b['response_schema_sha256']
    assert a['response_format_sha256']==b['response_format_sha256']


def test_format_name_is_recorded_without_guessing_request_role():
    a=provider.trace_request_metadata({'response_format':formatted('analysis')},b'wire-a',grammar_enabled=True)
    b=provider.trace_request_metadata({'response_format':formatted('draft_reply')},b'wire-b',grammar_enabled=True)
    assert a['response_schema_sha256']==b['response_schema_sha256']
    assert a['response_format_sha256']!=b['response_format_sha256']
    assert a['response_format']['json_schema']['name']=='analysis'
    assert 'request_role' not in a and 'request_role' not in b


@pytest.mark.parametrize('fmt',[None,{}])
def test_absent_or_empty_format_does_not_infer_grammar(fmt):
    data={} if fmt is None else {'response_format':fmt}
    row=provider.trace_request_metadata(data,encode(data),grammar_enabled=False)
    assert row['grammar_enabled'] is False and row['response_schema_sha256'] is None
    assert row['response_format']==fmt


def test_schema_content_change_changes_identity():
    fmt=formatted();data={'response_format':fmt}
    old=provider.trace_request_metadata(data,encode(data),grammar_enabled=True)
    fmt['json_schema']['schema']['properties']['draft']['type']='integer'
    new=provider.trace_request_metadata(data,encode(data),grammar_enabled=True)
    assert old['response_schema_sha256']!=new['response_schema_sha256']


def test_trace_keeps_a_snapshot_when_caller_later_changes_its_dictionary():
    fmt=formatted();row=provider.trace_request_metadata({'response_format':fmt},encode(fmt),grammar_enabled=True)
    fmt['json_schema']['name']='changed'
    assert row['response_format']['json_schema']['name']=='reply_plan'
