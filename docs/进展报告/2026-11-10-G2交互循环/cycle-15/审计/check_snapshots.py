"""Bind retained JSON source fingerprints to current bytes or immutable Git blobs."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
EV = HERE.parent/'实验'


def main():
    bindings = {}
    for evidence in EV.rglob('*.json'):
        data = json.loads(evidence.read_text())
        for name, digest in data.get('sourceSha256', {}).items():
            bindings.setdefault((name, digest), []).append(str(evidence.relative_to(EV)))
    freeze = ROOT/'evals/interaction/cycle-15/candidate-freeze-v1.json'
    for name, digest in json.loads(freeze.read_text())['sha256'].items():
        bindings.setdefault((name, digest), []).append('candidate-freeze-v1.json')
    results = []
    for (name, expected), evidence in sorted(bindings.items()):
        path = ROOT/name; actual = sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        ref = 'current' if actual == expected else None
        if ref is None:
            commits = subprocess.check_output(['git', 'log', '--format=%H', '--', name], cwd=ROOT, text=True).splitlines()
            for commit in commits:
                blob = subprocess.run(['git', 'show', commit+':'+name], cwd=ROOT, capture_output=True)
                if blob.returncode == 0 and sha256(blob.stdout).hexdigest() == expected:
                    ref = commit; break
        results.append({'path': name, 'sha256': expected, 'evidence': evidence,
                        'verified': ref is not None, 'source': ref})
    report = {'checked': len(results), 'allPassed': all(r['verified'] for r in results), 'bindings': results}
    (EV/'snapshot-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(report['checked'], 'bindings; allPassed', report['allPassed'])
    assert report['allPassed'], [r for r in results if not r['verified']]


if __name__ == '__main__': main()
