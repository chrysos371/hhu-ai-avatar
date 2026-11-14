"""Audit a genuinely absent interrupted worker; never restart or certify its phase."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

ROOT=Path('/data/Users/zrh/repo/hhu-ai-avatar')
BASE=ROOT/'docs/进展报告/2026-11-10-G2交互循环/cycle-54'
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE/'审计'))
from execution_common import RUN,WORK,LOCK,CASES,read,sha,require,write_new,verify_freeze
sys.path.insert(1,str(BASE.parent/'cycle-52/审计'))
sys.path.insert(2,str(BASE.parent/'cycle-52/审计/工作目录/006-调用结束态核验'))
from capture_transformers import validate_call
from trace_transition import validate_transition
from replay_common import case_for_replay,inspect_observations
from avatar.lab.runner import local_model


def main():
    require(not (HERE/'retirement-v1.json').exists(),'retirement already recorded')
    frozen=verify_freeze(WORK/'freeze-v1.json','e1fe8b92d38ef71bb05f619cbd3a045a1d7453a70f04bbbbfb2c734435a74d56')
    marker=read(RUN/'ledger/base-start.json');pid=marker['pid']
    proc=Path(f'/proc/{pid}')
    require(not proc.exists(),'original worker still present; wait rather than restart')
    GPU=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,gpu_uuid,used_memory','--format=csv,noheader,nounits'],text=True)
    own=[line for line in GPU.splitlines() if line.split(',')[0].strip()==str(pid)]
    require(not own,'original PID still owns GPU memory')
    live=[]
    script='docs/进展报告/2026-11-10-G2交互循环/cycle-54/审计/run_execution.py'
    for candidate in Path('/proc').glob('[0-9]*/cmdline'):
        try:args=candidate.read_bytes().decode().split('\0')
        except (OSError,UnicodeError):continue
        if args and 'python' in Path(args[0]).name and any(a==script or a==str(ROOT/script) for a in args):live.append(str(candidate.parent))
    require(not live,'another C54 real runner remains live')
    require(not (RUN/'base/process-result.json').exists() and not (RUN/'ledger/base-verified.json').exists(),
        'unexpected complete/verified stage record')
    require(sorted(p.name for p in (RUN/'ledger').glob('*-start.json'))==['base-start.json'],
        'unexpected later stage attempt')
    evaluation=read(RUN/'base/evaluation.json')
    require(evaluation['completed'] is False and evaluation['actual_trials']==13,'partial evaluation differs')
    from transformers import AutoTokenizer
    entry=next(e for e in read(LOCK)['models'] if e['name']=='4b')
    tokenizer=AutoTokenizer.from_pretrained(local_model(entry),local_files_only=True,trust_remote_code=False)
    traces=RUN/'base/actual-generate';completed=[]
    for ordinal in range(1,29):
        start=read(traces/f'{ordinal:04}-entry.json');row=read(traces/f'{ordinal:04}-result.json')
        validate_transition(start,row);validate_call(row)
        require(row['fixture'] is False and row['actual_generate_entries']==1,'nonactual complete boundary')
        expected=tokenizer.apply_chat_template(row['messages'],tokenize=True,add_generation_prompt=True,enable_thinking=False)
        require(row['input_ids']==[expected],'actual input/template mismatch')
        out=row['actual_output_ids'][0];tokens=out[len(expected):]
        require(out[:len(expected)]==expected and tokenizer.decode(tokens,skip_special_tokens=True)==row['backend_result']['reply'],
            'actual output reconstruction mismatch')
        completed.append({'ordinal':ordinal,'kind':row['kind'],'new_tokens':len(tokens),
            'result_sha256':sha(traces/f'{ordinal:04}-result.json')})
    pending=read(traces/'0029-entry.json');validate_call(pending)
    require(pending['ordinal']==29 and pending['completed'] is False and pending['kind']=='analysis'
        and not (traces/'0029-result.json').exists(),'incomplete call identity differs')
    require(len(list(traces.glob('*-entry.json')))==29 and len(list(traces.glob('*-result.json')))==28,'boundary counts differ')
    cases={c['id']:case_for_replay(c) for c in read(CASES)['cases']};receipts=[];SQL=0
    for path in sorted((RUN/'base').glob('repetition-*/*/receipt.json')):
        row=read(path);case=cases[row['case']]
        count=inspect_observations(path.parent,row,case,'production_snapshot');require(count==2,'complete trial SQL mismatch')
        SQL+=count;receipts.append({'case':row['case'],'receipt':str(path),'sha256':sha(path),'SQL_reconstructed':count})
    require(len(receipts)==13 and SQL==26,'completed trial count differs')
    partial=RUN/'base/repetition-1'/pending['context']['case'];sql=partial/'after-query-1.sql'
    require(sql.is_file() and not (partial/'receipt.json').exists(),'partial query snapshot differs')
    connection=sqlite3.connect(':memory:');connection.executescript(sql.read_text());connection.close()
    require(len(list((RUN/'base').glob('repetition-*/*/*.sql')))==27,'total partial SQL count differs')
    files={str(p.relative_to(RUN)):sha(p) for p in RUN.rglob('*') if p.is_file()}
    require(len(files)==100,'raw interrupted snapshot file count differs')
    snapshot=Path('/data/Users/zrh/data/hhu-ai-avatar/artifacts/c54/process-retirement-v1')
    require(not snapshot.exists(),'external retirement snapshot already exists');snapshot.mkdir(parents=True)
    write_new(snapshot/'raw-files.json',files)
    import torch
    require(not torch.cuda.is_initialized(),'CPU audit initialized CUDA')
    result={'verified':True,'scope':'interrupted C54 base forensic retirement only; phase incomplete and not quality-approved',
        'verifier_sha256':sha(Path(__file__)),'freeze_sha256':sha(WORK/'freeze-v1.json'),'frozen_inputs_unchanged':len(frozen['sha256']),
        'worker_pid':pid,'original_process_absent':True,'own_GPU_rows_after_exit':own,'other_C54_runners_live':live,
        'worker_actual_exit_code':None,'worker_exit_code_unavailable':True,'tool_handle_missing':True,
        'observed_interruption_context':'conversation turn was externally aborted; worker disappeared without Python terminal receipt',
        'normal_worker_terminal_receipt_present':False,'actual_complete_generate_results':28,'formal_complete_generate_results':26,
        'warmup_complete_generate_results':2,'captured_generate_entry_boundaries':29,'incomplete_boundary_entries':1,
        'incomplete_boundary_original_generate_completion_unknown':True,'incomplete_case':pending['context']['case'],
        'completed_Avatar_trials':13,'completed_trial_SQL_reconstructed':26,'additional_partial_query_SQL_snapshots':1,
        'raw_SQL_files_parsed_or_reconstructed':27,'raw_files':100,'external_raw_manifest':str(snapshot/'raw-files.json'),
        'external_raw_manifest_sha256':sha(snapshot/'raw-files.json'),'completed_generations':completed,'completed_trial_receipts':receipts,
        'new_training_steps':0,'new_adapter_created':False,'later_stages_attempted':False,
        'stage_execution_verified':False,'experiment_retired_incomplete':True,'same_C54_stage_restart_authorized':False,
        'semantic_gain_or_model_failure_inferred':False,'new_audit_LLM_calls':0,'audit_CUDA_initialized':False,'goal_active':True}
    write_new(HERE/'retirement-v1.json',result)
    print('C54 retired INCOMPLETE:PID absent/GPU released;28 complete+1 incomplete boundary;13 trials/27 SQL/100 files;507inputs unchanged;exitcode unknown;no restart')


if __name__=='__main__':main()
