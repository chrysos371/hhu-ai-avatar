"""Bind every retained source/bundle fingerprint, including failed runs."""
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
EV = HERE.parent/'实验'


def main():
    bindings = {}
    for evidence in EV.rglob('*.json'):
        data = json.loads(evidence.read_text())
        if 'protocolSha256' in data:
            assert evidence.parent.name == 'playback', evidence
            bindings.setdefault(('evals/interaction/cycle-08/playback-protocol.json', data['protocolSha256']), []).append(
                {'evidence': evidence.relative_to(EV).as_posix(), 'field': 'protocolSha256'})
        for field in ('sourceSha256', 'source_sha256', 'servedBundleSha256'):
            table = data.get(field, {})
            assert isinstance(table, dict)
            frontend = any(name.startswith(('../', 'src/features/', 'src/lib/', 'e2e/', 'dist/')) for name in table)
            base = ROOT/'frontend' if frontend else ROOT
            for name, digest in table.items():
                path = (base/name).resolve()
                assert path.is_relative_to(ROOT) and re.fullmatch('[0-9a-f]{64}', digest), (evidence, name)
                key = (path.relative_to(ROOT).as_posix(), digest)
                bindings.setdefault(key, []).append({'evidence': evidence.relative_to(EV).as_posix(), 'field': field})
    results = []
    for (name, expected), evidence in sorted(bindings.items()):
        path = ROOT/name
        actual = sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        source = 'current' if actual == expected else None
        if source is None:
            commits = subprocess.check_output(['git', 'log', '--format=%H', '--', name], cwd=ROOT, text=True).splitlines()
            for commit in commits:
                blob = subprocess.run(['git', 'show', commit+':'+name], cwd=ROOT, capture_output=True)
                if blob.returncode == 0 and sha256(blob.stdout).hexdigest() == expected:
                    source = commit; break
        results.append({'path': name, 'sha256': expected, 'source': source,
                        'verified': source is not None, 'evidence': evidence})
    report = {'checked': len(results), 'allPassed': all(r['verified'] for r in results), 'bindings': results}
    (EV/'snapshot-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(report['checked'], 'unique source/bundle bindings; allPassed', report['allPassed'])
    assert report['allPassed'], [r for r in results if not r['verified']]


if __name__ == '__main__': main()
