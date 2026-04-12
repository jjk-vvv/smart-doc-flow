from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

from app.services.query.neo4j import Neo4jGraphProjector, Neo4jSettings


def test_neo4j_projector_projects_graph_payload_when_configured(monkeypatch) -> None:
    queries: list[tuple[str, dict]] = []

    class FakeResult:
        def consume(self) -> None:
            return None

    class FakeTx:
        def run(self, query: str, **params: object) -> FakeResult:
            queries.append((query, params))
            return FakeResult()

    class FakeSession:
        def __enter__(self) -> "FakeSession":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def execute_write(self, fn, **kwargs):
            return fn(FakeTx(), **kwargs)

    class FakeDriver:
        def session(self, database: str) -> FakeSession:
            assert database == "neo4j"
            return FakeSession()

        def close(self) -> None:
            return None

    class FakeGraphDatabase:
        @staticmethod
        def driver(uri: str, auth: tuple[str, str], **config: object) -> FakeDriver:
            assert uri == "neo4j+s://example.databases.neo4j.io:7687"
            assert auth == ("neo4j", "secret")
            assert config["max_connection_pool_size"] == 2
            assert config["connection_timeout"] == 2.0
            assert config["connection_acquisition_timeout"] == 2.0
            assert config["max_transaction_retry_time"] == 0.0
            return FakeDriver()

    monkeypatch.setenv("MODULE4_NEO4J_PROJECT_ON_READY", "1")
    monkeypatch.setitem(sys.modules, "neo4j", SimpleNamespace(GraphDatabase=FakeGraphDatabase))

    projector = Neo4jGraphProjector(
        Neo4jSettings(
            uri="neo4j+s://example.databases.neo4j.io:7687",
            username="neo4j",
            password="secret",
            database="neo4j",
        )
    )

    result = projector.project(
        tenant_id="tenant-1",
        file_hash="hash-1",
        graph_file_id="graph-file-1",
        graph_version_id="graph-version-1",
        workspace_id="workspace-1",
        nodes=[
            {
                "node_id": "node-1",
                "node_type": "Document",
                "canonical_key": "doc-1",
                "display_name": "Doc 1",
                "confidence": 1.0,
                "attrs": {"workspace_id": "workspace-1"},
                "updated_at": "2026-03-17T00:00:00Z",
            }
        ],
        edges=[
            {
                "edge_id": "edge-1",
                "source_node_id": "node-1",
                "target_node_id": "node-1",
                "relation_type": "SELF",
                "direction": "out",
                "confidence": 1.0,
                "risk_score": 0.0,
                "attrs": {"kind": "test"},
                "updated_at": "2026-03-17T00:00:00Z",
            }
        ],
        source_node_count=1,
        source_edge_count=1,
    )

    assert result.status == "success"
    assert result.projected_nodes == 1
    assert result.projected_edges == 1
    assert len(queries) == 3
