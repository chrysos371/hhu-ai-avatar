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


def test_cached_geometry_cannot_be_mutated():
    from avatar.face.lipsync import _formant_basis
    grid,basis=_formant_basis(512,19)
    with pytest.raises(ValueError):grid[0]=1
    with pytest.raises(ValueError):basis[0][0]=2


def test_cache_entries_are_bounded_across_configurations():
    from avatar.face.lipsync import _formant_basis
    _formant_basis.cache_clear()
    for resolution in range(257,281):_formant_basis(resolution,19)
    assert _formant_basis.cache_info().currsize==8


def test_returned_frequencies_do_not_alias_cached_geometry():
    case=REFERENCE['coefficient_cases'][0]
    coefficients=np.array(case['coefficients'])
    result=_formants(coefficients,case['sample_rate'])
    result[:]=0
    assert np.array_equal(_formants(coefficients,case['sample_rate']),case['expected'])


def test_shared_cache_is_exact_across_concurrent_configurations():
    from concurrent.futures import ThreadPoolExecutor
    cases=REFERENCE['coefficient_cases']*4
    with ThreadPoolExecutor(max_workers=4) as executor:
        results=list(executor.map(lambda case:_formants(np.array(case['coefficients']),case['sample_rate']),cases))
    assert all(np.array_equal(result,case['expected']) for result,case in zip(results,cases))
