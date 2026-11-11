"""Post-development reanalysis; preserve failed raw estimates and labels."""
import argparse
import json
from pathlib import Path
import numpy as np
from avatar.face.lipsync import _classify_vowel
from evaluate_real_interaction import save, sha

PROTOCOL=Path('evals/audio/cycle-06/conservative-refinement.json')


def run(source,output):
    if output.exists():raise FileExistsError(output)
    report=json.loads(source.read_text());assert report['execution_complete']
    result={'scope':'Known development reanalysis only, not unseen validation','source_sha256':sha(source),
        'protocol_sha256':sha(PROTOCOL),'protocol':json.loads(PROTOCOL.read_text()),
        'rows':[],'summary':{},'selected':False,'human_approved':False}
    probes=[500.,1500.,2500.]
    spec=json.loads(Path(report['protocol']['development_suite']).read_text())
    for row in report['rows']:
        old=row['arms']['legacy']['estimates'];candidate=row['arms']['fallback50']['estimates']
        refined=[]
        for a,b in zip(old,candidate):
            reject=a[2] is None and b[2] is not None and any(_classify_vowel(a[1],f2)!=_classify_vowel(b[1],f2) for f2 in probes)
            refined.append(a if reject else b)
        # Development errors must use the ORIGINAL cycle05 points, not the sealed prospective ones.
        anchor=next(a for a in spec['anchors'] if a['id']==row['anchor'])
        metrics={'correct':sum(v[3]==row['anchor'] for v in refined),'count':len(refined),
            'missing_f2':sum(v[2] is None for v in refined),
            'newly_wrong_from_unknown':sum(a[3] is None and b[3] is not None and b[3]!=row['anchor'] for a,b in zip(old,refined)),
            'f1_errors':[abs(v[1]-anchor['formants_hz'][0]) for v in refined if v[1] is not None],
            'f2_errors':[abs(v[2]-anchor['formants_hz'][1]) for v in refined if v[2] is not None]}
        result['rows'].append({key:row[key] for key in ['anchor','sample_rate','rms','excitation','f0','route','waveform_sha256']}|
            {'baseline':row['arms']['legacy'],'refined':metrics,'estimates':refined})
    gates=[]
    for route in report['summary']:
        rows=[row for row in result['rows'] if row['route']==route]
        values=[row['refined'] for row in rows]
        summary={'correct':sum(v['correct'] for v in values),'frames':sum(v['count'] for v in values),
            'missing_f2':sum(v['missing_f2'] for v in values),'newly_wrong_from_unknown':sum(v['newly_wrong_from_unknown'] for v in values),
            'case_regressions':sum(row['refined']['correct']<row['baseline']['correct'] for row in rows),
            'median_f1_error_hz':float(np.median([e for v in values for e in v['f1_errors']])),
            'median_f2_error_hz':float(np.median([e for v in values for e in v['f2_errors']]))}
        baseline=report['summary'][route]['legacy'];summary['frame_accuracy']=summary['correct']/summary['frames']
        passed=summary['case_regressions']==0 and summary['newly_wrong_from_unknown']==0 and summary['missing_f2']<baseline['missing_f2'] and all(summary[key]<=baseline[key] for key in ['median_f1_error_hz','median_f2_error_hz'])
        summary['gate_passed']=passed;gates.append(passed);result['summary'][route]=summary
    result['selected']=all(gates);save(output,result)
    print(json.dumps({'summary':result['summary'],'selected':result['selected']},ensure_ascii=False))
    if not result['selected']:raise SystemExit(1)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();run(args.source,args.output)
