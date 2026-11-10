"""Execute only the trusted selector block against fake inventory; allocates no GPU."""
import argparse
import hashlib
import json
from pathlib import Path
import textwrap
from types import SimpleNamespace
from avatar.gpu_resources import select_available_gpu

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    path=Path('scripts/serve_local_model_eval.py');source=path.read_text()
    start=source.index('    snapshot = subprocess.check_output(')
    end=source.index('    from llama_cpp import',start)
    block=textwrap.dedent(source[start:end])
    raw='\n'.join(f'{i}, GPU-fake-{i}, 40000, 0' for i in range(8))
    env={'CUDA_VISIBLE_DEVICES':'6'}
    namespace={'subprocess':SimpleNamespace(check_output=lambda *args,**kwargs:raw),
        'os':SimpleNamespace(environ=env),'specification':{'required_free_mib':24576},'select_available_gpu':select_available_gpu}
    exec(compile(block,str(path),'exec'),namespace)
    selected = namespace['chosen']['index'] if isinstance(namespace['chosen'],dict) else namespace['chosen'][3]
    report={'scope':'Mock selector only, no CUDA import/model load/GPU allocation',
        'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'input_visible_mask':'6',
        'expected_physical_gpu':6,'selected_physical_gpu':selected,
        'result_visible_mask':env['CUDA_VISIBLE_DEVICES'],
        'respects_requested_mask':selected==6}
    with args.output.open('x') as target:json.dump(report,target,indent=2)
    print(report)
