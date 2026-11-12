"""Fixed source and separately committed actual browser bundle phase identity."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'evals/interaction/cycle-35/browser-state-privacy-protocol.json'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_names():
    tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().split('\0')
    selected = {name for name in tracked if name.startswith(('src/', 'frontend/'))
        or (name.startswith(('tests/', 'scripts/')) and name.endswith('.py'))}
    selected.update(str((BASE / '审计' / name).relative_to(ROOT)) for name in (
        'browser_common.py', 'prepare_browser_phase.py', 'browser_probe.py', 'browser_probe.cjs'))
    selected.add(str(PROTOCOL.relative_to(ROOT)))
    return selected


def verify(path, expected, phase):
    assert digest(path) == expected
    frozen = json.loads(Path(path).read_text())
    assert frozen['phase'] == phase and frozen['scope'] == json.loads(PROTOCOL.read_text())['scope']
    assert source_names() <= frozen['sha256'].keys()
    for name, value in frozen['sha256'].items():
        assert digest(ROOT / name) == value, name
    actual_bundle = {str(p.relative_to(ROOT)): digest(p) for p in (ROOT / 'frontend/dist').rglob('*') if p.is_file()}
    assert actual_bundle == {name: entry['sha256'] for name, entry in frozen['browser_bundle'].items()}
    for name, entry in frozen['browser_bundle'].items():
        assert frozen['sha256'][entry['archived_path']] == entry['sha256'] == digest(ROOT / name)
    raw = subprocess.check_output(['git', 'archive', '--format=tar', frozen['source_ref'], '--', *sorted(frozen['sha256'])], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        historical = {m.name: hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in archive.getmembers() if m.isfile()}
    assert historical == frozen['sha256']
    return frozen
