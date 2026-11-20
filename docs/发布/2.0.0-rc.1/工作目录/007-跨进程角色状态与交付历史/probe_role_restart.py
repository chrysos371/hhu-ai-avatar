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
bot=Avatar(db_path=sys.argv[1],llm=Offline(),summary_enabled=False)
state=bot.emotion.state
before=dict(valence=state.valence,arousal=state.arousal,energy=bot.emotion.energy,
    user_valence=bot.emotion.user_state.valence,user_arousal=bot.emotion.user_state.arousal)
result=bot.respond('我很开心，今天的练习进展顺利。' if sys.argv[2]=='first' else '随便聊聊窗外。')
print(json.dumps(dict(before=before,result=result,ended_wallclock=time.time()),ensure_ascii=False))
bot.memory.close()
'''


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--label',required=True)
    parser.add_argument('--expect',choices=['lost','retained'],required=True);args=parser.parse_args()
    import re
    assert re.fullmatch(r'restart-(?:baseline|fixed)-v[1-9][0-9]*',args.label)
    raw=Path('/data/Users/zrh/data/hhu-ai-avatar/artifacts/release/role-state')/args.label
    raw.mkdir(parents=True,exist_ok=False)
    binding=json.loads((HERE.parent/'006-写作交付与严格格式/python-writing-v8-binding.json').read_text())
    before={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in binding['source_sha256']}
    rows=[];start=time.monotonic()
    for phase in ('first','second'):
        argv=[sys.executable,'-B','-c',CODE,str(raw/'memory.db'),phase]
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
        source_unchanged=unchanged,expected=args.expect,actual_role_retained=retained,
        actual_role_lost=lost,past_user_observation_restored=False,rows=rows,
        seconds_including_two_processes=time.monotonic()-start,
        scope='actual offline two-OS-process role continuity only; no model/human quality approval',
        raw_root=str(raw),raw_sha256={str(p.relative_to(raw)):sha256(p.read_bytes()).hexdigest()
            for p in sorted(raw.rglob('*')) if p.is_file()})
    with (HERE/(args.label+'.json')).open('x') as stream:json.dump(report,stream,ensure_ascii=False,indent=2);stream.write('\n')
    print(json.dumps({k:report[k] for k in ('expected','actual_role_retained','actual_role_lost','source_unchanged','seconds_including_two_processes')},ensure_ascii=False))


if __name__=='__main__':main()
