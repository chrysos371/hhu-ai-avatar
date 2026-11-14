"""Actual SDK SSE and same-client HTTP hooks; scripted loopback stream, no model."""
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import threading
import httpx
from openai import OpenAI
from native_common import collect_sdk_stream
from native_common import ROOT,WORK,digest

out=WORK/'sse-controlled-v1.json';assert not out.exists()
requests=[];observed=[];responses=[]
events=[{'id':'scripted-sse-1','object':'chat.completion.chunk','model':'scripted','choices':[{'index':0,'delta':{'content':text},'finish_reason':finish}]} for text,finish in [('预热',None),('完成。',None),('','stop')]]
body=''.join('data: '+json.dumps(e,ensure_ascii=False)+'\n\n' for e in events)+'data: [DONE]\n\n'
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        raw=self.rfile.read(int(self.headers['Content-Length']))
        requests.append({'body':json.loads(raw),'sha256':hashlib.sha256(raw).hexdigest()})
        self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(body.encode())));self.end_headers();self.wfile.write(body.encode())
server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever);thread.start()
def request_hook(req):observed.append(hashlib.sha256(req.read()).hexdigest())
def response_hook(resp):responses.append(resp.status_code)
try:
    client=httpx.Client(trust_env=False,event_hooks={'request':[request_hook],'response':[response_hook]})
    with OpenAI(base_url=f'http://127.0.0.1:{server.server_port}/v1',api_key='scripted-only',max_retries=0,http_client=client) as sdk:
        result,parsed=collect_sdk_stream(sdk,model='scripted',messages=[{'role':'user','content':'预热'}],max_tokens=32)
    assert result=='预热完成。' and len(parsed)==3
    assert observed==[requests[0]['sha256']] and responses==[200]
finally:
    server.shutdown();server.server_close();thread.join(5)
assert not thread.is_alive()
out.write_text(json.dumps({'verified':True,'scope':'actual SDK same-client SSE hook positive control with scripted loopback HTTP, no model/GPU','native_or_GPU_calls':0,'scripted_HTTP_streams':1,'requests':requests,'hook_SHA256':observed,'response_statuses':responses,'raw_SSE':body,'SDK_events':parsed,'result':result,'server_closed':True,'probe_sha256':digest(__file__),'sampler_sha256':digest(Path(__file__).parent/'native_common.py')},ensure_ascii=False,indent=2)+'\n')
print('Same-client SDK SSE collector: one actual HTTP stream/hook/3 events/stop,closed;0 native')
