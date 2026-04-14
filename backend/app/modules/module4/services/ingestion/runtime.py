from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Optional, Sequence

from ...schemas import IngestRequest, IngestResponse, RebuildRequest

from ..graphrag.indexer import GraphRAGIndexError
from ..graphrag.importer import GraphRAGArtifactImporter
from ..graphrag.workspace import WorkspaceSourceFile
from .text_corpus import _compose_document_text


_GRAPHRAG_ARTIFACT_PATHS: dict[str, tuple[str, tuple[str, ...]]] = {
    "create_base_text_units": ("artifacts", ("create_base_text_units.parquet", "create_final_text_units.parquet", "text_units.parquet")),
    "create_base_extracted_entities": (
        "artifacts",
        ("create_base_extracted_entities.parquet", "create_summarized_entities.parquet", "create_final_entities.parquet", "entities.parquet"),
    ),
    "create_final_entities": ("artifacts", ("create_final_entities.parquet", "entities.parquet")),
    "create_final_relationships": ("artifacts", ("create_final_relationships.parquet", "relationships.parquet")),
    "create_final_communities": ("artifacts", ("create_final_communities.parquet", "communities.parquet")),
    "create_final_community_reports": ("artifacts", ("create_final_community_reports.parquet", "community_reports.parquet")),
}

_PARTIAL_ARTIFACT_MARKERS: tuple[tuple[str, ...], ...] = (
    ("create_base_text_units.parquet", "create_final_text_units.parquet", "text_units.parquet"),
    ("create_base_extracted_entities.parquet", "create_summarized_entities.parquet", "create_final_entities.parquet", "entities.parquet"),
)

_SUSPICIOUS_TEXT_MARKERS = ("�", "Ã", "Â", "Ð", "Ñ", "æ", "ç", "¤", "�")
_GRAPH_ELIGIBLE_SUFFIXES = {".docx", ".pdf", ".txt", ".md"}


@dataclass(frozen=True)
class Module4IngestRuntimeHelpers:
    default_tenant: Callable[[], str]
    now_utc: Callable[[], datetime]
    risk_key: Callable[[str], str]
    workspace_builder_getter: Optional[Callable[[], Any]] = None
    graphrag_indexer_getter: Optional[Callable[[], Any]] = None


ProcessDocumentCallback = Callable[..., Awaitable[Dict[str, Any]]]
RunDocumentIngestJobCallback = Callable[[str, str, IngestRequest], Awaitable[Dict[str, Any]]]
ScheduleIngestJobCallback = Callable[[str, str, IngestRequest], None]
ScheduleRebuildJobCallback = Callable[[str, RebuildRequest], None]
DerivedIngestBatchKeyCallback = Callable[[IngestRequest, Optional[str]], str]
UpdateJobStageCallback = Callable[..., Awaitable[None]]

_GRAPHRAG_IMPORTER = GraphRAGArtifactImporter()


@dataclass(frozen=True)
class DocumentGraphBuildError(RuntimeError):
    message: str
    diagnostics: Dict[str, Any]

    def __str__(self) -> str:
        return self.message


def _allow_partial_import_after_index_failure() -> bool:
    raw = str(os.getenv("MODULE4_GRAPHRAG_ALLOW_PARTIAL_IMPORT", "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _allow_document_fallback_graph() -> bool:
    raw = str(os.getenv("MODULE4_INGEST_ALLOW_DOCUMENT_FALLBACK", "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _recover_rebuild_jobs_enabled() -> bool:
    raw = str(os.getenv("MODULE4_RECOVER_REBUILD_JOBS", "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _workspace_result_meta(result: Any) -> Dict[str, Any]:
    if result is None:
        return {}
    return {
        "workspace_id": str(getattr(result, "workspace_id", "") or "").strip() or None,
        "workspace_dir": str(getattr(result, "workspace_dir", "") or "").strip() or None,
        "manifest_path": str(getattr(result, "manifest_path", "") or "").strip() or None,
    }


def _index_result_meta(result: Any) -> Dict[str, Any]:
    if result is None:
        return {}
    return {
        "output_dir": str(getattr(result, "output_dir", "") or "").strip() or None,
        "artifacts_dir": str(getattr(result, "artifacts_dir", "") or "").strip() or None,
        "reports_dir": str(getattr(result, "reports_dir", "") or "").strip() or None,
        "log_path": str(getattr(result, "log_path", "") or "").strip() or None,
        "skipped_workflows": list(getattr(result, "skipped_workflows", []) or []),
    }


async def _import_partial_artifacts_after_index_failure(
    *,
    storage: Any,
    tenant_id: str,
    batch_id: str,
    graph_file_id: Optional[str],
    file_hash: str,
    workspace: Any,
    graphrag_indexer: Any,
    exc: Exception,
) -> Dict[str, Any] | None:
    inspect_result = graphrag_indexer.inspect_output(workspace.workspace_dir)
    artifact_stage_status = _collect_graphrag_artifact_stage_status(
        workspace_dir=workspace.workspace_dir,
        output_dir=getattr(inspect_result, "output_dir", None),
        artifacts_dir=getattr(inspect_result, "artifacts_dir", None),
        reports_dir=getattr(inspect_result, "reports_dir", None),
    )
    artifacts_dir = Path(str(getattr(inspect_result, "artifacts_dir", "") or "").strip())
    if not artifacts_dir.exists():
        return None

    if not all(any((artifacts_dir / name).exists() for name in candidates) for candidates in _PARTIAL_ARTIFACT_MARKERS):
        return None

    if graph_file_id:
        await storage.reset_graph_file_scope(
            tenant_id=tenant_id,
            graph_file_id=graph_file_id,
            file_hash=file_hash,
        )

    summary = await _GRAPHRAG_IMPORTER.import_into_storage(
        storage=storage,
        tenant_id=tenant_id,
        batch_id=batch_id,
        workspace_id=workspace.workspace_id,
        graph_file_id=graph_file_id,
        artifacts_dir=artifacts_dir,
        source_files=workspace.files,
        import_mode="partial",
    )
    summary_dict = summary.as_dict()
    _set_manifest_status(
        workspace.manifest_path,
        status="ready",
        last_index_status="partial",
        latest_output_dir=str(getattr(inspect_result, "output_dir", "") or ""),
        latest_artifacts_dir=str(getattr(inspect_result, "artifacts_dir", "") or ""),
        latest_reports_dir=str(getattr(inspect_result, "reports_dir", "") or ""),
        last_error=f"{type(exc).__name__}: {exc}",
        import_summary=summary_dict,
        artifact_stage_status=artifact_stage_status,
    )
    return {
        "nodes": int(summary_dict.get("nodes", 0) or 0),
        "edges": int(summary_dict.get("edges", 0) or 0),
        "alerts": 0,
        "evidence": int(summary_dict.get("evidence", 0) or 0),
        "workspace": _workspace_result_meta(workspace),
        "index": _index_result_meta(inspect_result),
        "import_summary": summary_dict,
        "graph_build_mode": "graphrag_partial",
        "artifact_stage_status": artifact_stage_status,
    }


def _set_manifest_status(manifest_path: str | Path | None, **updates: Any) -> None:
    target = Path(str(manifest_path or "").strip())
    if not str(target):
        return
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return
    payload.update({key: value for key, value in updates.items() if value is not None})
    try:
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def _is_graph_eligible_file_name(file_name: Any) -> bool:
    normalized = str(file_name or "").strip().lower()
    if not normalized:
        return False
    return Path(normalized).suffix in _GRAPH_ELIGIBLE_SUFFIXES


def _filter_graph_eligible_documents(documents: Sequence[Dict[str, Any]]) -> list[Dict[str, Any]]:
    return [dict(item) for item in documents if _is_graph_eligible_file_name(item.get("file_name"))]


def _synthesize_documents(payload: IngestRequest | Dict[str, Any], *, tenant_id: str) -> list[dict[str, Any]]:
    if isinstance(payload, IngestRequest):
        documents = payload.documents if isinstance(payload.documents, list) else []
        text_corpus = str(payload.text_corpus or "").strip()
        source_texts = payload.source_texts if isinstance(payload.source_texts, list) else []
        metadata = payload.metadata if isinstance(payload.metadata, dict) else {}
        settings_overrides = dict(payload.settings_overrides or {})
    elif isinstance(payload, dict):
        raw_documents = payload.get("documents")
        documents = raw_documents if isinstance(raw_documents, list) else []
        text_corpus = str(payload.get("text_corpus") or "").strip()
        source_texts_raw = payload.get("source_texts")
        source_texts = source_texts_raw if isinstance(source_texts_raw, list) else []
        raw_metadata = payload.get("metadata")
        metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
        raw_overrides = payload.get("settings_overrides")
        settings_overrides = dict(raw_overrides) if isinstance(raw_overrides, dict) else {}
    else:
        return []

    if documents:
        normalized_documents = [dict(item) for item in documents if isinstance(item, dict)]
        return _filter_graph_eligible_documents(normalized_documents)

    if not text_corpus and not source_texts:
        return []

    file_name = str(metadata.get("file_name") or metadata.get("title") or "").strip() or "text_corpus.md"
    file_hash = str(metadata.get("file_hash") or "").strip()
    track = str(metadata.get("track") or "text-corpus").strip() or "text-corpus"
    diagnostics = {
        "ingest_input_mode": "text_corpus",
        "source_text_count": len(source_texts),
    }
    return [
        {
            "file_name": file_name,
            "file_hash": file_hash,
            "track": track,
            "text_corpus": text_corpus,
            "source_texts": source_texts,
            "settings_overrides": settings_overrides,
            "metadata": metadata,
            "diagnostics": diagnostics,
            "tenant_id": tenant_id,
        }
    ]


def count_inputs_from_batches(batches: Sequence[Dict[str, Any]]) -> int:
    total = 0
    for batch in batches:
        payload = batch.get("raw_payload") if isinstance(batch.get("raw_payload"), dict) else {}
        documents = payload.get("documents") if isinstance(payload.get("documents"), list) else []
        normalized_documents = [dict(item) for item in documents if isinstance(item, dict)]
        total += len(_filter_graph_eligible_documents(normalized_documents))
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
        elif failure_category == "runtime_binary_incompatible":
            failure_stage = "validating_runtime"
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


def _safe_preview_lines(text: str, *, limit: int = 8, line_width: int = 220) -> list[str]:
    preview: list[str] = []
    for raw in str(text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        preview.append(line[:line_width])
        if len(preview) >= limit:
            break
    return preview


def _input_text_diagnostics(text_payload: str) -> Dict[str, Any]:
    text = str(text_payload or "")
    lines = text.splitlines()
    non_empty_lines = [line for line in lines if line.strip()]
    suspicious_count = sum(text.count(marker) for marker in _SUSPICIOUS_TEXT_MARKERS)
    suspicious_ratio = round(suspicious_count / max(1, len(text)), 6)
    return {
        "text_chars": len(text),
        "text_lines": len(lines),
        "non_empty_lines": len(non_empty_lines),
        "paragraphs": len([part for part in text.split("\n\n") if part.strip()]),
        "avg_line_length": round(len(text) / max(1, len(lines)), 2),
        "contains_cjk": any("\u4e00" <= ch <= "\u9fff" for ch in text),
        "suspicious_marker_count": suspicious_count,
        "suspicious_marker_ratio": suspicious_ratio,
        "preview_lines": _safe_preview_lines(text),
    }


def _write_input_snapshot(
    *,
    workspace_dir: Path,
    file_hash: str,
    file_name: str,
    text_payload: str,
    source_input_path: str | None,
) -> Dict[str, Any]:
    diagnostics_dir = workspace_dir / "diagnostics"
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = diagnostics_dir / f"input_snapshot_{file_hash[:12] or 'document'}.json"
    payload = {
        "file_name": file_name,
        "file_hash": file_hash,
        "source_input_path": source_input_path,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "summary": _input_text_diagnostics(text_payload),
    }
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "input_snapshot_path": str(snapshot_path),
        "source_input_path": source_input_path,
        **payload["summary"],
    }


def _graph_token(value: Any, fallback: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_\-:.]+", "_", str(value or "").strip()).strip("_")
    return cleaned or fallback


def _extract_chunk_candidates(*, doc: Dict[str, Any], text_payload: str, limit: int = 3) -> list[str]:
    candidates: list[str] = []
    trace_hits = doc.get("trace_hits")
    if isinstance(trace_hits, list):
        for hit in trace_hits[:8]:
            if not isinstance(hit, dict):
                continue
            snippet = str(hit.get("snippet") or "").strip()
            if snippet:
                candidates.append(snippet)
    for line in str(text_payload or "").splitlines():
        normalized = line.strip()
        if normalized:
            candidates.append(normalized)
        if len(candidates) >= limit * 2:
            break

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        key = item[:240]
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(key)
        if len(deduped) >= max(1, int(limit)):
            break
    if deduped:
        return deduped
    file_name = str(doc.get("file_name") or "").strip()
    return [f"{file_name or 'document'} content overview"]


async def _import_document_fallback_graph(
    *,
    storage: Any,
    tenant_id: str,
    batch_id: str,
    graph_file_id: Optional[str],
    file_name: str,
    file_hash: str,
    track: str,
    doc: Dict[str, Any],
    failure: Dict[str, Any],
) -> Dict[str, Any]:
    text_payload = _compose_document_text(doc)
    diagnostics = dict(doc.get("diagnostics") or {}) if isinstance(doc.get("diagnostics"), dict) else {}
    if graph_file_id:
        await storage.reset_graph_file_scope(
            tenant_id=tenant_id,
            graph_file_id=graph_file_id,
            file_hash=file_hash,
        )

    document_row = await storage.upsert_document(
        tenant_id=tenant_id,
        batch_id=batch_id,
        file_name=file_name,
        file_hash=file_hash,
        track=track,
        diagnostics={
            **diagnostics,
            "graph_build_mode": "document_fallback",
            "fallback_failure": dict(failure or {}),
        },
    )
    doc_id = str(document_row.get("doc_id") or "").strip()
    graph_source = "graphrag_artifacts:fallback"

    async def _upsert_node(
        *,
        node_type: str,
        canonical_key: str,
        display_name: str,
        attrs: Dict[str, Any],
        confidence: float = 1.0,
    ) -> Dict[str, Any]:
        return await storage.upsert_node(
            tenant_id=tenant_id,
            graph_file_id=graph_file_id,
            graph_version_id=None,
            node_type=node_type,
            canonical_key=canonical_key,
            display_name=display_name,
            attrs=attrs,
            confidence=confidence,
        )

    async def _upsert_edge(
        *,
        source_node_id: str,
        target_node_id: str,
        relation_type: str,
        attrs: Dict[str, Any],
        confidence: float = 1.0,
        risk_score: float = 0.0,
    ) -> Dict[str, Any]:
        return await storage.upsert_edge(
            tenant_id=tenant_id,
            graph_file_id=graph_file_id,
            graph_version_id=None,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relation_type=relation_type,
            direction="out",
            attrs=attrs,
            confidence=confidence,
            risk_score=risk_score,
        )

    nodes: list[Dict[str, Any]] = []
    edges: list[Dict[str, Any]] = []
    evidence_count = 0

    document_graphrag_id = _graph_token(file_hash, "document")
    document_node = await _upsert_node(
        node_type="Document",
        canonical_key=f"document::{document_graphrag_id}",
        display_name=file_name or document_graphrag_id,
        attrs={
            "graph_source": graph_source,
            "workspace_id": None,
            "file_hash": file_hash,
            "graphrag_id": document_graphrag_id,
            "document_ids": [document_graphrag_id],
            "track": track,
        },
        confidence=1.0,
    )
    nodes.append(document_node)

    chunk_candidates = _extract_chunk_candidates(doc=doc, text_payload=text_payload, limit=3)
    chunk_rows: list[Dict[str, Any]] = []
    for index, snippet in enumerate(chunk_candidates, start=1):
        chunk_key = _graph_token(f"{file_hash}:chunk:{index}", f"chunk_{index}")
        chunk_row = await _upsert_node(
            node_type="Chunk",
            canonical_key=f"chunk::{chunk_key}",
            display_name=snippet[:120] or chunk_key,
            attrs={
                "graph_source": graph_source,
                "workspace_id": None,
                "file_hash": file_hash,
                "graphrag_id": chunk_key,
                "text": snippet[:1000],
                "document_ids": [document_graphrag_id],
            },
            confidence=0.92,
        )
        nodes.append(chunk_row)
        chunk_rows.append(chunk_row)
        edge_row = await _upsert_edge(
            source_node_id=str(document_node.get("node_id") or ""),
            target_node_id=str(chunk_row.get("node_id") or ""),
            relation_type="has_chunk",
            attrs={
                "graph_source": graph_source,
                "file_hash": file_hash,
                "document_id": document_graphrag_id,
                "chunk_id": chunk_key,
            },
            confidence=0.9,
        )
        edges.append(edge_row)
        await storage.insert_evidence(
            tenant_id=tenant_id,
            doc_id=doc_id,
            object_type="chunk",
            object_id=chunk_key,
            ref_id=None,
            page_no=None,
            snippet=snippet[:1000],
            locator={},
            bbox=[],
            artifact_url=None,
            confidence=0.9,
        )
        evidence_count += 1

    result = doc.get("result")
    result_fields = result if isinstance(result, dict) else {}
    entity_rows: list[Dict[str, Any]] = []
    entity_refs: list[tuple[str, float]] = []
    for index, (field_name, payload) in enumerate(result_fields.items(), start=1):
        if not isinstance(payload, dict):
            continue
        value = str(payload.get("value") or "").strip()
        if not value:
            continue
        entity_key = _graph_token(f"{file_hash}:{field_name}:{index}", f"entity_{index}")
        try:
            confidence = float(payload.get("confidence", 0.86) or 0.86)
        except (TypeError, ValueError):
            confidence = 0.86
        entity_row = await _upsert_node(
            node_type="Entity",
            canonical_key=f"entity::{entity_key}",
            display_name=value[:160] or field_name,
            attrs={
                "graph_source": graph_source,
                "workspace_id": None,
                "file_hash": file_hash,
                "graphrag_id": entity_key,
                "field_name": str(field_name or "").strip(),
                "value": value,
                "document_ids": [document_graphrag_id],
            },
            confidence=confidence,
        )
        nodes.append(entity_row)
        entity_rows.append(entity_row)
        entity_refs.append((entity_key, confidence))

    if not entity_rows:
        entity_key = _graph_token(f"{file_hash}:entity:summary", "entity_summary")
        fallback_label = Path(file_name).stem or "Document Entity"
        entity_row = await _upsert_node(
            node_type="Entity",
            canonical_key=f"entity::{entity_key}",
            display_name=fallback_label[:160],
            attrs={
                "graph_source": graph_source,
                "workspace_id": None,
                "file_hash": file_hash,
                "graphrag_id": entity_key,
                "field_name": "summary",
                "value": fallback_label,
                "document_ids": [document_graphrag_id],
            },
            confidence=0.8,
        )
        nodes.append(entity_row)
        entity_rows.append(entity_row)
        entity_refs.append((entity_key, 0.8))

    community_key = _graph_token(f"{file_hash}:community:1", "community_1")
    report_key = _graph_token(f"{file_hash}:community_report:1", "community_report_1")
    community_row = await _upsert_node(
        node_type="Community",
        canonical_key=f"community::{community_key}",
        display_name=f"{Path(file_name).stem or 'Document'} 社区",
        attrs={
            "graph_source": graph_source,
            "workspace_id": None,
            "file_hash": file_hash,
            "graphrag_id": community_key,
            "report_id": report_key,
            "document_ids": [document_graphrag_id],
        },
        confidence=0.82,
    )
    report_row = await _upsert_node(
        node_type="CommunityReport",
        canonical_key=f"community_report::{report_key}",
        display_name=f"{Path(file_name).stem or 'Document'} 报告摘要",
        attrs={
            "graph_source": graph_source,
            "workspace_id": None,
            "file_hash": file_hash,
            "graphrag_id": community_key,
            "report_id": report_key,
            "document_ids": [document_graphrag_id],
        },
        confidence=0.82,
    )
    nodes.extend([community_row, report_row])

    for entity_row, (entity_key, entity_confidence) in zip(entity_rows, entity_refs):
        edge_row = await _upsert_edge(
            source_node_id=str(document_node.get("node_id") or ""),
            target_node_id=str(entity_row.get("node_id") or ""),
            relation_type="has_entity",
            attrs={
                "graph_source": graph_source,
                "file_hash": file_hash,
                "document_id": document_graphrag_id,
                "entity_id": entity_key,
            },
            confidence=max(0.5, min(1.0, entity_confidence)),
        )
        edges.append(edge_row)
        await storage.insert_evidence(
            tenant_id=tenant_id,
            doc_id=doc_id,
            object_type="entity",
            object_id=entity_key,
            ref_id=None,
            page_no=None,
            snippet=str(entity_row.get("display_name") or ""),
            locator={},
            bbox=[],
            artifact_url=None,
            confidence=max(0.5, min(1.0, entity_confidence)),
        )
        evidence_count += 1

    relationship_index = 1
    for idx in range(len(entity_rows) - 1):
        left = entity_rows[idx]
        right = entity_rows[idx + 1]
        relationship_id = _graph_token(f"{file_hash}:relationship:{relationship_index}", f"relationship_{relationship_index}")
        relationship_index += 1
        edge_row = await _upsert_edge(
            source_node_id=str(left.get("node_id") or ""),
            target_node_id=str(right.get("node_id") or ""),
            relation_type="related_to",
            attrs={
                "graph_source": graph_source,
                "file_hash": file_hash,
                "graphrag_id": relationship_id,
                "weight": 0.75,
                "text_unit_ids": [str(chunk_rows[0].get("attrs", {}).get("graphrag_id") or "")] if chunk_rows else [],
            },
            confidence=0.78,
        )
        edges.append(edge_row)
        await storage.insert_evidence(
            tenant_id=tenant_id,
            doc_id=doc_id,
            object_type="relationship",
            object_id=relationship_id,
            ref_id=None,
            page_no=None,
            snippet=f"{left.get('display_name')} related to {right.get('display_name')}",
            locator={},
            bbox=[],
            artifact_url=None,
            confidence=0.72,
        )
        evidence_count += 1

    for idx, (entity_row, _) in enumerate(zip(entity_rows, entity_refs), start=1):
        relationship_id = _graph_token(f"{file_hash}:entity-community:{idx}", f"entity_community_{idx}")
        edge_row = await _upsert_edge(
            source_node_id=str(entity_row.get("node_id") or ""),
            target_node_id=str(community_row.get("node_id") or ""),
            relation_type="in_community",
            attrs={
                "graph_source": graph_source,
                "file_hash": file_hash,
                "community_id": community_key,
                "relationship_id": relationship_id,
            },
            confidence=0.76,
        )
        edges.append(edge_row)

    edges.append(
        await _upsert_edge(
            source_node_id=str(community_row.get("node_id") or ""),
            target_node_id=str(report_row.get("node_id") or ""),
            relation_type="has_report",
            attrs={
                "graph_source": graph_source,
                "file_hash": file_hash,
                "community_id": community_key,
                "report_id": report_key,
            },
            confidence=0.82,
        )
    )

    trace_hits = doc.get("trace_hits")
    if isinstance(trace_hits, list):
        for index, hit in enumerate(trace_hits[:16], start=1):
            if not isinstance(hit, dict):
                continue
            object_type = str(hit.get("object_type") or "chunk").strip().lower() or "chunk"
            object_id = str(hit.get("object_id") or f"{object_type}_{index}").strip() or f"{object_type}_{index}"
            snippet = str(hit.get("snippet") or "").strip() or f"{object_type}:{object_id}"
            locator = dict(hit.get("locator") or {}) if isinstance(hit.get("locator"), dict) else {}
            page_raw = hit.get("page")
            page_no = int(page_raw) if isinstance(page_raw, int) else None
            artifact_url = str(hit.get("artifact_url") or "").strip() or None
            try:
                confidence = float(hit.get("confidence", 0.8) or 0.8)
            except (TypeError, ValueError):
                confidence = 0.8
            await storage.insert_evidence(
                tenant_id=tenant_id,
                doc_id=doc_id,
                object_type=object_type,
                object_id=object_id,
                ref_id=str(hit.get("ref_id") or "").strip() or None,
                page_no=page_no,
                snippet=snippet[:1000],
                locator=locator,
                bbox=list(hit.get("bbox") or []) if isinstance(hit.get("bbox"), list) else [],
                artifact_url=artifact_url,
                confidence=confidence,
            )
            evidence_count += 1

    report_snippet = str(diagnostics.get("summary") or "").strip()
    if not report_snippet:
        report_snippet = str(chunk_candidates[0] if chunk_candidates else f"{file_name} report summary")
    await storage.insert_evidence(
        tenant_id=tenant_id,
        doc_id=doc_id,
        object_type="community_report",
        object_id=report_key,
        ref_id=None,
        page_no=None,
        snippet=report_snippet[:1000],
        locator={},
        bbox=[],
        artifact_url=None,
        confidence=0.81,
    )
    evidence_count += 1

    import_summary = {
        "mode": "document_fallback",
        "nodes": len(nodes),
        "edges": len(edges),
        "alerts": 0,
        "evidence": evidence_count,
    }
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "alerts": 0,
        "evidence": evidence_count,
        "workspace": {},
        "index": {},
        "import_summary": import_summary,
        "graph_build_mode": "document_fallback",
        "diagnostics": {
            "fallback_mode": "document_graph",
            "failure": dict(failure or {}),
        },
    }


def _collect_graphrag_artifact_stage_status(
    *,
    workspace_dir: Path,
    output_dir: str | Path | None,
    artifacts_dir: str | Path | None,
    reports_dir: str | Path | None,
) -> Dict[str, Any]:
    workspace_root = Path(str(workspace_dir)).resolve()
    artifacts_root = Path(str(artifacts_dir)).resolve() if str(artifacts_dir or "").strip() else None
    reports_root = Path(str(reports_dir)).resolve() if str(reports_dir or "").strip() else None
    output_root = Path(str(output_dir)).resolve() if str(output_dir or "").strip() else None

    stages: Dict[str, Any] = {}
    for stage_name, (scope, candidate_names) in _GRAPHRAG_ARTIFACT_PATHS.items():
        if scope == "artifacts" and artifacts_root is not None:
            base_dir = artifacts_root
        elif scope == "reports" and reports_root is not None:
            base_dir = reports_root
        else:
            base_dir = workspace_root

        candidate_paths = [base_dir / relative_name for relative_name in candidate_names]
        target = next((candidate for candidate in candidate_paths if candidate.exists()), candidate_paths[0])
        exists = target.exists()
        stages[stage_name] = {
            "exists": exists,
            "path": str(target),
            "size_bytes": int(target.stat().st_size) if exists else 0,
            "matched_artifact": target.name if exists else None,
            "candidates": [str(candidate) for candidate in candidate_paths],
        }

    full_ready = all(bool(item.get("exists")) for item in stages.values())
    partial_ready = bool(stages["create_base_text_units"]["exists"] and stages["create_base_extracted_entities"]["exists"])
    return {
        "workspace_dir": str(workspace_root),
        "output_dir": str(output_root) if output_root is not None else None,
        "artifacts_dir": str(artifacts_root) if artifacts_root is not None else None,
        "reports_dir": str(reports_root) if reports_root is not None else None,
        "stages": stages,
        "full_ready": full_ready,
        "partial_ready": partial_ready,
    }


async def update_job_stage(
    *,
    storage: Any,
    job_id: str,
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


async def recover_jobs(
    *,
    storage: Any,
    helpers: Module4IngestRuntimeHelpers,
    job_tasks: Dict[str, asyncio.Task[Any]],
    schedule_ingest_job: ScheduleIngestJobCallback,
    schedule_rebuild_job: ScheduleRebuildJobCallback,
) -> None:
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
                    finished_at=helpers.now_utc(),
                )
                continue
            try:
                payload = IngestRequest.model_validate(raw_payload)
            except Exception as exc:
                await storage.update_job(
                    job_id,
                    status="failed",
                    error_message=f"Recover payload invalid: {type(exc).__name__}: {exc}",
                    finished_at=helpers.now_utc(),
                )
                continue
            schedule_ingest_job(job_id, batch_id, payload)
            continue

        if job_type == "rebuild_graph":
            if not _recover_rebuild_jobs_enabled():
                await storage.update_job(
                    job_id,
                    status="failed",
                    error_message="Rebuild job recovery is disabled. Trigger /module4/rebuild to start a new run.",
                    finished_at=helpers.now_utc(),
                )
                continue
            payload_raw = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            try:
                payload = RebuildRequest.model_validate(payload_raw)
            except Exception as exc:
                await storage.update_job(
                    job_id,
                    status="failed",
                    error_message=f"Recover rebuild payload invalid: {type(exc).__name__}: {exc}",
                    finished_at=helpers.now_utc(),
                )
                continue
            schedule_rebuild_job(job_id, payload)


async def process_document(
    *,
    storage: Any,
    helpers: Module4IngestRuntimeHelpers,
    tenant_id: str,
    batch_id: str,
    graph_file_id: Optional[str],
    doc: Dict[str, Any],
) -> Dict[str, Any]:
    workspace_builder = helpers.workspace_builder_getter() if callable(helpers.workspace_builder_getter) else None
    graphrag_indexer = helpers.graphrag_indexer_getter() if callable(helpers.graphrag_indexer_getter) else None
    if workspace_builder is None or graphrag_indexer is None:
        raise RuntimeError("GraphRAG runtime dependencies are not attached to module4 ingest")

    file_name = str(doc.get("file_name") or "unknown")
    file_hash = str(doc.get("file_hash") or "").strip() or helpers.risk_key(file_name + json.dumps(doc, ensure_ascii=False))
    text_payload = _compose_document_text(doc)
    if not str(text_payload or "").strip():
        raise ValueError(f"GraphRAG normalized text is empty for {file_name}")
    doc_metadata = dict(doc.get("metadata") or {}) if isinstance(doc.get("metadata"), dict) else {}
    diagnostics = dict(doc.get("diagnostics") or {}) if isinstance(doc.get("diagnostics"), dict) else {}

    workspace = workspace_builder.prepare_workspace(
        tenant_id=tenant_id,
        batch_id=batch_id,
        source=str(doc.get("source") or "module2"),
        source_batch_key=str(doc.get("source_batch_key") or f"{batch_id}:{file_hash}"),
        graph_mode=str(doc.get("graph_mode") or "hybrid"),
        files=[
            WorkspaceSourceFile(
                file_name=file_name,
                file_hash=file_hash,
                text_content=text_payload,
                source_kind=str(doc.get("track") or "module2"),
                original_path=str(doc_metadata.get("original_path") or "").strip() or None,
                artifact_path=str(doc_metadata.get("artifact_path") or "").strip() or None,
                artifact_url=str(doc_metadata.get("artifact_url") or "").strip() or None,
                metadata={
                    **doc_metadata,
                    "track": str(doc.get("track") or ""),
                    "diagnostics": diagnostics,
                },
            )
        ],
    )
    source_input_path = None
    if workspace.files:
        source_input_path = str((workspace.files[0] or {}).get("input_txt") or "").strip() or None
    input_snapshot = _write_input_snapshot(
        workspace_dir=workspace.workspace_dir,
        file_hash=file_hash,
        file_name=file_name,
        text_payload=text_payload,
        source_input_path=source_input_path,
    )
    _set_manifest_status(
        workspace.manifest_path,
        status="indexing",
        last_index_status="running",
        last_error="",
        input_snapshot=input_snapshot,
    )

    try:
        # GraphRAG indexing is CPU/IO intensive and runs synchronously. Execute it
        # in a worker thread so API health and query endpoints remain responsive.
        index_result = await asyncio.to_thread(graphrag_indexer.run, workspace.workspace_dir)
    except Exception as exc:
        inspect_result = await asyncio.to_thread(graphrag_indexer.inspect_output, workspace.workspace_dir)
        artifact_stage_status = _collect_graphrag_artifact_stage_status(
            workspace_dir=workspace.workspace_dir,
            output_dir=getattr(inspect_result, "output_dir", None),
            artifacts_dir=getattr(inspect_result, "artifacts_dir", None),
            reports_dir=getattr(inspect_result, "reports_dir", None),
        )
        failure = _classify_graph_failure(exc, fallback_stage="indexing")
        _set_manifest_status(
            workspace.manifest_path,
            status="failed",
            last_index_status="failed",
            last_error=f"{type(exc).__name__}: {exc}",
            artifact_stage_status=artifact_stage_status,
            failure=failure,
        )
        if _allow_partial_import_after_index_failure():
            partial_result = await _import_partial_artifacts_after_index_failure(
                storage=storage,
                tenant_id=tenant_id,
                batch_id=batch_id,
                graph_file_id=graph_file_id,
                file_hash=file_hash,
                workspace=workspace,
                graphrag_indexer=graphrag_indexer,
                exc=exc,
            )
            if partial_result is not None:
                partial_result["diagnostics"] = {
                    "input_snapshot": input_snapshot,
                    "artifact_stage_status": artifact_stage_status,
                    "failure": failure,
                }
                return partial_result
        raise DocumentGraphBuildError(
            message=failure["failure_message"],
            diagnostics={
                "input_snapshot": input_snapshot,
                "artifact_stage_status": artifact_stage_status,
                "failure": failure,
                "workspace": _workspace_result_meta(workspace),
                "index": _index_result_meta(inspect_result),
            },
        ) from exc

    if graph_file_id:
        await storage.reset_graph_file_scope(
            tenant_id=tenant_id,
            graph_file_id=graph_file_id,
            file_hash=file_hash,
        )

    summary = await _GRAPHRAG_IMPORTER.import_into_storage(
        storage=storage,
        tenant_id=tenant_id,
        batch_id=batch_id,
        workspace_id=workspace.workspace_id,
        graph_file_id=graph_file_id,
        artifacts_dir=Path(index_result.artifacts_dir),
        source_files=workspace.files,
    )
    artifact_stage_status = _collect_graphrag_artifact_stage_status(
        workspace_dir=workspace.workspace_dir,
        output_dir=index_result.output_dir,
        artifacts_dir=index_result.artifacts_dir,
        reports_dir=index_result.reports_dir,
    )
    _set_manifest_status(
        workspace.manifest_path,
        status="ready",
        last_index_status="success",
        latest_output_dir=str(index_result.output_dir or ""),
        latest_artifacts_dir=str(index_result.artifacts_dir or ""),
        latest_reports_dir=str(index_result.reports_dir or ""),
        last_error="",
        import_summary=summary.as_dict(),
        input_snapshot=input_snapshot,
        artifact_stage_status=artifact_stage_status,
    )
    summary_dict = summary.as_dict()
    return {
        "nodes": int(summary_dict.get("nodes", 0) or 0),
        "edges": int(summary_dict.get("edges", 0) or 0),
        "alerts": 0,
        "evidence": int(summary_dict.get("evidence", 0) or 0),
        "workspace": _workspace_result_meta(workspace),
        "index": _index_result_meta(index_result),
        "import_summary": summary_dict,
        "graph_build_mode": "graphrag",
        "diagnostics": {
            "input_snapshot": input_snapshot,
            "artifact_stage_status": artifact_stage_status,
        },
    }


async def run_document_ingest_job(
    *,
    storage: Any,
    helpers: Module4IngestRuntimeHelpers,
    job_id: str,
    batch_id: str,
    payload: IngestRequest,
    process_document_callback: ProcessDocumentCallback,
    update_job_stage_callback: Optional[UpdateJobStageCallback] = None,
) -> Dict[str, Any]:
    tenant_id = payload.tenant_id or helpers.default_tenant()
    raw_documents = [dict(item) for item in payload.documents if isinstance(item, dict)]
    documents = _filter_graph_eligible_documents(raw_documents)
    total = len(documents)
    skipped_documents = max(0, len(raw_documents) - total)
    agg = {
        "stage": "processing_documents",
        "nodes": 0,
        "edges": 0,
        "alerts": 0,
        "evidence": 0,
        "documents": total,
        "skipped_documents": skipped_documents,
        "uploads": 0,
    }

    async def _stage(job_id: str, stage: str, progress: float, base_result: Any) -> None:
        if update_job_stage_callback is not None:
            await update_job_stage_callback(job_id=job_id, stage=stage, progress=progress, base_result=base_result)
        else:
            await update_job_stage(storage=storage, job_id=job_id, stage=stage, progress=progress, base_result=base_result)

    await _stage(job_id, "processing_documents", 1.0, agg)
    for idx, doc in enumerate(documents, start=1):
        file_name = str(doc.get("file_name") or "unknown")
        file_hash = str(doc.get("file_hash") or "").strip() or helpers.risk_key(file_name + json.dumps(doc, ensure_ascii=False))
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
            counters = await process_document_callback(
                tenant_id=tenant_id,
                batch_id=batch_id,
                graph_file_id=graph_file_id,
                doc=doc,
            )
        except Exception as exc:
            failure_message = _trim_error_text(f"{type(exc).__name__}: {exc}")
            diagnostics_meta = {}
            if isinstance(exc, DocumentGraphBuildError):
                diagnostics_meta = dict(exc.diagnostics or {})
            fallback_meta = diagnostics_meta.get("failure") if isinstance(diagnostics_meta.get("failure"), dict) else {}
            counters = None
            if isinstance(exc, DocumentGraphBuildError) and _allow_document_fallback_graph():
                try:
                    counters = await _import_document_fallback_graph(
                        storage=storage,
                        tenant_id=tenant_id,
                        batch_id=batch_id,
                        graph_file_id=graph_file_id,
                        file_name=file_name,
                        file_hash=file_hash,
                        track=track,
                        doc=doc,
                        failure=fallback_meta
                        or {
                            "failure_stage": "processing_documents",
                            "failure_category": "document_ingest_failed",
                            "failure_message": failure_message,
                        },
                    )
                except Exception:
                    counters = None
            if counters is None:
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
                        "failure_stage": str(fallback_meta.get("failure_stage") or "processing_documents"),
                        "failure_category": str(fallback_meta.get("failure_category") or "document_ingest_failed"),
                        "failure_message": str(fallback_meta.get("failure_message") or failure_message),
                        **diagnostics_meta,
                    },
                )
                raise
        for key in ("nodes", "edges", "alerts", "evidence"):
            agg[key] += int(counters.get(key, 0) or 0)
        workspace_meta = counters.get("workspace") if isinstance(counters.get("workspace"), dict) else {}
        index_meta = counters.get("index") if isinstance(counters.get("index"), dict) else {}
        import_summary = counters.get("import_summary") if isinstance(counters.get("import_summary"), dict) else {}
        graph_build_mode = str(counters.get("graph_build_mode") or "document")
        diagnostics_meta = counters.get("diagnostics") if isinstance(counters.get("diagnostics"), dict) else {}
        graph_file = await storage.upsert_graph_file(
            tenant_id=tenant_id,
            file_hash=file_hash,
            file_name=file_name,
            workspace_id=str(workspace_meta.get("workspace_id") or "") or None,
            graph_mode=payload.graph_mode,
            source=payload.source,
            status="ready",
            current_job_id=job_id,
            last_error=None,
            node_count=int(counters.get("nodes", 0) or 0),
            edge_count=int(counters.get("edges", 0) or 0),
            metadata={
                **processing_metadata,
                "stage": "ready",
                "graph_build_mode": graph_build_mode,
                "workspace_dir": workspace_meta.get("workspace_dir"),
                "manifest_path": workspace_meta.get("manifest_path"),
                "output_dir": index_meta.get("output_dir"),
                "artifacts_dir": index_meta.get("artifacts_dir"),
                "reports_dir": index_meta.get("reports_dir"),
                "graphrag_log_path": index_meta.get("log_path"),
                "skipped_workflows": index_meta.get("skipped_workflows") or [],
                "import_summary": import_summary,
                **diagnostics_meta,
            },
            last_indexed_at=helpers.now_utc(),
        )
        graph_version = await storage.add_graph_version(
            tenant_id=tenant_id,
            file_hash=file_hash,
            job_id=job_id,
            workspace_id=str(workspace_meta.get("workspace_id") or "") or None,
            status=str(graph_file.get("status") or "ready"),
            manifest_path=str(workspace_meta.get("manifest_path") or "") or None,
            output_dir=str(index_meta.get("output_dir") or "") or None,
            artifacts_dir=str(index_meta.get("artifacts_dir") or "") or None,
            reports_dir=str(index_meta.get("reports_dir") or "") or None,
            import_summary=import_summary
            or {
                "mode": graph_build_mode,
                "nodes": int(counters.get("nodes", 0) or 0),
                "edges": int(counters.get("edges", 0) or 0),
                "alerts": int(counters.get("alerts", 0) or 0),
                "evidence": int(counters.get("evidence", 0) or 0),
            },
        )
        graph_version_id = str(graph_version.get("graph_version_id") or "").strip() or None
        if graph_file_id and graph_version_id and hasattr(storage, "assign_graph_version"):
            await storage.assign_graph_version(
                tenant_id=tenant_id,
                graph_file_id=graph_file_id,
                graph_version_id=graph_version_id,
                workspace_id=None,
            )
        progress = round((idx / max(1, total)) * 100.0, 2)
        await _stage(job_id, "processing_documents", progress, agg)
    return agg


async def run_ingest_job(
    *,
    storage: Any,
    job_tasks: Dict[str, asyncio.Task[Any]],
    helpers: Module4IngestRuntimeHelpers,
    job_id: str,
    batch_id: str,
    payload: IngestRequest,
    run_document_ingest_job_callback: RunDocumentIngestJobCallback,
) -> None:
    await storage.update_job(job_id, status="running", started_at=helpers.now_utc(), progress=1.0)
    try:
        result = await run_document_ingest_job_callback(job_id, batch_id, payload)
        await storage.update_job(job_id, status="success", progress=100.0, result=result, finished_at=helpers.now_utc())
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
            finished_at=helpers.now_utc(),
        )
    finally:
        job_tasks.pop(job_id, None)


async def run_rebuild_job(
    *,
    storage: Any,
    job_tasks: Dict[str, asyncio.Task[Any]],
    helpers: Module4IngestRuntimeHelpers,
    job_id: str,
    payload: RebuildRequest,
    run_document_ingest_job_callback: RunDocumentIngestJobCallback,
) -> None:
    tenant_id = payload.tenant_id or helpers.default_tenant()
    batches = await storage.list_ingest_batches(tenant_id=tenant_id)
    total_inputs = count_inputs_from_batches(batches)
    agg = {
        "documents": total_inputs,
        "batches": len(batches),
        "skipped_batches": 0,
        "nodes": 0,
        "edges": 0,
        "alerts": 0,
        "evidence": 0,
    }

    await storage.update_job(job_id, status="running", started_at=helpers.now_utc(), progress=1.0)
    try:
        await storage.delete_tenant_graph_data(tenant_id=tenant_id)

        processed = 0
        for batch in batches:
            batch_id = str(batch.get("batch_id") or "").strip()
            raw_payload = batch.get("raw_payload") if isinstance(batch.get("raw_payload"), dict) else {}
            payload_data = dict(raw_payload)
            payload_data["tenant_id"] = tenant_id
            synthesized_documents = _synthesize_documents(payload_data, tenant_id=tenant_id)
            if synthesized_documents:
                payload_data["documents"] = synthesized_documents
            try:
                ingest_payload = IngestRequest.model_validate(payload_data)
            except Exception:
                agg["skipped_batches"] = int(agg.get("skipped_batches", 0) or 0) + 1
                progress = round((processed / max(1, total_inputs)) * 100.0, 2)
                await storage.update_job(job_id, progress=progress, result=_merge_result(agg, stage="rebuilding"))
                continue
            result = await run_document_ingest_job_callback(job_id, batch_id, ingest_payload)
            processed += len(ingest_payload.documents)

            for key in ("nodes", "edges", "alerts", "evidence"):
                agg[key] += int(result.get(key, 0) or 0)

            progress = round((processed / max(1, total_inputs)) * 100.0, 2)
            await storage.update_job(job_id, progress=progress, result=_merge_result(agg, stage="rebuilding"))

        await storage.update_job(job_id, status="success", progress=100.0, result=agg, finished_at=helpers.now_utc())
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
            finished_at=helpers.now_utc(),
        )
    finally:
        job_tasks.pop(job_id, None)


async def submit_ingest_job(
    *,
    storage: Any,
    payload: IngestRequest,
    tenant_id: str,
    derived_ingest_batch_key: DerivedIngestBatchKeyCallback,
    schedule_ingest_job: ScheduleIngestJobCallback,
) -> IngestResponse:
    if payload.source != "module2":
        raise ValueError("module4 only accepts document sync from module2")
    effective_documents = _synthesize_documents(payload, tenant_id=tenant_id)
    if not effective_documents:
        raise ValueError("No graph-eligible documents found. Supported suffixes: .docx, .pdf, .txt, .md")

    source_batch_key = derived_ingest_batch_key(payload, tenant_id=tenant_id)
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
                schedule_ingest_job(str(existing_job["job_id"]), str(existing_batch["batch_id"]), recover_payload)
            return IngestResponse(
                job_id=str(existing_job["job_id"]),
                batch_id=str(existing_batch["batch_id"]),
                status=str(existing_job["status"]),
            )

    payload_data = payload.model_dump(mode="json")
    payload_data["documents"] = effective_documents
    payload_data["tenant_id"] = tenant_id
    payload_data["source_batch_key"] = source_batch_key
    job = await storage.create_job(
        tenant_id=tenant_id,
        job_type="ingest",
        status="queued",
        payload={
            "source": payload.source,
            "source_batch_key": source_batch_key,
            "graph_mode": payload.graph_mode,
            "documents": len(effective_documents),
            "inputs": len(effective_documents),
        },
    )
    batch = await storage.create_ingest_batch(
        tenant_id=tenant_id,
        source=payload.source,
        source_batch_key=source_batch_key,
        job_id=str(job["job_id"]),
        raw_payload=payload_data,
    )
    normalized_payload = IngestRequest.model_validate(payload_data)
    schedule_ingest_job(str(job["job_id"]), str(batch["batch_id"]), normalized_payload)
    return IngestResponse(job_id=str(job["job_id"]), batch_id=str(batch["batch_id"]), status=str(job["status"]))


async def submit_rebuild_job(
    *,
    storage: Any,
    tenant_id: str,
    schedule_rebuild_job: ScheduleRebuildJobCallback,
) -> Dict[str, Any]:
    batches = await storage.list_ingest_batches(tenant_id=tenant_id)
    documents = count_inputs_from_batches(batches)
    job = await storage.create_job(
        tenant_id=tenant_id,
        job_type="rebuild_graph",
        status="queued",
        payload={"tenant_id": tenant_id, "batches": len(batches), "documents": documents},
    )
    schedule_rebuild_job(str(job["job_id"]), RebuildRequest(tenant_id=tenant_id))
    return {
        "job_id": str(job["job_id"]),
        "status": str(job["status"]),
        "batches": len(batches),
        "documents": documents,
    }
