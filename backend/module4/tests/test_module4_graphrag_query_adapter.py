from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi import HTTPException

MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.composition.app_runtime import build_query_runtime_helpers  # noqa: E402
from app.services.query.runtime import (  # noqa: E402
    graph_file_node_detail_response,
    graph_file_view_response,
    graph_response,
    list_graph_files_response,
    neighborhood_response,
)


def _write_parquet(path: Path, rows: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


def _seed_final_artifacts(artifacts_dir: Path) -> None:
    _write_parquet(
        artifacts_dir / "create_final_documents.parquet",
        [
            {
                "id": "doc-1",
                "title": "Contract Overview",
                "raw_content": "Acme signed with Contoso.",
            }
        ],
    )
    _write_parquet(
        artifacts_dir / "create_final_text_units.parquet",
        [
            {
                "id": "chunk-1",
                "text": "Acme signed with Contoso in 2025.",
                "n_tokens": 32,
                "document_ids": ["doc-1"],
                "entity_ids": ["ent-1", "ent-2"],
                "relationship_ids": ["rel-1"],
            }
        ],
    )
    _write_parquet(
        artifacts_dir / "create_final_entities.parquet",
        [
            {
                "id": "ent-1",
                "name": "Acme",
                "type": "organization",
                "description": "Party A",
                "human_readable_id": 1,
                "text_unit_ids": ["chunk-1"],
                "community_ids": ["comm-1"],
            },
            {
                "id": "ent-2",
                "name": "Contoso",
                "type": "organization",
                "description": "Party B",
                "human_readable_id": 2,
                "text_unit_ids": ["chunk-1"],
                "community_ids": ["comm-1"],
            },
        ],
    )
    _write_parquet(
        artifacts_dir / "create_final_relationships.parquet",
        [
            {
                "id": "rel-1",
                "source": "Acme",
                "target": "Contoso",
                "rank": 1,
                "weight": 0.87,
                "human_readable_id": 1,
                "description": "signed_with",
                "text_unit_ids": ["chunk-1"],
            }
        ],
    )
    _write_parquet(
        artifacts_dir / "create_final_communities.parquet",
        [
            {
                "id": "comm-1",
                "level": 0,
                "title": "Contract Parties",
                "text_unit_ids": ["chunk-1"],
                "relationship_ids": ["rel-1"],
            }
        ],
    )
    _write_parquet(
        artifacts_dir / "create_final_community_reports.parquet",
        [
            {
                "id": "report-1",
                "community": "comm-1",
                "title": "Community Report 1",
                "summary": "Acme and Contoso contract summary.",
                "full_content": "Detailed findings",
                "level": 0,
                "rank": 1,
                "rank_explanation": "highest rank",
            }
        ],
    )


def _seed_v3_final_artifacts(artifacts_dir: Path) -> None:
    _write_parquet(
        artifacts_dir / "documents.parquet",
        [
            {
                "id": "doc-1",
                "human_readable_id": 1,
                "title": "Contract Overview",
                "text": "Acme signed with Contoso.",
                "text_unit_ids": ["chunk-1"],
                "raw_data": '{"source":"demo"}',
            }
        ],
    )
    _write_parquet(
        artifacts_dir / "text_units.parquet",
        [
            {
                "id": "chunk-1",
                "human_readable_id": 1,
                "text": "Acme signed with Contoso in 2025.",
                "n_tokens": 32,
                "document_id": "doc-1",
                "entity_ids": ["ent-1", "ent-2"],
                "relationship_ids": ["rel-1"],
            }
        ],
    )
    _write_parquet(
        artifacts_dir / "entities.parquet",
        [
            {
                "id": "ent-1",
                "title": "Acme",
                "type": "organization",
                "description": "Party A",
                "human_readable_id": 1,
                "text_unit_ids": ["chunk-1"],
                "community_ids": ["comm-1"],
            },
            {
                "id": "ent-2",
                "title": "Contoso",
                "type": "organization",
                "description": "Party B",
                "human_readable_id": 2,
                "text_unit_ids": ["chunk-1"],
                "community_ids": ["comm-1"],
            },
        ],
    )
    _write_parquet(
        artifacts_dir / "relationships.parquet",
        [
            {
                "id": "rel-1",
                "source": "Acme",
                "target": "Contoso",
                "combined_degree": 5,
                "weight": 0.87,
                "human_readable_id": 1,
                "description": "signed_with",
                "text_unit_ids": ["chunk-1"],
            }
        ],
    )
    _write_parquet(
        artifacts_dir / "communities.parquet",
        [
            {
                "id": "comm-row-1",
                "community": "comm-1",
                "level": 0,
                "title": "Contract Parties",
                "text_unit_ids": ["chunk-1"],
                "relationship_ids": ["rel-1"],
            }
        ],
    )
    _write_parquet(
        artifacts_dir / "community_reports.parquet",
        [
            {
                "id": "report-1",
                "community": "comm-1",
                "title": "Community Report 1",
                "summary": "Acme and Contoso contract summary.",
                "full_content": "Detailed findings",
                "level": 0,
                "rank": 1,
                "rating_explanation": "highest rank",
            }
        ],
    )


class _FakeStorage:
    def __init__(self, graph_file_row: Dict[str, Any]) -> None:
        self.graph_file_row = graph_file_row
        self.evidence_rows: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
        self.graph_files: List[Dict[str, Any]] = [dict(graph_file_row)]
        self.list_graph_files_limits: List[int] = []

    async def get_graph_file(self, *, tenant_id: str, file_hash: str) -> Dict[str, Any] | None:
        if tenant_id != str(self.graph_file_row.get("tenant_id") or ""):
            return None
        if file_hash != str(self.graph_file_row.get("file_hash") or ""):
            return None
        return dict(self.graph_file_row)

    async def list_graph_files(
        self,
        *,
        tenant_id: str,
        status: str | None,
        limit: int,
    ) -> List[Dict[str, Any]]:
        self.list_graph_files_limits.append(int(limit))
        rows = [dict(item) for item in self.graph_files if str(item.get("tenant_id") or "") == tenant_id]
        if status:
            rows = [item for item in rows if str(item.get("status") or "ready") == status]
        return rows[:limit]

    async def list_evidence(
        self,
        *,
        tenant_id: str,
        doc_id: str | None,
        object_type: str | None,
        object_id: str | None,
        page: int,
        page_size: int,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        key = (str(object_type or ""), str(object_id or ""))
        rows = [dict(item) for item in self.evidence_rows.get(key, [])]
        return len(rows), rows[:page_size]

    async def list_edge_evidence(
        self,
        *,
        tenant_id: str,
        edge_id: str,
        page: int,
        page_size: int,
    ) -> Tuple[int, List[Dict[str, Any]]]:
        return 0, []


def test_graph_file_view_prefers_graphrag_artifacts(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "workspace" / "output" / "latest" / "artifacts"
    _seed_final_artifacts(artifacts_dir)
    graph_file = {
        "graph_file_id": "gf-1",
        "tenant_id": "tenant-a",
        "file_hash": "hash-a",
        "file_name": "doc-a.txt",
        "workspace_id": "ws-a",
        "metadata": {"artifacts_dir": str(artifacts_dir)},
    }
    storage = _FakeStorage(graph_file_row=graph_file)
    helpers = build_query_runtime_helpers()

    result = asyncio.run(
        graph_file_view_response(
            storage=storage,
            helpers=helpers,
            tenant_id="tenant-a",
            file_hash="hash-a",
            node_types=[],
            relation_types=[],
            limit_nodes=500,
            limit_edges=500,
        )
    )

    assert result.source == "graphrag:artifacts:file"
    node_types = {node.node_type for node in result.nodes}
    relation_types = {edge.relation_type for edge in result.edges}
    assert {"Document", "Chunk", "Entity", "Community", "CommunityReport"}.issubset(node_types)
    assert {"has_chunk", "has_entity", "related_to", "in_community", "has_report"}.issubset(relation_types)


def test_list_graph_files_response_overfetches_before_render_filter() -> None:
    graph_file = {
        "graph_file_id": "gf-list-1",
        "tenant_id": "tenant-list",
        "file_hash": "hash-list-0",
        "file_name": "latest.xlsx",
        "workspace_id": "ws-list",
        "status": "ready",
        "metadata": {},
    }
    storage = _FakeStorage(graph_file_row=graph_file)
    storage.graph_files = [
        {
            "graph_file_id": "gf-list-1",
            "tenant_id": "tenant-list",
            "file_hash": "hash-list-1",
            "file_name": "a.xlsx",
            "workspace_id": "ws-list",
            "status": "ready",
            "metadata": {},
        },
        {
            "graph_file_id": "gf-list-2",
            "tenant_id": "tenant-list",
            "file_hash": "hash-list-2",
            "file_name": "b.xlsx",
            "workspace_id": "ws-list",
            "status": "ready",
            "metadata": {},
        },
        {
            "graph_file_id": "gf-list-3",
            "tenant_id": "tenant-list",
            "file_hash": "hash-list-3",
            "file_name": "c.docx",
            "workspace_id": "ws-list",
            "status": "failed",
            "metadata": {},
        },
    ]
    helpers = build_query_runtime_helpers()

    result = asyncio.run(
        list_graph_files_response(
            storage=storage,
            helpers=helpers,
            tenant_id="tenant-list",
            status=None,
            limit=1,
        )
    )

    assert len(result.items) == 1
    assert result.items[0].file_name == "c.docx"
    assert storage.list_graph_files_limits
    assert storage.list_graph_files_limits[-1] > 1


def test_graph_file_view_supports_graphrag_v3_artifact_naming(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "workspace-v3" / "output" / "latest" / "artifacts"
    _seed_v3_final_artifacts(artifacts_dir)
    graph_file = {
        "graph_file_id": "gf-v3",
        "tenant_id": "tenant-v3",
        "file_hash": "hash-v3",
        "file_name": "doc-v3.txt",
        "workspace_id": "ws-v3",
        "metadata": {"artifacts_dir": str(artifacts_dir)},
    }
    storage = _FakeStorage(graph_file_row=graph_file)
    helpers = build_query_runtime_helpers()

    result = asyncio.run(
        graph_file_view_response(
            storage=storage,
            helpers=helpers,
            tenant_id="tenant-v3",
            file_hash="hash-v3",
            node_types=[],
            relation_types=[],
            limit_nodes=500,
            limit_edges=500,
        )
    )

    assert result.source == "graphrag:artifacts:file"
    node_types = {node.node_type for node in result.nodes}
    relation_types = {edge.relation_type for edge in result.edges}
    assert {"Document", "Chunk", "Entity", "Community", "CommunityReport"}.issubset(node_types)
    assert {"has_chunk", "has_entity", "related_to", "in_community", "has_report"}.issubset(relation_types)


def test_graph_file_view_raises_when_artifacts_unavailable(tmp_path: Path) -> None:
    graph_file = {
        "graph_file_id": "gf-2",
        "tenant_id": "tenant-b",
        "file_hash": "hash-b",
        "file_name": "doc-b.txt",
        "workspace_id": "ws-b",
        "metadata": {},
    }
    storage = _FakeStorage(graph_file_row=graph_file)
    helpers = build_query_runtime_helpers()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            graph_file_view_response(
                storage=storage,
                helpers=helpers,
                tenant_id="tenant-b",
                file_hash="hash-b",
                node_types=[],
                relation_types=[],
                limit_nodes=100,
                limit_edges=100,
            )
        )

    assert exc.value.status_code == 409
    assert "GraphRAG artifacts unavailable" in str(exc.value.detail)


def test_graph_file_node_detail_in_artifact_mode_returns_edge_evidence(
    tmp_path: Path,
) -> None:
    artifacts_dir = tmp_path / "workspace" / "output" / "latest" / "artifacts"
    _seed_final_artifacts(artifacts_dir)
    graph_file = {
        "graph_file_id": "gf-3",
        "tenant_id": "tenant-c",
        "file_hash": "hash-c",
        "file_name": "doc-c.txt",
        "workspace_id": "ws-c",
        "metadata": {"artifacts_dir": str(artifacts_dir)},
        "graph_mode": "hybrid",
        "source": "module2",
        "status": "ready",
        "current_job_id": None,
        "active_version_id": "gv-1",
        "last_error": None,
        "node_count": 5,
        "edge_count": 6,
        "created_at": None,
        "updated_at": None,
        "last_indexed_at": None,
    }
    storage = _FakeStorage(graph_file_row=graph_file)
    storage.evidence_rows = {
        ("entity", "ent-1"): [
            {
                "evidence_id": "ev-entity-1",
                "doc_id": "doc-row-1",
                "object_type": "entity",
                "object_id": "ent-1",
                "ref_id": "ent-1",
                "page_no": None,
                "snippet": "Entity evidence",
                "locator": {"source": "test"},
                "bbox": [],
                "artifact_url": None,
                "confidence": 1.0,
                "created_at": None,
            }
        ],
        ("relationship", "rel-1"): [
            {
                "evidence_id": "ev-rel-low",
                "doc_id": "doc-row-1",
                "object_type": "relationship",
                "object_id": "rel-1",
                "ref_id": "rel-1",
                "page_no": None,
                "snippet": "Relationship evidence low",
                "locator": {"source": "test"},
                "bbox": [],
                "artifact_url": None,
                "confidence": 0.3,
                "created_at": None,
            },
            {
                "evidence_id": "ev-rel-high",
                "doc_id": "doc-row-1",
                "object_type": "relationship",
                "object_id": "rel-1",
                "ref_id": "rel-1",
                "page_no": None,
                "snippet": "Relationship evidence high",
                "locator": {"source": "test"},
                "bbox": [],
                "artifact_url": None,
                "confidence": 0.95,
                "created_at": None,
            }
        ],
    }
    helpers = build_query_runtime_helpers()

    result = asyncio.run(
        graph_file_node_detail_response(
            storage=storage,
            helpers=helpers,
            tenant_id="tenant-c",
            file_hash="hash-c",
            node_id="entity::ent-1",
            depth=1,
            relation_types=[],
            limit=120,
        )
    )

    assert result.graph.source == "graphrag:artifacts:file"
    assert len(result.evidence) >= 1
    assert result.edge_evidence
    related_edge = next((edge for edge in result.graph.edges if edge.relation_type == "related_to"), None)
    assert related_edge is not None
    assert related_edge.edge_id in result.edge_evidence
    assert result.edge_evidence[related_edge.edge_id][0].evidence_id == "ev-rel-high"


def test_graph_file_node_detail_community_report_prefers_community_evidence(
    tmp_path: Path,
) -> None:
    artifacts_dir = tmp_path / "workspace-cr" / "output" / "latest" / "artifacts"
    _seed_final_artifacts(artifacts_dir)
    graph_file = {
        "graph_file_id": "gf-4",
        "tenant_id": "tenant-d",
        "file_hash": "hash-d",
        "file_name": "doc-d.txt",
        "workspace_id": "ws-d",
        "metadata": {"artifacts_dir": str(artifacts_dir)},
        "graph_mode": "hybrid",
        "source": "module2",
        "status": "ready",
        "current_job_id": None,
        "active_version_id": "gv-1",
        "last_error": None,
        "node_count": 5,
        "edge_count": 6,
        "created_at": None,
        "updated_at": None,
        "last_indexed_at": None,
    }
    storage = _FakeStorage(graph_file_row=graph_file)
    storage.evidence_rows = {
        ("community", "comm-1"): [
            {
                "evidence_id": "ev-community-1",
                "doc_id": "doc-row-1",
                "object_type": "community",
                "object_id": "comm-1",
                "ref_id": "comm-1",
                "page_no": None,
                "snippet": "Community evidence",
                "locator": {"source": "test"},
                "bbox": [],
                "artifact_url": None,
                "confidence": 0.91,
                "created_at": None,
            }
        ]
    }
    helpers = build_query_runtime_helpers()

    result = asyncio.run(
        graph_file_node_detail_response(
            storage=storage,
            helpers=helpers,
            tenant_id="tenant-d",
            file_hash="hash-d",
            node_id="community_report::report-1",
            depth=1,
            relation_types=[],
            limit=120,
        )
    )

    assert result.graph.source == "graphrag:artifacts:file"
    assert len(result.evidence) >= 1
    assert result.evidence[0].evidence_id == "ev-community-1"


def test_tenant_graph_prefers_artifact_aggregate(tmp_path: Path) -> None:
    artifacts_dir_1 = tmp_path / "workspace-1" / "output" / "latest" / "artifacts"
    artifacts_dir_2 = tmp_path / "workspace-2" / "output" / "latest" / "artifacts"
    _seed_final_artifacts(artifacts_dir_1)
    _seed_final_artifacts(artifacts_dir_2)
    graph_file = {
        "graph_file_id": "gf-tenant-1",
        "tenant_id": "tenant-t",
        "file_hash": "hash-t-1",
        "file_name": "doc-t-1.txt",
        "workspace_id": "ws-t-1",
        "status": "ready",
        "metadata": {"artifacts_dir": str(artifacts_dir_1)},
    }
    storage = _FakeStorage(graph_file_row=graph_file)
    storage.graph_files.append(
        {
            "graph_file_id": "gf-tenant-2",
            "tenant_id": "tenant-t",
            "file_hash": "hash-t-2",
            "file_name": "doc-t-2.txt",
            "workspace_id": "ws-t-2",
            "status": "ready",
            "metadata": {"artifacts_dir": str(artifacts_dir_2)},
        }
    )
    helpers = build_query_runtime_helpers()

    result = asyncio.run(
        graph_response(
            storage=storage,
            helpers=helpers,
            tenant_id="tenant-t",
            node_types=[],
            relation_types=[],
            limit_nodes=1200,
            limit_edges=2400,
        )
    )

    assert result.source == "graphrag:artifacts:tenant"
    assert len(result.nodes) >= 10
    assert len(result.edges) >= 10


def test_tenant_neighborhood_uses_artifact_aggregate(tmp_path: Path) -> None:
    artifacts_dir = tmp_path / "workspace-n" / "output" / "latest" / "artifacts"
    _seed_final_artifacts(artifacts_dir)
    graph_file = {
        "graph_file_id": "gf-nei-1",
        "tenant_id": "tenant-nei",
        "file_hash": "hash-nei-1",
        "file_name": "doc-nei-1.txt",
        "workspace_id": "ws-nei-1",
        "status": "ready",
        "metadata": {"artifacts_dir": str(artifacts_dir)},
    }
    storage = _FakeStorage(graph_file_row=graph_file)
    helpers = build_query_runtime_helpers()

    full_graph = asyncio.run(
        graph_response(
            storage=storage,
            helpers=helpers,
            tenant_id="tenant-nei",
            node_types=[],
            relation_types=[],
            limit_nodes=500,
            limit_edges=1000,
        )
    )
    target = next((item for item in full_graph.nodes if item.node_type == "Entity"), None)
    assert target is not None

    nei = asyncio.run(
        neighborhood_response(
            storage=storage,
            helpers=helpers,
            tenant_id="tenant-nei",
            node_id=target.node_id,
            depth=1,
            relation_types=[],
            limit=200,
        )
    )

    assert nei.source == "graphrag:artifacts:tenant"
    assert any(item.node_id == target.node_id for item in nei.nodes)


def test_tenant_graph_returns_empty_when_artifacts_unavailable(tmp_path: Path) -> None:
    graph_file = {
        "graph_file_id": "gf-empty-1",
        "tenant_id": "tenant-empty",
        "file_hash": "hash-empty-1",
        "file_name": "doc-empty-1.txt",
        "workspace_id": "ws-empty-1",
        "status": "ready",
        "metadata": {},
    }
    storage = _FakeStorage(graph_file_row=graph_file)
    helpers = build_query_runtime_helpers()

    result = asyncio.run(
        graph_response(
            storage=storage,
            helpers=helpers,
            tenant_id="tenant-empty",
            node_types=[],
            relation_types=[],
            limit_nodes=500,
            limit_edges=1000,
        )
    )

    assert result.source == "graphrag:artifacts:tenant"
    assert result.nodes == []
    assert result.edges == []


def test_tenant_neighborhood_raises_not_found_when_artifacts_unavailable(tmp_path: Path) -> None:
    graph_file = {
        "graph_file_id": "gf-empty-nei-1",
        "tenant_id": "tenant-empty-nei",
        "file_hash": "hash-empty-nei-1",
        "file_name": "doc-empty-nei-1.txt",
        "workspace_id": "ws-empty-nei-1",
        "status": "ready",
        "metadata": {},
    }
    storage = _FakeStorage(graph_file_row=graph_file)
    helpers = build_query_runtime_helpers()

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            neighborhood_response(
                storage=storage,
                helpers=helpers,
                tenant_id="tenant-empty-nei",
                node_id="entity::ent-1",
                depth=1,
                relation_types=[],
                limit=200,
            )
        )

    assert exc.value.status_code == 404
    assert "tenant artifact graph" in str(exc.value.detail)
