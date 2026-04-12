from __future__ import annotations

import importlib
import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, unquote, urlsplit

logger = logging.getLogger(__name__)
_LOCAL_DB_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_object(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            loaded = json.loads(text)
        except Exception:
            return {}
        return dict(loaded) if isinstance(loaded, dict) else {}
    return {}


class ExtractionStorage:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Optional[Any] = None
        self._asyncpg_module: Optional[Any] = None
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._assistant_memory_history: List[Dict[str, Any]] = []
        self._assistant_sessions: Dict[str, Dict[str, Any]] = {}
        self._assistant_messages: List[Dict[str, Any]] = []
        self._assistant_tool_calls: List[Dict[str, Any]] = []
        self._assistant_actions: Dict[str, Dict[str, Any]] = {}
        self._assistant_action_executions: List[Dict[str, Any]] = []
        self._graph_sync_outbox: Dict[str, Dict[str, Any]] = {}
        self._graph_sync_outbox_by_key: Dict[Tuple[str, str, str, str], str] = {}
        self._degraded_memory_mode = False
        self._last_connect_error = ""
        self._sync_commit_off = os.getenv("MODULE2_SYNC_COMMIT_OFF", "false").lower() in {"1", "true", "yes"}
        self._cache_unlogged = os.getenv("MODULE2_CACHE_UNLOGGED", "false").lower() in {"1", "true", "yes"}
        self._staging_unlogged = os.getenv("MODULE2_STAGING_UNLOGGED", "true").lower() in {"1", "true", "yes"}

    async def _load_asyncpg(self) -> Optional[Any]:
        if self._asyncpg_module is not None:
            return self._asyncpg_module

        import_timeout = max(1.0, float(os.getenv("MODULE2_DB_IMPORT_TIMEOUT_SEC", "8")))
        try:
            probe = subprocess.run(
                [sys.executable, "-c", "import asyncpg; print('asyncpg_import_probe_ok')"],
                capture_output=True,
                text=True,
                timeout=import_timeout,
                check=False,
            )
            if probe.returncode != 0:
                stderr = str(probe.stderr or "").strip()
                raise RuntimeError(stderr or f"probe_exit_{probe.returncode}")
            self._asyncpg_module = importlib.import_module("asyncpg")
        except Exception as exc:
            self._last_connect_error = f"asyncpg_import_failed:{type(exc).__name__}: {exc}"
            logger.warning("module2 storage cannot import asyncpg within %.1fs: %s", import_timeout, exc)
            self._asyncpg_module = None
        return self._asyncpg_module

    async def connect(self) -> None:
        asyncpg_module = await self._load_asyncpg()
        if asyncpg_module is None:
            self._pool = None
            self._degraded_memory_mode = True
            if not self._last_connect_error:
                self._last_connect_error = "asyncpg_import_failed"
            logger.warning("module2 storage downgraded to memory mode: %s", self._last_connect_error)
            return

        configured_min_pool = max(1, int(os.getenv("MODULE2_DB_POOL_MIN", "1")))
        max_pool = max(configured_min_pool, int(os.getenv("MODULE2_DB_POOL_MAX", "20")))
        min_pool = 1 if self._dsn_targets_localhost() else configured_min_pool
        connect_timeout = max(2.0, float(os.getenv("MODULE2_DB_CONNECT_TIMEOUT_SEC", "5")))
        errors: List[str] = []

        for label, pool_kwargs in self._build_pool_attempts():
            try:
                self._pool = await asyncpg_module.create_pool(
                    min_size=min_pool,
                    max_size=max_pool,
                    timeout=connect_timeout,
                    command_timeout=connect_timeout,
                    **pool_kwargs,
                )
                await self._init_schema()
                self._degraded_memory_mode = False
                self._last_connect_error = ""
                logger.info("module2 storage connected with strategy=%s", label)
                return
            except Exception as exc:
                errors.append(f"{label}: {type(exc).__name__}: {exc}")
                if self._pool:
                    await self._pool.close()
                    self._pool = None

        # Fallback for local/dev environments without PostgreSQL.
        self._pool = None
        self._degraded_memory_mode = True
        self._last_connect_error = " | ".join(errors[:4])
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

    async def find_recent_document_caches(self, file_hash: str, *, limit: int = 8) -> List[Dict[str, Any]]:
        normalized_file_hash = str(file_hash or "").strip()
        safe_limit = max(1, min(int(limit or 8), 24))
        if not normalized_file_hash:
            return []

        if not self._pool:
            matched: List[Dict[str, Any]] = []
            for payload in self._memory_cache.values():
                if not isinstance(payload, dict):
                    continue
                if str(payload.get("file_hash", "") or "").strip() != normalized_file_hash:
                    continue
                matched.append(dict(payload))
            matched.sort(key=lambda p: str(p.get("updated_at") or ""), reverse=True)
            return matched[:safe_limit]

        sql = """
            SELECT extraction_json
            FROM document_extractions
            WHERE extraction_json->>'file_hash' = $1
            ORDER BY updated_at DESC
            LIMIT $2
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, normalized_file_hash, safe_limit)

        out: List[Dict[str, Any]] = []
        for row in rows:
            payload = row["extraction_json"]
            if isinstance(payload, str):
                try:
                    loaded = json.loads(payload)
                except Exception:
                    continue
                if isinstance(loaded, dict):
                    out.append(loaded)
                continue
            if isinstance(payload, dict):
                out.append(dict(payload))
        return out

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
            "current_object_lock_json": _json_object(row["current_object_lock_json"]),
            "metadata_json": _json_object(row["metadata_json"]),
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
            payload_json = _json_object(row["payload_json"])
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
            for index, item in enumerate(self._assistant_messages):
                if str(item.get("message_id") or "") != record["message_id"]:
                    continue
                created_at = str(item.get("created_at") or "")
                self._assistant_messages[index] = {
                    **record,
                    "created_at": created_at,
                }
                return
            self._assistant_messages.append(record)
            return

        sql = """
            INSERT INTO assist_message (
                message_id, session_id, role, message_type, content_text, payload_json
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            ON CONFLICT (message_id)
            DO UPDATE SET
                role = EXCLUDED.role,
                message_type = EXCLUDED.message_type,
                content_text = EXCLUDED.content_text,
                payload_json = EXCLUDED.payload_json
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

    async def upsert_graph_sync_outbox(
        self,
        *,
        tenant_id: str,
        source: str,
        source_batch_key: str,
        endpoint: str,
        payload: Dict[str, Any],
        sync_kind: str,
        file_hash: Optional[str] = None,
        max_attempts: int = 3,
    ) -> Dict[str, Any]:
        tenant_value = str(tenant_id or "").strip()
        source_value = str(source or "").strip()
        batch_key_value = str(source_batch_key or "").strip()
        endpoint_value = str(endpoint or "").strip()
        sync_kind_value = str(sync_kind or "upload_file").strip() or "upload_file"
        file_hash_value = str(file_hash or "").strip() or None
        payload_value = dict(payload or {})
        capped_attempts = max(1, min(int(max_attempts or 3), 8))

        if not tenant_value or not source_value or not batch_key_value or not endpoint_value:
            raise ValueError("tenant_id, source, source_batch_key and endpoint are required")

        if not self._pool:
            key = (tenant_value, source_value, batch_key_value, endpoint_value)
            existing_id = self._graph_sync_outbox_by_key.get(key)
            now = _utcnow()
            if existing_id and existing_id in self._graph_sync_outbox:
                row = self._graph_sync_outbox[existing_id]
                if str(row.get("status") or "") != "delivered":
                    row.update(
                        {
                            "sync_kind": sync_kind_value,
                            "file_hash": file_hash_value,
                            "payload_json": payload_value,
                            "max_attempts": capped_attempts,
                            "status": "queued",
                            "last_error": None,
                            "next_attempt_at": now,
                            "updated_at": now,
                        }
                    )
                return dict(row)

            outbox_id = f"graphsync_{uuid.uuid4().hex[:24]}"
            row = {
                "outbox_id": outbox_id,
                "tenant_id": tenant_value,
                "source": source_value,
                "source_batch_key": batch_key_value,
                "endpoint": endpoint_value,
                "sync_kind": sync_kind_value,
                "file_hash": file_hash_value,
                "payload_json": payload_value,
                "status": "queued",
                "attempt_count": 0,
                "max_attempts": capped_attempts,
                "last_error": None,
                "last_response_json": {},
                "next_attempt_at": now,
                "last_attempt_at": None,
                "delivered_at": None,
                "created_at": now,
                "updated_at": now,
            }
            self._graph_sync_outbox[outbox_id] = row
            self._graph_sync_outbox_by_key[key] = outbox_id
            return dict(row)

        outbox_id = f"graphsync_{uuid.uuid4().hex[:24]}"
        sql = """
            INSERT INTO graph_sync_outbox (
                outbox_id,
                tenant_id,
                source,
                source_batch_key,
                endpoint,
                sync_kind,
                file_hash,
                payload_json,
                status,
                attempt_count,
                max_attempts,
                next_attempt_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, 'queued', 0, $9, NOW())
            ON CONFLICT (tenant_id, source, source_batch_key, endpoint)
            DO UPDATE SET
                sync_kind = EXCLUDED.sync_kind,
                file_hash = COALESCE(EXCLUDED.file_hash, graph_sync_outbox.file_hash),
                payload_json = EXCLUDED.payload_json,
                max_attempts = EXCLUDED.max_attempts,
                status = CASE
                    WHEN graph_sync_outbox.status = 'delivered' THEN graph_sync_outbox.status
                    ELSE 'queued'
                END,
                last_error = NULL,
                next_attempt_at = CASE
                    WHEN graph_sync_outbox.status = 'delivered' THEN graph_sync_outbox.next_attempt_at
                    ELSE NOW()
                END,
                updated_at = NOW()
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                sql,
                outbox_id,
                tenant_value,
                source_value,
                batch_key_value,
                endpoint_value,
                sync_kind_value,
                file_hash_value,
                json.dumps(payload_value, ensure_ascii=False),
                capped_attempts,
            )
        return dict(row) if row else {}

    async def get_graph_sync_outbox(self, outbox_id: str) -> Optional[Dict[str, Any]]:
        key = str(outbox_id or "").strip()
        if not key:
            return None

        if not self._pool:
            row = self._graph_sync_outbox.get(key)
            return dict(row) if row else None

        sql = "SELECT * FROM graph_sync_outbox WHERE outbox_id = $1"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, key)
        return dict(row) if row else None

    async def list_graph_sync_outbox(
        self,
        *,
        tenant_id: Optional[str] = None,
        source: Optional[str] = None,
        source_batch_key: Optional[str] = None,
        endpoint: Optional[str] = None,
        statuses: Optional[List[str]] = None,
        limit: int = 100,
        due_before: Optional[datetime] = None,
        include_future: bool = False,
    ) -> List[Dict[str, Any]]:
        tenant_value = str(tenant_id or "").strip()
        source_value = str(source or "").strip()
        batch_key_value = str(source_batch_key or "").strip()
        endpoint_value = str(endpoint or "").strip()
        status_values = [str(item).strip() for item in (statuses or []) if str(item).strip()]
        capped_limit = max(1, min(int(limit or 100), 500))
        due_at = due_before or _utcnow()

        if not self._pool:
            rows = [dict(item) for item in self._graph_sync_outbox.values()]
            if tenant_value:
                rows = [item for item in rows if str(item.get("tenant_id") or "").strip() == tenant_value]
            if source_value:
                rows = [item for item in rows if str(item.get("source") or "").strip() == source_value]
            if batch_key_value:
                rows = [item for item in rows if str(item.get("source_batch_key") or "").strip() == batch_key_value]
            if endpoint_value:
                rows = [item for item in rows if str(item.get("endpoint") or "").strip() == endpoint_value]
            if status_values:
                allowed = set(status_values)
                rows = [item for item in rows if str(item.get("status") or "") in allowed]
            if not include_future:
                rows = [
                    item for item in rows
                    if not item.get("next_attempt_at") or item.get("next_attempt_at") <= due_at
                ]
            rows.sort(
                key=lambda item: (
                    item.get("next_attempt_at") or due_at,
                    item.get("created_at") or due_at,
                )
            )
            return rows[:capped_limit]

        where_parts: List[str] = []
        params: List[Any] = []
        next_idx = 1
        if tenant_value:
            where_parts.append(f"tenant_id = ${next_idx}")
            params.append(tenant_value)
            next_idx += 1
        if source_value:
            where_parts.append(f"source = ${next_idx}")
            params.append(source_value)
            next_idx += 1
        if batch_key_value:
            where_parts.append(f"source_batch_key = ${next_idx}")
            params.append(batch_key_value)
            next_idx += 1
        if endpoint_value:
            where_parts.append(f"endpoint = ${next_idx}")
            params.append(endpoint_value)
            next_idx += 1
        if status_values:
            where_parts.append(f"status = ANY(${next_idx}::text[])")
            params.append(status_values)
            next_idx += 1
        if not include_future:
            where_parts.append(f"(next_attempt_at IS NULL OR next_attempt_at <= ${next_idx})")
            params.append(due_at)
            next_idx += 1
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        sql = f"""
            SELECT *
            FROM graph_sync_outbox
            {where_sql}
            ORDER BY COALESCE(next_attempt_at, created_at) ASC, created_at ASC
            LIMIT ${next_idx}
        """
        params.append(capped_limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [dict(row) for row in rows]

    async def claim_graph_sync_outbox(self, outbox_id: str) -> Optional[Dict[str, Any]]:
        key = str(outbox_id or "").strip()
        if not key:
            return None

        if not self._pool:
            row = self._graph_sync_outbox.get(key)
            if not row or str(row.get("status") or "") == "delivered":
                return dict(row) if row else None
            now = _utcnow()
            row["status"] = "delivering"
            row["attempt_count"] = int(row.get("attempt_count") or 0) + 1
            row["last_attempt_at"] = now
            row["updated_at"] = now
            return dict(row)

        sql = """
            UPDATE graph_sync_outbox
            SET
                status = 'delivering',
                attempt_count = attempt_count + 1,
                last_attempt_at = NOW(),
                updated_at = NOW()
            WHERE outbox_id = $1
              AND status <> 'delivered'
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, key)
        return dict(row) if row else None

    async def mark_graph_sync_outbox_delivered(
        self,
        *,
        outbox_id: str,
        response_payload: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        key = str(outbox_id or "").strip()
        payload_value = dict(response_payload or {})
        if not key:
            return None

        if not self._pool:
            row = self._graph_sync_outbox.get(key)
            if not row:
                return None
            now = _utcnow()
            row.update(
                {
                    "status": "delivered",
                    "last_error": None,
                    "last_response_json": payload_value,
                    "delivered_at": now,
                    "updated_at": now,
                }
            )
            return dict(row)

        sql = """
            UPDATE graph_sync_outbox
            SET
                status = 'delivered',
                last_error = NULL,
                last_response_json = $2::jsonb,
                delivered_at = NOW(),
                updated_at = NOW()
            WHERE outbox_id = $1
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, key, json.dumps(payload_value, ensure_ascii=False))
        return dict(row) if row else None

    async def requeue_graph_sync_outbox(
        self,
        *,
        outbox_id: str,
        error_message: str,
        next_attempt_at: datetime,
    ) -> Optional[Dict[str, Any]]:
        key = str(outbox_id or "").strip()
        message = str(error_message or "").strip()[:1000]
        if not key:
            return None

        if not self._pool:
            row = self._graph_sync_outbox.get(key)
            if not row:
                return None
            row.update(
                {
                    "status": "queued",
                    "last_error": message,
                    "next_attempt_at": next_attempt_at,
                    "updated_at": _utcnow(),
                }
            )
            return dict(row)

        sql = """
            UPDATE graph_sync_outbox
            SET
                status = 'queued',
                last_error = $2,
                next_attempt_at = $3,
                updated_at = NOW()
            WHERE outbox_id = $1
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, key, message, next_attempt_at)
        return dict(row) if row else None

    async def mark_graph_sync_outbox_failed(
        self,
        *,
        outbox_id: str,
        error_message: str,
    ) -> Optional[Dict[str, Any]]:
        key = str(outbox_id or "").strip()
        message = str(error_message or "").strip()[:1000]
        if not key:
            return None

        if not self._pool:
            row = self._graph_sync_outbox.get(key)
            if not row:
                return None
            row.update(
                {
                    "status": "failed",
                    "last_error": message,
                    "updated_at": _utcnow(),
                }
            )
            return dict(row)

        sql = """
            UPDATE graph_sync_outbox
            SET
                status = 'failed',
                last_error = $2,
                updated_at = NOW()
            WHERE outbox_id = $1
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, key, message)
        return dict(row) if row else None

    async def recover_pending_graph_sync_outbox(self, limit: int = 200) -> List[Dict[str, Any]]:
        capped_limit = max(1, min(int(limit or 200), 500))
        if not self._pool:
            recovered: List[Dict[str, Any]] = []
            for row in self._graph_sync_outbox.values():
                if str(row.get("status") or "") == "delivering":
                    row["status"] = "queued"
                    row["updated_at"] = _utcnow()
                if str(row.get("status") or "") == "queued":
                    recovered.append(dict(row))
            recovered.sort(
                key=lambda item: (
                    item.get("next_attempt_at") or _utcnow(),
                    item.get("created_at") or _utcnow(),
                )
            )
            return recovered[:capped_limit]

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE graph_sync_outbox
                    SET status = 'queued', updated_at = NOW()
                    WHERE status = 'delivering'
                    """
                )
                rows = await conn.fetch(
                    """
                    SELECT *
                    FROM graph_sync_outbox
                    WHERE status = 'queued'
                    ORDER BY COALESCE(next_attempt_at, created_at) ASC, created_at ASC
                    LIMIT $1
                    """,
                    capped_limit,
                )
        return [dict(row) for row in rows]

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
        graph_sync_outbox_count = len(self._graph_sync_outbox)
        self._graph_sync_outbox.clear()
        self._graph_sync_outbox_by_key.clear()

        out: Dict[str, int] = {
            "memory_cache": memory_cache_count,
            "assistant_memory": assistant_mem_count,
            "assist_session_memory": assistant_session_count,
            "assist_message_memory": assistant_message_count,
            "assist_tool_call_memory": assistant_tool_call_count,
            "graph_sync_outbox_memory": graph_sync_outbox_count,
            "document_extractions": 0,
            "field_staging": 0,
            "table_staging": 0,
            "assistant_history": 0,
            "assist_session": 0,
            "assist_message": 0,
            "assist_tool_call": 0,
            "graph_sync_outbox": 0,
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
                out["graph_sync_outbox"] = self._parse_command_rows(
                    await conn.execute("DELETE FROM graph_sync_outbox")
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
            "graph_sync_outbox_memory_size": len(self._graph_sync_outbox),
        }

    def _dsn_targets_localhost(self) -> bool:
        parsed = urlsplit(self._dsn)
        return str(parsed.hostname or "").strip().lower() in _LOCAL_DB_HOSTS

    def _build_pool_attempts(self) -> List[Tuple[str, Dict[str, Any]]]:
        parsed = urlsplit(self._dsn)
        scheme = str(parsed.scheme or "").lower()
        if scheme not in {"postgres", "postgresql"}:
            return [("dsn", {"dsn": self._dsn})]

        base: Dict[str, Any] = {}
        if parsed.username is not None:
            base["user"] = unquote(parsed.username)
        if parsed.password is not None:
            base["password"] = unquote(parsed.password)
        if parsed.hostname:
            base["host"] = parsed.hostname
        if parsed.port is not None:
            base["port"] = parsed.port
        database = str(parsed.path or "").lstrip("/")
        if database:
            base["database"] = unquote(database)

        query = {key.lower(): value for key, value in parse_qsl(parsed.query, keep_blank_values=True)}
        sslmode = str(query.get("sslmode", "") or "").strip().lower()
        if sslmode == "disable":
            base["ssl"] = "disable"

        host = str(base.get("host") or "").strip().lower()
        is_local = host in _LOCAL_DB_HOSTS
        attempts: List[Tuple[str, Dict[str, Any]]] = []

        def _push_attempt(label: str, payload: Dict[str, Any]) -> None:
            clean = {key: value for key, value in payload.items() if value is not None}
            if is_local and not clean.get("ssl"):
                clean["ssl"] = "disable"
            fingerprint = json.dumps(clean, ensure_ascii=False, sort_keys=True, default=str)
            if any(existing[0] == fingerprint for existing in _seen):
                return
            _seen.append((fingerprint, label))
            attempts.append((label, clean))

        _seen: List[Tuple[str, str]] = []

        if is_local:
            local_base = dict(base)
            local_base["host"] = "127.0.0.1"

            no_password = dict(local_base)
            no_password.pop("password", None)
            _push_attempt("local_ipv4_no_password", no_password)

            empty_password = dict(local_base)
            empty_password["password"] = ""
            _push_attempt("local_ipv4_empty_password", empty_password)

            _push_attempt("local_ipv4_original_password", local_base)

        _push_attempt("parsed_dsn", dict(base))
        _push_attempt("raw_dsn", {"dsn": self._dsn})
        return attempts

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
        conn: Any,
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

            CREATE INDEX IF NOT EXISTS idx_document_extractions_payload_file_hash
                ON document_extractions ((extraction_json->>'file_hash'));

            CREATE INDEX IF NOT EXISTS idx_document_extractions_payload_file_hash_schema_hash
                ON document_extractions (
                    (extraction_json->>'file_hash'),
                    (extraction_json->>'schema_hash')
                );

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

            CREATE TABLE IF NOT EXISTS graph_sync_outbox (
                outbox_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                source TEXT NOT NULL,
                source_batch_key TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                sync_kind TEXT NOT NULL,
                file_hash TEXT,
                payload_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                status TEXT NOT NULL DEFAULT 'queued',
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                last_error TEXT,
                last_response_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                last_attempt_at TIMESTAMPTZ,
                delivered_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                CONSTRAINT uq_graph_sync_outbox_scope UNIQUE (tenant_id, source, source_batch_key, endpoint)
            );

            CREATE INDEX IF NOT EXISTS idx_graph_sync_outbox_status_due
                ON graph_sync_outbox (status, next_attempt_at, created_at);

            CREATE INDEX IF NOT EXISTS idx_graph_sync_outbox_file_hash
                ON graph_sync_outbox (file_hash, created_at DESC);
        """

        async with self._pool.acquire() as conn:
            await conn.execute(ddl)
