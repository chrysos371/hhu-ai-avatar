"""Supported application configuration; direct SDK callers remain explicit."""


def release_options():
    return dict(capability_contract_enabled=True,role_state_enabled=True)
