"""Probe admission/data checks only: these tests do not call a model or GPU."""
from hashlib import sha256
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from probe_structured_provider import schema_valid, verify_freeze, prior_gate, validate_trace, PROTOCOL, MODELS

SCHEMA={'type':'object','properties':{'status':{'type':'string','const':'未执行'}},'required':['status'],'additionalProperties':False}

@pytest.mark.parametrize('text, valid', [('{"status":"未执行"}',True),('{"status":"已发送"}',False),
    ('{"status":"未执行","extra":1}',False),('{"status":"已发送","status":"未执行"}',False),
    ('{"status":null}',False),('[]',False),('{"status":"未执行"} trailing',False)])
def test_strict_small_schema_and_duplicate_properties(text, valid):
    assert schema_valid(text,SCHEMA) is valid


def test_unsupported_schema_cannot_be_silently_accepted():
    with pytest.raises(ValueError,match='Unsupported'):schema_valid('{}',dict(SCHEMA,additionalProperties=True))
    schema=dict(SCHEMA,properties={'status':{'type':'string','maxLength':1}})
    with pytest.raises(ValueError,match='Unsupported'):schema_valid('{}',schema)


@pytest.fixture
def frozen(tmp_path):
    names={PROTOCOL,'scripts/probe_structured_provider.py','scripts/serve_local_model_eval.py','src/avatar/gpu_resources.py',
           'evals/interaction/cycle-02/model-scale-protocol.json',*MODELS.values()}
    inputs={}
    for name in names:
        p=tmp_path/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('fixture-only')
        inputs[name]=sha256(p.read_bytes()).hexdigest()
    document={'scope':'standalone_native_structure_diagnostic','backend':'cuda','protocol':PROTOCOL,
              'models':list(MODELS),'sha256':inputs}
    path=tmp_path/'frozen.json';path.write_text(json.dumps(document))
    return tmp_path,path,document


def test_freeze_validates_raw_identity_before_parsing(frozen):
    root,path,document=frozen;expected=sha256(path.read_bytes()).hexdigest()
    assert verify_freeze(path,expected,next(iter(MODELS)),root=root)==document
    path.write_text('{malformed')
    with pytest.raises(ValueError,match='identity changed'):verify_freeze(path,expected,next(iter(MODELS)),root=root)


@pytest.mark.parametrize('change',['backend','model','input'])
def test_freeze_rejects_execution_or_source_mismatch(frozen,change):
    root,path,document=frozen
    if change=='backend':document['backend']='cpu_explicit'
    elif change=='model':document['models']=[]
    else:(root/'src/avatar/gpu_resources.py').write_text('changed')
    path.write_text(json.dumps(document));expected=sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):verify_freeze(path,expected,next(iter(MODELS)),root=root)


def test_14b_does_not_accept_mutated_or_self_report_only_4b_flags(tmp_path):
    path=tmp_path/'probe.json';path.write_text(json.dumps({'completed':True,'engineering_passed':True}))
    with pytest.raises(ValueError,match='identity changed'):prior_gate(path,'freeze','wrong-sha')
    with pytest.raises(ValueError,match='gate not met'):prior_gate(path,'freeze',sha256(path.read_bytes()).hexdigest())
    with pytest.raises(ValueError,match='requires completed'):prior_gate(None,'freeze',None)


def trace_pair():
    row={'provider_call_id':'eval-1','request':{'messages':[{'role':'user','content':'fixture'}],'stream':False},
         'reply':'fixture reply','finish_reason':'stop'}
    actual={'id':'eval-1','messages':row['request']['messages'],'response':'fixture reply',
            'stream':False,'analysis':False,'finish_reason':'stop','outcome':'completed'}
    return row,actual


def test_matching_trace_data_is_accepted():
    row,actual=trace_pair();validate_trace([row],[actual])


@pytest.mark.parametrize('field',['response','messages','stream','analysis','finish_reason','outcome'])
def test_native_binding_rejects_relabelled_or_changed_trace(field):
    row,actual=trace_pair();actual[field]='changed'
    with pytest.raises(ValueError,match='trace/request mismatch'):validate_trace([row],[actual])


def identity_pair():
    row,actual=trace_pair()
    row['request']['response_format']={'type':'json_schema','json_schema':{'schema':SCHEMA}}
    row['request_sha256']=sha256(json.dumps(row['request'],ensure_ascii=False).encode()).hexdigest()
    def canonical(value):return sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',', ':')).encode()).hexdigest()
    actual.update(analysis=True,grammar_enabled=True,request_body_sha256=row['request_sha256'],
                  response_format=row['request']['response_format'],response_format_sha256=canonical(row['request']['response_format']),
                  response_schema_sha256=canonical(SCHEMA))
    return row,actual


def test_new_trace_identity_binds_wire_format_schema_and_grammar():
    row,actual=identity_pair();validate_trace([row],[actual],require_request_identity=True)


@pytest.mark.parametrize('field',['request_body_sha256','response_format','response_format_sha256','response_schema_sha256','grammar_enabled'])
def test_new_trace_identity_rejects_wrong_or_missing_fields(field):
    row,actual=identity_pair();actual[field]='changed'
    with pytest.raises(ValueError,match='request/schema identity mismatch'):
        validate_trace([row],[actual],require_request_identity=True)


def test_historical_trace_requires_explicit_historical_mode():
    row,actual=trace_pair();validate_trace([row],[actual])
    with pytest.raises(ValueError,match='request/schema identity mismatch'):
        validate_trace([row],[actual],require_request_identity=True)


@pytest.mark.parametrize('field',['request_body_sha256','response_format','response_format_sha256','response_schema_sha256','grammar_enabled'])
def test_new_trace_cannot_omit_identity_fields(field):
    row,actual=identity_pair();actual.pop(field)
    with pytest.raises(ValueError,match='request/schema identity mismatch'):
        validate_trace([row],[actual],require_request_identity=True)


def test_new_trace_recomputes_declared_wire_hash():
    row,actual=identity_pair();row['request_sha256']=actual['request_body_sha256']='forged'
    with pytest.raises(ValueError,match='request/schema identity mismatch'):
        validate_trace([row],[actual],require_request_identity=True)
