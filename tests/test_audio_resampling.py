import numpy as np
import pytest

from avatar.cancellation import CancellationToken, Cancelled
from avatar.utils.audio import downsample_for_analysis


@pytest.mark.parametrize('sr,frequency',[(24000,2000),(48000,2000),(24000,10000),(48000,14000)])
def test_passband_preserved_and_above_nyquist_rejected(sr,frequency):
    signal=.1*np.sin(2*np.pi*frequency*np.arange(sr)/sr)
    output,rate=downsample_for_analysis(signal,sr)
    rms=np.sqrt(np.mean(output[1600:-1600]**2))
    gain=20*np.log10(max(rms,1e-12)/(.1/np.sqrt(2)))
    assert rate==16000 and len(output)==16000 and np.isfinite(output).all()
    assert abs(gain)<1 if frequency==2000 else gain < -40


def test_impulse_keeps_time_and_short_and_empty_inputs_are_finite():
    signal=np.zeros(48000,dtype=np.float32);signal[24000]=1
    output,rate=downsample_for_analysis(signal,48000)
    assert np.argmax(np.abs(output))==8000 and rate==16000
    for size in [0,1,2,15]:
        output,_=downsample_for_analysis(np.zeros(size,dtype=np.float32),48000)
        assert np.isfinite(output).all() and np.all(output==0)
    signal=np.arange(80,dtype=np.float32)
    output,rate=downsample_for_analysis(signal,8000)
    assert rate==8000 and np.array_equal(output,signal)


def test_cancellation_during_long_filtering_is_observed():
    class Midway(CancellationToken):
        checks=0
        def checkpoint(self):
            self.checks+=1
            if self.checks==3:self.cancel()
            super().checkpoint()
    token=Midway()
    with pytest.raises(Cancelled):
        downsample_for_analysis(np.zeros(48000*4),48000,cancel=token)
    assert token.checks==3
