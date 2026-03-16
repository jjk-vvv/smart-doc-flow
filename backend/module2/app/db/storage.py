from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

logger = logging.getLogger(__name__)


class ExtractionStorage:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._assistant_memory_history: List[Dict[str, Any]] = []
        self._assistant_sessions: Dict[str, Dict[str, Any]] = {}
        self._assistant_messages: List[Dict[str, Any]] = []
        self._assistant_tool_calls: List[Dict[str, Any]] = []
        self._assistant_actions: Dict[str, Dict[str, Any]] = {}
        self._assistant_action_executions: List[Dict[str, Any]] = []
        self._degraded_memory_mode = False
        self._last_connect_error = ""
        self._sync_commit_off = os.getenv("MODULE2_SYNC_COMMIT_OFF", "false").lower() in {"1", "true", "yes"}
        self._cache_unlogged = os.getenv("MODULE2_CACHE_UNLOGGED", "false").lower() in {"1", "true", "yes"}
        self._staging_unlogged = os.getenv("MODULE2_STAGING_UNLOGGED", "true").lower() in {"1", "true", "yes"}

    async def connect(self) -> None:
        min_pool = max(1, int(os.getenv("MODULE2_DB_POOL_MIN", "2")))
        max_pool = max(min_pool, int(os.getenv("MODULE2_DB_POOL_MAX", "20")))
        try:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=min_pool, max_size=max_pool)
            await self._init_schema()
            self._degraded_memory_mode = False
            self._last_connect_error = ""
        except Exception as exc:
            # Fallback for local/dev environments without PostgreSQL.
            self._pool = None
            self._degraded_memory_mode = True
            self._last_connect_error = f"{type(exc).__name__}: {exc}"
            logger.warning("module2 storage downgraded to memory mode: %s", self._last_connect_error)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    async def check_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        if not self._pool:
            payload = self._memory_cache.get(cache_key)
            return dict(payload) if isinstance(payload, dict) else None

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
            self._memory_cache[cache_key] = dict(payload)
            return

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

    async def save_assistant_interaction(self, payload: Dict[str, Any]) -> int:
        record = dict(payload)
        if not self._pool:
            self._assistant_memory_history.append(record)
            return 1

        sql = """
            INSERT INTO extraction_assistant_history (
                file_hash, file_name, user_instruction, summary_text, matched_json
            )
            VALUES ($1, $2, $3, $4, $5::jsonb)
        """
        file_hash = str(record.get("file_hash", "") or "")
        file_name = str(record.get("file_name", "") or "")
        user_instruction = str(record.get("user_instruction", "") or "")
        summary_text = str(record.get("summary_text", "") or "")
        matched_json = json.dumps(record.get("matched", []), ensure_ascii=False)
        async with self._pool.acquire() as conn:
            await conn.execute(sql, file_hash, file_name, user_instruction, summary_text, matched_json)
        return 1

    async def load_extraction_payload(self, file_hash: str) -> Optional[Dict[str, Any]]:
        key = str(file_hash or "").strip()
        if not key:
            return None

        if not self._pool:
            for payload in self._memory_cache.values():
                if str(payload.get("file_hash", "") or "").strip() == key:
                    return dict(payload)
            return None

        sql = """
            SELECT extraction_json
            FROM document_extractions
            WHERE extraction_json->>'file_hash' = $1
            ORDER BY updated_at DESC
            LIMIT 1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, key)
        if not row:
            return None
        payload = row["extraction_json"]
        if isinstance(payload, str):
            return json.loads(payload)
        return dict(payload) if isinstance(payload, dict) else None

    async def fetch_assistant_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        key = str(session_id or "").strip()
        if not key:
            return None

        if not self._pool:
            payload = self._assistant_sessions.get(key)
            return dict(payload) if isinstance(payload, dict) else None

        sql = """
            SELECT session_id, file_hash, file_name, summary_text, current_object_lock_json, metadata_json, created_at, updated_at
            FROM assist_session
            WHERE session_id = $1
            LIMIT 1
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, key)
        if not row:
            return None
        return {
            "session_id": str(row["session_id"] or ""),
            "file_hash": str(row["file_hash"] or ""),
            "file_name": str(row["file_name"] or ""),
            "summary_text": str(row["summary_text"] or ""),
            "current_object_lock_json": row["current_object_lock_json"] if isinstance(row["current_object_lock_json"], dict) else {},
            "metadata_json": row["metadata_json"] if isinstance(row["metadata_json"], dict) else {},
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
        }

    async def upsert_assistant_session(
        self,
        *,
        session_id: str,
        file_hash: str,
        file_name: str,
        summary_text: str,
        current_object_lock: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        record = {
            "session_id": str(session_id or "").strip(),
            "file_hash": str(file_hash or "").strip(),
            "file_name": str(file_name or "").strip(),
            "summary_text": str(summary_text or ""),
            "current_object_lock_json": dict(current_object_lock or {}),
            "metadata_json": dict(metadata or {}),
        }
        if not record["session_id"]:
            raise ValueError("session_id is required")

        if not self._pool:
            self._assistant_sessions[record["session_id"]] = {
                **record,
                "updated_at": "",
            }
            return

        sql = """
            INSERT INTO assist_session (
                session_id, file_hash, file_name, summary_text, current_object_lock_json, metadata_json
            )
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb)
            ON CONFLICT (session_id)
            DO UPDATE SET
                file_hash = EXCLUDED.file_hash,
                file_name = EXCLUDED.file_name,
                summary_text = EXCLUDED.summary_text,
                current_object_lock_json = EXCLUDED.current_object_lock_json,
                metadata_json = EXCLUDED.metadata_json,
                updated_at = NOW()
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                sql,
                record["session_id"],
                record["file_hash"],
                record["file_name"],
                record["summary_text"],
                json.dumps(record["current_object_lock_json"], ensure_ascii=False),
                json.dumps(record["metadata_json"], ensure_ascii=False),
            )

    async def list_assistant_messages(self, session_id: str, limit: int = 40) -> List[Dict[str, Any]]:
        key = str(session_id or "").strip()
        size = max(1, int(limit or 40))
        if not key:
            return []

        if not self._pool:
            items = [item for item in self._assistant_messages if str(item.get("session_id") or "") == key]
            return [dict(item) for item in items[-size:]]

        sql = """
            SELECT message_id, session_id, role, message_type, content_text, payload_json, created_at
            FROM assist_message
            WHERE session_id = $1
            ORDER BY created_at ASC
            LIMIT $2
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, key, size)
        out: List[Dict[str, Any]] = []
        for row in rows:
            payload_json = row["payload_json"] if isinstance(row["payload_json"], dict) else {}
            out.append(
                {
                    "message_id": str(row["message_id"] or ""),
                    "session_id": str(row["session_id"] or ""),
                    "role": str(row["role"] or ""),
                    "message_type": str(row["message_type"] or "assistant_text"),
                    "content": str(row["content_text"] or ""),
                    "payload": payload_json,
                    "created_at": str(row["created_at"] or ""),
                }
            )
        return out

    async def save_assistant_message(
        self,
        *,
        session_id: str,
        message_id: str,
        role: str,
        message_type: str,
        content: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        record = {
            "session_id": str(session_id or "").strip(),
            "message_id": str(message_id or "").strip(),
            "role": str(role or "").strip(),
            "message_type": str(message_type or "assistant_text").strip(),
            "content": str(content or ""),
            "payload": dict(payload or {}),
            "created_at": "",
        }
        if not record["session_id"] or not record["message_id"]:
            raise ValueError("session_id and message_id are required")

        if not self._pool:
            self._assistant_messages.append(record)
            return

        sql = """
            INSERT INTO assist_message (
                message_id, session_id, role, message_type, content_text, payload_json
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                sql,
                record["message_id"],
                record["session_id"],
                record["role"],
                record["message_type"],
                record["content"],
                json.dumps(record["payload"], ensure_ascii=False),
            )

    async def save_tool_invocation(
        self,
        *,
        session_id: str,
        message_id: str,
        tool_name: str,
        status: str,
        input_summary: Optional[Dict[str, Any]] = None,
        output_summary: Optional[Dict[str, Any]] = None,
        latency_ms: int = 0,
    ) -> None:
        record = {
            "session_id": str(session_id or "").strip(),
            "message_id": str(message_id or "").strip(),
            "tool_name": str(tool_name or "").strip(),
            "status": str(status or "").strip(),
            "input_summary": dict(input_summary or {}),
            "output_summary": dict(output_summary or {}),
            "latency_ms": max(0, int(latency_ms or 0)),
        }
        if not record["session_id"] or not record["tool_name"]:
            return

        if not self._pool:
            self._assistant_tool_calls.append(record)
            return

        sql = """
            INSERT INTO assist_tool_call (
                session_id, message_id, tool_name, status, input_summary_json, output_summary_json, latency_ms
            )
            VALUES ($1, $2, $3, $4, $5::jsonb, $6::jsonb, $7)
        """
        async with self._pool.acquire() as conn:
            await conn.execute(
                sql,
                record["session_id"],
                record["message_id"],
                record["tool_name"],
                record["status"],
                json.dumps(record["input_summary"], ensure_ascii=False),
                json.dumps(record["output_summary"], ensure_ascii=False),
                record["latency_ms"],
            )

    @staticmethod
    def _parse_command_rows(command_tag: str) -> int:
        text = str(command_tag or "").strip()
        if not text:
            return 0
        parts = text.split()
        if not parts:
            return 0
        try:
            return int(parts[-1])
        except Exception:
            return 0

    async def clear_runtime_cache(self) -> Dict[str, int]:
        memory_cache_count = len(self._memory_cache)
        assistant_mem_count = len(self._assistant_memory_history)
        assistant_session_count = len(self._assistant_sessions)
        assistant_message_count = len(self._assistant_messages)
        assistant_tool_call_count = len(self._assistant_tool_calls)
        self._memory_cache.clear()
        self._assistant_memory_history.clear()
        self._assistant_sessions.clear()
        self._assistant_messages.clear()
        self._assistant_tool_calls.clear()
        self._assistant_actions.clear()
        self._assistant_action_executions.clear()

        out: Dict[str, int] = {
            "memory_cache": memory_cache_count,
            "assistant_memory": assistant_mem_count,
            "assist_session_memory": assistant_session_count,
            "assist_message_memory": assistant_message_count,
            "assist_tool_call_memory": assistant_tool_call_count,
            "document_extractions": 0,
            "field_staging": 0,
            "table_staging": 0,
            "assistant_history": 0,
            "assist_session": 0,
            "assist_message": 0,
            "assist_tool_call": 0,
        }
        if not self._pool:
            return out

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                out["document_extractions"] = self._parse_command_rows(
                    await conn.execute("DELETE FROM document_extractions")
                )
                out["field_staging"] = self._parse_command_rows(
                    await conn.execute("DELETE FROM extraction_field_staging")
                )
                out["table_staging"] = self._parse_command_rows(
                    await conn.execute("DELETE FROM extraction_table_staging")
                )
                out["assistant_history"] = self._parse_command_rows(
                    await conn.execute("DELETE FROM extraction_assistant_history")
                )
                out["assist_tool_call"] = self._parse_command_rows(
                    await conn.execute("DELETE FROM assist_tool_call")
                )
                out["assist_message"] = self._parse_command_rows(
                    await conn.execute("DELETE FROM assist_message")
                )
                out["assist_session"] = self._parse_command_rows(
                    await conn.execute("DELETE FROM assist_session")
                )
        return out

    def diagnostics(self) -> Dict[str, Any]:
        return {
            "db_connected": bool(self._pool is not None),
            "degraded_memory_mode": bool(self._degraded_memory_mode),
            "last_connect_error": self._last_connect_error,
            "memory_cache_size": len(self._memory_cache),
            "assistant_memory_size": len(self._assistant_memory_history),
            "assist_session_memory_size": len(self._assistant_sessions),
            "assist_message_memory_size": len(self._assistant_messages),
            "assist_tool_call_memory_size": len(self._assistant_tool_calls),
        }

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

            CREATE {staging_mode} TABLE IF NOT EXISTS extraction_assistant_history (
                id BIGSERIAL PRIMARY KEY,
                file_hash TEXT,
                file_name TEXT,
                user_instruction TEXT NOT NULL,
                summary_text TEXT,
                matched_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_extraction_assistant_history_file_hash
                ON extraction_assistant_history (file_hash);

            CREATE {staging_mode} TABLE IF NOT EXISTS assist_session (
                session_id TEXT PRIMARY KEY,
                file_hash TEXT NOT NULL,
                file_name TEXT NOT NULL,
                summary_text TEXT,
                current_object_lock_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                metadata_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_assist_session_file_hash
                ON assist_session (file_hash);

            CREATE {staging_mode} TABLE IF NOT EXISTS assist_message (
                message_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                message_type TEXT NOT NULL,
                content_text TEXT,
                payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_assist_message_session_id
                ON assist_message (session_id, created_at);

            CREATE {staging_mode} TABLE IF NOT EXISTS assist_tool_call (
                id BIGSERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                message_id TEXT,
                tool_name TEXT NOT NULL,
                status TEXT NOT NULL,
                input_summary_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                output_summary_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                latency_ms INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );

            CREATE INDEX IF NOT EXISTS idx_assist_tool_call_session_id
                ON assist_tool_call (session_id, created_at);
        """

        async with self._pool.acquire() as conn:
            await conn.execute(ddl)
