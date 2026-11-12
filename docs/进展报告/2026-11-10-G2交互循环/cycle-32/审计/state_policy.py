"""Explicit interventions on one owned llama-cpp0.3.19 model context only."""
POLICIES=('reuse','logical_reset','memory_clear_reset')


def apply_policy(model,policy):
    if policy not in POLICIES:raise ValueError('Unknown owned-model state policy')
    before=int(model.n_tokens);reset=False;clear=False
    if policy=='memory_clear_reset':
        if model._ctx.memory is None:raise RuntimeError('Owned model context memory is unavailable')
        model._ctx.kv_cache_clear();clear=True
    if policy!='reuse':model.reset();reset=True
    after=int(model.n_tokens)
    if reset and after!=0:raise RuntimeError('Explicit logical token reset did not reach zero')
    return {'policy':policy,'logical_tokens_before_policy':before,'logical_tokens_after_policy':after,
        'explicit_logical_reset_called':reset,'explicit_context_memory_clear_called':clear,
        'library_internal_resets_not_counted':True,'general_physical_state_guarantee':False}
