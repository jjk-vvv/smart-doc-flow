from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
from collections import Counter
from datetime import datetime, timezone
from string import Formatter
from typing import Any, Dict, List, Optional, Sequence

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query
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
    GraphNode,
    GraphResponse,
    GraphStats,
    HealthzResponse,
    IngestRequest,
    IngestResponse,
    JobResponse,
    RuleItem,
    RuleListResponse,
    RuleUpsertRequest,
    RuleUpsertResponse,
    SimulateRequest,
    SimulateResponse,
)

load_dotenv()

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
RULE_KIND = {"deterministic", "semantic", "anomaly"}


def _cors_origins() -> tuple[list[str], bool]:
    raw = os.getenv("MODULE4_CORS_ORIGINS", "http://localhost:3000,http://localhost:3002,http://localhost:5173")
    origins = [item.strip() for item in raw.split(",") if item.strip()]
    allow_all = "*" in origins
    return origins or ["http://localhost:3000"], allow_all


def _default_tenant() -> str:
    return os.getenv("MODULE4_DEFAULT_TENANT", "default").strip() or "default"


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


app = FastAPI(title="A23 Module 4 - Global Knowledge Graph & Risk Intelligence", version="1.1.0")
CORS_ORIGINS, CORS_ALLOW_ALL = _cors_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if CORS_ALLOW_ALL else CORS_ORIGINS,
    allow_credentials=not CORS_ALLOW_ALL,
    allow_methods=["*"],
    allow_headers=["*"],
)

storage = Module4Storage(os.getenv("MODULE4_DATABASE_DSN", "postgresql://postgres:postgres@localhost:5432/a23"))
job_tasks: Dict[str, asyncio.Task[Any]] = {}


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
    )


async def _process_document(
    *,
    tenant_id: str,
    batch_id: str,
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

    doc_row = await storage.upsert_document(
        tenant_id=tenant_id,
        batch_id=batch_id,
        file_name=file_name,
        file_hash=file_hash,
        track=track,
        diagnostics=diagnostics,
    )
    doc_node = await storage.upsert_node(
        tenant_id=tenant_id,
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
        )
        field_node_ids[str(field_name)] = str(field_node["node_id"])
        counters["nodes"] += 1

        await storage.upsert_edge(
            tenant_id=tenant_id,
            source_node_id=str(doc_node["node_id"]),
            target_node_id=str(field_node["node_id"]),
            relation_type="extracts",
            direction="out",
            attrs={"field_name": field_name},
            confidence=max(0.1, confidence),
            risk_score=max(0.0, 1.0 - confidence),
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
            )
            counters["alerts"] += 1

    if errors:
        risk_node = await storage.upsert_node(
            tenant_id=tenant_id,
            node_type="Risk",
            canonical_key=f"{file_hash}:errors:{_risk_key('|'.join(errors))}",
            display_name=f"{file_name} parsing errors",
            attrs={"errors": errors},
            confidence=0.99,
        )
        counters["nodes"] += 1
        await storage.upsert_edge(
            tenant_id=tenant_id,
            source_node_id=str(doc_node["node_id"]),
            target_node_id=str(risk_node["node_id"]),
            relation_type="has_risk",
            direction="out",
            attrs={"kind": "errors"},
            confidence=0.95,
            risk_score=92.0,
        )
        counters["edges"] += 1

    for warning in soft_warnings[:6]:
        risk_node = await storage.upsert_node(
            tenant_id=tenant_id,
            node_type="Risk",
            canonical_key=f"{file_hash}:warning:{_risk_key(warning)}",
            display_name=f"{file_name} warning",
            attrs={"warning": warning},
            confidence=0.8,
        )
        counters["nodes"] += 1
        await storage.upsert_edge(
            tenant_id=tenant_id,
            source_node_id=str(doc_node["node_id"]),
            target_node_id=str(risk_node["node_id"]),
            relation_type="has_warning",
            direction="out",
            attrs={"kind": "soft_warning"},
            confidence=0.75,
            risk_score=35.0,
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
        )
        counters["evidence"] += 1

        object_type = str(hit_map.get("object_type") or "").strip().lower()
        object_id = str(hit_map.get("object_id") or "").strip()
        if object_type in {"table", "figure"} and object_id:
            target_node = await storage.upsert_node(
                tenant_id=tenant_id,
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
            )
            counters["nodes"] += 1
            edge = await storage.upsert_edge(
                tenant_id=tenant_id,
                source_node_id=str(doc_node["node_id"]),
                target_node_id=str(target_node["node_id"]),
                relation_type="contains",
                direction="out",
                attrs={"object_type": object_type},
                confidence=_to_float(hit_map.get("confidence"), 0.6),
                risk_score=0.0,
            )
            counters["edges"] += 1
            await storage.link_edge_evidence(edge_id=str(edge["edge_id"]), evidence_id=str(evidence["evidence_id"]))

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
                node_type=target_type.title(),
                canonical_key=f"{file_hash}:{target_type}:{target_id}",
                display_name=target_id,
                attrs={"file_hash": file_hash, "type": target_type},
                confidence=_to_float(target_map.get("confidence"), 0.6),
            )
            counters["nodes"] += 1
            await storage.upsert_edge(
                tenant_id=tenant_id,
                source_node_id=src_id,
                target_node_id=str(tgt_node["node_id"]),
                relation_type="links_to",
                direction="out",
                attrs={"match": target_map.get("match"), "page": target_map.get("page")},
                confidence=_to_float(target_map.get("confidence"), 0.6),
                risk_score=0.0,
            )
            counters["edges"] += 1

    return counters


async def _run_ingest_job(job_id: str, batch_id: str, payload: IngestRequest) -> None:
    tenant_id = payload.tenant_id or _default_tenant()
    documents = payload.documents
    total = len(documents)
    agg = {"nodes": 0, "edges": 0, "alerts": 0, "evidence": 0, "documents": total}

    rules = await storage.list_rules(enabled_only=True)
    deterministic_rules = [rule for rule in rules if str(rule.get("rule_kind")).lower() in SUPPORTED_RULE_KINDS]
    field_rules = [rule for rule in deterministic_rules if _rule_scope(rule) == "field"]
    document_rules = [rule for rule in deterministic_rules if _rule_scope(rule) == "document"]

    await storage.update_job(job_id, status="running", started_at=_now_utc(), progress=1.0)
    try:
        for idx, doc in enumerate(documents, start=1):
            counters = await _process_document(
                tenant_id=tenant_id,
                batch_id=batch_id,
                doc=doc,
                field_rules=field_rules,
                document_rules=document_rules,
            )
            for key, value in counters.items():
                agg[key] += int(value)
            progress = round((idx / max(1, total)) * 100.0, 2)
            await storage.update_job(job_id, progress=progress, result=agg)

        await storage.update_job(job_id, status="success", progress=100.0, result=agg, finished_at=_now_utc())
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


@app.on_event("startup")
async def startup_event() -> None:
    await storage.connect()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    for task in list(job_tasks.values()):
        if not task.done():
            task.cancel()
    await storage.close()


@app.post("/module4/ingest", response_model=IngestResponse)
async def module4_ingest(payload: IngestRequest) -> IngestResponse:
    tenant_id = payload.tenant_id or _default_tenant()
    job = await storage.create_job(
        tenant_id=tenant_id,
        job_type="ingest",
        status="queued",
        payload={"source": payload.source, "source_batch_key": payload.source_batch_key, "documents": len(payload.documents)},
    )
    batch = await storage.create_ingest_batch(
        tenant_id=tenant_id,
        source=payload.source,
        source_batch_key=payload.source_batch_key,
        job_id=str(job["job_id"]),
        raw_payload=payload.model_dump(mode="json"),
    )
    task = asyncio.create_task(_run_ingest_job(str(job["job_id"]), str(batch["batch_id"]), payload))
    job_tasks[str(job["job_id"])] = task
    return IngestResponse(job_id=str(job["job_id"]), batch_id=str(batch["batch_id"]), status=str(job["status"]))


@app.get("/module4/jobs/{job_id}", response_model=JobResponse)
async def module4_job_status(job_id: str) -> JobResponse:
    row = await storage.get_job(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobResponse(**row)


@app.get("/module4/graph", response_model=GraphResponse)
async def module4_graph(
    tenant_id: str = Query(default=_default_tenant()),
    node_types: str = "",
    relation_types: str = "",
    limit_nodes: int = 800,
    limit_edges: int = 1500,
) -> GraphResponse:
    nodes_raw, edges_raw = await storage.list_graph(
        tenant_id=tenant_id,
        node_types=_parse_csv_list(node_types),
        relation_types=_parse_csv_list(relation_types),
        limit_nodes=limit_nodes,
        limit_edges=limit_edges,
    )
    node_rows = [_normalize_graph_node_row(row) for row in nodes_raw]
    edge_rows = [_normalize_graph_edge_row(row) for row in edges_raw]
    nodes = [GraphNode(**row) for row in node_rows]
    edges = [GraphEdge(**row) for row in edge_rows]
    return GraphResponse(nodes=nodes, edges=edges, stats=_build_stats(node_rows, edge_rows))


@app.get("/module4/graph/neighborhood/{node_id}", response_model=GraphResponse)
async def module4_neighborhood(
    node_id: str,
    tenant_id: str = Query(default=_default_tenant()),
    depth: int = 1,
    relation_types: str = "",
    limit: int = 1200,
) -> GraphResponse:
    nodes_raw, edges_raw = await storage.list_graph(
        tenant_id=tenant_id,
        node_types=None,
        relation_types=_parse_csv_list(relation_types),
        limit_nodes=limit,
        limit_edges=limit * 3,
    )
    node_rows = [_normalize_graph_node_row(row) for row in nodes_raw]
    edge_rows = [_normalize_graph_edge_row(row) for row in edges_raw]
    node_map = {str(n["node_id"]): n for n in node_rows}
    if node_id not in node_map:
        raise HTTPException(status_code=404, detail="Node not found")
    depth = max(1, min(4, int(depth)))
    visited = {node_id}
    frontier = {node_id}
    selected_edges: List[Dict[str, Any]] = []
    for _ in range(depth):
        next_frontier = set()
        for edge in edge_rows:
            src = str(edge.get("source_node_id"))
            tgt = str(edge.get("target_node_id"))
            if src in frontier or tgt in frontier:
                selected_edges.append(edge)
                if src not in visited:
                    visited.add(src)
                    next_frontier.add(src)
                if tgt not in visited:
                    visited.add(tgt)
                    next_frontier.add(tgt)
        frontier = next_frontier
        if not frontier:
            break
    selected_nodes = [node_map[nid] for nid in visited if nid in node_map]
    selected_edges = selected_edges[: limit * 2]
    return GraphResponse(
        nodes=[GraphNode(**row) for row in selected_nodes],
        edges=[GraphEdge(**row) for row in selected_edges],
        stats=_build_stats(selected_nodes, selected_edges),
    )


@app.get("/module4/alerts", response_model=AlertListResponse)
async def module4_alerts(
    tenant_id: str = Query(default=_default_tenant()),
    status: Optional[str] = None,
    severity: Optional[str] = None,
    rule_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> AlertListResponse:
    total, items = await storage.list_alerts(
        tenant_id=tenant_id,
        status=status,
        severity=severity,
        rule_id=rule_id,
        page=page,
        page_size=page_size,
    )
    normalized = [_normalize_alert_row(row) for row in items]
    return AlertListResponse(total=total, items=[AlertItem(**row) for row in normalized])


@app.post("/module4/alerts/{alert_id}/ack", response_model=AlertActionResponse)
async def module4_alert_ack(alert_id: str, body: AlertActionRequest) -> AlertActionResponse:
    row = await storage.update_alert_status(
        alert_id=alert_id,
        status="ack",
        actor=body.actor,
        comment=body.comment,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertActionResponse(ok=True, alert=AlertItem(**_normalize_alert_row(row)))


@app.post("/module4/alerts/{alert_id}/resolve", response_model=AlertActionResponse)
async def module4_alert_resolve(alert_id: str, body: AlertResolveRequest) -> AlertActionResponse:
    row = await storage.update_alert_status(
        alert_id=alert_id,
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
    tenant_id: str = Query(default=_default_tenant()),
    doc_id: Optional[str] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> EvidenceListResponse:
    total, items = await storage.list_evidence(
        tenant_id=tenant_id,
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
    tenant_id: str = Query(default=_default_tenant()),
    page: int = 1,
    page_size: int = 50,
) -> EvidenceListResponse:
    total, items = await storage.list_edge_evidence(
        tenant_id=tenant_id,
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
async def module4_explain(body: ExplainRequest) -> ExplainResponse:
    if body.alert_id:
        alert = await storage.get_alert(body.alert_id)
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        payload = alert.get("payload") if isinstance(alert.get("payload"), dict) else {}
        steps = [
            f"Matched rule: {alert.get('rule_id')}",
            f"Severity: {alert.get('severity')}",
            f"Risk score: {_to_float(alert.get('risk_score')):.2f}",
        ]
        if payload:
            steps.append("Use /module4/evidence to inspect source snippets and document anchors.")
        return ExplainResponse(
            conclusion=str(alert.get("summary") or ""),
            reasoning_steps=steps,
            evidence=[payload] if payload else [],
        )

    if body.node_id:
        return ExplainResponse(
            conclusion="Node neighborhood is available via /module4/graph/neighborhood/{node_id}.",
            reasoning_steps=[
                "Load the node and adjacent edges",
                "Group by relation_type and node_type",
                "Trace evidence on high risk edges",
            ],
            evidence=[{"node_id": body.node_id, "target_node_id": body.target_node_id}],
        )

    raise HTTPException(status_code=400, detail="alert_id or node_id is required")


@app.post("/module4/simulate", response_model=SimulateResponse)
async def module4_simulate(body: SimulateRequest) -> SimulateResponse:
    multiplier = _to_float(body.params.get("risk_multiplier", 1.0), 1.0)
    total, alerts = await storage.list_alerts(
        tenant_id=body.tenant_id,
        status="open",
        severity=None,
        rule_id=None,
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
                "original_risk_score": round(original, 3),
                "simulated_risk_score": round(simulated, 3),
                "delta": round(simulated - original, 3),
            }
        )
    if changed_alerts:
        avg_delta = sum(item["delta"] for item in changed_alerts) / len(changed_alerts)
        impacts.append({"metric": "avg_risk_delta", "value": round(avg_delta, 3)})
    summary = f"Scenario {body.scenario_name} evaluated. Open alerts involved: {min(total, len(changed_alerts))}."
    return SimulateResponse(impacts=impacts, changed_alerts=changed_alerts, summary=summary)


@app.get("/module4/healthz", response_model=HealthzResponse)
async def module4_healthz() -> HealthzResponse:
    diag = storage.diagnostics()
    queue_size = await storage.queue_size()
    return HealthzResponse(
        status="ok",
        db_connected=bool(diag.get("db_connected")),
        degraded_memory_mode=bool(diag.get("degraded_memory_mode")),
        jobs_in_queue=queue_size,
        now=_now_utc(),
    )
