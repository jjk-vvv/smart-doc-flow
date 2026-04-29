from __future__ import annotations

import json
from typing import Any

import asyncpg

from .config import Assistant1Settings
from .models import DocumentBundle, KnowledgeUnit


class Assistant1PgVectorStore:
    def __init__(self, settings: Assistant1Settings | None = None) -> None:
        self.settings = settings or Assistant1Settings.from_env()
        self.pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        if self.pool is not None:
            return
        if not self.settings.database_dsn:
            raise RuntimeError("ASSISTANT1_DATABASE_DSN or MODULE2_DATABASE_DSN is required for vector storage")
        self.pool = await asyncpg.create_pool(dsn=self.settings.database_dsn, min_size=1, max_size=5, timeout=20)

    async def close(self) -> None:
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def init_schema(self) -> None:
        await self.connect()
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            await conn.execute(self.schema_sql(dimensions=self.settings.embedding_dimensions))
            await self._ensure_embedding_dimension(conn, dimensions=self.settings.embedding_dimensions)

    async def upsert_document(self, bundle: DocumentBundle, raw_markdown: str, clean_markdown: str) -> str:
        await self.connect()
        assert self.pool is not None
        sql = """
        INSERT INTO doc_knowledge_document (
            id,
            file_hash,
            file_name,
            source_bundle_json,
            merged_raw_markdown,
            merged_clean_markdown,
            build_stats_json
        )
        VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7::jsonb)
        ON CONFLICT (file_hash)
        DO UPDATE SET
            file_name = EXCLUDED.file_name,
            source_bundle_json = EXCLUDED.source_bundle_json,
            merged_raw_markdown = EXCLUDED.merged_raw_markdown,
            merged_clean_markdown = EXCLUDED.merged_clean_markdown,
            build_stats_json = EXCLUDED.build_stats_json,
            updated_at = NOW()
        RETURNING id
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                sql,
                bundle.document_id,
                bundle.file_hash,
                bundle.file_name,
                json.dumps(bundle.source_bundle.to_dict(), ensure_ascii=False),
                raw_markdown,
                clean_markdown,
                json.dumps({"bundle_stats": bundle.stats, "warnings": bundle.build_warnings}, ensure_ascii=False),
            )
        return str(row["id"])

    async def replace_units(self, document_id: str, file_hash: str, units: list[KnowledgeUnit]) -> None:
        await self.connect()
        assert self.pool is not None
        sql = """
        INSERT INTO doc_knowledge_unit (
            id,
            document_id,
            file_hash,
            unit_type,
            title,
            content,
            page_start,
            page_end,
            source_block_ids,
            unit_meta_json,
            embedding
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::jsonb, $11::vector)
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM doc_knowledge_unit WHERE document_id = $1", document_id)
                for unit in units:
                    await conn.execute(
                        sql,
                        unit.unit_id,
                        document_id,
                        file_hash,
                        unit.unit_type,
                        unit.title,
                        unit.content,
                        unit.page_start,
                        unit.page_end,
                        json.dumps(unit.source_block_ids, ensure_ascii=False),
                        json.dumps(unit.metadata, ensure_ascii=False),
                        self._vector_literal(unit.embedding),
                    )

    async def record_ingest_run(
        self,
        *,
        file_hash: str,
        status: str,
        stage: str,
        warning_count: int,
        error_text: str = "",
        stats: dict[str, Any] | None = None,
    ) -> None:
        await self.connect()
        assert self.pool is not None
        sql = """
        INSERT INTO doc_ingest_run (id, file_hash, status, stage, warning_count, error_text, stats_json, finished_at)
        VALUES (gen_random_uuid(), $1, $2, $3, $4, $5, $6::jsonb, NOW())
        """
        async with self.pool.acquire() as conn:
            await conn.execute(
                sql,
                file_hash,
                status,
                stage,
                warning_count,
                error_text,
                json.dumps(stats or {}, ensure_ascii=False),
            )

    async def file_stats(self, file_hash: str) -> dict[str, int]:
        await self.connect()
        assert self.pool is not None
        async with self.pool.acquire() as conn:
            document_row = await conn.fetchrow(
                "SELECT COUNT(*) AS c FROM doc_knowledge_document WHERE file_hash = $1",
                file_hash,
            )
            unit_row = await conn.fetchrow(
                "SELECT COUNT(*) AS c FROM doc_knowledge_unit WHERE file_hash = $1",
                file_hash,
            )
        return {
            "document_count": int(document_row["c"] or 0) if document_row else 0,
            "unit_count": int(unit_row["c"] or 0) if unit_row else 0,
        }

    async def query_similar(
        self,
        embedding: list[float],
        *,
        file_hash: str = "",
        unit_types: list[str] | None = None,
        top_k: int = 8,
    ) -> list[dict[str, Any]]:
        await self.connect()
        assert self.pool is not None
        params: list[Any] = [self._vector_literal(embedding)]
        filters: list[str] = []
        if file_hash:
            params.append(file_hash)
            filters.append(f"file_hash = ${len(params)}")
        if unit_types:
            params.append(unit_types)
            filters.append(f"unit_type = ANY(${len(params)}::text[])")
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(max(1, top_k))
        operator = self._similarity_operator()
        sql = f"""
        SELECT
            id,
            document_id,
            file_hash,
            unit_type,
            title,
            content,
            page_start,
            page_end,
            source_block_ids,
            unit_meta_json,
            embedding {operator} $1::vector AS distance
        FROM doc_knowledge_unit
        {where}
        ORDER BY embedding {operator} $1::vector
        LIMIT ${len(params)}
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(row) for row in rows]

    def _similarity_operator(self) -> str:
        metric = self.settings.similarity_metric
        if metric == "l2":
            return "<->"
        if metric == "inner_product":
            return "<#>"
        return "<=>"

    @staticmethod
    def _vector_literal(values: list[float]) -> str:
        return "[" + ",".join(f"{float(value):.12f}" for value in values) + "]"

    async def _ensure_embedding_dimension(self, conn: asyncpg.Connection, *, dimensions: int) -> None:
        expected_type = f"vector({int(dimensions)})"
        row = await conn.fetchrow(
            """
            SELECT format_type(a.atttypid, a.atttypmod) AS type_name
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = current_schema()
              AND c.relname = 'doc_knowledge_unit'
              AND a.attname = 'embedding'
              AND NOT a.attisdropped
            """
        )
        current_type = str(row["type_name"] or "").strip() if row else ""
        if not current_type or current_type == expected_type:
            return

        # Embeddings are derived cache data. When the configured model dimension changes,
        # old vectors are mathematically incompatible, so reset units and let ingest rebuild.
        await conn.execute("DELETE FROM doc_knowledge_unit")
        await conn.execute(f"ALTER TABLE doc_knowledge_unit ALTER COLUMN embedding TYPE vector({int(dimensions)})")

    @staticmethod
    def schema_sql(*, dimensions: int) -> str:
        return f"""
        CREATE EXTENSION IF NOT EXISTS vector;
        CREATE EXTENSION IF NOT EXISTS pgcrypto;

        CREATE TABLE IF NOT EXISTS doc_knowledge_document (
            id uuid PRIMARY KEY,
            file_hash text NOT NULL UNIQUE,
            file_name text NOT NULL,
            source_bundle_json jsonb NOT NULL,
            merged_raw_markdown text,
            merged_clean_markdown text,
            build_stats_json jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT NOW(),
            updated_at timestamptz NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS doc_knowledge_unit (
            id text PRIMARY KEY,
            document_id uuid NOT NULL REFERENCES doc_knowledge_document(id) ON DELETE CASCADE,
            file_hash text NOT NULL,
            unit_type text NOT NULL,
            title text,
            content text NOT NULL,
            page_start integer,
            page_end integer,
            source_block_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
            unit_meta_json jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            embedding vector({dimensions}) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT NOW()
        );

        CREATE TABLE IF NOT EXISTS doc_ingest_run (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            file_hash text NOT NULL,
            status text NOT NULL,
            stage text NOT NULL,
            warning_count integer NOT NULL DEFAULT 0,
            error_text text,
            stats_json jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT NOW(),
            finished_at timestamptz
        );

        CREATE INDEX IF NOT EXISTS idx_doc_knowledge_unit_file_hash ON doc_knowledge_unit(file_hash);
        CREATE INDEX IF NOT EXISTS idx_doc_knowledge_unit_type ON doc_knowledge_unit(unit_type);
        """
