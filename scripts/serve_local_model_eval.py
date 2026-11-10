"""Loopback-only serial evaluation provider; not a production server.
Run in the isolated llama-cpp-python CUDA environment. No runtime model swap.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading
import time


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--metadata', type=Path, required=True)
    parser.add_argument('--ready', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    args = parser.parse_args()
    if args.ready.exists() or args.trace.exists():
        raise ValueError('Use new evidence paths')
    metadata = json.loads(args.metadata.read_text())
    digest = sha(args.model)
    assert digest == metadata['lfs']['oid']
    snapshot = subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.free,utilization.gpu',
        '--format=csv,noheader,nounits'],text=True)
    available = []
    for line in snapshot.splitlines():
        index, uid, free, utilization = (part.strip() for part in line.split(','))
        if int(free)>=16384 and int(utilization)<=85:
            available.append((int(free),-int(utilization),uid,int(index)))
    if not available:
        raise RuntimeError('No GPU meets current headroom gate')
    chosen = max(available)
    os.environ['CUDA_VISIBLE_DEVICES'] = chosen[2]
    from llama_cpp import Llama, LlamaGrammar, llama_supports_gpu_offload
    from jinja2 import Environment, StrictUndefined
    from importlib.metadata import version
    if not llama_supports_gpu_offload():
        raise RuntimeError('GPU offload unavailable; refusing silent CPU fallback')
    start = time.monotonic()
    model = Llama(model_path=str(args.model),n_gpu_layers=-1,n_ctx=8192,n_batch=256,
        n_threads=4,seed=42,flash_attn=True,verbose=True)
    load_seconds = time.monotonic()-start
    allocated = []
    raw_processes = subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,used_memory',
        '--format=csv,noheader,nounits'], text=True)
    for line in raw_processes.splitlines():
        pid, used = (part.strip() for part in line.split(','))
        if int(pid) == os.getpid():
            allocated.append(int(used))
    if not allocated or max(allocated) < 1024:
        raise RuntimeError('No substantial model allocation on GPU; refusing unverified offload')

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
            data=json.loads(self.rfile.read(length))
            if data.get('tools'):
                self.send_json(400,{'error':{'message':'tool evaluation not enabled'}});return
            with guard:
                counter[0]+=1
                identifier=f'eval-{counter[0]}'
                prompt=template.render(messages=data['messages'],tools=None,add_generation_prompt=True,
                    enable_thinking=False,bos_token='',eos_token='')
                assert prompt.endswith('<think>\n\n</think>\n\n')
                grammar=None
                if data.get('response_format'):
                    response=data['response_format']
                    schema=response.get('json_schema',{}).get('schema')
                    if schema is None:
                        self.send_json(400,{'error':{'message':'schema required'}});return
                    grammar=LlamaGrammar.from_json_schema(json.dumps(schema),verbose=False)
                started=time.monotonic();first=None;parts=[];outcome='completed';usage=None
                stream=bool(data.get('stream'))
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
                                text=chunk['choices'][0]['text'];parts.append(text)
                                if first is None and text:first=time.monotonic()-started
                                obj={'id':identifier,'object':'chat.completion.chunk','model':'qwen3-4b-q4_k_m',
                                    'choices':[{'index':0,'delta':{'content':text},'finish_reason':chunk['choices'][0]['finish_reason']}]}
                                self.wfile.write(('data: '+json.dumps(obj,ensure_ascii=False)+'\n\n').encode());self.wfile.flush()
                            self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
                        finally:
                            response.close()
                    else:
                        text=response['choices'][0]['text'];parts=[text];usage=response.get('usage')
                        first=time.monotonic()-started
                        self.send_json(200,{'id':identifier,'object':'chat.completion','model':'qwen3-4b-q4_k_m',
                            'choices':[{'index':0,'message':{'role':'assistant','content':text},
                                'finish_reason':response['choices'][0]['finish_reason']}],'usage':usage})
                except (BrokenPipeError,ConnectionResetError):
                    outcome='client_disconnected'
                except Exception as exc:
                    outcome=type(exc).__name__
                    if not stream:self.send_json(500,{'error':{'message':'local inference failed'}})
                finally:
                    trace.write(json.dumps({'id':identifier,'stream':stream,'analysis':grammar is not None,
                        'prompt_sha256':hashlib.sha256(prompt.encode()).hexdigest(),'messages':data['messages'],
                        'response':''.join(parts),'first_seconds':first,'total_seconds':time.monotonic()-started,
                        'usage':usage,'outcome':outcome},ensure_ascii=False)+'\n');trace.flush()
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.daemon_threads=True
    args.ready.write_text(json.dumps({'url':f'http://127.0.0.1:{server.server_port}/v1',
        'model_sha256':digest,'model_revision':'bc640142c66e1fdd12af0bd68f40445458f3869b',
        'template_sha256':hashlib.sha256(template_text.encode()).hexdigest(),
        'gpu_snapshot_before':snapshot,'chosen_gpu':{'index':chosen[3],'uuid':chosen[2],'free_mib':chosen[0]},
        'configuration':{'n_gpu_layers':-1,'n_ctx':8192,'n_batch_prompt_tokens':256,'concurrent_sequences':1,
            'temperature':0,'seed':42,'max_tokens_cap':512,'thinking':False,'flash_attention':True},
        'llama_cpp_python':version('llama-cpp-python'),'load_seconds':load_seconds,
        'provider_source_sha256':sha(__file__),'process_gpu_mib_after_load':allocated,
        'pid':os.getpid()},indent=2)+'\n')
    try:server.serve_forever()
    finally:server.server_close();trace.close();model.close()


if __name__=='__main__':main()
