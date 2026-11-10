import sys
from types import SimpleNamespace
from unittest.mock import patch
import wave

import numpy as np
import pytest

from avatar.utils.audio import load_audio, AudioDurationError


def test_pcm_metadata_is_rejected_before_frame_read(tmp_path):
    path=tmp_path/'long.wav'
    with wave.open(str(path),'wb') as audio:
        audio.setparams((1,2,16000,0,'NONE','not compressed'))
        audio.writeframes(np.zeros(3200,dtype='<i2').tobytes())
    with patch.object(wave.Wave_read,'readframes',side_effect=AssertionError('must not allocate')):
        with pytest.raises(AudioDurationError):load_audio(path,max_seconds=.1)
    samples,rate=load_audio(path,max_seconds=.3)
    assert len(samples)==3200 and rate==16000


def test_soundfile_checks_metadata_and_bounds_read_even_when_metadata_understates(tmp_path):
    sf=pytest.importorskip('soundfile')
    path=tmp_path/'audio.mp3';path.write_bytes(b'ID3'+b'x'*20)
    info=SimpleNamespace(samplerate=16000,frames=100000)
    with patch.object(sf,'info',return_value=info),patch.object(sf,'read') as read:
        with pytest.raises(AudioDurationError):load_audio(path,max_seconds=.1)
        read.assert_not_called()
    info.frames=100
    with patch.object(sf,'info',return_value=info),patch.object(sf,'read',return_value=(np.zeros((1601,1)),16000)) as read:
        with pytest.raises(AudioDurationError):load_audio(path,max_seconds=.1)
        assert read.call_args.kwargs['frames']==1601
    with patch.object(sf,'info',return_value=info),patch.object(sf,'read',return_value=(np.zeros((100,1)),16000)):
        samples,rate=load_audio(path,max_seconds=.1)
        assert len(samples)==100 and rate==16000


def test_librosa_fallback_also_receives_a_duration_budget(tmp_path,monkeypatch):
    sf=pytest.importorskip('soundfile')
    path=tmp_path/'fallback.mp3';path.write_bytes(b'ID3'+b'x'*20)
    def load(*args,**kwargs):
        assert kwargs['duration']==pytest.approx(.1+1/48000)
        return np.zeros(100),48000
    monkeypatch.setitem(sys.modules,'librosa',SimpleNamespace(get_samplerate=lambda path:48000,load=load))
    with patch.object(sf,'info',side_effect=RuntimeError('unsupported codec')):
        samples,rate=load_audio(path,max_seconds=.1)
        assert len(samples)==100 and rate==48000
