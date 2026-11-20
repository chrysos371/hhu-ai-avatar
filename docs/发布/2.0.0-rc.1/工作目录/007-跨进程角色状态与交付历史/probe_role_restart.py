"""Two real OS processes, public offline source; retain baseline and repaired runs."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path('/data/Users/zrh/repo/hhu-ai-avatar')
HERE=Path(__file__).resolve().parent
CODE='''
from avatar.main import Avatar
import json,sys,time
class Offline:
    available=False
options={'role_state_enabled':True} if sys.argv[3]=='1' else {}
bot=Avatar(db_path=sys.argv[1],llm=Offline(),summary_enabled=False,**options)
state=bot.emotion.state
before=dict(valence=state.valence,arousal=state.arousal,energy=bot.emotion.energy,
    user_valence=bot.emotion.user_state.valence,user_arousal=bot.emotion.user_state.arousal)
result=bot.respond('我很开心，今天的练习进展顺利。' if sys.argv[2]=='first' else '随便聊聊窗外。')
print(json.dumps(dict(before=before,result=result,ended_wallclock=time.time()),ensure_ascii=False))
bot.memory.close()
'''


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--label',required=True)
    parser.add_argument('--enabled',action='store_true')
    parser.add_argument('--expect',choices=['lost','retained'],required=True);args=parser.parse_args()
    import re
    assert re.fullmatch(r'restart-(?:baseline|fixed)-v[1-9][0-9]*',args.label)
    raw=Path('/data/Users/zrh/data/hhu-ai-avatar/artifacts/release/role-state')/args.label
    raw.mkdir(parents=True,exist_ok=False)
    def execution(p):
        return (p.startswith(('src/','scripts/','tests/','frontend/','evals/','training/'))
            or p=='pyproject.toml' or p.startswith('requirements') and p.endswith('.txt')
            or '/' not in p and p.endswith('.py'))
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    selected={p for p in names if p and execution(p)} | {str(Path(__file__).relative_to(ROOT))}
    untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=ROOT).decode().split('\0')
    assert not any(p and execution(p) for p in untracked)
    subprocess.run(['git','diff','--exit-code','HEAD','--',*sorted(selected)],cwd=ROOT,check=True,stdout=subprocess.DEVNULL)
    before={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(selected)}
    rows=[];start=time.monotonic()
    for phase in ('first','second'):
        argv=[sys.executable,'-B','-c',CODE,str(raw/'memory.db'),phase,'1' if args.enabled else '0']
        result=subprocess.run(argv,cwd=ROOT,capture_output=True,text=True)
        (raw/(phase+'.stdout.log')).write_text(result.stdout)
        (raw/(phase+'.stderr.log')).write_text(result.stderr)
        assert result.returncode==0,result.stderr
        rows.append(dict(phase=phase,actual_returncode=result.returncode,output=json.loads(result.stdout)))
    first=rows[0]['output']['result'];second=rows[1]['output']['before']
    assert first['valence']>.1
    retained=first['valence']*.95<=second['valence']<=first['valence']+.001
    lost=second['valence']==second['arousal']==0
    assert (lost if args.expect=='lost' else retained)
    assert second['user_valence']==second['user_arousal']==0,'past user observation must not restore'
    unchanged=all(sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in before.items());assert unchanged
    report=dict(source_ref=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        driver_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),source_sha256=before,
        source_unchanged=unchanged,role_state_enabled=args.enabled,expected=args.expect,actual_role_retained=retained,
        actual_role_lost=lost,past_user_observation_restored=False,rows=rows,
        seconds_including_two_processes=time.monotonic()-start,
        scope='actual offline two-OS-process role continuity only; no model/human quality approval',
        raw_root=str(raw),raw_sha256={str(p.relative_to(raw)):sha256(p.read_bytes()).hexdigest()
            for p in sorted(raw.rglob('*')) if p.is_file()})
    with (HERE/(args.label+'.json')).open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({k:report[k] for k in ('expected','actual_role_retained','actual_role_lost','source_unchanged','seconds_including_two_processes')},ensure_ascii=False))


if __name__=='__main__':main()
