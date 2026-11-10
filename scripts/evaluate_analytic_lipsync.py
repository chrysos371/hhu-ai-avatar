"""Deterministic analytic signal mechanics, not labelled human speech."""
import argparse
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys
import time
import types

import numpy as np
from avatar.utils.audio import frame_signal, downsample_for_analysis
import avatar.face.lipsync as current
from evaluate_real_interaction import sha, save

SPEC=Path('evals/audio/cycle-05/analytic-formants.json')


def synthesize(spec, anchor, sr, excitation, f0, rms, seed):
    n=int(sr*spec['duration_seconds']);t=np.arange(n)/sr
    if excitation=='white_noise':source=np.random.default_rng(seed).normal(size=n)
    else:
        source=np.zeros(n)
        for k in range(1,int(min(5000,sr/2)/f0)):
            source+=np.cos(2*np.pi*k*f0*t)/k
    source-=source.mean()
    z=np.exp(-2j*np.pi*np.fft.rfftfreq(n))
    denominator=np.ones(z.shape,dtype=np.complex128)
    for f,bw in zip(anchor['formants_hz'],spec['bandwidths_hz']):
        radius=np.exp(-np.pi*bw/sr)
        denominator*=1-2*radius*np.cos(2*np.pi*f/sr)*z+radius*radius*z*z
    signal=np.fft.irfft(np.fft.rfft(source)/denominator,n=n)
    signal*=rms/np.sqrt(np.mean(signal*signal))
    if not np.isfinite(signal).all() or np.max(np.abs(signal))>=1:
        raise ValueError('Synthetic source violates finite PCM range')
    return signal.astype(np.float32)


def legacy(revision):
    source=subprocess.check_output(['git','show',revision+':src/avatar/face/lipsync.py'],text=True)
    module=types.ModuleType('avatar.face._analytic_baseline');module.__package__='avatar.face'
    sys.modules[module.__name__]=module
    exec(compile(source,revision+':lipsync.py','exec'),module.__dict__)
    return module,hashlib.sha256(source.encode()).hexdigest()


def run(split,arm,output):
    if output.exists():raise FileExistsError('Evidence output must be fresh')
    spec=json.loads(SPEC.read_text())
    engine_module,engine_sha=legacy(spec['baseline_revision']) if arm=='baseline' else (current,sha('src/avatar/face/lipsync.py'))
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'source_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'scope':spec['scope'],'protocol':spec,'spec_sha256':sha(SPEC),'split':split,'arm':arm,
        'engine_sha256':engine_sha,'script_sha256':sha(__file__),'audio_utils_sha256':sha('src/avatar/utils/audio.py'),
        'rows':[],'summary':{},'execution_complete':False,'human_or_semantic_approved':False,'failure':None}
    save(output,report);started=time.perf_counter()
    try:
        for anchor,sr,rms,excitation in itertools.product(spec['anchors'],spec['sample_rates'],spec['target_rms'],spec['excitations']):
            pitches=spec['fundamentals_hz'] if excitation=='harmonic' else spec['fundamentals_hz'][:1]
            for pitch in pitches:
                signal=synthesize(spec,anchor,sr,excitation,pitch,rms,spec[split+'_seed'])
                waveform_sha=hashlib.sha256(signal.tobytes()).hexdigest()
                for route in spec['routes']:
                    audio,rate=downsample_for_analysis(signal,sr) if route=='web_analysis_16k' else (signal,sr)
                    start=time.perf_counter();frames=engine_module.LipSyncEngine().analyze(audio,rate)
                    seconds=time.perf_counter()-start
                    interior=[f for f in frames if spec['interior_seconds'][0]<=f.time<=spec['interior_seconds'][1]]
                    assert interior and all(np.isfinite(f.mouth_open) and 0<=f.mouth_open<=1 for f in frames)
                    median=float(np.median([f.mouth_open for f in interior]))
                    closures=sum(f.mouth_open<.25*median for f in interior) if median>=.3 else 0
                    analysis_frames=frame_signal(audio,sr=rate)
                    estimated=[]
                    for seconds_ in spec['generation']['formant_samples_seconds']:
                        index=round(seconds_/.01)
                        formants=engine_module._formants(engine_module._lpc(analysis_frames[index],min(2+rate//1000,24)),rate)
                        estimated.append([seconds_,*[float(x) for x in formants[:2]]])
                    errors=[abs(estimate[i+1]-anchor['formants_hz'][i]) for estimate in estimated if len(estimate)==3 for i in range(2)]
                    row={'anchor':anchor['id'],'sample_rate':sr,'analysis_rate':rate,'rms':rms,
                        'excitation':excitation,'f0':pitch,'route':route,'waveform_sha256':waveform_sha,
                        'frame_count':len(frames),'interior_count':len(interior),'correct_vowel_frames':sum(f.vowel==anchor['id'] for f in interior),
                        'confusion':dict(Counter(f.vowel or 'unknown' for f in interior)),
                        'sudden_closures':closures,'closure_eligible':median>=.3,'median_mouth_open':median,
                        'formant_samples':estimated,'median_abs_formant_error_hz':float(np.median(errors)) if errors else None,
                        'seconds':seconds,'frames':[[f.time,f.mouth_open,f.vowel,f.energy] for f in frames]}
                    report['rows'].append(row)
                print(split,arm,anchor['id'],sr,rms,excitation,pitch,flush=True)
                save(output,report)
        silence=[]
        for sr in spec['sample_rates']:
            for kind,signal in [('zero',np.zeros(sr,dtype=np.float32)),('low_noise',np.random.default_rng(17).normal(0,.0003,sr).astype(np.float32))]:
                frames=engine_module.LipSyncEngine().analyze(signal,sr)
                silence.append({'sample_rate':sr,'kind':kind,'all_closed':all(f.mouth_open==0 for f in frames)})
        report['silence']=silence
        for route in spec['routes']:
            rows=[r for r in report['rows'] if r['route']==route]
            total=sum(r['interior_count'] for r in rows)
            eligible=sum(r['interior_count'] for r in rows if r['closure_eligible'])
            report['summary'][route]={'cases':len(rows),'vowel_frame_accuracy':sum(r['correct_vowel_frames'] for r in rows)/total,
                'median_case_accuracy':float(np.median([r['correct_vowel_frames']/r['interior_count'] for r in rows])),
                'sudden_closures':sum(r['sudden_closures'] for r in rows),'closure_eligible_frames':eligible,
                'sudden_closure_rate':sum(r['sudden_closures'] for r in rows)/eligible if eligible else 0,
                'median_abs_formant_error_hz':float(np.median([r['median_abs_formant_error_hz'] for r in rows if r['median_abs_formant_error_hz'] is not None])),
                'analysis_seconds':sum(r['seconds'] for r in rows)}
        report['execution_complete']=True
    except Exception as exc:
        report['failure']=type(exc).__name__+': '+str(exc)
        raise
    finally:
        report['seconds']=time.perf_counter()-started;save(output,report)
        print(json.dumps({'summary':report['summary'],'failure':report['failure']},ensure_ascii=False),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--split',choices=['development','validation'],required=True)
    p.add_argument('--arm',choices=['baseline','candidate'],required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();run(args.split,args.arm,args.output)
