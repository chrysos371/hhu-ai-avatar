import pytest
from avatar.gpu_resources import select_available_gpu


@pytest.fixture
def cards():
    return [dict(index=i,uuid=f'GPU-fake-{i}',free_mib=40000,utilization_percent=0) for i in range(8)]


@pytest.mark.parametrize('mask',['6','GPU-fake-6',' 6 '])
def test_explicit_mask_is_respected_even_when_other_cards_are_freer(cards,mask):
    cards[6]['free_mib']=30000
    chosen=select_available_gpu(cards,required_free_mib=24576,visible_mask=mask)
    assert chosen['index']==6


@pytest.mark.parametrize('mask',['','-1','99','6,99','6,','GPU-unknown'])
def test_disabled_or_invalid_mask_cannot_escape_to_other_cards(cards,mask):
    with pytest.raises(RuntimeError):select_available_gpu(cards,required_free_mib=24576,visible_mask=mask)


def test_insufficient_visible_card_is_rejected_without_cpu_or_other_card_fallback(cards):
    cards[6]['free_mib']=100
    with pytest.raises(RuntimeError):select_available_gpu(cards,required_free_mib=24576,visible_mask='6')
    assert select_available_gpu(cards,required_free_mib=24576,visible_mask='6,7')['index']==7


def test_dynamic_headroom_and_same_group_are_combined_with_visibility(cards):
    for row in cards[:4]:row['free_mib']=0
    cards[6]['utilization_percent']=90
    chosen=select_available_gpu(cards,required_free_mib=8192,required_group=1,visible_mask='0,6,7')
    assert chosen['index']==7
    with pytest.raises(RuntimeError):select_available_gpu(cards,required_free_mib=8192,required_group=0)
    assert select_available_gpu(cards,required_free_mib=8192,allowed_indices={5})['index']==5
