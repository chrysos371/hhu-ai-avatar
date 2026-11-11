"""Render the explicit repository Markdown and seal only completed evidence."""
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
TITLE = '系统审计与推进报告'


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def render():
    source = HERE / (TITLE + '.md')
    text = source.read_text()
    links = re.findall(r'\[[^\]]+\]\(([^)]+)\)', text)
    for link in links:
        assert not link.startswith(('https:', 'http:', '#')), link
        assert (HERE / link).resolve().exists(), link
    inline = lambda value: re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', escape(value))
    body = []
    table = False
    for line in text.splitlines():
        if line.startswith('| ---'):
            continue
        if line.startswith('|'):
            tag = 'td' if table else 'th'
            if not table:
                body.append('<div class="table-wrap"><table>')
                table = True
            body.append('<tr>' + ''.join(f'<{tag}>' + inline(cell) + f'</{tag}>'
                                         for cell in line.strip('| ').split(' | ')) + '</tr>')
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
    style = re.search(r'<style>.*?</style>', (HERE / '独立SDK与语音修复报告.html').read_text()).group()
    output = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>第二十一轮系统审计与推进报告</title>' + style + '<main>' + '\n'.join(body) + '</main></html>'
    (HERE / (TITLE + '.html')).write_text(output)
    print('Rendered; checked', len(links), 'local links')


def seal():
    subprocess.run([str(Path(__import__('sys').executable)), str(HERE / 'verify_delivery.py')], check=True)
    check = json.loads((HERE / '交付核验/final-report-browser.json').read_text())
    assert check['reportSha256'] == digest(HERE / (TITLE + '.html'))
    assert len(check['results']) == 2
    assert all(v['h1'] == 1 and v['tables'] == 4 and not v['overflow'] and not v['errors'] for v in check['results'])
    # Preserve live process notes and issues without freezing their future upkeep.
    snapshot = HERE / '交付核验/周期过程快照'
    live = [BASE / '进展.md', BASE / '交付进展.md', *sorted((HERE / 'issues').glob('*.md'))]
    for path in live:
        dest = snapshot / path.relative_to(BASE)
        if dest.exists():
            assert dest.read_bytes() == path.read_bytes(), path
        else:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(path.read_bytes())
    excluded = set(live) | {HERE / '证据清单.json'}
    manifest = {path.relative_to(BASE).as_posix(): digest(path)
                for path in sorted(BASE.rglob('*')) if path.is_file() and path not in excluded}
    (HERE / '证据清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print('Sealed', len(manifest), 'files; live process notes and issues preserved separately')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seal', action='store_true')
    args = parser.parse_args()
    render()
    if args.seal:
        seal()
