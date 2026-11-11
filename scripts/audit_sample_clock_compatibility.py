"""Known cycle06 signals: acoustic fields exact, timeline independently correct."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np
from avatar.face.lipsync import LipSyncEngine
from avatar.utils.audio import downsample_for_analysis
from evaluate_analytic_lipsync import synthesize
from evaluate_real_interaction import save,sha


def run(source,output):
    if output.exists():raise FileExistsError(output)
    old=json.loads(source.read_text());assert old['execution_complete']
    protocol=json.loads(Path('evals/audio/cycle-06/formant-protocol.json').read_text())
    spec=json.loads(Path(protocol['development_suite']).read_text());settings=protocol['prospective']
    for field in ['anchors','bandwidths_hz','duration_seconds']:spec[field]=settings[field]
    report={'scope':'Previously executed cycle06 synthetic waveforms; known regression, zero new examples',
        'source_head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
        'baseline_evidence_sha256':sha(source),'engine_sha256':sha('src/avatar/face/lipsync.py'),
        'script_sha256':sha(__file__),'rows':[],'execution_complete':False,'passed':False,'new_examples':0}
    save(output,report)
    for row in old['rows']:
        sr=row['sample_rate'];anchor=next(item for item in settings['anchors'] if item['id']==row['anchor'])
        waveform=synthesize(spec,anchor,sr,row['excitation'],row['f0'],row['rms'],settings['seed'])
        assert hashlib.sha256(waveform.tobytes()).hexdigest()==row['waveform_sha256']
        samples,rate=downsample_for_analysis(waveform,sr) if row['route']=='web_analysis_16k' else (waveform,sr)
        frames=LipSyncEngine().analyze(samples,rate)
        previous=row['arms']['legacy']['frames'];current=[[f.time,f.mouth_open,f.vowel,f.energy] for f in frames]
        count_equal=len(previous)==len(current)
        acoustic_equal=count_equal and all(a[1:]==b[1:] for a,b in zip(previous,current))
        hop=int(rate*.01);window=int(rate*.025)
        error=max(abs(f.time*rate-i*hop) for i,f in enumerate(frames))
        old_error=max(abs(f[0]*rate-i*hop) for i,f in enumerate(previous))
        integral=rate*.01==hop
        timestamps_preserved=all(a[0]==b[0] for a,b in zip(previous,current))
        within=frames[-1].time*rate+window<=len(samples)+1e-6
        passed=count_equal and acoustic_equal and error<=1e-6 and within and (not integral or timestamps_preserved)
        report['rows'].append({key:row[key] for key in ['anchor','sample_rate','rms','excitation','f0','route','waveform_sha256']}|
            {'frame_count':len(frames),'acoustic_fields_equal':acoustic_equal,'integral_hop':integral,
             'timestamps_preserved':timestamps_preserved,'old_max_error_ms':old_error/rate*1000,
             'new_max_error_ms':error/rate*1000,'passed':passed,'frames':current})
    assert len(report['rows'])==160
    report.update(execution_complete=True,passed=all(row['passed'] for row in report['rows']))
    save(output,report)
    print(json.dumps({'passed':report['passed'],'rows':len(report['rows']),'all_acoustic_fields_equal':all(row['acoustic_fields_equal'] for row in report['rows'])}))
    if not report['passed']:raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline-evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();run(args.baseline_evidence,args.output)
