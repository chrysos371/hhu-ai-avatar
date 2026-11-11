"""Bind runtime, worker, bundle and historical test bytes without rewriting logs."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
EV = HERE.parent/'实验'


def main():
    bindings = {}; log_bindings = []
    for evidence in EV.rglob('*.json'):
        if evidence.name == 'snapshot-check.json': continue
        data = json.loads(evidence.read_text())
        tables = [data, *data.get('entries', [])]
        for container in tables:
            for field in ('sourceSha256', 'workerSourceSha256', 'source_sha256', 'servedBundleSha256'):
                table = container.get(field, {})
                frontend = any(name.startswith(('../', 'src/features/', 'src/lib/', 'e2e/', 'dist/')) for name in table)
                base = ROOT/'frontend' if frontend else ROOT
                for name, digest in table.items():
                    target = (base/name).resolve(); assert target.is_relative_to(ROOT)
                    origin = {'evidence': evidence.relative_to(EV).as_posix(), 'field': field,
                              'phase': container.get('phase')}
                    bindings.setdefault((target.relative_to(ROOT).as_posix(), digest), []).append(origin)
            if 'evidence_path' in container:
                log = (EV/container['evidence_path']).resolve(); assert log.is_relative_to(EV)
                assert sha256(log.read_bytes()).hexdigest() == container['evidence_sha256']
                for name, ref in container['source_refs'].items():
                    blob = subprocess.check_output(['git', 'show', ref+':'+name], cwd=ROOT)
                    assert sha256(blob).hexdigest() == container['sourceSha256'][name]
                log_bindings.append({'phase': container['phase'], 'entry_head': container['entry_head'],
                    'evidence_path': container['evidence_path'], 'sources_verified': len(container['source_refs']),
                    'uncommitted_byte_origin': container['source_origin_note']})
    results = []
    for (name, expected), evidence in sorted(bindings.items()):
        path = ROOT/name; actual = sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        source = 'current' if actual == expected else None
        if source is None:
            commits = subprocess.check_output(['git', 'log', '--format=%H', '--', name], cwd=ROOT, text=True).splitlines()
            for commit in commits:
                blob = subprocess.run(['git', 'show', commit+':'+name], cwd=ROOT, capture_output=True)
                if blob.returncode == 0 and sha256(blob.stdout).hexdigest() == expected: source = commit; break
        results.append({'path': name, 'sha256': expected, 'source': source, 'verified': source is not None, 'evidence': evidence})
    restart = json.loads((EV/'os-restart/role-restart.json').read_text())
    assert restart['allPassed'] and len(restart['cases']) == 10
    assert all(service['exit'] == 0 and service['initial']['sourceSha256'] == service['final']['sourceSha256']
               == restart['workerSourceSha256'] for case in restart['cases'] for service in case['services'])
    report = {'checked': len(results), 'allPassed': all(row['verified'] for row in results),
              'bindings': results, 'test_log_bindings': log_bindings, 'owned_os_services_verified': 20}
    (EV/'snapshot-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(report['checked'], 'unique source/test/bundle versions;', len(log_bindings), 'test phase bindings; 20 owned OS services;', report['allPassed'])
    assert report['allPassed'], [row for row in results if not row['verified']]


if __name__ == '__main__': main()
