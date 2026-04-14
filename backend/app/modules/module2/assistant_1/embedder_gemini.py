from __future__ import annotations

import json
from urllib.parse import urlparse

import requests

from .config import Assistant1Settings


class GeminiEmbeddingClient:
    def __init__(self, settings: Assistant1Settings | None = None) -> None:
        self.settings = settings or Assistant1Settings.from_env()
        self.api_key = self.settings.embedding_api_key
        self.base_url = self.settings.embedding_base_url.rstrip("/")
        self.model = self.settings.embedding_model
        self.timeout_sec = self.settings.embedding_timeout_sec
        self.batch_size = self.settings.embedding_batch_size
        self.dimensions = self.settings.embedding_dimensions

    @property
    def ready(self) -> bool:
        return bool(self.api_key and self.base_url and self.model)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._embed_many(texts, task_type=self.settings.embedding_document_task_type)

    def embed_query(self, text: str) -> list[float]:
        vectors = self._embed_many([text], task_type=self.settings.embedding_query_task_type)
        return vectors[0] if vectors else []

    def _embed_many(self, texts: list[str], task_type: str) -> list[list[float]]:
        if not self.ready:
            raise RuntimeError("Gemini embedding client is not configured")
        endpoint_style = self._resolve_endpoint_style()
        if endpoint_style == "openai":
            return self._embed_openai(texts)
        return [self._embed_native(text, task_type=task_type) for text in texts]

    def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        url = self._openai_embeddings_url()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            payload = {
                "model": self.model,
                "input": batch,
                "dimensions": self.dimensions,
            }
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout_sec)
            response.raise_for_status()
            data = response.json()
            embeddings = data.get("data", [])
            if not isinstance(embeddings, list) or len(embeddings) != len(batch):
                raise RuntimeError(f"unexpected OpenAI-style embedding response: {json.dumps(data, ensure_ascii=False)[:500]}")
            ordered = sorted(embeddings, key=lambda item: int(item.get("index", 0) or 0))
            for item in ordered:
                vector = item.get("embedding", [])
                if not isinstance(vector, list):
                    raise RuntimeError("embedding vector is missing from OpenAI-style response")
                vectors.append([float(value) for value in vector])
        return vectors

    def _embed_native(self, text: str, task_type: str) -> list[float]:
        url = self._native_embeddings_url()
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        payload = {
            "model": f"models/{self.model}" if not self.model.startswith("models/") else self.model,
            "content": {"parts": [{"text": text}]},
            "taskType": task_type,
            "outputDimensionality": self.dimensions,
        }
        response = requests.post(url, headers=headers, json=payload, timeout=self.timeout_sec)
        response.raise_for_status()
        data = response.json()
        vector = None
        if isinstance(data.get("embedding"), dict):
            vector = data["embedding"].get("values")
        elif isinstance(data.get("embeddings"), list) and data["embeddings"]:
            first = data["embeddings"][0]
            if isinstance(first, dict):
                vector = first.get("values")
        if not isinstance(vector, list):
            raise RuntimeError(f"unexpected native embedding response: {json.dumps(data, ensure_ascii=False)[:500]}")
        return [float(value) for value in vector]

    def _resolve_endpoint_style(self) -> str:
        style = self.settings.embedding_endpoint_style
        if style in {"native", "openai"}:
            return style
        parsed = urlparse(self.base_url)
        path = parsed.path.rstrip("/").lower()
        if path.endswith("/v1") or path.endswith("/embeddings") or "/openai" in path:
            return "openai"
        return "native"

    def _openai_embeddings_url(self) -> str:
        if self.base_url.endswith("/embeddings"):
            return self.base_url
        return f"{self.base_url}/embeddings"

    def _native_embeddings_url(self) -> str:
        if ":embedcontent" in self.base_url.lower():
            return self.base_url
        base = self.base_url
        lower = base.lower()
        if lower.endswith("/v1beta") or "/v1beta/" in lower:
            return f"{base}/models/{self.model}:embedContent"
        # Accept provider bases written as ".../v1" (common in OpenAI-style configs)
        # and normalize them back to provider root for native Gemini endpoints.
        if lower.endswith("/v1"):
            provider_root = base[:-3]
            return f"{provider_root}/v1beta/models/{self.model}:embedContent"
        return f"{base}/v1beta/models/{self.model}:embedContent"
