from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from .config import Assistant1Settings
from .embedding_client import EmbeddingClient
from .pgvector_store import Assistant1PgVectorStore


class Assistant1RetrievalPipeline:
    def __init__(self, settings: Assistant1Settings | None = None) -> None:
        self.settings = settings or Assistant1Settings.from_env()
        self.embedder = EmbeddingClient(self.settings)

    def stats(self, file_hash: str) -> dict[str, Any]:
        return asyncio.run(self._file_stats(file_hash=file_hash))

    def query(
        self,
        text: str,
        *,
        file_hash: str = "",
        unit_types: list[str] | None = None,
        top_k: int = 8,
    ) -> dict[str, Any]:
        if not self.embedder.ready:
            raise RuntimeError("embedding config is missing; cannot query vectors")
        query_vector = self.embedder.embed_query(text)
        matches = asyncio.run(
            self._query_store(
                query_vector=query_vector,
                file_hash=file_hash,
                unit_types=unit_types or [],
                top_k=top_k,
            )
        )
        return {
            "query": text,
            "file_hash": file_hash,
            "unit_types": unit_types or [],
            "top_k": top_k,
            "match_count": len(matches),
            "matches": [self._json_ready_match(match) for match in matches],
        }

    async def _file_stats(self, *, file_hash: str) -> dict[str, Any]:
        store = Assistant1PgVectorStore(self.settings)
        try:
            await store.init_schema()
            return await store.file_stats(file_hash)
        finally:
            await store.close()

    async def _query_store(
        self,
        *,
        query_vector: list[float],
        file_hash: str,
        unit_types: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        store = Assistant1PgVectorStore(self.settings)
        try:
            await store.init_schema()
            return await store.query_similar(
                query_vector,
                file_hash=file_hash,
                unit_types=unit_types,
                top_k=top_k,
            )
        finally:
            await store.close()

    @staticmethod
    def _json_ready_match(match: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, value in match.items():
            if isinstance(value, uuid.UUID):
                normalized[key] = str(value)
            elif key in {"source_block_ids", "unit_meta_json"} and isinstance(value, str):
                try:
                    normalized[key] = json.loads(value)
                except Exception:
                    normalized[key] = value
            else:
                normalized[key] = value
        return normalized
