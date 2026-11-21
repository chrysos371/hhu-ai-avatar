"""Actual report rendering child status and immutable screenshot/log binding."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
ASSETS = Path('/data/Users/zrh/data/hhu-ai-avatar')
RAW = ASSETS/'artifacts/release/final-report-qa-v1'


def h(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    path = HERE/'report-qa-v1.json'
    assert not path.exists() and not RAW.exists()
    reports = {str(p.relative_to(ROOT)): h(p) for p in [
        HERE.parent.parent/'系统审计与发布报告.md', HERE.parent.parent/'系统审计与发布报告.html']}
    env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(ASSETS/'runtime/playwright'),
               FONTCONFIG_FILE=str(ASSETS/'runtime/browser-libs/fontconfig.xml'))
    env['LD_LIBRARY_PATH'] = str(ASSETS/'runtime/browser-libs/extracted/usr/lib/x86_64-linux-gnu')+os.pathsep+env.get('LD_LIBRARY_PATH', '')
    child = subprocess.run([str(ASSETS/'runtime/node-npm/node_modules/node/bin/node'),
                            str(HERE/'report_qa.cjs'), str(RAW)], cwd=ROOT, env=env,
                           capture_output=True, text=True)
    RAW.mkdir(exist_ok=True)
    (RAW/'stdout.log').write_text(child.stdout)
    (RAW/'stderr.log').write_text(child.stderr)
    value = json.loads((RAW/'result.json').read_text()) if (RAW/'result.json').exists() else dict(passed=False)
    value.update(actual_returncode=child.returncode, report_sha256=reports,
                 source_sha256={str(p.relative_to(ROOT)): h(p) for p in [Path(__file__), HERE/'report_qa.cjs']},
                 raw=str(RAW), raw_sha256={p.name: h(p) for p in RAW.iterdir() if p.is_file()})
    assert all(h(ROOT/p) == digest for p, digest in reports.items())
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({k: v for k, v in value.items() if k not in ('source_sha256', 'raw_sha256', 'report_sha256')}, ensure_ascii=False))
    assert child.returncode == 0 and value['passed']


if __name__ == '__main__':
    main()
