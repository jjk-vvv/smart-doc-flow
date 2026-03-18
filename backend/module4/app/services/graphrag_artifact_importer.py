from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence

from app.db.storage import Module4Storage


def _ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def _normalize_text(value: Any) -> str:
    return str(value or "").replace("\x00", " ").strip()


def _clean_graph_text(value: Any) -> str:
    text = _normalize_text(value)
    if not text:
        return ""
    for token in ('("entity"', '("relationship"', ")(\"entity\"", ")(\"relationship\""):
        text = text.replace(token, "")
    return text.strip(" \t\r\n|,;")


def _display_excerpt(value: str, max_chars: int = 72) -> str:
    text = _normalize_text(value)
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3].rstrip()}..."


def _evidence_snippet(value: Any, max_chars: int = 500) -> str:
    text = _normalize_text(value)
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3].rstrip()}..."


def _is_placeholder_community_title(title: str, community_id: str) -> bool:
    value = _normalize_text(title).lower()
    community_value = _normalize_text(community_id).lower()
    if not value:
        return True
    return value in {f"community {community_value}", f"community_{community_value}", f"community-{community_value}"}


def _stable_key(prefix: str, raw_value: str) -> str:
    digest = hashlib.sha256(f"{prefix}:{raw_value}".encode("utf-8")).hexdigest()[:20]
    return f"{prefix}:{digest}"


def _read_rows(path: Path, required_columns: Sequence[str], optional_columns: Sequence[str] | None = None) -> List[Dict[str, Any]]:
    import pyarrow.parquet as pq

    if not path.exists():
        raise FileNotFoundError(f"GraphRAG artifact not found: {path}")

    schema_names = set(pq.read_schema(path).names)
    missing = [name for name in required_columns if name not in schema_names]
    if missing:
        raise ValueError(f"{path.name} is missing required columns: {missing}")

    selected = list(required_columns)
    for name in optional_columns or []:
        if name in schema_names and name not in selected:
            selected.append(name)

    table = pq.read_table(path, columns=selected)
    return list(table.to_pylist())


def _read_optional_rows(path: Path) -> List[Dict[str, Any]]:
    import pyarrow.parquet as pq

    if not path.exists():
        return []
    return list(pq.read_table(path).to_pylist())


def _graphml_key_map(root: ET.Element) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for item in root.findall(".//{*}key"):
        key_id = _normalize_text(item.attrib.get("id"))
        attr_name = _normalize_text(item.attrib.get("attr.name")) or key_id
        if key_id:
            mapping[key_id] = attr_name
    return mapping


def _parse_graphml_rows(graphml_text: str) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    payload = _normalize_text(graphml_text)
    if not payload:
        return [], []
    try:
        root = ET.fromstring(payload)
    except ET.ParseError:
        return [], []

    key_map = _graphml_key_map(root)
    graph = next(iter(root.findall(".//{*}graph")), None)
    if graph is None:
        return [], []

    node_rows: List[Dict[str, Any]] = []
    edge_rows: List[Dict[str, Any]] = []

    for node in graph.findall("{*}node"):
        row: Dict[str, Any] = {"id": _normalize_text(node.attrib.get("id"))}
        for data in node.findall("{*}data"):
            key = key_map.get(_normalize_text(data.attrib.get("key")), _normalize_text(data.attrib.get("key")))
            row[key] = _normalize_text(data.text)
        if row["id"]:
            node_rows.append(row)

    for edge in graph.findall("{*}edge"):
        row = {
            "source": _normalize_text(edge.attrib.get("source")),
            "target": _normalize_text(edge.attrib.get("target")),
        }
        for data in edge.findall("{*}data"):
            key = key_map.get(_normalize_text(data.attrib.get("key")), _normalize_text(data.attrib.get("key")))
            row[key] = _normalize_text(data.text)
        if row["source"] and row["target"]:
            edge_rows.append(row)

    return node_rows, edge_rows


def _split_source_ids(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        items = value
    else:
        text = _normalize_text(value)
        if not text:
            return []
        normalized = text.replace(";", ",").replace("|", ",")
        items = [item.strip() for item in normalized.split(",") if item.strip()]
    out: List[str] = []
    seen = set()
    for item in items:
        cleaned = _normalize_text(item)
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            out.append(cleaned)
    return out


def _resolve_partial_document_meta(
    document_ids: Sequence[str],
    source_files: Sequence[Mapping[str, Any]] | None,
) -> Dict[str, Dict[str, Any]]:
    doc_ids = [doc_id for doc_id in (_normalize_text(item) for item in document_ids) if doc_id]
    if not doc_ids:
        doc_ids = ["workspace-document"]

    files = [dict(item or {}) for item in (source_files or [])]
    mapping: Dict[str, Dict[str, Any]] = {}
    for index, doc_id in enumerate(doc_ids):
        if index < len(files):
            source = files[index]
        elif len(files) == 1:
            source = files[0]
        else:
            source = {}

        file_name = _normalize_text(source.get("file_name")) or f"Document {index + 1}"
        file_hash = _normalize_text(source.get("file_hash")) or doc_id
        mapping[doc_id] = {
            "file_name": file_name,
            "file_hash": file_hash,
            "artifact_path": _normalize_text(source.get("artifact_path")) or None,
            "artifact_url": _normalize_text(source.get("artifact_url")) or None,
            "original_path": _normalize_text(source.get("original_path")) or None,
            "metadata": dict(source.get("metadata") or {}),
        }
    return mapping


@dataclass(frozen=True)
class GraphRAGImportSummary:
    documents: int = 0
    chunks: int = 0
    entities: int = 0
    communities: int = 0
    covariates: int = 0
    nodes: int = 0
    edges: int = 0
    evidence: int = 0
    edge_evidence_links: int = 0
    mode: str = "final"
    partial: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "documents": self.documents,
            "chunks": self.chunks,
            "entities": self.entities,
            "communities": self.communities,
            "covariates": self.covariates,
            "nodes": self.nodes,
            "edges": self.edges,
            "evidence": self.evidence,
            "edge_evidence_links": self.edge_evidence_links,
            "mode": self.mode,
            "partial": self.partial,
        }


class GraphRAGArtifactImporter:
    async def import_into_storage(
        self,
        *,
        storage: Module4Storage,
        tenant_id: str,
        batch_id: str,
        workspace_id: str,
        graph_file_id: str | None = None,
        artifacts_dir: Path,
        source_files: Sequence[Mapping[str, Any]] | None = None,
        import_mode: str | None = None,
    ) -> GraphRAGImportSummary:
        artifacts_dir = artifacts_dir.resolve()
        mode = str(import_mode or "").strip().lower()
        final_documents_path = artifacts_dir / "create_final_documents.parquet"
        if mode == "final" or (not mode and final_documents_path.exists()):
            return await self._import_final_into_storage(
                storage=storage,
                tenant_id=tenant_id,
                batch_id=batch_id,
                workspace_id=workspace_id,
                graph_file_id=graph_file_id,
                artifacts_dir=artifacts_dir,
                source_files=source_files,
            )
        return await self._import_partial_into_storage(
            storage=storage,
            tenant_id=tenant_id,
            batch_id=batch_id,
            workspace_id=workspace_id,
            graph_file_id=graph_file_id,
            artifacts_dir=artifacts_dir,
            source_files=source_files,
        )

    async def _import_final_into_storage(
        self,
        *,
        storage: Module4Storage,
        tenant_id: str,
        batch_id: str,
        workspace_id: str,
        graph_file_id: str | None,
        artifacts_dir: Path,
        source_files: Sequence[Mapping[str, Any]] | None,
    ) -> GraphRAGImportSummary:
        documents = _read_rows(
            artifacts_dir / "create_final_documents.parquet",
            required_columns=("id", "title", "raw_content"),
        )
        text_units = _read_rows(
            artifacts_dir / "create_final_text_units.parquet",
            required_columns=("id", "text", "n_tokens", "document_ids", "entity_ids", "relationship_ids"),
            optional_columns=("covariate_ids",),
        )
        entities = _read_rows(
            artifacts_dir / "create_final_entities.parquet",
            required_columns=("id", "name", "type", "description", "human_readable_id", "text_unit_ids"),
        )
        relationships = _read_rows(
            artifacts_dir / "create_final_relationships.parquet",
            required_columns=("id", "source", "target", "rank", "weight", "human_readable_id", "description", "text_unit_ids"),
        )
        community_reports = _read_optional_rows(artifacts_dir / "create_final_community_reports.parquet")
        communities = _read_rows(
            artifacts_dir / "create_final_communities.parquet",
            required_columns=("id", "level", "title", "text_unit_ids", "relationship_ids"),
        )
        covariates = _read_optional_rows(artifacts_dir / "create_final_covariates.parquet")
        document_ids = [_normalize_text(row.get("id")) for row in documents if _normalize_text(row.get("id"))]
        doc_meta = _resolve_partial_document_meta(document_ids, source_files)

        doc_nodes: Dict[str, Dict[str, Any]] = {}
        doc_rows: Dict[str, Dict[str, Any]] = {}
        chunk_nodes: Dict[str, Dict[str, Any]] = {}
        entity_nodes_by_id: Dict[str, Dict[str, Any]] = {}
        entity_nodes_by_name: Dict[str, Dict[str, Any]] = {}
        community_nodes: Dict[str, Dict[str, Any]] = {}
        relationship_refs: Dict[str, Dict[str, str]] = {}
        chunk_evidence_ids: Dict[str, List[str]] = {}
        relationship_evidence_ids: Dict[str, List[str]] = {}
        community_evidence_ids: Dict[str, List[str]] = {}
        covariate_evidence_ids: Dict[str, List[str]] = {}
        node_count = 0
        edge_count = 0
        evidence_count = 0
        edge_evidence_links = 0
        graph_key_prefix = f"graphrag_final:{workspace_id}"

        async def _upsert_node_scoped(**kwargs: Any) -> Dict[str, Any]:
            return await storage.upsert_node(
                graph_file_id=graph_file_id,
                graph_version_id=None,
                **kwargs,
            )

        async def _upsert_edge_scoped(**kwargs: Any) -> Dict[str, Any]:
            return await storage.upsert_edge(
                graph_file_id=graph_file_id,
                graph_version_id=None,
                **kwargs,
            )

        def _doc_ref_for_document_ids(document_ids_value: Any) -> tuple[Dict[str, Any] | None, Dict[str, Any]]:
            for document_id in _ensure_list(document_ids_value):
                normalized = _normalize_text(document_id)
                if normalized and normalized in doc_rows:
                    return doc_rows[normalized], dict(doc_meta.get(normalized) or {})
            if doc_rows:
                fallback_key = next(iter(doc_rows))
                return doc_rows[fallback_key], dict(doc_meta.get(fallback_key) or {})
            return None, {}

        def _doc_ref_for_chunk_ids(chunk_ids: Any) -> tuple[Dict[str, Any] | None, Dict[str, Any]]:
            for chunk_id in _ensure_list(chunk_ids):
                chunk_node = chunk_nodes.get(_normalize_text(chunk_id))
                if not chunk_node:
                    continue
                attrs = chunk_node.get("attrs") if isinstance(chunk_node.get("attrs"), dict) else {}
                doc_row, meta = _doc_ref_for_document_ids(attrs.get("document_ids"))
                if doc_row:
                    return doc_row, meta
            return _doc_ref_for_document_ids([])

        async def _insert_evidence_row(
            *,
            doc_row: Dict[str, Any] | None,
            object_type: str,
            object_id: str,
            ref_id: str | None,
            snippet: str,
            locator: Dict[str, Any],
            artifact_url: str | None,
            confidence: float,
        ) -> Dict[str, Any] | None:
            nonlocal evidence_count
            if not doc_row:
                return None
            evidence = await storage.insert_evidence(
                tenant_id=tenant_id,
                doc_id=str(doc_row["doc_id"]),
                object_type=object_type,
                object_id=object_id,
                ref_id=ref_id,
                page_no=None,
                snippet=_evidence_snippet(snippet),
                locator=locator,
                bbox=[],
                artifact_url=artifact_url,
                confidence=confidence,
                conn=conn,
            )
            evidence_count += 1
            return evidence

        async def _link_edge_evidence_ids(edge_row: Dict[str, Any], evidence_ids: Sequence[str]) -> None:
            nonlocal edge_evidence_links
            edge_id = str(edge_row.get("edge_id") or "").strip()
            if not edge_id:
                return
            seen = set()
            for evidence_id in evidence_ids:
                normalized = str(evidence_id or "").strip()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                await storage.link_edge_evidence(edge_id=edge_id, evidence_id=normalized, conn=conn)
                edge_evidence_links += 1

        async with storage.transaction() as conn:
            for row in documents:
                graphrag_id = _normalize_text(row.get("id"))
                title = _normalize_text(row.get("title")) or graphrag_id or "Document"
                raw_content = _normalize_text(row.get("raw_content"))
                document_key = _stable_key(f"{graph_key_prefix}:document", graphrag_id or title)
                meta = doc_meta.get(graphrag_id) or {}

                doc_row = await storage.upsert_document(
                    tenant_id=tenant_id,
                    batch_id=batch_id,
                    file_name=title,
                    file_hash=document_key,
                    track="GraphRAG",
                    diagnostics={
                        "graph_source": "graphrag",
                        "workspace_id": workspace_id,
                        "graphrag_document_id": graphrag_id,
                        "artifact_path": meta.get("artifact_path"),
                        "artifact_url": meta.get("artifact_url"),
                        "original_path": meta.get("original_path"),
                    },
                    conn=conn,
                )
                doc_rows[graphrag_id] = doc_row
                doc_node = await _upsert_node_scoped(
                    tenant_id=tenant_id,
                    node_type="Document",
                    canonical_key=document_key,
                    display_name=title,
                    attrs={
                        "graph_source": "graphrag",
                        "workspace_id": workspace_id,
                        "graphrag_id": graphrag_id,
                        "raw_content": raw_content,
                        "artifact_path": meta.get("artifact_path"),
                        "artifact_url": meta.get("artifact_url"),
                        "original_path": meta.get("original_path"),
                        "metadata": dict(meta.get("metadata") or {}),
                    },
                    confidence=1.0,
                    conn=conn,
                )
                doc_nodes[graphrag_id] = doc_node
                node_count += 1
                await _insert_evidence_row(
                    doc_row=doc_row,
                    object_type="document",
                    object_id=graphrag_id or title,
                    ref_id=graphrag_id or None,
                    snippet=raw_content or title,
                    locator={
                        "graph_source": "graphrag",
                        "workspace_id": workspace_id,
                        "graphrag_document_id": graphrag_id,
                    },
                    artifact_url=str(meta.get("artifact_url") or "") or None,
                    confidence=1.0,
                )

            for row in text_units:
                graphrag_id = _normalize_text(row.get("id"))
                text = _normalize_text(row.get("text"))
                row_document_ids = _ensure_list(row.get("document_ids"))
                chunk_node = await _upsert_node_scoped(
                    tenant_id=tenant_id,
                    node_type="Chunk",
                    canonical_key=_stable_key(f"{graph_key_prefix}:chunk", graphrag_id or text),
                    display_name=_display_excerpt(text) or graphrag_id or "Chunk",
                    attrs={
                        "graph_source": "graphrag",
                        "workspace_id": workspace_id,
                        "graphrag_id": graphrag_id,
                        "text": text,
                        "n_tokens": row.get("n_tokens"),
                        "document_ids": row_document_ids,
                        "entity_ids": _ensure_list(row.get("entity_ids")),
                        "relationship_ids": _ensure_list(row.get("relationship_ids")),
                        "covariate_ids": _ensure_list(row.get("covariate_ids")),
                    },
                    confidence=1.0,
                    conn=conn,
                )
                chunk_nodes[graphrag_id] = chunk_node
                node_count += 1
                doc_row, meta = _doc_ref_for_document_ids(row_document_ids)
                chunk_evidence = await _insert_evidence_row(
                    doc_row=doc_row,
                    object_type="chunk",
                    object_id=graphrag_id or _display_excerpt(text),
                    ref_id=graphrag_id or None,
                    snippet=text,
                    locator={
                        "graph_source": "graphrag",
                        "workspace_id": workspace_id,
                        "graphrag_id": graphrag_id,
                        "document_ids": row_document_ids,
                        "n_tokens": row.get("n_tokens"),
                    },
                    artifact_url=str(meta.get("artifact_url") or "") or None,
                    confidence=1.0,
                )
                if chunk_evidence:
                    chunk_evidence_ids[graphrag_id] = [str(chunk_evidence["evidence_id"])]
                for document_id in row_document_ids:
                    doc_node = doc_nodes.get(_normalize_text(document_id))
                    if not doc_node:
                        continue
                    edge = await _upsert_edge_scoped(
                        tenant_id=tenant_id,
                        source_node_id=str(chunk_node["node_id"]),
                        target_node_id=str(doc_node["node_id"]),
                        relation_type="PART_OF",
                        direction="out",
                        attrs={"graph_source": "graphrag", "workspace_id": workspace_id},
                        confidence=1.0,
                        risk_score=0.0,
                        conn=conn,
                    )
                    edge_count += 1
                    await _link_edge_evidence_ids(edge, chunk_evidence_ids.get(graphrag_id, []))

            for row in entities:
                graphrag_id = _normalize_text(row.get("id"))
                name = _normalize_text(row.get("name")) or graphrag_id or "Entity"
                entity_type = _normalize_text(row.get("type")) or "entity"
                text_unit_ids = _ensure_list(row.get("text_unit_ids"))
                entity_node = await _upsert_node_scoped(
                    tenant_id=tenant_id,
                    node_type="Entity",
                    canonical_key=_stable_key(f"{graph_key_prefix}:entity", graphrag_id or name),
                    display_name=name,
                    attrs={
                        "graph_source": "graphrag",
                        "workspace_id": workspace_id,
                        "graphrag_id": graphrag_id,
                        "entity_type": entity_type,
                        "description": _clean_graph_text(row.get("description")),
                        "human_readable_id": _normalize_text(row.get("human_readable_id")),
                        "text_unit_ids": text_unit_ids,
                    },
                    confidence=1.0,
                    conn=conn,
                )
                entity_nodes_by_id[graphrag_id] = entity_node
                entity_nodes_by_name[name] = entity_node
                node_count += 1
                doc_row, meta = _doc_ref_for_chunk_ids(text_unit_ids)
                entity_evidence = await _insert_evidence_row(
                    doc_row=doc_row,
                    object_type="entity",
                    object_id=graphrag_id or name,
                    ref_id=_normalize_text(row.get("human_readable_id")) or graphrag_id or None,
                    snippet=_clean_graph_text(row.get("description")) or name,
                    locator={
                        "graph_source": "graphrag",
                        "workspace_id": workspace_id,
                        "graphrag_id": graphrag_id,
                        "entity_type": entity_type,
                        "text_unit_ids": text_unit_ids,
                    },
                    artifact_url=str(meta.get("artifact_url") or "") or None,
                    confidence=1.0,
                )
                entity_evidence_ids = [str(entity_evidence["evidence_id"])] if entity_evidence else []
                for text_unit_id in text_unit_ids:
                    chunk_node = chunk_nodes.get(_normalize_text(text_unit_id))
                    if not chunk_node:
                        continue
                    edge = await _upsert_edge_scoped(
                        tenant_id=tenant_id,
                        source_node_id=str(chunk_node["node_id"]),
                        target_node_id=str(entity_node["node_id"]),
                        relation_type="HAS_ENTITY",
                        direction="out",
                        attrs={"graph_source": "graphrag", "workspace_id": workspace_id},
                        confidence=1.0,
                        risk_score=0.0,
                        conn=conn,
                    )
                    edge_count += 1
                    await _link_edge_evidence_ids(
                        edge,
                        list(chunk_evidence_ids.get(_normalize_text(text_unit_id), [])) + entity_evidence_ids,
                    )

            for row in relationships:
                relation_id = _normalize_text(row.get("id"))
                source_name = _normalize_text(row.get("source"))
                target_name = _normalize_text(row.get("target"))
                text_unit_ids = _ensure_list(row.get("text_unit_ids"))
                source_node = entity_nodes_by_name.get(source_name)
                target_node = entity_nodes_by_name.get(target_name)
                if not source_node or not target_node:
                    continue
                doc_row, meta = _doc_ref_for_chunk_ids(text_unit_ids)
                relationship_evidence = await _insert_evidence_row(
                    doc_row=doc_row,
                    object_type="relationship",
                    object_id=relation_id or f"{source_name}->{target_name}",
                    ref_id=_normalize_text(row.get("human_readable_id")) or relation_id or None,
                    snippet=_clean_graph_text(row.get("description")) or f"{source_name} -> {target_name}",
                    locator={
                        "graph_source": "graphrag",
                        "workspace_id": workspace_id,
                        "graphrag_id": relation_id,
                        "source": source_name,
                        "target": target_name,
                        "text_unit_ids": text_unit_ids,
                        "rank": row.get("rank"),
                        "weight": row.get("weight"),
                    },
                    artifact_url=str(meta.get("artifact_url") or "") or None,
                    confidence=1.0,
                )
                if relationship_evidence:
                    relationship_evidence_ids[relation_id] = [str(relationship_evidence["evidence_id"])]
                edge = await _upsert_edge_scoped(
                    tenant_id=tenant_id,
                    source_node_id=str(source_node["node_id"]),
                    target_node_id=str(target_node["node_id"]),
                    relation_type="RELATED",
                    direction="out",
                    attrs={
                        "graph_source": "graphrag",
                        "workspace_id": workspace_id,
                        "graphrag_id": relation_id,
                        "rank": row.get("rank"),
                        "weight": row.get("weight"),
                        "human_readable_id": _normalize_text(row.get("human_readable_id")),
                        "description": _clean_graph_text(row.get("description")),
                        "text_unit_ids": text_unit_ids,
                    },
                    confidence=1.0,
                    risk_score=0.0,
                    conn=conn,
                )
                relationship_refs[relation_id] = {
                    "source_node_id": str(source_node["node_id"]),
                    "target_node_id": str(target_node["node_id"]),
                    "edge_id": str(edge["edge_id"]),
                }
                edge_count += 1
                relationship_supporting_evidence = list(relationship_evidence_ids.get(relation_id, []))
                for text_unit_id in text_unit_ids:
                    relationship_supporting_evidence.extend(chunk_evidence_ids.get(_normalize_text(text_unit_id), []))
                await _link_edge_evidence_ids(edge, relationship_supporting_evidence)

            for row in community_reports:
                community_id = _normalize_text(row.get("community")) or _normalize_text(row.get("id"))
                if not community_id:
                    continue
                community_node = await _upsert_node_scoped(
                    tenant_id=tenant_id,
                    node_type="Community",
                    canonical_key=_stable_key(f"{graph_key_prefix}:community", community_id),
                    display_name=_normalize_text(row.get("title")) or community_id or "Community",
                    attrs={
                        "graph_source": "graphrag",
                        "workspace_id": workspace_id,
                        "report_id": _normalize_text(row.get("id")),
                        "graphrag_id": community_id,
                        "community": _normalize_text(row.get("community")),
                        "summary": _clean_graph_text(row.get("summary")),
                        "full_content": _clean_graph_text(row.get("full_content")),
                        "level": row.get("level"),
                        "rank": row.get("rank"),
                        "rank_explanation": _clean_graph_text(row.get("rank_explanation")),
                        "findings": _ensure_list(row.get("findings")),
                    },
                    confidence=1.0,
                    conn=conn,
                )
                community_nodes[community_id] = community_node
                node_count += 1
                doc_row, meta = _doc_ref_for_chunk_ids(_ensure_list(row.get("text_unit_ids")))
                community_evidence = await _insert_evidence_row(
                    doc_row=doc_row,
                    object_type="community",
                    object_id=community_id,
                    ref_id=_normalize_text(row.get("id")) or community_id or None,
                    snippet=_clean_graph_text(row.get("summary")) or _clean_graph_text(row.get("full_content")) or community_id,
                    locator={
                        "graph_source": "graphrag",
                        "workspace_id": workspace_id,
                        "community": community_id,
                        "report_id": _normalize_text(row.get("id")),
                        "level": row.get("level"),
                        "rank": row.get("rank"),
                    },
                    artifact_url=str(meta.get("artifact_url") or "") or None,
                    confidence=1.0,
                )
                if community_evidence:
                    community_evidence_ids[community_id] = [str(community_evidence["evidence_id"])]

            for row in communities:
                community_id = _normalize_text(row.get("id"))
                if not community_id:
                    continue
                row_text_unit_ids = _ensure_list(row.get("text_unit_ids"))
                row_relationship_ids = _ensure_list(row.get("relationship_ids"))
                community_node = community_nodes.get(community_id)
                if not community_node:
                    community_node = await _upsert_node_scoped(
                        tenant_id=tenant_id,
                        node_type="Community",
                        canonical_key=_stable_key(f"{graph_key_prefix}:community", community_id),
                        display_name=_normalize_text(row.get("title")) or community_id or "Community",
                        attrs={
                            "graph_source": "graphrag",
                            "workspace_id": workspace_id,
                            "graphrag_id": community_id,
                            "level": row.get("level"),
                            "text_unit_ids": row_text_unit_ids,
                            "relationship_ids": row_relationship_ids,
                        },
                        confidence=1.0,
                        conn=conn,
                    )
                    community_nodes[community_id] = community_node
                    node_count += 1
                else:
                    existing_attrs = dict(community_node.get("attrs") or {})
                    merged_attrs = {
                        **existing_attrs,
                        "graph_source": "graphrag",
                        "workspace_id": workspace_id,
                        "graphrag_id": community_id,
                        "level": row.get("level"),
                        "text_unit_ids": row_text_unit_ids,
                        "relationship_ids": row_relationship_ids,
                    }
                    row_title = _normalize_text(row.get("title"))
                    display_name = (
                        str(community_node.get("display_name") or "").strip()
                        if _is_placeholder_community_title(row_title, community_id)
                        else row_title
                    ) or community_id or "Community"
                    community_node = await _upsert_node_scoped(
                        tenant_id=tenant_id,
                        node_type="Community",
                        canonical_key=_stable_key(f"{graph_key_prefix}:community", community_id),
                        display_name=display_name,
                        attrs=merged_attrs,
                        confidence=1.0,
                        conn=conn,
                    )
                    community_nodes[community_id] = community_node

                if community_id not in community_evidence_ids:
                    doc_row, meta = _doc_ref_for_chunk_ids(row_text_unit_ids)
                    community_evidence = await _insert_evidence_row(
                        doc_row=doc_row,
                        object_type="community",
                        object_id=community_id,
                        ref_id=community_id or None,
                        snippet=_normalize_text(row.get("title")) or community_id,
                        locator={
                            "graph_source": "graphrag",
                            "workspace_id": workspace_id,
                            "community": community_id,
                            "level": row.get("level"),
                            "text_unit_ids": row_text_unit_ids,
                            "relationship_ids": row_relationship_ids,
                        },
                        artifact_url=str(meta.get("artifact_url") or "") or None,
                        confidence=1.0,
                    )
                    if community_evidence:
                        community_evidence_ids[community_id] = [str(community_evidence["evidence_id"])]

                for text_unit_id in row_text_unit_ids:
                    chunk_node = chunk_nodes.get(_normalize_text(text_unit_id))
                    if not chunk_node:
                        continue
                    edge = await _upsert_edge_scoped(
                        tenant_id=tenant_id,
                        source_node_id=str(community_node["node_id"]),
                        target_node_id=str(chunk_node["node_id"]),
                        relation_type="HAS_CHUNK",
                        direction="out",
                        attrs={"graph_source": "graphrag", "workspace_id": workspace_id},
                        confidence=1.0,
                        risk_score=0.0,
                        conn=conn,
                    )
                    edge_count += 1
                    await _link_edge_evidence_ids(
                        edge,
                        list(chunk_evidence_ids.get(_normalize_text(text_unit_id), [])) + list(community_evidence_ids.get(community_id, [])),
                    )

                for relation_id in row_relationship_ids:
                    relation_ref = relationship_refs.get(_normalize_text(relation_id))
                    if not relation_ref:
                        continue
                    for key in ("source_node_id", "target_node_id"):
                        edge = await _upsert_edge_scoped(
                            tenant_id=tenant_id,
                            source_node_id=str(relation_ref[key]),
                            target_node_id=str(community_node["node_id"]),
                            relation_type="IN_COMMUNITY",
                            direction="out",
                            attrs={
                                "graph_source": "graphrag",
                                "workspace_id": workspace_id,
                                "relationship_id": _normalize_text(relation_id),
                            },
                            confidence=1.0,
                            risk_score=0.0,
                            conn=conn,
                        )
                        edge_count += 1
                        await _link_edge_evidence_ids(
                            edge,
                            list(relationship_evidence_ids.get(_normalize_text(relation_id), []))
                            + list(community_evidence_ids.get(community_id, [])),
                        )

            for row in covariates:
                covariate_id = _normalize_text(row.get("id"))
                title = _normalize_text(row.get("title")) or covariate_id or "Covariate"
                covariate_node = await _upsert_node_scoped(
                    tenant_id=tenant_id,
                    node_type="Covariate",
                    canonical_key=_stable_key(f"{graph_key_prefix}:covariate", covariate_id or title),
                    display_name=title,
                    attrs={
                        "graph_source": "graphrag",
                        "workspace_id": workspace_id,
                        **{str(key): value for key, value in row.items()},
                    },
                    confidence=1.0,
                    conn=conn,
                )
                node_count += 1
                text_unit_id = _normalize_text(row.get("text_unit_id"))
                doc_row, meta = _doc_ref_for_chunk_ids([text_unit_id])
                covariate_evidence = await _insert_evidence_row(
                    doc_row=doc_row,
                    object_type="covariate",
                    object_id=covariate_id or title,
                    ref_id=covariate_id or None,
                    snippet=title,
                    locator={
                        "graph_source": "graphrag",
                        "workspace_id": workspace_id,
                        "graphrag_id": covariate_id,
                        "text_unit_id": text_unit_id,
                    },
                    artifact_url=str(meta.get("artifact_url") or "") or None,
                    confidence=1.0,
                )
                if covariate_evidence:
                    covariate_evidence_ids[covariate_id] = [str(covariate_evidence["evidence_id"])]
                chunk_node = chunk_nodes.get(text_unit_id)
                if chunk_node:
                    edge = await _upsert_edge_scoped(
                        tenant_id=tenant_id,
                        source_node_id=str(chunk_node["node_id"]),
                        target_node_id=str(covariate_node["node_id"]),
                        relation_type="HAS_COVARIATE",
                        direction="out",
                        attrs={"graph_source": "graphrag", "workspace_id": workspace_id},
                        confidence=1.0,
                        risk_score=0.0,
                        conn=conn,
                    )
                    edge_count += 1
                    await _link_edge_evidence_ids(
                        edge,
                        list(chunk_evidence_ids.get(text_unit_id, [])) + list(covariate_evidence_ids.get(covariate_id, [])),
                    )

        return GraphRAGImportSummary(
            documents=len(documents),
            chunks=len(text_units),
            entities=len(entities),
            communities=len(community_nodes),
            covariates=len(covariates),
            nodes=node_count,
            edges=edge_count,
            evidence=evidence_count,
            edge_evidence_links=edge_evidence_links,
            mode="final",
            partial=False,
        )

    async def _import_partial_into_storage(
        self,
        *,
        storage: Module4Storage,
        tenant_id: str,
        batch_id: str,
        workspace_id: str,
        graph_file_id: str | None,
        artifacts_dir: Path,
        source_files: Sequence[Mapping[str, Any]] | None,
    ) -> GraphRAGImportSummary:
        text_units = _read_rows(
            artifacts_dir / "create_base_text_units.parquet",
            required_columns=("id", "chunk", "document_ids", "n_tokens"),
            optional_columns=("chunk_id",),
        )
        if not text_units:
            raise ValueError(f"No usable partial GraphRAG artifacts found under {artifacts_dir}")

        entity_graph_rows: List[Dict[str, Any]] = []
        for candidate in ("create_summarized_entities.parquet", "create_base_extracted_entities.parquet"):
            path = artifacts_dir / candidate
            if path.exists():
                entity_graph_rows = _read_rows(path, required_columns=("entity_graph",))
                if entity_graph_rows:
                    break

        unique_document_ids: List[str] = []
        seen_doc_ids = set()
        document_text_map: Dict[str, List[str]] = {}
        for row in text_units:
            row_doc_ids = [_normalize_text(item) for item in _ensure_list(row.get("document_ids")) if _normalize_text(item)]
            if not row_doc_ids:
                row_doc_ids = ["workspace-document"]
            for doc_id in row_doc_ids:
                if doc_id not in seen_doc_ids:
                    seen_doc_ids.add(doc_id)
                    unique_document_ids.append(doc_id)
                document_text_map.setdefault(doc_id, []).append(_normalize_text(row.get("chunk")))

        doc_meta = _resolve_partial_document_meta(unique_document_ids, source_files)
        parsed_entity_nodes: List[Dict[str, Any]] = []
        parsed_entity_edges: List[Dict[str, Any]] = []
        for row in entity_graph_rows:
            nodes, edges = _parse_graphml_rows(_normalize_text(row.get("entity_graph")))
            parsed_entity_nodes.extend(nodes)
            parsed_entity_edges.extend(edges)

        doc_nodes: Dict[str, Dict[str, Any]] = {}
        doc_rows: Dict[str, Dict[str, Any]] = {}
        chunk_nodes: Dict[str, Dict[str, Any]] = {}
        entity_nodes_by_name: Dict[str, Dict[str, Any]] = {}
        chunk_evidence_ids: Dict[str, List[str]] = {}
        node_count = 0
        edge_count = 0
        evidence_count = 0
        edge_evidence_links = 0

        async def _upsert_node_scoped(**kwargs: Any) -> Dict[str, Any]:
            return await storage.upsert_node(
                graph_file_id=graph_file_id,
                graph_version_id=None,
                **kwargs,
            )

        async def _upsert_edge_scoped(**kwargs: Any) -> Dict[str, Any]:
            return await storage.upsert_edge(
                graph_file_id=graph_file_id,
                graph_version_id=None,
                **kwargs,
            )

        def _doc_ref_for_document_ids(document_ids_value: Any) -> tuple[Dict[str, Any] | None, Dict[str, Any]]:
            for document_id in _ensure_list(document_ids_value):
                normalized = _normalize_text(document_id)
                if normalized and normalized in doc_rows:
                    return doc_rows[normalized], dict(doc_meta.get(normalized) or {})
            if doc_rows:
                fallback_key = next(iter(doc_rows))
                return doc_rows[fallback_key], dict(doc_meta.get(fallback_key) or {})
            return None, {}

        async def _insert_evidence_row(
            *,
            doc_row: Dict[str, Any] | None,
            object_type: str,
            object_id: str,
            ref_id: str | None,
            snippet: str,
            locator: Dict[str, Any],
            artifact_url: str | None,
            confidence: float,
        ) -> Dict[str, Any] | None:
            nonlocal evidence_count
            if not doc_row:
                return None
            evidence = await storage.insert_evidence(
                tenant_id=tenant_id,
                doc_id=str(doc_row["doc_id"]),
                object_type=object_type,
                object_id=object_id,
                ref_id=ref_id,
                page_no=None,
                snippet=_evidence_snippet(snippet),
                locator=locator,
                bbox=[],
                artifact_url=artifact_url,
                confidence=confidence,
                conn=conn,
            )
            evidence_count += 1
            return evidence

        async def _link_edge_evidence_ids(edge_row: Dict[str, Any], evidence_ids: Sequence[str]) -> None:
            nonlocal edge_evidence_links
            edge_id = str(edge_row.get("edge_id") or "").strip()
            if not edge_id:
                return
            seen = set()
            for evidence_id in evidence_ids:
                normalized = str(evidence_id or "").strip()
                if not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                await storage.link_edge_evidence(edge_id=edge_id, evidence_id=normalized, conn=conn)
                edge_evidence_links += 1

        async with storage.transaction() as conn:
            for doc_id in unique_document_ids:
                meta = doc_meta.get(doc_id) or {"file_name": doc_id or "Document", "file_hash": doc_id or "document"}
                raw_content = "\n\n".join(part for part in document_text_map.get(doc_id, []) if part).strip()
                doc_row = await storage.upsert_document(
                    tenant_id=tenant_id,
                    batch_id=batch_id,
                    file_name=str(meta.get("file_name") or doc_id or "Document"),
                    file_hash=str(meta.get("file_hash") or doc_id or "document"),
                    track="GraphRAGPartial",
                    diagnostics={
                        "graph_source": "graphrag_partial",
                        "workspace_id": workspace_id,
                        "graphrag_document_id": doc_id,
                        "artifact_path": meta.get("artifact_path"),
                        "artifact_url": meta.get("artifact_url"),
                        "original_path": meta.get("original_path"),
                    },
                    conn=conn,
                )
                doc_rows[doc_id] = doc_row
                doc_node = await _upsert_node_scoped(
                    tenant_id=tenant_id,
                    node_type="Document",
                    canonical_key=_stable_key(f"graphrag_partial_document:{workspace_id}", doc_id),
                    display_name=str(meta.get("file_name") or doc_id or "Document"),
                    attrs={
                        "graph_source": "graphrag_partial",
                        "workspace_id": workspace_id,
                        "graphrag_id": doc_id,
                        "raw_content": raw_content,
                        "artifact_path": meta.get("artifact_path"),
                        "artifact_url": meta.get("artifact_url"),
                        "original_path": meta.get("original_path"),
                        "metadata": dict(meta.get("metadata") or {}),
                    },
                    confidence=0.9,
                    conn=conn,
                )
                doc_nodes[doc_id] = doc_node
                node_count += 1
                await _insert_evidence_row(
                    doc_row=doc_row,
                    object_type="document",
                    object_id=doc_id or str(meta.get("file_name") or "Document"),
                    ref_id=doc_id or None,
                    snippet=raw_content or str(meta.get("file_name") or doc_id or "Document"),
                    locator={
                        "graph_source": "graphrag_partial",
                        "workspace_id": workspace_id,
                        "graphrag_document_id": doc_id,
                    },
                    artifact_url=str(meta.get("artifact_url") or "") or None,
                    confidence=0.9,
                )

            for row in text_units:
                chunk_id = _normalize_text(row.get("id")) or _normalize_text(row.get("chunk_id")) or "chunk"
                text = _normalize_text(row.get("chunk"))
                row_doc_ids = [_normalize_text(item) for item in _ensure_list(row.get("document_ids")) if _normalize_text(item)]
                if not row_doc_ids:
                    row_doc_ids = unique_document_ids[:1] or ["workspace-document"]

                chunk_node = await _upsert_node_scoped(
                    tenant_id=tenant_id,
                    node_type="Chunk",
                    canonical_key=_stable_key(f"graphrag_partial_chunk:{workspace_id}", chunk_id),
                    display_name=_display_excerpt(text) or chunk_id or "Chunk",
                    attrs={
                        "graph_source": "graphrag_partial",
                        "workspace_id": workspace_id,
                        "graphrag_id": chunk_id,
                        "text": text,
                        "n_tokens": row.get("n_tokens"),
                        "document_ids": row_doc_ids,
                    },
                    confidence=0.9,
                    conn=conn,
                )
                chunk_nodes[chunk_id] = chunk_node
                node_count += 1
                doc_row, meta = _doc_ref_for_document_ids(row_doc_ids)
                chunk_evidence = await _insert_evidence_row(
                    doc_row=doc_row,
                    object_type="chunk",
                    object_id=chunk_id,
                    ref_id=chunk_id,
                    snippet=text,
                    locator={
                        "graph_source": "graphrag_partial",
                        "workspace_id": workspace_id,
                        "graphrag_id": chunk_id,
                        "document_ids": row_doc_ids,
                        "n_tokens": row.get("n_tokens"),
                    },
                    artifact_url=str(meta.get("artifact_url") or "") or None,
                    confidence=0.9,
                )
                if chunk_evidence:
                    chunk_evidence_ids[chunk_id] = [str(chunk_evidence["evidence_id"])]

                for doc_id in row_doc_ids:
                    doc_node = doc_nodes.get(doc_id)
                    if not doc_node:
                        continue
                    edge = await _upsert_edge_scoped(
                        tenant_id=tenant_id,
                        source_node_id=str(chunk_node["node_id"]),
                        target_node_id=str(doc_node["node_id"]),
                        relation_type="PART_OF",
                        direction="out",
                        attrs={"graph_source": "graphrag_partial", "workspace_id": workspace_id},
                        confidence=0.9,
                        risk_score=0.0,
                        conn=conn,
                    )
                    edge_count += 1
                    await _link_edge_evidence_ids(edge, chunk_evidence_ids.get(chunk_id, []))

            for row in parsed_entity_nodes:
                name = _normalize_text(row.get("id")) or "Entity"
                source_chunk_ids = _split_source_ids(row.get("source_id"))
                entity_node = await _upsert_node_scoped(
                    tenant_id=tenant_id,
                    node_type="Entity",
                    canonical_key=_stable_key(f"graphrag_partial_entity:{workspace_id}", name),
                    display_name=name,
                    attrs={
                        "graph_source": "graphrag_partial",
                        "workspace_id": workspace_id,
                        "entity_type": _normalize_text(row.get("type")) or "entity",
                        "description": _clean_graph_text(row.get("description")),
                        "source_chunk_ids": source_chunk_ids,
                    },
                    confidence=0.8,
                    conn=conn,
                )
                entity_nodes_by_name[name] = entity_node
                node_count += 1
                doc_row, meta = _doc_ref_for_document_ids(
                    list(
                        {
                            doc_id
                            for chunk_id in source_chunk_ids
                            for doc_id in (
                                (chunk_nodes.get(chunk_id) or {}).get("attrs", {}).get("document_ids", [])
                                if isinstance((chunk_nodes.get(chunk_id) or {}).get("attrs"), dict)
                                else []
                            )
                        }
                    )
                )
                await _insert_evidence_row(
                    doc_row=doc_row,
                    object_type="entity",
                    object_id=name,
                    ref_id=name,
                    snippet=_clean_graph_text(row.get("description")) or name,
                    locator={
                        "graph_source": "graphrag_partial",
                        "workspace_id": workspace_id,
                        "entity_type": _normalize_text(row.get("type")) or "entity",
                        "source_chunk_ids": source_chunk_ids,
                    },
                    artifact_url=str(meta.get("artifact_url") or "") or None,
                    confidence=0.8,
                )

                for chunk_id in source_chunk_ids:
                    chunk_node = chunk_nodes.get(chunk_id)
                    if not chunk_node:
                        continue
                    edge = await _upsert_edge_scoped(
                        tenant_id=tenant_id,
                        source_node_id=str(chunk_node["node_id"]),
                        target_node_id=str(entity_node["node_id"]),
                        relation_type="HAS_ENTITY",
                        direction="out",
                        attrs={"graph_source": "graphrag_partial", "workspace_id": workspace_id},
                        confidence=0.8,
                        risk_score=0.0,
                        conn=conn,
                    )
                    edge_count += 1
                    await _link_edge_evidence_ids(edge, chunk_evidence_ids.get(chunk_id, []))

            for row in parsed_entity_edges:
                source_node = entity_nodes_by_name.get(_normalize_text(row.get("source")))
                target_node = entity_nodes_by_name.get(_normalize_text(row.get("target")))
                if not source_node or not target_node:
                    continue
                source_chunk_ids = _split_source_ids(row.get("source_id"))
                edge = await _upsert_edge_scoped(
                    tenant_id=tenant_id,
                    source_node_id=str(source_node["node_id"]),
                    target_node_id=str(target_node["node_id"]),
                    relation_type="RELATED",
                    direction="out",
                    attrs={
                        "graph_source": "graphrag_partial",
                        "workspace_id": workspace_id,
                        "description": _clean_graph_text(row.get("description")),
                        "weight": row.get("weight"),
                        "source_chunk_ids": source_chunk_ids,
                    },
                    confidence=0.75,
                    risk_score=0.0,
                    conn=conn,
                )
                edge_count += 1
                supporting_evidence: List[str] = []
                for chunk_id in source_chunk_ids:
                    supporting_evidence.extend(chunk_evidence_ids.get(chunk_id, []))
                await _link_edge_evidence_ids(edge, supporting_evidence)

        return GraphRAGImportSummary(
            documents=len(unique_document_ids),
            chunks=len(text_units),
            entities=len(entity_nodes_by_name),
            communities=0,
            covariates=0,
            nodes=node_count,
            edges=edge_count,
            evidence=evidence_count,
            edge_evidence_links=edge_evidence_links,
            mode="partial",
            partial=True,
        )
