"""Replay actual CPU error receipts at the native-run stop gate; no new calls."""
import json
from pathlib import Path
import subprocess

from native_common import ROOT,BASE,WORK,CONTROLS,read,digest
from run_native import require_trial_transport


def main():
    destination = BASE/'审计/工作目录/001-材料与来源调查/transport-gate-replay.json'
    assert not destination.exists()
    admission = read(WORK/'admission.json'); assert admission['admitted']
    path = BASE/'审计/run_native.py'
    previous = subprocess.check_output(['git','show',admission['head']+':'+str(path.relative_to(ROOT))],cwd=ROOT,text=True)
    def before_sampling(text): return text.split('def run(args):',1)[1].split('receipt = sample_trial',1)[0]
    assert before_sampling(previous) == before_sampling(path.read_text())
    checks = []
    for name,allowed in [('active-neutral-typed_observation_history',True),
            ('malformed_generation',True),('cognition_error',False),('generation_error',False),('unavailable',False)]:
        receipt_path = CONTROLS/'v1'/name/'receipt.json'; receipt = read(receipt_path)
        try:
            require_trial_transport(receipt); actual = True
        except RuntimeError:
            actual = False
        assert actual is allowed
        checks.append({'fixture':str(receipt_path.relative_to(ROOT)),'sha256':digest(receipt_path),
            'continue_fixed_sampling':actual,'format_score':receipt['final_reply_score']['format_valid']})
    result = {'verified':True,'scope':'replay existing real SDK CPU receipts; malformed semantic output is scored, interface errors stop run',
        'checks':checks,'runner_sha256':digest(path),'probe_sha256':digest(Path(__file__)),
        'admission_sha256':digest(WORK/'admission.json'),'admitted_source_ref':admission['head'],
        'early_run_body_before_sampling_unchanged':True,'new_SDK_trials':0,'new_native_calls':0}
    destination.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C48 transport gate:5 existing CPU receipts;3 error stops/2 continuations;early CLI paths unchanged;0 new calls')


if __name__ == '__main__': main()
