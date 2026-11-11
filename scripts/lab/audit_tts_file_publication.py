"""Controlled Edge adapter file publication; no real voice/network test."""
import argparse
import asyncio
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile

from avatar.cancellation import CancellationToken
import avatar.mouth.tts as module

ROOT = Path(__file__).resolve().parents[2]
OLD = b'previous-user-owned-output'
PARTIAL = b'fixture-partial-audio'
NEW = b'fixture-complete-audio'


def audit(output):
    if output.exists(): raise ValueError('Use a new evidence path')
    paths = [ROOT/'src/avatar/mouth/tts.py', Path(__file__).resolve()]
    report = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'sourceSha256': {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in paths},
        'scope': 'Actual EdgeTTSEngine file handling; Communicate.save fixture writes sentinel bytes/raises. No real Edge, valid speech format, physical playback or natural failure frequency claim.',
        'cases': [], 'completed': False}
    original = module.edge_tts.Communicate
    def save(): output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    save()
    try:
        for behavior in ('normal', 'error', 'cancel', 'empty'):
            for existing in (True, False):
                row = {'behavior': behavior, 'target_existed': existing, 'component_paths': [], 'cleanup': False}
                report['cases'].append(row); token = CancellationToken()
                with tempfile.TemporaryDirectory(prefix='tts-publication-', dir=ROOT.parent/'runtime/tmp') as folder:
                    target = Path(folder)/'user-output.mp3'
                    if existing: target.write_bytes(OLD)
                    class Communication:
                        def __init__(self, *args, **kwargs): pass
                        async def save(self, path):
                            row['component_paths'].append(str(path))
                            if behavior == 'empty': return
                            Path(path).write_bytes(PARTIAL)
                            if behavior == 'error': raise OSError('fixture failure after partial write')
                            if behavior == 'cancel':
                                token.cancel(); await asyncio.sleep(.001)
                            Path(path).write_bytes(NEW)
                    module.edge_tts.Communicate = Communication
                    try:
                        result = module.EdgeTTSEngine().synthesize_cancellable('受控文本', str(target), cancel=token)
                        row['terminal'] = 'result'; row['returned_path'] = result
                    except Exception as error:
                        row['terminal'] = 'error'; row['error_type'] = type(error).__name__
                    content = target.read_bytes() if target.exists() else None
                    row['target_exists_after'] = target.exists()
                    row['old_target_preserved'] = content == OLD if existing else None
                    row['new_target_absent'] = content is None if not existing else None
                    row['partial_target_left'] = content == PARTIAL
                    row['complete_target'] = content == NEW
                    row['files_after'] = sorted(p.name for p in Path(folder).iterdir())
                row['cleanup'] = not Path(folder).exists(); save()
    finally: module.edge_tts.Communicate = original
    report['completed'] = True; save(); return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    result = audit(parser.parse_args().output)
    for row in result['cases']:
        print(row['behavior'], 'existing', row['target_existed'], row['terminal'],
              'preserved', row['old_target_preserved'], 'new absent', row['new_target_absent'],
              'partial', row['partial_target_left'])
