"""Fixed-round, exact-output full-component timing; no generation/TTS timing."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import time

import numpy as np
import avatar.face.lipsync as current
from avatar.utils.audio import downsample_for_analysis, load_wav
from evaluate_analytic_lipsync import legacy, synthesize
from evaluate_real_interaction import save, sha

SPEC=Path('evals/audio/cycle-06/performance-protocol.json')


def fingerprint(frames):
    values=[[f.time,f.mouth_open,f.vowel,f.energy] for f in frames]
    return hashlib.sha256(json.dumps(values,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),values


def run(output):
    if output.exists():raise FileExistsError(output)
    spec=json.loads(SPEC.read_text());source_spec=json.loads(Path('evals/audio/cycle-05/analytic-formants.json').read_text())
    allowed=sorted(os.sched_getaffinity(0));os.sched_setaffinity(0,{allowed[-1]})
    baseline,baseline_sha=legacy(spec['baseline_revision'])
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'source_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'scope':'Single CPU full LipSyncEngine.analyze only; same existing reading audio has no phoneme gold labels',
        'protocol':spec,'protocol_sha256':sha(SPEC),'baseline_engine_sha256':baseline_sha,
        'candidate_engine_sha256':sha('src/avatar/face/lipsync.py'),'script_sha256':sha(__file__),
        'host':platform.platform(),'numpy':np.__version__,'affinity_before':allowed,'affinity_used':sorted(os.sched_getaffinity(0)),
        'thread_environment':{key:os.environ.get(key) for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS']},
        'inputs':[],'cold':[],'rounds':[],'failure':None,'engineering_gate_passed':False,'human_quality_approved':False}
    save(output,report);inputs=[]
    try:
        for key in report['thread_environment']:
            if report['thread_environment'][key]!='1':raise ValueError('Use single-thread numerical environment')
        for index,item in enumerate(spec['analytic_inputs']):
            sr=item['sample_rate'];signal=synthesize(source_spec,source_spec['anchors'][item['anchor_index']],sr,
                item['excitation'],item['f0'],item['rms'],item['seed'])
            for route in spec['analytic_routes']:
                samples,rate=downsample_for_analysis(signal,sr) if route=='web_analysis_16k' else (signal,sr)
                inputs.append((f'analytic{index}:{route}',samples,rate))
        for item in spec['archived_reading_inputs']:
            if sha(item['path'])!=item['audio_sha256']:raise ValueError('Reading source hash mismatch')
            samples,rate=load_wav(item['path']);samples,rate=downsample_for_analysis(samples,rate)
            inputs.append((item['id'],samples,rate))
        report['inputs']=[{'id':name,'analysis_rate':sr,'samples':len(samples),'seconds':len(samples)/sr,
            'pcm_sha256':hashlib.sha256(samples.tobytes()).hexdigest()} for name,samples,sr in inputs]
        reference={}
        modules={'baseline':baseline,'candidate':current}
        def measure(arm,keep_reference=False):
            engine=modules[arm].LipSyncEngine();rows=[]
            for name,samples,rate in inputs:
                start=time.perf_counter();frames=engine.analyze(samples,rate);elapsed=time.perf_counter()-start
                digest,values=fingerprint(frames)
                if keep_reference:reference[name]=digest
                if digest!=reference[name]:raise AssertionError('Full output mismatch: '+name+' '+arm)
                row={'id':name,'analysis_seconds':elapsed,'frame_count':len(frames),'output_sha256':digest}
                if keep_reference:row['frames']=values
                rows.append(row)
            return {'arm':arm,'analysis_seconds':sum(row['analysis_seconds'] for row in rows),'inputs':rows}
        current._formant_basis.cache_clear()
        report['cold'].append(measure('baseline',True));report['cold'].append(measure('candidate'))
        save(output,report)
        for index in range(spec['rounds']):
            order=['baseline','candidate'] if index%2==0 else ['candidate','baseline']
            round_={'round':index+1,'order':order,'arms':[measure(arm) for arm in order]}
            report['rounds'].append(round_);save(output,report)
            print(index+1,{row['arm']:round(row['analysis_seconds'],6) for row in round_['arms']},flush=True)
        values={arm:[next(value['analysis_seconds'] for value in row['arms'] if value['arm']==arm) for row in report['rounds']] for arm in modules}
        summary={arm:{'median_seconds':statistics.median(seconds),'min_seconds':min(seconds),'max_seconds':max(seconds)} for arm,seconds in values.items()}
        speedup=summary['baseline']['median_seconds']/summary['candidate']['median_seconds']
        cache=current._formant_basis.cache_info()._asdict()
        report.update(summary=summary,median_speedup=speedup,cache=cache,exact_outputs=True,
            engineering_gate_passed=speedup>=spec['median_speedup_gate'] and cache['currsize']<=8)
    except Exception as exc:
        report['failure']=type(exc).__name__+': '+str(exc);raise
    finally:
        save(output,report)
    print(json.dumps({key:report[key] for key in ['summary','median_speedup','cache','engineering_gate_passed']},ensure_ascii=False),flush=True)
    if not report['engineering_gate_passed']:raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.output)
