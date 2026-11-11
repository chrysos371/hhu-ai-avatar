"""Verify source versions, artifact links, pinned providers and owned cleanup."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
EV = HERE.parent/'实验'
PROTOCOLS = ROOT/'evals/interaction/cycle-19'


def main():
    paths = [*EV.rglob('*.json'), *PROTOCOLS.glob('*.json')]
    evidence = {path: json.loads(path.read_text()) for path in paths if path.name != 'snapshot-check.json'}
    bindings = {}
    for path, data in evidence.items():
        for field in ('sourceSha256', 'source_sha256', 'sha256'):
            table = data.get(field, {})
            if not isinstance(table, dict): continue
            for name, digest in table.items():
                target = (ROOT/name).resolve()
                assert target.is_relative_to(ROOT)
                bindings.setdefault((target.relative_to(ROOT).as_posix(), digest), []).append(
                    {'evidence': path.relative_to(ROOT).as_posix(), 'field': field})
    results = []
    for (name, expected), origins in sorted(bindings.items()):
        target = ROOT/name
        actual = sha256(target.read_bytes()).hexdigest() if target.is_file() else None
        source = 'current' if actual == expected else None
        if source is None:
            commits = subprocess.check_output(['git', 'log', '--format=%H', '--', name], cwd=ROOT, text=True).splitlines()
            for commit in commits:
                blob = subprocess.run(['git', 'show', commit+':'+name], cwd=ROOT, capture_output=True)
                if blob.returncode == 0 and sha256(blob.stdout).hexdigest() == expected: source = commit; break
        results.append({'path': name, 'sha256': expected, 'source': source, 'verified': source is not None, 'evidence': origins})
    artifacts = [*EV.rglob('*'), *PROTOCOLS.glob('*.json'), ROOT/'evals/interaction/cycle-02/model-scale-protocol.json']
    hashes = {}
    for path in artifacts:
        if path.is_file() and path.name != 'snapshot-check.json':
            hashes.setdefault(sha256(path.read_bytes()).hexdigest(), []).append(path.relative_to(ROOT).as_posix())
    references = []
    for path, data in evidence.items():
        for field in ('sample_sha256', 'protocol_sha256', 'candidate_freeze_sha256', 'candidateFreezeSha256',
                      'mechanical_summary_sha256', 'summary_sha256', 'baseline_source_review_sha256', 'prior_summary_sha256'):
            value = data.get(field)
            if value is None: continue
            references.append({'evidence': path.relative_to(ROOT).as_posix(), 'field': field,
                               'sha256': value, 'targets': hashes.get(value, [])})
    registry = {model['model_id']: model for model in json.loads((ROOT/'evals/interaction/cycle-02/model-scale-protocol.json').read_text())['models']}
    providers = []
    for path, data in evidence.items():
        if path.name != 'lifecycle.json': continue
        assert data['completed'] and data['failure'] is None and len(data['models']) == 1
        model = data['models'][0]; ready = model['provider_ready']; key = model['model_id']
        assert model['cleanup_passed'] and model['sampler_exit'] == model['provider_exit'] == 0
        assert ready['pid'] == model['provider_pid']
        assert ready['model_sha256'] == registry[key]['sha256'] and ready['model_revision'] == registry[key]['revision']
        providers.append({'evidence': path.relative_to(ROOT).as_posix(), 'model': key, 'pid': model['provider_pid'],
                          'gpu': ready['chosen_gpu']['index'], 'owned_exit': 0, 'model_registry_match': True})
    report = {'checked': len(results), 'allPassed': all(row['verified'] for row in results)
              and all(row['targets'] for row in references), 'bindings': results,
              'artifact_references': references, 'providers': providers}
    (EV/'snapshot-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(report['checked'], 'source/evidence versions;', len(references), 'artifact references;', len(providers), 'owned pinned providers;', report['allPassed'])
    assert report['allPassed'], [row for row in results if not row['verified']]


if __name__ == '__main__': main()
