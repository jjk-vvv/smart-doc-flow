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

logger = logging.getLogger(__name__)


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


class Module4Storage:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._pool: Optional[Any] = None
        self._degraded_memory_mode = False
        self._last_connect_error = ""
        self._lock = asyncio.Lock()

        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._batches: Dict[str, Dict[str, Any]] = {}
        self._batch_unique: Dict[Tuple[str, str, str], str] = {}
        self._documents: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._nodes: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        self._nodes_by_id: Dict[str, Dict[str, Any]] = {}
        self._edges: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
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
            self._pool = None
            self._degraded_memory_mode = True
            self._last_connect_error = "forced memory mode"
            await self.ensure_default_rules()
            return
        try:
            import asyncpg

            connect_timeout = _safe_float(os.getenv("MODULE4_DB_CONNECT_TIMEOUT_SEC", "3"), 3.0)
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=10, timeout=connect_timeout)
            await self._init_schema()
            self._degraded_memory_mode = False
            self._last_connect_error = ""
        except Exception as exc:
            self._pool = None
            self._degraded_memory_mode = True
            self._last_connect_error = f"{type(exc).__name__}: {exc}"
            logger.warning("module4 storage downgraded to memory mode: %s", self._last_connect_error)
        await self.ensure_default_rules()

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()

    def diagnostics(self) -> Dict[str, Any]:
        return {
            "db_connected": bool(self._pool is not None),
            "degraded_memory_mode": self._degraded_memory_mode,
            "last_connect_error": self._last_connect_error,
            "jobs_in_memory": len(self._jobs),
            "alerts_in_memory": len(self._alerts),
            "nodes_in_memory": len(self._nodes),
            "edges_in_memory": len(self._edges),
        }

    async def _init_schema(self) -> None:
        if not self._pool:
            return
        init_path = Path(__file__).resolve().parents[2] / "sql" / "init.sql"
        sql = init_path.read_text(encoding="utf-8")
        async with self._pool.acquire() as conn:
            await conn.execute(sql)

    async def ensure_default_rules(self) -> None:
        existing = await self.list_rules()
        existing_ids = {str(item.get("rule_id")) for item in existing}
        for rule in _build_default_rules():
            if str(rule["rule_id"]) in existing_ids:
                continue
            await self.upsert_rule(**rule)

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
        node_type: str,
        canonical_key: str,
        display_name: str,
        attrs: Dict[str, Any],
        confidence: float,
        conn: Optional[Any] = None,
    ) -> Dict[str, Any]:
        attrs = _to_plain(attrs)
        confidence = _safe_float(confidence, 0.0)
        canonical_key = (canonical_key or "").strip() or str(uuid.uuid4())
        display_name = (display_name or "").strip() or canonical_key

        if not self._pool:
            async with self._lock:
                key = (tenant_id, node_type, canonical_key)
                now = _now()
                row = self._nodes.get(key)
                if row:
                    row.update(
                        {
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

        sql = """
            INSERT INTO module4.nodes (tenant_id, node_type, canonical_key, display_name, attrs, confidence)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6)
            ON CONFLICT (tenant_id, node_type, canonical_key)
            DO UPDATE SET
                display_name = EXCLUDED.display_name,
                attrs = EXCLUDED.attrs,
                confidence = EXCLUDED.confidence,
                last_seen_at = NOW(),
                updated_at = NOW()
            RETURNING *
        """
        if conn is not None:
            row = await conn.fetchrow(sql, tenant_id, node_type, canonical_key, display_name, attrs, confidence)
        else:
            async with self._pool.acquire() as acquired:
                row = await acquired.fetchrow(sql, tenant_id, node_type, canonical_key, display_name, attrs, confidence)
        return _to_plain(dict(row))

    async def upsert_edge(
        self,
        *,
        tenant_id: str,
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
        direction = direction if direction in {"out", "bi"} else "out"

        if not self._pool:
            async with self._lock:
                key = (tenant_id, str(source_node_id), str(target_node_id), relation_type)
                now = _now()
                row = self._edges.get(key)
                if row:
                    row.update(
                        {
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

        sql = """
            INSERT INTO module4.edges (
                tenant_id, source_node_id, target_node_id, relation_type, direction, attrs, confidence, risk_score
            )
            VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7, $8)
            ON CONFLICT (tenant_id, source_node_id, target_node_id, relation_type)
            DO UPDATE SET
                direction = EXCLUDED.direction,
                attrs = EXCLUDED.attrs,
                confidence = EXCLUDED.confidence,
                risk_score = EXCLUDED.risk_score,
                last_seen_at = NOW(),
                updated_at = NOW()
            RETURNING *
        """
        if conn is not None:
            row = await conn.fetchrow(
                sql,
                tenant_id,
                source_node_id,
                target_node_id,
                relation_type,
                direction,
                attrs,
                confidence,
                risk_score,
            )
        else:
            async with self._pool.acquire() as acquired:
                row = await acquired.fetchrow(
                    sql,
                    tenant_id,
                    source_node_id,
                    target_node_id,
                    relation_type,
                    direction,
                    attrs,
                    confidence,
                    risk_score,
                )
        return _to_plain(dict(row))

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
            ON CONFLICT (tenant_id, evidence_key)
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
        rule_id: str,
        name: str,
        severity: str,
        rule_kind: str,
        expr: Dict[str, Any],
        enabled: bool = True,
        version: int = 1,
    ) -> Dict[str, Any]:
        severity = severity if severity in {"yellow", "orange", "red"} else "yellow"
        rule_kind = rule_kind if rule_kind in {"deterministic", "semantic", "anomaly"} else "deterministic"
        expr = _to_plain(expr)

        if not self._pool:
            async with self._lock:
                now = _now()
                row = {
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
                self._rules[rule_id] = row
                return dict(row)

        sql = """
            INSERT INTO module4.rules (rule_id, name, severity, rule_kind, expr, enabled, version)
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
            ON CONFLICT (rule_id)
            DO UPDATE SET
                name = EXCLUDED.name,
                severity = EXCLUDED.severity,
                rule_kind = EXCLUDED.rule_kind,
                expr = EXCLUDED.expr,
                enabled = EXCLUDED.enabled,
                version = EXCLUDED.version,
                updated_at = NOW()
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, rule_id, name, severity, rule_kind, expr, enabled, int(version))
        return _to_plain(dict(row))

    async def list_rules(self, *, enabled_only: bool = False) -> List[Dict[str, Any]]:
        if not self._pool:
            items = list(self._rules.values())
            if enabled_only:
                items = [item for item in items if bool(item.get("enabled"))]
            items.sort(key=lambda x: str(x.get("rule_id", "")))
            return [dict(v) for v in items]
        where_sql = "WHERE enabled = true" if enabled_only else ""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(f"SELECT * FROM module4.rules {where_sql} ORDER BY rule_id ASC")
        return [_to_plain(dict(r)) for r in rows]

    async def delete_tenant_graph_data(self, *, tenant_id: str) -> Dict[str, int]:
        if not self._pool:
            alert_ids = [alert_id for alert_id, row in self._alerts.items() if row.get("tenant_id") == tenant_id]
            evidence_ids = [evidence_id for evidence_id, row in self._evidence.items() if row.get("tenant_id") == tenant_id]
            edge_ids = [edge_id for edge_id, row in self._edges_by_id.items() if row.get("tenant_id") == tenant_id]
            node_ids = [node_id for node_id, row in self._nodes_by_id.items() if row.get("tenant_id") == tenant_id]
            doc_keys = [key for key, row in self._documents.items() if row.get("tenant_id") == tenant_id]

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
            }

        statements = {
            "alerts": "DELETE FROM module4.alerts WHERE tenant_id = $1",
            "evidence": "DELETE FROM module4.evidence WHERE tenant_id = $1",
            "edges": "DELETE FROM module4.edges WHERE tenant_id = $1",
            "nodes": "DELETE FROM module4.nodes WHERE tenant_id = $1",
            "documents": "DELETE FROM module4.documents WHERE tenant_id = $1",
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
            ON CONFLICT (tenant_id, alert_key)
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

    async def list_neighborhood(
        self,
        *,
        tenant_id: str,
        node_id: str,
        depth: int,
        relation_types: Optional[Iterable[str]],
        limit: int,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        relation_types_set = {str(x) for x in (relation_types or []) if str(x).strip()}
        depth = max(1, min(4, int(depth)))
        limit = max(20, min(5000, int(limit)))

        root = await self.get_node(tenant_id=tenant_id, node_id=node_id)
        if not root:
            return [], []

        if not self._pool:
            visited = {str(node_id)}
            frontier = {str(node_id)}
            selected_edges: Dict[str, Dict[str, Any]] = {}
            all_edges = [dict(v) for v in self._edges_by_id.values() if v.get("tenant_id") == tenant_id]
            if relation_types_set:
                all_edges = [edge for edge in all_edges if edge.get("relation_type") in relation_types_set]
            all_edges.sort(key=lambda x: x.get("updated_at") or _now(), reverse=True)
            for _ in range(depth):
                if not frontier or len(visited) >= limit:
                    break
                next_frontier = set()
                for edge in all_edges:
                    src = str(edge.get("source_node_id") or "")
                    tgt = str(edge.get("target_node_id") or "")
                    if src not in frontier and tgt not in frontier:
                        continue
                    selected_edges[str(edge.get("edge_id"))] = edge
                    for candidate in (src, tgt):
                        if candidate and candidate not in visited and len(visited) < limit:
                            visited.add(candidate)
                            next_frontier.add(candidate)
                frontier = next_frontier
            nodes = [dict(self._nodes_by_id[nid]) for nid in visited if nid in self._nodes_by_id]
            nodes.sort(key=lambda x: x.get("updated_at") or _now(), reverse=True)
            edges = list(selected_edges.values())
            edges.sort(key=lambda x: x.get("updated_at") or _now(), reverse=True)
            return nodes[:limit], edges[: limit * 2]

        visited = {str(node_id)}
        frontier = {str(node_id)}
        selected_edges: Dict[str, Dict[str, Any]] = {}
        async with self._pool.acquire() as conn:
            for _ in range(depth):
                if not frontier or len(visited) >= limit:
                    break
                frontier_list = list(frontier)
                next_frontier = set()
                if relation_types_set:
                    rows = await conn.fetch(
                        """
                        SELECT *
                        FROM module4.edges
                        WHERE tenant_id = $1
                          AND relation_type = ANY($2::text[])
                          AND (
                            source_node_id::text = ANY($3::text[])
                            OR target_node_id::text = ANY($3::text[])
                          )
                        ORDER BY updated_at DESC
                        LIMIT $4
                        """,
                        tenant_id,
                        list(relation_types_set),
                        frontier_list,
                        max(limit * 3, 200),
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT *
                        FROM module4.edges
                        WHERE tenant_id = $1
                          AND (
                            source_node_id::text = ANY($2::text[])
                            OR target_node_id::text = ANY($2::text[])
                          )
                        ORDER BY updated_at DESC
                        LIMIT $3
                        """,
                        tenant_id,
                        frontier_list,
                        max(limit * 3, 200),
                    )
                for row in rows:
                    edge = _to_plain(dict(row))
                    selected_edges[str(edge.get("edge_id"))] = edge
                    src = str(edge.get("source_node_id") or "")
                    tgt = str(edge.get("target_node_id") or "")
                    for candidate in (src, tgt):
                        if candidate and candidate not in visited and len(visited) < limit:
                            visited.add(candidate)
                            next_frontier.add(candidate)
                frontier = next_frontier

            node_rows = await conn.fetch(
                """
                SELECT *
                FROM module4.nodes
                WHERE tenant_id = $1 AND node_id::text = ANY($2::text[])
                ORDER BY updated_at DESC
                """,
                tenant_id,
                list(visited),
            )
        nodes = [_to_plain(dict(row)) for row in node_rows]
        edges = list(selected_edges.values())
        edges.sort(key=lambda x: x.get("updated_at") or _now(), reverse=True)
        return nodes[:limit], edges[: limit * 2]

    async def list_graph(
        self,
        *,
        tenant_id: str,
        node_types: Optional[Iterable[str]],
        relation_types: Optional[Iterable[str]],
        limit_nodes: int,
        limit_edges: int,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        node_types_set = {str(x) for x in (node_types or []) if str(x).strip()}
        relation_types_set = {str(x) for x in (relation_types or []) if str(x).strip()}
        limit_nodes = max(20, min(5000, int(limit_nodes)))
        limit_edges = max(20, min(10000, int(limit_edges)))

        if not self._pool:
            nodes = [dict(v) for v in self._nodes_by_id.values() if v.get("tenant_id") == tenant_id]
            if node_types_set:
                nodes = [n for n in nodes if n.get("node_type") in node_types_set]
            nodes.sort(key=lambda x: x.get("updated_at") or _now(), reverse=True)
            nodes = nodes[:limit_nodes]
            node_ids = {n["node_id"] for n in nodes}

            edges = [dict(v) for v in self._edges_by_id.values() if v.get("tenant_id") == tenant_id]
            edges = [e for e in edges if e.get("source_node_id") in node_ids and e.get("target_node_id") in node_ids]
            if relation_types_set:
                edges = [e for e in edges if e.get("relation_type") in relation_types_set]
            edges.sort(key=lambda x: x.get("updated_at") or _now(), reverse=True)
            edges = edges[:limit_edges]
            return nodes, edges

        async with self._pool.acquire() as conn:
            if node_types_set:
                node_rows = await conn.fetch(
                    """
                    SELECT *
                    FROM module4.nodes
                    WHERE tenant_id = $1 AND node_type = ANY($2::text[])
                    ORDER BY updated_at DESC
                    LIMIT $3
                    """,
                    tenant_id,
                    list(node_types_set),
                    limit_nodes,
                )
            else:
                node_rows = await conn.fetch(
                    "SELECT * FROM module4.nodes WHERE tenant_id = $1 ORDER BY updated_at DESC LIMIT $2",
                    tenant_id,
                    limit_nodes,
                )
            nodes = [_to_plain(dict(r)) for r in node_rows]
            node_ids = {n["node_id"] for n in nodes}
            if not node_ids:
                return [], []
            if relation_types_set:
                edge_rows = await conn.fetch(
                    """
                    SELECT *
                    FROM module4.edges
                    WHERE tenant_id = $1
                      AND relation_type = ANY($2::text[])
                    ORDER BY updated_at DESC
                    LIMIT $3
                    """,
                    tenant_id,
                    list(relation_types_set),
                    max(limit_edges, 2000),
                )
            else:
                edge_rows = await conn.fetch(
                    "SELECT * FROM module4.edges WHERE tenant_id = $1 ORDER BY updated_at DESC LIMIT $2",
                    tenant_id,
                    max(limit_edges, 2000),
                )
            edges = [_to_plain(dict(r)) for r in edge_rows]
            edges = [e for e in edges if e.get("source_node_id") in node_ids and e.get("target_node_id") in node_ids]
            return nodes, edges[:limit_edges]
