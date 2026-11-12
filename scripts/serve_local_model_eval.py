"""Loopback-only serial evaluation provider; not a production server.
Run in the isolated llama-cpp-python environment. CPU requires explicit selection.
"""
import argparse
from copy import deepcopy
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
import re
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from avatar.gpu_resources import select_available_gpu
from avatar.lab.native_tool_wire import ToolWireError, request_tools, adapt_completion


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def load_registry(path=None, *, expected_sha256=None, root=None):
    """Bind a selected project registry before any model or CUDA construction."""
    root = ROOT if root is None else Path(root)
    default = root / 'evals/interaction/cycle-02/model-scale-protocol.json'
    path = default if path is None else Path(path).resolve()
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Model registry must be inside the project')
    if path.resolve() != default.resolve() and expected_sha256 is None:
        raise ValueError('Explicit override requires expected registry SHA')
    raw = path.read_bytes(); identity = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and identity != expected_sha256:
        raise ValueError('Registry identity changed')
    registry = json.loads(raw)
    if not isinstance(registry, dict): raise ValueError('Invalid model registry')
    models = registry.get('models')
    if not isinstance(models, list) or not models:
        raise ValueError('Invalid model registry')
    ids = set()
    for model in models:
        if (not isinstance(model, dict) or not isinstance(model.get('model_id'), str)
                or not re.fullmatch(r'[a-z0-9_-]+', model['model_id']) or model['model_id'] in ids
                or not isinstance(model.get('file'), str) or Path(model['file']).name != model['file']
                or not model['file'].endswith('.gguf')
                or not isinstance(model.get('sha256'), str) or not re.fullmatch(r'[0-9a-f]{64}', model['sha256'])
                or not isinstance(model.get('revision'), str) or not re.fullmatch(r'[0-9a-f]{40}', model['revision'])
                or type(model.get('required_free_mib')) is not int or model['required_free_mib'] <= 0):
            raise ValueError('Invalid or duplicate model specification')
        if 'metadata' in model:
            name = model['metadata']
            if (not isinstance(name, str) or Path(name).is_absolute()
                    or not (root / name).resolve().is_relative_to(root.resolve())):
                raise ValueError('Model metadata must be a project input')
        ids.add(model['model_id'])
    return registry, identity, path


def trace_request_metadata(data, raw_request, *, grammar_enabled):
    """Record wire and canonical format identities without inferring call role."""
    response_format = deepcopy(data.get('response_format'))
    schema = None
    if isinstance(response_format, dict):
        description = response_format.get('json_schema')
        if isinstance(description, dict):
            schema = description.get('schema')
    def canonical(value):
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
            separators=(',', ':')).encode()).hexdigest() if value is not None else None
    return {'request_body_sha256': hashlib.sha256(raw_request).hexdigest(),
            'response_format': response_format,
            'response_format_sha256': canonical(response_format),
            'response_schema_sha256': canonical(schema),
            'grammar_enabled': grammar_enabled}


def validate_cpu_headroom(evidence, required_free_mib):
    affinity = evidence['affinity']; memory = evidence['memory_available_mib']; load = evidence['load_average']
    if (not isinstance(affinity, list) or len(affinity) < 4 or len(set(affinity)) != len(affinity)
            or any(type(index) is not int or index < 0 for index in affinity)
            or type(memory) is not int or memory < required_free_mib
            or len(load) != 3 or any(not math.isfinite(value) or value < 0 for value in load)
            or load[0] > len(affinity)-4):
        raise RuntimeError('Insufficient measured CPU/memory headroom for explicit four-thread inference')
    return {**evidence, 'n_threads': 4, 'required_free_mib': required_free_mib}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--model-key', default='qwen3-4b-q4_k_m')
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--ready', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--backend', choices=['cuda', 'cpu_explicit'], default='cuda')
    parser.add_argument('--enable-tools', action='store_true', help='isolated nonstreaming single-call XML adapter; default disabled')
    parser.add_argument('--registry', type=Path)
    parser.add_argument('--expected-registry-sha256')
    args = parser.parse_args()
    if args.ready.exists() or args.trace.exists():
        raise ValueError('Use new evidence paths')
    registry, registry_sha256, registry_path = load_registry(args.registry, expected_sha256=args.expected_registry_sha256)
    metadata_raw = args.metadata.read_bytes()
    metadata_sha256 = hashlib.sha256(metadata_raw).hexdigest()
    metadata = json.loads(metadata_raw)
    specification = next(item for item in registry['models'] if item['model_id'] == args.model_key)
    if specification.get('metadata') and args.metadata.resolve() != (ROOT / specification['metadata']).resolve():
        raise ValueError('Metadata path differs from selected registry')
    assert metadata['path'] == specification['file']
    assert metadata['lfs']['oid'] == specification['sha256']
    if 'revision' in metadata:
        assert metadata['revision'] == specification['revision']

    digest = sha(args.model)
    assert digest == specification['sha256']
    snapshot = subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.free,utilization.gpu',
        '--format=csv,noheader,nounits'],text=True)
    inventory = []
    for line in snapshot.splitlines():
        index, uid, free, utilization = (part.strip() for part in line.split(','))
        inventory.append({'index':int(index),'uuid':uid,'free_mib':int(free),'utilization_percent':int(utilization)})
    requested_mask = os.environ.get('CUDA_VISIBLE_DEVICES')
    cpu_resources = None
    if args.backend == 'cuda':
        chosen = select_available_gpu(inventory,required_free_mib=specification['required_free_mib'],visible_mask=requested_mask)
        os.environ['CUDA_VISIBLE_DEVICES'] = chosen['uuid']
    else:
        memory = Path('/proc/meminfo').read_text().splitlines()
        available = int(next(line.split()[1] for line in memory if line.startswith('MemAvailable:')))//1024
        cpu_resources = validate_cpu_headroom({'affinity': sorted(os.sched_getaffinity(0)),
            'memory_available_mib': available, 'load_average': list(os.getloadavg())},
            max(24576, specification['required_free_mib']))
        chosen = None
        os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
    from llama_cpp import Llama, LlamaGrammar, llama_supports_gpu_offload
    from jinja2 import Environment, StrictUndefined
    from importlib.metadata import version
    if args.backend == 'cuda' and not llama_supports_gpu_offload():
        raise RuntimeError('GPU offload unavailable; refusing silent CPU fallback')
    start = time.monotonic()
    model_options = dict(model_path=str(args.model), n_gpu_layers=-1 if args.backend == 'cuda' else 0,
        n_ctx=8192, n_batch=256, n_threads=4, seed=42, flash_attn=True, verbose=True)
    if args.backend == 'cpu_explicit':
        model_options.update(offload_kqv=False, n_threads_batch=4)
    model = Llama(**model_options)
    load_seconds = time.monotonic()-start
    allocated = []
    raw_processes = subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,used_memory',
        '--format=csv,noheader,nounits'], text=True)
    for line in raw_processes.splitlines():
        pid, used = (part.strip() for part in line.split(','))
        if int(pid) == os.getpid():
            allocated.append(int(used))
    if args.backend == 'cuda' and (not allocated or max(allocated) < 1024):
        raise RuntimeError('No substantial model allocation on GPU; refusing unverified offload')
    if args.backend == 'cpu_explicit' and allocated:
        raise RuntimeError('Explicit CPU provider unexpectedly allocated GPU memory')

    if sha(registry_path) != registry_sha256 or sha(args.metadata) != metadata_sha256:
        raise ValueError('Registry or metadata changed while loading model')

    # Use the official template embedded in the hash-verified GGUF, with explicit thinking=False.
    template_text = model.metadata['tokenizer.chat_template']
    env = Environment(undefined=StrictUndefined)
    def fail(message):
        raise ValueError(message)
    env.globals['raise_exception'] = fail
    template = env.from_string(template_text)
    guard = threading.Lock()
    counter = [0]
    trace = args.trace.open('x')
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self,*args):
            pass
        def send_json(self,status,data):
            body=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def do_POST(self):
            if self.path!='/v1/chat/completions' or self.headers.get('Authorization')!='Bearer local-eval-only':
                self.send_json(403,{'error':{'message':'evaluation endpoint only'}});return
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=1024*1024:
                self.send_json(413,{'error':{'message':'invalid request length'}});return
            raw_request=self.rfile.read(length)
            data=json.loads(raw_request)
            try:
                tools=request_tools(data,enabled=args.enable_tools)
            except ToolWireError as error:
                self.send_json(400,{'error':{'message':str(error)}});return
            with guard:
                counter[0]+=1
                identifier=f'eval-{counter[0]}'
                messages=[{'tool_calls': [], 'reasoning_content': None} | message for message in data['messages']]
                prompt=template.render(messages=messages,tools=tools,add_generation_prompt=True,
                    enable_thinking=False,bos_token='',eos_token='')
                assert prompt.endswith('<think>\n\n</think>\n\n')
                grammar=None
                if data.get('response_format'):
                    response=data['response_format']
                    schema=response.get('json_schema',{}).get('schema')
                    if schema is None:
                        self.send_json(400,{'error':{'message':'schema required'}});return
                    grammar=LlamaGrammar.from_json_schema(json.dumps(schema),verbose=False)
                started=time.monotonic();first=None;parts=[];outcome='completed';usage=None;finish_reason=None
                stream=bool(data.get('stream'))
                wire_message=None;wire_finish_reason=None
                try:
                    if stream:
                        self.send_response(200);self.send_header('Content-Type','text/event-stream')
                        self.send_header('Connection','close');self.end_headers();self.close_connection=True
                    response=model.create_completion(prompt=prompt,temperature=0,seed=42,
                        max_tokens=min(int(data.get('max_tokens',512)),512),stop=['<|im_end|>','<|endoftext|>'],
                        stream=stream,grammar=grammar,repeat_penalty=1.0,top_p=1.0,top_k=0)
                    if stream:
                        try:
                            for chunk in response:
                                if chunk['choices'][0]['finish_reason'] is not None:
                                    finish_reason=chunk['choices'][0]['finish_reason']
                                text=chunk['choices'][0]['text'];parts.append(text)
                                if first is None and text:first=time.monotonic()-started
                                obj={'id':identifier,'object':'chat.completion.chunk','model':args.model_key,
                                    'choices':[{'index':0,'delta':{'content':text},'finish_reason':chunk['choices'][0]['finish_reason']}]}
                                self.wfile.write(('data: '+json.dumps(obj,ensure_ascii=False)+'\n\n').encode());self.wfile.flush()
                            self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
                        finally:
                            response.close()
                    else:
                        text=response['choices'][0]['text'];parts=[text];usage=response.get('usage')
                        finish_reason=response['choices'][0]['finish_reason']
                        first=time.monotonic()-started
                        wire_message,wire_finish_reason=adapt_completion(text,finish_reason,tools,identifier)
                        self.send_json(200,{'id':identifier,'object':'chat.completion','model':args.model_key,
                            'choices':[{'index':0,'message':wire_message,
                                'finish_reason':wire_finish_reason}],'usage':usage})
                except (BrokenPipeError,ConnectionResetError):
                    outcome='client_disconnected'
                except Exception as exc:
                    outcome=type(exc).__name__
                    if not stream:self.send_json(500,{'error':{'message':'local inference failed'}})
                finally:
                    # Legacy analysis is a grammar flag, not a semantic role.
                    trace.write(json.dumps({**trace_request_metadata(data, raw_request, grammar_enabled=grammar is not None),
                        'id':identifier,'stream':stream,'analysis':grammar is not None,
                        'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'messages':data['messages'],
                        'response':''.join(parts),'first_seconds':first,'total_seconds':time.monotonic()-started,
                        'usage':usage,'finish_reason':finish_reason,'outcome':outcome,
                        'tool_adapter_enabled':args.enable_tools,'tools':tools,
                        'wire_message':wire_message,'wire_finish_reason':wire_finish_reason},ensure_ascii=False)+'\n');trace.flush()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=True
    args.ready.write_text(json.dumps({'url':f'http://127.0.0.1:{server.server_port}/v1',
        'model_sha256':digest,'model_revision':specification['revision'],'model_id':args.model_key,
        'registry_sha256':registry_sha256, 'registry_path':str(registry_path.relative_to(ROOT)),
        'metadata_sha256':metadata_sha256, 'metadata_path':str(args.metadata.resolve()),
        'gguf_general_name':model.metadata.get('general.name'),
        'template_sha256':hashlib.sha256(template_text.encode()).hexdigest(),
        'backend':args.backend, 'cpu_resources':cpu_resources,
        'gpu_snapshot_before':snapshot,'chosen_gpu':chosen,'requested_visible_devices':requested_mask,
        'effective_visible_devices':os.environ['CUDA_VISIBLE_DEVICES'],
        'resource_selector_sha256':sha('src/avatar/gpu_resources.py'),
        'configuration':{'n_gpu_layers':model_options['n_gpu_layers'],'n_threads':4,
            **({'offload_kqv':False, 'n_threads_batch':4} if args.backend == 'cpu_explicit' else {}),
            'n_ctx':8192,'n_batch_prompt_tokens':256,'concurrent_sequences':1,
            'temperature':0,'seed':42,'max_tokens_cap':512,'thinking':False,'flash_attention':True},
        'llama_cpp_python':version('llama-cpp-python'),'load_seconds':load_seconds,
        'provider_source_sha256':sha(__file__),'tool_adapter_enabled':args.enable_tools,
        'tool_adapter_source_sha256':sha(ROOT/'src/avatar/lab/native_tool_wire.py'),
        'process_gpu_mib_after_load':allocated,
        'pid':os.getpid()},indent=2)+'\n')
    stopping=threading.Event()
    def shutdown(signum, frame):
        if not stopping.is_set():
            stopping.set()
            threading.Thread(target=server.shutdown,daemon=True).start()
    for signum in (signal.SIGINT,signal.SIGTERM):signal.signal(signum,shutdown)
    try:server.serve_forever()
    finally:
        server.server_close()
        with guard:
            trace.close();model.close()


if __name__=='__main__':main()
