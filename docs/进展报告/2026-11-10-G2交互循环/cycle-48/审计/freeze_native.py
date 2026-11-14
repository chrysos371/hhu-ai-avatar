"""Create model-specific committed-source descriptors or retire verified runs."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from native_common import ROOT,BASE,WORK,PROTOCOL,REGISTRY,RUNTIME,WEIGHTS,read,digest,historical,required_inputs,protocol_check


def main(action,model_id):
    short = '4b' if model_id == 'qwen3-4b-q4_k_m' else '14b'
    path = WORK/(short+'-freeze-v1.json')
    if action == 'freeze':
        protocol_check(); assert read(WORK/'admission.json')['admitted']
        assert not path.exists() and not path.with_name(path.stem+'-retirement.json').exists()
        assert not (BASE/'实验'/(short+'-development-v1')).exists()
        names = required_inputs(model_id)
        hashes = {n:digest(ROOT/n) for n in names}
        head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
        assert historical(head,names) == hashes,'commit all execution inputs before freezing'
        value = {'scope':'C48 preregistered actual SDK diagnostic development only',
            'registration_version':1,'source_ref':head,'model_id':model_id,'partition':'development',
            'protected_authorized':False,'output_tag':short+'-development-v1',
            'repetitions':3,'max_native_calls':146,'protocol_sha256':digest(PROTOCOL),
            'registry_sha256':digest(REGISTRY),'runtime_sha256':digest(RUNTIME),'weights_sha256':digest(WEIGHTS),
            'sha256':hashes,'default_model_change_authorized':False}
        path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
        print(short,'freeze inputs',len(hashes),'source',head,'SHA',digest(path))
        return
    frozen = read(path)
    verification_path = WORK/(short+'-verification.json'); verification = read(verification_path)
    assert verification['verified'] and verification['model_id'] == model_id
    assert verification['freeze_sha256'] == digest(path)
    folder = BASE/'实验'/frozen['output_tag']; report = read(folder/'evaluation.json')
    assert report['completed'] and report['cleanup_passed']
    assert verification['evaluation_sha256'] == digest(folder/'evaluation.json')
    retired = path.with_name(path.stem+'-retirement.json'); assert not retired.exists()
    marker = {'scope':'finished native descriptor retired; future CLI must refuse before provider',
        'freeze_sha256':digest(path),'verification_sha256':digest(verification_path),
        'native_calls_recorded':verification['native_calls'],'model_id':model_id,
        'primary_gate_passed':verification['primary_gate_passed'],'retired':True}
    retired.write_text(json.dumps(marker,ensure_ascii=False,indent=2)+'\n')
    before = {str(p.relative_to(folder)):digest(p) for p in folder.rglob('*') if p.is_file()}
    command = [sys.executable,str(BASE/'审计/run_native.py'),'--freeze',str(path),
        '--expected-freeze-sha256',digest(path),'--model',model_id,'--output',str(folder)]
    result = subprocess.run(command,cwd=ROOT,text=True,capture_output=True)
    assert result.returncode != 0 and 'descriptor retired' in result.stderr
    assert before == {str(p.relative_to(folder)):digest(p) for p in folder.rglob('*') if p.is_file()}
    proof = {'verified':True,'model_id':model_id,'retirement_sha256':digest(retired),
        'verification_sha256':digest(verification_path),'argv':command,'returncode':result.returncode,
        'stdout':result.stdout,'stderr':result.stderr,'closed_output_unchanged':True,
        'additional_native_calls':0,'verifier_sha256':digest(Path(__file__))}
    destination = WORK/(short+'-retirement-verification.json'); assert not destination.exists()
    destination.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
    print(short,'retired;actual CLI refused;0 extra native calls')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('freeze','retire'))
    parser.add_argument('--model',choices=('qwen3-4b-q4_k_m','qwen3-14b-q4_k_m'),required=True)
    args = parser.parse_args(); main(args.action,args.model)
