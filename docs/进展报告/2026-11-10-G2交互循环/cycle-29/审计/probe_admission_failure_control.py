"""Explicit in-memory HTTP fault injection; NOT a valid context baseline run."""
import argparse
import json
from pathlib import Path
import subprocess
from urllib.error import HTTPError
from urllib.request import ProxyHandler
import run_context_baseline as controller
from context_baseline_common import digest


def main(args):
    factory=controller.build_opener;real=factory(ProxyHandler({}));overrides=[]
    class FaultOpener:
        def open(self,request,**kwargs):
            if request.full_url.endswith('/api/v1/turns') and request.data is not None:
                original=json.loads(request.data);actual=dict(original,request_id='short')
                request.data=json.dumps(actual,ensure_ascii=False).encode()
                overrides.append({'url':request.full_url,'original_fixture_payload':original,'actual_injected_http_payload':actual})
            return real.open(request,**kwargs)
    controller.build_opener=lambda *handlers:FaultOpener()
    error=None
    try:controller.run(args)
    except HTTPError as failure:error=repr(failure)
    finally:controller.build_opener=factory
    value=json.loads((args.output/'baseline.json').read_text())
    assert error is not None and '422' in error and value['failure']==error
    assert not value['completed'] and not value['engineering_passed'] and value['cleanup_errors']==[]
    assert len(value['workers'])==1 and value['workers'][0]['exit_code']==0 and not value['workers'][0]['forced_cleanup']
    assert len(value['cases'][0]['turns'])==0 and value['cases'][0]['model_requests']==[]
    assert value['http_calls'][0]['status']==422 and 'invalid_turn' in value['http_calls'][0]['raw_body']
    result={'verified':True,'control_kind':'explicit runtime opener bad-ID injection, not context baseline','fault_control_source_sha256':digest(Path(__file__)),
        'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'baseline_sha256':digest(args.output/'baseline.json'),
        'override':overrides,'primary_http_error_preserved':True,'raw_error_body_archived':True,'zero_turn_worker_source_validation_and_cleanup_passed':True,
        'app_processes':1,'accepted_turns':0,'model_requests':0,'context_conclusion_valid':False,
        'warning':'baseline.json http_calls.request records the pre-injection fixture payload. override.actual_injected_http_payload is the deliberate actual bad request. Never use this control as a source-faithful context comparison.'}
    with (args.output/'fault-control-verification.json').open('x') as out:json.dump(result,out,ensure_ascii=False,indent=2);out.write('\n')
    print('Actual HTTP422 retained; zero-turn worker clean exit; no model call. Explicit fault control, not context data.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);parser.add_argument('--freeze',required=True,type=Path)
    parser.add_argument('--expected-freeze-sha256',required=True);main(parser.parse_args())
