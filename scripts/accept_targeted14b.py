"""Frozen, paired full-dialogue acceptance; never trains or deploys."""
from pathlib import Path
import argparse
import json
import traceback
from avatar.lab.common import PROJECT, WORKSPACE, sha, source_state, write_json, new_output
from avatar.lab.runner import (STYLE_HINT, TransformersBackend, gpu_lease, local_model,
                              run_suite, validate_settings)
from avatar.lab.checks import compare_reports
from avatar.lab.training import require_idle_gpus


def run(root, name, gpu):
    protocol=json.loads((root/'protocol.json').read_text())
    suite=json.loads((root/'suite.json').read_text())
    if sha(root/'suite.json')!=protocol['suite_sha256'] or source_state()['files']!=protocol['backend']['files']:
        raise ValueError('Frozen suite/source changed')
    lock=json.loads(Path(protocol['lock_path']).read_text());validate_settings(lock['generation'])
    if sha(protocol['lock_path'])!=protocol['lock_sha256']:raise ValueError('Lock changed')
    entry=next(m for m in lock['models'] if m['name']==name)
    adapter=Path(protocol['adapter']) if name=='14b' else None
    if adapter:
        proof=json.loads((adapter.parent/'manifest.json').read_text())
        reload=json.loads((adapter.parent/'reload-verification.json').read_text())
        if (proof['status']!='completed' or proof['base_revision']!=entry['revision']
            or proof['base_model_id']!=entry['repo'] or not reload['passed']
            or sha(adapter/'adapter_model.safetensors')!=proof['adapter_sha256']
            or sha(adapter/'adapter_config.json')!=proof['adapter_config_sha256']
            or sha(adapter/'adapter_model.safetensors')!=protocol['adapter_sha256']):
            raise ValueError('Adapter proof changed/missing')
    output=new_output(root/name)
    manifest={'kind':'real-local-model','model':entry,'generation':lock['generation'],
              'backend':source_state(),'suite_sha256':sha(root/'suite.json'),
              'arms':['style_prompt','style_lora'] if adapter else ['style_prompt'],
              'style_hint':STYLE_HINT,'analysis_adapter':False,'fresh_state_per_case':True,
              'web_tts_embeddings':False,'human_reviewed':False,'semantic_quality':'unscored',
              'physical_gpus':[gpu], 'case_ids':[c['id'] for c in suite['cases']],
              'arm_order':'alternate by case index; same model object; adapter disabled in baseline/analysis',
              'adapter_sha256':protocol['adapter_sha256'] if adapter else None}
    write_json(output/'manifest.json',manifest)
    results={a:[] for a in manifest['arms']};scores={a:[] for a in manifest['arms']}
    from avatar.config import config
    config.embedding.model='';config.llm.api_key='';config.avatar_name='小海'
    config.avatar_persona='一个温柔又有点好奇心的AI伙伴'
    try:
        require_idle_gpus([gpu])
        with gpu_lease([gpu],1):
            path=local_model(entry);require_idle_gpus([gpu])
            backend=TransformersBackend(path,lock['generation'],adapter=adapter,gpu_count=1)
            # Fixed equal warmup, excluded from latency and quality; no Avatar state.
            warm=[{'role':'system','content':'你是一个AI助手。'},{'role':'user','content':'只回复一个字：好'}]
            write_json(output/'warmup.json',[backend.generate(warm,'reply',False)])
            for n,case in enumerate(suite['cases']):
                folder=output/'cases'/case['id'];folder.mkdir(parents=True)
                arms=list(manifest['arms'])
                if adapter and n%2:arms.reverse()
                part=run_suite({'cases':[case]},backend,folder,arms=arms)
                checks=json.loads((folder/'checks.json').read_text())
                for arm in part:results[arm]+=part[arm];scores[arm]+=checks[arm]
                write_json(output/'results.partial.json',results)
                write_json(output/'status.json',{'stage':'running','completed_cases':n+1,'total_cases':len(suite['cases'])})
                print(f'{name} {n+1}/{len(suite["cases"])} {case["id"]}',flush=True)
            write_json(output/'results.json',results);write_json(output/'checks.json',scores)
            write_json(output/'comparison.json',compare_reports(scores))
        if source_state()['files']!=manifest['backend']['files']:raise ValueError('Source changed during generation')
        write_json(output/'status.json',{'stage':'completed','cases':len(suite['cases']),'quality_approved':False})
    except BaseException as exc:
        write_json(output/'status.json',{'stage':'failed','error':type(exc).__name__,'message':str(exc)})
        raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--model',choices=['14b','4b'],required=True);p.add_argument('--gpu',type=int,required=True)
    a=p.parse_args();run(a.root.resolve(),a.model,a.gpu)
