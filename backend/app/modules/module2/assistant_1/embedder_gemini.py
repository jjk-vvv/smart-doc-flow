from __future__ import annotations

import json
from urllib.parse import urlparse

import requests
from requests.exceptions import HTTPError, RequestException

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
        if self._looks_like_generation_endpoint(url):
            raise RuntimeError(
                "OpenAI-style embedding base points to a generation endpoint. "
                "Please set ASSISTANT1_EMBEDDING_BASE/ASSISTANT1_EMBEDDING_BASE_URL to the provider root or embeddings endpoint."
            )
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
            try:
                response = requests.post(url, headers=headers, json=payload, timeout=self.timeout_sec)
                response.raise_for_status()
            except (HTTPError, RequestException) as exc:
                self._raise_embedding_request_error(mode="openai", url=url, exc=exc)
            try:
                data = response.json()
            except ValueError as exc:
                raise RuntimeError(
                    f"OpenAI-style embedding response is not valid JSON "
                    f"(model={self.model}, url={url}, status={response.status_code}). "
                    f"response={self._response_excerpt(response)}"
                ) from exc
            embeddings = data.get("data", [])
            if not isinstance(embeddings, list) or len(embeddings) != len(batch):
                raise RuntimeError(
                    f"unexpected OpenAI-style embedding response (model={self.model}, url={url}): "
                    f"{json.dumps(data, ensure_ascii=False)[:500]}"
                )
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
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=self.timeout_sec)
            response.raise_for_status()
        except (HTTPError, RequestException) as exc:
            self._raise_embedding_request_error(mode="native", url=url, exc=exc)
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Native embedding response is not valid JSON "
                f"(model={self.model}, url={url}, status={response.status_code}). "
                f"response={self._response_excerpt(response)}"
            ) from exc
        vector = None
        if isinstance(data.get("embedding"), dict):
            vector = data["embedding"].get("values")
        elif isinstance(data.get("embeddings"), list) and data["embeddings"]:
            first = data["embeddings"][0]
            if isinstance(first, dict):
                vector = first.get("values")
        if not isinstance(vector, list):
            raise RuntimeError(
                f"unexpected native embedding response (model={self.model}, url={url}): "
                f"{json.dumps(data, ensure_ascii=False)[:500]}"
            )
        return [float(value) for value in vector]

    def _resolve_endpoint_style(self) -> str:
        style = self.settings.embedding_endpoint_style
        if style in {"native", "openai"}:
            return style
        parsed = urlparse(self.base_url)
        path = parsed.path.rstrip("/").lower()
        model_lower = self.model.lower()
        if ":embedcontent" in path or ":generatecontent" in path or "/v1beta/models/" in path:
            return "native"
        # Many Gemini-compatible providers publish a provider root ending with /v1.
        # If model naming already indicates Gemini, default to native endpoint style.
        if path.endswith("/v1") and "gemini" in model_lower:
            return "native"
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
        if ":generatecontent" in lower and "/v1beta/models/" in lower:
            provider_root = base[: lower.index("/v1beta/models/")]
            return f"{provider_root}/v1beta/models/{self.model}:embedContent"
        if lower.endswith("/v1beta") or "/v1beta/" in lower:
            return f"{base}/models/{self.model}:embedContent"
        # Accept provider bases written as ".../v1" (common in OpenAI-style configs)
        # and normalize them back to provider root for native Gemini endpoints.
        if lower.endswith("/v1"):
            provider_root = base[:-3]
            return f"{provider_root}/v1beta/models/{self.model}:embedContent"
        return f"{base}/v1beta/models/{self.model}:embedContent"

    @staticmethod
    def _looks_like_generation_endpoint(url: str) -> bool:
        lower = (url or "").lower()
        return (
            ":generatecontent" in lower
            or lower.endswith("/chat/completions")
            or lower.endswith("/responses")
        )

    @staticmethod
    def _response_excerpt(response: requests.Response | None, *, limit: int = 380) -> str:
        if response is None:
            return ""
        try:
            text = (response.text or "").strip()
        except Exception:
            return ""
        if not text:
            return ""
        compact = text.replace("\r", " ").replace("\n", " ")
        if len(compact) > limit:
            return compact[:limit] + "..."
        return compact

    def _raise_embedding_request_error(self, *, mode: str, url: str, exc: Exception) -> None:
        status_code = "n/a"
        response_excerpt = ""
        if isinstance(exc, HTTPError):
            response = exc.response
            if response is not None:
                status_code = str(response.status_code)
                response_excerpt = self._response_excerpt(response)
        message = (
            f"Gemini embedding request failed (mode={mode}, model={self.model}, "
            f"endpoint_style={self._resolve_endpoint_style()}, url={url}, "
            f"timeout_sec={self.timeout_sec}, status={status_code})."
        )
        if response_excerpt:
            message = f"{message} response={response_excerpt}"
        raise RuntimeError(message) from exc
