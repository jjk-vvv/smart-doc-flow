from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from string import Formatter
from typing import Any, Dict, List, Optional, Sequence

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from app.db.storage import Module4Storage
from app.schemas import (
    AlertActionRequest,
    AlertActionResponse,
    AlertItem,
    AlertListResponse,
    AlertResolveRequest,
    EvidenceItem,
    EvidenceListResponse,
    ExplainRequest,
    ExplainResponse,
    GraphEdge,
    GraphFileDetailResponse,
    GraphFileItem,
    GraphFileListResponse,
    GraphNode,
    GraphNodeDetailResponse,
    GraphResponse,
    GraphStats,
    HealthzResponse,
    IngestRequest,
    IngestResponse,
    JobResponse,
    RebuildRequest,
    RebuildResponse,
    RuleItem,
    RuleListResponse,
    RuleUpsertRequest,
    RuleUpsertResponse,
    SimulateRequest,
    SimulateResponse,
)
from app.services import (
    GraphRAGIndexError,
    GraphRAGIndexer,
    GraphRAGWorkspaceBuilder,
    Neo4jGraphProjector,
)

MODULE4_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=MODULE4_ROOT / ".env", override=False, interpolate=False)

SEVERITY_DEFAULT_RISK = {"yellow": 40.0, "orange": 70.0, "red": 90.0}
SUPPORTED_RULE_KINDS = {"deterministic"}
SUPPORTED_RULE_OPS = {
    "eq",
    "neq",
    "lt",
    "lte",
    "gt",
    "gte",
    "contains",
    "in",
    "exists",
    "not_exists",
    "non_empty",
    "is_empty",
}
ALERT_SEVERITY = {"yellow", "orange", "red"}
ALERT_STATUS = {"open", "ack", "resolved", "false_positive"}
EDGE_DIRECTION = {"out", "bi"}
RULE_KIND = {"deterministic"}
logger = logging.getLogger("uvicorn.error")


def _cors_origins() -> tuple[list[str], bool]:
    raw = os.getenv("MODULE4_CORS_ORIGINS", "http://localhost:3000,http://localhost:3002,http://localhost:5173")
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    allow_all = "*" in origins
    return origins or ["http://localhost:3000"], allow_all


def _default_tenant() -> str:
    return os.getenv("MODULE4_DEFAULT_TENANT", "default").strip() or "default"


def _tenant_from_request(request: Optional[Request], candidate: Optional[str] = None) -> str:
    if candidate and str(candidate).strip():
        return str(candidate).strip()
    if request is not None:
        header_value = str(request.headers.get("x-tenant-id") or "").strip()
        if header_value:
            return header_value
    return _default_tenant()


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_csv_list(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else default
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _risk_key(text: str) -> str:
    digest = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
    return digest[:16]


def _stable_json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set, dict, str)):
        return len(value) > 0
    return True


def _get_by_path(data: Any, path: str) -> Any:
    if not path:
        return data
    cur: Any = data
    for token in str(path).split("."):
        key = token.strip()
        if not key:
            continue
        if isinstance(cur, dict):
            cur = cur.get(key)
            continue
        if isinstance(cur, list) and key.isdigit():
            idx = int(key)
            cur = cur[idx] if 0 <= idx < len(cur) else None
            continue
        return None
    return cur


def _flatten_for_template(data: Any, prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.update(_flatten_for_template(value, next_prefix))
        return out
    if isinstance(data, (list, tuple)):
        out[prefix] = ",".join(str(x) for x in data)
        return out
    out[prefix] = data
    return out


def _render_template(template: str, context: Dict[str, Any]) -> str:
    if not template:
        return ""
    flat = _flatten_for_template(context)
    fields = {name for _, name, _, _ in Formatter().parse(template) if name}
    values = {name: flat.get(name, context.get(name, "")) for name in fields}
    try:
        return template.format(**values).strip()
    except Exception:
        return template.strip()


def _normalize_op(expr: Dict[str, Any]) -> str:
    op = str(expr.get("op") or expr.get("condition") or "").strip().lower()
    if not op and "equals" in expr:
        op = "eq"
    if not op and "threshold" in expr:
        op = "lt"
    if not op:
        op = "exists"
    if op not in SUPPORTED_RULE_OPS:
        return "exists"
    return op


def _compare_values(op: str, actual: Any, expected: Any) -> bool:
    if op == "exists":
        return actual is not None
    if op == "not_exists":
        return actual is None
    if op == "non_empty":
        return _is_non_empty(actual)
    if op == "is_empty":
        return not _is_non_empty(actual)

    if op in {"lt", "lte", "gt", "gte"}:
        actual_num = _to_float(actual, float("nan"))
        expected_num = _to_float(expected, float("nan"))
        if str(actual_num) == "nan" or str(expected_num) == "nan":
            return False
        if op == "lt":
            return actual_num < expected_num
        if op == "lte":
            return actual_num <= expected_num
        if op == "gt":
            return actual_num > expected_num
        return actual_num >= expected_num

    if op == "contains":
        if isinstance(actual, (list, tuple, set)):
            return expected in actual
        return str(expected) in str(actual or "")

    if op == "in":
        if not isinstance(expected, (list, tuple, set)):
            return False
        return actual in expected

    if op == "neq":
        return actual != expected
    return actual == expected


def _evaluate_rule_expr(expr: Dict[str, Any], context: Dict[str, Any]) -> bool:
    if not isinstance(expr, dict):
        return False
    if "all" in expr:
        children = expr.get("all")
        if not isinstance(children, list) or not children:
            return False
        return all(_evaluate_rule_expr(item, context) for item in children if isinstance(item, dict))
    if "any" in expr:
        children = expr.get("any")
        if not isinstance(children, list) or not children:
            return False
        return any(_evaluate_rule_expr(item, context) for item in children if isinstance(item, dict))
    if "not" in expr and isinstance(expr.get("not"), dict):
        return not _evaluate_rule_expr(expr["not"], context)

    path = str(expr.get("path") or expr.get("field") or "").strip()
    op = _normalize_op(expr)
    actual = _get_by_path(context, path) if path else context
    expected = expr.get("value")
    if expected is None and "equals" in expr:
        expected = expr.get("equals")
    if expected is None and "threshold" in expr:
        expected = expr.get("threshold")
    return _compare_values(op, actual, expected)


def _rule_scope(rule: Dict[str, Any]) -> str:
    expr = rule.get("expr") if isinstance(rule.get("expr"), dict) else {}
    scope = str(expr.get("scope") or "").strip().lower()
    if scope in {"field", "document"}:
        return scope
    path = str(expr.get("path") or expr.get("field") or "").strip().lower()
    if "confidence" in path or "value" in path:
        return "field"
    return "document"


def _compact_payload_context(context: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "file_name": context.get("file_name"),
        "file_hash": context.get("file_hash"),
        "track": context.get("track"),
        "field_name": context.get("field_name"),
        "value": context.get("value"),
        "confidence": context.get("confidence"),
        "errors_count": context.get("errors_count"),
        "soft_warning_count": context.get("soft_warning_count"),
        "quality_status": _get_by_path(context, "diagnostics.quality_status"),
    }
    return {k: v for k, v in payload.items() if v is not None and v != ""}


def _derived_ingest_batch_key(payload: IngestRequest, tenant_id: Optional[str] = None) -> str:
    if payload.source_batch_key:
        return str(payload.source_batch_key).strip()
    normalized_payload = payload.model_dump(mode="json")
    normalized: Dict[str, Any] = {
        "tenant_id": tenant_id or payload.tenant_id or _default_tenant(),
        "source": payload.source,
        "graph_mode": payload.graph_mode,
        "documents": normalized_payload.get("documents", []),
    }
    return _risk_key(_stable_json_dumps(normalized))


def _rule_risk_score(rule: Dict[str, Any], context: Dict[str, Any]) -> float:
    severity = str(rule.get("severity") or "yellow").lower()
    expr = rule.get("expr") if isinstance(rule.get("expr"), dict) else {}
    explicit = expr.get("risk_score")
    if isinstance(explicit, (int, float, str)):
        return round(_clamp(_to_float(explicit, 0.0), 0.0, 100.0), 3)
    formula = str(expr.get("risk_formula") or "").strip().lower()
    if formula == "1_minus_confidence":
        confidence = _to_float(_get_by_path(context, "confidence"), 1.0)
        return round(_clamp((1.0 - confidence) * 100.0, 0.0, 100.0), 3)
    return round(SEVERITY_DEFAULT_RISK.get(severity, 40.0), 3)


def _evaluate_rule_hit(rule: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not bool(rule.get("enabled", True)):
        return None
    if str(rule.get("rule_kind") or "").strip().lower() not in SUPPORTED_RULE_KINDS:
        return None

    expr = rule.get("expr") if isinstance(rule.get("expr"), dict) else {}
    if not _evaluate_rule_expr(expr, context):
        return None

    merged_context = dict(context)
    merged_context.update(
        {
            "rule_id": rule.get("rule_id"),
            "rule_name": rule.get("name"),
            "severity": rule.get("severity"),
        }
    )
    title_template = str(expr.get("title") or f"Rule hit: {rule.get('name') or rule.get('rule_id')}")
    summary_template = str(expr.get("summary") or "Rule {rule_id} matched for {file_name}")
    title = _render_template(title_template, merged_context) or str(rule.get("name") or rule.get("rule_id"))
    summary = _render_template(summary_template, merged_context) or f"Rule {rule.get('rule_id')} matched"
    return {
        "rule_id": str(rule.get("rule_id")),
        "severity": str(rule.get("severity") or "yellow"),
        "title": title,
        "summary": summary,
        "risk_score": _rule_risk_score(rule, context),
        "payload": {
            "rule_expr": expr,
            "context": _compact_payload_context(context),
        },
    }


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None:
        return {}
    return {"raw": value}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _normalize_graph_node_row(row: Dict[str, Any]) -> Dict[str, Any]:
    node_id = str(row.get("node_id") or "").strip()
    canonical_key = str(row.get("canonical_key") or "").strip() or node_id
    display_name = str(row.get("display_name") or "").strip() or canonical_key or "node"
    return {
        "node_id": node_id or _risk_key(display_name),
        "node_type": str(row.get("node_type") or "Unknown"),
        "canonical_key": canonical_key or display_name,
        "display_name": display_name,
        "confidence": _to_float(row.get("confidence"), 0.0),
        "attrs": _as_dict(row.get("attrs")),
        "updated_at": row.get("updated_at"),
    }


def _normalize_graph_edge_row(row: Dict[str, Any]) -> Dict[str, Any]:
    direction = str(row.get("direction") or "out")
    if direction not in EDGE_DIRECTION:
        direction = "out"
    return {
        "edge_id": str(row.get("edge_id") or _risk_key(json.dumps(row, ensure_ascii=False))),
        "source_node_id": str(row.get("source_node_id") or ""),
        "target_node_id": str(row.get("target_node_id") or ""),
        "relation_type": str(row.get("relation_type") or "related_to"),
        "direction": direction,
        "confidence": _to_float(row.get("confidence"), 0.0),
        "risk_score": _to_float(row.get("risk_score"), 0.0),
        "attrs": _as_dict(row.get("attrs")),
        "updated_at": row.get("updated_at"),
    }


def _normalize_projection_payload(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    labels_raw = value.get("labels")
    labels = [str(item) for item in labels_raw if str(item).strip()] if isinstance(labels_raw, list) else []
    return {
        "status": str(value.get("status") or "").strip(),
        "projected_nodes": _to_int(value.get("projected_nodes"), 0),
        "projected_edges": _to_int(value.get("projected_edges"), 0),
        "source_node_count": _to_int(value.get("source_node_count"), 0),
        "source_edge_count": _to_int(value.get("source_edge_count"), 0),
        "skipped_reason": str(value.get("skipped_reason") or "").strip() or None,
        "error_message": str(value.get("error_message") or "").strip() or None,
        "labels": labels,
        "relationship_type": str(value.get("relationship_type") or "MODULE4_EDGE"),
    }


def _projection_runtime_status() -> Dict[str, Any]:
    neo4j_graph_projector.refresh_settings(getattr(workspace_builder, "neo4j", None))
    settings = neo4j_graph_projector.settings
    configured = settings.is_configured()
    return {
        "enabled": bool(neo4j_graph_projector.enabled),
        "configured": configured,
        "can_project": bool(neo4j_graph_projector.enabled and configured),
        "database": str(settings.database or "neo4j"),
        "max_nodes": int(neo4j_graph_projector.max_nodes),
        "max_edges": int(neo4j_graph_projector.max_edges),
        "timeout_sec": float(getattr(neo4j_graph_projector, "timeout_sec", 0.0) or 0.0),
        "missing_fields": settings.missing_fields(),
        "labels": ["Module4Node"],
        "relationship_type": "MODULE4_EDGE",
    }


def _normalize_graph_file_row(row: Dict[str, Any]) -> Dict[str, Any]:
    metadata = _as_dict(row.get("metadata"))
    projection = _normalize_projection_payload(metadata.get("projection"))
    return {
        "graph_file_id": str(row.get("graph_file_id") or ""),
        "tenant_id": str(row.get("tenant_id") or _default_tenant()),
        "file_hash": str(row.get("file_hash") or ""),
        "file_name": str(row.get("file_name") or "unknown"),
        "workspace_id": str(row.get("workspace_id") or "") or None,
        "graph_mode": str(row.get("graph_mode") or "hybrid"),
        "source": str(row.get("source") or "module2"),
        "status": str(row.get("status") or "queued"),
        "current_job_id": str(row.get("current_job_id") or "") or None,
        "active_version_id": str(row.get("active_version_id") or "") or None,
        "last_error": str(row.get("last_error") or "") or None,
        "node_count": _to_int(row.get("node_count"), 0),
        "edge_count": _to_int(row.get("edge_count"), 0),
        "metadata": metadata,
        "projection": projection,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "last_indexed_at": row.get("last_indexed_at"),
    }


def _normalize_alert_row(row: Dict[str, Any]) -> Dict[str, Any]:
    severity = str(row.get("severity") or "yellow").lower()
    if severity not in ALERT_SEVERITY:
        severity = "yellow"
    status = str(row.get("status") or "open").lower()
    if status not in ALERT_STATUS:
        status = "open"
    title = str(row.get("title") or row.get("rule_id") or "Alert")
    summary = str(row.get("summary") or title)
    return {
        "alert_id": str(row.get("alert_id") or _risk_key(title + summary)),
        "rule_id": str(row.get("rule_id") or "UNKNOWN"),
        "severity": severity,
        "status": status,
        "subject_node_id": str(row.get("subject_node_id")) if row.get("subject_node_id") else None,
        "title": title,
        "summary": summary,
        "risk_score": _to_float(row.get("risk_score"), 0.0),
        "payload": _as_dict(row.get("payload")),
        "detected_at": row.get("detected_at"),
        "acknowledged_at": row.get("acknowledged_at"),
        "resolved_at": row.get("resolved_at"),
        "updated_at": row.get("updated_at"),
    }


def _normalize_rule_row(row: Dict[str, Any]) -> Dict[str, Any]:
    severity = str(row.get("severity") or "yellow").lower()
    if severity not in ALERT_SEVERITY:
        severity = "yellow"
    rule_kind = str(row.get("rule_kind") or "deterministic").lower()
    if rule_kind not in RULE_KIND:
        rule_kind = "deterministic"
    return {
        "rule_id": str(row.get("rule_id") or "UNKNOWN"),
        "name": str(row.get("name") or row.get("rule_id") or "rule"),
        "severity": severity,
        "rule_kind": rule_kind,
        "expr": _as_dict(row.get("expr")),
        "enabled": bool(row.get("enabled", True)),
        "version": _to_int(row.get("version"), 1),
        "updated_at": row.get("updated_at"),
    }


def _normalize_evidence_row(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "evidence_id": str(row.get("evidence_id") or _risk_key(json.dumps(row, ensure_ascii=False))),
        "doc_id": str(row.get("doc_id") or ""),
        "object_type": str(row.get("object_type") or "field"),
        "object_id": str(row.get("object_id") or ""),
        "ref_id": str(row.get("ref_id")) if row.get("ref_id") is not None else None,
        "page_no": _to_int(row.get("page_no"), 0) if row.get("page_no") is not None else None,
        "snippet": str(row.get("snippet") or ""),
        "locator": _as_dict(row.get("locator")),
        "bbox": _as_list(row.get("bbox")),
        "artifact_url": str(row.get("artifact_url")) if row.get("artifact_url") else None,
        "confidence": _to_float(row.get("confidence"), 0.0),
        "created_at": row.get("created_at"),
    }


def _append_evidence_candidate(
    candidates: List[tuple[str, str]],
    seen: set[tuple[str, str]],
    object_type: str,
    object_id: Any,
) -> None:
    object_type_value = str(object_type or "").strip().lower()
    object_id_value = str(object_id or "").strip()
    if not object_type_value or not object_id_value:
        return
    key = (object_type_value, object_id_value)
    if key in seen:
        return
    seen.add(key)
    candidates.append(key)


def _node_evidence_candidates(node_row: Dict[str, Any]) -> List[tuple[str, str]]:
    attrs = _as_dict(node_row.get("attrs"))
    node_type = str(node_row.get("node_type") or "").strip().lower()
    display_name = str(node_row.get("display_name") or "").strip()
    graphrag_id = str(attrs.get("graphrag_id") or "").strip()
    report_id = str(attrs.get("report_id") or "").strip()
    file_hash = str(attrs.get("file_hash") or "").strip()
    field_name = str(attrs.get("field_name") or "").strip()
    candidates: List[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    if node_type == "document":
        _append_evidence_candidate(candidates, seen, "document", graphrag_id or file_hash or display_name)
    elif node_type == "chunk":
        _append_evidence_candidate(candidates, seen, "chunk", graphrag_id or display_name)
    elif node_type == "entity":
        _append_evidence_candidate(candidates, seen, "entity", graphrag_id or display_name)
    elif node_type == "community":
        _append_evidence_candidate(candidates, seen, "community", graphrag_id or report_id or display_name)
    elif node_type == "covariate":
        _append_evidence_candidate(candidates, seen, "covariate", graphrag_id or display_name)
    elif node_type == "field":
        _append_evidence_candidate(candidates, seen, "field", field_name or display_name)
    elif node_type in {"table", "figure"}:
        _append_evidence_candidate(candidates, seen, node_type, display_name)

    for chunk_id in _as_list(attrs.get("text_unit_ids")):
        _append_evidence_candidate(candidates, seen, "chunk", chunk_id)
    for chunk_id in _as_list(attrs.get("source_chunk_ids")):
        _append_evidence_candidate(candidates, seen, "chunk", chunk_id)
    for document_id in _as_list(attrs.get("document_ids")):
        _append_evidence_candidate(candidates, seen, "document", document_id)

    return candidates


async def _load_evidence_for_node(tenant_id: str, node_row: Dict[str, Any], *, limit: int = 10) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for object_type, object_id in _node_evidence_candidates(node_row):
        _, rows = await storage.list_evidence(
            tenant_id=tenant_id,
            doc_id=None,
            object_type=object_type,
            object_id=object_id,
            page=1,
            page_size=max(limit, 10),
        )
        for row in rows:
            normalized = _normalize_evidence_row(row)
            evidence_id = str(normalized.get("evidence_id") or "")
            if not evidence_id or evidence_id in seen:
                continue
            seen.add(evidence_id)
            items.append(normalized)
            if len(items) >= limit:
                return items
    return items


async def _load_edge_evidence_for_edges(
    tenant_id: str,
    edge_rows: List[Dict[str, Any]],
    *,
    limit_per_edge: int = 4,
    edge_cap: int = 8,
) -> Dict[str, List[Dict[str, Any]]]:
    items: Dict[str, List[Dict[str, Any]]] = {}
    for edge_row in edge_rows[: max(1, edge_cap)]:
        edge_id = str(edge_row.get("edge_id") or "").strip()
        if not edge_id:
            continue
        _, rows = await storage.list_edge_evidence(
            tenant_id=tenant_id,
            edge_id=edge_id,
            page=1,
            page_size=max(limit_per_edge, 4),
        )
        normalized = [_normalize_evidence_row(row) for row in rows]
        if normalized:
            items[edge_id] = normalized[:limit_per_edge]
    return items


def _scope_values(raw: Any) -> List[str]:
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, tuple):
        values = list(raw)
    elif raw is None:
        values = []
    else:
        text = str(raw).strip()
        if not text:
            values = []
        else:
            values = [item.strip() for item in text.replace("|", ",").split(",") if item.strip()]
    return [str(item).strip() for item in values if str(item).strip()]


def _simulation_context_label(scope_name: str, context: Dict[str, Any], index: int) -> str:
    if scope_name == "field":
        field_name = str(context.get("field_name") or "").strip()
        file_name = str(context.get("file_name") or "").strip()
        if field_name and file_name:
            return f"{file_name}:{field_name}"
        if field_name:
            return f"field:{field_name}"
    if scope_name == "document":
        file_name = str(context.get("file_name") or "").strip()
        file_hash = str(context.get("file_hash") or "").strip()
        if file_name:
            return f"document:{file_name}"
        if file_hash:
            return f"document:{file_hash}"
    return f"{scope_name}:{index}"


def _inflate_simulation_context(raw_context: Dict[str, Any]) -> Dict[str, Any]:
    context = dict(raw_context or {})
    quality_status = str(context.get("quality_status") or "").strip()
    diagnostics = context.get("diagnostics") if isinstance(context.get("diagnostics"), dict) else {}
    if quality_status and "quality_status" not in diagnostics:
        diagnostics = {**diagnostics, "quality_status": quality_status}
        context["diagnostics"] = diagnostics

    errors_count = _to_int(context.get("errors_count"), 0)
    if errors_count > 0 and not isinstance(context.get("errors"), list):
        context["errors"] = ["simulated_error"] * errors_count

    soft_warning_count = _to_int(context.get("soft_warning_count"), 0)
    if soft_warning_count > 0 and not isinstance(context.get("soft_warnings"), list):
        context["soft_warnings"] = ["simulated_warning"] * soft_warning_count

    return context


async def _simulation_contexts_from_request(tenant_id: str, body: SimulateRequest) -> List[Dict[str, Any]]:
    contexts: List[Dict[str, Any]] = []
    params = body.params if isinstance(body.params, dict) else {}
    scope = body.scope if isinstance(body.scope, dict) else {}
    context_overrides = params.get("context_overrides") if isinstance(params.get("context_overrides"), dict) else {}

    def _append_context(scope_name: str, raw_context: Dict[str, Any], index: int, *, source_alert_id: str | None = None) -> None:
        context = _inflate_simulation_context(raw_context)
        if context_overrides:
            context.update(context_overrides)
        context["__scope"] = scope_name
        context["__label"] = str(context.get("__label") or _simulation_context_label(scope_name, context, index))
        if source_alert_id:
            context["__source_alert_id"] = source_alert_id
        contexts.append(context)

    if isinstance(params.get("document_context"), dict):
        _append_context("document", params["document_context"], len(contexts) + 1)
    if isinstance(params.get("field_context"), dict):
        _append_context("field", params["field_context"], len(contexts) + 1)

    for item in _as_list(params.get("document_contexts")):
        if isinstance(item, dict):
            _append_context("document", item, len(contexts) + 1)
    for item in _as_list(params.get("field_contexts")):
        if isinstance(item, dict):
            _append_context("field", item, len(contexts) + 1)

    alert_ids = _scope_values(scope.get("alert_ids"))
    single_alert_id = str(scope.get("alert_id") or "").strip()
    if single_alert_id:
        alert_ids.append(single_alert_id)
    seen_alert_ids: set[str] = set()
    for alert_id in alert_ids:
        if alert_id in seen_alert_ids:
            continue
        seen_alert_ids.add(alert_id)
        alert = await storage.get_alert(alert_id, tenant_id=tenant_id)
        if not alert:
            continue
        payload = alert.get("payload") if isinstance(alert.get("payload"), dict) else {}
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        rule_expr = payload.get("rule_expr") if isinstance(payload.get("rule_expr"), dict) else {}
        scope_name = _rule_scope({"expr": rule_expr}) if rule_expr else "document"
        if context:
            _append_context(scope_name, context, len(contexts) + 1, source_alert_id=alert_id)

    return contexts


storage = Module4Storage(os.getenv("MODULE4_DATABASE_DSN", "postgresql://postgres:postgres@localhost:5432/a23"))
job_tasks: Dict[str, asyncio.Task[Any]] = {}
workspace_builder = GraphRAGWorkspaceBuilder()
graphrag_indexer = GraphRAGIndexer()
neo4j_graph_projector = Neo4jGraphProjector(workspace_builder.neo4j)


def _count_inputs_from_batches(batches: Sequence[Dict[str, Any]]) -> int:
    total = 0
    for batch in batches:
        payload = batch.get("raw_payload") if isinstance(batch.get("raw_payload"), dict) else {}
        documents = payload.get("documents") if isinstance(payload.get("documents"), list) else []
        total += len(documents)
    return total


def _merge_result(base: Optional[Dict[str, Any]] = None, **updates: Any) -> Dict[str, Any]:
    merged = dict(base or {})
    merged.update({key: value for key, value in updates.items() if value is not None})
    return merged


def _trim_error_text(value: Any, limit: int = 600) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)].rstrip()}..."


def _classify_graph_failure(exc: Exception, *, fallback_stage: str) -> Dict[str, str]:
    failure_category = "unexpected_failure"
    failure_stage = fallback_stage

    if isinstance(exc, GraphRAGIndexError):
        failure_category = str(exc.category or "index_failure").strip() or "index_failure"
        if failure_category in {"index_timeout", "index_process_failed"}:
            failure_stage = "indexing"
        elif failure_category == "artifacts_missing":
            failure_stage = "importing_graph"
    else:
        message = str(exc or "").lower()
        if "normaliz" in message:
            failure_category = "normalization_failed"
            failure_stage = "normalizing"
        elif "artifact quality gate failed" in message:
            failure_category = "artifact_quality_failed"
            failure_stage = "importing_graph"
        elif "runtime not ready" in message:
            failure_category = "runtime_not_ready"
            failure_stage = "validating_runtime"
        elif "artifact" in message and "not found" in message:
            failure_category = "artifacts_missing"
            failure_stage = "importing_graph"
        elif "neo4j" in message and ("import" in message or "connect" in message):
            failure_category = "graph_import_failed"
            failure_stage = "importing_graph"
        elif "graphrag index" in message:
            failure_category = "index_process_failed"
            failure_stage = "indexing"

    message = _trim_error_text(f"{type(exc).__name__}: {exc}")
    return {
        "failure_category": failure_category,
        "failure_stage": failure_stage,
        "failure_message": message,
    }


async def _update_job_stage(
    job_id: str,
    *,
    stage: str,
    progress: float,
    base_result: Optional[Dict[str, Any]] = None,
    **updates: Any,
) -> None:
    await storage.update_job(
        job_id,
        progress=progress,
        result=_merge_result(base_result, stage=stage, **updates),
    )

async def _recover_jobs() -> None:
    recoverable = await storage.list_recoverable_jobs()
    for row in recoverable:
        job_type = str(row.get("job_type") or "").strip()
        job_id = str(row.get("job_id") or "").strip()
        if not job_id or job_id in job_tasks:
            continue
        if job_type == "ingest":
            batch_id = str(row.get("batch_id") or "").strip()
            raw_payload = row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {}
            if not batch_id:
                await storage.update_job(
                    job_id,
                    status="failed",
                    error_message="Recover payload invalid: missing batch_id",
                    finished_at=_now_utc(),
                )
                continue
            try:
                payload = IngestRequest.model_validate(raw_payload)
            except Exception as exc:
                await storage.update_job(
                    job_id,
                    status="failed",
                    error_message=f"Recover payload invalid: {type(exc).__name__}: {exc}",
                    finished_at=_now_utc(),
                )
                continue
            _schedule_ingest_job(job_id, batch_id, payload)
            continue

        if job_type == "rebuild_graph":
            payload_raw = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            try:
                payload = RebuildRequest.model_validate(payload_raw)
            except Exception as exc:
                await storage.update_job(
                    job_id,
                    status="failed",
                    error_message=f"Recover rebuild payload invalid: {type(exc).__name__}: {exc}",
                    finished_at=_now_utc(),
                )
                continue
            _schedule_rebuild_job(job_id, payload)


@asynccontextmanager
async def lifespan(_: FastAPI):
    startup_timeout = max(5.0, _to_float(os.getenv("MODULE4_STARTUP_TIMEOUT_SEC"), 20.0))
    recovery_timeout = max(3.0, _to_float(os.getenv("MODULE4_RECOVERY_TIMEOUT_SEC"), 8.0))
    logger.info("module4 startup begin")
    try:
        await asyncio.wait_for(storage.connect(), timeout=startup_timeout)
        logger.info("module4 storage connect completed: %s", storage.diagnostics())
    except asyncio.TimeoutError as exc:
        logger.error("module4 storage connect timed out after %.1fs", startup_timeout)
        raise RuntimeError(f"module4 storage.connect exceeded {startup_timeout:.1f}s") from exc
    except Exception as exc:
        logger.exception("module4 storage connect failed during startup: %s", exc)
        raise
    try:
        await asyncio.wait_for(_recover_jobs(), timeout=recovery_timeout)
        logger.info("module4 job recovery completed")
    except asyncio.TimeoutError:
        logger.warning("module4 job recovery timed out after %.1fs; continuing startup", recovery_timeout)
    except Exception as exc:
        logger.exception("module4 job recovery failed during startup: %s", exc)
    try:
        yield
    finally:
        logger.info("module4 shutdown begin")
        tasks = [task for task in job_tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        await storage.close()


app = FastAPI(title="A23 Module 4 - Global Knowledge Graph & Risk Intelligence", version="1.1.0", lifespan=lifespan)
CORS_ORIGINS, CORS_ALLOW_ALL = _cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if CORS_ALLOW_ALL else CORS_ORIGINS,
    allow_credentials=not CORS_ALLOW_ALL,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _emit_alert(
    *,
    tenant_id: str,
    rule_id: str,
    severity: str,
    subject_node_id: Optional[str],
    title: str,
    summary: str,
    risk_score: float,
    payload: Dict[str, Any],
    db_conn: Any = None,
) -> None:
    await storage.insert_alert(
        tenant_id=tenant_id,
        rule_id=rule_id,
        severity=severity,
        subject_node_id=subject_node_id,
        title=title,
        summary=summary,
        risk_score=risk_score,
        payload=payload,
        conn=db_conn,
    )


async def _process_document(
    *,
    tenant_id: str,
    batch_id: str,
    graph_file_id: Optional[str],
    doc: Dict[str, Any],
    field_rules: Sequence[Dict[str, Any]],
    document_rules: Sequence[Dict[str, Any]],
) -> Dict[str, int]:
    file_name = str(doc.get("file_name") or "unknown")
    file_hash = str(doc.get("file_hash") or "").strip() or _risk_key(file_name + json.dumps(doc, ensure_ascii=False))
    track = str(doc.get("track") or "")
    diagnostics = doc.get("diagnostics") if isinstance(doc.get("diagnostics"), dict) else {}
    errors = [str(x) for x in (doc.get("errors") if isinstance(doc.get("errors"), list) else []) if str(x).strip()]
    soft_warnings = [
        str(x) for x in (doc.get("soft_warnings") if isinstance(doc.get("soft_warnings"), list) else []) if str(x).strip()
    ]

    async with storage.transaction() as db_conn:
        if graph_file_id:
            await storage.reset_graph_file_scope(
                tenant_id=tenant_id,
                graph_file_id=graph_file_id,
                file_hash=file_hash,
                conn=db_conn,
            )
        doc_row = await storage.upsert_document(
            tenant_id=tenant_id,
            batch_id=batch_id,
            file_name=file_name,
            file_hash=file_hash,
            track=track,
            diagnostics=diagnostics,
            conn=db_conn,
        )
        doc_node = await storage.upsert_node(
            tenant_id=tenant_id,
            graph_file_id=graph_file_id,
            node_type="Document",
            canonical_key=file_hash,
            display_name=file_name,
            attrs={
                "file_hash": file_hash,
                "file_name": file_name,
                "track": track,
                "cached": bool(doc.get("cached")),
                "diagnostics": diagnostics,
            },
            confidence=1.0,
            conn=db_conn,
        )

        counters = {"nodes": 1, "edges": 0, "alerts": 0, "evidence": 0}
        field_node_ids: Dict[str, str] = {}
        result = doc.get("result") if isinstance(doc.get("result"), dict) else {}

        for field_name, entity in result.items():
            entity_map = entity if isinstance(entity, dict) else {}
            value = entity_map.get("value")
            confidence = _to_float(entity_map.get("confidence"), 0.0)
            source_ref_id = str(entity_map.get("source_ref_id") or "").strip() or None
            bbox = entity_map.get("bbox") if isinstance(entity_map.get("bbox"), list) else []

            field_node = await storage.upsert_node(
                tenant_id=tenant_id,
                graph_file_id=graph_file_id,
                node_type="Field",
                canonical_key=f"{file_hash}:{field_name}",
                display_name=str(field_name),
                attrs={
                    "file_hash": file_hash,
                    "file_name": file_name,
                    "field_name": field_name,
                    "value": value,
                    "source_ref_id": source_ref_id,
                    "bbox": bbox,
                },
                confidence=confidence,
                conn=db_conn,
            )
            counters["nodes"] += 1
            field_node_ids[str(field_name)] = str(field_node["node_id"])

            await storage.upsert_edge(
                tenant_id=tenant_id,
                graph_file_id=graph_file_id,
                source_node_id=str(doc_node["node_id"]),
                target_node_id=str(field_node["node_id"]),
                relation_type="extracts",
                direction="out",
                attrs={"field_name": field_name},
                confidence=max(0.1, confidence),
                risk_score=round(_clamp((1.0 - confidence) * 100.0, 0.0, 100.0), 3),
                conn=db_conn,
            )
            counters["edges"] += 1

            field_context = {
                "tenant_id": tenant_id,
                "file_hash": file_hash,
                "file_name": file_name,
                "track": track,
                "field_name": str(field_name),
                "value": value,
                "confidence": confidence,
                "source_ref_id": source_ref_id,
                "bbox": bbox,
                "errors_count": len(errors),
                "soft_warning_count": len(soft_warnings),
                "diagnostics": diagnostics,
            }
            for rule in field_rules:
                hit = _evaluate_rule_hit(rule, field_context)
                if not hit:
                    continue
                await _emit_alert(
                    tenant_id=tenant_id,
                    rule_id=hit["rule_id"],
                    severity=hit["severity"],
                    subject_node_id=str(field_node["node_id"]),
                    title=hit["title"],
                    summary=hit["summary"],
                    risk_score=hit["risk_score"],
                    payload=hit["payload"],
                    db_conn=db_conn,
                )
                counters["alerts"] += 1

        if errors:
            risk_node = await storage.upsert_node(
                tenant_id=tenant_id,
                graph_file_id=graph_file_id,
                node_type="Risk",
                canonical_key=f"{file_hash}:errors:{_risk_key('|'.join(errors))}",
                display_name=f"{file_name} parsing errors",
                attrs={"errors": errors},
                confidence=0.99,
                conn=db_conn,
            )
            counters["nodes"] += 1
            await storage.upsert_edge(
                tenant_id=tenant_id,
                graph_file_id=graph_file_id,
                source_node_id=str(doc_node["node_id"]),
                target_node_id=str(risk_node["node_id"]),
                relation_type="has_risk",
                direction="out",
                attrs={"kind": "errors"},
                confidence=0.95,
                risk_score=92.0,
                conn=db_conn,
            )
            counters["edges"] += 1

        for warning in soft_warnings[:6]:
            risk_node = await storage.upsert_node(
                tenant_id=tenant_id,
                graph_file_id=graph_file_id,
                node_type="Risk",
                canonical_key=f"{file_hash}:warning:{_risk_key(warning)}",
                display_name=f"{file_name} warning",
                attrs={"warning": warning},
                confidence=0.8,
                conn=db_conn,
            )
            counters["nodes"] += 1
            await storage.upsert_edge(
                tenant_id=tenant_id,
                graph_file_id=graph_file_id,
                source_node_id=str(doc_node["node_id"]),
                target_node_id=str(risk_node["node_id"]),
                relation_type="has_warning",
                direction="out",
                attrs={"kind": "soft_warning"},
                confidence=0.75,
                risk_score=35.0,
                conn=db_conn,
            )
            counters["edges"] += 1

        doc_context = {
            "tenant_id": tenant_id,
            "file_hash": file_hash,
            "file_name": file_name,
            "track": track,
            "errors": errors,
            "errors_count": len(errors),
            "soft_warnings": soft_warnings,
            "soft_warning_count": len(soft_warnings),
            "diagnostics": diagnostics,
            "field_count": len(result),
        }
        for rule in document_rules:
            hit = _evaluate_rule_hit(rule, doc_context)
            if not hit:
                continue
            await _emit_alert(
                tenant_id=tenant_id,
                rule_id=hit["rule_id"],
                severity=hit["severity"],
                subject_node_id=str(doc_node["node_id"]),
                title=hit["title"],
                summary=hit["summary"],
                risk_score=hit["risk_score"],
                payload=hit["payload"],
                db_conn=db_conn,
            )
            counters["alerts"] += 1

        trace_hits = doc.get("trace_hits") if isinstance(doc.get("trace_hits"), list) else []
        for hit in trace_hits[:200]:
            hit_map = hit if isinstance(hit, dict) else {}
            page_raw = hit_map.get("page")
            page_no = _to_int(page_raw, -1) if str(page_raw or "").strip() else None
            page_no = page_no if page_no is None or page_no >= 0 else None

            evidence = await storage.insert_evidence(
                tenant_id=tenant_id,
                doc_id=str(doc_row["doc_id"]),
                object_type=str(hit_map.get("object_type") or "field"),
                object_id=str(hit_map.get("object_id") or ""),
                ref_id=str(hit_map.get("ref_id") or "").strip() or None,
                page_no=page_no,
                snippet=str(hit_map.get("snippet") or "")[:500],
                locator=hit_map.get("locator") if isinstance(hit_map.get("locator"), dict) else {},
                bbox=hit_map.get("bbox") if isinstance(hit_map.get("bbox"), list) else [],
                artifact_url=str(hit_map.get("artifact_url") or "").strip() or None,
                confidence=_to_float(hit_map.get("confidence"), 0.0),
                conn=db_conn,
            )
            counters["evidence"] += 1

            object_type = str(hit_map.get("object_type") or "").strip().lower()
            object_id = str(hit_map.get("object_id") or "").strip()
            if object_type in {"table", "figure"} and object_id:
                target_node = await storage.upsert_node(
                    tenant_id=tenant_id,
                    graph_file_id=graph_file_id,
                    node_type=object_type.title(),
                    canonical_key=f"{file_hash}:{object_type}:{object_id}",
                    display_name=object_id,
                    attrs={
                        "file_hash": file_hash,
                        "object_type": object_type,
                        "snippet": str(hit_map.get("snippet") or "")[:300],
                        "page": hit_map.get("page"),
                    },
                    confidence=_to_float(hit_map.get("confidence"), 0.6),
                    conn=db_conn,
                )
                counters["nodes"] += 1
                edge = await storage.upsert_edge(
                    tenant_id=tenant_id,
                    graph_file_id=graph_file_id,
                    source_node_id=str(doc_node["node_id"]),
                    target_node_id=str(target_node["node_id"]),
                    relation_type="contains",
                    direction="out",
                    attrs={"object_type": object_type},
                    confidence=_to_float(hit_map.get("confidence"), 0.6),
                    risk_score=0.0,
                    conn=db_conn,
                )
                counters["edges"] += 1
                await storage.link_edge_evidence(
                    edge_id=str(edge["edge_id"]),
                    evidence_id=str(evidence["evidence_id"]),
                    conn=db_conn,
                )

        polymorphic_links = diagnostics.get("polymorphic_links") if isinstance(diagnostics.get("polymorphic_links"), list) else []
        for link in polymorphic_links[:120]:
            link_map = link if isinstance(link, dict) else {}
            field_name = str(link_map.get("field") or "").strip()
            src_id = field_node_ids.get(field_name)
            if not src_id:
                continue
            targets = link_map.get("targets") if isinstance(link_map.get("targets"), list) else []
            for target in targets[:10]:
                target_map = target if isinstance(target, dict) else {}
                target_type = str(target_map.get("type") or "").strip().lower()
                target_id = str(target_map.get("id") or "").strip()
                if target_type not in {"table", "figure"} or not target_id:
                    continue
                tgt_node = await storage.upsert_node(
                    tenant_id=tenant_id,
                    graph_file_id=graph_file_id,
                    node_type=target_type.title(),
                    canonical_key=f"{file_hash}:{target_type}:{target_id}",
                    display_name=target_id,
                    attrs={"file_hash": file_hash, "type": target_type},
                    confidence=_to_float(target_map.get("confidence"), 0.6),
                    conn=db_conn,
                )
                counters["nodes"] += 1
                await storage.upsert_edge(
                    tenant_id=tenant_id,
                    graph_file_id=graph_file_id,
                    source_node_id=src_id,
                    target_node_id=str(tgt_node["node_id"]),
                    relation_type="links_to",
                    direction="out",
                    attrs={"match": target_map.get("match"), "page": target_map.get("page")},
                    confidence=_to_float(target_map.get("confidence"), 0.6),
                    risk_score=0.0,
                    conn=db_conn,
                )
                counters["edges"] += 1

    return counters


def _schedule_ingest_job(job_id: str, batch_id: str, payload: IngestRequest) -> None:
    existing = job_tasks.get(job_id)
    if existing and not existing.done():
        return
    task = asyncio.create_task(_run_ingest_job(job_id, batch_id, payload))
    job_tasks[job_id] = task


def _schedule_rebuild_job(job_id: str, payload: RebuildRequest) -> None:
    existing = job_tasks.get(job_id)
    if existing and not existing.done():
        return
    task = asyncio.create_task(_run_rebuild_job(job_id, payload))
    job_tasks[job_id] = task

async def _run_document_ingest_job(job_id: str, batch_id: str, payload: IngestRequest) -> Dict[str, Any]:
    tenant_id = payload.tenant_id or _default_tenant()
    documents = payload.documents
    total = len(documents)
    agg = {
        "stage": "processing_documents",
        "nodes": 0,
        "edges": 0,
        "alerts": 0,
        "evidence": 0,
        "documents": total,
        "uploads": 0,
    }

    rules = await storage.list_rules(enabled_only=True)
    deterministic_rules = [rule for rule in rules if str(rule.get("rule_kind")).lower() in SUPPORTED_RULE_KINDS]
    field_rules = [rule for rule in deterministic_rules if _rule_scope(rule) == "field"]
    document_rules = [rule for rule in deterministic_rules if _rule_scope(rule) == "document"]

    await _update_job_stage(job_id, stage="processing_documents", progress=1.0, base_result=agg)
    for idx, doc in enumerate(documents, start=1):
        file_name = str(doc.get("file_name") or "unknown")
        file_hash = str(doc.get("file_hash") or "").strip() or _risk_key(file_name + json.dumps(doc, ensure_ascii=False))
        track = str(doc.get("track") or "")
        processing_metadata = {
            "batch_id": batch_id,
            "track": track,
            "ingest_mode": "document",
            "stage": "processing_documents",
        }
        graph_file = await storage.upsert_graph_file(
            tenant_id=tenant_id,
            file_hash=file_hash,
            file_name=file_name,
            workspace_id=None,
            graph_mode=payload.graph_mode,
            source=payload.source,
            status="processing_documents",
            current_job_id=job_id,
            last_error=None,
            node_count=0,
            edge_count=0,
            metadata=processing_metadata,
        )
        graph_file_id = str(graph_file.get("graph_file_id") or "").strip() or None
        try:
            counters = await _process_document(
                tenant_id=tenant_id,
                batch_id=batch_id,
                graph_file_id=graph_file_id,
                doc=doc,
                field_rules=field_rules,
                document_rules=document_rules,
            )
        except Exception as exc:
            failure_message = _trim_error_text(f"{type(exc).__name__}: {exc}")
            await storage.upsert_graph_file(
                tenant_id=tenant_id,
                file_hash=file_hash,
                file_name=file_name,
                workspace_id=None,
                graph_mode=payload.graph_mode,
                source=payload.source,
                status="failed",
                current_job_id=job_id,
                last_error=failure_message,
                node_count=0,
                edge_count=0,
                metadata={
                    **processing_metadata,
                    "stage": "failed",
                    "failure_stage": "processing_documents",
                    "failure_category": "document_ingest_failed",
                    "failure_message": failure_message,
                },
            )
            raise
        for key, value in counters.items():
            agg[key] += int(value)
        graph_file = await storage.upsert_graph_file(
            tenant_id=tenant_id,
            file_hash=file_hash,
            file_name=file_name,
            workspace_id=None,
            graph_mode=payload.graph_mode,
            source=payload.source,
            status="ready",
            current_job_id=job_id,
            last_error=None,
            node_count=int(counters.get("nodes", 0) or 0),
            edge_count=int(counters.get("edges", 0) or 0),
            metadata={**processing_metadata, "stage": "ready"},
            last_indexed_at=_now_utc(),
        )
        graph_version = await storage.add_graph_version(
            tenant_id=tenant_id,
            file_hash=file_hash,
            job_id=job_id,
            workspace_id=None,
            status=str(graph_file.get("status") or "ready"),
            manifest_path=None,
            output_dir=None,
            artifacts_dir=None,
            reports_dir=None,
            import_summary={
                "mode": "document",
                "nodes": int(counters.get("nodes", 0) or 0),
                "edges": int(counters.get("edges", 0) or 0),
                "alerts": int(counters.get("alerts", 0) or 0),
                "evidence": int(counters.get("evidence", 0) or 0),
            },
        )
        graph_version_id = str(graph_version.get("graph_version_id") or "").strip() or None
        if graph_file_id and graph_version_id:
            await storage.assign_graph_version(
                tenant_id=tenant_id,
                graph_file_id=graph_file_id,
                graph_version_id=graph_version_id,
                workspace_id=None,
            )
        progress = round((idx / max(1, total)) * 100.0, 2)
        await _update_job_stage(job_id, stage="processing_documents", progress=progress, base_result=agg)
    return agg

async def _run_ingest_job(job_id: str, batch_id: str, payload: IngestRequest) -> None:
    await storage.update_job(job_id, status="running", started_at=_now_utc(), progress=1.0)
    try:
        result = await _run_document_ingest_job(job_id, batch_id, payload)

        await storage.update_job(job_id, status="success", progress=100.0, result=result, finished_at=_now_utc())
    except asyncio.CancelledError:
        await storage.update_job(
            job_id,
            status="queued",
            error_message="Job interrupted during shutdown and queued for recovery",
            started_at=None,
            finished_at=None,
        )
        raise
    except Exception as exc:
        current_job = await storage.get_job(job_id)
        current_result = current_job.get("result") if current_job and isinstance(current_job.get("result"), dict) else {}
        failure = _classify_graph_failure(exc, fallback_stage=str(current_result.get("stage") or "failed"))
        await storage.update_job(
            job_id,
            status="failed",
            error_message=failure["failure_message"],
            result=_merge_result(
                current_result,
                stage="failed",
                failure_stage=failure["failure_stage"],
                failure_category=failure["failure_category"],
                error=failure["failure_message"],
            ),
            finished_at=_now_utc(),
        )
    finally:
        job_tasks.pop(job_id, None)


async def _run_rebuild_job(job_id: str, payload: RebuildRequest) -> None:
    tenant_id = payload.tenant_id or _default_tenant()
    batches = await storage.list_ingest_batches(tenant_id=tenant_id)
    total_inputs = _count_inputs_from_batches(batches)
    agg = {
        "documents": total_inputs,
        "batches": len(batches),
        "nodes": 0,
        "edges": 0,
        "alerts": 0,
        "evidence": 0,
    }

    await storage.update_job(job_id, status="running", started_at=_now_utc(), progress=1.0)
    try:
        await storage.delete_tenant_graph_data(tenant_id=tenant_id)

        processed = 0
        for batch in batches:
            batch_id = str(batch.get("batch_id") or "").strip()
            raw_payload = batch.get("raw_payload") if isinstance(batch.get("raw_payload"), dict) else {}
            ingest_payload = IngestRequest.model_validate(raw_payload)
            result = await _run_document_ingest_job(job_id, batch_id, ingest_payload)
            processed += len(ingest_payload.documents)

            for key in ("nodes", "edges", "alerts", "evidence"):
                agg[key] += int(result.get(key, 0) or 0)

            progress = round((processed / max(1, total_inputs)) * 100.0, 2)
            await storage.update_job(job_id, progress=progress, result=_merge_result(agg, stage="rebuilding"))

        await storage.update_job(job_id, status="success", progress=100.0, result=agg, finished_at=_now_utc())
    except asyncio.CancelledError:
        await storage.update_job(
            job_id,
            status="queued",
            error_message="Rebuild interrupted during shutdown and queued for recovery",
            started_at=None,
            finished_at=None,
        )
        raise
    except Exception as exc:
        await storage.update_job(
            job_id,
            status="failed",
            error_message=f"{type(exc).__name__}: {exc}",
            finished_at=_now_utc(),
        )
    finally:
        job_tasks.pop(job_id, None)


def _build_stats(nodes: Sequence[Dict[str, Any]], edges: Sequence[Dict[str, Any]]) -> GraphStats:
    type_counter = Counter(str(x.get("node_type", "Unknown")) for x in nodes)
    rel_counter = Counter(str(x.get("relation_type", "related_to")) for x in edges)
    return GraphStats(
        node_count=len(nodes),
        edge_count=len(edges),
        by_node_type=dict(type_counter),
        by_relation_type=dict(rel_counter),
    )


async def _submit_ingest_job(payload: IngestRequest, request: Request) -> IngestResponse:
    if payload.source != "module2":
        raise HTTPException(status_code=400, detail="module4 only accepts document sync from module2")
    if not payload.documents:
        raise HTTPException(status_code=400, detail="documents payload is required")
    tenant_id = _tenant_from_request(request, payload.tenant_id)
    source_batch_key = _derived_ingest_batch_key(payload, tenant_id=tenant_id)
    existing_batch = await storage.get_ingest_batch(
        tenant_id=tenant_id,
        source=payload.source,
        source_batch_key=source_batch_key,
    )
    if existing_batch and existing_batch.get("job_id"):
        existing_job = await storage.get_job(str(existing_batch.get("job_id")))
        if existing_job and str(existing_job.get("status") or "") in {"queued", "running", "success"}:
            if str(existing_job.get("status")) in {"queued", "running"}:
                raw_payload = existing_batch.get("raw_payload") if isinstance(existing_batch.get("raw_payload"), dict) else {}
                recover_payload = IngestRequest.model_validate(raw_payload or payload.model_dump(mode="json"))
                _schedule_ingest_job(str(existing_job["job_id"]), str(existing_batch["batch_id"]), recover_payload)
            return IngestResponse(
                job_id=str(existing_job["job_id"]),
                batch_id=str(existing_batch["batch_id"]),
                status=str(existing_job["status"]),
            )

    payload_data = payload.model_dump(mode="json")
    payload_data["tenant_id"] = tenant_id
    payload_data["source_batch_key"] = source_batch_key
    input_count = len(payload.documents)
    job = await storage.create_job(
        tenant_id=tenant_id,
        job_type="ingest",
        status="queued",
        payload={
            "source": payload.source,
            "source_batch_key": source_batch_key,
            "graph_mode": payload.graph_mode,
            "documents": len(payload.documents),
            "inputs": input_count,
        },
    )
    batch = await storage.create_ingest_batch(
        tenant_id=tenant_id,
        source=payload.source,
        source_batch_key=source_batch_key,
        job_id=str(job["job_id"]),
        raw_payload=payload_data,
    )
    effective_payload = IngestRequest.model_validate(payload_data)
    _schedule_ingest_job(str(job["job_id"]), str(batch["batch_id"]), effective_payload)
    return IngestResponse(job_id=str(job["job_id"]), batch_id=str(batch["batch_id"]), status=str(job["status"]))


@app.post("/module4/ingest", response_model=IngestResponse)
async def module4_ingest(payload: IngestRequest, request: Request) -> IngestResponse:
    return await _submit_ingest_job(payload, request)


@app.get("/module4/jobs/{job_id}", response_model=JobResponse)
async def module4_job_status(job_id: str, request: Request, tenant_id: str = Query(default="")) -> JobResponse:
    resolved_tenant = _tenant_from_request(request, tenant_id)
    row = await storage.get_job(job_id, tenant_id=resolved_tenant)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(**row)


@app.post("/module4/rebuild", response_model=RebuildResponse)
async def module4_rebuild(body: RebuildRequest, request: Request) -> RebuildResponse:
    tenant_id = _tenant_from_request(request, body.tenant_id)
    batches = await storage.list_ingest_batches(tenant_id=tenant_id)
    if not batches:
        raise HTTPException(status_code=404, detail="No ingest batches found for tenant")

    documents = _count_inputs_from_batches(batches)
    job = await storage.create_job(
        tenant_id=tenant_id,
        job_type="rebuild_graph",
        status="queued",
        payload={"tenant_id": tenant_id, "batches": len(batches), "documents": documents},
    )
    _schedule_rebuild_job(str(job["job_id"]), RebuildRequest(tenant_id=tenant_id))
    return RebuildResponse(
        job_id=str(job["job_id"]),
        status=str(job["status"]),
        batches=len(batches),
        documents=documents,
    )


@app.get("/module4/graph/files", response_model=GraphFileListResponse)
async def module4_graph_files(
    request: Request,
    tenant_id: str = Query(default=""),
    status: str = Query(default=""),
    limit: int = 200,
) -> GraphFileListResponse:
    resolved_tenant = _tenant_from_request(request, tenant_id)
    rows = await storage.list_graph_files(
        tenant_id=resolved_tenant,
        status=str(status or "").strip() or None,
        limit=limit,
    )
    return GraphFileListResponse(items=[GraphFileItem(**_normalize_graph_file_row(row)) for row in rows])


@app.get("/module4/graph/files/{file_hash}", response_model=GraphFileDetailResponse)
async def module4_graph_file_detail(file_hash: str, request: Request, tenant_id: str = Query(default="")) -> GraphFileDetailResponse:
    resolved_tenant = _tenant_from_request(request, tenant_id)
    row = await storage.get_graph_file(tenant_id=resolved_tenant, file_hash=file_hash)
    if not row:
        raise HTTPException(status_code=404, detail="Graph file not found")
    return GraphFileDetailResponse(item=GraphFileItem(**_normalize_graph_file_row(row)))


@app.get("/module4/graph/files/{file_hash}/view", response_model=GraphResponse)
async def module4_graph_file_view(
    file_hash: str,
    request: Request,
    tenant_id: str = Query(default=""),
    node_types: str = "",
    relation_types: str = "",
    limit_nodes: int = 800,
    limit_edges: int = 1500,
) -> GraphResponse:
    resolved_tenant = _tenant_from_request(request, tenant_id)
    graph_file = await storage.get_graph_file(tenant_id=resolved_tenant, file_hash=file_hash)
    if not graph_file:
        raise HTTPException(status_code=404, detail="Graph file not found")
    nodes_raw, edges_raw = await storage.list_graph_for_file(
        tenant_id=resolved_tenant,
        file_hash=file_hash,
        node_types=_parse_csv_list(node_types),
        relation_types=_parse_csv_list(relation_types),
        limit_nodes=limit_nodes,
        limit_edges=limit_edges,
    )
    node_rows = [_normalize_graph_node_row(row) for row in nodes_raw]
    edge_rows = [_normalize_graph_edge_row(row) for row in edges_raw]
    return GraphResponse(
        nodes=[GraphNode(**row) for row in node_rows],
        edges=[GraphEdge(**row) for row in edge_rows],
        stats=_build_stats(node_rows, edge_rows),
        source="storage:file",
        workspace_id=str(graph_file.get("workspace_id") or "") or None,
    )


@app.get("/module4/graph/files/{file_hash}/neighborhood/{node_id}", response_model=GraphResponse)
async def module4_graph_file_neighborhood(
    file_hash: str,
    node_id: str,
    request: Request,
    tenant_id: str = Query(default=""),
    depth: int = 1,
    relation_types: str = "",
    limit: int = 1200,
) -> GraphResponse:
    resolved_tenant = _tenant_from_request(request, tenant_id)
    graph_file = await storage.get_graph_file(tenant_id=resolved_tenant, file_hash=file_hash)
    if not graph_file:
        raise HTTPException(status_code=404, detail="Graph file not found")
    nodes_raw, edges_raw = await storage.list_neighborhood_for_file(
        tenant_id=resolved_tenant,
        file_hash=file_hash,
        node_id=node_id,
        depth=depth,
        relation_types=_parse_csv_list(relation_types),
        limit=limit,
    )
    if not nodes_raw:
        raise HTTPException(status_code=404, detail="Node not found in graph file")
    node_rows = [_normalize_graph_node_row(row) for row in nodes_raw]
    edge_rows = [_normalize_graph_edge_row(row) for row in edges_raw]
    return GraphResponse(
        nodes=[GraphNode(**row) for row in node_rows],
        edges=[GraphEdge(**row) for row in edge_rows],
        stats=_build_stats(node_rows, edge_rows),
        source="storage:file",
        workspace_id=str(graph_file.get("workspace_id") or "") or None,
    )


@app.get("/module4/graph/files/{file_hash}/node/{node_id}", response_model=GraphNodeDetailResponse)
async def module4_graph_file_node_detail(
    file_hash: str,
    node_id: str,
    request: Request,
    tenant_id: str = Query(default=""),
    depth: int = 1,
    relation_types: str = "",
    limit: int = 240,
) -> GraphNodeDetailResponse:
    resolved_tenant = _tenant_from_request(request, tenant_id)
    graph_file = await storage.get_graph_file(tenant_id=resolved_tenant, file_hash=file_hash)
    if not graph_file:
        raise HTTPException(status_code=404, detail="Graph file not found")
    nodes_raw, edges_raw = await storage.list_neighborhood_for_file(
        tenant_id=resolved_tenant,
        file_hash=file_hash,
        node_id=node_id,
        depth=depth,
        relation_types=_parse_csv_list(relation_types),
        limit=limit,
    )
    if not nodes_raw:
        raise HTTPException(status_code=404, detail="Node not found in graph file")
    node_rows = [_normalize_graph_node_row(row) for row in nodes_raw]
    edge_rows = [_normalize_graph_edge_row(row) for row in edges_raw]
    node_items = [GraphNode(**row) for row in node_rows]
    target_node_row = next((row for row in nodes_raw if str(row.get("node_id") or "") == node_id), {})
    subject_edge_rows = [
        row
        for row in edges_raw
        if str(row.get("source_node_id") or "") == node_id or str(row.get("target_node_id") or "") == node_id
    ]
    evidence_rows = await _load_evidence_for_node(resolved_tenant, target_node_row, limit=12) if target_node_row else []
    edge_evidence_rows = await _load_edge_evidence_for_edges(
        resolved_tenant,
        subject_edge_rows,
        limit_per_edge=4,
        edge_cap=10,
    )
    return GraphNodeDetailResponse(
        node=next((item for item in node_items if item.node_id == node_id), None),
        graph=GraphResponse(
            nodes=node_items,
            edges=[GraphEdge(**row) for row in edge_rows],
            stats=_build_stats(node_rows, edge_rows),
            source="storage:file",
            workspace_id=str(graph_file.get("workspace_id") or "") or None,
        ),
        file=GraphFileItem(**_normalize_graph_file_row(graph_file)),
        evidence=[EvidenceItem(**row) for row in evidence_rows],
        edge_evidence={
            edge_id: [EvidenceItem(**item) for item in items]
            for edge_id, items in edge_evidence_rows.items()
        },
    )


@app.get("/module4/graph", response_model=GraphResponse)
async def module4_graph(
    request: Request,
    tenant_id: str = Query(default=""),
    node_types: str = "",
    relation_types: str = "",
    limit_nodes: int = 800,
    limit_edges: int = 1500,
) -> GraphResponse:
    resolved_tenant = _tenant_from_request(request, tenant_id)
    nodes_raw, edges_raw = await storage.list_graph(
        tenant_id=resolved_tenant,
        node_types=_parse_csv_list(node_types),
        relation_types=_parse_csv_list(relation_types),
        limit_nodes=limit_nodes,
        limit_edges=limit_edges,
    )
    node_rows = [_normalize_graph_node_row(row) for row in nodes_raw]
    edge_rows = [_normalize_graph_edge_row(row) for row in edges_raw]
    nodes = [GraphNode(**row) for row in node_rows]
    edges = [GraphEdge(**row) for row in edge_rows]
    return GraphResponse(
        nodes=nodes,
        edges=edges,
        stats=_build_stats(node_rows, edge_rows),
        source="storage:tenant",
        workspace_id=None,
    )


@app.get("/module4/graph/neighborhood/{node_id}", response_model=GraphResponse)
async def module4_neighborhood(
    node_id: str,
    request: Request,
    tenant_id: str = Query(default=""),
    depth: int = 1,
    relation_types: str = "",
    limit: int = 1200,
) -> GraphResponse:
    resolved_tenant = _tenant_from_request(request, tenant_id)
    nodes_raw, edges_raw = await storage.list_neighborhood(
        tenant_id=resolved_tenant,
        node_id=node_id,
        depth=depth,
        relation_types=_parse_csv_list(relation_types),
        limit=limit,
    )
    if not nodes_raw:
        raise HTTPException(status_code=404, detail="Node not found")
    selected_nodes = [_normalize_graph_node_row(row) for row in nodes_raw]
    selected_edges = [_normalize_graph_edge_row(row) for row in edges_raw]
    return GraphResponse(
        nodes=[GraphNode(**row) for row in selected_nodes],
        edges=[GraphEdge(**row) for row in selected_edges],
        stats=_build_stats(selected_nodes, selected_edges),
        source="storage:tenant",
        workspace_id=None,
    )


@app.get("/module4/alerts", response_model=AlertListResponse)
async def module4_alerts(
    request: Request,
    tenant_id: str = Query(default=""),
    status: Optional[str] = None,
    severity: Optional[str] = None,
    rule_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> AlertListResponse:
    resolved_tenant = _tenant_from_request(request, tenant_id)
    total, items = await storage.list_alerts(
        tenant_id=resolved_tenant,
        status=status,
        severity=severity,
        rule_id=rule_id,
        page=page,
        page_size=page_size,
    )
    normalized = [_normalize_alert_row(row) for row in items]
    return AlertListResponse(total=total, items=[AlertItem(**row) for row in normalized])


@app.post("/module4/alerts/{alert_id}/ack", response_model=AlertActionResponse)
async def module4_alert_ack(alert_id: str, body: AlertActionRequest, request: Request) -> AlertActionResponse:
    tenant_id = _tenant_from_request(request, body.tenant_id)
    row = await storage.update_alert_status(
        alert_id=alert_id,
        tenant_id=tenant_id,
        status="ack",
        actor=body.actor,
        comment=body.comment,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertActionResponse(ok=True, alert=AlertItem(**_normalize_alert_row(row)))


@app.post("/module4/alerts/{alert_id}/resolve", response_model=AlertActionResponse)
async def module4_alert_resolve(alert_id: str, body: AlertResolveRequest, request: Request) -> AlertActionResponse:
    tenant_id = _tenant_from_request(request, body.tenant_id)
    row = await storage.update_alert_status(
        alert_id=alert_id,
        tenant_id=tenant_id,
        status="resolved",
        actor=body.actor,
        comment=body.comment,
        resolution=body.resolution,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertActionResponse(ok=True, alert=AlertItem(**_normalize_alert_row(row)))


@app.get("/module4/evidence", response_model=EvidenceListResponse)
async def module4_evidence(
    request: Request,
    tenant_id: str = Query(default=""),
    doc_id: Optional[str] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> EvidenceListResponse:
    resolved_tenant = _tenant_from_request(request, tenant_id)
    total, items = await storage.list_evidence(
        tenant_id=resolved_tenant,
        doc_id=doc_id,
        object_type=object_type,
        object_id=object_id,
        page=page,
        page_size=page_size,
    )
    normalized = [_normalize_evidence_row(item) for item in items]
    return EvidenceListResponse(total=total, items=[EvidenceItem(**item) for item in normalized])


@app.get("/module4/evidence/edge/{edge_id}", response_model=EvidenceListResponse)
async def module4_edge_evidence(
    edge_id: str,
    request: Request,
    tenant_id: str = Query(default=""),
    page: int = 1,
    page_size: int = 50,
) -> EvidenceListResponse:
    resolved_tenant = _tenant_from_request(request, tenant_id)
    total, items = await storage.list_edge_evidence(
        tenant_id=resolved_tenant,
        edge_id=edge_id,
        page=page,
        page_size=page_size,
    )
    normalized = [_normalize_evidence_row(item) for item in items]
    return EvidenceListResponse(total=total, items=[EvidenceItem(**item) for item in normalized])


@app.get("/module4/rules", response_model=RuleListResponse)
async def module4_rules(enabled_only: bool = False) -> RuleListResponse:
    items = await storage.list_rules(enabled_only=enabled_only)
    normalized = [_normalize_rule_row(row) for row in items]
    return RuleListResponse(items=[RuleItem(**row) for row in normalized])


@app.put("/module4/rules/{rule_id}", response_model=RuleUpsertResponse)
async def module4_rule_upsert(rule_id: str, body: RuleUpsertRequest) -> RuleUpsertResponse:
    all_rules = await storage.list_rules()
    current = next((r for r in all_rules if str(r.get("rule_id")) == rule_id), None)
    next_version = int(current.get("version", 1)) + 1 if current else 1
    row = await storage.upsert_rule(
        rule_id=rule_id,
        name=body.name,
        severity=body.severity,
        rule_kind=body.rule_kind,
        expr=body.expr,
        enabled=body.enabled,
        version=next_version,
    )
    return RuleUpsertResponse(ok=True, rule=RuleItem(**_normalize_rule_row(row)))


@app.post("/module4/explain", response_model=ExplainResponse)
async def module4_explain(body: ExplainRequest, request: Request) -> ExplainResponse:
    tenant_id = _tenant_from_request(request, body.tenant_id)
    if body.alert_id:
        alert = await storage.get_alert(body.alert_id, tenant_id=tenant_id)
        if not alert:
            raise HTTPException(status_code=404, detail="告警不存在")
        payload = alert.get("payload") if isinstance(alert.get("payload"), dict) else {}
        evidence_rows: List[Dict[str, Any]] = []
        steps = [
            f"命中规则：{alert.get('rule_id')}",
            f"风险等级：{alert.get('severity')}",
            f"风险分：{_to_float(alert.get('risk_score')):.2f}",
        ]
        subject_node_id = str(alert.get("subject_node_id") or "").strip()
        if subject_node_id:
            node_row = await storage.get_node(tenant_id=tenant_id, node_id=subject_node_id)
            if node_row:
                normalized_node = _normalize_graph_node_row(node_row)
                evidence_rows = await _load_evidence_for_node(tenant_id, node_row, limit=8)
                steps.append(f"关联节点：{normalized_node['display_name']}（{normalized_node['node_type']}）")
                if evidence_rows:
                    steps.append(f"已为该节点解析出 {len(evidence_rows)} 条直接证据。")
        if payload and not evidence_rows:
            steps.append("未解析到直接证据，当前返回告警载荷中的上下文信息供人工复核。")
        return ExplainResponse(
            conclusion=str(alert.get("summary") or "该告警需要进一步核查。"),
            reasoning_steps=steps,
            evidence=evidence_rows or ([payload] if payload else []),
        )

    if body.node_id:
        node_row = await storage.get_node(tenant_id=tenant_id, node_id=body.node_id)
        if not node_row:
            raise HTTPException(status_code=404, detail="节点不存在")
        evidence_rows = await _load_evidence_for_node(tenant_id, node_row, limit=10)
        nodes_raw, edges_raw = await storage.list_neighborhood(
            tenant_id=tenant_id,
            node_id=body.node_id,
            depth=1,
            relation_types=None,
            limit=40,
        )
        normalized_node = _normalize_graph_node_row(node_row)
        return ExplainResponse(
            conclusion=(
                f"节点“{normalized_node['display_name']}”（{normalized_node['node_type']}）"
                f"当前关联 {len(evidence_rows)} 条证据、{len(edges_raw)} 条邻接关系。"
            ),
            reasoning_steps=[
                f"已加载节点“{normalized_node['display_name']}”（{normalized_node['node_type']}）。",
                f"在 1 跳邻域内共检索到 {max(0, len(nodes_raw) - 1)} 个相邻节点、{len(edges_raw)} 条关系。",
                f"基于节点类型与图谱血缘信息，共回溯到 {len(evidence_rows)} 条证据。",
            ],
            evidence=evidence_rows or [normalized_node],
        )

    raise HTTPException(status_code=400, detail="必须提供 alert_id 或 node_id")


@app.post("/module4/simulate", response_model=SimulateResponse)
async def module4_simulate(body: SimulateRequest, request: Request) -> SimulateResponse:
    tenant_id = _tenant_from_request(request, body.tenant_id)
    params = body.params if isinstance(body.params, dict) else {}
    scope = body.scope if isinstance(body.scope, dict) else {}
    contexts = await _simulation_contexts_from_request(tenant_id, body)
    rules = await storage.list_rules(enabled_only=True)
    deterministic_rules = [rule for rule in rules if str(rule.get("rule_kind") or "").lower() in SUPPORTED_RULE_KINDS]

    explicit_rule_ids = set(_scope_values(scope.get("rule_ids")))
    single_rule_id = str(scope.get("rule_id") or "").strip()
    if single_rule_id:
        explicit_rule_ids.add(single_rule_id)
    if explicit_rule_ids:
        deterministic_rules = [rule for rule in deterministic_rules if str(rule.get("rule_id") or "") in explicit_rule_ids]

    if contexts:
        changed_alerts: List[Dict[str, Any]] = []
        impacts: List[Dict[str, Any]] = []
        hits_by_rule: Counter[str] = Counter()
        hits_by_severity: Counter[str] = Counter()

        for context in contexts:
            scope_name = str(context.get("__scope") or "document")
            applicable_rules = [rule for rule in deterministic_rules if _rule_scope(rule) == scope_name]
            context_label = str(context.get("__label") or scope_name)
            for rule in applicable_rules:
                hit = _evaluate_rule_hit(rule, context)
                if not hit:
                    continue
                hits_by_rule[str(hit["rule_id"])] += 1
                hits_by_severity[str(hit["severity"])] += 1
                changed_alerts.append(
                    {
                        "scenario_name": body.scenario_name,
                        "context_label": context_label,
                        "scope": scope_name,
                        "rule_id": hit["rule_id"],
                        "severity": hit["severity"],
                        "title": hit["title"],
                        "summary": hit["summary"],
                        "simulated_risk_score": round(_to_float(hit["risk_score"]), 3),
                        "source_alert_id": str(context.get("__source_alert_id") or "") or None,
                    }
                )

        impacts.append({"metric": "simulated_contexts", "value": len(contexts)})
        impacts.append({"metric": "evaluated_rules", "value": len(deterministic_rules)})
        impacts.append({"metric": "simulated_hits", "value": len(changed_alerts)})
        if hits_by_rule:
            impacts.append({"metric": "hits_by_rule", "value": dict(hits_by_rule)})
        if hits_by_severity:
            impacts.append({"metric": "hits_by_severity", "value": dict(hits_by_severity)})

        summary = (
            f"场景“{body.scenario_name}”已完成模拟，共评估 {len(contexts)} 个上下文、"
            f"{len(deterministic_rules)} 条确定性规则，命中 {len(changed_alerts)} 条结果。"
        )
        return SimulateResponse(impacts=impacts, changed_alerts=changed_alerts, summary=summary)

    multiplier = _to_float(params.get("risk_multiplier", 1.0), 1.0)
    rule_id_filter = next(iter(explicit_rule_ids), None) if explicit_rule_ids else None
    total, alerts = await storage.list_alerts(
        tenant_id=tenant_id,
        status="open",
        severity=None,
        rule_id=rule_id_filter,
        page=1,
        page_size=100,
    )
    changed_alerts: List[Dict[str, Any]] = []
    impacts: List[Dict[str, Any]] = []
    for alert in alerts:
        original = _to_float(alert.get("risk_score"), 0.0)
        simulated = max(0.0, min(100.0, original * multiplier))
        changed_alerts.append(
            {
                "alert_id": alert.get("alert_id"),
                "rule_id": alert.get("rule_id"),
                "original_risk_score": round(original, 3),
                "simulated_risk_score": round(simulated, 3),
                "delta": round(simulated - original, 3),
            }
        )
    if changed_alerts:
        avg_delta = sum(item["delta"] for item in changed_alerts) / len(changed_alerts)
    impacts.append({"metric": "avg_risk_delta", "value": round(avg_delta, 3)})
    impacts.append({"metric": "mode", "value": "legacy_multiplier"})
    impacts.append({"metric": "supported_rule_kinds", "value": sorted(SUPPORTED_RULE_KINDS)})
    summary = (
        f"场景“{body.scenario_name}”已按旧版风险倍率模式完成模拟，"
        f"涉及 {min(total, len(changed_alerts))} 条开放告警。"
    )
    return SimulateResponse(impacts=impacts, changed_alerts=changed_alerts, summary=summary)


@app.get("/module4/healthz", response_model=HealthzResponse)
async def module4_healthz(probe: str = Query(default="basic")) -> HealthzResponse:
    diag = storage.diagnostics()
    queue_size = await storage.queue_size()
    check_remote = str(probe or "").strip().lower() == "deep"
    runtime_probe = await asyncio.to_thread(
        graphrag_indexer.probe,
        workspace_builder.runtime,
        workspace_builder.neo4j,
        check_remote=check_remote,
    )
    return HealthzResponse(
        status="ok" if bool(diag.get("db_connected")) else "failed",
        db_connected=bool(diag.get("db_connected")),
        jobs_in_queue=queue_size,
        last_connect_error=str(diag.get("last_connect_error") or "") or None,
        graphrag=runtime_probe.as_dict(),
        projection_runtime=_projection_runtime_status(),
        now=_now_utc(),
    )
