"""No-adapter 14B comparison: same source/model/settings, reply-context flag only."""
from pathlib import Path
import argparse,json
from avatar.lab.common import new_output,source_state,sha,write_json
from avatar.lab.runner import TransformersBackend,run_suite,gpu_lease,local_model,validate_settings,STYLE_HINT
from avatar.lab.training import require_idle_gpus
from avatar.lab.checks import compare_reports


def run(root,gpu):
    p=json.loads((root/'protocol.json').read_text());suite=json.loads((root/'suite.json').read_text())
    assert sha(root/'suite.json')==p['suite_sha256'] and source_state()['files']==p['backend']['files']
    lock=json.loads(Path(p['lock']).read_text());assert sha(p['lock'])==p['lock_sha256']
    validate_settings(lock['generation']);entry=next(m for m in lock['models'] if m['name']=='14b')
    require_idle_gpus([gpu])
    import avatar.main as main
    Original=main.Avatar
    results={'before':[],'after':[]};checks={'before':[],'after':[]}
    write_json(root/'manifest.json',{'kind':'real-local-model','model':entry,'generation':lock['generation'],
        'backend':source_state(),'style_hint':STYLE_HINT,'adapter':None,'analysis_adapter':False,
        'case_ids':[c['id'] for c in suite['cases']],'fresh_state_per_case':True,'physical_gpus':[gpu],
        'only_variable':'Avatar.reply_context_enabled; analysis unchanged','arm_order':'alternates by case',
        'human_reviewed':False,'quality_approved':False})
    try:
        with gpu_lease([gpu],1):
            path=local_model(entry);require_idle_gpus([gpu])
            backend=TransformersBackend(path,lock['generation'],adapter=None,gpu_count=1)
            write_json(root/'warmup.json',backend.generate([{'role':'system','content':'你是AI助手。'},{'role':'user','content':'只回复：好'}],'reply',False))
            for n,case in enumerate(suite['cases']):
                for arm in (['before','after'] if n%2==0 else ['after','before']):
                    enabled=arm=='after'
                    class Candidate(Original):
                        def __init__(self,*a,**kw):
                            kw['reply_context_enabled']=enabled
                            super().__init__(*a,**kw)
                    main.Avatar=Candidate
                    folder=root/'cases'/case['id']/arm;folder.mkdir(parents=True)
                    output=run_suite({'cases':[case]},backend,folder,arms=['style_prompt'])
                    results[arm]+=output['style_prompt']
                    checks[arm]+=json.loads((folder/'checks.json').read_text())['style_prompt']
                    write_json(root/'results.partial.json',results)
                write_json(root/'status.json',{'stage':'running','completed_cases':n+1,'total_cases':len(suite['cases'])})
                print(f'{n+1}/{len(suite["cases"])} {case["id"]}',flush=True)
        assert source_state()['files']==p['backend']['files']
        write_json(root/'results.json',results);write_json(root/'checks.json',checks)
        write_json(root/'comparison.json',compare_reports(checks))
        write_json(root/'status.json',{'stage':'completed','quality_approved':False})
    except BaseException as exc:
        write_json(root/'status.json',{'stage':'failed','error':type(exc).__name__,'message':str(exc)})
        raise
    finally:main.Avatar=Original

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--gpu',type=int,default=0)
    a=p.parse_args();run(a.root.resolve(),a.gpu)
