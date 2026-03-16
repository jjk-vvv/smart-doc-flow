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
        artifacts_dir: Path,
        source_files: Sequence[Mapping[str, Any]] | None = None,
    ) -> GraphRAGImportSummary:
        artifacts_dir = artifacts_dir.resolve()
        final_documents_path = artifacts_dir / "create_final_documents.parquet"
        if final_documents_path.exists():
            return await self._import_final_into_storage(
                storage=storage,
                tenant_id=tenant_id,
                batch_id=batch_id,
                workspace_id=workspace_id,
                artifacts_dir=artifacts_dir,
            )
        return await self._import_partial_into_storage(
            storage=storage,
            tenant_id=tenant_id,
            batch_id=batch_id,
            workspace_id=workspace_id,
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
        artifacts_dir: Path,
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

        doc_nodes: Dict[str, Dict[str, Any]] = {}
        chunk_nodes: Dict[str, Dict[str, Any]] = {}
        entity_nodes_by_id: Dict[str, Dict[str, Any]] = {}
        entity_nodes_by_name: Dict[str, Dict[str, Any]] = {}
        community_nodes: Dict[str, Dict[str, Any]] = {}
        relationship_refs: Dict[str, Dict[str, str]] = {}
        node_count = 0
        edge_count = 0

        async with storage.transaction() as conn:
            for row in documents:
                graphrag_id = _normalize_text(row.get("id"))
                title = _normalize_text(row.get("title")) or graphrag_id or "Document"
                raw_content = _normalize_text(row.get("raw_content"))

                await storage.upsert_document(
                    tenant_id=tenant_id,
                    batch_id=batch_id,
                    file_name=title,
                    file_hash=graphrag_id or title,
                    track="GraphRAG",
                    diagnostics={
                        "graph_source": "graphrag",
                        "workspace_id": workspace_id,
                        "graphrag_document_id": graphrag_id,
                    },
                    conn=conn,
                )
                doc_node = await storage.upsert_node(
                    tenant_id=tenant_id,
                    node_type="Document",
                    canonical_key=f"graphrag_document:{graphrag_id}",
                    display_name=title,
                    attrs={
                        "graph_source": "graphrag",
                        "workspace_id": workspace_id,
                        "graphrag_id": graphrag_id,
                        "raw_content": raw_content,
                    },
                    confidence=1.0,
                    conn=conn,
                )
                doc_nodes[graphrag_id] = doc_node
                node_count += 1

            for row in text_units:
                graphrag_id = _normalize_text(row.get("id"))
                text = _normalize_text(row.get("text"))
                chunk_node = await storage.upsert_node(
                    tenant_id=tenant_id,
                    node_type="Chunk",
                    canonical_key=f"graphrag_chunk:{graphrag_id}",
                    display_name=_display_excerpt(text) or graphrag_id or "Chunk",
                    attrs={
                        "graph_source": "graphrag",
                        "workspace_id": workspace_id,
                        "graphrag_id": graphrag_id,
                        "text": text,
                        "n_tokens": row.get("n_tokens"),
                        "document_ids": _ensure_list(row.get("document_ids")),
                        "entity_ids": _ensure_list(row.get("entity_ids")),
                        "relationship_ids": _ensure_list(row.get("relationship_ids")),
                        "covariate_ids": _ensure_list(row.get("covariate_ids")),
                    },
                    confidence=1.0,
                    conn=conn,
                )
                chunk_nodes[graphrag_id] = chunk_node
                node_count += 1
                for document_id in _ensure_list(row.get("document_ids")):
                    doc_node = doc_nodes.get(_normalize_text(document_id))
                    if not doc_node:
                        continue
                    await storage.upsert_edge(
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

            for row in entities:
                graphrag_id = _normalize_text(row.get("id"))
                name = _normalize_text(row.get("name")) or graphrag_id or "Entity"
                entity_type = _normalize_text(row.get("type")) or "entity"
                entity_node = await storage.upsert_node(
                    tenant_id=tenant_id,
                    node_type="Entity",
                    canonical_key=f"graphrag_entity:{graphrag_id}",
                    display_name=name,
                    attrs={
                        "graph_source": "graphrag",
                        "workspace_id": workspace_id,
                        "graphrag_id": graphrag_id,
                        "entity_type": entity_type,
                        "description": _clean_graph_text(row.get("description")),
                        "human_readable_id": _normalize_text(row.get("human_readable_id")),
                        "text_unit_ids": _ensure_list(row.get("text_unit_ids")),
                    },
                    confidence=1.0,
                    conn=conn,
                )
                entity_nodes_by_id[graphrag_id] = entity_node
                entity_nodes_by_name[name] = entity_node
                node_count += 1
                for text_unit_id in _ensure_list(row.get("text_unit_ids")):
                    chunk_node = chunk_nodes.get(_normalize_text(text_unit_id))
                    if not chunk_node:
                        continue
                    await storage.upsert_edge(
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

            for row in relationships:
                relation_id = _normalize_text(row.get("id"))
                source_name = _normalize_text(row.get("source"))
                target_name = _normalize_text(row.get("target"))
                source_node = entity_nodes_by_name.get(source_name)
                target_node = entity_nodes_by_name.get(target_name)
                if not source_node or not target_node:
                    continue
                edge = await storage.upsert_edge(
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
                        "text_unit_ids": _ensure_list(row.get("text_unit_ids")),
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

            for row in community_reports:
                community_id = _normalize_text(row.get("community")) or _normalize_text(row.get("id"))
                if not community_id:
                    continue
                community_node = await storage.upsert_node(
                    tenant_id=tenant_id,
                    node_type="Community",
                    canonical_key=f"graphrag_community:{community_id}",
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

            for row in communities:
                community_id = _normalize_text(row.get("id"))
                if not community_id:
                    continue
                community_node = community_nodes.get(community_id)
                if not community_node:
                    community_node = await storage.upsert_node(
                        tenant_id=tenant_id,
                        node_type="Community",
                        canonical_key=f"graphrag_community:{community_id}",
                        display_name=_normalize_text(row.get("title")) or community_id or "Community",
                        attrs={
                            "graph_source": "graphrag",
                            "workspace_id": workspace_id,
                            "graphrag_id": community_id,
                            "level": row.get("level"),
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
                        "text_unit_ids": _ensure_list(row.get("text_unit_ids")),
                        "relationship_ids": _ensure_list(row.get("relationship_ids")),
                    }
                    row_title = _normalize_text(row.get("title"))
                    display_name = (
                        str(community_node.get("display_name") or "").strip()
                        if _is_placeholder_community_title(row_title, community_id)
                        else row_title
                    ) or community_id or "Community"
                    community_node = await storage.upsert_node(
                        tenant_id=tenant_id,
                        node_type="Community",
                        canonical_key=f"graphrag_community:{community_id}",
                        display_name=display_name,
                        attrs=merged_attrs,
                        confidence=1.0,
                        conn=conn,
                    )
                    community_nodes[community_id] = community_node

                for text_unit_id in _ensure_list(row.get("text_unit_ids")):
                    chunk_node = chunk_nodes.get(_normalize_text(text_unit_id))
                    if not chunk_node:
                        continue
                    await storage.upsert_edge(
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

                for relation_id in _ensure_list(row.get("relationship_ids")):
                    relation_ref = relationship_refs.get(_normalize_text(relation_id))
                    if not relation_ref:
                        continue
                    for key in ("source_node_id", "target_node_id"):
                        await storage.upsert_edge(
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

            for row in covariates:
                covariate_id = _normalize_text(row.get("id"))
                title = _normalize_text(row.get("title")) or covariate_id or "Covariate"
                covariate_node = await storage.upsert_node(
                    tenant_id=tenant_id,
                    node_type="Covariate",
                    canonical_key=f"graphrag_covariate:{covariate_id}",
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
                chunk_node = chunk_nodes.get(text_unit_id)
                if chunk_node:
                    await storage.upsert_edge(
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

        return GraphRAGImportSummary(
            documents=len(documents),
            chunks=len(text_units),
            entities=len(entities),
            communities=len(community_nodes),
            covariates=len(covariates),
            nodes=node_count,
            edges=edge_count,
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
        chunk_nodes: Dict[str, Dict[str, Any]] = {}
        entity_nodes_by_name: Dict[str, Dict[str, Any]] = {}
        node_count = 0
        edge_count = 0

        async with storage.transaction() as conn:
            for doc_id in unique_document_ids:
                meta = doc_meta.get(doc_id) or {"file_name": doc_id or "Document", "file_hash": doc_id or "document"}
                raw_content = "\n\n".join(part for part in document_text_map.get(doc_id, []) if part).strip()
                await storage.upsert_document(
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
                doc_node = await storage.upsert_node(
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

            for row in text_units:
                chunk_id = _normalize_text(row.get("id")) or _normalize_text(row.get("chunk_id")) or "chunk"
                text = _normalize_text(row.get("chunk"))
                row_doc_ids = [_normalize_text(item) for item in _ensure_list(row.get("document_ids")) if _normalize_text(item)]
                if not row_doc_ids:
                    row_doc_ids = unique_document_ids[:1] or ["workspace-document"]

                chunk_node = await storage.upsert_node(
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

                for doc_id in row_doc_ids:
                    doc_node = doc_nodes.get(doc_id)
                    if not doc_node:
                        continue
                    await storage.upsert_edge(
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

            for row in parsed_entity_nodes:
                name = _normalize_text(row.get("id")) or "Entity"
                source_chunk_ids = _split_source_ids(row.get("source_id"))
                entity_node = await storage.upsert_node(
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

                for chunk_id in source_chunk_ids:
                    chunk_node = chunk_nodes.get(chunk_id)
                    if not chunk_node:
                        continue
                    await storage.upsert_edge(
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

            for row in parsed_entity_edges:
                source_node = entity_nodes_by_name.get(_normalize_text(row.get("source")))
                target_node = entity_nodes_by_name.get(_normalize_text(row.get("target")))
                if not source_node or not target_node:
                    continue
                await storage.upsert_edge(
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
                        "source_chunk_ids": _split_source_ids(row.get("source_id")),
                    },
                    confidence=0.75,
                    risk_score=0.0,
                    conn=conn,
                )
                edge_count += 1

        return GraphRAGImportSummary(
            documents=len(unique_document_ids),
            chunks=len(text_units),
            entities=len(entity_nodes_by_name),
            communities=0,
            covariates=0,
            nodes=node_count,
            edges=edge_count,
            mode="partial",
            partial=True,
        )
