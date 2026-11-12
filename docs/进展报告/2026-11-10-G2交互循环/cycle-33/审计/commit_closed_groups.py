"""Archive only closed C33 groups, one commit each; active totals stay untracked."""
import argparse
import json
import os
from pathlib import Path
import subprocess
BASE=Path(__file__).resolve().parents[1];ROOT=Path(__file__).resolve().parents[5]


def main(args):
    folder=args.experiment.resolve()
    if not folder.is_relative_to(BASE/'实验') or not folder.name.startswith('shared-affect-') or (BASE/'审计/证据清单.json').exists():raise ValueError('Use active C33 shared experiment only')
    assert not subprocess.check_output(['git','diff','--cached','--name-only'],cwd=ROOT)
    assert subprocess.check_output(['git','config','user.name'],cwd=ROOT,text=True).strip()=='spinner-bot'
    committed=[]
    for path in sorted(folder.glob('r*/group-completed.json')):
        relative=str(path.parent.relative_to(ROOT))
        if subprocess.check_output(['git','ls-files','--',relative],cwd=ROOT):continue
        group=json.loads(path.read_text());assert group['complete'] and group['id']==path.parent.name
        for segment in ('preparation','current_analysis','lab_readonly_candidate'):
            assert json.loads((path.parent/segment/'segment-completed.json').read_text())['complete']
        progress=BASE/'进展.md'
        with progress.open('a') as out:out.write('\n- '+args.label+' '+group['id']+'共享准备与双OS已闭合；skip='+str(group['actual_candidate_skipped'])+'，原观察字段差异='+str(group['differing_fields'])+'，严格代号='+str(group['strict_code_correct'])+'。非整轮语义结论；及时独立提交。\n')
        subprocess.run(['git','add',relative,str(progress.relative_to(ROOT))],cwd=ROOT,check=True)
        subprocess.run(['git','diff','--cached','--check','--','.',':(exclude)*.log'],cwd=ROOT,check=True)
        subprocess.run(['git','commit','-qm','docs(experiment): retain'+args.label+' '+group['id']+' shared SQL and closed OS evidence'],cwd=ROOT,check=True);committed.append(group['id'])
    if args.push and committed:
        subprocess.run(['git','push','origin','main'],cwd=ROOT,env=dict(os.environ,GIT_SSH_COMMAND='ssh -i /root/Users/zrh/.ssh/id_ed25519_github -o IdentitiesOnly=yes'),check=True)
    print('Individually committed',len(committed),'closed groups',committed)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('experiment',type=Path);parser.add_argument('--label',required=True);parser.add_argument('--push',action='store_true');main(parser.parse_args())
