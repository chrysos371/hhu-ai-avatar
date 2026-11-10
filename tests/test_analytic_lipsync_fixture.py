"""Check signal fixture against its explicit spectrum and amplitude contract."""
import json
from pathlib import Path
import sys
import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from evaluate_analytic_lipsync import synthesize
SPEC=json.loads((ROOT/'evals/audio/cycle-05/analytic-formants.json').read_text())

@pytest.mark.parametrize('sr',[16000,24000,48000])
def test_harmonic_below_cutoff_is_not_dropped_at_fractional_harmonic_count(sr):
    anchor=SPEC['anchors'][0]
    samples=synthesize(SPEC,anchor,sr,'harmonic',180,.03,11)
    coefficients=np.array([1.])
    for frequency,bandwidth in zip(anchor['formants_hz'],SPEC['bandwidths_hz']):
        radius=np.exp(-np.pi*bandwidth/sr)
        coefficients=np.convolve(coefficients,[1,-2*radius*np.cos(2*np.pi*frequency/sr),radius*radius])
    restored=np.fft.rfft(samples)*np.fft.rfft(coefficients,n=len(samples))
    index=lambda frequency:round(frequency*len(samples)/sr)
    ratio=abs(restored[index(27*180)])/abs(restored[index(180)])
    assert ratio==pytest.approx(1/27,rel=.01,abs=1e-5)

@pytest.mark.parametrize('excitation',['white_noise','harmonic'])
def test_analytic_fixture_has_declared_rms_and_finite_pcm(excitation):
    samples=synthesize(SPEC,SPEC['anchors'][0],16000,excitation,180,.03,11)
    assert np.isfinite(samples).all() and np.max(np.abs(samples))<1
    assert np.sqrt(np.mean(samples**2))==pytest.approx(.03,rel=1e-5)
