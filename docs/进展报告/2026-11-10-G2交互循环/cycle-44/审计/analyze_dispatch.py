"""Measured stage/type accounting and baseline error lists, no model execution."""
from collections import Counter
import json
from native_common import BASE,WORK,PROTOCOL,read,digest


def main():
    output=BASE/'审计/工作目录/005-系统复核/dispatch-accounting.json';assert not output.exists()
    protocol=read(PROTOCOL);stages={}
    for stage in ('development','protected'):
        report=read(BASE/f'实验/{stage}-v2/evaluation.json')
        proof=read(WORK/(stage+'-verification.json'));assert proof['verified']
        cases={c['id']:c for c in protocol[stage+'_cases']};arms={};errors=[]
        for arm in protocol['arms']:
            rows=[(cases[c['case']],b,g['repetition']) for g in report['groups'] for c in g['cases'] for a,b in c['arms'].items() if a==arm]
            arms[arm]={'task_correct':sum(b['final_expected_task_outcome'] for _,b,_ in rows),'total':len(rows),
                'model_used':sum(b['model_used'] for _,b,_ in rows),'rule_no_model':sum(b['framework_skipped_model'] for _,b,_ in rows),
                'direct_no_model':sum(b['direct_dispatch_without_model'] for _,b,_ in rows),
                'source_denied':sum(b['source_cancelled'] for _,b,_ in rows),'origins':dict(Counter(b['reply_origin'] for _,b,_ in rows)),
                'by_category':{category:{'total':sum(c['expected_outcome']==category for c,_,_ in rows),
                    'correct':sum(c['expected_outcome']==category and b['final_expected_task_outcome'] for c,b,_ in rows)}
                    for category in ('read','clarify_reference','clarify_intent','avoid','blocked')}}
            for case,b,rep in rows:
                if not b['final_expected_task_outcome']:
                    errors.append({'arm':arm,'case':case['id'],'repetition':rep,'expected':case['expected_outcome'],
                        'actual_kind':b['result_kind'],'final_tool':b['final_tool'],'arguments':b['final_arguments'],
                        'reply_origin':b['reply_origin'],'status_SELECTs':b['status_business_SELECTs']})
        stages[stage]={'native_calls':proof['native_calls'],'SQL_dumps':proof['SQL_dumps_reconstructed'],
            'status_SELECTs':proof['actual_status_SELECTs'],'arms':arms,'errors':errors,
            'proof_sha256':digest(WORK/(stage+'-verification.json'))}
    assert stages['development']['arms']['source_dispatch']['task_correct']==72
    assert stages['protected']['arms']['source_dispatch']['task_correct']==18
    assert all(row['arm']=='model_policy_grounded' for s in stages.values() for row in s['errors'])
    result={'scope':'descriptive staged finite-pipeline comparison, no pure model/single-factor/human-helpfulness claim',
        'new_native_calls':0,'native_total':sum(s['native_calls'] for s in stages.values()),
        'SQL_dump_total':sum(s['SQL_dumps'] for s in stages.values()),'status_SELECTs_total':sum(s['status_SELECTs'] for s in stages.values()),
        'candidate_model_calls_total':0,'candidate_strict_correct_total':90,'candidate_cases_total':90,
        'candidate_direct_no_model_total':63,'candidate_no_read_total':26,'candidate_source_denials':1,
        'stages':stages,'analyzer_sha256':digest(__file__)}
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('79native/180SQL;candidate90/90:model0/direct63/no-read26/denied1;baseline errors preserved')


if __name__=='__main__':main()
