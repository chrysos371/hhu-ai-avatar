import io
import json

import numpy as np
import pytest

from avatar.brain.embeddings import OllamaEmbeddingProvider, normalized_vector


def test_ollama_adapter_sends_input_without_silent_truncation(monkeypatch):
    def respond(request, timeout):
        assert request.full_url == 'http://localhost:11434/api/embed'
        payload = json.loads(request.data)
        assert payload == {'model': 'bge-m3', 'input': '我养了一只猫', 'truncate': False}
        assert timeout == 5
        return io.BytesIO(json.dumps({'embeddings': [[3.0, 4.0]]}).encode())

    monkeypatch.setattr('urllib.request.urlopen', respond)
    provider = OllamaEmbeddingProvider('http://localhost:11434/', 'bge-m3', timeout=5)
    assert provider.model_id == 'ollama:http://localhost:11434:bge-m3'
    assert np.allclose(provider.embed('我养了一只猫'), [0.6, 0.8])


@pytest.mark.parametrize('vector', [[], [0, 0], [float('nan'), 1], [True, 1], ['1', 2], [[1, 2]]])
def test_invalid_vectors_are_rejected(vector):
    with pytest.raises(ValueError):
        normalized_vector(vector)


@pytest.mark.parametrize('payload', [{}, {'embeddings': []}, {'embeddings': [[1], [2]]}, {'embeddings': 'bad'}])
def test_invalid_service_output_is_not_silently_cached(monkeypatch, payload):
    monkeypatch.setattr('urllib.request.urlopen', lambda *args, **kwargs: io.BytesIO(json.dumps(payload).encode()))
    with pytest.raises(ValueError):
        OllamaEmbeddingProvider('http://localhost:11434', 'bge-m3').embed('猫')


@pytest.mark.parametrize('base,model', [('file:///tmp', 'x'), ('http://localhost', ''), ('http://user:pass@localhost', 'x')])
def test_adapter_rejects_invalid_endpoint_configuration(base, model):
    with pytest.raises(ValueError):
        OllamaEmbeddingProvider(base, model)
