"""Absolute cosmetic target scheduling; no default speech-motion quality claim."""
import argparse
import json
from pathlib import Path
import subprocess
import numpy as np
from evaluate_analytic_lipsync import synthesize,legacy
from evaluate_real_interaction import save,sha
from avatar.face.lipsync import LipSyncEngine
SPEC=Path('evals/audio/cycle-07/cosmetic-timer.json')


def run(arm,output):
    if output.exists():raise FileExistsError(output)
    spec=json.loads(SPEC.read_text());source=json.loads(Path('evals/audio/cycle-05/analytic-formants.json').read_text())
    module,digest=legacy(spec['baseline_revision']) if arm=='baseline' else (None,sha('src/avatar/face/lipsync.py'))
    cls=module.LipSyncEngine if module else LipSyncEngine
    rows=[]
    for case in spec['cases']:
        settings=dict(source);settings['duration_seconds']=case['duration_seconds'];sr=case['sample_rate'];period=case['period_seconds']
        signal=synthesize(settings,settings['anchors'][0],sr,'harmonic',100,.12,11)
        plain=cls().analyze(signal,sr);decor=cls(close_every=period).analyze(signal,sr)
        hop=int(sr*.01);last=plain[-1].time
        targets=[k*period for k in range(1,int(last/period)+1)]
        expected=sorted(set(max(1,round(target*sr/hop)) for target in targets))
        expected=[i for i in expected if i<len(plain) and plain[i].mouth_open>.3]
        actual=[i for i,(a,b) in enumerate(zip(plain,decor)) if a.mouth_open!=b.mouth_open]
        rows.append(case|{'hop_samples':hop,'frame_count':len(plain),'expected_indices':expected,'actual_indices':actual,
            'expected_times':[plain[i].time for i in expected],'actual_times':[decor[i].time for i in actual],
            'exact_schedule':actual==expected,'plain_frames':[[f.time,f.mouth_open,f.vowel,f.energy] for f in plain],
            'decor_frames':[[f.time,f.mouth_open,f.vowel,f.energy] for f in decor]})
    report={'source_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'arm':arm,
        'protocol_sha256':sha(SPEC),'engine_sha256':digest,'script_sha256':sha(__file__),'rows':rows,
        'passed':all(row['exact_schedule'] for row in rows),'naturalness_approved':False}
    save(output,report);print(json.dumps({'passed':report['passed'],'counts':[(len(r['expected_indices']),len(r['actual_indices'])) for r in rows]}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--arm',choices=['baseline','candidate'],required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args();run(args.arm,args.output)
