"""Actual opt-in component versus pinned legacy; sealed inputs only after selection."""
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
import avatar.face.lipsync as current
from avatar.utils.audio import frame_signal,downsample_for_analysis
from evaluate_analytic_lipsync import synthesize,legacy
from evaluate_real_interaction import save,sha

PROTOCOL=Path('evals/audio/cycle-06/formant-protocol.json')


def run(split,output,development_evidence):
    if output.exists():raise FileExistsError(output)
    protocol=json.loads(PROTOCOL.read_text());original=json.loads(Path(protocol['development_suite']).read_text())
    spec=dict(original);seed=protocol['development_seed'];expected={}
    if split=='prospective':
        proof=json.loads(development_evidence.read_text())
        if not proof['engineering_gate_passed'] or not proof['actual_component_matches_reanalysis']:
            raise ValueError('Actual development component has not passed')
        settings=protocol['prospective']
        for key in ['anchors','sample_rates','target_rms','fundamentals_hz','bandwidths_hz','duration_seconds','excitations']:spec[key]=settings[key]
        seed=settings['seed']
    else:
        proof=json.loads(development_evidence.read_text())
        if not proof['selected']:raise ValueError('Development refinement was not selected')
        key=lambda row:tuple(row[k] for k in ['anchor','sample_rate','rms','excitation','f0','route'])
        expected={key(row):row['estimates'] for row in proof['rows']}
    baseline,baseline_sha=legacy(protocol['baseline_revision'])
    report={'source_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'created_utc':datetime.now(timezone.utc).isoformat(),'protocol_sha256':sha(PROTOCOL),
        'refinement_sha256':sha('evals/audio/cycle-06/conservative-refinement.json'),
        'candidate_engine_sha256':sha('src/avatar/face/lipsync.py'),'baseline_engine_sha256':baseline_sha,
        'script_sha256':sha(__file__),'development_evidence_sha256':sha(development_evidence),
        'split':split,'seed':seed,'scope':'Actual component opt-in on synthetic mechanism fixtures; not human phonetic approval',
        'rows':[],'summary':{},'execution_complete':False,'engineering_gate_passed':False,
        'actual_component_matches_reanalysis':True,'human_approved':False,'failure':None}
    save(output,report);started=time.perf_counter()
    try:
        for anchor,sr,rms,excitation in itertools.product(spec['anchors'],spec['sample_rates'],spec['target_rms'],spec['excitations']):
            pitches=spec['fundamentals_hz'] if excitation=='harmonic' else spec['fundamentals_hz'][:1]
            for f0 in pitches:
                waveform=synthesize(spec,anchor,sr,excitation,f0,rms,seed)
                for route in spec['routes']:
                    samples,rate=downsample_for_analysis(waveform,sr) if route=='web_analysis_16k' else (waveform,sr)
                    outputs={};seconds={}
                    for arm,engine in [('legacy',baseline.LipSyncEngine()),('conservative',current.LipSyncEngine(formant_mode='conservative'))]:
                        start=time.perf_counter();outputs[arm]=engine.analyze(samples,rate);seconds[arm]=time.perf_counter()-start
                    a,b=outputs.values()
                    if len(a)!=len(b) or any(x.time!=y.time or x.energy!=y.energy for x,y in zip(a,b)):
                        raise AssertionError('Timeline or energy changed')
                    analysis_frames=frame_signal(samples,sr=rate);estimates={'legacy':[],'conservative':[]}
                    for index,frame in enumerate(analysis_frames):
                        if not .1<=index*.01<=.65:continue
                        coefficients=current._lpc(frame,min(2+rate//1000,24))
                        for arm,extract in [('legacy',baseline._formants),('conservative',current._conservative_formants)]:
                            frequencies=extract(coefficients,rate)
                            first=float(frequencies[0]) if len(frequencies) else None
                            second=float(frequencies[1]) if len(frequencies)>1 else None
                            v=current._classify_vowel(first,second)
                            if (outputs[arm][index].vowel or None)!=v:raise AssertionError('Actual component and extractor disagree')
                            estimates[arm].append([index*.01,first,second,v])
                    row={'anchor':anchor['id'],'sample_rate':sr,'rms':rms,'excitation':excitation,'f0':f0,'route':route,
                        'waveform_sha256':hashlib.sha256(waveform.tobytes()).hexdigest(),'arms':{},'seconds':seconds}
                    if expected:
                        k=tuple(row[name] for name in ['anchor','sample_rate','rms','excitation','f0','route'])
                        if estimates['conservative']!=expected[k]:
                            report['actual_component_matches_reanalysis']=False
                            raise AssertionError('Actual component differs from prior development reanalysis')
                    for arm,values in estimates.items():
                        interior=[frame for frame in outputs[arm] if .1<=frame.time<=.65]
                        median=float(np.median([frame.mouth_open for frame in interior]))
                        row['arms'][arm]={'count':len(values),'correct':sum(v[3]==anchor['id'] for v in values),
                            'missing_f2':sum(v[2] is None for v in values),
                            'newly_wrong_from_unknown':sum(old[3] is None and value[3] is not None and value[3]!=anchor['id'] for old,value in zip(estimates['legacy'],values)),
                            'confusion':dict(Counter(v[3] or 'unknown' for v in values)),
                            'f1_errors':[abs(v[1]-anchor['formants_hz'][0]) for v in values if v[1] is not None],
                            'f2_errors':[abs(v[2]-anchor['formants_hz'][1]) for v in values if v[2] is not None],
                            'sudden_closures':sum(frame.mouth_open<.25*median for frame in interior) if median>=.3 else 0,
                            'estimates':values,'frames':[[f.time,f.mouth_open,f.vowel,f.energy] for f in outputs[arm]]}
                    report['rows'].append(row)
                save(output,report);print(split,anchor['id'],sr,rms,excitation,f0,flush=True)
        gates=[];motion=[]
        for route in spec['routes']:
            rows=[row for row in report['rows'] if row['route']==route];report['summary'][route]={}
            expected_count=120 if split=='development' else protocol['prospective']['count_per_route']
            if len(rows)!=expected_count:raise AssertionError('Incomplete fixed grid')
            for arm in ['legacy','conservative']:
                values=[row['arms'][arm] for row in rows]
                summary={'cases':len(rows),'frames':sum(v['count'] for v in values),'correct':sum(v['correct'] for v in values),
                    'missing_f2':sum(v['missing_f2'] for v in values),'newly_wrong_from_unknown':sum(v['newly_wrong_from_unknown'] for v in values),
                    'case_regressions':sum(row['arms'][arm]['correct']<row['arms']['legacy']['correct'] for row in rows),
                    'median_f1_error_hz':float(np.median([e for v in values for e in v['f1_errors']])),
                    'median_f2_error_hz':float(np.median([e for v in values for e in v['f2_errors']])),
                    'sudden_closures':sum(v['sudden_closures'] for v in values)}
                summary['frame_accuracy']=summary['correct']/summary['frames'];report['summary'][route][arm]=summary
            base,candidate=report['summary'][route].values()
            gates.append(candidate['case_regressions']==0 and candidate['newly_wrong_from_unknown']==0 and candidate['missing_f2']<base['missing_f2']
                and all(candidate[key]<=base[key] for key in ['median_f1_error_hz','median_f2_error_hz']))
            motion.append(candidate['sudden_closures']<=base['sudden_closures'])
        report['engineering_gate_passed']=all(gates)
        report['motion_no_regression']=all(motion)
        report['execution_complete']=True
    except Exception as exc:
        report['failure']=type(exc).__name__+': '+str(exc);raise
    finally:
        report['seconds']=time.perf_counter()-started;save(output,report)
        print(json.dumps({'summary':report['summary'],'gate':report['engineering_gate_passed'],'failure':report['failure']},ensure_ascii=False),flush=True)
    if not report['engineering_gate_passed']:raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--split',choices=['development','prospective'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--development-evidence',type=Path,required=True)
    args=p.parse_args();run(args.split,args.output,args.development_evidence)
