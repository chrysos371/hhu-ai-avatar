import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('smoke', Path(__file__).resolve().parents[1] / 'scripts/train_companion_smoke.py')
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)


class Tokenizer:
    eos_token_id = 9

    def apply_chat_template(self, messages, **kwargs):
        assert kwargs['enable_thinking'] is False
        assert messages[-1]['role'] == 'user'
        return [1, 2, 3, 4]

    def encode(self, text, **kwargs):
        return [5, 6]


def test_only_final_assistant_target_and_eos_are_supervised():
    row = dict(id='test', messages=[{'role': role, 'content': 'test'}
                                  for role in ['system', 'user', 'assistant', 'user', 'assistant']])
    result = smoke.encode_record(Tokenizer(), row, 7)
    assert result == {'input_ids': [1, 2, 3, 4, 5, 6, 9], 'labels': [-100] * 4 + [5, 6, 9]}
    with pytest.raises(ValueError, match='overlength'):
        smoke.encode_record(Tokenizer(), row, 6)
