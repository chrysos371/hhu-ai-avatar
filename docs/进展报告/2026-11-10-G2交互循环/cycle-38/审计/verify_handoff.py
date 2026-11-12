"""Reproduce the retired name defect, then exercise repaired child argv via OS."""
import json
from pathlib import Path
import subprocess
import tempfile
from native_common import ROOT, BASE, WORK, ADMISSION, HANDOFF_PROOF, digest, read
from run_pairs import sampler_command
from check_research_names import undefined_globals
from avatar.paths import project_data_root


def main():
    assert not HANDOFF_PROOF.exists()
    controller = BASE/'审计/run_pairs.py'
    relative = str(controller.relative_to(ROOT))
    original = subprocess.check_output(['git','show','26af0a3:'+relative],cwd=ROOT,text=True)
    red = undefined_globals(original, relative)
    assert red == [{'scope':'main','name':'relay_metadata'}], red
    green = {p.name:undefined_globals(p.read_text(),str(p)) for p in sorted((BASE/'审计').glob('*.py'))}
    assert all(not errors for errors in green.values()), green
    old_admission = read(ADMISSION)
    assert old_admission['verified'] and old_admission['new_native_calls'] == 0
    old = read(WORK/'execution-freeze-retirement.json')
    assert old['actual_native_calls'] == old['actual_application_results'] == 0
    assert old['actual_GPU_provider_loads'] == 1 and old['owned_pid_absent']
    assert not Path('/proc',str(old['provider_pid'])).exists()
    gpu = subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory','--format=csv,noheader,nounits'],text=True)
    assert all(line.split(',')[0].strip()!=str(old['provider_pid']) for line in gpu.splitlines())
    with tempfile.TemporaryDirectory(prefix='c38-handoff-negative-',dir=project_data_root(ROOT)/'tmp') as temp:
        temp = Path(temp)
        descriptor = temp/'wrong-parent.json'
        descriptor.write_text('{}')
        metadata = BASE/'实验/paired-4b-r1/relay-provider-ready.json'
        command = sampler_command(metadata,temp/'not-created',descriptor,'0'*64,1)
        assert command[command.index('--provider')+1] == str(metadata)
        assert command[command.index('--freeze')+1] == str(descriptor.resolve())
        assert command[command.index('--expected-freeze-sha256')+1] == '0'*64
        completed = subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
        assert completed.returncode != 0 and 'descriptor bytes changed' in completed.stderr
        assert 'NameError' not in completed.stderr and not (temp/'not-created').exists()
        child = {'argv':command,'stdout':completed.stdout,'stderr':completed.stderr,'exit_code':completed.returncode,
                 'parsed_actual_repaired_controller_argv':True,'rejected_before_provider_read_or_output':True}
    result = {'verified':True,'scope':'controller_name_and_child_argument_regression_only_not_model_quality',
        'source_ref':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'verifier_sha256':digest(Path(__file__)),'controller_sha256':digest(controller),
        'sampler_sha256':digest(BASE/'审计/sample_pairs.py'),'name_checker_sha256':digest(BASE/'审计/check_research_names.py'),
        'original_controller_ref':'26af0a3','original_undefined_globals':red,'current_static_name_checks':green,
        'actual_child_negative':child,'previous_controlled_admission_sha256':digest(ADMISSION),
        'previous_freeze_retirement_sha256':digest(WORK/'execution-freeze-retirement.json'),
        'native_requests_to_date':0,'GPU_provider_loads_to_date':1,'additional_native_or_GPU_loads_this_check':0,
        'old_owned_provider_absent':True,'actual_gpu_processes_after':gpu,'candidate_protocol_or_model_changes':False}
    HANDOFF_PROOF.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C38 handoff:originalrelay_metadata RED;current research scripts GREEN;actual child argv parent-SHA rejection passed;0newnative/load')


if __name__ == '__main__':
    main()
