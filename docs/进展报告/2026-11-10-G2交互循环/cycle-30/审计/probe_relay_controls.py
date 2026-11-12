"""Explicit fake-upstream CPU control; never evidence of real native inference."""
from hashlib import sha256
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request,build_opener,ProxyHandler
from context_native_common import ROOT,BASE,PROTOCOL,digest
from context_native_relay import NativeRelay
from run_native_context_use import parse_wire,grade


class Upstream(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        assert self.headers.get('Authorization')=='Bearer local-eval-only'
        raw=self.rfile.read(int(self.headers['Content-Length']));data=json.loads(raw);i=len(self.server.rows)+1;ident='fake-relay-'+str(i)
        reply='{"emotion":{"valence":0,"arousal":0},"facts":[]}' if data.get('response_format') else '明确虚构的CPU夹具。'
        if data['stream']:
            chunks=[{'id':ident,'choices':[{'delta':{'content':reply},'finish_reason':None}]},{'id':ident,'choices':[{'delta':{},'finish_reason':'stop'}]}]
            body=(''.join('data: '+json.dumps(c,ensure_ascii=False)+'\n\n' for c in chunks)+'data: [DONE]\n\n').encode();kind='text/event-stream'
        else:body=json.dumps({'id':ident,'choices':[{'message':{'content':reply},'finish_reason':'stop'}]},ensure_ascii=False).encode();kind='application/json'
        self.server.rows.append({'raw_request':raw,'raw_body':body,'kind':kind,'reply':reply,'id':ident})
        self.send_response(200);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)


def main():
    upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream);upstream.rows=[]
    threads=[threading.Thread(target=upstream.serve_forever,daemon=True)];threads[0].start()
    relay=NativeRelay(f'http://127.0.0.1:{upstream.server_port}/v1',actual_native=False);threads.append(threading.Thread(target=relay.serve_forever,daemon=True));threads[1].start()
    opener=build_opener(ProxyHandler({}));url=f'http://127.0.0.1:{relay.server_port}/v1/chat/completions';checks=[]
    try:
        for stream in (False,True):
            for cognitive in (False,True):
                payload={'model':'fake-cpu-only','messages':[{'role':'user','content':'含中文与空白 控制'}],'stream':stream,'temperature':0}
                if cognitive:payload['response_format']={'type':'json_schema','json_schema':{'name':'fake','schema':{'type':'object'}}}
                raw=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
                assert raw!=json.dumps(payload,ensure_ascii=False).encode()
                with opener.open(Request(url,data=raw,headers={'Content-Type':'application/json','Authorization':'Bearer local-c30-eval-only'}),timeout=5) as response:body=response.read();kind=response.headers['Content-Type']
                archived=relay.rows[-1];native=upstream.rows[-1];parsed=parse_wire(archived)
                assert native['raw_request']==raw==archived['raw_request_json'].encode()
                assert native['raw_body']==body==archived['raw_http_body'].encode() and native['kind']==kind
                assert archived['request_body_sha256']==sha256(raw).hexdigest() and archived['response_body_sha256']==sha256(body).hexdigest()
                assert parsed['reply']==native['reply'] and parsed['provider_call_id']==native['id'] and parsed['finish_reason']=='stop' and parsed['actual_llm_or_gpu'] is False
                checks.append({'stream':stream,'cognitive':cognitive,'raw_request_sha256':sha256(raw).hexdigest(),'raw_response_sha256':sha256(body).hexdigest(),'passed':True})
        try:opener.open(Request(url,data=b'{}',headers={'Authorization':'Bearer wrong-fixture-only'}),timeout=5);raise AssertionError('Wrong credential accepted')
        except HTTPError as error:assert error.code==403
        assert len(relay.rows)==len(upstream.rows)==4
        cases=json.loads((ROOT/PROTOCOL).read_text())['cases'];grades=[]
        for case in cases:
            positive='无法确认。' if case['metric']=='missing_abstention' else case['expected']
            assert grade(positive,case)['correct'] and not grade('无依据猜测1234567890。',case)['correct']
            grades.append({'case':case['id'],'positive_and_wrong_negative_passed':True})
    finally:
        relay.shutdown();threads[1].join(5);relay.server_close();upstream.shutdown();threads[0].join(5);upstream.server_close()
    out=BASE/'审计/工作目录/001-真实模型重启历史利用/relay-cpu-controls.json';assert not out.exists()
    out.write_text(json.dumps({'passed':True,'actual_llm_or_gpu':False,'fake_upstream_only':True,'helper_sha256':digest(__file__ if hasattr(__file__,'read_bytes') else __import__('pathlib').Path(__file__)),
        'wire_checks':checks,'wrong_credential_rejected_before_upstream':True,'grade_controls':grades,'threads_closed':all(not t.is_alive() for t in threads)},ensure_ascii=False,indent=2)+'\n')
    print('CPU fake-upstream control:4 byte-exact sync/stream cognition/generation paths,wrong credential blocked,6 score positive/negative pairs; no real model or GPU.')


if __name__=='__main__':main()
