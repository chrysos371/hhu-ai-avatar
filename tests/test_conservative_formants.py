"""Finite candidate boundaries; experimental mode cannot silently activate."""
import json
from pathlib import Path
import sys
import numpy as np
import pytest
from avatar.face.lipsync import LipSyncEngine,_lpc,_formants
from avatar.lab.conservative_lipsync import ConservativeLipSyncExperiment,_conservative_formants
from avatar.utils.audio import frame_signal
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from evaluate_analytic_lipsync import synthesize
SPEC=json.loads((ROOT/'evals/audio/cycle-05/analytic-formants.json').read_text())


def test_default_remains_legacy():
    assert not isinstance(LipSyncEngine(),ConservativeLipSyncExperiment)


@pytest.mark.parametrize('mode',[None,False,[],{},'automatic','roots400'])
def test_invalid_mode_does_not_silently_choose_an_extractor(mode):
    with pytest.raises(TypeError):LipSyncEngine(formant_mode=mode)


def test_f1_region_crossing_is_rejected_on_observed_wrong_unknown_assignment():
    signal=synthesize(SPEC,SPEC['anchors'][3],48000,'white_noise',100,.03,11)
    coefficients=_lpc(frame_signal(signal,sr=48000)[19],24)
    old=_formants(coefficients,48000)
    assert len(old)==1
    assert np.array_equal(_conservative_formants(coefficients,48000),old)


def test_complete_legacy_spectrum_is_preserved_exactly():
    for anchor in SPEC['anchors']:
        coefficients=np.array([1.])
        for frequency,bandwidth in zip(anchor['formants_hz'],SPEC['bandwidths_hz']):
            radius=np.exp(-np.pi*bandwidth/16000)
            coefficients=np.convolve(coefficients,[1.,-2*radius*np.cos(2*np.pi*frequency/16000),radius*radius])
        old=_formants(coefficients,16000)
        assert len(old)>=2
        assert np.array_equal(_conservative_formants(coefficients,16000),old)


def test_experimental_silence_stays_closed():
    frames=ConservativeLipSyncExperiment().analyze(np.zeros(16000,dtype=np.float32),16000)
    assert frames and all(frame.mouth_open==0 and frame.vowel=='' for frame in frames)
