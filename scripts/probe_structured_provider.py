"""Frozen native-provider structure probe, separate from Avatar semantic claims."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import Request, ProxyHandler, build_opener

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = 'evals/interaction/cycle-25/structured-provider-protocol.json'
MODELS = {'qwen3-4b-q4_k_m': 'evals/interaction/cycle-25/model-metadata-4b.json',
          'qwen3-14b-q4_k_m': 'evals/interaction/cycle-25/model-metadata-14b.json'}


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def write(path, value):
    temporary = path.with_suffix(path.suffix + '.part')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    os.replace(temporary, path)


def verify_freeze(path, expected, model, *, root=ROOT):
    raw = path.read_bytes()
    if sha256(raw).hexdigest() != expected:
        raise ValueError('Freeze descriptor identity changed')
    data = json.loads(raw)
    if (data.get('scope') != 'standalone_native_structure_diagnostic' or data.get('backend') != 'cuda'
            or data.get('protocol') != PROTOCOL or model not in data.get('models', []) or model not in MODELS):
        raise ValueError('Frozen execution contract mismatch')
    required = {PROTOCOL, 'scripts/probe_structured_provider.py', 'scripts/serve_local_model_eval.py',
                'src/avatar/gpu_resources.py', 'evals/interaction/cycle-02/model-scale-protocol.json', *MODELS.values()}
    if not required <= data.get('sha256', {}).keys():
        raise ValueError('Frozen inputs incomplete')
    for name, value in data['sha256'].items():
        target = root / name
        if not target.resolve().is_relative_to(root.resolve()) or digest(target) != value:
            raise ValueError('Frozen source changed: ' + name)
    return data


def decode(text):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out: raise ValueError('duplicate JSON property')
            out[key] = value
        return out
    return json.loads(text, object_pairs_hook=unique)


def schema_valid(text, schema):
    """Only the deliberately small preregistered flat-string schema subset."""
    if (schema.get('type') != 'object' or schema.get('additionalProperties') is not False
            or set(schema.get('properties', {})) != set(schema.get('required', []))):
        raise ValueError('Unsupported probe schema')
    properties = schema['properties']
    for rule in properties.values():
        if rule.get('type') != 'string' or set(rule) - {'type', 'const', 'enum'}:
            raise ValueError('Unsupported probe property')
    try: value = decode(text)
    except (ValueError, TypeError): return False
    return (type(value) is dict and set(value) == set(properties)
            and all(type(value[key]) is str
                    and ('const' not in rule or value[key] == rule['const'])
                    and ('enum' not in rule or value[key] in rule['enum'])
                    for key, rule in properties.items()))


def prior_gate(path, expected, prior_sha256):
    if path is None: raise ValueError('14B requires completed same-freeze 4B evidence')
    raw = path.read_bytes()
    if not prior_sha256 or sha256(raw).hexdigest() != prior_sha256:
        raise ValueError('4B evidence identity changed')
    prior = json.loads(raw)
    if (prior.get('freeze_sha256') != expected or prior.get('model_id') != 'qwen3-4b-q4_k_m'
            or not prior.get('completed') or not prior.get('engineering_passed')
            or not prior.get('plain_controls_differ') or not prior.get('cleanup_passed')):
        raise ValueError('14B prior engineering gate not met')
    trace = path.parent / 'provider-trace.jsonl'
    if digest(trace) != prior.get('native_trace_sha256'):
        raise ValueError('4B native trace identity changed')
    rows = prior.get('requests', [])
    calls = [json.loads(line) for line in trace.read_text().splitlines()]
    validate_trace(rows, calls)
    constrained = [r for r in rows if r.get('arm') == 'schema']
    if (len(rows) != 10 or len(constrained) != 4
            or any(not schema_valid(r['reply'], r['request']['response_format']['json_schema']['schema']) for r in constrained)
            or any(r['finish_reason'] != 'stop' for r in rows)):
        raise ValueError('4B raw engineering evidence incomplete')


def validate_trace(rows, calls, *, require_request_identity=False):
    if len(calls) != len(rows): raise ValueError('Native trace count mismatch')
    for row, actual in zip(rows, calls):
        if (actual['id'] != row['provider_call_id'] or actual['messages'] != row['request']['messages']
                or actual['response'] != row['reply'] or actual['stream'] != row['request']['stream']
                or actual['analysis'] != ('response_format' in row['request'])
                or actual['finish_reason'] != row['finish_reason'] or actual['outcome'] != 'completed'):
            raise ValueError('Native trace/request mismatch')
        if require_request_identity:
            response_format = row['request'].get('response_format')
            schema = response_format.get('json_schema', {}).get('schema') if response_format else None
            def canonical(value):
                return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                    separators=(',', ':')).encode()).hexdigest() if value is not None else None
            required = {'request_body_sha256','response_format','response_format_sha256','response_schema_sha256','grammar_enabled'}
            expected_wire = sha256(json.dumps(row['request'], ensure_ascii=False).encode()).hexdigest()
            if (not required <= actual.keys() or row.get('request_sha256') != expected_wire
                    or actual.get('request_body_sha256') != row.get('request_sha256')
                    or 'request_body_sha256' not in actual or 'request_sha256' not in row
                    or actual.get('response_format') != response_format
                    or actual.get('response_format_sha256') != canonical(response_format)
                    or actual.get('response_schema_sha256') != canonical(schema)
                    or actual.get('grammar_enabled') is not ('response_format' in row['request'])):
                raise ValueError('Native request/schema identity mismatch')


def environment(python):
    purelib = Path(subprocess.check_output([str(python), '-c', 'import sysconfig;print(sysconfig.get_path("purelib"))'], text=True).strip())
    libraries = [purelib/'nvidia/cuda_runtime/lib', ROOT.parent/'runtime/gpu-libs/nvidia/cublas/lib',
                 ROOT.parent/'runtime/gpu-libs/nvidia/cudnn/lib']
    env = dict(os.environ)
    env['LD_LIBRARY_PATH'] = ':'.join([str(p) for p in libraries]+([env['LD_LIBRARY_PATH']] if env.get('LD_LIBRARY_PATH') else []))
    return env


def gpu_processes():
    return subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory','--format=csv,noheader,nounits'], text=True)


def request(url, payload):
    raw = json.dumps(payload, ensure_ascii=False).encode()
    req = Request(url + '/chat/completions', data=raw, headers={'Authorization':'Bearer local-eval-only', 'Content-Type':'application/json'})
    started = time.monotonic()
    with build_opener(ProxyHandler({})).open(req, timeout=180) as response:
        body = response.read().decode()
        status = response.status
    events = []
    if payload['stream']:
        for line in body.splitlines():
            if line.startswith('data: ') and line != 'data: [DONE]': events.append(json.loads(line[6:]))
        if 'data: [DONE]' not in body: raise ValueError('SSE warmup did not complete')
        text = ''.join(e['choices'][0]['delta'].get('content','') for e in events)
        identifier = events[0]['id']
        reasons = [e['choices'][0]['finish_reason'] for e in events if e['choices'][0]['finish_reason'] is not None]
        finish = reasons[-1] if reasons else None
    else:
        value = json.loads(body);text=value['choices'][0]['message']['content'];identifier=value['id'];finish=value['choices'][0]['finish_reason']
    return {'request':payload,'request_sha256':sha256(raw).hexdigest(),'status':status,'raw_http_body':body,
            'reply':text,'provider_call_id':identifier,'finish_reason':finish,'seconds':time.monotonic()-started}


def run(args):
    if not __debug__: raise ValueError('Run without Python optimization')
    frozen = verify_freeze(args.freeze, args.expected_freeze_sha256, args.model)
    if args.model == 'qwen3-14b-q4_k_m': prior_gate(args.prior_4b, args.expected_freeze_sha256, args.prior_4b_sha256)
    protocol = json.loads((ROOT/PROTOCOL).read_text())
    if len(protocol['cases']) != 4 or len(protocol['arm_orders']) != 4 or len(protocol['warmup']) != 2:
        raise ValueError('Unexpected fixed protocol dimensions')
    for case in protocol['cases']: schema_valid('{}', case['schema'])
    if any(sorted(order) != ['plain','schema'] for order in protocol['arm_orders']): raise ValueError('Invalid paired order')
    args.output.mkdir(parents=True, exist_ok=False)
    registry = json.loads((ROOT/'evals/interaction/cycle-02/model-scale-protocol.json').read_text())
    specification = next(m for m in registry['models'] if m['model_id'] == args.model)
    ready=args.output/'provider-ready.json';trace=args.output/'provider-trace.jsonl'
    model_path=ROOT/'models'/args.model.replace('-q4_k_m','-gguf')/specification['file']
    command=[str(args.provider_python),str(ROOT/'scripts/serve_local_model_eval.py'),'--model',str(model_path),
             '--model-key',args.model,'--metadata',str(ROOT/MODELS[args.model]),'--ready',str(ready),'--trace',str(trace),'--backend','cuda']
    report={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'model_id':args.model,
            'scope':protocol['scope'],'freeze_sha256':args.expected_freeze_sha256,'frozen_inputs':frozen,
            'provider_command':command,'trace_identity_required':frozen.get('trace_identity_required',False),'requests':[],'completed':False,'failure':None,'engineering_passed':False,
            'semantic_approved':False,'cleanup_passed':False,'provider_pid':None,'provider_exit':None}
    def save():write(args.output/'probe.json',report)
    save();process=None;started=time.monotonic()
    def verify():return verify_freeze(args.freeze,args.expected_freeze_sha256,args.model)
    try:
        verify()
        with (args.output/'provider.log').open('x') as log:
            process=subprocess.Popen(command,cwd=ROOT,env=environment(args.provider_python),stdout=log,stderr=subprocess.STDOUT)
            report['provider_pid']=process.pid;save()
            while True:
                if process.poll() is not None: raise RuntimeError('Provider exited before ready: '+str(process.returncode))
                if ready.exists():
                    try:metadata=json.loads(ready.read_text())
                    except json.JSONDecodeError:metadata=None
                    if metadata is not None:break
                time.sleep(.1)
            if (metadata['pid'] != process.pid or metadata['backend'] != 'cuda'
                    or metadata['model_sha256'] != specification['sha256']
                    or metadata['provider_source_sha256'] != frozen['sha256']['scripts/serve_local_model_eval.py']):
                raise ValueError('Provider runtime identity mismatch')
            report['provider_ready']=metadata;save();print('Ready',args.model,'GPU',metadata['chosen_gpu']['index'],metadata['chosen_gpu']['uuid'],flush=True)
            for index,warm in enumerate(protocol['warmup']):
                verify();payload={'model':args.model,**protocol['generation'],'stream':warm['stream'],'messages':[{'role':'user','content':warm['text']}]}
                row=request(metadata['url'],payload);row.update(role='warmup',warmup_index=index);report['requests'].append(row);save()
            for case,order in zip(protocol['cases'],protocol['arm_orders']):
                for arm in order:
                    verify();payload={'model':args.model,**protocol['generation'],'messages':case['messages']}
                    if arm=='schema':payload['response_format']={'type':'json_schema','json_schema':{'name':case['id'],'strict':True,'schema':case['schema']}}
                    row=request(metadata['url'],payload);row.update(role=case['role'],case=case['id'],arm=arm,
                        declared_schema_valid=schema_valid(row['reply'],case['schema']))
                    if 'expected_draft' in case:
                        try: content=decode(row['reply'])['draft'] if arm=='schema' else row['reply']
                        except (ValueError,KeyError,TypeError):content=None
                        row['exact_literal_match']=content==case['expected_draft']
                    report['requests'].append(row);save();print(case['id'],arm,'stop',row['finish_reason'],'schema',row['declared_schema_valid'],flush=True)
        verify()
    except BaseException as error:
        report['failure']=repr(error);raise
    finally:
        if process is not None:
            if process.poll() is None:process.terminate()
            try:report['provider_exit']=process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill();report['provider_exit']=process.wait();report['forced_cleanup']=True
            for _ in range(100):
                raw=gpu_processes()
                if not any(line.split(',')[0].strip()==str(process.pid) for line in raw.splitlines()):break
                time.sleep(.1)
            report['gpu_processes_after']=raw
            report['cleanup_passed']=report['provider_exit']==0 and not any(line.split(',')[0].strip()==str(process.pid) for line in raw.splitlines())
        report['seconds']=time.monotonic()-started;save()
    try:
        calls=[json.loads(line) for line in trace.read_text().splitlines()]
        validate_trace(report['requests'], calls, require_request_identity=report['trace_identity_required'])
        report['native_trace_sha256'] = digest(trace)
        for row in report['requests']: row['native_trace_matched'] = True
    except BaseException as error:
        report['failure'] = repr(error); save(); raise
    constrained=[r for r in report['requests'] if r.get('arm')=='schema']
    controls=[r for r in report['requests'] if r.get('arm')=='plain' and r['case'] in ('const_sentinel','status_enum_adversarial')]
    report['plain_controls_differ']=len(controls)==2 and all(not r['declared_schema_valid'] for r in controls)
    report['engineering_passed']=(len(report['requests'])==10 and len(constrained)==4 and all(r['declared_schema_valid'] for r in constrained)
        and all(r['finish_reason']=='stop' and actual['outcome']=='completed' for r,actual in zip(report['requests'],calls)) and report['cleanup_passed'])
    verify();report['completed']=True;report['schema_arms_passed']=sum(r['declared_schema_valid'] for r in constrained);save()
    print('Completed structural probe',report['schema_arms_passed'],'/4; semantic approval false; cleanup',report['cleanup_passed'],flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--model',required=True,choices=list(MODELS));parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--freeze',required=True,type=Path);parser.add_argument('--expected-freeze-sha256',required=True)
    parser.add_argument('--provider-python',required=True,type=Path);parser.add_argument('--prior-4b',type=Path);parser.add_argument('--prior-4b-sha256')
    run(parser.parse_args())
