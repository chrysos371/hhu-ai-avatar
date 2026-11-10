"""Stationary source timing, explicit legacy closure, and public input limits."""
import json
from pathlib import Path
import sys
import numpy as np
import pytest
from avatar.face.lipsync import LipSyncEngine
from avatar.cancellation import CancellationToken, Cancelled
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from evaluate_analytic_lipsync import synthesize
SPEC=json.loads((ROOT/'evals/audio/cycle-05/analytic-formants.json').read_text())


def test_stationary_source_does_not_get_periodic_unvoiced_closures_by_default():
    signal=synthesize(SPEC,SPEC['anchors'][0],16000,'harmonic',100,.12,11)
    frames=LipSyncEngine().analyze(signal,16000)
    interior=np.array([frame.mouth_open for frame in frames if .1<=frame.time<=.65])
    assert interior.min()>.5*np.median(interior)


def test_explicit_legacy_cosmetic_closures_remain_available():
    signal=synthesize(SPEC,SPEC['anchors'][0],16000,'harmonic',100,.12,11)
    frames=LipSyncEngine(close_every=.3).analyze(signal,16000)
    interior=np.array([frame.mouth_open for frame in frames if .1<=frame.time<=.65])
    assert sum(interior<.25*np.median(interior))==2


@pytest.mark.parametrize('kwargs',[
    {'frame_ms':0},{'frame_ms':float('nan')},{'frame_ms':True},
    {'hop_ms':0},{'hop_ms':-1},{'hop_ms':float('inf')},
    {'smooth':0},{'smooth':1.5},{'smooth':True},
    {'silence_ratio':-1},{'silence_ratio':float('nan')},{'silence_ratio':1.1},
    {'close_every':0},{'close_every':-1},{'close_every':float('nan')},
])
def test_invalid_component_options_fail_before_analysis(kwargs):
    with pytest.raises(ValueError):LipSyncEngine(**kwargs)


@pytest.mark.parametrize('signal,sr',[
    (np.zeros((10,2)),16000),(np.array([float('nan')]),16000),
    (np.array([float('inf')]),16000),(np.array([1.1]),16000),
    (np.zeros(10),0),(np.zeros(10),-1),(np.zeros(10),True),
    (np.zeros(10),16000.5),(np.zeros(10),1),(np.zeros(10),400000),
])
def test_invalid_pcm_or_sampling_metadata_is_rejected(signal,sr):
    with pytest.raises(ValueError):LipSyncEngine().analyze(signal,sr)


def test_cancelled_empty_analysis_propagates_cancellation():
    token=CancellationToken();token.cancel()
    with pytest.raises(Cancelled):LipSyncEngine().analyze(np.zeros(0),16000,cancel=token)

@pytest.mark.parametrize('dtype',[np.int32,np.int64])
def test_minimum_signed_integer_is_not_accepted_as_normalized_pcm(dtype):
    signal=np.full(500,np.iinfo(dtype).min,dtype=dtype)
    with pytest.raises(ValueError):LipSyncEngine().analyze(signal,16000)


@pytest.mark.parametrize('option',['frame_ms','hop_ms'])
def test_finite_but_unrepresentable_window_is_rejected_as_metadata(option):
    with pytest.raises(ValueError):LipSyncEngine(**{option:1e308}).analyze(np.zeros(800),16000)


def test_very_long_explicit_closure_interval_is_a_noop_for_short_audio():
    samples=(.1*np.sin(2*np.pi*300*np.arange(8000)/16000)).astype(np.float32)
    normal=LipSyncEngine().analyze(samples,16000)
    long_period=LipSyncEngine(close_every=1e308).analyze(samples,16000)
    assert [frame.mouth_open for frame in long_period]==[frame.mouth_open for frame in normal]
