"""Pair exact synthetic waveforms; do not mistake mechanics for speech quality."""
import argparse
from collections import Counter
import json
from pathlib import Path
from evaluate_real_interaction import sha, save


def compare(baseline, candidate, output):
    if output.exists():raise FileExistsError(output)
    a,b=[json.loads(path.read_text()) for path in [baseline,candidate]]
    assert a['execution_complete'] and b['execution_complete']
    assert a['spec_sha256']==b['spec_sha256'] and a['split']==b['split']
    key=lambda row:tuple(row[name] for name in ['anchor','sample_rate','rms','excitation','f0','route'])
    aa,bb=[{key(row):row for row in report['rows']} for report in [a,b]]
    assert len(aa)==len(a['rows'])==len(bb)==len(b['rows'])==240
    assert aa.keys()==bb.keys()
    waveform_equal=all(aa[k]['waveform_sha256']==bb[k]['waveform_sha256'] for k in aa)
    classification_equal=all(
        len(aa[k]['frames'])==len(bb[k]['frames']) and
        all(x[0]==y[0] and x[2:]==y[2:] for x,y in zip(aa[k]['frames'],bb[k]['frames'])) for k in aa)
    regressions=[list(k) for k in aa if bb[k]['correct_vowel_frames']<aa[k]['correct_vowel_frames']]
    closure_regressions=[list(k) for k in aa if bb[k]['sudden_closures']>aa[k]['sudden_closures']]
    silence=all(row['all_closed'] for report in [a,b] for row in report['silence'])
    result={'scope':'Identical synthetic waveforms and source geometry; not human or semantic approval',
        'split':a['split'],'baseline_sha256':sha(baseline),'candidate_sha256':sha(candidate),
        'identical_waveforms':waveform_equal,'identical_frame_time_vowel_energy':classification_equal,
        'classification_case_regressions':regressions,'sudden_closure_case_regressions':closure_regressions,
        'silence_all_closed':silence,'baseline_summary':a['summary'],'candidate_summary':b['summary'],
        'engineering_gate_passed':waveform_equal and classification_equal and not regressions and not closure_regressions and silence,
        'validation_novelty':b.get('validation_novelty'), 'human_or_semantic_approved':False,
        'candidate_split_use':b.get('split_use',b['split']),
        'counts_per_route':dict(Counter(row['route'] for row in a['rows']))}
    save(output,result);print(json.dumps(result,ensure_ascii=False,indent=2))
    if not result['engineering_gate_passed']:raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();compare(args.baseline,args.candidate,args.output)
