from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import SplitResult, parse_qsl, urlencode, urlsplit, urlunsplit

logger = logging.getLogger("uvicorn.error")


def _stable_dumps(value: Any) -> str:
    return json.dumps(_to_plain(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _fingerprint(*parts: Any) -> str:
    joined = "||".join(_stable_dumps(part) for part in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:32]


def _default_low_conf_threshold() -> float:
    raw = _safe_float(os.getenv("MODULE4_ALERT_LOW_CONF_THRESHOLD", "0.55"), 0.55)
    return max(0.0, min(1.0, raw))


def _build_default_rules() -> Tuple[Dict[str, Any], ...]:
    low_conf_threshold = _default_low_conf_threshold()
    return (
        {
            "rule_id": "RULE_LOW_CONFIDENCE",
            "name": "Low Confidence Extraction",
            "severity": "yellow",
            "rule_kind": "deterministic",
            "expr": {
                "scope": "field",
                "path": "confidence",
                "op": "lt",
                "value": low_conf_threshold,
                "risk_formula": "1_minus_confidence",
                "title": "Field confidence too low: {field_name}",
                "summary": "{file_name} field {field_name} confidence={confidence}",
            },
            "enabled": True,
            "version": 1,
        },
        {
            "rule_id": "RULE_DOC_ERRORS",
            "name": "Document Parsing Errors",
            "severity": "orange",
            "rule_kind": "deterministic",
            "expr": {
                "scope": "document",
                "path": "errors",
                "op": "non_empty",
                "risk_score": 92.0,
                "title": "Document parsing errors: {file_name}",
                "summary": "{file_name} has {errors_count} parsing errors",
            },
            "enabled": True,
            "version": 1,
        },
        {
            "rule_id": "RULE_QUALITY_DEGRADED",
            "name": "Quality Gate Degraded",
            "severity": "orange",
            "rule_kind": "deterministic",
            "expr": {
                "scope": "document",
                "path": "diagnostics.quality_status",
                "op": "eq",
                "value": "degraded",
                "risk_score": 80.0,
                "title": "Quality degraded: {file_name}",
                "summary": "Quality gate degraded for {file_name}",
            },
            "enabled": True,
            "version": 1,
        },
        {
            "rule_id": "BUSINESS_ALERT_PRIMARY_SIGNAL",
            "name": "Primary Business Signal Alert",
            "severity": "orange",
            "rule_kind": "deterministic",
            "expr": {
                "scope": "document",
                "path": "__semantic_business_alert_kind__",
                "op": "eq",
                "value": "primary_signal",
                "risk_score": 78.0,
                "title": "Primary business signal detected: {file_name}",
                "summary": "Business semantic pipeline identified a primary signal in {file_name}",
            },
            "enabled": True,
            "version": 1,
        },
        {
            "rule_id": "BUSINESS_ALERT_DISPARITY",
            "name": "Business Disparity Alert",
            "severity": "orange",
            "rule_kind": "deterministic",
            "expr": {
                "scope": "document",
                "path": "__semantic_business_alert_kind__",
                "op": "eq",
                "value": "disparity",
                "risk_score": 83.0,
                "title": "Business disparity detected: {file_name}",
                "summary": "Business semantic pipeline identified a disparity signal in {file_name}",
            },
            "enabled": True,
            "version": 1,
        },
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    return value


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else default
    except Exception:
        return default


def _is_unique_violation_error(exc: Exception) -> bool:
    return type(exc).__name__ == "UniqueViolationError"


def _json_text(value: Any, key: str) -> str:
    if not isinstance(value, dict):
        return ""
    raw = value.get(key)
    return str(raw or "").strip()


def _payload_file_hash(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    context = value.get("context") if isinstance(value.get("context"), dict) else {}
    raw = context.get("file_hash")
    if raw is None:
        raw = value.get("file_hash")
    return str(raw or "").strip()


def _graph_scope_key(graph_file_id: Optional[str]) -> str:
    return str(graph_file_id or "").strip() or "__legacy__"


def _rewrite_localhost_dsn(dsn: str, replacement_host: str = "127.0.0.1") -> str | None:
    raw = str(dsn or "").strip()
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
    except Exception:
        return None
    if not parts.scheme or not parts.hostname or parts.hostname.lower() != "localhost":
        return None

    auth = ""
    if parts.username is not None:
        auth = parts.username
        if parts.password is not None:
            auth = f"{auth}:{parts.password}"
        auth = f"{auth}@"
    host = replacement_host
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    rewritten = SplitResult(
        scheme=parts.scheme,
        netloc=f"{auth}{host}",
        path=parts.path,
        query=parts.query,
        fragment=parts.fragment,
    )
    return urlunsplit(rewritten)


def _rewrite_local_dsn_sslmode(dsn: str, sslmode: str = "disable") -> str | None:
    raw = str(dsn or "").strip()
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
    except Exception:
        return None
    hostname = str(parts.hostname or "").strip().lower()
    if hostname not in {"localhost", "127.0.0.1"}:
        return None

    query_items = dict(parse_qsl(parts.query, keep_blank_values=True))
    current_sslmode = str(query_items.get("sslmode") or "").strip().lower()
    if current_sslmode:
        return None

    query_items["sslmode"] = sslmode
    rewritten = SplitResult(
        scheme=parts.scheme,
        netloc=parts.netloc,
        path=parts.path,
        query=urlencode(query_items),
        fragment=parts.fragment,
    )
    return urlunsplit(rewritten)


def _dsn_connection_candidates(dsn: str) -> List[str]:
    raw = str(dsn or "").strip()
    if not raw:
        return []

    initial_candidates: List[str] = []
    preferred_local = _rewrite_local_dsn_sslmode(raw)
    if preferred_local:
        initial_candidates.append(preferred_local)
    initial_candidates.append(raw)

    candidates: List[str] = []
    for candidate in initial_candidates:
        if candidate not in candidates:
            candidates.append(candidate)

    for candidate in list(candidates):
        ipv4_fallback = _rewrite_localhost_dsn(candidate)
        if ipv4_fallback and ipv4_fallback not in candidates:
            candidates.append(ipv4_fallback)

    for candidate in list(candidates):
        ssl_disabled = _rewrite_local_dsn_sslmode(candidate)
        if ssl_disabled and ssl_disabled not in candidates:
            candidates.append(ssl_disabled)

    return candidates


async def _configure_asyncpg_connection(conn: Any) -> None:
    await conn.set_type_codec(
        "json",
        schema="pg_catalog",
        encoder=json.dumps,
        decoder=json.loads,
        format="text",
    )
    await conn.set_type_codec(
        "jsonb",
        schema="pg_catalog",
        encoder=json.dumps,
        decoder=json.loads,
        format="text",
    )


class Module4Storage:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Optional[Any] = None
        self._last_connect_error = ""
        self._lock = asyncio.Lock()

        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._batches: Dict[str, Dict[str, Any]] = {}
        self._batch_unique: Dict[Tuple[str, str, str], str] = {}
        self._documents: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._graph_files: Dict[str, Dict[str, Any]] = {}
        self._graph_file_by_key: Dict[Tuple[str, str], str] = {}
        self._graph_versions: Dict[str, Dict[str, Any]] = {}
        self._nodes: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
        self._nodes_by_id: Dict[str, Dict[str, Any]] = {}
        self._edges: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}
        self._edges_by_id: Dict[str, Dict[str, Any]] = {}
        self._evidence: Dict[str, Dict[str, Any]] = {}
        self._evidence_by_key: Dict[Tuple[str, str], str] = {}
        self._edge_evidence: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._alerts: Dict[str, Dict[str, Any]] = {}
        self._alerts_by_key: Dict[Tuple[str, str], str] = {}
        self._rules: Dict[str, Dict[str, Any]] = {}

    async def connect(self) -> None:
        force_memory = str(os.getenv("MODULE4_FORCE_MEMORY_MODE", "0")).strip().lower() in {"1", "true", "yes"}
        if force_memory:
            raise RuntimeError("MODULE4_FORCE_MEMORY_MODE is no longer supported")
        try:
            import asyncpg

            connect_timeout = _safe_float(os.getenv("MODULE4_DB_CONNECT_TIMEOUT_SEC", "3"), 3.0)
            schema_timeout = max(connect_timeout, _safe_float(os.getenv("MODULE4_DB_SCHEMA_TIMEOUT_SEC", "8"), 8.0))
            connect_errors: List[str] = []
            for candidate_dsn in _dsn_connection_candidates(self._dsn):
                logger.info("module4 storage trying database candidate: %s", candidate_dsn)
                try:
                    self._pool = await asyncio.wait_for(
                        asyncpg.create_pool(
                            candidate_dsn,
                            min_size=1,
                            max_size=10,
                            timeout=connect_timeout,
                            init=_configure_asyncpg_connection,
                        ),
                        timeout=max(connect_timeout + 1.0, 5.0),
                    )
                    logger.info("module4 storage pool created for candidate: %s", candidate_dsn)
                    await asyncio.wait_for(self._init_schema(), timeout=schema_timeout)
                    logger.info("module4 storage schema init completed for candidate: %s", candidate_dsn)
                    self._last_connect_error = ""
                    break
                except Exception as exc:
                    if self._pool is not None:
                        try:
                            await self._pool.close()
                        except Exception:
                            pass
                    self._pool = None
                    logger.warning("module4 storage candidate failed: %s: %s", candidate_dsn, exc)
                    connect_errors.append(f"{candidate_dsn} -> {type(exc).__name__}: {exc}")
            if self._pool is None:
                raise RuntimeError(" | ".join(connect_errors) or "No valid database connection candidates")
        except Exception as exc:
            self._pool = None
            self._last_connect_error = f"{type(exc).__name__}: {exc}"
            logger.error("module4 storage connect failed: %s", self._last_connect_error)
            raise
        await self.ensure_default_rules()

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    def diagnostics(self) -> Dict[str, Any]:
        return {
            "db_connected": self._pool is not None,
            "last_connect_error": self._last_connect_error,
            "jobs_in_memory": len(self._jobs),
            "alerts_in_memory": len(self._alerts),
            "nodes_in_memory": len(self._nodes),
            "edges_in_memory": len(self._edges),
        }

    async def _init_schema(self) -> None:
        if not self._pool:
            return
        init_path = Path(__file__).resolve().parents[1] / "sql" / "init.sql"
        sql = init_path.read_text(encoding="utf-8")
        async with self._pool.acquire() as conn:
            await conn.execute(sql)

    async def ensure_default_rules(self) -> None:
        existing = await self.list_rules(tenant_id="default")
        existing_ids = {str(item.get("rule_id")) for item in existing}
        for rule in _build_default_rules():
            if str(rule["rule_id"]) in existing_ids:
                continue
            await self.upsert_rule(tenant_id="default", **rule)

    async def queue_size(self) -> int:
        if not self._pool:
            return sum(1 for v in self._jobs.values() if v.get("status") in {"queued", "running"})
        async with self._pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT COUNT(1) FROM module4.jobs WHERE status IN ('queued','running')"
            )
        return int(value or 0)

    @asynccontextmanager
    async def transaction(self) -> Any:
        if not self._pool:
            yield None
            return
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    async def create_job(self, *, tenant_id: str, job_type: str, status: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        payload = _to_plain(payload)
        if not self._pool:
            async with self._lock:
                now = _now()
                job_id = str(uuid.uuid4())
                row = {
                    "job_id": job_id,
                    "tenant_id": tenant_id,
                    "job_type": job_type,
                    "status": status,
                    "progress": 0.0,
                    "error_message": None,
                    "payload": payload,
                    "result": {},
                    "created_at": now,
                    "started_at": None,
                    "finished_at": None,
                }
                self._jobs[job_id] = row
                return dict(row)

        sql = """
            INSERT INTO module4.jobs (tenant_id, job_type, status, payload)
            VALUES ($1, $2, $3, $4::jsonb)
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, tenant_id, job_type, status, payload)
        return _to_plain(dict(row))

    async def get_job(self, job_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        job_id = str(job_id).strip()
        if not self._pool:
            value = self._jobs.get(job_id)
            if not value:
                return None
            if tenant_id and str(value.get("tenant_id")) != str(tenant_id):
                return None
            return dict(value)
        async with self._pool.acquire() as conn:
            if tenant_id:
                row = await conn.fetchrow(
                    "SELECT * FROM module4.jobs WHERE job_id = $1 AND tenant_id = $2",
                    job_id,
                    tenant_id,
                )
            else:
                row = await conn.fetchrow("SELECT * FROM module4.jobs WHERE job_id = $1", job_id)
        return _to_plain(dict(row)) if row else None

    async def update_job(self, job_id: str, **fields: Any) -> Optional[Dict[str, Any]]:
        allowed = {"status", "progress", "error_message", "payload", "result", "started_at", "finished_at"}
        update_fields = {k: _to_plain(v) for k, v in fields.items() if k in allowed}
        if not update_fields:
            return await self.get_job(job_id)

        job_id = str(job_id).strip()
        if not self._pool:
            async with self._lock:
                item = self._jobs.get(job_id)
                if not item:
                    return None
                item.update(update_fields)
                return dict(item)

        keys = list(update_fields.keys())
        values: List[Any] = []
        sets: List[str] = []
        for idx, key in enumerate(keys, start=1):
            values.append(update_fields[key])
            if key in {"payload", "result"}:
                sets.append(f"{key} = ${idx}::jsonb")
            else:
                sets.append(f"{key} = ${idx}")
        values.append(job_id)
        sql = f"UPDATE module4.jobs SET {', '.join(sets)} WHERE job_id = ${len(values)} RETURNING *"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, *values)
        return _to_plain(dict(row)) if row else None

    async def create_ingest_batch(
        self,
        *,
        tenant_id: str,
        source: str,
        source_batch_key: Optional[str],
        job_id: str,
        raw_payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_payload = _to_plain(raw_payload)
        source_batch_key = (source_batch_key or "").strip() or None

        if not self._pool:
            async with self._lock:
                if source_batch_key:
                    uniq = (tenant_id, source, source_batch_key)
                    existing = self._batch_unique.get(uniq)
                    if existing and existing in self._batches:
                        row = self._batches[existing]
                        row.update({"job_id": job_id, "raw_payload": raw_payload})
                        return dict(row)
                batch_id = str(uuid.uuid4())
                row = {
                    "batch_id": batch_id,
                    "tenant_id": tenant_id,
                    "source": source,
                    "source_batch_key": source_batch_key,
                    "job_id": job_id,
                    "raw_payload": raw_payload,
                    "created_at": _now(),
                }
                self._batches[batch_id] = row
                if source_batch_key:
                    self._batch_unique[(tenant_id, source, source_batch_key)] = batch_id
                return dict(row)

        sql = """
            INSERT INTO module4.ingest_batches (tenant_id, source, source_batch_key, job_id, raw_payload)
            VALUES ($1, $2, $3, $4, $5::jsonb)
            ON CONFLICT (tenant_id, source, source_batch_key)
            DO UPDATE SET raw_payload = EXCLUDED.raw_payload, job_id = EXCLUDED.job_id
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, tenant_id, source, source_batch_key, job_id, raw_payload)
        return _to_plain(dict(row))

    async def get_ingest_batch(
        self,
        *,
        tenant_id: str,
        source: str,
        source_batch_key: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        source_batch_key = (source_batch_key or "").strip() or None
        if not source_batch_key:
            return None

        if not self._pool:
            batch_id = self._batch_unique.get((tenant_id, source, source_batch_key))
            if not batch_id:
                return None
            row = self._batches.get(batch_id)
            return dict(row) if row else None

        sql = """
            SELECT *
            FROM module4.ingest_batches
            WHERE tenant_id = $1 AND source = $2 AND source_batch_key = $3
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, tenant_id, source, source_batch_key)
        return _to_plain(dict(row)) if row else None

    async def list_ingest_batches(self, *, tenant_id: str) -> List[Dict[str, Any]]:
        if not self._pool:
            items = [dict(v) for v in self._batches.values() if v.get("tenant_id") == tenant_id]
            items.sort(key=lambda x: x.get("created_at") or _now())
            return items

        sql = """
            SELECT *
            FROM module4.ingest_batches
            WHERE tenant_id = $1
            ORDER BY created_at ASC
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, tenant_id)
        return [_to_plain(dict(row)) for row in rows]

    async def upsert_graph_file(
        self,
        *,
        tenant_id: str,
        file_hash: str,
        file_name: str,
        workspace_id: Optional[str],
        graph_mode: str,
        source: str,
        status: str,
        current_job_id: Optional[str] = None,
        active_version_id: Optional[str] = None,
        last_error: Optional[str] = None,
        node_count: Optional[int] = None,
        edge_count: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        last_indexed_at: Optional[datetime] = None,
        conn: Optional[Any] = None,
    ) -> Dict[str, Any]:
        file_hash = str(file_hash or "").strip()
        file_name = str(file_name or "").strip() or file_hash or "unknown"
        payload = _to_plain(metadata or {})
        workspace_value = str(workspace_id or "").strip() or None
        status_value = str(status or "queued").strip() or "queued"
        graph_mode_value = str(graph_mode or "hybrid").strip() or "hybrid"
        source_value = str(source or "module2").strip() or "module2"
        current_job_value = str(current_job_id or "").strip() or None
        active_version_value = str(active_version_id or "").strip() or None
        last_error_value = str(last_error or "").strip() or None
        node_total = max(0, int(node_count or 0))
        edge_total = max(0, int(edge_count or 0))

        if not self._pool:
            async with self._lock:
                now = _now()
                key = (tenant_id, file_hash)
                graph_file_id = self._graph_file_by_key.get(key)
                row = self._graph_files.get(graph_file_id or "")
                if row:
                    row.update(
                        {
                            "file_name": file_name,
                            "workspace_id": workspace_value,
                            "graph_mode": graph_mode_value,
                            "source": source_value,
                            "status": status_value,
                            "current_job_id": current_job_value,
                            "active_version_id": active_version_value,
                            "last_error": last_error_value,
                            "node_count": node_total,
                            "edge_count": edge_total,
                            "metadata": payload,
                            "updated_at": now,
                            "last_indexed_at": last_indexed_at,
                        }
                    )
                    return dict(row)
                row = {
                    "graph_file_id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "file_hash": file_hash,
                    "file_name": file_name,
                    "workspace_id": workspace_value,
                    "graph_mode": graph_mode_value,
                    "source": source_value,
                    "status": status_value,
                    "current_job_id": current_job_value,
                    "active_version_id": active_version_value,
                    "last_error": last_error_value,
                    "node_count": node_total,
                    "edge_count": edge_total,
                    "metadata": payload,
                    "created_at": now,
                    "updated_at": now,
                    "last_indexed_at": last_indexed_at,
                }
                self._graph_files[row["graph_file_id"]] = row
                self._graph_file_by_key[key] = row["graph_file_id"]
                return dict(row)

        sql = """
            INSERT INTO module4.graph_files (
                tenant_id,
                file_hash,
                file_name,
                workspace_id,
                graph_mode,
                source,
                status,
                current_job_id,
                active_version_id,
                last_error,
                node_count,
                edge_count,
                metadata,
                last_indexed_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::jsonb, $14)
            ON CONFLICT (tenant_id, file_hash)
            DO UPDATE SET
                file_name = EXCLUDED.file_name,
                workspace_id = EXCLUDED.workspace_id,
                graph_mode = EXCLUDED.graph_mode,
                source = EXCLUDED.source,
                status = EXCLUDED.status,
                current_job_id = EXCLUDED.current_job_id,
                active_version_id = COALESCE(EXCLUDED.active_version_id, module4.graph_files.active_version_id),
                last_error = EXCLUDED.last_error,
                node_count = EXCLUDED.node_count,
                edge_count = EXCLUDED.edge_count,
                metadata = EXCLUDED.metadata,
                last_indexed_at = COALESCE(EXCLUDED.last_indexed_at, module4.graph_files.last_indexed_at),
                updated_at = NOW()
            RETURNING *
        """
        if conn is not None:
            row = await conn.fetchrow(
                sql,
                tenant_id,
                file_hash,
                file_name,
                workspace_value,
                graph_mode_value,
                source_value,
                status_value,
                current_job_value,
                active_version_value,
                last_error_value,
                node_total,
                edge_total,
                payload,
                last_indexed_at,
            )
        else:
            async with self._pool.acquire() as acquired:
                row = await acquired.fetchrow(
                    sql,
                    tenant_id,
                    file_hash,
                    file_name,
                    workspace_value,
                    graph_mode_value,
                    source_value,
                    status_value,
                    current_job_value,
                    active_version_value,
                    last_error_value,
                    node_total,
                    edge_total,
                    payload,
                    last_indexed_at,
                )
        return _to_plain(dict(row))

    async def add_graph_version(
        self,
        *,
        tenant_id: str,
        file_hash: str,
        job_id: Optional[str],
        workspace_id: Optional[str],
        status: str,
        manifest_path: Optional[str],
        output_dir: Optional[str],
        artifacts_dir: Optional[str],
        reports_dir: Optional[str],
        import_summary: Optional[Dict[str, Any]] = None,
        activate: bool = True,
        conn: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        graph_file = await self.get_graph_file(tenant_id=tenant_id, file_hash=file_hash)
        if not graph_file:
            return None

        payload = _to_plain(import_summary or {})
        job_value = str(job_id or "").strip() or None
        workspace_value = str(workspace_id or "").strip() or None
        manifest_value = str(manifest_path or "").strip() or None
        output_value = str(output_dir or "").strip() or None
        artifacts_value = str(artifacts_dir or "").strip() or None
        reports_value = str(reports_dir or "").strip() or None
        status_value = str(status or "queued").strip() or "queued"

        if not self._pool:
            async with self._lock:
                now = _now()
                row = {
                    "graph_version_id": str(uuid.uuid4()),
                    "graph_file_id": str(graph_file.get("graph_file_id")),
                    "tenant_id": tenant_id,
                    "file_hash": file_hash,
                    "job_id": job_value,
                    "workspace_id": workspace_value,
                    "status": status_value,
                    "manifest_path": manifest_value,
                    "output_dir": output_value,
                    "artifacts_dir": artifacts_value,
                    "reports_dir": reports_value,
                    "import_summary": payload,
                    "created_at": now,
                    "updated_at": now,
                }
                self._graph_versions[row["graph_version_id"]] = row
                graph_row = self._graph_files.get(str(graph_file.get("graph_file_id")))
                if graph_row and activate:
                    graph_row["active_version_id"] = row["graph_version_id"]
                    graph_row["updated_at"] = now
                return dict(row)

        sql = """
            INSERT INTO module4.graph_versions (
                graph_file_id,
                tenant_id,
                file_hash,
                job_id,
                workspace_id,
                status,
                manifest_path,
                output_dir,
                artifacts_dir,
                reports_dir,
                import_summary
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb)
            RETURNING *
        """
        if conn is not None:
            row = await conn.fetchrow(
                sql,
                graph_file["graph_file_id"],
                tenant_id,
                file_hash,
                job_value,
                workspace_value,
                status_value,
                manifest_value,
                output_value,
                artifacts_value,
                reports_value,
                payload,
            )
            if activate:
                await conn.execute(
                    """
                    UPDATE module4.graph_files
                    SET active_version_id = $1, updated_at = NOW()
                    WHERE graph_file_id = $2
                    """,
                    row["graph_version_id"],
                    graph_file["graph_file_id"],
                )
        else:
            async with self._pool.acquire() as acquired:
                row = await acquired.fetchrow(
                    sql,
                    graph_file["graph_file_id"],
                    tenant_id,
                    file_hash,
                    job_value,
                    workspace_value,
                    status_value,
                    manifest_value,
                    output_value,
                    artifacts_value,
                    reports_value,
                    payload,
                )
                if activate:
                    await acquired.execute(
                        """
                        UPDATE module4.graph_files
                        SET active_version_id = $1, updated_at = NOW()
                        WHERE graph_file_id = $2
                        """,
                        row["graph_version_id"],
                        graph_file["graph_file_id"],
                    )
        return _to_plain(dict(row))

    async def update_graph_version(
        self,
        *,
        tenant_id: str,
        graph_version_id: str,
        status: Optional[str] = None,
        job_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        manifest_path: Optional[str] = None,
        output_dir: Optional[str] = None,
        artifacts_dir: Optional[str] = None,
        reports_dir: Optional[str] = None,
        import_summary: Optional[Dict[str, Any]] = None,
        conn: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        graph_version_id = str(graph_version_id or "").strip()
        if not graph_version_id:
            return None

        status_value = str(status or "").strip() or None
        job_value = str(job_id or "").strip() or None
        workspace_value = str(workspace_id or "").strip() or None
        manifest_value = str(manifest_path or "").strip() or None
        output_value = str(output_dir or "").strip() or None
        artifacts_value = str(artifacts_dir or "").strip() or None
        reports_value = str(reports_dir or "").strip() or None
        summary_value = _to_plain(import_summary) if import_summary is not None else None

        if not self._pool:
            async with self._lock:
                row = self._graph_versions.get(graph_version_id)
                if not row or str(row.get("tenant_id") or "") != tenant_id:
                    return None
                row["updated_at"] = _now()
                if status_value is not None:
                    row["status"] = status_value
                if job_id is not None:
                    row["job_id"] = job_value
                if workspace_id is not None:
                    row["workspace_id"] = workspace_value
                if manifest_path is not None:
                    row["manifest_path"] = manifest_value
                if output_dir is not None:
                    row["output_dir"] = output_value
                if artifacts_dir is not None:
                    row["artifacts_dir"] = artifacts_value
                if reports_dir is not None:
                    row["reports_dir"] = reports_value
                if import_summary is not None:
                    row["import_summary"] = summary_value or {}
                return dict(row)

        assignments: List[str] = []
        values: List[Any] = []
        idx = 1

        def _assign(column: str, value: Any, *, jsonb: bool = False) -> None:
            nonlocal idx
            assignments.append(f"{column} = ${idx}{'::jsonb' if jsonb else ''}")
            values.append(value)
            idx += 1

        if status_value is not None:
            _assign("status", status_value)
        if job_id is not None:
            _assign("job_id", job_value)
        if workspace_id is not None:
            _assign("workspace_id", workspace_value)
        if manifest_path is not None:
            _assign("manifest_path", manifest_value)
        if output_dir is not None:
            _assign("output_dir", output_value)
        if artifacts_dir is not None:
            _assign("artifacts_dir", artifacts_value)
        if reports_dir is not None:
            _assign("reports_dir", reports_value)
        if import_summary is not None:
            _assign("import_summary", summary_value or {}, jsonb=True)

        if not assignments:
            return None

        assignments.append("updated_at = NOW()")
        values.extend([tenant_id, graph_version_id])
        sql = f"""
            UPDATE module4.graph_versions
            SET {', '.join(assignments)}
            WHERE tenant_id = ${idx} AND graph_version_id = ${idx + 1}
            RETURNING *
        """

        if conn is not None:
            row = await conn.fetchrow(sql, *values)
        else:
            async with self._pool.acquire() as acquired:
                row = await acquired.fetchrow(sql, *values)
        return _to_plain(dict(row)) if row else None

    async def get_graph_version(self, *, tenant_id: str, graph_version_id: str) -> Optional[Dict[str, Any]]:
        graph_version_id = str(graph_version_id or "").strip()
        if not graph_version_id:
            return None

        if not self._pool:
            row = self._graph_versions.get(graph_version_id)
            if not row or str(row.get("tenant_id") or "") != tenant_id:
                return None
            return dict(row)

        sql = """
            SELECT *
            FROM module4.graph_versions
            WHERE tenant_id = $1 AND graph_version_id = $2
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, tenant_id, graph_version_id)
        return _to_plain(dict(row)) if row else None

    async def assign_graph_version(
        self,
        *,
        tenant_id: str,
        graph_file_id: str,
        graph_version_id: str,
        workspace_id: Optional[str] = None,
    ) -> Dict[str, int]:
        graph_file_id = str(graph_file_id or "").strip()
        graph_version_id = str(graph_version_id or "").strip()
        workspace_value = str(workspace_id or "").strip() or None
        if not graph_file_id or not graph_version_id:
            return {"nodes": 0, "edges": 0}

        if not self._pool:
            async with self._lock:
                node_count = 0
                edge_count = 0
                for row in self._nodes_by_id.values():
                    if str(row.get("tenant_id") or "") != tenant_id:
                        continue
                    if str(row.get("graph_file_id") or "") != graph_file_id:
                        continue
                    attrs = row.get("attrs") if isinstance(row.get("attrs"), dict) else {}
                    if workspace_value and _json_text(attrs, "workspace_id") != workspace_value:
                        continue
                    row["graph_version_id"] = graph_version_id
                    row["updated_at"] = _now()
                    node_count += 1
                for row in self._edges_by_id.values():
                    if str(row.get("tenant_id") or "") != tenant_id:
                        continue
                    if str(row.get("graph_file_id") or "") != graph_file_id:
                        continue
                    attrs = row.get("attrs") if isinstance(row.get("attrs"), dict) else {}
                    if workspace_value and _json_text(attrs, "workspace_id") != workspace_value:
                        continue
                    row["graph_version_id"] = graph_version_id
                    row["updated_at"] = _now()
                    edge_count += 1
                return {"nodes": node_count, "edges": edge_count}

        node_sql = """
            UPDATE module4.nodes
            SET graph_version_id = $1, updated_at = NOW()
            WHERE tenant_id = $2
              AND graph_file_id = $3
              AND ($4::text IS NULL OR (attrs->>'workspace_id') = $4)
        """
        edge_sql = """
            UPDATE module4.edges
            SET graph_version_id = $1, updated_at = NOW()
            WHERE tenant_id = $2
              AND graph_file_id = $3
              AND ($4::text IS NULL OR (attrs->>'workspace_id') = $4)
        """
        async with self._pool.acquire() as conn:
            node_status = await conn.execute(node_sql, graph_version_id, tenant_id, graph_file_id, workspace_value)
            edge_status = await conn.execute(edge_sql, graph_version_id, tenant_id, graph_file_id, workspace_value)
        try:
            node_count = int(str(node_status).rsplit(" ", 1)[-1])
        except Exception:
            node_count = 0
        try:
            edge_count = int(str(edge_status).rsplit(" ", 1)[-1])
        except Exception:
            edge_count = 0
        return {"nodes": node_count, "edges": edge_count}

    async def get_graph_file(self, *, tenant_id: str, file_hash: str) -> Optional[Dict[str, Any]]:
        file_hash = str(file_hash or "").strip()
        if not file_hash:
            return None

        if not self._pool:
            graph_file_id = self._graph_file_by_key.get((tenant_id, file_hash))
            row = self._graph_files.get(graph_file_id or "")
            return dict(row) if row else None

        sql = """
            SELECT *
            FROM module4.graph_files
            WHERE tenant_id = $1 AND file_hash = $2
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, tenant_id, file_hash)
        return _to_plain(dict(row)) if row else None

    async def list_graph_files(
        self,
        *,
        tenant_id: str,
        status: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        limit = max(1, min(500, int(limit)))
        status_value = str(status or "").strip() or None

        if not self._pool:
            items = [dict(v) for v in self._graph_files.values() if v.get("tenant_id") == tenant_id]
            if status_value:
                items = [item for item in items if str(item.get("status") or "") == status_value]
            items.sort(key=lambda item: item.get("updated_at") or item.get("created_at") or _now(), reverse=True)
            return items[:limit]

        clauses = ["tenant_id = $1"]
        params: List[Any] = [tenant_id]
        if status_value:
            clauses.append("status = $2")
            params.append(status_value)
            limit_idx = 3
        else:
            limit_idx = 2
        sql = f"""
            SELECT *
            FROM module4.graph_files
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ${limit_idx}
        """
        params.append(limit)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [_to_plain(dict(row)) for row in rows]

    async def list_recoverable_jobs(self) -> List[Dict[str, Any]]:
        if not self._pool:
            items = [
                dict(v)
                for v in self._jobs.values()
                if v.get("status") in {"queued", "running"} and v.get("job_type") in {"ingest", "rebuild_graph"}
            ]
            items.sort(key=lambda x: x.get("created_at") or _now())
            for item in items:
                batch = next(
                    (dict(value) for value in self._batches.values() if str(value.get("job_id")) == str(item.get("job_id"))),
                    None,
                )
                if batch:
                    item["batch_id"] = batch.get("batch_id")
                    item["raw_payload"] = batch.get("raw_payload")
            return items

        sql = """
            SELECT job.job_id, job.job_type, job.status, job.payload, batch.batch_id, batch.raw_payload
            FROM module4.jobs job
            LEFT JOIN module4.ingest_batches batch ON batch.job_id = job.job_id
            WHERE job.status IN ('queued', 'running')
              AND job.job_type IN ('ingest', 'rebuild_graph')
            ORDER BY job.created_at ASC
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql)
        return [_to_plain(dict(row)) for row in rows]

    async def upsert_document(
        self,
        *,
        tenant_id: str,
        batch_id: str,
        file_name: str,
        file_hash: str,
        track: str,
        diagnostics: Dict[str, Any],
        conn: Optional[Any] = None,
    ) -> Dict[str, Any]:
        diagnostics = _to_plain(diagnostics)
        file_hash = (file_hash or "").strip() or str(uuid.uuid4())
        file_name = (file_name or "").strip() or "unknown"
        track = (track or "").strip()

        if not self._pool:
            async with self._lock:
                key = (tenant_id, file_hash)
                now = _now()
                row = self._documents.get(key)
                if row:
                    row.update(
                        {
                            "batch_id": batch_id,
                            "file_name": file_name,
                            "track": track,
                            "diagnostics": diagnostics,
                        }
                    )
                    return dict(row)
                row = {
                    "doc_id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "batch_id": batch_id,
                    "file_name": file_name,
                    "file_hash": file_hash,
                    "track": track,
                    "diagnostics": diagnostics,
                    "created_at": now,
                }
                self._documents[key] = row
                return dict(row)

        sql = """
            INSERT INTO module4.documents (tenant_id, batch_id, file_name, file_hash, track, diagnostics)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
            ON CONFLICT (tenant_id, file_hash)
            DO UPDATE SET
                batch_id = EXCLUDED.batch_id,
                file_name = EXCLUDED.file_name,
                track = EXCLUDED.track,
                diagnostics = EXCLUDED.diagnostics
            RETURNING *
        """
        if conn is not None:
            row = await conn.fetchrow(sql, tenant_id, batch_id, file_name, file_hash, track, diagnostics)
        else:
            async with self._pool.acquire() as acquired:
                row = await acquired.fetchrow(sql, tenant_id, batch_id, file_name, file_hash, track, diagnostics)
        return _to_plain(dict(row))

    async def upsert_node(
        self,
        *,
        tenant_id: str,
        graph_file_id: Optional[str] = None,
        graph_version_id: Optional[str] = None,
        node_type: str,
        canonical_key: str,
        display_name: str,
        attrs: Dict[str, Any],
        confidence: float,
        conn: Optional[Any] = None,
    ) -> Dict[str, Any]:
        attrs = _to_plain(attrs)
        confidence = _safe_float(confidence, 0.0)
        graph_file_value = str(graph_file_id or "").strip() or None
        graph_version_value = str(graph_version_id or "").strip() or None
        canonical_key = (canonical_key or "").strip() or str(uuid.uuid4())
        display_name = (display_name or "").strip() or canonical_key

        if not self._pool:
            async with self._lock:
                key = (tenant_id, _graph_scope_key(graph_file_value), node_type, canonical_key)
                now = _now()
                row = self._nodes.get(key)
                if row:
                    row.update(
                        {
                            "graph_file_id": graph_file_value,
                            "graph_version_id": graph_version_value,
                            "display_name": display_name,
                            "attrs": attrs,
                            "confidence": confidence,
                            "last_seen_at": now,
                            "updated_at": now,
                        }
                    )
                    self._nodes_by_id[row["node_id"]] = row
                    return dict(row)
                row = {
                    "node_id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "graph_file_id": graph_file_value,
                    "graph_version_id": graph_version_value,
                    "node_type": node_type,
                    "canonical_key": canonical_key,
                    "display_name": display_name,
                    "attrs": attrs,
                    "confidence": confidence,
                    "first_seen_at": now,
                    "last_seen_at": now,
                    "created_at": now,
                    "updated_at": now,
                }
                self._nodes[key] = row
                self._nodes_by_id[row["node_id"]] = row
                return dict(row)

        if graph_file_value:
            update_sql = """
                WITH candidate AS (
                    SELECT node_id
                    FROM module4.nodes
                    WHERE tenant_id = $1
                      AND graph_file_id = $2::uuid
                      AND node_type = $4
                      AND canonical_key = $5
                    ORDER BY updated_at DESC, created_at DESC, node_id DESC
                    LIMIT 1
                )
                UPDATE module4.nodes AS node
                SET graph_version_id = COALESCE($3::uuid, node.graph_version_id),
                    display_name = $6,
                    attrs = $7::jsonb,
                    confidence = $8,
                    last_seen_at = NOW(),
                    updated_at = NOW()
                FROM candidate
                WHERE node.node_id = candidate.node_id
                RETURNING node.*
            """
            insert_sql = """
                INSERT INTO module4.nodes (
                    tenant_id, graph_file_id, graph_version_id, node_type, canonical_key, display_name, attrs, confidence
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8)
                RETURNING *
            """
            params = (
                tenant_id,
                graph_file_value,
                graph_version_value,
                node_type,
                canonical_key,
                display_name,
                attrs,
                confidence,
            )
        else:
            update_sql = """
                WITH candidate AS (
                    SELECT node_id
                    FROM module4.nodes
                    WHERE tenant_id = $1
                      AND graph_file_id IS NULL
                      AND node_type = $3
                      AND canonical_key = $4
                    ORDER BY updated_at DESC, created_at DESC, node_id DESC
                    LIMIT 1
                )
                UPDATE module4.nodes AS node
                SET graph_version_id = COALESCE($2::uuid, node.graph_version_id),
                    display_name = $5,
                    attrs = $6::jsonb,
                    confidence = $7,
                    last_seen_at = NOW(),
                    updated_at = NOW()
                FROM candidate
                WHERE node.node_id = candidate.node_id
                RETURNING node.*
            """
            insert_sql = """
                INSERT INTO module4.nodes (
                    tenant_id, graph_file_id, graph_version_id, node_type, canonical_key, display_name, attrs, confidence
                )
                VALUES ($1, NULL, $2, $3, $4, $5, $6::jsonb, $7)
                RETURNING *
            """
            params = (
                tenant_id,
                graph_version_value,
                node_type,
                canonical_key,
                display_name,
                attrs,
                confidence,
            )

        async def _execute(conn_obj: Any) -> Dict[str, Any]:
            row = await conn_obj.fetchrow(update_sql, *params)
            if row:
                return _to_plain(dict(row))
            try:
                row = await conn_obj.fetchrow(insert_sql, *params)
            except Exception as exc:
                if not _is_unique_violation_error(exc):
                    raise
                row = await conn_obj.fetchrow(update_sql, *params)
                if row:
                    return _to_plain(dict(row))
                raise
            return _to_plain(dict(row))

        if conn is not None:
            return await _execute(conn)
        async with self._pool.acquire() as acquired:
            return await _execute(acquired)

    async def upsert_edge(
        self,
        *,
        tenant_id: str,
        graph_file_id: Optional[str] = None,
        graph_version_id: Optional[str] = None,
        source_node_id: str,
        target_node_id: str,
        relation_type: str,
        direction: str,
        attrs: Dict[str, Any],
        confidence: float,
        risk_score: float,
        conn: Optional[Any] = None,
    ) -> Dict[str, Any]:
        attrs = _to_plain(attrs)
        confidence = _safe_float(confidence, 0.0)
        risk_score = _safe_float(risk_score, 0.0)
        graph_file_value = str(graph_file_id or "").strip() or None
        graph_version_value = str(graph_version_id or "").strip() or None
        direction = direction if direction in {"out", "bi"} else "out"

        if not self._pool:
            async with self._lock:
                key = (
                    tenant_id,
                    _graph_scope_key(graph_file_value),
                    str(source_node_id),
                    str(target_node_id),
                    relation_type,
                )
                now = _now()
                row = self._edges.get(key)
                if row:
                    row.update(
                        {
                            "graph_file_id": graph_file_value,
                            "graph_version_id": graph_version_value,
                            "direction": direction,
                            "attrs": attrs,
                            "confidence": confidence,
                            "risk_score": risk_score,
                            "last_seen_at": now,
                            "updated_at": now,
                        }
                    )
                    self._edges_by_id[row["edge_id"]] = row
                    return dict(row)
                row = {
                    "edge_id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "graph_file_id": graph_file_value,
                    "graph_version_id": graph_version_value,
                    "source_node_id": str(source_node_id),
                    "target_node_id": str(target_node_id),
                    "relation_type": relation_type,
                    "direction": direction,
                    "attrs": attrs,
                    "confidence": confidence,
                    "risk_score": risk_score,
                    "first_seen_at": now,
                    "last_seen_at": now,
                    "created_at": now,
                    "updated_at": now,
                }
                self._edges[key] = row
                self._edges_by_id[row["edge_id"]] = row
                return dict(row)

        if graph_file_value:
            update_sql = """
                WITH candidate AS (
                    SELECT edge_id
                    FROM module4.edges
                    WHERE tenant_id = $1
                      AND graph_file_id = $2::uuid
                      AND source_node_id = $4::uuid
                      AND target_node_id = $5::uuid
                      AND relation_type = $6
                    ORDER BY updated_at DESC, created_at DESC, edge_id DESC
                    LIMIT 1
                )
                UPDATE module4.edges AS edge
                SET graph_version_id = COALESCE($3::uuid, edge.graph_version_id),
                    direction = $7,
                    attrs = $8::jsonb,
                    confidence = $9,
                    risk_score = $10,
                    last_seen_at = NOW(),
                    updated_at = NOW()
                FROM candidate
                WHERE edge.edge_id = candidate.edge_id
                RETURNING edge.*
            """
            insert_sql = """
                INSERT INTO module4.edges (
                    tenant_id, graph_file_id, graph_version_id, source_node_id, target_node_id, relation_type, direction, attrs, confidence, risk_score
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9, $10)
                RETURNING *
            """
            params = (
                tenant_id,
                graph_file_value,
                graph_version_value,
                source_node_id,
                target_node_id,
                relation_type,
                direction,
                attrs,
                confidence,
                risk_score,
            )
        else:
            update_sql = """
                WITH candidate AS (
                    SELECT edge_id
                    FROM module4.edges
                    WHERE tenant_id = $1
                      AND graph_file_id IS NULL
                      AND source_node_id = $3::uuid
                      AND target_node_id = $4::uuid
                      AND relation_type = $5
                    ORDER BY updated_at DESC, created_at DESC, edge_id DESC
                    LIMIT 1
                )
                UPDATE module4.edges AS edge
                SET graph_version_id = COALESCE($2::uuid, edge.graph_version_id),
                    direction = $6,
                    attrs = $7::jsonb,
                    confidence = $8,
                    risk_score = $9,
                    last_seen_at = NOW(),
                    updated_at = NOW()
                FROM candidate
                WHERE edge.edge_id = candidate.edge_id
                RETURNING edge.*
            """
            insert_sql = """
                INSERT INTO module4.edges (
                    tenant_id, graph_file_id, graph_version_id, source_node_id, target_node_id, relation_type, direction, attrs, confidence, risk_score
                )
                VALUES ($1, NULL, $2, $3, $4, $5, $6, $7::jsonb, $8, $9)
                RETURNING *
            """
            params = (
                tenant_id,
                graph_version_value,
                source_node_id,
                target_node_id,
                relation_type,
                direction,
                attrs,
                confidence,
                risk_score,
            )

        async def _execute(conn_obj: Any) -> Dict[str, Any]:
            row = await conn_obj.fetchrow(update_sql, *params)
            if row:
                return _to_plain(dict(row))
            try:
                row = await conn_obj.fetchrow(insert_sql, *params)
            except Exception as exc:
                if not _is_unique_violation_error(exc):
                    raise
                row = await conn_obj.fetchrow(update_sql, *params)
                if row:
                    return _to_plain(dict(row))
                raise
            return _to_plain(dict(row))

        if conn is not None:
            return await _execute(conn)
        async with self._pool.acquire() as acquired:
            return await _execute(acquired)

    async def insert_evidence(
        self,
        *,
        tenant_id: str,
        doc_id: str,
        object_type: str,
        object_id: str,
        ref_id: Optional[str],
        page_no: Optional[int],
        snippet: str,
        locator: Dict[str, Any],
        bbox: Sequence[Any],
        artifact_url: Optional[str],
        confidence: float,
        conn: Optional[Any] = None,
    ) -> Dict[str, Any]:
        locator = _to_plain(locator)
        bbox_list = list(bbox or [])
        confidence = _safe_float(confidence, 0.0)
        evidence_key = _fingerprint(
            tenant_id,
            doc_id,
            object_type,
            object_id,
            ref_id,
            page_no,
            snippet,
            locator,
            bbox_list,
            artifact_url,
        )

        if not self._pool:
            async with self._lock:
                existing_id = self._evidence_by_key.get((tenant_id, evidence_key))
                if existing_id and existing_id in self._evidence:
                    row = self._evidence[existing_id]
                    row.update(
                        {
                            "ref_id": ref_id,
                            "page_no": page_no,
                            "snippet": snippet,
                            "locator": locator,
                            "bbox": bbox_list,
                            "artifact_url": artifact_url,
                            "confidence": confidence,
                            "evidence_key": evidence_key,
                        }
                    )
                    return dict(row)
                evidence_id = str(uuid.uuid4())
                row = {
                    "evidence_id": evidence_id,
                    "tenant_id": tenant_id,
                    "evidence_key": evidence_key,
                    "doc_id": doc_id,
                    "object_type": object_type,
                    "object_id": object_id,
                    "ref_id": ref_id,
                    "page_no": page_no,
                    "snippet": snippet,
                    "locator": locator,
                    "bbox": bbox_list,
                    "artifact_url": artifact_url,
                    "confidence": confidence,
                    "created_at": _now(),
                }
                self._evidence[evidence_id] = row
                self._evidence_by_key[(tenant_id, evidence_key)] = evidence_id
                return dict(row)

        sql = """
            INSERT INTO module4.evidence (
                tenant_id, evidence_key, doc_id, object_type, object_id, ref_id, page_no, snippet, locator, bbox, artifact_url, confidence
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::jsonb, $11, $12)
            ON CONFLICT (tenant_id, evidence_key) WHERE evidence_key IS NOT NULL
            DO UPDATE SET
                ref_id = EXCLUDED.ref_id,
                page_no = EXCLUDED.page_no,
                snippet = EXCLUDED.snippet,
                locator = EXCLUDED.locator,
                bbox = EXCLUDED.bbox,
                artifact_url = EXCLUDED.artifact_url,
                confidence = EXCLUDED.confidence
            RETURNING *
        """
        if conn is not None:
            row = await conn.fetchrow(
                sql,
                tenant_id,
                evidence_key,
                doc_id,
                object_type,
                object_id,
                ref_id,
                page_no,
                snippet,
                locator,
                bbox_list,
                artifact_url,
                confidence,
            )
        else:
            async with self._pool.acquire() as acquired:
                row = await acquired.fetchrow(
                    sql,
                    tenant_id,
                    evidence_key,
                    doc_id,
                    object_type,
                    object_id,
                    ref_id,
                    page_no,
                    snippet,
                    locator,
                    bbox_list,
                    artifact_url,
                    confidence,
                )
        return _to_plain(dict(row))

    async def link_edge_evidence(self, *, edge_id: str, evidence_id: str, conn: Optional[Any] = None) -> None:
        if not self._pool:
            async with self._lock:
                self._edge_evidence[(edge_id, evidence_id)] = {"edge_id": edge_id, "evidence_id": evidence_id}
            return
        sql = """
            INSERT INTO module4.edge_evidence (edge_id, evidence_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
        """
        if conn is not None:
            await conn.execute(sql, edge_id, evidence_id)
        else:
            async with self._pool.acquire() as acquired:
                await acquired.execute(sql, edge_id, evidence_id)

    async def upsert_rule(
        self,
        *,
        tenant_id: str = "default",
        rule_id: str,
        name: str,
        severity: str,
        rule_kind: str,
        expr: Dict[str, Any],
        enabled: bool = True,
        version: int = 1,
    ) -> Dict[str, Any]:
        tenant_value = str(tenant_id or "default").strip() or "default"
        severity = severity if severity in {"yellow", "orange", "red"} else "yellow"
        rule_kind = "deterministic"
        expr = _to_plain(expr)

        if not self._pool:
            async with self._lock:
                now = _now()
                cache_key = f"{tenant_value}::{rule_id}"
                row = {
                    "tenant_id": tenant_value,
                    "rule_id": rule_id,
                    "name": name,
                    "severity": severity,
                    "rule_kind": rule_kind,
                    "expr": expr,
                    "enabled": bool(enabled),
                    "version": int(version),
                    "created_at": now,
                    "updated_at": now,
                }
                self._rules[cache_key] = row
                return dict(row)

        sql = """
            INSERT INTO module4.rules (tenant_id, rule_id, name, severity, rule_kind, expr, enabled, version)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
            ON CONFLICT (rule_id)
            DO UPDATE SET
                name = EXCLUDED.name,
                severity = EXCLUDED.severity,
                rule_kind = EXCLUDED.rule_kind,
                expr = EXCLUDED.expr,
                enabled = EXCLUDED.enabled,
                version = EXCLUDED.version,
                updated_at = NOW()
            WHERE module4.rules.tenant_id = EXCLUDED.tenant_id
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                sql,
                tenant_value,
                rule_id,
                name,
                severity,
                rule_kind,
                expr,
                enabled,
                int(version),
            )
            if not row:
                existing = await conn.fetchrow("SELECT tenant_id FROM module4.rules WHERE rule_id = $1", rule_id)
                if existing:
                    raise ValueError("rule_id already exists under another tenant")
                raise RuntimeError("module4 rule upsert returned empty result")
        return _to_plain(dict(row))

    async def list_rules(self, *, tenant_id: str = "", enabled_only: bool = False) -> List[Dict[str, Any]]:
        tenant_value = str(tenant_id or "").strip()
        if not self._pool:
            items = list(self._rules.values())
            if tenant_value:
                items = [item for item in items if str(item.get("tenant_id") or "").strip() == tenant_value]
            if enabled_only:
                items = [item for item in items if bool(item.get("enabled"))]
            items.sort(key=lambda x: str(x.get("rule_id", "")))
            return [dict(v) for v in items]

        where_parts: List[str] = []
        params: List[Any] = []
        next_idx = 1
        if tenant_value:
            where_parts.append(f"tenant_id = ${next_idx}")
            params.append(tenant_value)
            next_idx += 1
        if enabled_only:
            where_parts.append("enabled = true")
        where_sql = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT * FROM module4.rules {where_sql} ORDER BY rule_id ASC",
                *params,
            )
        return [_to_plain(dict(r)) for r in rows]

    async def reset_graph_file_scope(
        self,
        *,
        tenant_id: str,
        graph_file_id: str,
        file_hash: Optional[str],
        conn: Optional[Any] = None,
    ) -> Dict[str, int]:
        graph_file_value = str(graph_file_id or "").strip()
        file_hash_value = str(file_hash or "").strip() or None
        if not graph_file_value:
            return {"alerts": 0, "evidence": 0, "edges": 0, "nodes": 0, "graph_versions": 0}

        if not self._pool:
            async with self._lock:
                target_node_ids = {
                    node_id
                    for node_id, row in self._nodes_by_id.items()
                    if str(row.get("tenant_id") or "") == tenant_id
                    and str(row.get("graph_file_id") or "") == graph_file_value
                }
                target_doc_ids = {
                    str(row.get("doc_id") or "")
                    for row in self._documents.values()
                    if str(row.get("tenant_id") or "") == tenant_id
                    and (not file_hash_value or str(row.get("file_hash") or "") == file_hash_value)
                }

                removed_alert_ids: List[str] = []
                for alert_id, row in list(self._alerts.items()):
                    if str(row.get("tenant_id") or "") != tenant_id:
                        continue
                    subject_node_id = str(row.get("subject_node_id") or "").strip()
                    payload_hash = _payload_file_hash(row.get("payload"))
                    if subject_node_id in target_node_ids or (file_hash_value and payload_hash == file_hash_value):
                        removed_alert_ids.append(alert_id)
                        removed = self._alerts.pop(alert_id, None)
                        if removed and removed.get("alert_key"):
                            self._alerts_by_key.pop((tenant_id, str(removed.get("alert_key"))), None)

                removed_evidence_ids: List[str] = []
                for evidence_id, row in list(self._evidence.items()):
                    if str(row.get("tenant_id") or "") != tenant_id:
                        continue
                    if str(row.get("doc_id") or "") not in target_doc_ids:
                        continue
                    removed_evidence_ids.append(evidence_id)
                    removed = self._evidence.pop(evidence_id, None)
                    if removed and removed.get("evidence_key"):
                        self._evidence_by_key.pop((tenant_id, str(removed.get("evidence_key"))), None)

                removed_edge_ids: List[str] = []
                for edge_id, row in list(self._edges_by_id.items()):
                    if str(row.get("tenant_id") or "") != tenant_id:
                        continue
                    if str(row.get("graph_file_id") or "") != graph_file_value:
                        continue
                    removed_edge_ids.append(edge_id)
                    removed = self._edges_by_id.pop(edge_id, None)
                    if removed:
                        key = (
                            tenant_id,
                            _graph_scope_key(str(removed.get("graph_file_id") or "").strip() or None),
                            str(removed.get("source_node_id") or ""),
                            str(removed.get("target_node_id") or ""),
                            str(removed.get("relation_type") or ""),
                        )
                        self._edges.pop(key, None)

                removed_node_ids: List[str] = []
                for node_id, row in list(self._nodes_by_id.items()):
                    if str(row.get("tenant_id") or "") != tenant_id:
                        continue
                    if str(row.get("graph_file_id") or "") != graph_file_value:
                        continue
                    removed_node_ids.append(node_id)
                    removed = self._nodes_by_id.pop(node_id, None)
                    if removed:
                        key = (
                            tenant_id,
                            _graph_scope_key(str(removed.get("graph_file_id") or "").strip() or None),
                            str(removed.get("node_type") or ""),
                            str(removed.get("canonical_key") or ""),
                        )
                        self._nodes.pop(key, None)

                removed_graph_version_ids: List[str] = []
                for graph_version_id, row in list(self._graph_versions.items()):
                    if str(row.get("tenant_id") or "") != tenant_id:
                        continue
                    if str(row.get("graph_file_id") or "") != graph_file_value:
                        continue
                    removed_graph_version_ids.append(graph_version_id)
                    self._graph_versions.pop(graph_version_id, None)

                removed_edge_id_set = set(removed_edge_ids)
                removed_evidence_id_set = set(removed_evidence_ids)
                self._edge_evidence = {
                    key: value
                    for key, value in self._edge_evidence.items()
                    if key[0] not in removed_edge_id_set and key[1] not in removed_evidence_id_set
                }

                graph_file_row = self._graph_files.get(graph_file_value)
                if graph_file_row:
                    graph_file_row["active_version_id"] = None
                    graph_file_row["node_count"] = 0
                    graph_file_row["edge_count"] = 0
                    graph_file_row["updated_at"] = _now()

                return {
                    "alerts": len(removed_alert_ids),
                    "evidence": len(removed_evidence_ids),
                    "edges": len(removed_edge_ids),
                    "nodes": len(removed_node_ids),
                    "graph_versions": len(removed_graph_version_ids),
                }

        async def _execute(conn_obj: Any) -> Dict[str, int]:
            alert_rows = await conn_obj.fetch(
                """
                DELETE FROM module4.alerts
                WHERE tenant_id = $1
                  AND (
                    subject_node_id IN (
                        SELECT node_id
                        FROM module4.nodes
                        WHERE tenant_id = $1
                          AND graph_file_id = $2::uuid
                    )
                    OR (
                        $3::text IS NOT NULL
                        AND COALESCE(payload->'context'->>'file_hash', payload->>'file_hash') = $3
                    )
                  )
                RETURNING alert_id
                """,
                tenant_id,
                graph_file_value,
                file_hash_value,
            )
            evidence_rows = await conn_obj.fetch(
                """
                DELETE FROM module4.evidence
                WHERE tenant_id = $1
                  AND doc_id IN (
                    SELECT doc_id
                    FROM module4.documents
                    WHERE tenant_id = $1
                      AND ($2::text IS NULL OR file_hash = $2)
                  )
                RETURNING evidence_id
                """,
                tenant_id,
                file_hash_value,
            )
            edge_rows = await conn_obj.fetch(
                """
                DELETE FROM module4.edges
                WHERE tenant_id = $1
                  AND graph_file_id = $2::uuid
                RETURNING edge_id
                """,
                tenant_id,
                graph_file_value,
            )
            node_rows = await conn_obj.fetch(
                """
                DELETE FROM module4.nodes
                WHERE tenant_id = $1
                  AND graph_file_id = $2::uuid
                RETURNING node_id
                """,
                tenant_id,
                graph_file_value,
            )
            graph_version_rows = await conn_obj.fetch(
                """
                DELETE FROM module4.graph_versions
                WHERE tenant_id = $1
                  AND graph_file_id = $2::uuid
                RETURNING graph_version_id
                """,
                tenant_id,
                graph_file_value,
            )
            await conn_obj.execute(
                """
                UPDATE module4.graph_files
                SET active_version_id = NULL,
                    node_count = 0,
                    edge_count = 0,
                    updated_at = NOW()
                WHERE tenant_id = $1
                  AND graph_file_id = $2::uuid
                """,
                tenant_id,
                graph_file_value,
            )
            return {
                "alerts": len(alert_rows),
                "evidence": len(evidence_rows),
                "edges": len(edge_rows),
                "nodes": len(node_rows),
                "graph_versions": len(graph_version_rows),
            }

        if conn is not None:
            return await _execute(conn)
        async with self.transaction() as acquired:
            return await _execute(acquired)

    async def delete_tenant_graph_data(self, *, tenant_id: str) -> Dict[str, int]:
        if not self._pool:
            alert_ids = [alert_id for alert_id, row in self._alerts.items() if row.get("tenant_id") == tenant_id]
            evidence_ids = [evidence_id for evidence_id, row in self._evidence.items() if row.get("tenant_id") == tenant_id]
            edge_ids = [edge_id for edge_id, row in self._edges_by_id.items() if row.get("tenant_id") == tenant_id]
            node_ids = [node_id for node_id, row in self._nodes_by_id.items() if row.get("tenant_id") == tenant_id]
            doc_keys = [key for key, row in self._documents.items() if row.get("tenant_id") == tenant_id]
            graph_file_ids = [graph_file_id for graph_file_id, row in self._graph_files.items() if row.get("tenant_id") == tenant_id]
            graph_version_ids = [
                graph_version_id
                for graph_version_id, row in self._graph_versions.items()
                if row.get("tenant_id") == tenant_id
            ]

            for alert_id in alert_ids:
                row = self._alerts.pop(alert_id, None)
                if row and row.get("alert_key"):
                    self._alerts_by_key.pop((tenant_id, str(row.get("alert_key"))), None)

            for evidence_id in evidence_ids:
                row = self._evidence.pop(evidence_id, None)
                if row and row.get("evidence_key"):
                    self._evidence_by_key.pop((tenant_id, str(row.get("evidence_key"))), None)

            for edge_id in edge_ids:
                row = self._edges_by_id.pop(edge_id, None)
                if row:
                    key = (
                        tenant_id,
                        str(row.get("source_node_id")),
                        str(row.get("target_node_id")),
                        str(row.get("relation_type")),
                    )
                    self._edges.pop(key, None)

            for node_id in node_ids:
                row = self._nodes_by_id.pop(node_id, None)
                if row:
                    key = (tenant_id, str(row.get("node_type")), str(row.get("canonical_key")))
                    self._nodes.pop(key, None)

            for key in doc_keys:
                self._documents.pop(key, None)

            for graph_file_id in graph_file_ids:
                row = self._graph_files.pop(graph_file_id, None)
                if row:
                    self._graph_file_by_key.pop((tenant_id, str(row.get("file_hash") or "")), None)

            for graph_version_id in graph_version_ids:
                self._graph_versions.pop(graph_version_id, None)

            self._edge_evidence = {
                key: value
                for key, value in self._edge_evidence.items()
                if key[0] not in set(edge_ids) and key[1] not in set(evidence_ids)
            }

            return {
                "alerts": len(alert_ids),
                "evidence": len(evidence_ids),
                "edges": len(edge_ids),
                "nodes": len(node_ids),
                "documents": len(doc_keys),
                "graph_files": len(graph_file_ids),
                "graph_versions": len(graph_version_ids),
            }

        statements = {
            "alerts": "DELETE FROM module4.alerts WHERE tenant_id = $1",
            "evidence": "DELETE FROM module4.evidence WHERE tenant_id = $1",
            "edges": "DELETE FROM module4.edges WHERE tenant_id = $1",
            "nodes": "DELETE FROM module4.nodes WHERE tenant_id = $1",
            "documents": "DELETE FROM module4.documents WHERE tenant_id = $1",
            "graph_versions": "DELETE FROM module4.graph_versions WHERE tenant_id = $1",
            "graph_files": "DELETE FROM module4.graph_files WHERE tenant_id = $1",
        }
        counts: Dict[str, int] = {}
        async with self.transaction() as conn:
            for key, sql in statements.items():
                result = await conn.execute(sql, tenant_id)
                counts[key] = int(str(result).split()[-1])
        return counts

    async def insert_alert(
        self,
        *,
        tenant_id: str,
        rule_id: str,
        severity: str,
        subject_node_id: Optional[str],
        title: str,
        summary: str,
        risk_score: float,
        payload: Dict[str, Any],
        conn: Optional[Any] = None,
    ) -> Dict[str, Any]:
        severity = severity if severity in {"yellow", "orange", "red"} else "yellow"
        payload = _to_plain(payload)
        risk_score = _safe_float(risk_score, 0.0)
        alert_key = _fingerprint(tenant_id, rule_id, subject_node_id, title, summary, payload.get("context", payload))

        if not self._pool:
            async with self._lock:
                existing_id = self._alerts_by_key.get((tenant_id, alert_key))
                if existing_id and existing_id in self._alerts:
                    now = _now()
                    row = self._alerts[existing_id]
                    row.update(
                        {
                            "severity": severity,
                            "status": "open",
                            "subject_node_id": subject_node_id,
                            "title": title,
                            "summary": summary,
                            "risk_score": risk_score,
                            "payload": payload,
                            "alert_key": alert_key,
                            "detected_at": now,
                            "acknowledged_at": None,
                            "resolved_at": None,
                            "updated_at": now,
                        }
                    )
                    return dict(row)
                now = _now()
                alert_id = str(uuid.uuid4())
                row = {
                    "alert_id": alert_id,
                    "tenant_id": tenant_id,
                    "alert_key": alert_key,
                    "rule_id": rule_id,
                    "severity": severity,
                    "status": "open",
                    "subject_node_id": subject_node_id,
                    "title": title,
                    "summary": summary,
                    "risk_score": risk_score,
                    "payload": payload,
                    "detected_at": now,
                    "acknowledged_at": None,
                    "resolved_at": None,
                    "created_at": now,
                    "updated_at": now,
                }
                self._alerts[alert_id] = row
                self._alerts_by_key[(tenant_id, alert_key)] = alert_id
                return dict(row)

        sql = """
            INSERT INTO module4.alerts (
                tenant_id, alert_key, rule_id, severity, status, subject_node_id, title, summary, risk_score, payload
            )
            VALUES ($1, $2, $3, $4, 'open', $5, $6, $7, $8, $9::jsonb)
            ON CONFLICT (tenant_id, alert_key) WHERE alert_key IS NOT NULL
            DO UPDATE SET
                rule_id = EXCLUDED.rule_id,
                severity = EXCLUDED.severity,
                status = 'open',
                subject_node_id = EXCLUDED.subject_node_id,
                title = EXCLUDED.title,
                summary = EXCLUDED.summary,
                risk_score = EXCLUDED.risk_score,
                payload = EXCLUDED.payload,
                detected_at = NOW(),
                acknowledged_at = NULL,
                resolved_at = NULL,
                updated_at = NOW()
            RETURNING *
        """
        if conn is not None:
            existing = await conn.fetchrow(
                "SELECT alert_id, status FROM module4.alerts WHERE tenant_id = $1 AND alert_key = $2",
                tenant_id,
                alert_key,
            )
            row = await conn.fetchrow(
                sql,
                tenant_id,
                alert_key,
                rule_id,
                severity,
                subject_node_id,
                title,
                summary,
                risk_score,
                payload,
            )
            if not existing:
                await conn.execute(
                    "INSERT INTO module4.alert_events (alert_id, action, actor, detail) VALUES ($1, 'created', 'system', $2::jsonb)",
                    row["alert_id"],
                    {"rule_id": rule_id},
                )
            elif str(existing["status"] or "").lower() != "open":
                await conn.execute(
                    "INSERT INTO module4.alert_events (alert_id, action, actor, detail) VALUES ($1, 'reopened', 'system', $2::jsonb)",
                    row["alert_id"],
                    {"rule_id": rule_id},
                )
        else:
            async with self._pool.acquire() as acquired:
                existing = await acquired.fetchrow(
                    "SELECT alert_id, status FROM module4.alerts WHERE tenant_id = $1 AND alert_key = $2",
                    tenant_id,
                    alert_key,
                )
                row = await acquired.fetchrow(
                    sql,
                    tenant_id,
                    alert_key,
                    rule_id,
                    severity,
                    subject_node_id,
                    title,
                    summary,
                    risk_score,
                    payload,
                )
                if not existing:
                    await acquired.execute(
                        "INSERT INTO module4.alert_events (alert_id, action, actor, detail) VALUES ($1, 'created', 'system', $2::jsonb)",
                        row["alert_id"],
                        {"rule_id": rule_id},
                    )
                elif str(existing["status"] or "").lower() != "open":
                    await acquired.execute(
                        "INSERT INTO module4.alert_events (alert_id, action, actor, detail) VALUES ($1, 'reopened', 'system', $2::jsonb)",
                        row["alert_id"],
                        {"rule_id": rule_id},
                    )
        return _to_plain(dict(row))

    async def get_alert(self, alert_id: str, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        alert_id = str(alert_id).strip()
        if not self._pool:
            item = self._alerts.get(alert_id)
            if not item:
                return None
            if tenant_id and str(item.get("tenant_id")) != str(tenant_id):
                return None
            return dict(item)
        async with self._pool.acquire() as conn:
            if tenant_id:
                row = await conn.fetchrow(
                    "SELECT * FROM module4.alerts WHERE alert_id = $1 AND tenant_id = $2",
                    alert_id,
                    tenant_id,
                )
            else:
                row = await conn.fetchrow("SELECT * FROM module4.alerts WHERE alert_id = $1", alert_id)
        return _to_plain(dict(row)) if row else None

    async def update_alert_status(
        self,
        *,
        alert_id: str,
        tenant_id: Optional[str],
        status: str,
        actor: str,
        comment: str,
        resolution: str = "",
    ) -> Optional[Dict[str, Any]]:
        status = status if status in {"open", "ack", "resolved", "false_positive"} else "open"
        alert_id = str(alert_id).strip()
        if not self._pool:
            async with self._lock:
                item = self._alerts.get(alert_id)
                if not item:
                    return None
                if tenant_id and str(item.get("tenant_id")) != str(tenant_id):
                    return None
                now = _now()
                item["status"] = status
                item["updated_at"] = now
                if status == "ack":
                    item["acknowledged_at"] = now
                if status in {"resolved", "false_positive"}:
                    item["resolved_at"] = now
                return dict(item)

        sql = """
            UPDATE module4.alerts
            SET status = $1,
                acknowledged_at = CASE WHEN $1 = 'ack' THEN NOW() ELSE acknowledged_at END,
                resolved_at = CASE WHEN $1 IN ('resolved', 'false_positive') THEN NOW() ELSE resolved_at END,
                updated_at = NOW()
            WHERE alert_id = $2 AND ($3::text IS NULL OR tenant_id = $3)
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, status, alert_id, tenant_id)
            if not row:
                return None
            action = "ack" if status == "ack" else ("resolved" if status == "resolved" else "false_positive")
            await conn.execute(
                "INSERT INTO module4.alert_events (alert_id, action, actor, detail) VALUES ($1, $2, $3, $4::jsonb)",
                alert_id,
                action,
                actor or "user",
                {"comment": comment, "resolution": resolution},
            )
        return _to_plain(dict(row))

    async def list_alerts(
        self,
        *,
        tenant_id: str,
        status: Optional[str],
        severity: Optional[str],
        rule_id: Optional[str],
        page: int,
        page_size: int,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        page = max(1, int(page))
        page_size = max(1, min(200, int(page_size)))
        offset = (page - 1) * page_size

        if not self._pool:
            items = [dict(v) for v in self._alerts.values() if v.get("tenant_id") == tenant_id]
            if status:
                items = [v for v in items if v.get("status") == status]
            if severity:
                items = [v for v in items if v.get("severity") == severity]
            if rule_id:
                items = [v for v in items if v.get("rule_id") == rule_id]
            items.sort(key=lambda x: x.get("detected_at") or _now(), reverse=True)
            return len(items), items[offset : offset + page_size]

        clauses = ["tenant_id = $1"]
        params: List[Any] = [tenant_id]
        idx = 2
        if status:
            clauses.append(f"status = ${idx}")
            params.append(status)
            idx += 1
        if severity:
            clauses.append(f"severity = ${idx}")
            params.append(severity)
            idx += 1
        if rule_id:
            clauses.append(f"rule_id = ${idx}")
            params.append(rule_id)
            idx += 1
        where_sql = " AND ".join(clauses)
        sql_count = f"SELECT COUNT(1) FROM module4.alerts WHERE {where_sql}"
        sql_items = (
            f"SELECT * FROM module4.alerts WHERE {where_sql} "
            f"ORDER BY detected_at DESC LIMIT ${idx} OFFSET ${idx + 1}"
        )
        params_items = params + [page_size, offset]
        async with self._pool.acquire() as conn:
            total = int(await conn.fetchval(sql_count, *params) or 0)
            rows = await conn.fetch(sql_items, *params_items)
        return total, [_to_plain(dict(r)) for r in rows]

    async def list_evidence(
        self,
        *,
        tenant_id: str,
        doc_id: Optional[str],
        object_type: Optional[str],
        object_id: Optional[str],
        page: int,
        page_size: int,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        page = max(1, int(page))
        page_size = max(1, min(500, int(page_size)))
        offset = (page - 1) * page_size

        if not self._pool:
            items = [dict(v) for v in self._evidence.values() if v.get("tenant_id") == tenant_id]
            if doc_id:
                items = [v for v in items if str(v.get("doc_id")) == str(doc_id)]
            if object_type:
                items = [v for v in items if str(v.get("object_type")) == str(object_type)]
            if object_id:
                items = [v for v in items if str(v.get("object_id")) == str(object_id)]
            items.sort(key=lambda x: x.get("created_at") or _now(), reverse=True)
            return len(items), items[offset : offset + page_size]

        clauses = ["tenant_id = $1"]
        params: List[Any] = [tenant_id]
        idx = 2
        if doc_id:
            clauses.append(f"doc_id = ${idx}")
            params.append(doc_id)
            idx += 1
        if object_type:
            clauses.append(f"object_type = ${idx}")
            params.append(object_type)
            idx += 1
        if object_id:
            clauses.append(f"object_id = ${idx}")
            params.append(object_id)
            idx += 1
        where_sql = " AND ".join(clauses)
        sql_count = f"SELECT COUNT(1) FROM module4.evidence WHERE {where_sql}"
        sql_items = (
            f"SELECT * FROM module4.evidence WHERE {where_sql} "
            f"ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}"
        )
        params_items = params + [page_size, offset]
        async with self._pool.acquire() as conn:
            total = int(await conn.fetchval(sql_count, *params) or 0)
            rows = await conn.fetch(sql_items, *params_items)
        return total, [_to_plain(dict(r)) for r in rows]

    async def list_edge_evidence(
        self,
        *,
        tenant_id: str,
        edge_id: str,
        page: int,
        page_size: int,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        page = max(1, int(page))
        page_size = max(1, min(500, int(page_size)))
        offset = (page - 1) * page_size

        if not self._pool:
            edge = self._edges_by_id.get(str(edge_id))
            if not edge or str(edge.get("tenant_id")) != tenant_id:
                return 0, []
            evidence_ids = [ev_id for e_id, ev_id in self._edge_evidence.keys() if str(e_id) == str(edge_id)]
            items = [dict(self._evidence[ev_id]) for ev_id in evidence_ids if ev_id in self._evidence]
            items.sort(key=lambda x: x.get("created_at") or _now(), reverse=True)
            return len(items), items[offset : offset + page_size]

        sql_count = """
            SELECT COUNT(1)
            FROM module4.edge_evidence ee
            JOIN module4.edges edge ON edge.edge_id = ee.edge_id
            JOIN module4.evidence ev ON ev.evidence_id = ee.evidence_id
            WHERE ee.edge_id = $1 AND edge.tenant_id = $2 AND ev.tenant_id = $2
        """
        sql_items = """
            SELECT ev.*
            FROM module4.edge_evidence ee
            JOIN module4.edges edge ON edge.edge_id = ee.edge_id
            JOIN module4.evidence ev ON ev.evidence_id = ee.evidence_id
            WHERE ee.edge_id = $1 AND edge.tenant_id = $2 AND ev.tenant_id = $2
            ORDER BY ev.created_at DESC
            LIMIT $3 OFFSET $4
        """
        async with self._pool.acquire() as conn:
            total = int(await conn.fetchval(sql_count, edge_id, tenant_id) or 0)
            rows = await conn.fetch(sql_items, edge_id, tenant_id, page_size, offset)
        return total, [_to_plain(dict(r)) for r in rows]

    async def list_nodes_by_graph_file(
        self,
        *,
        tenant_id: str,
        graph_file_id: str,
        node_types: Optional[Sequence[str]] = None,
        limit: int = 5000,
    ) -> List[Dict[str, Any]]:
        graph_file_value = str(graph_file_id or "").strip()
        if not graph_file_value:
            return []
        normalized_node_types = [str(value).strip() for value in (node_types or []) if str(value).strip()]
        limit_value = max(1, min(50000, int(limit)))

        if not self._pool:
            items: List[Dict[str, Any]] = []
            for row in self._nodes_by_id.values():
                if str(row.get("tenant_id") or "") != tenant_id:
                    continue
                if str(row.get("graph_file_id") or "") != graph_file_value:
                    continue
                if normalized_node_types and str(row.get("node_type") or "") not in normalized_node_types:
                    continue
                items.append(dict(row))
            items.sort(
                key=lambda item: (
                    str(item.get("updated_at") or ""),
                    str(item.get("created_at") or ""),
                    str(item.get("node_id") or ""),
                ),
                reverse=True,
            )
            return items[:limit_value]

        clauses = ["tenant_id = $1", "graph_file_id = $2::uuid"]
        params: List[Any] = [tenant_id, graph_file_value]
        idx = 3
        if normalized_node_types:
            clauses.append(f"node_type = ANY(${idx}::text[])")
            params.append(normalized_node_types)
            idx += 1
        sql = (
            f"SELECT * FROM module4.nodes WHERE {' AND '.join(clauses)} "
            f"ORDER BY updated_at DESC, created_at DESC, node_id DESC LIMIT ${idx}"
        )
        params.append(limit_value)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [_to_plain(dict(row)) for row in rows]

    async def list_edges_by_graph_file(
        self,
        *,
        tenant_id: str,
        graph_file_id: str,
        relation_types: Optional[Sequence[str]] = None,
        node_ids: Optional[Sequence[str]] = None,
        limit: int = 10000,
    ) -> List[Dict[str, Any]]:
        graph_file_value = str(graph_file_id or "").strip()
        if not graph_file_value:
            return []
        normalized_relation_types = [
            str(value).strip() for value in (relation_types or []) if str(value).strip()
        ]
        normalized_node_ids = [str(value).strip() for value in (node_ids or []) if str(value).strip()]
        node_id_set = set(normalized_node_ids)
        limit_value = max(1, min(100000, int(limit)))

        if not self._pool:
            items: List[Dict[str, Any]] = []
            for row in self._edges_by_id.values():
                if str(row.get("tenant_id") or "") != tenant_id:
                    continue
                if str(row.get("graph_file_id") or "") != graph_file_value:
                    continue
                if normalized_relation_types and str(row.get("relation_type") or "") not in normalized_relation_types:
                    continue
                source_node_id = str(row.get("source_node_id") or "")
                target_node_id = str(row.get("target_node_id") or "")
                if node_id_set and (source_node_id not in node_id_set or target_node_id not in node_id_set):
                    continue
                items.append(dict(row))
            items.sort(
                key=lambda item: (
                    str(item.get("updated_at") or ""),
                    str(item.get("created_at") or ""),
                    str(item.get("edge_id") or ""),
                ),
                reverse=True,
            )
            return items[:limit_value]

        clauses = ["tenant_id = $1", "graph_file_id = $2::uuid"]
        params: List[Any] = [tenant_id, graph_file_value]
        idx = 3
        if normalized_relation_types:
            clauses.append(f"relation_type = ANY(${idx}::text[])")
            params.append(normalized_relation_types)
            idx += 1
        if normalized_node_ids:
            clauses.append(f"source_node_id::text = ANY(${idx}::text[])")
            clauses.append(f"target_node_id::text = ANY(${idx}::text[])")
            params.append(normalized_node_ids)
            idx += 1
        sql = (
            f"SELECT * FROM module4.edges WHERE {' AND '.join(clauses)} "
            f"ORDER BY updated_at DESC, created_at DESC, edge_id DESC LIMIT ${idx}"
        )
        params.append(limit_value)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
        return [_to_plain(dict(row)) for row in rows]

    async def get_node(self, *, tenant_id: str, node_id: str) -> Optional[Dict[str, Any]]:
        node_id = str(node_id).strip()
        if not node_id:
            return None

        if not self._pool:
            row = self._nodes_by_id.get(node_id)
            if not row or str(row.get("tenant_id")) != tenant_id:
                return None
            return dict(row)

        sql = "SELECT * FROM module4.nodes WHERE tenant_id = $1 AND node_id::text = $2"
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, tenant_id, node_id)
        return _to_plain(dict(row)) if row else None
