"""Owned real application OS worker against a controlled loopback HTTP provider."""
import argparse
import json
import os
from pathlib import Path
import signal
import sys
import threading
from context_baseline_common import ROOT,verify_freeze,require_loopback,runtime_modules


def main(args):
    if not __debug__:raise ValueError('Run without Python optimization')
    verify_freeze(args.freeze,args.expected_freeze_sha256);require_loopback(args.provider_url)
    db=args.db.resolve();temporary=(ROOT.parent/'runtime/tmp').resolve()
    if not db.is_relative_to(temporary) or not db.parent.name.startswith('c29-context-'):raise ValueError('Use owned C29 temporary DB only')
    if args.ready.exists() or args.runtime_out.exists():raise ValueError('Use fresh worker evidence paths')
    os.environ['NO_PROXY']='127.0.0.1,localhost';os.environ['no_proxy']='127.0.0.1,localhost'
    sys.path.insert(0,str(ROOT/'src'))
    from avatar.config import config
    config.llm.base_url=args.provider_url;config.llm.api_key='local-c29-fixture-only';config.llm.model='c29-controlled'
    config.embedding.model=''
    from avatar.web import create_server
    server=create_server(str(db),port=0,legacy_writes=False,identity_grounding=False,profile_grounding=False,task_delivery_check=False,literal_composition=False)
    initial={'pid':os.getpid(),'base_url':f'http://127.0.0.1:{server.server_port}/api/v1','token':server.token,'session_id':server.session_id}
    # Live fixture token stays in ignored runtime; it is never archived in reports.
    with args.ready.open('x') as out:json.dump(initial,out)
    def stop(signum,frame):threading.Thread(target=server.shutdown,daemon=True).start()
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    failure=None
    try:server.serve_forever(poll_interval=.05)
    except BaseException as error:failure=repr(error);raise
    finally:
        server.server_close();verify_freeze(args.freeze,args.expected_freeze_sha256)
        result={'pid':os.getpid(),'session_id':server.session_id,'module_sources':runtime_modules(),'short_term_after':server.short_term,
                'context_revision_after':server.context_revision,'failure':failure,'provider_kind':'controlled_loopback_fixture','actual_llm_or_gpu':False}
        with args.runtime_out.open('x') as out:json.dump(result,out,ensure_ascii=False,indent=2);out.write('\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--db',required=True,type=Path);parser.add_argument('--ready',required=True,type=Path)
    parser.add_argument('--runtime-out',required=True,type=Path);parser.add_argument('--provider-url',required=True)
    parser.add_argument('--freeze',required=True,type=Path);parser.add_argument('--expected-freeze-sha256',required=True);main(parser.parse_args())
