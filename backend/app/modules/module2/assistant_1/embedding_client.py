from __future__ import annotations

import json
from urllib.parse import urlparse

import requests
from requests.exceptions import HTTPError, RequestException

from app.core.ai_api_logging import (
    log_ai_api_exception,
    log_ai_api_request,
    log_ai_api_response,
)

from .config import Assistant1Settings


class EmbeddingClient:
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
        return self._embed_many(texts)

    def embed_query(self, text: str) -> list[float]:
        vectors = self._embed_many([text])
        return vectors[0] if vectors else []

    def _embed_many(self, texts: list[str]) -> list[list[float]]:
        if not self.ready:
            raise RuntimeError("Embedding client is not configured")
        self._resolve_endpoint_style()
        return self._embed_openai(texts)

    def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        url = self._openai_embeddings_url()
        if self._looks_like_generation_endpoint(url):
            raise RuntimeError(
                "OpenAI-style embedding base points to a generation endpoint. "
                "Please set ASSISTANT1_EMBEDDING_BASE_URL to the provider root or embeddings endpoint."
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
                log_ai_api_request(
                    api_url=url,
                    request_body=payload,
                    model=self.model,
                    logger_name="app.modules.module2.assistant_1.embedding.ai_api",
                    config_prefix="MODULE2",
                )
                response = requests.post(url, headers=headers, json=payload, timeout=self.timeout_sec)
                log_ai_api_response(
                    response=response,
                    logger_name="app.modules.module2.assistant_1.embedding.ai_api",
                    config_prefix="MODULE2",
                )
                response.raise_for_status()
            except (HTTPError, RequestException) as exc:
                log_ai_api_exception(
                    exc=exc,
                    close_call=not (isinstance(exc, HTTPError) and exc.response is not None),
                    logger_name="app.modules.module2.assistant_1.embedding.ai_api",
                    config_prefix="MODULE2",
                )
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


    def _resolve_endpoint_style(self) -> str:
        if self.settings.embedding_endpoint_style != "openai":
            raise RuntimeError("Unsupported embedding endpoint style; use openai.")
        parsed = urlparse(self.base_url)
        if ":embedcontent" in parsed.path.lower() or ":generatecontent" in parsed.path.lower() or "/v1beta/models/" in parsed.path.lower():
            raise RuntimeError("Embedding base must point to an OpenAI-compatible provider root or embeddings endpoint.")
        return "openai"

    def _openai_embeddings_url(self) -> str:
        if self.base_url.endswith("/embeddings"):
            return self.base_url
        return f"{self.base_url}/embeddings"


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
            f"embedding request failed (mode={mode}, model={self.model}, "
            f"endpoint_style={self._resolve_endpoint_style()}, url={url}, "
            f"timeout_sec={self.timeout_sec}, status={status_code})."
        )
        if response_excerpt:
            message = f"{message} response={response_excerpt}"
        raise RuntimeError(message) from exc
