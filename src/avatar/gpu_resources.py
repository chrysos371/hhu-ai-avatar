"""Pure GPU admission policy; inventory collection and CUDA initialization stay outside."""
from __future__ import annotations


def select_available_gpu(inventory, *, required_free_mib, visible_mask=None,
                         max_utilization=20, required_group=None, allowed_indices=None):
    visible = None
    if visible_mask is not None:
        if visible_mask.strip() in ('', '-1'):
            visible = set()
        else:
            visible = {value.strip() for value in visible_mask.split(',')}
            known = {str(row['index']) for row in inventory} | {row['uuid'] for row in inventory}
            if not visible or not visible <= known:
                raise RuntimeError('CUDA visible mask contains an unknown device')
    candidates = [row for row in inventory
        if row['free_mib'] >= required_free_mib and row['utilization_percent'] <= max_utilization
        and (visible is None or str(row['index']) in visible or row['uuid'] in visible)
        and (required_group is None or row['index']//4 == required_group)
        and (allowed_indices is None or row['index'] in allowed_indices)]
    if not candidates:
        raise RuntimeError('No currently visible GPU meets headroom/group gate')
    return dict(max(candidates,key=lambda row:(row['free_mib'],-row['utilization_percent'],-row['index'])))
