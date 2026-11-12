"""Default SDK post-commit boundary, with a controlled TTS component.

No real Edge service, physical audio or model-quality claim. Fixture text and
silence WAV make dispatch and stale SDK return independently observable.
"""
import argparse
from contextlib import closing, contextmanager, nullcontext
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
import time
import wave
from unittest.mock import patch

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar
from avatar.mouth.tts import EdgeTTSEngine

ROOT = Path(__file__).resolve().parents[2]
from avatar.paths import project_data_root
PRIVATE = '待删语音实验名'


def audit(output, native_edge=False):
    if output.exists(): raise ValueError('Use a new evidence path')
    paths = [*ROOT.glob('src/avatar/**/*.py'), Path(__file__).resolve()]
    report = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'sourceSha256': {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in sorted(paths)},
        'scope': 'Actual Avatar SDK with fixture model and silence WAV; optional actual EdgeTTSEngine with fixture Communicate.save. No physical audio, real Edge HTTP or native model-quality result.',
        'tts_adapter': 'native_edge_with_fixture_save' if native_edge else 'fixture_tts_only',
        'cases': [], 'completed': False}
    def save(): output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    save()
    cases = ('normal', 'cancel_after_commit', 'forget_after_commit')
    if native_edge: cases += ('forget_during_tts',)
    for change in cases:
        row = {'case': change, 'tts_calls': [], 'changed': None, 'cleanup': False}
        report['cases'].append(row); token = CancellationToken()
        with tempfile.TemporaryDirectory(prefix='sdk-tts-privacy-', dir=project_data_root(ROOT)/'tmp') as folder:
            path = str(Path(folder)/'owned.db'); audio = str(Path(folder)/'reply.wav')
            class Engine:
                available = True
                def chat_analysis(self, *args, **kwargs): return '{"emotion":{"valence":0,"arousal":0},"facts":[]}'
                def chat(self, *args, **kwargs): return PRIVATE+'你好。'
            class TTS:
                def synthesize(self, text, out_path, rate, pitch):
                    row['tts_calls'].append({'at_monotonic': time.monotonic(), 'text': text, 'path': out_path})
                    if change == 'forget_during_tts':
                        with closing(MemoryStore(path)) as writer: writer.forget(fragment)
                        row['changed'] = {'at_monotonic': time.monotonic(), 'kind': change,
                                          'actual_revision': bot.memory.context_revision}
                    with wave.open(out_path, 'wb') as stream:
                        stream.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
                        stream.writeframes(b'\0\0'*1600)
                    return out_path
            class Communication:
                def __init__(self, text, voice, **kwargs):
                    self.text, self.rate, self.pitch = text, kwargs['rate'], kwargs['pitch']
                async def save(self, out_path):
                    TTS().synthesize(self.text, out_path, self.rate, self.pitch)
            bot = Avatar(db_path=path, llm=Engine(), tts=EdgeTTSEngine() if native_edge else TTS())
            fragment = bot.memory.remember_user('名字', PRIVATE)
            original = bot.memory.transaction
            @contextmanager
            def committed():
                with original(): yield
                if (change != 'forget_during_tts' and row['changed'] is None and not bot.memory._conn.in_transaction
                        and bot.memory._conn.execute("SELECT 1 FROM memory_messages WHERE role='assistant'").fetchone()):
                    if change == 'cancel_after_commit': token.cancel()
                    elif change == 'forget_after_commit':
                        with closing(MemoryStore(path)) as writer: writer.forget(fragment)
                    row['changed'] = {'at_monotonic': time.monotonic(), 'kind': change,
                                      'actual_revision': bot.memory.context_revision}
            bot.memory.transaction = committed
            try:
                try:
                    context = patch('avatar.mouth.tts.edge_tts.Communicate', Communication) if native_edge else nullcontext()
                    with context:
                        result = bot.respond('我的名字是'+PRIVATE+'。', use_tts=True, tts_path=audio, cancel=token)
                    row['terminal'] = 'result'; row['result'] = result
                    row['private_in_returned_reply'] = PRIVATE in result['reply']
                except Cancelled as error:
                    row['terminal'] = 'cancelled'; row['error'] = str(error)
                    row['private_in_returned_reply'] = False
                row['token_cancelled'] = token.cancelled
                row['current_revision'] = bot.memory.context_revision
                row['stored_assistants'] = [dict(record) for record in bot.memory._conn.execute(
                    "SELECT id,content FROM memory_messages WHERE role='assistant'")]
                row['audio_file_created'] = Path(audio).exists()
                assert row['changed'] is not None
            finally:
                bot.memory.close(); save()
        row['cleanup'] = not Path(folder).exists(); save()
    assert all(sha256((ROOT/name).read_bytes()).hexdigest() == digest for name, digest in report['sourceSha256'].items())
    report['completed'] = True; save(); return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--native-edge', action='store_true')
    args = parser.parse_args(); result = audit(args.output, args.native_edge)
    for row in result['cases']:
        print(row['case'], 'TTS component calls', len(row['tts_calls']), 'terminal', row['terminal'],
              'private in returned reply', row['private_in_returned_reply'], 'revision', row['current_revision'])
