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
