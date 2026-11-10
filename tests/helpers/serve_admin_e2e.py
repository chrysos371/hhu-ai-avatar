"""Disposable, offline browser-test fixture. Never opens the user's database."""

from contextlib import ExitStack
import json
from urllib.parse import urlsplit
from pathlib import Path
import os
import tempfile
import subprocess
import wave
import numpy as np
from avatar.config import config
from avatar.brain.memory import MemoryStore
from avatar.web import create_server
from avatar.lab.transport_fixture import controlled_provider

root = Path(__file__).resolve().parents[3]
folder = tempfile.TemporaryDirectory(prefix="admin-e2e-", dir=root / "runtime/tmp")
provider_context = ExitStack()
if os.getenv('AVATAR_E2E_LLM_PROVIDER'):
    evidence = json.loads(Path(os.environ['AVATAR_E2E_LLM_PROVIDER']).read_text())
    provider_url = evidence['url']
    parsed = urlsplit(provider_url)
    if parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or parsed.path != '/v1':
        raise ValueError('Real browser evaluation requires an explicit loopback provider')
    config.llm.api_key = 'local-eval-only'
    config.llm.model = evidence.get('model_id', 'qwen3-4b-q4_k_m')
else:
    _, provider_url = provider_context.enter_context(controlled_provider(delay=0.02))
    config.llm.api_key = 'local-browser-fixture'
    config.llm.model = 'fixture'
config.llm.base_url = provider_url
config.embedding.model = ""
memory = MemoryStore(str(Path(folder.name) / "browser.db"))
if os.getenv("AVATAR_E2E_EMPTY_PROFILE") != "1":
    memory.remember_user("名字", "浏览器测试原名")
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
try:
    server.serve_forever()
finally:
    server.server_close()
    provider_context.close()
    folder.cleanup()
