"""Read-only historical inventory at the delivered source; no model experiments."""
from collections import Counter
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
END = 'ef6053bf3776fa980f291c0cc33c962bca5bc2ef'
BASE = '715274a7'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True)


def main():
    assert git('rev-parse', END).strip() == END
    included = set(git('rev-list', BASE+'..'+END).splitlines())
    commits = []
    for record in git('log', '--reverse', '--topo-order', '--format=%H%x1f%P%x1f%aI%x1f%cI%x1f%an%x1f%ae%x1f%s%x1e', END).split('\x1e'):
        if not record.strip():
            continue
        ident, parents, authored, committed, author, email, subject = record.strip().split('\x1f')
        date = datetime.fromisoformat(authored).astimezone(ZoneInfo('Asia/Shanghai'))
        commits.append(dict(sha=ident, parents=parents.split(), authored_at=authored,
            committed_at=committed, shanghai_time=date.isoformat(), day=date.date().isoformat(),
            author=author, email=email, subject=subject, in_handover_graph_range=ident in included))
    cycles = []
    sources = {}
    for number in range(1, 58):
        folder = ROOT/f'docs/进展报告/2026-11-10-G2交互循环/cycle-{number:02}'
        path = folder/('阶段总结.md' if number == 1 else '审计/系统审计与推进报告.md' if number < 57 else '计划.md')
        text = path.read_text()
        key = str(path.relative_to(ROOT))
        sources[key] = sha256(path.read_bytes()).hexdigest()
        dates = git('log', '--format=%aI', END, '--', key).splitlines()
        cycles.append(dict(number=number, path=key, sha256=sources[key], text=text,
            title=next(line.lstrip('# ') for line in text.splitlines() if line.startswith('# ')),
            first_document_commit=min(dates) if dates else None,
            last_document_commit=max(dates) if dates else None,
            finalized_cycle_report=number < 57))
    for name in ['docs/进展报告/2026-11-10_项目现状与推进策略.md',
        'audit/2026-11-10-completed-components/11项修复与优化汇总.md',
        'audit/2026-11-10-docs-code-alignment/进展报告.md',
        'docs/进展报告/2026-11-10-语音形象闭环/阶段总结.md',
        'docs/首次LoRA20条开发对照报告.md', 'docs/可靠性第一轮开发回归.md',
        'docs/可靠性第二轮任务消融与修复.md', 'docs/陪伴大脑训练路线.md',
        'docs/发布/2.0.0-rc.1/既有问题处置台账.json',
        'docs/发布/2.0.0-rc.1/发布构建新增问题台账.json',
        'audit/2026-11-21-release-2.0.0/系统审计与发布报告.md',
        'audit/2026-11-21-release-2.0.0/工作目录/002-发布门控/release-gate-v1.json']:
        sources[name] = sha256((ROOT/name).read_bytes()).hexdigest()
    result = dict(source_commit=END, baseline=git('rev-parse', BASE).strip(),
        scope='All reachable commits at delivery; handover is graph difference, including concurrent merges. Dates are author timestamps converted to Asia/Shanghai; no inference of continuous working hours.',
        reachable_commits=len(commits), handover_graph_commits=len(included),
        merges=sum(len(c['parents']) > 1 for c in commits),
        authors=dict(Counter(c['author'] for c in commits)),
        daily_commits=dict(sorted(Counter(c['day'] for c in commits if c['in_handover_graph_range']).items())),
        cycles=cycles, commits=commits, source_sha256=sources)
    assert len(commits) == 2432 and len(included) == 2418 and len(cycles) == 57
    path = HERE/'历史资料与提交清单.json'
    assert not path.exists()
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('cycles','commits','source_sha256')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
