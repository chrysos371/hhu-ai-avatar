"""Disposable, offline browser-test fixture. Never opens the user's database."""

from contextlib import ExitStack
import json
from urllib.parse import urlsplit
from pathlib import Path
import os
import tempfile
import subprocess
import signal
import threading
import wave
import sys
import time
from hashlib import sha256

# npm starts this helper with cwd=frontend. Shared editable environments may
# point to another worktree, so bind this fixture's own source before imports.
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / 'src'))
import numpy as np
import avatar.main
import avatar.web
import avatar.web_api
import avatar.web_state
import avatar.brain.emotion
import avatar.brain.memory
import avatar.brain.reminders
from avatar.config import config
from avatar.brain.memory import MemoryStore
from avatar.brain.reminders import ReminderStore
from avatar.web import create_server
from avatar.paths import temporary_dir
from avatar.lab.transport_fixture import controlled_provider

modules = (avatar.main, avatar.web, avatar.web_api, avatar.web_state,
           avatar.brain.emotion, avatar.brain.memory, avatar.brain.reminders)
module_paths = {module.__name__: Path(module.__file__).resolve() for module in modules}
if not all(path.is_relative_to(project_root / 'src') for path in module_paths.values()):
    raise RuntimeError('Browser fixture imported another project source tree')
runtime_binding = {'project_root': str(project_root), 'python_prefix': sys.prefix,
    'module_paths': {name: str(path) for name, path in module_paths.items()},
    'module_sha256': {name: sha256(path.read_bytes()).hexdigest() for name, path in module_paths.items()},
    'frontend_dir': str(project_root / 'frontend/dist'),
    'frontend_sha256': {str(path.relative_to(project_root)): sha256(path.read_bytes()).hexdigest()
        for path in sorted((project_root / 'frontend/dist').rglob('*')) if path.is_file()}}
if os.getenv('AVATAR_E2E_RUNTIME_EVIDENCE'):
    with Path(os.environ['AVATAR_E2E_RUNTIME_EVIDENCE']).open('x') as stream:
        json.dump(runtime_binding, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
if '--check-project-runtime' in sys.argv:
    print(json.dumps(runtime_binding, ensure_ascii=False))
    raise SystemExit(0)
print('Browser fixture runtime: '+json.dumps(runtime_binding, ensure_ascii=False), flush=True)

temporary_dir().mkdir(parents=True, exist_ok=True)
folder = tempfile.TemporaryDirectory(prefix="admin-e2e-", dir=temporary_dir())
provider_context = ExitStack()
reminder_delivery_case = os.getenv('AVATAR_E2E_REMINDER_DELIVERY_CASE')
if reminder_delivery_case:
    if reminder_delivery_case not in ('normal_claim', 'response_drop_after_commit', 'navigation_before_response', 'ack_response_drop_after_commit'):
        raise ValueError('Unknown reminder delivery fixture case')
    if os.getenv('AVATAR_E2E_LLM_PROVIDER') or os.getenv('AVATAR_E2E_REAL_ASR_MODEL'):
        raise ValueError('Reminder delivery fixture must not load real models')
    provider_url = 'http://127.0.0.1:1/v1'
    config.llm.api_key = ''
    config.llm.model = 'disabled-reminder-delivery-fixture'
elif os.getenv('AVATAR_E2E_LLM_PROVIDER'):
    evidence = json.loads(Path(os.environ['AVATAR_E2E_LLM_PROVIDER']).read_text())
    provider_url = evidence['url']
    parsed = urlsplit(provider_url)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.path != '/v1':
        raise ValueError('Real browser evaluation requires an explicit loopback provider')
    config.llm.api_key = 'local-eval-only'
    config.llm.model = evidence.get('model_id', 'qwen3-4b-q4_k_m')
else:
    playback_overrides = None
    if os.getenv('AVATAR_E2E_PLAYBACK_AUDIT') == '1':
        playback_overrides = {'fixture-playback-audit':
            (Path(__file__).resolve().parents[2] / 'evals/interaction/cycle-08/final-three-segments.txt').read_text().strip()}
    _, provider_url = provider_context.enter_context(controlled_provider(delay=0.02, reply_overrides=playback_overrides))
    config.llm.api_key = 'local-browser-fixture'
    config.llm.model = 'fixture'
config.llm.base_url = provider_url
config.embedding.model = ""
memory = MemoryStore(str(Path(folder.name) / "browser.db"))
if os.getenv("AVATAR_E2E_EMPTY_PROFILE") != "1":
    memory.remember_user("名字", "浏览器测试原名")
if reminder_delivery_case:
    now = time.time()
    store = ReminderStore(memory)
    original = store.create('提醒我明天下午3点到期投递实验提醒', now=now)
    with memory.transaction():
        memory._conn.execute('UPDATE memory_reminders SET due_at=? WHERE id=?', (now - 60, original['id']))
    if os.getenv('AVATAR_E2E_EVIDENCE_DIR'):
        evidence_dir = Path(os.environ['AVATAR_E2E_EVIDENCE_DIR'])
        evidence_dir.mkdir(parents=True, exist_ok=True)
        with (evidence_dir / 'fixture-seed.json').open('x') as stream:
            json.dump({'case': reminder_delivery_case, 'original_store_create': original,
                'controlled_sql': [dict(r) for r in memory._conn.execute('SELECT * FROM memory_reminders')],
                'llm_enabled': False, 'scope': 'Controlled due timestamp, no natural wait or dialog creation claim.'},
                stream, ensure_ascii=False, indent=2)
            stream.write('\n')
memory.close()
server = create_server(
    str(Path(folder.name) / "browser.db"), port=18765, legacy_writes=False,
    identity_grounding=os.getenv("AVATAR_E2E_IDENTITY_GROUNDING") == "1",
    profile_grounding=os.getenv("AVATAR_E2E_PROFILE_GROUNDING") == "1",
    task_delivery_check=os.getenv("AVATAR_E2E_TASK_DELIVERY") == "1",
    literal_composition=os.getenv("AVATAR_E2E_LITERAL_COMPOSITION") == "1"
)

# Offline fixtures exercise real browser codecs/AudioWorklet without network or models.
class FixtureTTS:
    def synthesize(self, text, path, rate, pitch):
        t = np.arange(48000) / 16000
        samples = 0.25 * np.sin(2 * np.pi * 220 * t)
        samples[(t % 1) > 0.7] = 0
        with wave.open(path, "wb") as stream:
            stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
            stream.writeframes((samples * 32767).astype("<i2").tobytes())
        return path

class FixtureASR:
    def transcribe(self, path):
        with wave.open(path) as stream:
            assert stream.getnframes() > 0
        return "浏览器识别草稿"

if os.getenv("AVATAR_E2E_REAL_TTS") != "1":
    server.speech.engine = FixtureTTS()
if os.getenv('AVATAR_E2E_REAL_ASR_MODEL'):
    if os.getenv('AVATAR_E2E_ASR_DEVICE') == 'cuda':
        # Check at process startup, not from a previous interactive shell snapshot.
        raw = subprocess.check_output(['nvidia-smi',
            '--query-gpu=index,uuid,memory.free,utilization.gpu',
            '--format=csv,noheader,nounits'], text=True)
        print('ASR GPU snapshot at startup:\n' + raw, flush=True)
        from avatar.gpu_resources import select_available_gpu
        mask = os.environ.get('CUDA_VISIBLE_DEVICES')
        group = evidence['chosen_gpu']['index'] // 4 if os.getenv('AVATAR_E2E_LLM_PROVIDER') else None
        inventory = []
        for line in raw.splitlines():
            index, uid, free, util = (part.strip() for part in line.split(','))
            inventory.append({'index':int(index),'uuid':uid,'free_mib':int(free),'utilization_percent':int(util)})
        chosen = select_available_gpu(inventory,required_free_mib=8192,visible_mask=mask,required_group=group)
        os.environ['CUDA_VISIBLE_DEVICES'] = chosen['uuid']
        print('ASR selected GPU UUID: ' + chosen['uuid'], flush=True)
        if os.getenv('AVATAR_E2E_EVIDENCE_DIR'):
            artifact_folder = Path(os.environ['AVATAR_E2E_EVIDENCE_DIR'])
            artifact_folder.mkdir(parents=True, exist_ok=True)
            with (artifact_folder / 'asr-gpu-launch.json').open('x') as artifact:
                json.dump({'snapshot': raw, 'chosen_uuid': chosen['uuid'], 'chosen_index': chosen['index'],
                    'free_mib': chosen['free_mib'], 'required_free_mib': 8192,
                    'required_group': group, 'visible_mask': mask}, artifact, indent=2)
    from avatar.ears.asr import FasterWhisperEngine
    server.transcription.engine = FasterWhisperEngine(os.environ['AVATAR_E2E_REAL_ASR_MODEL'],
        device=os.getenv('AVATAR_E2E_ASR_DEVICE','cpu'))
else:
    server.transcription.engine = FixtureASR()
server.token = "mission-control-disposable-e2e-token"
stopping = threading.Event()

def request_shutdown(signum, frame):
    if not stopping.is_set():
        stopping.set()
        # BaseServer.shutdown must run outside the serve_forever thread.
        threading.Thread(target=server.shutdown, daemon=True).start()

for stop_signal in (signal.SIGTERM, signal.SIGINT):
    signal.signal(stop_signal, request_shutdown)

try:
    server.serve_forever()
finally:
    server.server_close()
    provider_context.close()
    folder.cleanup()
