from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.services.graphrag import query_adapter, query_service


def test_canonicalize_linked_node_ids_resolves_to_canonical_node_ids(monkeypatch: Any) -> None:
    snapshot = query_adapter.GraphRAGArtifactGraph(
        nodes=[
            {
                "node_id": "entity::e-001",
                "canonical_key": "entity::e-001",
                "display_name": "台风路径",
                "attrs": {
                    "graphrag_id": "1",
                    "name": "台风路径",
                },
            },
            {
                "node_id": "community::c-001",
                "canonical_key": "community::c-001",
                "display_name": "气象主题社区",
                "attrs": {
                    "graphrag_id": "88",
                    "community_id": "88",
                },
            },
            {
                "node_id": "community_report::r-001",
                "canonical_key": "community_report::r-001",
                "display_name": "社区报告",
                "attrs": {
                    "report_id": "report-human-id",
                    "graphrag_id": "88",
                },
            },
            {
                "node_id": "chunk::t-001",
                "canonical_key": "chunk::t-001",
                "display_name": "片段",
                "attrs": {
                    "graphrag_id": "42",
                },
            },
            {
                "node_id": "doc::d-001",
                "canonical_key": "document::d-001",
                "display_name": "文档",
                "attrs": {
                    "graphrag_id": "doc-7",
                    "human_readable_id": "文档-7",
                },
            },
        ],
        edges=[],
        workspace_id="ws-1",
    )
    monkeypatch.setattr(query_service, "load_artifact_graph_snapshot", lambda graph_file: snapshot)

    linked = query_service._canonicalize_linked_node_ids(
        candidates=[
            "entity::1",
            "community::88",
            "community_report::report-human-id",
            "chunk::42",
            "doc::doc-7",
            "entity::missing-alias",
        ],
        graph_file={"file_hash": "hash-1"},
    )

    assert linked == [
        "entity::e-001",
        "community::c-001",
        "community_report::r-001",
        "chunk::t-001",
        "doc::d-001",
    ]


def test_canonicalize_linked_node_ids_falls_back_when_snapshot_unavailable(monkeypatch: Any) -> None:
    monkeypatch.setattr(query_service, "load_artifact_graph_snapshot", lambda graph_file: None)

    linked = query_service._canonicalize_linked_node_ids(
        candidates=["entity::1", "entity::1", "community::2", "", "  "],
        graph_file={"file_hash": "hash-1"},
    )

    assert linked == ["entity::1", "community::2"]


def test_canonicalize_linked_node_ids_uses_storage_fallback_when_snapshot_missing(monkeypatch: Any) -> None:
    monkeypatch.setattr(query_service, "load_artifact_graph_snapshot", lambda graph_file: None)

    class _Storage:
        async def list_nodes_by_graph_file(
            self,
            *,
            tenant_id: str,
            graph_file_id: str,
            node_types: list[str],
            limit: int,
        ) -> list[dict[str, object]]:
            assert tenant_id == "tenant-demo"
            assert graph_file_id == "graph-file-1"
            assert isinstance(node_types, list)
            assert limit >= 1000
            return [
                {
                    "node_id": "entity::entity-real-1",
                    "canonical_key": "entity::entity-real-1",
                    "display_name": "实体节点",
                    "attrs": {"graphrag_id": "1"},
                }
            ]

    linked = asyncio.run(
        query_service._canonicalize_linked_node_ids_with_storage(
            candidates=["entity::1"],
            graph_file={"graph_file_id": "graph-file-1"},
            storage=_Storage(),
            tenant_id="tenant-demo",
        )
    )

    assert linked == ["entity::entity-real-1"]


def test_canonicalize_linked_node_ids_storage_first_over_artifact(monkeypatch: Any) -> None:
    snapshot = query_adapter.GraphRAGArtifactGraph(
        nodes=[
            {
                "node_id": "entity::artifact-1",
                "canonical_key": "entity::artifact-1",
                "display_name": "台风路径(旧)",
                "attrs": {"graphrag_id": "1"},
            }
        ],
        edges=[],
        workspace_id="ws-artifact",
    )
    monkeypatch.setattr(query_service, "load_artifact_graph_snapshot", lambda graph_file: snapshot)

    class _Storage:
        async def list_nodes_by_graph_file(
            self,
            *,
            tenant_id: str,
            graph_file_id: str,
            node_types: list[str],
            limit: int,
        ) -> list[dict[str, object]]:
            assert tenant_id == "tenant-demo"
            assert graph_file_id == "graph-file-1"
            assert isinstance(node_types, list)
            assert limit >= 1000
            return [
                {
                    "node_id": "entity::storage-1",
                    "canonical_key": "entity::storage-1",
                    "display_name": "台风路径",
                    "attrs": {"graphrag_id": "1"},
                }
            ]

    linked, diagnostics = asyncio.run(
        query_service._canonicalize_linked_node_ids_with_storage_diagnostics(
            candidates=["entity::1"],
            graph_file={"graph_file_id": "graph-file-1", "file_hash": "hash-1"},
            storage=_Storage(),
            tenant_id="tenant-demo",
        )
    )

    assert linked == ["entity::storage-1"]
    assert diagnostics["resolved_count"] == 1
    assert diagnostics["unresolved_count"] == 0
    assert diagnostics["resolution_strategy"] == "storage_first_then_artifact"
    assert diagnostics["resolution_source_counts"] == {"storage": 1, "artifact": 0}
    assert diagnostics["used_fallback_candidates"] is False


def test_canonicalize_linked_node_ids_diagnostics_reports_unresolved(monkeypatch: Any) -> None:
    snapshot = query_adapter.GraphRAGArtifactGraph(
        nodes=[
            {
                "node_id": "entity::artifact-1",
                "canonical_key": "entity::artifact-1",
                "display_name": "台风路径",
                "attrs": {"graphrag_id": "1"},
            }
        ],
        edges=[],
        workspace_id="ws-artifact",
    )
    monkeypatch.setattr(query_service, "load_artifact_graph_snapshot", lambda graph_file: snapshot)

    class _Storage:
        async def list_nodes_by_graph_file(
            self,
            *,
            tenant_id: str,
            graph_file_id: str,
            node_types: list[str],
            limit: int,
        ) -> list[dict[str, object]]:
            return []

    linked, diagnostics = asyncio.run(
        query_service._canonicalize_linked_node_ids_with_storage_diagnostics(
            candidates=["entity::1", "entity::missing"],
            graph_file={"graph_file_id": "graph-file-1", "file_hash": "hash-1"},
            storage=_Storage(),
            tenant_id="tenant-demo",
        )
    )

    assert linked == ["entity::artifact-1"]
    assert diagnostics["candidate_count"] == 2
    assert diagnostics["resolved_count"] == 1
    assert diagnostics["unresolved_count"] == 1
    assert diagnostics["unresolved_candidates"] == ["entity::missing"]
    assert diagnostics["resolution_strategy"] == "artifact_only"
    assert diagnostics["resolution_source_counts"] == {"storage": 0, "artifact": 1}
    assert diagnostics["used_fallback_candidates"] is False


def test_canonicalize_linked_node_ids_diagnostics_identity_fallback_when_no_aliases(monkeypatch: Any) -> None:
    monkeypatch.setattr(query_service, "load_artifact_graph_snapshot", lambda graph_file: None)

    class _Storage:
        async def list_nodes_by_graph_file(
            self,
            *,
            tenant_id: str,
            graph_file_id: str,
            node_types: list[str],
            limit: int,
        ) -> list[dict[str, object]]:
            return []

    linked, diagnostics = asyncio.run(
        query_service._canonicalize_linked_node_ids_with_storage_diagnostics(
            candidates=["entity::1", "community::2", "entity::1"],
            graph_file={"graph_file_id": "graph-file-1", "file_hash": "hash-1"},
            storage=_Storage(),
            tenant_id="tenant-demo",
        )
    )

    assert linked == ["entity::1", "community::2"]
    assert diagnostics["candidate_count"] == 2
    assert diagnostics["resolved_count"] == 0
    assert diagnostics["unresolved_count"] == 2
    assert diagnostics["unresolved_candidates"] == ["entity::1", "community::2"]
    assert diagnostics["resolution_strategy"] == "identity_fallback"
    assert diagnostics["resolution_source_counts"] == {"storage": 0, "artifact": 0}
    assert diagnostics["used_fallback_candidates"] is True
