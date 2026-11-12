"""Actual loopback HTTP controls for replay transport; no native model/GPU."""
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.error import HTTPError
from run_state_replay import send_raw


def main():
    seen=[];controls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_POST(self):
            raw=self.rfile.read(int(self.headers['Content-Length']))
            seen.append({'raw':raw.decode(),'authorization':self.headers.get('Authorization'),'path':self.path})
            request=json.loads(raw);mode=request['model']
            if mode=='http_error':status=503;body=b'{"error":"controlled unavailable"}'
            elif request['stream']:
                chunks=[{'id':'cpu-stream','choices':[{'delta':{'content':'核验'},'finish_reason':None}]},
                        {'id':'cpu-stream','choices':[{'delta':{'content':'通过'},'finish_reason':'stop'}]}]
                status=200;body=(''.join('data: '+json.dumps(c,ensure_ascii=False)+'\n\n' for c in chunks)+('' if mode=='incomplete' else 'data: [DONE]\n\n')).encode()
            else:
                status=200;body=json.dumps({'id':'cpu-json','choices':[{'message':{'content':'核验通过'},'finish_reason':'stop'}]},ensure_ascii=False).encode()
            self.send_response(status);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}/v1'
    try:
        for stream in (False,True):
            raw=json.dumps({'model':'cpu-only','messages':[{'role':'user','content':'原字节：你好'}],'stream':stream},ensure_ascii=False,separators=(',',':'))
            row={};send_raw(url,raw,row)
            assert seen[-1]=={'raw':raw,'authorization':'Bearer local-eval-only','path':'/v1/chat/completions'}
            assert row['reply']=='核验通过' and row['finish_reason']=='stop' and row['outcome']=='completed'
            assert row['request_sha256']==sha256(raw.encode()).hexdigest() and row['response_body_sha256']==sha256(row['raw_http_body'].encode()).hexdigest()
            controls.append({'control':'compact_stream' if stream else 'compact_json','row':row,'received':seen[-1],'passed':True})
        for mode,error in (('http_error',HTTPError),('incomplete',ValueError)):
            row={};raw=json.dumps({'model':mode,'stream':True},separators=(',',':'))
            try:send_raw(url,raw,row);raise AssertionError('Transport accepted controlled failure')
            except error:pass
            assert row.get('error') and 'finish_reason' not in row and row['request_sha256']==sha256(raw.encode()).hexdigest()
            assert row['response_body_sha256']==sha256(row['raw_http_body'].encode()).hexdigest()
            if mode=='http_error':assert row['status']==503 and row['outcome']=='http_error'
            controls.append({'control':mode,'row':row,'received':seen[-1],'passed':True})
        count=len(seen)
        for endpoint in ('http://example.invalid/v1',url+'?query=1'):
            try:send_raw(endpoint,'{}',{});raise AssertionError('Unowned endpoint accepted')
            except ValueError:pass
        assert len(seen)==count
        controls.append({'control':'nonlocal_or_query_endpoint','rejected_before_network':True,'passed':True})
    finally:server.shutdown();server.server_close();thread.join()
    out=Path(__file__).resolve().parents[1]/'审计/工作目录/001-原生状态隔离/transport-cpu-controls.json'
    with out.open('x') as stream:json.dump({'passed':True,'actual_llm_or_gpu':False,'actual_loopback_http':True,'controls':controls},stream,ensure_ascii=False,indent=2);stream.write('\n')
    print('5 actual loopback HTTP controls passed; exact compact UTF-8 bytes, JSON/SSE completion, retained HTTP/incomplete failures, endpoint admission; no native model/GPU.')


if __name__=='__main__':main()
