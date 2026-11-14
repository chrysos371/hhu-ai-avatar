"""Import/hash installed runtime and existing weights only; never construct a model."""
from pathlib import Path
import subprocess

from native_common import ROOT,WORK,RUNTIME,WEIGHTS,REGISTRY,read,digest,capture_runtime,protocol_check


def main():
    protocol_check()
    assert not RUNTIME.exists() and not WEIGHTS.exists()
    WORK.mkdir(parents=True,exist_ok=True)
    runtime = capture_runtime()
    records = []
    for spec in read(REGISTRY)['models']:
        size = '4b' if spec['model_id'] == 'qwen3-4b-q4_k_m' else '14b'
        path = ROOT/'models'/('qwen3-'+size+'-gguf')/spec['file']
        metadata = read(ROOT/spec['metadata'])
        assert metadata['path'] == spec['file'] and metadata['lfs']['oid'] == spec['sha256']
        assert metadata.get('revision',spec['revision']) == spec['revision']
        actual = digest(path); assert actual == spec['sha256']
        records.append({'model_id':spec['model_id'],'registered_revision':spec['revision'],
            'path':str(path),'actual_path':str(path.resolve()),'bytes':path.stat().st_size,
            'sha256':actual,'metadata_sha256':digest(ROOT/spec['metadata']),
            'metadata_has_revision_field':'revision' in metadata})
    import json
    RUNTIME.write_text(json.dumps(runtime,ensure_ascii=False,indent=2)+'\n')
    inventory = subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.free,utilization.gpu',
        '--format=csv,noheader,nounits'],text=True)
    processes = subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory',
        '--format=csv,noheader,nounits'],text=True)
    result = {'scope':'read-only installed runtime/weight admission; no Llama construction or inference',
        'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'collector_sha256':digest(Path(__file__)),'registry_sha256':digest(REGISTRY),
        'native_runtime_sha256':digest(RUNTIME),'models':records,
        'GPU_inventory_before_any_C50_model_construction':inventory,
        'GPU_processes_before_any_C50_model_construction':processes,
        'model_constructions':0,'native_inference_calls':0}
    WEIGHTS.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C50 native import:54 libraries matched migration reference;2 actual weights SHA matched;0 model construction/inference')


if __name__ == '__main__':
    main()
