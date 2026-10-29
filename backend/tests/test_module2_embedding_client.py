from __future__ import annotations

import json as json_module
from types import SimpleNamespace

import pytest
import requests

from app.modules.module2.assistant_1 import embedding_client
from app.modules.module2.core.visual.vision_extractor import VisionExtractor


def _settings(**overrides):
    values = {
        "embedding_api_key": "test-key",
        "embedding_base_url": "https://provider.test/v1",
        "embedding_model": "text-embedding-3-small",
        "embedding_timeout_sec": 5,
        "embedding_batch_size": 2,
        "embedding_dimensions": 384,
        "embedding_endpoint_style": "openai",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_embedding_client_batches_and_orders_compatible_provider_results(monkeypatch) -> None:
    calls = []

    def post(url, *, headers, json: dict, timeout):
        calls.append((url, headers, json, timeout))
        response = requests.Response()
        response.status_code = 200
        response.url = url
        response._content = json_module.dumps({
            "data": [
                {"index": index, "embedding": [float(index)] * 384}
                for index in reversed(range(len(json["input"])))
            ],
        }).encode()
        return response

    monkeypatch.setattr(embedding_client.requests, "post", post)
    result = embedding_client.EmbeddingClient(_settings()).embed_documents(["a", "b", "c"])

    assert len(calls) == 2
    assert all(call[0] == "https://provider.test/v1/embeddings" for call in calls)
    assert calls[0][1]["Authorization"] == "Bearer test-key"
    assert calls[0][2]["model"] == "text-embedding-3-small"
    assert calls[0][2]["dimensions"] == 384
    assert [vector[0] for vector in result] == [0.0, 1.0, 0.0]
    assert all(len(vector) == 384 for vector in result)


def test_embedding_client_rejects_unsupported_style_without_network(monkeypatch) -> None:
    def unexpected_request(*args, **kwargs):
        pytest.fail("invalid configuration must not issue a network request")

    monkeypatch.setattr(embedding_client.requests, "post", unexpected_request)
    client = embedding_client.EmbeddingClient(_settings(embedding_endpoint_style="unsupported"))
    with pytest.raises(RuntimeError, match="Unsupported embedding endpoint style"):
        client.embed_query("query")


def test_vision_extractor_rejects_unsupported_endpoint_style() -> None:
    with pytest.raises(RuntimeError, match="Unsupported vision endpoint style"):
        VisionExtractor(api_key="test-key", endpoint_style="unsupported")
