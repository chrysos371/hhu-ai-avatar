"""Existing C19 material is known regression data, never new independent gold."""
import json
from pathlib import Path

import pytest

from avatar.brain.capability_requests import explicit_unavailable_request
from avatar.brain.response_frames import _advance_frame

ROOT = Path(__file__).resolve().parents[1]
CASES = {c['id']: c for c in json.loads((ROOT/'evals/interaction/cycle-19/capability-output-protocol.json').read_text())['cases']}


@pytest.mark.parametrize('ident,channel', [
    ('dev_sms_execution', 'sms'), ('dev_email_execution', 'email'), ('dev_phone_execution', 'phone'),
    ('dev_future_send_offer', 'message'), ('pros_email_send', 'email'), ('pros_phone', 'phone'),
    ('pros_group_message', 'message'), ('pros_future_authorization', 'sms'),
])
def test_known_explicit_external_request_is_not_left_to_model_invention(ident, channel):
    parsed = explicit_unavailable_request(CASES[ident]['turns'][0])
    assert parsed is not None and parsed.channel == channel


@pytest.mark.parametrize('ident', ['dev_known_sms_draft', 'dev_polite_draft', 'dev_literal_sent_draft',
    'dev_native_reply_draft', 'pros_sms_rewrite', 'pros_literal_offer_draft'])
def test_known_genuine_writing_requests_keep_their_root(ident):
    writing = False
    for text in CASES[ident]['turns']:
        writing, _ = _advance_frame(text, writing)
        assert writing is True
        assert explicit_unavailable_request(text) is None
