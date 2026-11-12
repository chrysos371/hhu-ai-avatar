"""Owned real application OS worker against a controlled loopback HTTP provider."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import threading
from analysis_cost_common import ROOT,verify_freeze,require_loopback,runtime_modules


def main(args):
    if not __debug__:raise ValueError('Run without Python optimization')
    verify_freeze(args.freeze,args.expected_freeze_sha256,args.model);require_loopback(args.provider_url)
    db=args.db.resolve();temporary=(ROOT.parent/'runtime/tmp').resolve()
    if not db.is_relative_to(temporary) or not db.parent.name.startswith('c31-context-'):raise ValueError('Use owned C31 temporary DB only')
    if args.ready.exists() or args.runtime_out.exists():raise ValueError('Use fresh worker evidence paths')
    os.environ['NO_PROXY']='127.0.0.1,localhost';os.environ['no_proxy']='127.0.0.1,localhost'
    sys.path.insert(0,str(ROOT/'src'))
    from avatar.config import config
    config.llm.base_url=args.provider_url;config.llm.api_key='local-c30-eval-only';config.llm.model=args.model
    config.embedding.model='';config.avatar_name='审计形象C31';config.avatar_persona='本机只读问题分析成本审计助手'
    analysis_rows=[];candidate_source=None
    if args.analysis_arm=='lab_readonly_candidate':
        import readonly_analysis_candidate as candidate
        expected=Path(__file__).with_name('readonly_analysis_candidate.py').resolve()
        if Path(candidate.__file__).resolve()!=expected:raise ValueError('Foreign audit candidate module')
        from hashlib import sha256
        candidate_source={'path':str(expected),'sha256':sha256(expected.read_bytes()).hexdigest()}
        candidate.install(analysis_rows)
    from avatar.web import create_server
    server=create_server(str(db),port=0,legacy_writes=False,identity_grounding=False,profile_grounding=False,task_delivery_check=False,literal_composition=False,recover_context=not args.no_context_recovery)
    initial={'pid':os.getpid(),'base_url':f'http://127.0.0.1:{server.server_port}/api/v1','token':server.token,'session_id':server.session_id}
    # Live fixture token stays in ignored runtime; it is never archived in reports.
    with args.ready.open('x') as out:json.dump(initial,out)
    def stop(signum,frame):threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    failure=None
    try:server.serve_forever(poll_interval=.05)
    except BaseException as error:failure=repr(error);raise
    finally:
        server.server_close();verify_freeze(args.freeze,args.expected_freeze_sha256,args.model)
        result={'pid':os.getpid(),'session_id':server.session_id,'module_sources':runtime_modules(),'short_term_after':server.short_term,
                'context_revision_after':server.context_revision,'failure':failure,'provider_kind':'actual_native_loopback_relay','actual_llm_or_gpu':True,'fixed_persona':'本机只读问题分析成本审计助手','embedding_disabled':True,'recover_context':server.recover_context,'audit_timing_hooks':False,'audit_analysis_arm':args.analysis_arm,'audit_analysis_hook':args.analysis_arm=='lab_readonly_candidate','audit_candidate_source':candidate_source,'audit_analysis_rows':analysis_rows}
        with args.runtime_out.open('x') as out:json.dump(result,out,ensure_ascii=False,indent=2);out.write('\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--db',required=True,type=Path);parser.add_argument('--ready',required=True,type=Path)
    parser.add_argument('--runtime-out',required=True,type=Path);parser.add_argument('--provider-url',required=True)
    parser.add_argument('--freeze',required=True,type=Path);parser.add_argument('--expected-freeze-sha256',required=True);parser.add_argument('--analysis-arm',required=True,choices=('current_analysis','lab_readonly_candidate'));parser.add_argument('--no-context-recovery',action='store_true');parser.add_argument('--model',required=True,choices=('qwen3-4b-q4_k_m','qwen3-32b-q4_k_m'));main(parser.parse_args())
