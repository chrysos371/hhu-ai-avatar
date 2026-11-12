"""Render and optionally seal the C23 audit, preserving live process records."""
import argparse
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = HERE.parents[4]
NAME = '系统审计与推进报告'


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def render():
    lines = (HERE / (NAME + '.md')).read_text().splitlines()
    links = re.findall(r'\[[^\]]+\]\(([^)]+)\)', '\n'.join(lines))
    for link in links:
        assert (HERE / link).resolve().exists(), link
    def inline(text):
        return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', escape(text))
    body = []
    table = False
    for line in lines:
        if line.startswith('| ---'):
            continue
        if line.startswith('|'):
            tag = 'td' if table else 'th'
            if not table:
                body.append('<div class="table-wrap"><table>')
                table = True
            body.append('<tr>' + ''.join(f'<{tag}>' + inline(cell) + f'</{tag}>' for cell in line.strip('| ').split(' | ')) + '</tr>')
            continue
        if table:
            body.append('</table></div>')
            table = False
        if line.startswith('# '):
            body.append('<h1>' + inline(line[2:]) + '</h1>')
        elif line.startswith('## '):
            body.append('<h2>' + inline(line[3:]) + '</h2>')
        elif line:
            body.append('<p>' + inline(line) + '</p>')
    assert not table
    donor = BASE.parent / 'cycle-22/审计/系统审计与推进报告.html'
    style = re.search(r'<style>.*?</style>', donor.read_text()).group()
    (HERE / (NAME + '.html')).write_text('<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第二十三轮系统审计与推进报告</title>' + style + '<main>' + '\n'.join(body) + '</main></html>')
    print('Rendered, local links checked:', len(links))


def seal():
    verification = json.loads((HERE / '收尾核验/阶段来源与系统收尾核验.json').read_text())
    browser = json.loads((HERE / '收尾核验/report-browser.json').read_text())
    assert verification['passed'] and verification['overall_candidate_rejected']
    assert browser['reportSha256'] == digest(HERE / (NAME + '.html'))
    assert len(browser['results']) == 2
    assert all(v['h1'] == 1 and v['tables'] == 4 and not v['overflow'] and not v['errors'] for v in browser['results'])
    live = [BASE / '进展.md', HERE / '工作目录/001-当前请求范围与草稿忠实性v4/进展.md',
            HERE / '工作目录/002-冻结描述符执行期身份/进展.md', *sorted((HERE / 'issues').glob('*.md'))]
    for path in live:
        target = HERE / '收尾核验/过程快照' / path.relative_to(BASE)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            assert target.read_bytes() == path.read_bytes()
        else:
            target.write_bytes(path.read_bytes())
    canonical = {}
    for name in ('AGENTS.md', 'README.md', 'docs/项目进度.md'):
        target = HERE / '收尾核验/规范文档快照' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            assert target.read_bytes() == (ROOT / name).read_bytes()
        else:
            target.write_bytes((ROOT / name).read_bytes())
        canonical[name] = digest(target)
    (HERE / '收尾核验/规范文档哈希.json').write_text(json.dumps(canonical, ensure_ascii=False, indent=2) + '\n')
    inputs = {}
    for name, ref in [
        ('evals/interaction/cycle-23/source-capability-candidate-v4.json', '738af79'),
        ('evals/interaction/cycle-23/capability-output-protocol.json', '738af79'),
        ('evals/interaction/cycle-23/paired-capability-protocol.json', '738af79'),
        ('evals/interaction/cycle-23/candidate-development-freeze-v4.json', 'faf105f'),
        ('evals/interaction/cycle-23/candidate-development-freeze-v4-retirement.json', '17bb877'),
        ('evals/interaction/cycle-02/model-scale-protocol.json', '738af79'),
    ]:
        value = subprocess.check_output(['git', 'show', ref + ':' + name], cwd=ROOT)
        assert value == (ROOT / name).read_bytes()
        target = HERE / '收尾核验/冻结输入副本' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            assert target.read_bytes() == value
        else:
            target.write_bytes(value)
        inputs[name] = {'git_ref': ref, 'sha256': digest(target)}
    (HERE / '收尾核验/冻结输入来源.json').write_text(json.dumps(inputs, ensure_ascii=False, indent=2) + '\n')
    manifest = {path.relative_to(BASE).as_posix(): digest(path) for path in sorted(BASE.rglob('*'))
                if path.is_file() and path not in set(live) | {HERE / '证据清单.json'}}
    (HERE / '证据清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print('Sealed', len(manifest), 'files; live progress/issues copied into immutable snapshots')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seal', action='store_true')
    args = parser.parse_args()
    render()
    if args.seal:
        seal()
