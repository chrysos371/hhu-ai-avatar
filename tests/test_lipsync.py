"""口型同步（自研元音驱动）测试。"""
import numpy as np

from avatar.face.lipsync import LipSyncEngine, _classify_vowel, _lpc


def test_lpc_stable_and_shape():
    rng = np.random.default_rng(0)
    sig = rng.standard_normal(600).astype(np.float32)
    a = _lpc(sig, 16)
    assert a.shape == (17,)
    assert a[0] == 1.0
    assert np.all(np.isfinite(a))


def test_vowel_classify():
    assert _classify_vowel(750, 1300) == "a"  # 高 F1、低 F2 -> a
    assert _classify_vowel(300, 2500) == "i"  # 低 F1、高 F2 -> i
    assert _classify_vowel(350, 750) == "u"   # 低 F1、低 F2 -> u


def test_analyze_sine_returns_valid_frames():
    sr = 24000
    t = np.arange(int(sr * 0.5)) / sr
    sig = (0.5 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
    eng = LipSyncEngine()
    frames = eng.analyze(sig, sr)
    assert len(frames) > 0
    for f in frames:
        assert 0.0 <= f.mouth_open <= 1.0

def test_silent_audio_returns_finite_closed_frames():
    for sig in (np.zeros(12000, dtype=np.float32),
                np.full(12000, 1e-9, dtype=np.float32)):
        frames = LipSyncEngine().analyze(sig, 24000)
        assert frames
        assert all(f.mouth_open == 0 and f.vowel == '' and f.energy == 0 for f in frames)

def test_low_level_noise_does_not_become_full_scale_mouth_motion():
    noise = np.random.default_rng(17).normal(0, 0.0003, 16000).astype(np.float32)
    frames = LipSyncEngine().analyze(noise, 16000)
    assert frames and all(frame.mouth_open == 0 for frame in frames)


def test_smoothing_never_reopens_a_silent_pause():
    sr = 16000
    samples = (0.2 * np.sin(2 * np.pi * 220 * np.arange(sr) / sr)).astype(np.float32)
    samples[int(sr*0.3):int(sr*0.7)] = 0
    frames = LipSyncEngine(smooth=9).analyze(samples, sr)
    assert any(frame.mouth_open > 0.05 for frame in frames if frame.time < 0.2)
    assert all(frame.mouth_open == 0 for frame in frames if 0.32 <= frame.time <= 0.65)
