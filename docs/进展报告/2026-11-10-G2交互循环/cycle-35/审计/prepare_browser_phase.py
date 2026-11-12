"""Archive a bundle first; freeze only after every phase input is committed."""
import argparse
import json
import shutil
import subprocess
from browser_common import ROOT, BASE, PROTOCOL, source_names, digest, verify

parser = argparse.ArgumentParser()
parser.add_argument('action', choices=('archive', 'freeze'))
parser.add_argument('--phase', required=True, choices=('before', 'after'))
args = parser.parse_args()
work = BASE / '审计/工作目录/001-页面版本屏障' / (args.phase + '-inputs')
mapping = work / 'browser-bundle.json'
if args.action == 'archive':
    assert not mapping.exists()
    archive = {}
    for path in sorted((ROOT / 'frontend/dist').rglob('*')):
        if not path.is_file():
            continue
        output = work / 'browser-dist' / path.relative_to(ROOT / 'frontend/dist')
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, output)
        assert digest(output) == digest(path)
        archive[str(path.relative_to(ROOT))] = {'archived_path': str(output.relative_to(ROOT)), 'sha256': digest(path)}
    mapping.write_text(json.dumps(archive, ensure_ascii=False, indent=2) + '\n')
    print('Archived actual bundle files:', len(archive), '; commit before freezing.')
else:
    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip(), 'Commit all inputs first'
    target = work / 'freeze.json'
    assert not target.exists()
    archive = json.loads(mapping.read_text())
    names = source_names() | {entry['archived_path'] for entry in archive.values()} | {str(mapping.relative_to(ROOT))}
    protocol = json.loads(PROTOCOL.read_text())
    frozen = {'phase': args.phase, 'scope': protocol['scope'],
        'source_ref': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'sha256': {name: digest(ROOT / name) for name in sorted(names)}, 'browser_bundle': archive}
    target.write_text(json.dumps(frozen, ensure_ascii=False, indent=2) + '\n')
    verify(target, digest(target), args.phase)
    print('Frozen', args.phase, len(names), 'inputs; SHA', digest(target))
