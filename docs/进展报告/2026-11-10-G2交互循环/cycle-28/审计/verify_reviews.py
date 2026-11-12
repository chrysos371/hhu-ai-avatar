"""Bind all72 diagnostic annotations and free/schema pairs to raw evidence."""
from hashlib import sha256
import json
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]

def read(path):return json.loads(path.read_text())
def digest(path):return sha256(path.read_bytes()).hexdigest()

def verify():
    results=[]
    for label in ('4b','32b'):
        path=BASE/f'实验/three-arm-{label}/probe.json';probe=read(path)
        review_path=BASE/f'审计/工作目录/002-三臂逐项语义审查/{label}-source-aware-review.json';review=read(review_path)
        assert review['probe_sha256']==digest(path) and review['model_id']==probe['model_id']
        rows=[r for r in probe['requests'] if r.get('role')!='warmup'];assert len(rows)==len(review['rows'])==36
        bycase={};markers=0
        for row,native in zip(review['rows'],rows):
            assert (row['case'],row['arm'],row['native_call'],row['reply'])==(native['case'],native['arm'],native['provider_call_id'],native['reply'])
            for key in ('plan_exact','render_passed','rendered','render_error'):assert row[key]==native.get(key)
            for finding in row['findings']:assert row['reply'][finding['start']:finding['end']]==finding['span']
            assert row['source_grounded_review'];bycase.setdefault(row['case'],{})[row['arm']]=row
            if row['arm']=='natural':
                marker=row['reply'].lstrip().startswith(('capability_boundary','copy_draft','answer_actor','report_receipt','insufficient_evidence'))
                try:marker=marker or isinstance(json.loads(row['reply']),(dict,list))
                except (ValueError,TypeError):pass
                markers+=marker
        assert review['natural_plan_markers_or_json']==markers and review['arm_metrics']==probe['arm_metrics']
        assert len(review['pairs'])==12 and len({pair['case'] for pair in review['pairs']})==12
        for pair in review['pairs']:
            a=bycase[pair['case']]['plan_free'];b=bycase[pair['case']]['plan_schema']
            assert (pair['free_call'],pair['schema_call'])==(a['native_call'],b['native_call'])
            assert pair['raw_reply_identical']==(a['reply']==b['reply']) and pair['rendered_identical']==(a['rendered']==b['rendered'])
        assert review['plan_pair_raw_identical']==sum(pair['raw_reply_identical'] for pair in review['pairs']) and review['semantic_release_approved'] is False
        results.append({'model_id':probe['model_id'],'review_sha256':digest(review_path),'bound_diagnostic_arms':36,'natural_format_markers':markers,'identical_raw_plan_pairs':review['plan_pair_raw_identical']})
    report=BASE/'审计/系统审计与推进报告.html';browser=read(BASE/'审计/收尾核验/report-browser.json');assert browser['reportSha256']==digest(report) and browser['completed'] and browser['errors']==[]
    assert [v['viewport']['width'] for v in browser['views']]==[1440,390]
    for view in browser['views']:assert view['tableCount']==4 and not view['overflow'] and len(view['links'])==18 and all(x['exists'] for x in view['links'])
    assert len(browser['views'][1]['horizontalTables'])==4 and all(x['lastCellReadable'] for x in browser['views'][1]['horizontalTables'])
    result={'verified':True,'reviews':results,'bound_diagnostic_arms':72,'report_sha256':digest(report),'desktop_mobile_and_horizontal_cells_verified':True,'same_agent_review_not_independent_human':True,'semantic_release_approved':False}
    output=BASE/'审计/收尾核验/语义审阅与报告绑定.json';text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if output.exists():assert output.read_text()==text
    else:output.write_text(text)
    print('Verified72 raw/annotation bindings,24 plan-pair comparisons and final report/browser SHA; same-agent review only.')

if __name__=='__main__':verify()
