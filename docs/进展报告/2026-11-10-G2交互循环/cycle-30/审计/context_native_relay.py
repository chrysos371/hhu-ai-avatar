"""Transparent owned loopback wire archive, no request or response rewriting."""
from hashlib import sha256
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
import threading
import time
from urllib.request import Request,build_opener,ProxyHandler
from urllib.error import HTTPError
from context_native_common import require_loopback


class NativeRelay(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,upstream):
        require_loopback(upstream);self.upstream=upstream;self.rows=[];self.guard=threading.RLock();self.opener=build_opener(ProxyHandler({}))
        super().__init__(('127.0.0.1',0),RelayHandler)


class RelayHandler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        if self.path!='/v1/chat/completions':self.send_error(404);return
        raw=self.rfile.read(int(self.headers['Content-Length']));payload=json.loads(raw);start=time.monotonic()
        record={'kind':'cognitive' if payload.get('response_format') else 'generation','request':payload,'raw_request_json':raw.decode(),
                'request_body_sha256':sha256(raw).hexdigest(),'controller_pid':os.getpid(),'actual_llm_or_gpu':True,'outcome':'admitted'}
        with self.server.guard:record['ordinal']=len(self.server.rows)+1;self.server.rows.append(record)
        try:
            request=Request(self.server.upstream+'/chat/completions',data=raw,headers={'Content-Type':'application/json'})
            try:
                with self.server.opener.open(request,timeout=120) as response:body=response.read();status=response.status;kind=response.headers.get('Content-Type','application/json')
            except HTTPError as error:body=error.read();status=error.code;kind=error.headers.get('Content-Type','application/json')
            record.update(http_status=status,raw_http_body=body.decode(),response_body_sha256=sha256(body).hexdigest(),content_type=kind)
            self.send_response(status);self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(body)));self.send_header('Connection','close');self.end_headers();self.wfile.write(body);self.wfile.flush()
            record['outcome']='completed'
        except BaseException as error:record['outcome']='failed';record['error']=repr(error);raise
        finally:record['seconds']=time.monotonic()-start
