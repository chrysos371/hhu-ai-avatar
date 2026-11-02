"""Optional local embeddings, independent of the conversational model."""
from __future__ import annotations

import json
import math
import urllib.request
from typing import Protocol
from urllib.parse import urlsplit

import numpy as np


class EmbeddingProvider(Protocol):
    model_id: str

    def embed(self, text: str) -> list[float]:
        ...


def normalized_vector(values) -> np.ndarray:
    """Validate before conversion: bools/strings/NaNs must not become stored vectors."""
    if not isinstance(values, (list, tuple, np.ndarray)) or len(values) == 0:
        raise ValueError('Embedding must be a non-empty numeric vector')
    if any(isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, float, np.number))
           or not math.isfinite(float(value)) for value in values):
        raise ValueError('Embedding must contain finite numbers')
    vector = np.asarray(values, dtype=np.float64)
    norm = np.linalg.norm(vector)
    if vector.ndim != 1 or not math.isfinite(float(norm)) or norm <= 0:
        raise ValueError('Embedding has invalid shape or zero norm')
    return (vector / norm).astype(np.float32)


class OllamaEmbeddingProvider:
    def __init__(self, base_url: str = 'http://localhost:11434', model: str = 'bge-m3',
                 timeout: float = 10):
        base_url = base_url.rstrip('/')
        parsed = urlsplit(base_url)
        if (parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment or not model.strip()
                or not math.isfinite(timeout) or timeout <= 0):
            raise ValueError('Invalid embedding endpoint, model or timeout')
        self.base_url = base_url
        self.model = model.strip()
        self.timeout = timeout
        # Endpoint participates in identity: two servers can serve different weights under a tag.
        self.model_id = f'ollama:{base_url}:{self.model}'

    def embed(self, text: str) -> list[float]:
        payload = json.dumps({'model': self.model, 'input': text, 'truncate': False}).encode('utf-8')
        request = urllib.request.Request(self.base_url + '/api/embed', data=payload,
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            data = json.load(response)
        vectors = data.get('embeddings') if isinstance(data, dict) else None
        if not isinstance(vectors, list) or len(vectors) != 1:
            raise ValueError('Embedding service returned an invalid batch')
        return normalized_vector(vectors[0]).tolist()
