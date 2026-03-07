from __future__ import annotations

import asyncio
import logging
import math
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


DEFAULT_RULES: Tuple[Dict[str, Any], ...] = (
    {
        "rule_id": "RULE_LOW_CONFIDENCE",
        "name": "Low Confidence Extraction",
        "severity": "yellow",
        "rule_kind": "deterministic",
        "expr": {
            "scope": "field",
            "path": "confidence",
            "op": "lt",
            "value": 0.55,
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
        self._edge_evidence: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self._alerts: Dict[str, Dict[str, Any]] = {}
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
        for rule in DEFAULT_RULES:
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

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        job_id = str(job_id).strip()
        if not self._pool:
            value = self._jobs.get(job_id)
            return dict(value) if value else None
        async with self._pool.acquire() as conn:
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
                        return dict(self._batches[existing])
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

    async def upsert_document(
        self,
        *,
        tenant_id: str,
        batch_id: str,
        file_name: str,
        file_hash: str,
        track: str,
        diagnostics: Dict[str, Any],
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
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, tenant_id, batch_id, file_name, file_hash, track, diagnostics)
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
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, tenant_id, node_type, canonical_key, display_name, attrs, confidence)
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
        async with self._pool.acquire() as conn:
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
    ) -> Dict[str, Any]:
        locator = _to_plain(locator)
        bbox_list = list(bbox or [])
        confidence = _safe_float(confidence, 0.0)

        if not self._pool:
            async with self._lock:
                evidence_id = str(uuid.uuid4())
                row = {
                    "evidence_id": evidence_id,
                    "tenant_id": tenant_id,
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
                return dict(row)

        sql = """
            INSERT INTO module4.evidence (
                tenant_id, doc_id, object_type, object_id, ref_id, page_no, snippet, locator, bbox, artifact_url, confidence
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::jsonb, $10, $11)
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                sql,
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
                confidence,
            )
        return _to_plain(dict(row))

    async def link_edge_evidence(self, *, edge_id: str, evidence_id: str) -> None:
        if not self._pool:
            async with self._lock:
                self._edge_evidence[(edge_id, evidence_id)] = {"edge_id": edge_id, "evidence_id": evidence_id}
            return
        sql = """
            INSERT INTO module4.edge_evidence (edge_id, evidence_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
        """
        async with self._pool.acquire() as conn:
            await conn.execute(sql, edge_id, evidence_id)

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
    ) -> Dict[str, Any]:
        severity = severity if severity in {"yellow", "orange", "red"} else "yellow"
        payload = _to_plain(payload)
        risk_score = _safe_float(risk_score, 0.0)

        if not self._pool:
            async with self._lock:
                now = _now()
                alert_id = str(uuid.uuid4())
                row = {
                    "alert_id": alert_id,
                    "tenant_id": tenant_id,
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
                return dict(row)

        sql = """
            INSERT INTO module4.alerts (
                tenant_id, rule_id, severity, status, subject_node_id, title, summary, risk_score, payload
            )
            VALUES ($1, $2, $3, 'open', $4, $5, $6, $7, $8::jsonb)
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                sql,
                tenant_id,
                rule_id,
                severity,
                subject_node_id,
                title,
                summary,
                risk_score,
                payload,
            )
            await conn.execute(
                "INSERT INTO module4.alert_events (alert_id, action, actor, detail) VALUES ($1, 'created', 'system', $2::jsonb)",
                row["alert_id"],
                {"rule_id": rule_id},
            )
        return _to_plain(dict(row))

    async def get_alert(self, alert_id: str) -> Optional[Dict[str, Any]]:
        alert_id = str(alert_id).strip()
        if not self._pool:
            item = self._alerts.get(alert_id)
            return dict(item) if item else None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM module4.alerts WHERE alert_id = $1", alert_id)
        return _to_plain(dict(row)) if row else None

    async def update_alert_status(
        self,
        *,
        alert_id: str,
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
            WHERE alert_id = $2
            RETURNING *
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(sql, status, alert_id)
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
            node_rows = await conn.fetch(
                "SELECT * FROM module4.nodes WHERE tenant_id = $1 ORDER BY updated_at DESC LIMIT $2",
                tenant_id,
                limit_nodes,
            )
            nodes = [_to_plain(dict(r)) for r in node_rows]
            if node_types_set:
                nodes = [n for n in nodes if n.get("node_type") in node_types_set]
            node_ids = {n["node_id"] for n in nodes}
            if not node_ids:
                return [], []
            edge_rows = await conn.fetch(
                "SELECT * FROM module4.edges WHERE tenant_id = $1 ORDER BY updated_at DESC LIMIT $2",
                tenant_id,
                max(limit_edges, 2000),
            )
            edges = [_to_plain(dict(r)) for r in edge_rows]
            edges = [e for e in edges if e.get("source_node_id") in node_ids and e.get("target_node_id") in node_ids]
            if relation_types_set:
                edges = [e for e in edges if e.get("relation_type") in relation_types_set]
            return nodes, edges[:limit_edges]
