"""Archived pre-optimization outputs: exact spectral and full-engine parity."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pytest
from avatar.face.lipsync import _formants, LipSyncEngine
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from evaluate_analytic_lipsync import synthesize
REFERENCE=json.loads((ROOT/'evals/audio/cycle-06/cache-reference.json').read_text())
SPEC=json.loads((ROOT/'evals/audio/cycle-05/analytic-formants.json').read_text())

@pytest.mark.parametrize('case',REFERENCE['coefficient_cases'])
def test_spectral_output_matches_frozen_pre_cache_reference(case):
    got=_formants(np.array(case['coefficients']),case['sample_rate'])
    assert np.array_equal(got,np.array(case['expected']))

@pytest.mark.parametrize('case',REFERENCE['component_cases'])
def test_all_component_fields_match_frozen_pre_cache_frames(case):
    waveform=synthesize(SPEC,SPEC['anchors'][case['anchor_index']],case['sample_rate'],
        case['excitation'],case['f0'],case['rms'],case['seed'])
    assert hashlib.sha256(waveform.tobytes()).hexdigest()==case['waveform_sha256']
    frames=LipSyncEngine().analyze(waveform,case['sample_rate'])
    assert [[frame.time,frame.mouth_open,frame.vowel,frame.energy] for frame in frames]==case['frames']
