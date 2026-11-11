"""Rejected synthetic candidate, retained for research replay only.

Cycle06 prospective gate failed one unknown-to-wrong assignment. This class is
not wired into Avatar, speech service, CLI or the production engine options.
"""
import numpy as np
from ..face.lipsync import LipSyncEngine, _formants, _classify_vowel


def _conservative_formants(a: np.ndarray, sr: int) -> np.ndarray:
    """Experimental missing-peak fallback; never replace a complete legacy pair."""
    legacy = _formants(a, sr)
    if len(legacy) != 1:
        return legacy
    try:
        poles = np.roots(a)
    except np.linalg.LinAlgError:
        return legacy
    radii = np.abs(poles)
    poles = poles[(poles.imag > 1e-6) & (radii > 0) & (radii < 1)]
    frequencies = np.angle(poles) * sr / (2 * np.pi)
    bandwidths = -sr * np.log(np.abs(poles)) / np.pi
    roots = np.sort(frequencies[(frequencies > 200) & (frequencies < 4000)
                                & (bandwidths > 0) & (bandwidths <= 400)])
    if len(roots) < 2 or abs(legacy[0] - roots[0]) > 50:
        return legacy
    # Refinement must not cross existing F1 decision regions. Probe each F2
    # region through the classifier itself rather than duplicating thresholds.
    if any(_classify_vowel(legacy[0], probe) != _classify_vowel(roots[0], probe)
           for probe in (500., 1500., 2500.)):
        return legacy
    return roots


class ConservativeLipSyncExperiment(LipSyncEngine):
    """Laboratory candidate; no human phonetic or general quality approval."""

    def _extract_formants(self, coefficients, sample_rate):
        return _conservative_formants(coefficients, sample_rate)
