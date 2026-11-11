"""Fixed spectral candidates on known analytic signals; no production mutation."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import time

import numpy as np
from avatar.face.lipsync import _lpc, _formants, _classify_vowel
from avatar.utils.audio import frame_signal, downsample_for_analysis
from evaluate_analytic_lipsync import synthesize
from evaluate_real_interaction import save, sha

PROTOCOL=Path('evals/audio/cycle-06/formant-protocol.json')


def roots400(coefficients,sr):
    poles=np.roots(coefficients)
    poles=poles[(poles.imag>1e-6)&(np.abs(poles)>0)&(np.abs(poles)<1)]
    frequency=np.angle(poles)*sr/(2*np.pi)
    bandwidth=-sr*np.log(np.abs(poles))/np.pi
    return np.sort(frequency[(frequency>200)&(frequency<4000)&(bandwidth>0)&(bandwidth<=400)])


def extract(arm,coefficients,sr,legacy=None):
    if arm=='legacy':return _formants(coefficients,sr)
    if arm=='roots400':return roots400(coefficients,sr)
    if arm=='dense10':return _formants(coefficients,sr,n_fft=max(512,int(np.ceil(sr/20))+1))
    if arm!='fallback50':raise ValueError(arm)
    old=_formants(coefficients,sr) if legacy is None else legacy
    if len(old)>=2:return old
    roots=roots400(coefficients,sr)
    return roots if len(old) and len(roots)>=2 and abs(old[0]-roots[0])<=50 else old


def run(output):
    if output.exists():raise FileExistsError(output)
    protocol=json.loads(PROTOCOL.read_text());spec_path=Path(protocol['development_suite'])
    spec=json.loads(spec_path.read_text());arms=[item['id'] for item in protocol['arms']]
    report={'created_utc':datetime.now(timezone.utc).isoformat(),'source_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'protocol':protocol,'protocol_sha256':sha(PROTOCOL),'spec_sha256':sha(spec_path),
        'source_sha256':{str(p):sha(p) for p in [Path(__file__),Path('src/avatar/face/lipsync.py'),Path('scripts/evaluate_analytic_lipsync.py')]},
        'scope':'Known synthetic development regression only; prospective signals remain sealed',
        'rows':[],'summary':{},'selection':None,'execution_complete':False,'human_approved':False,'failure':None}
    save(output,report);started=time.perf_counter()
    try:
        for anchor,sr,rms,excitation in itertools.product(spec['anchors'],spec['sample_rates'],spec['target_rms'],spec['excitations']):
            pitches=spec['fundamentals_hz'] if excitation=='harmonic' else spec['fundamentals_hz'][:1]
            for f0 in pitches:
                waveform=synthesize(spec,anchor,sr,excitation,f0,rms,protocol['development_seed'])
                for route in spec['routes']:
                    samples,rate=downsample_for_analysis(waveform,sr) if route=='web_analysis_16k' else (waveform,sr)
                    frames=frame_signal(samples,sr=rate)
                    data={arm:[] for arm in arms}
                    for index,frame in enumerate(frames):
                        t=index*.01
                        if not .1<=t<=.65:continue
                        coefficients=_lpc(frame,min(2+rate//1000,24))
                        old=extract('legacy',coefficients,rate)
                        for arm in arms:
                            frequencies=old if arm=='legacy' else extract(arm,coefficients,rate,old)
                            f1=float(frequencies[0]) if len(frequencies)>0 else None
                            f2=float(frequencies[1]) if len(frequencies)>1 else None
                            data[arm].append([t,f1,f2,_classify_vowel(f1,f2)])
                    row={'anchor':anchor['id'],'sample_rate':sr,'analysis_rate':rate,'rms':rms,'excitation':excitation,
                        'f0':f0,'route':route,'waveform_sha256':hashlib.sha256(waveform.tobytes()).hexdigest(),'arms':{}}
                    for arm,values in data.items():
                        old_values=data['legacy']
                        row['arms'][arm]={'correct':sum(value[3]==anchor['id'] for value in values),'count':len(values),
                            'missing_f2':sum(value[2] is None for value in values),
                            'newly_wrong_from_unknown':sum(old[3] is None and value[3] is not None and value[3]!=anchor['id'] for old,value in zip(old_values,values)),
                            'f1_errors':[abs(value[1]-anchor['formants_hz'][0]) for value in values if value[1] is not None],
                            'f2_errors':[abs(value[2]-anchor['formants_hz'][1]) for value in values if value[2] is not None],
                            'confusion':dict(Counter(value[3] or 'unknown' for value in values)),'estimates':values}
                    report['rows'].append(row)
                print(anchor['id'],sr,rms,excitation,f0,flush=True);save(output,report)
        gates={arm:[] for arm in arms if arm!='legacy'}
        for route in spec['routes']:
            rows=[row for row in report['rows'] if row['route']==route]
            report['summary'][route]={}
            for arm in arms:
                values=[row['arms'][arm] for row in rows]
                summary={'case_count':len(rows),'frames':sum(value['count'] for value in values),
                    'correct':sum(value['correct'] for value in values),'missing_f2':sum(value['missing_f2'] for value in values),
                    'newly_wrong_from_unknown':sum(value['newly_wrong_from_unknown'] for value in values),
                    'case_regressions':sum(row['arms'][arm]['correct']<row['arms']['legacy']['correct'] for row in rows),
                    'median_f1_error_hz':float(np.median([error for value in values for error in value['f1_errors']])),
                    'median_f2_error_hz':float(np.median([error for value in values for error in value['f2_errors']]))}
                summary['frame_accuracy']=summary['correct']/summary['frames']
                report['summary'][route][arm]=summary
            baseline=report['summary'][route]['legacy']
            for arm in gates:
                candidate=report['summary'][route][arm]
                gates[arm].append(candidate['case_regressions']==0 and candidate['newly_wrong_from_unknown']==0
                    and candidate['missing_f2']<baseline['missing_f2']
                    and candidate['median_f1_error_hz']<=baseline['median_f1_error_hz']
                    and candidate['median_f2_error_hz']<=baseline['median_f2_error_hz'])
        report['candidate_gates']={arm:all(values) for arm,values in gates.items()}
        report['selection']=next((arm for arm in ['fallback50','roots400','dense10'] if report['candidate_gates'][arm]),None)
        report['execution_complete']=True
    except Exception as exc:
        report['failure']=type(exc).__name__+': '+str(exc);raise
    finally:
        report['seconds']=time.perf_counter()-started;save(output,report)
        print(json.dumps({'summary':report['summary'],'selection':report['selection'],'failure':report['failure']},ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.output)
