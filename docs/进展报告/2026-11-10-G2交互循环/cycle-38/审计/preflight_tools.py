"""Deterministic scripted plans exercise sampler/wire plumbing, NOT model quality."""
import argparse
import re
import subprocess
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import threading
from urllib.request import ProxyHandler, build_opener

from native_common import ROOT, BASE, PROTOCOL, WORK, read, digest
from native_wire_relay import NativeWireRelay, parse_wire
from sample_pairs import collect_arm
from avatar.brain.facts import _mask_quoted
from avatar.config import config


def main(tag):
    assert re.fullmatch(r"[a-z0-9_-]+", tag)
    output = BASE/('审计/工作目录/002-工程全量/controlled-sampler-preflight-'+tag)
    output.mkdir(exist_ok=False)
    protocol = read(PROTOCOL)
    routes = {text: (case, route) for case in protocol['development_cases']
              for text, route in zip(case['turns'], case['expected_routes'], strict=True)}
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def do_POST(self):
            raw = self.rfile.read(int(self.headers['Content-Length'])).decode()
            body = json.loads(raw)
            schema = body.get('response_format', {}).get('json_schema', {}).get('name')
            kind = 'plan' if schema == 'avatar_lab_action_plan_v1' else 'cognitive' if schema else 'generation'
            requests.append({'ordinal': len(requests)+1, 'kind': kind, 'raw_request': raw})
            reply = '这是受控HTTP的原始草稿，不是模型生成。'
            if kind == 'cognitive':
                reply = json.dumps({'emotion': {'valence': 0, 'arousal': 0}, 'facts': []})
            elif kind == 'plan':
                payload = json.loads(body['messages'][-1]['content'])
                case, route = routes[payload['current_question']]
                plan = {'route': 'ordinary', 'actor': 'unknown', 'channel': 'none', 'source_message_id': 0, 'evidence': ''}
                if route.startswith('unavailable_'):
                    channel = case['id'].removeprefix('c38_')
                    channel = 'message' if channel == 'message' else channel
                    source = payload['user_sources'][-1] if route == 'unavailable_request' else payload['user_sources'][0]
                    evidence = max((part.strip() for part in re.split(r' +', _mask_quoted(source['text']))), key=len)
                    plan.update(route=route, actor='assistant', channel=channel,
                                source_message_id=source['id'], evidence=evidence)
                reply = json.dumps(plan, ensure_ascii=False)
            ident = 'controlled-c38-'+str(len(requests))
            base = {'id': ident, 'object': 'chat.completion', 'created': 0, 'model': 'controlled-cpu-fixture'}
            if body.get('stream'):
                payload = {**base, 'choices': [{'index': 0, 'delta': {'content': reply}, 'finish_reason': None}]}
                terminal = {**base, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]}
                content = ('data: '+json.dumps(payload, ensure_ascii=False)+'\n\ndata: '+json.dumps(terminal)+'\n\ndata: [DONE]\n\n').encode()
                content_type = 'text/event-stream'
            else:
                content = json.dumps({**base, 'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': reply}, 'finish_reason': 'stop'}]}, ensure_ascii=False).encode()
                content_type = 'application/json'
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
    provider = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=provider.serve_forever, daemon=True)
    thread.start()
    original = config.llm.base_url, config.llm.api_key, config.llm.model, config.embedding.model
    report = {'scope': 'scripted_plan_HTTP_SSE_SQL_wire_plumbing_only_NOT_native_classification',
        'native_or_gpu_calls': 0, 'arms': [], 'completed': False, 'failure': None,
        'fixture_requests': [], 'provider_closed': False,
        'execution_head': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
        'source_sha256': {str(p.relative_to(ROOT)): digest(p) for p in [Path(__file__), Path(__file__).with_name('sample_pairs.py'), ROOT/'src/avatar/lab/typed_capability_gate.py', PROTOCOL]}}
    try:
        with NativeWireRelay(f'http://127.0.0.1:{provider.server_port}/v1', output/'wire.jsonl', actual_native=False) as relay:
            config.llm.base_url, config.llm.api_key, config.llm.model = relay.url, 'local-eval-only', 'controlled-cpu-fixture'
            config.embedding.model = ''
            opener = build_opener(ProxyHandler({}))
            for case in protocol['development_cases']:
                for candidate in (False, True):
                    row = collect_arm(case, candidate, opener, output/'wire.jsonl', lambda: None, output, 1)
                    report['arms'].append(row)
                    assert row['completed'] and not row['failure'] and row['server_closed'], row['failure']
                    if candidate:
                        for turn, expected in zip(row['turns'], case['expected_routes'], strict=True):
                            review = turn['result'].get('response_review')
                            if expected.startswith('unavailable_'):
                                assert review['fixed_renderer_used'] and review['plan']['route'] == expected
                            elif review is not None:
                                assert not review['fixed_renderer_used']
        assert relay.closed
        wire = [json.loads(line) for line in (output/'wire.jsonl').read_text().splitlines()]
        assert len(wire) == len(requests)
        assert all(not row['actual_native'] and parse_wire(row)['finish_reason'] == 'stop' for row in wire)
        report['controlled_http_requests'] = len(wire)
        report['actual_app_results'] = sum(len(a['turns']) for a in report['arms'])
        assert report['actual_app_results'] == 44
        report['completed'] = True
    except BaseException as error:
        report['failure'] = repr(error)
        raise
    finally:
        provider.shutdown()
        thread.join()
        provider.server_close()
        config.llm.base_url, config.llm.api_key, config.llm.model, config.embedding.model = original
        report['provider_closed'] = not thread.is_alive()
        report['fixture_requests'] = requests
        (output/'evaluation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print('Controlled sampler/wire preflight:44 actual app results;', len(requests), 'scripted HTTP calls;0native')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    main(parser.parse_args().tag)
