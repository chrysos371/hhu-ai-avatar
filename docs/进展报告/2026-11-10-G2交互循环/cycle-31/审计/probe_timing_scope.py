"""Actual controller/HTTP timing-boundary control with explicit synthetic costs."""
from hashlib import sha256
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from urllib.request import build_opener,ProxyHandler
from run_readonly_analysis_cost import CostContext,BASE


def main():
    observations=[]
    def mark(event):observations.append({'event':event,'ns':time.monotonic_ns()})
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,status,value,kind='application/json'):
            raw=value.encode() if isinstance(value,str) else json.dumps(value).encode()
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_POST(self):
            assert self.path=='/api/v1/turns';self.rfile.read(int(self.headers['Content-Length']));mark('post_received');self.send(202,{'data':{'job_id':'c31_fixture_timing_job_0001'}})
        def do_GET(self):
            if self.path.endswith('/events'):
                reply='明确的计时HTTP夹具。';mark('fixture_sse_send')
                self.send(200,'event: text\ndata: '+json.dumps({'text':reply})+'\n\nevent: result\ndata: '+json.dumps({'reply':reply})+'\n\n','text/event-stream')
            else:
                assert self.path=='/api/v1/conversation';mark('post_terminal_conversation_started');time.sleep(.06);mark('post_terminal_conversation_finished');self.send(200,{'data':{'items':[]}})
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    h=CostContext.__new__(CostContext);h.opener=build_opener(ProxyHandler({}));h.report={'http_calls':[]}
    h.ready={'base_url':f'http://127.0.0.1:{server.server_port}/api/v1','token':'explicit-fake-timing-token'}
    h.case={'id':'timing_boundary_fixture','turns':[]};h.state={'process':SimpleNamespace(pid=os.getpid()),'record':{'turns_completed':0}}
    def verify():mark('source_verify_started');time.sleep(.04);mark('source_verify_finished')
    def persist():mark('persistence_started');time.sleep(.08);mark('persistence_finished')
    h.verify=verify;h.persist=persist
    try:
        overall=time.monotonic_ns();row=CostContext.begin(h,'受控计时请求。');CostContext.finish(h,row);finished=time.monotonic_ns()
        ns={r['event']:r['ns'] for r in observations}
        assert ns['source_verify_finished']<=row['client_submit_started_ns']<=ns['post_received']<=ns['fixture_sse_send']<=row['client_terminal_ns']
        assert row['client_terminal_ns']<=ns['post_terminal_conversation_started']<ns['post_terminal_conversation_finished']<=ns['persistence_started']<ns['persistence_finished']
        assert row['submit_to_terminal_seconds']==(row['client_terminal_ns']-row['client_submit_started_ns'])/1e9
        assert (finished-overall)/1e9-row['submit_to_terminal_seconds']>=.17
        assert h.state['record']['turns_completed']==1
    finally:server.shutdown();thread.join(5);server.server_close()
    out=BASE/'审计/工作目录/001-只读分析路由保护/timing-scope-control.json';assert not out.exists()
    result={'passed':True,'actual_llm_or_gpu':False,'actual_loopback_http_fixture':True,'application_os_restart_claim':False,
        'helper_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),'events':observations,'turn':row,
        'full_control_call_seconds':(finished-overall)/1e9,'measured_submit_to_terminal_seconds':row['submit_to_terminal_seconds'],
        'injected_costs_seconds':{'source_verification':.04,'after_terminal_conversation':.06,'persistence':.08},
        'source_verify_and_after_terminal_costs_excluded':True,'speedup_claim':False,'thread_closed':not thread.is_alive()}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('Actual HTTP timing boundary passed:source verification,post-terminal API and persistence excluded;not native speed data.')


if __name__=='__main__':main()
