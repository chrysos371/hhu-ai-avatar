"""Bind post-hoc same-agent annotations to original native replies and scores."""
from hashlib import sha256
import json
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]

def read(p):return json.loads(p.read_text())
def digest(p):return sha256(p.read_bytes()).hexdigest()

def verify():
    results=[]
    for label in ('4b','32b'):
        path=BASE/f'实验/source-atoms-{label}/probe.json';probe=read(path)
        review_path=BASE/f'审计/工作目录/002-对照有效性与语义审查/{label}-source-aware-review.json';review=read(review_path)
        assert review['probe_sha256']==digest(path) and review['model_id']==probe['model_id']
        raw=[r for r in probe['requests'] if r.get('arm') in ('plain','plan')]
        assert len(raw)==len(review['rows'])==24
        for row,native in zip(review['rows'],raw):
            assert (row['case'],row['arm'],row['native_call'],row['reply'])==(native['case'],native['arm'],native['provider_call_id'],native['reply'])
            for key in ('plan_exact','render_passed','rendered','render_error'):assert row[key]==native.get(key)
            marker=native['arm']=='plain' and native['reply'].strip().startswith(('insufficient_evidence','{"operation"'))
            assert row['plain_emitted_plan_marker_or_json']==marker
            for finding in row.get('findings',[]):assert row['reply'][finding['start']:finding['end']]==finding['span']
            assert row['source_grounded_review']
        markers=sum(r['plain_emitted_plan_marker_or_json'] for r in review['rows']);assert review['plain_plan_format_count']==markers
        for key in ('plan_exact','render_passed','rendered_task_exact'):assert review[key]==probe[key]
        assert review['render_rejections']==12-probe['render_passed'] and review['semantic_release_approved'] is False
        results.append({'model_id':probe['model_id'],'review_sha256':digest(review_path),'bound_diagnostic_arms':24,'plain_plan_marker_or_json':markers,'render_rejections':review['render_rejections']})
    report=BASE/'审计/系统审计与推进报告.html';browser=read(BASE/'审计/收尾核验/report-browser.json');assert browser['reportSha256']==digest(report)
    assert browser['completed'] and browser['errors']==[]
    assert [v['viewport']['width'] for v in browser['views']]==[1440,390]
    for view in browser['views']:assert view['tableCount']==4 and not view['overflow'] and len(view['links'])==18 and all(r['exists'] for r in view['links'])
    assert len(browser['views'][1]['horizontalTables'])==4 and all(t['lastCellReadable'] for t in browser['views'][1]['horizontalTables'])
    value={'verified':True,'reviews':results,'bound_diagnostic_arms':48,'report_sha256':digest(report),'desktop_mobile_links_and_horizontal_cells_verified':True,'reviewer':'same Codex agent; not independent human review','semantic_release_approved':False}
    output=BASE/'审计/收尾核验/语义审阅与报告绑定.json';text=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    if output.exists():assert output.read_text()==text
    else:output.write_text(text)
    print('Verified48 review/native bindings and final report/browser/layout links; same-agent review only.')

if __name__=='__main__':verify()
