"""Controlled transport evidence only; no prospective prompts or CUDA claim."""
import importlib.util
import json
from pathlib import Path
import sys
from urllib.request import ProxyHandler, build_opener

import pytest

from avatar.config import config
from avatar.lab.transport_fixture import controlled_provider
from avatar.main import Avatar
import avatar.main as main_module

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('body_pair', SCRIPTS/'evaluate_body_review_pair.py')
pair = importlib.util.module_from_spec(spec); spec.loader.exec_module(pair)
sys.path.remove(str(SCRIPTS))


@pytest.mark.parametrize('candidate', [False, True])
def test_actual_http_sse_pair_arm_preserves_or_buffers_controlled_body(monkeypatch, candidate):
    claim = '那我们下次可以一起去爬山，享受大自然的风景。'
    with controlled_provider(delay=.001, reply_overrides={'fixture-pair': claim}) as (_, url):
        monkeypatch.setattr(config.llm, 'base_url', url)
        monkeypatch.setattr(config.llm, 'api_key', 'fixture')
        monkeypatch.setattr(config.llm, 'model', 'fixture')
        monkeypatch.setattr(config.embedding, 'model', '')
        arm = 'candidate_lab_buffered_review' if candidate else 'baseline_current_defaults'
        row = pair.collect_arm({'id': 'cpu_transport', 'frame': 'fixture', 'turns': ['fixture-pair']},
            arm, build_opener(ProxyHandler({})))
    assert row['completed'], row['error']
    turn = row['turns'][0]
    assert turn['visible'] == turn['result']['reply'] == turn['stored_assistants'][0]
    assert (turn['visible'] != claim) == candidate
    assert turn['result']['generation_mode'] == ('reviewed_response' if candidate else 'llm')
    assert main_module.Avatar is Avatar


def test_trace_correlation_uses_byte_offset_and_current_input(tmp_path):
    path = tmp_path/'trace.jsonl'
    old = {'id': 'old', 'analysis': False, 'messages': [{'role': 'user', 'content': 'fixture'}],
           'response': '旧', 'finish_reason': 'stop', 'outcome': 'completed'}
    path.write_text(json.dumps(old)+'\n'); offset = path.stat().st_size
    current = {**old, 'id': 'new', 'response': '新'}
    with path.open('a') as stream: stream.write(json.dumps(current)+'\n')
    calls, native = pair.native_calls(path, offset, 'fixture')
    assert len(calls) == 1 and native['id'] == 'new'
    current['finish_reason'] = 'length'; path.write_text(json.dumps(current)+'\n')
    with pytest.raises(ValueError, match='truncated'): pair.native_calls(path, 0, 'fixture')


def test_frozen_candidate_rejects_changed_bytes(tmp_path):
    manifest = tmp_path/'freeze.json'
    manifest.write_text(json.dumps({'prospective_execution_authorized': True,
        'sha256': {'src/avatar/lab/body_review.py': 'wrong'}}))
    with pytest.raises(ValueError, match='mismatch'): pair.verify_freeze(manifest)
