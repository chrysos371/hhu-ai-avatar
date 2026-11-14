"""Actual candidate-screening red/fixed evidence; synthetic CPU fixtures, no training."""
import argparse
import hashlib
import json
from pathlib import Path

from avatar.lab import data

ROOT=Path(__file__).resolve().parents[5]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expect',choices=('red','fixed'),required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();assert not args.output.exists()
    texts,hashes=data.evaluation_texts()
    path=ROOT/'evals/interaction/cycle-50/natural-history-cases.json'
    material=json.loads(path.read_text());case=material['cases'][0]
    policy={'c51-controlled':{'language':'zh','use':'experimental-sft'}}
    def screen(text,ident):
        row=data.normalize_dialogue('c51-controlled','train',ident,
            [text,'这是一段仅用于检查数据隔离的受控参考回复。'])
        accepted,rejected=data.screen_candidates([row],texts,source_policy=policy)
        return {'input':text,'accepted':bool(accepted),'reasons':rejected[0]['reasons'] if rejected else []}
    actual=screen(case['followup_text'],'actual-c50-case')
    unrelated=screen('帮我写一条短信文案，提醒同伴带上指南针去观察山顶的星座。','unrelated')
    legacy=screen('我喜欢喝可乐。请帮我写一封信。','legacy-named-fixture')
    coverage=[];screened=[]
    for number,name in [(47,'native-history-cases.json'),(48,'typed-history-cases.json'),(49,'minimal-history-cases.json'),(50,'natural-history-cases.json')]:
        p=ROOT/f'evals/interaction/cycle-{number}'/name;cases=json.loads(p.read_text())['cases']
        inputs=[c[k] for c in cases for k in ('query_text','followup_text')]
        coverage.append({'file':str(p.relative_to(ROOT)),'protected_hash':str(p.relative_to(ROOT)) in hashes,
            'input_occurrences':len(inputs),'included_occurrences':sum(t in texts for t in inputs)})
        if args.expect=='fixed':screened.extend(screen(t,f'c{number}-{i}') for i,t in enumerate(inputs))
    assert unrelated['accepted'] and not legacy['accepted'] and 'eval_overlap' in legacy['reasons']
    if args.expect=='red':
        assert actual['accepted'] and not all(r['protected_hash'] for r in coverage)
    else:
        assert not actual['accepted'] and 'eval_overlap' in actual['reasons']
        assert all(r['protected_hash'] and r['included_occurrences']==r['input_occurrences'] for r in coverage)
        assert len(screened)==100 and all(not r['accepted'] and 'eval_overlap' in r['reasons'] for r in screened)
    result={'verified':True,'expected_behavior':args.expect,'screening_code_sha256':hashlib.sha256(Path(data.__file__).read_bytes()).hexdigest(),
        'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope':'actual CPU screen_candidates on synthetic fixture using actual registered input; not evidence of past training contamination',
        'actual_C50_case':actual,'unrelated_preservation':unrelated,'legacy_protection':legacy,'coverage':coverage,
        'fixed_all_100_input_occurrence_screening':screened,'native_calls':0,'training_steps':0}
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('C51 isolation',args.expect,'actual C50 accepted=',actual['accepted'],'legacy rejected,unrelated accepted;0 models/training')


if __name__=='__main__':main()
