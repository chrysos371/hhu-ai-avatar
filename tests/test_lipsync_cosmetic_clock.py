"""Explicit cosmetic events obey an absolute period, with bounded quantization."""
import json
from pathlib import Path
import sys
import numpy as np
import pytest
from avatar.face.lipsync import LipSyncEngine
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from evaluate_analytic_lipsync import synthesize
SPEC=json.loads((ROOT/'evals/audio/cycle-05/analytic-formants.json').read_text())


@pytest.mark.parametrize('sr,period,duration',[(22050,.3,4),(16000,.035,2),(16000,.3,2)])
def test_explicit_period_stays_within_half_sample_hop_of_absolute_targets(sr,period,duration):
    settings=dict(SPEC);settings['duration_seconds']=duration
    samples=synthesize(settings,settings['anchors'][0],sr,'harmonic',100,.12,11)
    base=LipSyncEngine().analyze(samples,sr)
    decorated=LipSyncEngine(close_every=period).analyze(samples,sr)
    events=[frame.time for original,frame in zip(base,decorated) if original.mouth_open!=frame.mouth_open]
    assert len(events)==int(base[-1].time/period)
    assert max(abs(t-(i+1)*period) for i,t in enumerate(events))<=int(sr*.01)/sr/2+1e-12
    assert [(f.time,f.vowel,f.energy) for f in base]==[(f.time,f.vowel,f.energy) for f in decorated]


def test_tiny_explicit_period_is_bounded_to_frame_count():
    samples=synthesize(SPEC,SPEC['anchors'][0],16000,'harmonic',100,.12,11)
    base=LipSyncEngine().analyze(samples,16000)
    decorated=LipSyncEngine(close_every=1e-308).analyze(samples,16000)
    assert len(decorated)==len(base)
    assert decorated[0].mouth_open==base[0].mouth_open
    assert all(b.mouth_open==(.05 if a.mouth_open>.3 else a.mouth_open) for a,b in zip(base[1:],decorated[1:]))


@pytest.mark.parametrize('sr,hop',[(11025,.27210884353741494),(22050,.13605442176870747),(44100,.06802721088435373)])
def test_operation_order_edge_uses_actual_two_sample_hop(sr,hop):
    assert int(sr*hop/1000)==2
    frames=LipSyncEngine(hop_ms=hop).analyze(np.zeros(2000,dtype=np.float32),sr)
    assert len(frames)==1+(2000-int(sr*.025))//2
    assert max(abs(f.time*sr-i*2) for i,f in enumerate(frames))<=1e-6
