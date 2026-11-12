"""Pre-registered pure shadow guards; no model call or GPU inference."""
from hashlib import sha256
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[5];BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from readonly_analysis_candidate import decide


def main():
    protocol=ROOT/'evals/interaction/cycle-31/readonly-analysis-cpu-controls.json';data=json.loads(protocol.read_text());rows=[]
    for case in data['cases']:
        args={k:v for k,v in case.items() if k in ('history','scope','risk','rule_fact_candidates')}
        result=decide(case['text'],**args);rows.append({'id':case['id'],'text':case['text'],'expected':case['expected'],'decision':result,'passed':result['eligible']==case['expected']})
    out=BASE/'审计/工作目录/001-只读分析路由保护/shadow-v1.json';assert not out.exists();out.write_text(json.dumps({'actual_llm_or_gpu':False,'protocol_sha256':sha256(protocol.read_bytes()).hexdigest(),'candidate_sha256':sha256((Path(__file__).parent/'readonly_analysis_candidate.py').read_bytes()).hexdigest(),'rows':rows,'eligible':sum(r['decision']['eligible'] for r in rows),'passed':sum(r['passed'] for r in rows),'total':len(rows)},ensure_ascii=False,indent=2)+'\n')
    bad=[r for r in rows if not r['passed']];print('CPU shadow',len(rows)-len(bad),'/',len(rows),'failures',[(r['id'],r['decision']) for r in bad]);assert not bad


if __name__=='__main__':main()
