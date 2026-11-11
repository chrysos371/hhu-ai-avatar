import pytest
from avatar.lab.checks import compare_reports


@pytest.mark.parametrize('times,p50,p95', [([],None,None),([4],4,4),([0,10],5,9.5),(list(range(60)),29.5,56.05)])
def test_latency_uses_standard_median_and_inclusive_linear_percentile(times,p50,p95):
    row={'id':'case','hard_failures':[],'style_warnings':[],'model_seconds':0,'tokens':0,'turn_seconds':times}
    metrics=compare_reports({'base':[row]})['arms']['base']
    if p50 is None:
        assert metrics['turn_seconds_p50'] is metrics['turn_seconds_p95'] is None
    else:
        assert metrics['turn_seconds_p50']==pytest.approx(p50)
        assert metrics['turn_seconds_p95']==pytest.approx(p95)
