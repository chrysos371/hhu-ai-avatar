"""Timeline timestamps must represent actual PCM windows, including file API."""
import hashlib
import json
from pathlib import Path
import wave
import numpy as np
import pytest
from avatar.face.lipsync import LipSyncEngine
from avatar.main import Avatar
from avatar.brain.memory import MemoryStore
ROOT=Path(__file__).resolve().parents[1]
SPEC=json.loads((ROOT/'evals/audio/cycle-07/timeline-protocol.json').read_text())
REFERENCE=json.loads((ROOT/'evals/audio/cycle-07/noninteger-reference.json').read_text())


@pytest.mark.parametrize('sr',SPEC['sample_rates'])
@pytest.mark.parametrize('hop',SPEC['hop_ms'])
def test_frame_start_tracks_integer_pcm_offset(sr,hop):
    frames=LipSyncEngine(hop_ms=hop).analyze(np.zeros(sr*2,dtype=np.float32),sr)
    sample_hop=int(sr*hop/1000)
    assert max(abs(frame.time*sr-index*sample_hop) for index,frame in enumerate(frames))<=1e-6
    assert frames[-1].time*sr+int(sr*.025)<=sr*2+1e-6


@pytest.mark.parametrize('case',REFERENCE['rows'])
def test_sample_clock_fix_preserves_every_acoustic_field(case):
    sr=case['sample_rate'];hop=case['hop_ms']
    samples=(.1*np.sin(2*np.pi*300*np.arange(sr*2)/sr)).astype(np.float32)
    assert hashlib.sha256(samples.tobytes()).hexdigest()==case['pcm_sha256']
    frames=LipSyncEngine(hop_ms=hop).analyze(samples,sr)
    assert len(frames)==len(case['frames'])
    assert [[f.mouth_open,f.vowel,f.energy] for f in frames]==[row[1:] for row in case['frames']]
    if sr*hop/1000==int(sr*hop/1000):assert [f.time for f in frames]==[row[0] for row in case['frames']]


def test_actual_avatar_local_wave_tts_uses_sample_accurate_timeline(tmp_path):
    class Offline:available=False
    class LocalWave:
        def synthesize(self,text,path,rate,pitch):
            sr=22050
            samples=.1*np.sin(2*np.pi*300*np.arange(sr*2)/sr)
            with wave.open(path,'wb') as target:
                target.setparams((1,2,sr,0,'NONE','not compressed'))
                target.writeframes((samples*32767).astype('<i2').tobytes())
            return path
    memory=MemoryStore(':memory:')
    bot=Avatar(memory=memory,llm=Offline(),tts=LocalWave())
    try:
        result=bot.respond('读一段测试。',use_tts=True,tts_path=str(tmp_path/'clock.wav'))
        assert result['lipsync_error'] is None
        frames=result['lip_sync_frames'];assert frames
        assert max(abs(row['time']*22050-index*220) for index,row in enumerate(frames))<=1e-6
    finally:memory.close()
