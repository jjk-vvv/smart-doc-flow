from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import asyncpg


class ExtractionStorage:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None
        self._sync_commit_off = os.getenv("MODULE2_SYNC_COMMIT_OFF", "false").lower() in {"1", "true", "yes"}
        self._cache_unlogged = os.getenv("MODULE2_CACHE_UNLOGGED", "false").lower() in {"1", "true", "yes"}
        self._staging_unlogged = os.getenv("MODULE2_STAGING_UNLOGGED", "true").lower() in {"1", "true", "yes"}

    async def connect(self) -> None:
        min_pool = max(1, int(os.getenv("MODULE2_DB_POOL_MIN", "2")))
        max_pool = max(min_pool, int(os.getenv("MODULE2_DB_POOL_MAX", "20")))
        self._pool = await asyncpg.create_pool(self._dsn, min_size=min_pool, max_size=max_pool)
        await self._init_schema()

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def check_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        if not self._pool:
            raise RuntimeError("DB pool is not initialized")

        query = "SELECT extraction_json FROM document_extractions WHERE file_hash = $1"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(query, cache_key)
            if not row:
                return None
            payload = row["extraction_json"]
            if isinstance(payload, str):
                return json.loads(payload)
            return payload

    async def save_extraction_result(self, cache_key: str, payload: Dict[str, Any]) -> None:
        if not self._pool:
            raise RuntimeError("DB pool is not initialized")

        final_upsert = """
            INSERT INTO document_extractions (file_hash, extraction_json)
            VALUES ($1, $2::jsonb)
            ON CONFLICT (file_hash)
            DO UPDATE SET extraction_json = EXCLUDED.extraction_json,
                          updated_at = NOW()
        """

        field_insert_cols = [
            "cache_key",
            "file_hash",
            "schema_hash",
            "file_name",
            "field_name",
            "field_value",
            "confidence",
            "source_ref_id",
            "bbox_json",
        ]
        field_records = self._to_field_staging_records(cache_key=cache_key, payload=payload)
        table_insert_cols = [
            "cache_key",
            "file_hash",
            "schema_hash",
            "file_name",
            "table_id",
            "source",
            "page_no",
            "row_idx",
            "col_idx",
            "cell_text",
            "cell_ref_id",
            "bbox_json",
        ]
        table_records = self._to_table_staging_records(cache_key=cache_key, payload=payload)
        serialized = json.dumps(payload, ensure_ascii=False)

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                if self._sync_commit_off:
                    await conn.execute("SET LOCAL synchronous_commit TO OFF")

                await conn.execute("DELETE FROM extraction_field_staging WHERE cache_key = $1", cache_key)
                await conn.execute("DELETE FROM extraction_table_staging WHERE cache_key = $1", cache_key)

                if field_records:
                    await self._copy_with_fallback(
                        conn=conn,
                        table_name="extraction_field_staging",
                        records=field_records,
                        columns=field_insert_cols,
                    )

                if table_records:
                    await self._copy_with_fallback(
                        conn=conn,
                        table_name="extraction_table_staging",
                        records=table_records,
                        columns=table_insert_cols,
                    )

                await conn.execute(final_upsert, cache_key, serialized)

    @staticmethod
    def _to_field_staging_records(cache_key: str, payload: Dict[str, Any]) -> List[Tuple[Any, ...]]:
        result = payload.get("result", {})
        file_hash = payload.get("file_hash", "")
        schema_hash = payload.get("schema_hash", "")
        file_name = payload.get("file_name", "")

        rows: List[Tuple[Any, ...]] = []
        for field_name, entity in result.items():
            value = entity.get("value")
            confidence = float(entity.get("confidence") or 0.0)
            source_ref_id = entity.get("source_ref_id")
            bbox = entity.get("bbox") if isinstance(entity.get("bbox"), list) else []

            rows.append(
                (
                    cache_key,
                    file_hash,
                    schema_hash,
                    file_name,
                    str(field_name),
                    None if value is None else str(value),
                    confidence,
                    None if source_ref_id is None else str(source_ref_id),
                    json.dumps(bbox, ensure_ascii=False),
                )
            )
        return rows

    @staticmethod
    def _to_table_staging_records(cache_key: str, payload: Dict[str, Any]) -> List[Tuple[Any, ...]]:
        file_hash = payload.get("file_hash", "")
        schema_hash = payload.get("schema_hash", "")
        file_name = payload.get("file_name", "")
        tables = payload.get("tables", [])
        max_cells = max(200, int(os.getenv("MODULE2_TABLE_STAGE_MAX_CELLS", "5000")))

        rows: List[Tuple[Any, ...]] = []
        for table in tables:
            table_id = str(table.get("table_id", ""))
            source = str(table.get("source", ""))
            page_no = int(table.get("page", 1) or 1)

            for row in table.get("rows", []):
                row_idx = int(row.get("row_index", 0) or 0)
                for cell in row.get("cells", []):
                    text = str(cell.get("text", "")).strip()
                    if not text:
                        continue
                    col_idx = int(cell.get("col_index", 0) or 0)
                    ref_id = cell.get("ref_id")
                    bbox = cell.get("bbox") if isinstance(cell.get("bbox"), list) else []

                    rows.append(
                        (
                            cache_key,
                            file_hash,
                            schema_hash,
                            file_name,
                            table_id,
                            source,
                            page_no,
                            row_idx,
                            col_idx,
                            text,
                            None if ref_id is None else str(ref_id),
                            json.dumps(bbox, ensure_ascii=False),
                        )
                    )
                    if len(rows) >= max_cells:
                        return rows
        return rows

    @staticmethod
    async def _copy_with_fallback(
        conn: asyncpg.Connection,
        table_name: str,
        records: List[Tuple[Any, ...]],
        columns: List[str],
    ) -> None:
        fail_on_partial = os.getenv("MODULE2_FAIL_ON_STAGING_PARTIAL", "true").lower() in {"1", "true", "yes"}
        try:
            await conn.copy_records_to_table(
                table_name,
                records=records,
                columns=columns,
            )
            return
        except Exception:
            # COPY is all-or-nothing; fallback keeps valid rows moving.
            col_names = ", ".join(columns)
            placeholders = ", ".join(f"${idx}" for idx in range(1, len(columns) + 1))
            insert_sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"
            inserted = 0
            failed = 0
            for row in records:
                try:
                    await conn.execute(insert_sql, *row)
                    inserted += 1
                except Exception:
                    failed += 1
                    continue
            if inserted == 0:
                raise
            if failed > 0 and fail_on_partial:
                raise RuntimeError(
                    f"Partial insert into {table_name}: inserted={inserted}, failed={failed}, total={len(records)}"
                )

    async def _init_schema(self) -> None:
        if not self._pool:
            raise RuntimeError("DB pool is not initialized")

        cache_mode = "UNLOGGED" if self._cache_unlogged else ""
        staging_mode = "UNLOGGED" if self._staging_unlogged else ""

        ddl = f"""
            CREATE {cache_mode} TABLE IF NOT EXISTS document_extractions (
                file_hash TEXT PRIMARY KEY,
                extraction_json JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_document_extractions_updated_at
                ON document_extractions (updated_at DESC);

            CREATE {staging_mode} TABLE IF NOT EXISTS extraction_field_staging (
                cache_key TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                schema_hash TEXT,
                file_name TEXT,
                field_name TEXT NOT NULL,
                field_value TEXT,
                confidence DOUBLE PRECISION NOT NULL,
                source_ref_id TEXT,
                bbox_json TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_extraction_field_staging_cache_key
                ON extraction_field_staging (cache_key);

            CREATE {staging_mode} TABLE IF NOT EXISTS extraction_table_staging (
                cache_key TEXT NOT NULL,
                file_hash TEXT NOT NULL,
                schema_hash TEXT,
                file_name TEXT,
                table_id TEXT NOT NULL,
                source TEXT,
                page_no INTEGER,
                row_idx INTEGER,
                col_idx INTEGER,
                cell_text TEXT NOT NULL,
                cell_ref_id TEXT,
                bbox_json TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_extraction_table_staging_cache_key
                ON extraction_table_staging (cache_key);

            CREATE INDEX IF NOT EXISTS idx_extraction_table_staging_table_id
                ON extraction_table_staging (table_id);
        """

        async with self._pool.acquire() as conn:
            await conn.execute(ddl)
