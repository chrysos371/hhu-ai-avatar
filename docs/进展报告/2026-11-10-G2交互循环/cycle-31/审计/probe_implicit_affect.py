"""Supplementary white-box synthetic guard coverage, not native outcome evidence."""
from hashlib import sha256
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[5];BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from readonly_analysis_candidate import decide
from avatar.brain.emotion import EmotionEngine


def main():
    path=ROOT/'evals/interaction/cycle-31/readonly-affect-whitebox-supplement.json';data=json.loads(path.read_text());rows=[]
    for case in data['cases']:
        decision=decide(case['text'],history=case['history']);scores=[EmotionEngine.infer(m['content']) for m in case['history']]
        rows.append({**case,'lexical_history_emotion_scores':scores,'decision':decision,'matches_conservative_semantic_expectation':decision['eligible']==case['expected_skip']})
    out=BASE/'审计/工作目录/001-只读分析路由保护/implicit-affect-whitebox-result.json';assert not out.exists()
    mismatches=[r for r in rows if not r['matches_conservative_semantic_expectation']]
    result={'scope':data['scope'],'protocol_sha256':sha256(path.read_bytes()).hexdigest(),'helper_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'candidate_sha256':sha256(Path(__file__).with_name('readonly_analysis_candidate.py').read_bytes()).hexdigest(),
        'actual_llm_or_gpu':False,'rows':rows,'synthetic_affect_cases':12,'neutral_controls':4,'conservative_expectation_mismatches':len(mismatches),
        'claim':'Classifications only. Lexical zero does not prove semantic neutrality. No native affect regression or natural frequency proved; candidate unchanged.'}
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print('Supplementary synthetic affect guard mismatches',len(mismatches),'of16;actual LLM/GPU false;native affect impact unmeasured.')


if __name__=='__main__':main()
