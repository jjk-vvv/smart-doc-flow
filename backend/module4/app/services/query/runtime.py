from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from fastapi import HTTPException

from ..graphrag.query_adapter import (
    GraphRAGArtifactGraph,
    artifact_neighborhood,
    filter_artifact_graph,
    load_artifact_graph_snapshot,
)

from ...schemas import (
    AlertActionResponse,
    AlertItem,
    AlertListResponse,
    EvidenceItem,
    EvidenceListResponse,
    GraphEdge,
    GraphFileDetailResponse,
    GraphFileItem,
    GraphFileListResponse,
    GraphNode,
    GraphNodeDetailResponse,
    GraphResponse,
    GraphStats,
    RuleItem,
    RuleListResponse,
    RuleUpsertRequest,
    RuleUpsertResponse,
)


@dataclass(frozen=True)
class Module4QueryRuntimeHelpers:
    default_tenant: Callable[[], str]
    risk_key: Callable[[str], str]
    to_float: Callable[[Any, float], float]
    to_int: Callable[[Any, int], int]
    as_dict: Callable[[Any], Dict[str, Any]]
    as_list: Callable[[Any], List[Any]]
    artifact_summary_snippet: Callable[..., str]
    normalize_artifact_attrs_for_response: Callable[[str, Dict[str, Any]], Dict[str, Any]]
    artifact_display_name_from_attrs: Callable[[str], str]
    edge_direction: set[str]
    alert_severity: set[str]
    alert_status: set[str]
    rule_kind: set[str]


_GRAPH_RENDER_ELIGIBLE_SUFFIXES = {".docx", ".pdf", ".txt", ".md"}
_GENERIC_COMMUNITY_RE = re.compile(r"^\s*community[\s_\-]*\d+\s*$", re.IGNORECASE)
_GENERIC_REPORT_RE = re.compile(r"^\s*report[\s_\-]*[a-z0-9\-]+\s*$", re.IGNORECASE)
_HEXISH_RE = re.compile(r"^[0-9a-f][0-9a-f\-]{11,}$", re.IGNORECASE)
_ARTIFACT_ENTITY_PREFIX_RE = re.compile(
    r"^(?:photo:|table[_\-]|figure[_\-]|image[_\-]|chart[_\-]|sheet[_\-]|workbook[_\-])",
    re.IGNORECASE,
)
_METRIC_ONLY_RE = re.compile(
    r"^(?:比上年)?(?:增长|下降|提高|增加|减少|增产|减产|上涨|回落)?\s*\d+(?:\.\d+)?\s*(?:%|‰)?$",
    re.IGNORECASE,
)
_ZH_UNNAMED_COMMUNITY = "\u672a\u547d\u540d\u793e\u533a"
_ZH_COMMUNITY_REPORT = "\u793e\u533a\u62a5\u544a"
_ZH_EVIDENCE_NODE = "\u5019\u9009\u8bc1\u636e\u8282\u70b9"


def _contains_cjk(value: Any) -> bool:
    for char in str(value or ""):
        code = ord(char)
        if 0x4E00 <= code <= 0x9FFF:
            return True
    return False


def _is_placeholder_community_title(title: str, community_id: str) -> bool:
    normalized = str(title or "").strip()
    if not normalized:
        return True
    lower_title = normalized.lower()
    lower_id = str(community_id or "").strip().lower()
    community_token = lower_id.split("::")[-1] if lower_id else ""
    if _GENERIC_COMMUNITY_RE.match(normalized):
        return True
    if lower_title in {"community", "community report", "report"}:
        return True
    if _HEXISH_RE.fullmatch(lower_title):
        return True
    return lower_title in {lower_id, community_token} and bool(
        community_token and (_HEXISH_RE.fullmatch(community_token) or community_token.isdigit())
    )


def _is_placeholder_report_title(title: str, report_id: str) -> bool:
    normalized = str(title or "").strip()
    if not normalized:
        return True
    lower_title = normalized.lower()
    lower_id = str(report_id or "").strip().lower()
    report_token = lower_id.split("::")[-1] if lower_id else ""
    if _GENERIC_REPORT_RE.match(normalized):
        return True
    if _HEXISH_RE.fullmatch(lower_title):
        return True
    return lower_title in {lower_id, report_token} and bool(
        report_token and (_HEXISH_RE.fullmatch(report_token) or report_token.isdigit())
    )


def _is_low_value_entity_label(label: str) -> bool:
    normalized = str(label or "").strip()
    if not normalized:
        return True
    if _HEXISH_RE.fullmatch(normalized):
        return True
    if _METRIC_ONLY_RE.fullmatch(normalized):
        return True
    if _ARTIFACT_ENTITY_PREFIX_RE.match(normalized):
        return True
    lowered = normalized.lower()
    if any(token in lowered for token in ("docx_media", "table schema", "chart schema", "table summary", "chart summary")):
        return True
    if lowered in {"document_title", "model connectivity check"}:
        return True
    return False


def _sanitize_graph_display_name(
    *,
    display_name: str,
    node_type: str,
    node_id: str,
    attrs: Dict[str, Any],
) -> tuple[str, bool]:
    normalized = str(display_name or "").strip()
    type_key = str(node_type or "").strip().lower()
    graphrag_id = str(attrs.get("graphrag_id") or "").strip()
    community_title = str(attrs.get("community_title") or "").strip()
    community_id = graphrag_id or node_id

    if type_key == "community":
        if _is_placeholder_community_title(normalized, community_id):
            if community_title and not _is_placeholder_community_title(community_title, community_id):
                return community_title, False
            return _ZH_UNNAMED_COMMUNITY, False
        return normalized, False

    if type_key == "communityreport":
        if _is_placeholder_report_title(normalized, graphrag_id or node_id):
            if community_title:
                return (
                    community_title
                    if community_title.endswith("\u62a5\u544a")
                    else f"{community_title}\u62a5\u544a"
                ), False
            return _ZH_COMMUNITY_REPORT, False
        return normalized, False

    if type_key == "entity":
        if _is_low_value_entity_label(normalized):
            return "", True
        return normalized, False

    if normalized and _HEXISH_RE.fullmatch(normalized) and type_key not in {"document", "chunk", "textunit"}:
        return "", True

    return normalized, False


def _is_graph_render_eligible_file_name(file_name: Any) -> bool:
    normalized = str(file_name or "").strip().lower()
    if not normalized:
        return False
    return Path(normalized).suffix in _GRAPH_RENDER_ELIGIBLE_SUFFIXES


def _expanded_graph_file_fetch_limit(limit: int) -> int:
    requested = max(1, int(limit))
    # Query runtime only renders graph-eligible files. We over-fetch candidates to avoid
    # returning an empty list when recent rows are dominated by non-eligible files (for
    # example xlsx entries from mixed ingestion history).
    return min(500, max(requested, requested * 4, requested + 20))


async def _list_graph_render_eligible_files(
    *,
    storage: Any,
    tenant_id: str,
    status: Optional[str],
    limit: int,
) -> List[Dict[str, Any]]:
    requested_limit = max(1, int(limit))
    fetch_limit = _expanded_graph_file_fetch_limit(requested_limit)
    rows = await storage.list_graph_files(
        tenant_id=tenant_id,
        status=str(status or "").strip() or None,
        limit=fetch_limit,
    )
    filtered_rows = [row for row in rows if _is_graph_render_eligible_file_name(row.get("file_name"))]
    return filtered_rows[:requested_limit]


def normalize_graph_node_row(*, helpers: Module4QueryRuntimeHelpers, row: Dict[str, Any]) -> Dict[str, Any]:
    node_id = str(row.get("node_id") or "").strip()
    canonical_key = str(row.get("canonical_key") or "").strip() or node_id
    node_type = str(row.get("node_type") or "Unknown")
    attrs = helpers.normalize_artifact_attrs_for_response(node_type, helpers.as_dict(row.get("attrs")))
    display_name = str(row.get("display_name") or "").strip() or canonical_key or "node"
    display_name = helpers.artifact_display_name_from_attrs(display_name, node_type=node_type, attrs=attrs)
    display_name, label_suppressed = _sanitize_graph_display_name(
        display_name=display_name,
        node_type=node_type,
        node_id=node_id,
        attrs=attrs,
    )
    if not display_name:
        if str(node_type or "").strip().lower() == "entity":
            display_name = _ZH_EVIDENCE_NODE
        else:
            display_name = canonical_key or "node"
    if label_suppressed:
        attrs = {**attrs, "label_quality": "suppressed"}
    return {
        "node_id": node_id or helpers.risk_key(display_name),
        "node_type": node_type,
        "canonical_key": canonical_key or display_name,
        "display_name": display_name,
        "confidence": helpers.to_float(row.get("confidence"), 0.0),
        "attrs": attrs,
        "updated_at": row.get("updated_at"),
    }


def normalize_graph_edge_row(*, helpers: Module4QueryRuntimeHelpers, row: Dict[str, Any]) -> Dict[str, Any]:
    direction = str(row.get("direction") or "out")
    if direction not in helpers.edge_direction:
        direction = "out"
    return {
        "edge_id": str(row.get("edge_id") or helpers.risk_key(json.dumps(row, ensure_ascii=False))),
        "source_node_id": str(row.get("source_node_id") or ""),
        "target_node_id": str(row.get("target_node_id") or ""),
        "relation_type": str(row.get("relation_type") or "related_to"),
        "direction": direction,
        "confidence": helpers.to_float(row.get("confidence"), 0.0),
        "risk_score": helpers.to_float(row.get("risk_score"), 0.0),
        "attrs": helpers.as_dict(row.get("attrs")),
        "updated_at": row.get("updated_at"),
    }


def normalize_projection_payload(*, helpers: Module4QueryRuntimeHelpers, value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None
    labels_raw = value.get("labels")
    labels = [str(item) for item in labels_raw if str(item).strip()] if isinstance(labels_raw, list) else []
    return {
        "status": str(value.get("status") or "").strip(),
        "projected_nodes": helpers.to_int(value.get("projected_nodes"), 0),
        "projected_edges": helpers.to_int(value.get("projected_edges"), 0),
        "source_node_count": helpers.to_int(value.get("source_node_count"), 0),
        "source_edge_count": helpers.to_int(value.get("source_edge_count"), 0),
        "skipped_reason": str(value.get("skipped_reason") or "").strip() or None,
        "error_message": str(value.get("error_message") or "").strip() or None,
        "labels": labels,
        "relationship_type": str(value.get("relationship_type") or "MODULE4_EDGE"),
    }


def projection_runtime_status(
    *,
    workspace_builder: Any,
    neo4j_graph_projector: Any,
) -> Dict[str, Any]:
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


def normalize_graph_file_row(*, helpers: Module4QueryRuntimeHelpers, row: Dict[str, Any]) -> Dict[str, Any]:
    metadata = helpers.as_dict(row.get("metadata"))
    projection = normalize_projection_payload(helpers=helpers, value=metadata.get("projection"))
    return {
        "graph_file_id": str(row.get("graph_file_id") or ""),
        "tenant_id": str(row.get("tenant_id") or helpers.default_tenant()),
        "file_hash": str(row.get("file_hash") or ""),
        "file_name": str(row.get("file_name") or "unknown"),
        "workspace_id": str(row.get("workspace_id") or "") or None,
        "graph_mode": str(row.get("graph_mode") or "hybrid"),
        "source": str(row.get("source") or "module2"),
        "status": str(row.get("status") or "queued"),
        "current_job_id": str(row.get("current_job_id") or "") or None,
        "active_version_id": str(row.get("active_version_id") or "") or None,
        "last_error": str(row.get("last_error") or "") or None,
        "node_count": helpers.to_int(row.get("node_count"), 0),
        "edge_count": helpers.to_int(row.get("edge_count"), 0),
        "metadata": metadata,
        "projection": projection,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "last_indexed_at": row.get("last_indexed_at"),
    }


def normalize_alert_row(*, helpers: Module4QueryRuntimeHelpers, row: Dict[str, Any]) -> Dict[str, Any]:
    severity = str(row.get("severity") or "yellow").lower()
    if severity not in helpers.alert_severity:
        severity = "yellow"
    status = str(row.get("status") or "open").lower()
    if status not in helpers.alert_status:
        status = "open"
    title = str(row.get("title") or row.get("rule_id") or "Alert")
    summary = str(row.get("summary") or title)
    return {
        "alert_id": str(row.get("alert_id") or helpers.risk_key(title + summary)),
        "rule_id": str(row.get("rule_id") or "UNKNOWN"),
        "severity": severity,
        "status": status,
        "subject_node_id": str(row.get("subject_node_id")) if row.get("subject_node_id") else None,
        "title": title,
        "summary": summary,
        "risk_score": helpers.to_float(row.get("risk_score"), 0.0),
        "payload": helpers.as_dict(row.get("payload")),
        "detected_at": row.get("detected_at"),
        "acknowledged_at": row.get("acknowledged_at"),
        "resolved_at": row.get("resolved_at"),
        "updated_at": row.get("updated_at"),
    }


def normalize_rule_row(*, helpers: Module4QueryRuntimeHelpers, row: Dict[str, Any]) -> Dict[str, Any]:
    severity = str(row.get("severity") or "yellow").lower()
    if severity not in helpers.alert_severity:
        severity = "yellow"
    rule_kind = str(row.get("rule_kind") or "deterministic").lower()
    if rule_kind not in helpers.rule_kind:
        rule_kind = "deterministic"
    return {
        "rule_id": str(row.get("rule_id") or "UNKNOWN"),
        "name": str(row.get("name") or row.get("rule_id") or "rule"),
        "severity": severity,
        "rule_kind": rule_kind,
        "expr": helpers.as_dict(row.get("expr")),
        "enabled": bool(row.get("enabled", True)),
        "version": helpers.to_int(row.get("version"), 1),
        "updated_at": row.get("updated_at"),
    }


def normalize_evidence_row(*, helpers: Module4QueryRuntimeHelpers, row: Dict[str, Any]) -> Dict[str, Any]:
    object_type = str(row.get("object_type") or "field")
    object_id = str(row.get("object_id") or "")
    page_no = helpers.to_int(row.get("page_no"), 0) if row.get("page_no") is not None else None
    locator = helpers.as_dict(row.get("locator"))
    snippet = helpers.artifact_summary_snippet(
        object_type=object_type,
        object_id=object_id,
        raw_snippet=row.get("snippet"),
        locator=locator,
        page_no=page_no,
    )
    return {
        "evidence_id": str(row.get("evidence_id") or helpers.risk_key(json.dumps(row, ensure_ascii=False))),
        "doc_id": str(row.get("doc_id") or ""),
        "object_type": object_type,
        "object_id": object_id,
        "ref_id": str(row.get("ref_id")) if row.get("ref_id") is not None else None,
        "page_no": page_no,
        "snippet": snippet,
        "locator": locator,
        "bbox": helpers.as_list(row.get("bbox")),
        "artifact_url": str(row.get("artifact_url")) if row.get("artifact_url") else None,
        "confidence": helpers.to_float(row.get("confidence"), 0.0),
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


def _is_graphrag_artifact_node(attrs: Dict[str, Any]) -> bool:
    graph_source = str(attrs.get("graph_source") or "").strip().lower()
    return graph_source.startswith("graphrag_artifacts")


def _artifact_node_evidence_candidates(*, helpers: Module4QueryRuntimeHelpers, node_row: Dict[str, Any]) -> List[tuple[str, str]]:
    attrs = helpers.as_dict(node_row.get("attrs"))
    node_type = str(node_row.get("node_type") or "").strip().lower()
    display_name = str(node_row.get("display_name") or "").strip()
    graphrag_id = str(attrs.get("graphrag_id") or "").strip()
    report_id = str(attrs.get("report_id") or "").strip()
    file_hash = str(attrs.get("file_hash") or "").strip()

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
    elif node_type == "communityreport":
        _append_evidence_candidate(candidates, seen, "community", graphrag_id)
        _append_evidence_candidate(candidates, seen, "community_report", report_id or graphrag_id or display_name)
    elif node_type == "covariate":
        _append_evidence_candidate(candidates, seen, "covariate", graphrag_id or display_name)

    for relationship_id in helpers.as_list(attrs.get("relationship_ids")):
        _append_evidence_candidate(candidates, seen, "relationship", relationship_id)
    for text_unit_id in helpers.as_list(attrs.get("text_unit_ids")):
        _append_evidence_candidate(candidates, seen, "chunk", text_unit_id)
    for source_chunk_id in helpers.as_list(attrs.get("source_chunk_ids")):
        _append_evidence_candidate(candidates, seen, "chunk", source_chunk_id)
    for document_id in helpers.as_list(attrs.get("document_ids")):
        _append_evidence_candidate(candidates, seen, "document", document_id)

    return candidates


def node_evidence_candidates(*, helpers: Module4QueryRuntimeHelpers, node_row: Dict[str, Any]) -> List[tuple[str, str]]:
    attrs = helpers.as_dict(node_row.get("attrs"))
    node_type = str(node_row.get("node_type") or "").strip().lower()
    display_name = str(node_row.get("display_name") or "").strip()
    graphrag_id = str(attrs.get("graphrag_id") or "").strip()
    report_id = str(attrs.get("report_id") or "").strip()
    file_hash = str(attrs.get("file_hash") or "").strip()
    field_name = str(attrs.get("field_name") or "").strip()
    object_id = str(attrs.get("object_id") or "").strip()
    candidates: List[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    if _is_graphrag_artifact_node(attrs):
        for object_type_candidate, object_id_candidate in _artifact_node_evidence_candidates(
            helpers=helpers,
            node_row=node_row,
        ):
            _append_evidence_candidate(candidates, seen, object_type_candidate, object_id_candidate)

    for ref in helpers.as_list(attrs.get("evidence_refs")):
        ref_map = helpers.as_dict(ref)
        _append_evidence_candidate(
            candidates,
            seen,
            str(ref_map.get("object_type") or ""),
            ref_map.get("object_id"),
        )

    for field_ref in helpers.as_list(attrs.get("field_names")):
        _append_evidence_candidate(candidates, seen, "field", field_ref)

    for artifact_ref in helpers.as_list(attrs.get("artifact_refs")):
        artifact_map = helpers.as_dict(artifact_ref)
        artifact_type = str(artifact_map.get("type") or artifact_map.get("object_type") or "").strip().lower()
        artifact_id = artifact_map.get("id") or artifact_map.get("object_id")
        if artifact_type == "image":
            artifact_type = "figure"
        _append_evidence_candidate(candidates, seen, artifact_type, artifact_id)

    if node_type == "document":
        _append_evidence_candidate(candidates, seen, "document", graphrag_id or file_hash or display_name)
    elif node_type == "chunk":
        _append_evidence_candidate(candidates, seen, "chunk", graphrag_id or display_name)
    elif node_type == "entity":
        _append_evidence_candidate(candidates, seen, "entity", graphrag_id or display_name)
    elif node_type == "community":
        _append_evidence_candidate(candidates, seen, "community", graphrag_id or report_id or display_name)
    elif node_type == "communityreport":
        _append_evidence_candidate(candidates, seen, "community_report", report_id or graphrag_id or display_name)
    elif node_type == "covariate":
        _append_evidence_candidate(candidates, seen, "covariate", graphrag_id or display_name)
    elif node_type == "field":
        _append_evidence_candidate(candidates, seen, "field", field_name or display_name)
    elif node_type in {"table", "figure", "image"}:
        _append_evidence_candidate(candidates, seen, "figure" if node_type == "image" else node_type, object_id or display_name)
    elif node_type in {"businesscontext", "topic", "observation", "claim", "businessalert"}:
        for ref_field_name in helpers.as_list(attrs.get("field_names")):
            _append_evidence_candidate(candidates, seen, "field", ref_field_name)

    for chunk_id in helpers.as_list(attrs.get("text_unit_ids")):
        _append_evidence_candidate(candidates, seen, "chunk", chunk_id)
    for chunk_id in helpers.as_list(attrs.get("source_chunk_ids")):
        _append_evidence_candidate(candidates, seen, "chunk", chunk_id)
    for document_id in helpers.as_list(attrs.get("document_ids")):
        _append_evidence_candidate(candidates, seen, "document", document_id)

    return candidates


def _sort_normalized_evidence_rows(*, helpers: Module4QueryRuntimeHelpers, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        [dict(item) for item in rows],
        key=lambda item: (
            helpers.to_float(item.get("confidence"), 0.0),
            str(item.get("created_at") or ""),
            str(item.get("evidence_id") or ""),
        ),
        reverse=True,
    )


async def load_evidence_for_node(
    *,
    storage: Any,
    helpers: Module4QueryRuntimeHelpers,
    tenant_id: str,
    node_row: Dict[str, Any],
    limit: int = 10,
) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for object_type, object_id in node_evidence_candidates(helpers=helpers, node_row=node_row):
        _, rows = await storage.list_evidence(
            tenant_id=tenant_id,
            doc_id=None,
            object_type=object_type,
            object_id=object_id,
            page=1,
            page_size=max(limit, 10),
        )
        normalized_rows = _sort_normalized_evidence_rows(
            helpers=helpers,
            rows=[normalize_evidence_row(helpers=helpers, row=row) for row in rows],
        )
        for normalized in normalized_rows:
            evidence_id = str(normalized.get("evidence_id") or "")
            if not evidence_id or evidence_id in seen:
                continue
            seen.add(evidence_id)
            items.append(normalized)
            if len(items) >= limit:
                return items
    return items


def _append_artifact_edge_evidence_candidate(
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


def _artifact_edge_evidence_candidates(*, helpers: Module4QueryRuntimeHelpers, edge_row: Dict[str, Any]) -> List[tuple[str, str]]:
    relation_type = str(edge_row.get("relation_type") or "").strip().lower()
    attrs = helpers.as_dict(edge_row.get("attrs"))
    candidates: List[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    if relation_type == "related_to":
        _append_artifact_edge_evidence_candidate(candidates, seen, "relationship", attrs.get("graphrag_id"))
        for text_unit_id in helpers.as_list(attrs.get("text_unit_ids")):
            _append_artifact_edge_evidence_candidate(candidates, seen, "chunk", text_unit_id)
    elif relation_type == "has_entity":
        _append_artifact_edge_evidence_candidate(candidates, seen, "entity", attrs.get("entity_id"))
        _append_artifact_edge_evidence_candidate(candidates, seen, "chunk", attrs.get("text_unit_id"))
    elif relation_type == "has_chunk":
        _append_artifact_edge_evidence_candidate(candidates, seen, "chunk", attrs.get("chunk_id"))
        _append_artifact_edge_evidence_candidate(candidates, seen, "document", attrs.get("document_id"))
    elif relation_type == "in_community":
        _append_artifact_edge_evidence_candidate(candidates, seen, "community", attrs.get("community_id"))
        _append_artifact_edge_evidence_candidate(candidates, seen, "relationship", attrs.get("relationship_id"))
    elif relation_type == "has_report":
        _append_artifact_edge_evidence_candidate(candidates, seen, "community", attrs.get("community_id"))
        _append_artifact_edge_evidence_candidate(candidates, seen, "community_report", attrs.get("report_id"))
        _append_artifact_edge_evidence_candidate(candidates, seen, "community", attrs.get("report_id"))
    elif relation_type == "has_covariate":
        _append_artifact_edge_evidence_candidate(candidates, seen, "covariate", attrs.get("covariate_id"))
        _append_artifact_edge_evidence_candidate(candidates, seen, "chunk", attrs.get("text_unit_id"))
    return candidates


async def load_artifact_edge_evidence_for_edges(
    *,
    storage: Any,
    helpers: Module4QueryRuntimeHelpers,
    tenant_id: str,
    edge_rows: List[Dict[str, Any]],
    limit_per_edge: int = 4,
    edge_cap: int = 8,
) -> Dict[str, List[Dict[str, Any]]]:
    items: Dict[str, List[Dict[str, Any]]] = {}
    for edge_row in edge_rows[: max(1, edge_cap)]:
        edge_id = str(edge_row.get("edge_id") or "").strip()
        if not edge_id:
            continue

        evidences: List[Dict[str, Any]] = []
        seen_evidence_ids: set[str] = set()
        for object_type, object_id in _artifact_edge_evidence_candidates(helpers=helpers, edge_row=edge_row):
            _, rows = await storage.list_evidence(
                tenant_id=tenant_id,
                doc_id=None,
                object_type=object_type,
            object_id=object_id,
            page=1,
            page_size=max(limit_per_edge * 3, 8),
        )
            normalized_rows = _sort_normalized_evidence_rows(
                helpers=helpers,
                rows=[normalize_evidence_row(helpers=helpers, row=row) for row in rows],
            )
            for normalized in normalized_rows:
                evidence_id = str(normalized.get("evidence_id") or "").strip()
                if not evidence_id or evidence_id in seen_evidence_ids:
                    continue
                seen_evidence_ids.add(evidence_id)
                evidences.append(normalized)
                if len(evidences) >= limit_per_edge:
                    break
            if len(evidences) >= limit_per_edge:
                break
        if evidences:
            items[edge_id] = evidences[:limit_per_edge]
    return items


def build_stats(nodes: Sequence[Dict[str, Any]], edges: Sequence[Dict[str, Any]]) -> GraphStats:
    type_counter = Counter(str(x.get("node_type", "Unknown")) for x in nodes)
    rel_counter = Counter(str(x.get("relation_type", "related_to")) for x in edges)
    return GraphStats(
        node_count=len(nodes),
        edge_count=len(edges),
        by_node_type=dict(type_counter),
        by_relation_type=dict(rel_counter),
    )


def _sort_node_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        [dict(row) for row in rows],
        key=lambda row: (
            str(row.get("node_type") or ""),
            str(row.get("canonical_key") or ""),
            str(row.get("display_name") or ""),
            str(row.get("node_id") or ""),
        ),
    )


def _sort_edge_rows(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        [dict(row) for row in rows],
        key=lambda row: (
            str(row.get("relation_type") or ""),
            str(row.get("source_node_id") or ""),
            str(row.get("target_node_id") or ""),
            str(row.get("edge_id") or ""),
        ),
    )


def _artifact_graph_for_graph_file(graph_file: Dict[str, Any]) -> Optional[GraphRAGArtifactGraph]:
    return load_artifact_graph_snapshot(graph_file)


def _artifact_unavailable_detail(graph_file: Dict[str, Any]) -> str:
    file_hash = str(graph_file.get("file_hash") or "").strip()
    graph_file_id = str(graph_file.get("graph_file_id") or "").strip()
    workspace_id = str(graph_file.get("workspace_id") or "").strip()
    identifier = file_hash or graph_file_id or workspace_id or "unknown"
    return (
        "GraphRAG artifacts unavailable for this graph file "
        f"({identifier}). Rebuild/index this file and ensure create_final_* artifacts are generated."
    )


def _safe_graph_segment(value: Any, fallback: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return fallback
    chars = [ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in raw]
    cleaned = "".join(chars).strip("._-")
    return cleaned or fallback


def _namespace_artifact_rows_for_graph_file(
    *,
    graph_file: Dict[str, Any],
    nodes: Sequence[Dict[str, Any]],
    edges: Sequence[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    namespace = _safe_graph_segment(
        graph_file.get("file_hash") or graph_file.get("workspace_id") or graph_file.get("graph_file_id"),
        "graph_file",
    )
    node_id_map: Dict[str, str] = {}
    namespaced_nodes: List[Dict[str, Any]] = []
    for row in nodes:
        old_node_id = str(row.get("node_id") or "").strip()
        if not old_node_id:
            continue
        new_node_id = f"{namespace}::{old_node_id}"
        node_id_map[old_node_id] = new_node_id
        attrs = dict(row.get("attrs") or {}) if isinstance(row.get("attrs"), dict) else {}
        attrs.setdefault("file_hash", str(graph_file.get("file_hash") or ""))
        attrs.setdefault("graph_file_id", str(graph_file.get("graph_file_id") or ""))
        attrs.setdefault("workspace_id", str(graph_file.get("workspace_id") or "") or None)
        namespaced_nodes.append(
            {
                **dict(row),
                "node_id": new_node_id,
                "canonical_key": f"{namespace}::{str(row.get('canonical_key') or old_node_id)}",
                "attrs": attrs,
            }
        )

    namespaced_edges: List[Dict[str, Any]] = []
    for row in edges:
        old_src = str(row.get("source_node_id") or "").strip()
        old_tgt = str(row.get("target_node_id") or "").strip()
        if old_src not in node_id_map or old_tgt not in node_id_map:
            continue
        new_src = node_id_map[old_src]
        new_tgt = node_id_map[old_tgt]
        attrs = dict(row.get("attrs") or {}) if isinstance(row.get("attrs"), dict) else {}
        attrs.setdefault("file_hash", str(graph_file.get("file_hash") or ""))
        attrs.setdefault("graph_file_id", str(graph_file.get("graph_file_id") or ""))
        attrs.setdefault("workspace_id", str(graph_file.get("workspace_id") or "") or None)
        relation_type = str(row.get("relation_type") or "related_to")
        namespaced_edges.append(
            {
                **dict(row),
                "edge_id": f"{namespace}::{relation_type}::{new_src}::{new_tgt}",
                "source_node_id": new_src,
                "target_node_id": new_tgt,
                "attrs": attrs,
            }
        )
    return namespaced_nodes, namespaced_edges


async def _tenant_artifact_graph_rows(
    *,
    storage: Any,
    tenant_id: str,
    node_types: Sequence[str],
    relation_types: Sequence[str],
    limit_nodes: int,
    limit_edges: int,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool]:
    graph_files = await _list_graph_render_eligible_files(
        storage=storage,
        tenant_id=tenant_id,
        status="ready",
        limit=200,
    )
    aggregated_nodes: List[Dict[str, Any]] = []
    aggregated_edges: List[Dict[str, Any]] = []
    found_any_artifact = False

    for graph_file in graph_files:
        artifact_graph = _artifact_graph_for_graph_file(graph_file)
        if artifact_graph is None:
            continue
        found_any_artifact = True
        file_nodes, file_edges = filter_artifact_graph(
            graph=artifact_graph,
            node_types=node_types,
            relation_types=relation_types,
            limit_nodes=5000,
            limit_edges=10000,
        )
        namespaced_nodes, namespaced_edges = _namespace_artifact_rows_for_graph_file(
            graph_file=graph_file,
            nodes=file_nodes,
            edges=file_edges,
        )
        aggregated_nodes.extend(namespaced_nodes)
        aggregated_edges.extend(namespaced_edges)
        if len(aggregated_nodes) >= max(limit_nodes * 3, 5000):
            break

    if not found_any_artifact:
        return [], [], False

    sorted_nodes = _sort_node_rows(aggregated_nodes)
    limited_nodes = sorted_nodes[: max(1, int(limit_nodes))]
    node_ids = {str(row.get("node_id") or "") for row in limited_nodes}
    sorted_edges = _sort_edge_rows(
        [
            row
            for row in aggregated_edges
            if str(row.get("source_node_id") or "") in node_ids and str(row.get("target_node_id") or "") in node_ids
        ]
    )
    limited_edges = sorted_edges[: max(1, int(limit_edges))]
    return limited_nodes, limited_edges, True


async def _tenant_db_graph_rows(
    *,
    storage: Any,
    tenant_id: str,
    node_types: Sequence[str],
    relation_types: Sequence[str],
    limit_nodes: int,
    limit_edges: int,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool]:
    list_graph_files = getattr(storage, "list_graph_files", None)
    if not callable(list_graph_files):
        return [], [], False

    raw_graph_files = await _list_graph_render_eligible_files(
        storage=storage,
        tenant_id=tenant_id,
        status="ready",
        limit=200,
    )
    graph_files = [dict(row) for row in raw_graph_files]
    aggregated_nodes: List[Dict[str, Any]] = []
    aggregated_edges: List[Dict[str, Any]] = []
    found_any_db = False

    for graph_file in graph_files:
        db_nodes, db_edges, has_db_graph = await _db_graph_rows_for_graph_file(
            storage=storage,
            graph_file=graph_file,
            tenant_id=tenant_id,
            node_types=node_types,
            relation_types=relation_types,
            limit_nodes=5000,
            limit_edges=10000,
        )
        if not has_db_graph:
            continue
        found_any_db = True
        namespaced_nodes, namespaced_edges = _namespace_artifact_rows_for_graph_file(
            graph_file=graph_file,
            nodes=db_nodes,
            edges=db_edges,
        )
        aggregated_nodes.extend(namespaced_nodes)
        aggregated_edges.extend(namespaced_edges)
        if len(aggregated_nodes) >= max(limit_nodes * 3, 5000):
            break

    if not found_any_db:
        return [], [], False

    sorted_nodes = _sort_node_rows(aggregated_nodes)
    limited_nodes = sorted_nodes[: max(1, int(limit_nodes))]
    node_ids = {str(row.get("node_id") or "") for row in limited_nodes}
    sorted_edges = _sort_edge_rows(
        [
            row
            for row in aggregated_edges
            if str(row.get("source_node_id") or "") in node_ids and str(row.get("target_node_id") or "") in node_ids
        ]
    )
    limited_edges = sorted_edges[: max(1, int(limit_edges))]
    return limited_nodes, limited_edges, True


async def list_graph_files_response(
    *,
    storage: Any,
    helpers: Module4QueryRuntimeHelpers,
    tenant_id: str,
    status: Optional[str],
    limit: int,
) -> GraphFileListResponse:
    filtered_rows = await _list_graph_render_eligible_files(
        storage=storage,
        tenant_id=tenant_id,
        status=status,
        limit=limit,
    )
    return GraphFileListResponse(
        items=[GraphFileItem(**normalize_graph_file_row(helpers=helpers, row=row)) for row in filtered_rows]
    )


async def graph_file_detail_response(
    *,
    storage: Any,
    helpers: Module4QueryRuntimeHelpers,
    tenant_id: str,
    file_hash: str,
) -> GraphFileDetailResponse:
    row = await storage.get_graph_file(tenant_id=tenant_id, file_hash=file_hash)
    if not row:
        raise HTTPException(status_code=404, detail="Graph file not found")
    if not _is_graph_render_eligible_file_name(row.get("file_name")):
        raise HTTPException(status_code=404, detail="Graph file not found")
    return GraphFileDetailResponse(item=GraphFileItem(**normalize_graph_file_row(helpers=helpers, row=row)))


async def _db_graph_rows_for_graph_file(
    *,
    storage: Any,
    graph_file: Dict[str, Any],
    tenant_id: str,
    node_types: Sequence[str],
    relation_types: Sequence[str],
    limit_nodes: int,
    limit_edges: int,
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], bool]:
    graph_file_id = str(graph_file.get("graph_file_id") or "").strip()
    if not graph_file_id:
        return [], [], False
    list_nodes_by_graph_file = getattr(storage, "list_nodes_by_graph_file", None)
    list_edges_by_graph_file = getattr(storage, "list_edges_by_graph_file", None)
    if not callable(list_nodes_by_graph_file) or not callable(list_edges_by_graph_file):
        return [], [], False

    node_limit = max(1, int(limit_nodes))
    edge_limit = max(1, int(limit_edges))
    raw_nodes = await list_nodes_by_graph_file(
        tenant_id=tenant_id,
        graph_file_id=graph_file_id,
        node_types=node_types,
        limit=max(node_limit * 4, 2000),
    )
    if not raw_nodes:
        return [], [], False

    sorted_nodes = _sort_node_rows(raw_nodes)
    limited_nodes = sorted_nodes[:node_limit]
    node_ids = [str(row.get("node_id") or "") for row in limited_nodes if str(row.get("node_id") or "")]
    raw_edges = await list_edges_by_graph_file(
        tenant_id=tenant_id,
        graph_file_id=graph_file_id,
        relation_types=relation_types,
        node_ids=node_ids,
        limit=max(edge_limit * 4, 4000),
    )
    sorted_edges = _sort_edge_rows(raw_edges)
    limited_edges = sorted_edges[:edge_limit]
    return limited_nodes, limited_edges, True


async def _db_graph_snapshot_for_graph_file(
    *,
    storage: Any,
    graph_file: Dict[str, Any],
    tenant_id: str,
    relation_types: Sequence[str],
    limit_nodes: int,
    limit_edges: int,
) -> Optional[GraphRAGArtifactGraph]:
    graph_file_id = str(graph_file.get("graph_file_id") or "").strip()
    if not graph_file_id:
        return None
    list_nodes_by_graph_file = getattr(storage, "list_nodes_by_graph_file", None)
    list_edges_by_graph_file = getattr(storage, "list_edges_by_graph_file", None)
    if not callable(list_nodes_by_graph_file) or not callable(list_edges_by_graph_file):
        return None
    raw_nodes = await list_nodes_by_graph_file(
        tenant_id=tenant_id,
        graph_file_id=graph_file_id,
        node_types=[],
        limit=max(1, int(limit_nodes)),
    )
    if not raw_nodes:
        return None
    node_ids = [str(row.get("node_id") or "") for row in raw_nodes if str(row.get("node_id") or "")]
    raw_edges = await list_edges_by_graph_file(
        tenant_id=tenant_id,
        graph_file_id=graph_file_id,
        relation_types=relation_types,
        node_ids=node_ids,
        limit=max(1, int(limit_edges)),
    )
    return GraphRAGArtifactGraph(
        nodes=_sort_node_rows(raw_nodes),
        edges=_sort_edge_rows(raw_edges),
        workspace_id=str(graph_file.get("workspace_id") or "") or None,
        source="module4:db:file_scope",
    )


async def graph_file_view_response(
    *,
    storage: Any,
    helpers: Module4QueryRuntimeHelpers,
    tenant_id: str,
    file_hash: str,
    node_types: Sequence[str],
    relation_types: Sequence[str],
    limit_nodes: int,
    limit_edges: int,
) -> GraphResponse:
    graph_file = await storage.get_graph_file(tenant_id=tenant_id, file_hash=file_hash)
    if not graph_file:
        raise HTTPException(status_code=404, detail="Graph file not found")
    if not _is_graph_render_eligible_file_name(graph_file.get("file_name")):
        raise HTTPException(status_code=404, detail="Graph file not found")
    artifact_graph = _artifact_graph_for_graph_file(graph_file)
    if artifact_graph is not None:
        artifact_nodes, artifact_edges = filter_artifact_graph(
            graph=artifact_graph,
            node_types=node_types,
            relation_types=relation_types,
            limit_nodes=limit_nodes,
            limit_edges=limit_edges,
        )
        node_rows = [normalize_graph_node_row(helpers=helpers, row=row) for row in _sort_node_rows(artifact_nodes)]
        edge_rows = [normalize_graph_edge_row(helpers=helpers, row=row) for row in _sort_edge_rows(artifact_edges)]
        source_value = artifact_graph.source
        workspace_value = artifact_graph.workspace_id or str(graph_file.get("workspace_id") or "") or None
    else:
        db_nodes, db_edges, has_db_graph = await _db_graph_rows_for_graph_file(
            storage=storage,
            graph_file=graph_file,
            tenant_id=tenant_id,
            node_types=node_types,
            relation_types=relation_types,
            limit_nodes=limit_nodes,
            limit_edges=limit_edges,
        )
        if not has_db_graph:
            raise HTTPException(status_code=409, detail=_artifact_unavailable_detail(graph_file))
        node_rows = [normalize_graph_node_row(helpers=helpers, row=row) for row in _sort_node_rows(db_nodes)]
        edge_rows = [normalize_graph_edge_row(helpers=helpers, row=row) for row in _sort_edge_rows(db_edges)]
        source_value = "module4:db:file_scope"
        workspace_value = str(graph_file.get("workspace_id") or "") or None
    return GraphResponse(
        nodes=[GraphNode(**row) for row in node_rows],
        edges=[GraphEdge(**row) for row in edge_rows],
        stats=build_stats(node_rows, edge_rows),
        source=source_value,
        workspace_id=workspace_value,
    )


async def graph_file_neighborhood_response(
    *,
    storage: Any,
    helpers: Module4QueryRuntimeHelpers,
    tenant_id: str,
    file_hash: str,
    node_id: str,
    depth: int,
    relation_types: Sequence[str],
    limit: int,
) -> GraphResponse:
    graph_file = await storage.get_graph_file(tenant_id=tenant_id, file_hash=file_hash)
    if not graph_file:
        raise HTTPException(status_code=404, detail="Graph file not found")
    if not _is_graph_render_eligible_file_name(graph_file.get("file_name")):
        raise HTTPException(status_code=404, detail="Graph file not found")
    artifact_graph = _artifact_graph_for_graph_file(graph_file)
    if artifact_graph is None:
        artifact_graph = await _db_graph_snapshot_for_graph_file(
            storage=storage,
            graph_file=graph_file,
            tenant_id=tenant_id,
            relation_types=relation_types,
            limit_nodes=max(limit * 8, 4000),
            limit_edges=max(limit * 16, 12000),
        )
    if artifact_graph is None:
        raise HTTPException(status_code=409, detail=_artifact_unavailable_detail(graph_file))
    nodes_raw, edges_raw = artifact_neighborhood(
        graph=artifact_graph,
        node_id=node_id,
        depth=depth,
        relation_types=relation_types,
        limit=limit,
    )
    if not nodes_raw:
        raise HTTPException(status_code=404, detail="Node not found in graph file")
    node_rows = [normalize_graph_node_row(helpers=helpers, row=row) for row in _sort_node_rows(nodes_raw)]
    edge_rows = [normalize_graph_edge_row(helpers=helpers, row=row) for row in _sort_edge_rows(edges_raw)]
    return GraphResponse(
        nodes=[GraphNode(**row) for row in node_rows],
        edges=[GraphEdge(**row) for row in edge_rows],
        stats=build_stats(node_rows, edge_rows),
        source=artifact_graph.source,
        workspace_id=artifact_graph.workspace_id or str(graph_file.get("workspace_id") or "") or None,
    )


async def graph_file_node_detail_response(
    *,
    storage: Any,
    helpers: Module4QueryRuntimeHelpers,
    tenant_id: str,
    file_hash: str,
    node_id: str,
    depth: int,
    relation_types: Sequence[str],
    limit: int,
) -> GraphNodeDetailResponse:
    graph_file = await storage.get_graph_file(tenant_id=tenant_id, file_hash=file_hash)
    if not graph_file:
        raise HTTPException(status_code=404, detail="Graph file not found")
    if not _is_graph_render_eligible_file_name(graph_file.get("file_name")):
        raise HTTPException(status_code=404, detail="Graph file not found")
    artifact_graph = _artifact_graph_for_graph_file(graph_file)
    if artifact_graph is None:
        artifact_graph = await _db_graph_snapshot_for_graph_file(
            storage=storage,
            graph_file=graph_file,
            tenant_id=tenant_id,
            relation_types=relation_types,
            limit_nodes=max(limit * 8, 4000),
            limit_edges=max(limit * 16, 12000),
        )
    if artifact_graph is None:
        raise HTTPException(status_code=409, detail=_artifact_unavailable_detail(graph_file))
    nodes_raw, edges_raw = artifact_neighborhood(
        graph=artifact_graph,
        node_id=node_id,
        depth=depth,
        relation_types=relation_types,
        limit=limit,
    )
    if not nodes_raw:
        raise HTTPException(status_code=404, detail="Node not found in graph file")
    node_rows = [normalize_graph_node_row(helpers=helpers, row=row) for row in _sort_node_rows(nodes_raw)]
    edge_rows = [normalize_graph_edge_row(helpers=helpers, row=row) for row in _sort_edge_rows(edges_raw)]
    node_items = [GraphNode(**row) for row in node_rows]
    target_node_row = next((row for row in nodes_raw if str(row.get("node_id") or "") == node_id), {})
    subject_edge_rows = [
        row
        for row in edges_raw
        if str(row.get("source_node_id") or "") == node_id or str(row.get("target_node_id") or "") == node_id
    ]
    evidence_rows = await load_evidence_for_node(
        storage=storage,
        helpers=helpers,
        tenant_id=tenant_id,
        node_row=target_node_row,
        limit=12,
    ) if target_node_row else []
    edge_evidence_rows = await load_artifact_edge_evidence_for_edges(
        storage=storage,
        helpers=helpers,
        tenant_id=tenant_id,
        edge_rows=subject_edge_rows,
        limit_per_edge=4,
        edge_cap=10,
    )
    return GraphNodeDetailResponse(
        node=next((item for item in node_items if item.node_id == node_id), None),
        graph=GraphResponse(
            nodes=node_items,
            edges=[GraphEdge(**row) for row in edge_rows],
            stats=build_stats(node_rows, edge_rows),
            source=artifact_graph.source,
            workspace_id=artifact_graph.workspace_id or str(graph_file.get("workspace_id") or "") or None,
        ),
        file=GraphFileItem(**normalize_graph_file_row(helpers=helpers, row=graph_file)),
        evidence=[EvidenceItem(**row) for row in evidence_rows],
        edge_evidence={edge_id: [EvidenceItem(**item) for item in items] for edge_id, items in edge_evidence_rows.items()},
    )


async def graph_response(
    *,
    storage: Any,
    helpers: Module4QueryRuntimeHelpers,
    tenant_id: str,
    node_types: Sequence[str],
    relation_types: Sequence[str],
    limit_nodes: int,
    limit_edges: int,
) -> GraphResponse:
    artifact_nodes, artifact_edges, artifact_available = await _tenant_artifact_graph_rows(
        storage=storage,
        tenant_id=tenant_id,
        node_types=node_types,
        relation_types=relation_types,
        limit_nodes=limit_nodes,
        limit_edges=limit_edges,
    )
    if artifact_available:
        node_rows = [normalize_graph_node_row(helpers=helpers, row=row) for row in artifact_nodes]
        edge_rows = [normalize_graph_edge_row(helpers=helpers, row=row) for row in artifact_edges]
        return GraphResponse(
            nodes=[GraphNode(**row) for row in node_rows],
            edges=[GraphEdge(**row) for row in edge_rows],
            stats=build_stats(node_rows, edge_rows),
            source="graphrag:artifacts:tenant",
            workspace_id=None,
        )

    db_nodes, db_edges, db_available = await _tenant_db_graph_rows(
        storage=storage,
        tenant_id=tenant_id,
        node_types=node_types,
        relation_types=relation_types,
        limit_nodes=limit_nodes,
        limit_edges=limit_edges,
    )
    if db_available:
        node_rows = [normalize_graph_node_row(helpers=helpers, row=row) for row in db_nodes]
        edge_rows = [normalize_graph_edge_row(helpers=helpers, row=row) for row in db_edges]
        return GraphResponse(
            nodes=[GraphNode(**row) for row in node_rows],
            edges=[GraphEdge(**row) for row in edge_rows],
            stats=build_stats(node_rows, edge_rows),
            source="module4:db:tenant",
            workspace_id=None,
        )

    node_rows: List[Dict[str, Any]] = []
    edge_rows: List[Dict[str, Any]] = []
    return GraphResponse(
        nodes=[GraphNode(**row) for row in node_rows],
        edges=[GraphEdge(**row) for row in edge_rows],
        stats=build_stats(node_rows, edge_rows),
        source="graphrag:artifacts:tenant",
        workspace_id=None,
    )


async def neighborhood_response(
    *,
    storage: Any,
    helpers: Module4QueryRuntimeHelpers,
    tenant_id: str,
    node_id: str,
    depth: int,
    relation_types: Sequence[str],
    limit: int,
) -> GraphResponse:
    artifact_nodes, artifact_edges, artifact_available = await _tenant_artifact_graph_rows(
        storage=storage,
        tenant_id=tenant_id,
        node_types=[],
        relation_types=relation_types,
        limit_nodes=max(limit * 4, 400),
        limit_edges=max(limit * 8, 800),
    )
    graph_nodes = artifact_nodes
    graph_edges = artifact_edges
    graph_source = "graphrag:artifacts:tenant"
    if not artifact_available:
        db_nodes, db_edges, db_available = await _tenant_db_graph_rows(
            storage=storage,
            tenant_id=tenant_id,
            node_types=[],
            relation_types=relation_types,
            limit_nodes=max(limit * 4, 400),
            limit_edges=max(limit * 8, 800),
        )
        if not db_available:
            raise HTTPException(status_code=404, detail="Node not found in tenant artifact graph")
        graph_nodes = db_nodes
        graph_edges = db_edges
        graph_source = "module4:db:tenant"

    artifact_graph = GraphRAGArtifactGraph(
        nodes=graph_nodes,
        edges=graph_edges,
        workspace_id=None,
        source=graph_source,
    )
    nodes_raw, edges_raw = artifact_neighborhood(
        graph=artifact_graph,
        node_id=node_id,
        depth=depth,
        relation_types=relation_types,
        limit=limit,
    )
    if not nodes_raw:
        raise HTTPException(status_code=404, detail="Node not found in tenant artifact graph")
    node_rows = [normalize_graph_node_row(helpers=helpers, row=row) for row in _sort_node_rows(nodes_raw)]
    edge_rows = [normalize_graph_edge_row(helpers=helpers, row=row) for row in _sort_edge_rows(edges_raw)]
    return GraphResponse(
        nodes=[GraphNode(**row) for row in node_rows],
        edges=[GraphEdge(**row) for row in edge_rows],
        stats=build_stats(node_rows, edge_rows),
        source=graph_source,
        workspace_id=None,
    )


async def alerts_response(
    *,
    storage: Any,
    helpers: Module4QueryRuntimeHelpers,
    tenant_id: str,
    status: Optional[str],
    severity: Optional[str],
    rule_id: Optional[str],
    page: int,
    page_size: int,
) -> AlertListResponse:
    total, items = await storage.list_alerts(
        tenant_id=tenant_id,
        status=status,
        severity=severity,
        rule_id=rule_id,
        page=page,
        page_size=page_size,
    )
    normalized = [normalize_alert_row(helpers=helpers, row=row) for row in items]
    return AlertListResponse(total=total, items=[AlertItem(**row) for row in normalized])


async def alert_action_response(
    *,
    storage: Any,
    helpers: Module4QueryRuntimeHelpers,
    alert_id: str,
    tenant_id: str,
    status: str,
    actor: str,
    comment: Optional[str],
    resolution: Optional[str] = None,
) -> AlertActionResponse:
    row = await storage.update_alert_status(
        alert_id=alert_id,
        tenant_id=tenant_id,
        status=status,
        actor=actor,
        comment=comment,
        resolution=resolution,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertActionResponse(ok=True, alert=AlertItem(**normalize_alert_row(helpers=helpers, row=row)))


async def evidence_response(
    *,
    storage: Any,
    helpers: Module4QueryRuntimeHelpers,
    tenant_id: str,
    doc_id: Optional[str],
    object_type: Optional[str],
    object_id: Optional[str],
    page: int,
    page_size: int,
) -> EvidenceListResponse:
    total, items = await storage.list_evidence(
        tenant_id=tenant_id,
        doc_id=doc_id,
        object_type=object_type,
        object_id=object_id,
        page=page,
        page_size=page_size,
    )
    normalized = [normalize_evidence_row(helpers=helpers, row=item) for item in items]
    return EvidenceListResponse(total=total, items=[EvidenceItem(**item) for item in normalized])


async def edge_evidence_response(
    *,
    storage: Any,
    helpers: Module4QueryRuntimeHelpers,
    tenant_id: str,
    edge_id: str,
    page: int,
    page_size: int,
) -> EvidenceListResponse:
    total, items = await storage.list_edge_evidence(
        tenant_id=tenant_id,
        edge_id=edge_id,
        page=page,
        page_size=page_size,
    )
    normalized = [normalize_evidence_row(helpers=helpers, row=item) for item in items]
    return EvidenceListResponse(total=total, items=[EvidenceItem(**item) for item in normalized])


async def rules_response(
    *,
    storage: Any,
    helpers: Module4QueryRuntimeHelpers,
    enabled_only: bool,
) -> RuleListResponse:
    items = await storage.list_rules(enabled_only=enabled_only)
    normalized = [normalize_rule_row(helpers=helpers, row=row) for row in items]
    return RuleListResponse(items=[RuleItem(**row) for row in normalized])


async def rule_upsert_response(
    *,
    storage: Any,
    helpers: Module4QueryRuntimeHelpers,
    rule_id: str,
    body: RuleUpsertRequest,
) -> RuleUpsertResponse:
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
    return RuleUpsertResponse(ok=True, rule=RuleItem(**normalize_rule_row(helpers=helpers, row=row)))
