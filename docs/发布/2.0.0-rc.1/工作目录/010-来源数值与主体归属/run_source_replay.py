"""Retain actual paired SDK/SQL controlled source replay; no native/human claim."""
from contextlib import closing
from hashlib import sha256
import io
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tarfile
import time

ROOT=Path('/data/Users/zrh/repo/hhu-ai-avatar')
HERE=Path(__file__).resolve().parent
RAW=Path('/data/Users/zrh/data/hhu-ai-avatar/artifacts/release/source-replay-v1')


def child():
    from avatar.brain.memory import MemoryStore
    from avatar.cancellation import CancellationToken
    from avatar.main import Avatar
    class Hostile:
        available=True
        def __init__(self):self.analysis=[];self.generations=[]
        def chat_analysis(self,messages,**kwargs):
            self.analysis.append(messages)
            return '{"emotion":{"valence":0,"arousal":0},"facts":[]}'
        def chat(self,messages,**kwargs):
            self.generations.append(messages);return self.reply
        def stream_chat(self,messages,*,on_delta=None,cancel=None,**kwargs):
            if cancel:cancel.checkpoint()
            value=self.chat(messages)
            if on_delta:on_delta(value)
            return value
    cases=[]
    for version,ident in [('30','corrected_budget'),('31','updated_material_total')]:
        filename='native-context-use-protocol.json' if version=='30' else 'readonly-analysis-cost-protocol.json'
        spec=json.loads((ROOT/f'evals/interaction/cycle-{version}'/filename).read_text())
        case=next(c for c in spec['cases'] if c['id']==ident)
        cases.append(dict(id=ident,turns=case['turns'],raw='93',expected=case['expected']))
    cases.extend([
        dict(id='third_party_name',turns=['我的朋友叫柳林。','我叫什么名字？'],raw='你好，柳林。我知道你叫柳林。',expected='目前没有足够记录确认你的名字，你可以告诉我希望怎么称呼你。'),
        dict(id='copied_preference',turns=['今天聊聊。'],profile={'偏好':'喜欢网球'},raw='我喜欢网球。我们一起去打吧。',expected='目前关于你的偏好记录是：喜欢网球。'),
    ])
    all_rows=[]
    for case in cases:
        for enabled in (False,True):
            arm='candidate' if enabled else 'legacy';folder=RAW/case['id']/arm;folder.mkdir(parents=True,exist_ok=False)
            model=Hostile();model.reply=case['raw'];turns=[]
            with closing(MemoryStore(str(folder/'state.db'))) as memory:
                for key,value in case.get('profile',{}).items():memory.remember_user(key,value)
                bot=Avatar(memory=memory,llm=model,capability_contract_enabled=enabled,role_state_enabled=enabled)
                for text in case['turns']:
                    a,g=len(model.analysis),len(model.generations);pieces=[]
                    result=bot.respond(text,cancel=CancellationToken(),on_delta=pieces.append)
                    turns.append(dict(text=text,result=result,deltas=pieces,
                        analysis_calls=len(model.analysis)-a,generation_calls=len(model.generations)-g))
                sql={table:[dict(r) for r in memory._conn.execute('SELECT * FROM '+table)] for table in
                    ('memory_messages','memory_response_context','memory_chat_results','memory_action_receipts')}
            data=dict(case_id=case['id'],arm=arm,turns=turns,sql=sql,
                actual_analysis_prompts=model.analysis,actual_generation_prompts=model.generations)
            (folder/'result.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
            all_rows.append(dict(case_id=case['id'],arm=arm,final_reply=turns[-1]['result']['reply'],
                final_generation_mode=turns[-1]['result']['generation_mode'],
                final_analysis_calls=turns[-1]['analysis_calls'],final_generation_calls=turns[-1]['generation_calls'],
                expected=case['expected'],exact_expected=turns[-1]['result']['reply']==case['expected']))
    (RAW/'summary.json').write_text(json.dumps(all_rows,ensure_ascii=False,indent=2)+'\n')
    assert all(r['exact_expected'] for r in all_rows if r['arm']=='candidate')


def main():
    if sys.argv[1:]==['--child']:child();return
    assert not sys.argv[1:]
    own=str(Path(__file__).resolve().relative_to(ROOT))
    common=runpy.run_path(str(HERE.parent/'006-写作交付与严格格式/run_current_python.py'))
    before=common['snapshot']();before[own]=sha256(Path(__file__).read_bytes()).hexdigest()
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    archived=subprocess.check_output(['git','archive','--format=tar',head,'--',*before],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archived)) as stream:
        historic={m.name:sha256(stream.extractfile(m).read()).hexdigest() for m in stream if m.isfile()}
    assert before==historic,'commit all execution inputs first'
    RAW.mkdir(parents=True,exist_ok=False)
    start=time.monotonic()
    with (RAW/'stdout.log').open('x') as out,(RAW/'stderr.log').open('x') as err:
        result=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--child'],cwd=ROOT,stdout=out,stderr=err)
    stable=all(sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in before.items())
    report=dict(source_ref=head,source_sha256=before,source_inputs=len(before),source_unchanged=stable,
        actual_child_returncode=result.returncode,seconds=time.monotonic()-start,whole_stage_wallclock_cutoff=None,
        scope='known source-controlled hostile stub; actual SDK SQL, no native model or human quality approval',
        raw=str(RAW),raw_sha256={str(p.relative_to(RAW)):sha256(p.read_bytes()).hexdigest() for p in sorted(RAW.rglob('*')) if p.is_file()})
    with (HERE/'source-replay-v1.json').open('x') as f:json.dump(report,f,ensure_ascii=False,indent=2);f.write('\n')
    assert result.returncode==0 and stable,'failure retained'
    print(json.dumps({k:report[k] for k in ('actual_child_returncode','source_unchanged','seconds')},ensure_ascii=False))


if __name__=='__main__':main()
