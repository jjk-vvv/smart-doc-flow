from __future__ import annotations

import asyncio
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))

import app.composition.application as module4_main  # noqa: E402
from app.composition.application import app  # noqa: E402
from app.db.storage import Module4Storage  # noqa: E402
from app.schemas import IngestRequest  # noqa: E402
from app.services.graphrag.indexer import GraphRAGDependencyProbe, GraphRAGRuntimeProbe  # noqa: E402
from app.services.graphrag.prompts import PromptRegistry  # noqa: E402
from app.services.graphrag.settings import GraphRAGRuntimeSettings  # noqa: E402
from app.services.graphrag.workspace import GraphRAGWorkspaceBuilder  # noqa: E402
from app.services.query.neo4j import Neo4jSettings  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_strict_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = Module4Storage("postgresql://invalid")

    async def _connect() -> None:
        await storage.ensure_default_rules()

    async def _close() -> None:
        return None

    monkeypatch.setattr(storage, "connect", _connect)
    monkeypatch.setattr(storage, "close", _close)
    module4_main._set_runtime_ref("storage", storage)
    module4_main._get_runtime_ref("job_tasks").clear()


def _wait_job_success(client: TestClient, job_id: str, tenant_id: str, timeout_s: float = 6.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"/module4/jobs/{job_id}?tenant_id={tenant_id}")
        assert resp.status_code == 200
        row = resp.json()
        if row["status"] in {"success", "failed", "cancelled"}:
            return row
        time.sleep(0.05)
    raise AssertionError("job timeout")


def test_storage_schema_uses_file_scoped_unique_indexes() -> None:
    sql_text = (MODULE4_DIR / "sql" / "init.sql").read_text(encoding="utf-8")

    assert "UNIQUE (tenant_id, node_type, canonical_key)" not in sql_text
    assert "UNIQUE (tenant_id, source_node_id, target_node_id, relation_type)" not in sql_text
    assert "DROP CONSTRAINT IF EXISTS nodes_tenant_id_node_type_canonical_key_key" in sql_text
    assert "DROP CONSTRAINT IF EXISTS edges_tenant_id_source_node_id_target_node_id_relation_type_key" in sql_text
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_m4_nodes_legacy_scope" in sql_text
    assert "WHERE graph_file_id IS NULL" in sql_text
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_m4_nodes_graph_file_scope" in sql_text
    assert "WHERE graph_file_id IS NOT NULL" in sql_text
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_m4_edges_legacy_scope" in sql_text
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_m4_edges_graph_file_scope" in sql_text


def test_module4_package_can_be_imported_from_backend_root() -> None:
    backend_root = str(MODULE4_DIR.parent)
    script = "\n".join(
        [
            "import sys",
            f"sys.path.insert(0, {backend_root!r})",
            "import module4.app.main as module4_main",
            "assert hasattr(module4_main, 'app')",
            "assert hasattr(module4_main, 'create_app')",
            "print('ok')",
        ]
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    assert "ok" in result.stdout


def test_partial_unique_indexes_have_matching_conflict_predicates() -> None:
    storage_text = (MODULE4_DIR / "app" / "db" / "storage.py").read_text(encoding="utf-8")

    assert "ON CONFLICT (tenant_id, evidence_key) WHERE evidence_key IS NOT NULL" in storage_text
    assert "ON CONFLICT (tenant_id, alert_key) WHERE alert_key IS NOT NULL" in storage_text


def test_default_rules_include_business_semantic_alert_ids() -> None:
    async def scenario() -> set[str]:
        await module4_main._get_runtime_ref("storage").ensure_default_rules()
        rows = await module4_main._get_runtime_ref("storage").list_rules()
        return {str(item.get("rule_id") or "") for item in rows}

    rule_ids = asyncio.run(scenario())

    assert "BUSINESS_ALERT_PRIMARY_SIGNAL" in rule_ids
    assert "BUSINESS_ALERT_DISPARITY" in rule_ids


def test_ingest_graph_alert_and_evidence_flow() -> None:
    tenant_id = f"test-{uuid.uuid4().hex[:10]}"
    payload = {
        "tenant_id": tenant_id,
        "source": "module2",
        "documents": [
            {
                "file_name": "sample_contract.pdf",
                "file_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "track": "alpha",
                "result": {
                    "amount": {"value": "10000", "confidence": 0.42, "source_ref_id": "r1"},
                    "buyer": {"value": "Acme Ltd.", "confidence": 0.92, "source_ref_id": "r2"},
                },
                "errors": ["table parse mismatch"],
                "soft_warnings": ["ambiguous date format"],
                "diagnostics": {"quality_status": "degraded"},
                "trace_hits": [
                    {
                        "object_type": "table",
                        "object_id": "table-1",
                        "page": 1,
                        "snippet": "amount due table",
                        "confidence": 0.88,
                    }
                ],
            }
        ],
    }

    with TestClient(app) as client:
        ingest_resp = client.post("/module4/ingest", json=payload)
        assert ingest_resp.status_code == 200, ingest_resp.text
        job_id = ingest_resp.json()["job_id"]

        final_job = _wait_job_success(client, job_id, tenant_id)
        assert final_job["status"] == "success", final_job

        graph_resp = client.get(f"/module4/graph?tenant_id={tenant_id}&limit_nodes=500&limit_edges=1000")
        assert graph_resp.status_code == 200
        graph = graph_resp.json()
        assert len(graph["nodes"]) >= 4
        assert len(graph["edges"]) >= 3

        alerts_resp = client.get(f"/module4/alerts?tenant_id={tenant_id}&page=1&page_size=50")
        assert alerts_resp.status_code == 200
        alerts = alerts_resp.json()
        assert alerts["total"] >= 0

        evidence_resp = client.get(f"/module4/evidence?tenant_id={tenant_id}&page=1&page_size=50")
        assert evidence_resp.status_code == 200
        evidence = evidence_resp.json()
        assert evidence["total"] >= 1


def test_ingest_rejects_non_graph_file_suffix_xlsx() -> None:
    tenant_id = f"test-{uuid.uuid4().hex[:10]}"
    payload = {
        "tenant_id": tenant_id,
        "source": "module2",
        "documents": [
            {
                "file_name": "sales.xlsx",
                "file_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "track": "module2",
                "result": {"table": {"value": "row-1"}},
            }
        ],
    }

    with TestClient(app) as client:
        ingest_resp = client.post("/module4/ingest", json=payload)
        assert ingest_resp.status_code == 400, ingest_resp.text
        detail = str(ingest_resp.json().get("detail") or "")
        assert "No graph-eligible documents found" in detail
        assert ".docx" in detail and ".pdf" in detail and ".txt" in detail and ".md" in detail


def test_graph_file_list_filters_out_xlsx_rows() -> None:
    tenant_id = f"test-{uuid.uuid4().hex[:10]}"
    storage = module4_main._get_runtime_ref("storage")

    async def _seed() -> None:
        await storage.upsert_graph_file(
            tenant_id=tenant_id,
            file_hash=f"hash-xlsx-{uuid.uuid4().hex[:8]}",
            file_name="table.xlsx",
            workspace_id="ws-xlsx",
            graph_mode="hybrid",
            source="module2",
            status="ready",
            metadata={"stage": "ready"},
            node_count=10,
            edge_count=20,
        )
        await storage.upsert_graph_file(
            tenant_id=tenant_id,
            file_hash=f"hash-md-{uuid.uuid4().hex[:8]}",
            file_name="notes.md",
            workspace_id="ws-md",
            graph_mode="hybrid",
            source="module2",
            status="ready",
            metadata={"stage": "ready"},
            node_count=5,
            edge_count=7,
        )

    asyncio.run(_seed())

    with TestClient(app) as client:
        resp = client.get(f"/module4/graph/files?tenant_id={tenant_id}&limit=50")
        assert resp.status_code == 200, resp.text
        items = resp.json().get("items") or []
        names = {str(item.get("file_name") or "") for item in items}
        assert "table.xlsx" not in names
        assert "notes.md" in names


def test_ingest_graphrag_native_graph_shapes(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = f"test-{uuid.uuid4().hex[:10]}"
    payload = {
        "tenant_id": tenant_id,
        "source": "module2",
        "documents": [
                {
                    "file_name": "native_graphrag.txt",
                    "file_hash": f"hash-{uuid.uuid4().hex[:8]}",
                    "track": "graphrag-native",
                    "result": {
                        "party_a": {"value": "Acme", "confidence": 0.91},
                        "party_b": {"value": "Contoso", "confidence": 0.93},
                        "location": {"value": "Beijing", "confidence": 0.88},
                        "contract_type": {"value": "SupplyContract", "confidence": 0.9},
                    },
                    "trace_hits": [
                        {
                            "object_type": "field",
                            "object_id": "summary",
                            "snippet": "Acme and Contoso signed a SupplyContract in Beijing.",
                            "confidence": 0.95,
                        }
                    ],
                    "diagnostics": {"quality_status": "ok"},
                }
            ],
        }

    with TestClient(app) as client:
        ingest_resp = client.post("/module4/ingest", json=payload)
        assert ingest_resp.status_code == 200, ingest_resp.text
        _wait_job_success(client, ingest_resp.json()["job_id"], tenant_id)

        graph_resp = client.get(f"/module4/graph?tenant_id={tenant_id}&limit_nodes=500&limit_edges=1000")
        assert graph_resp.status_code == 200, graph_resp.text
        graph = graph_resp.json()

        node_types = {str(node.get("node_type") or "") for node in graph["nodes"]}
        relation_types = {str(edge.get("relation_type") or "") for edge in graph["edges"]}
        assert {"Document", "Chunk", "Entity", "Community", "CommunityReport"}.issubset(node_types)
        assert {"has_chunk", "has_entity", "related_to", "in_community", "has_report"}.issubset(relation_types)

        related_edges = [edge for edge in graph["edges"] if str(edge.get("relation_type") or "") == "related_to"]
        assert related_edges, "expected at least one related_to edge"
        assert all("weight" in (edge.get("attrs") or {}) for edge in related_edges)


def test_query_search_api_uses_graphrag_query_service(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_query_service(**kwargs: object) -> dict[str, object]:
        assert kwargs["tenant_id"] == "tenant-query"
        assert kwargs["file_hash"] == "file-hash-001"
        assert kwargs["mode"] == "local"
        return {
            "answer": "基于当前 GraphRAG 工作区的检索结果。",
            "mode": "local",
            "query": "杭州空气质量有哪些关键结论？",
            "response_type": "multiple paragraphs",
            "community_level": 2,
            "dynamic_community_selection": False,
            "file_hash": "file-hash-001",
            "graph_file_id": "graph-file-001",
            "active_version_id": "version-001",
            "workspace_id": "workspace-001",
            "context_data": {
                "reports": [{"id": "7", "community": "2"}],
                "entities": [{"id": "19", "name": "杭州"}],
                "relationships": [],
                "claims": [],
                "sources": [{"id": "42"}],
            },
            "linked_node_ids": ["entity::19", "community_report::7", "community::2", "chunk::42"],
            "linked_node_resolution": {
                "candidate_count": 4,
                "resolved_count": 4,
                "unresolved_count": 0,
                "resolution_strategy": "storage_first_then_artifact",
                "used_fallback_candidates": False,
            },
            "source": "graphrag:query:local",
        }

    monkeypatch.setattr("app.api.v1.endpoints.module4.graphrag_query_response_service", _fake_query_service)

    with TestClient(app) as client:
        resp = client.post(
            "/module4/query/search",
            json={
                "tenant_id": "tenant-query",
                "file_hash": "file-hash-001",
                "query": "杭州空气质量有哪些关键结论？",
                "mode": "local",
                "response_type": "multiple paragraphs",
                "community_level": 2,
            },
        )
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert payload["answer"] == "基于当前 GraphRAG 工作区的检索结果。"
        assert payload["workspace_id"] == "workspace-001"
        assert payload["linked_node_ids"] == ["entity::19", "community_report::7", "community::2", "chunk::42"]
        assert payload["linked_node_resolution"]["resolved_count"] == 4
        assert payload["context_data"]["entities"][0]["id"] == "19"


def test_repeated_ingest_is_idempotent_for_same_payload() -> None:
    tenant_id = f"test-{uuid.uuid4().hex[:10]}"
    payload = {
        "tenant_id": tenant_id,
        "source": "module2",
        "documents": [
            {
                "file_name": "sample_contract.pdf",
                "file_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "track": "beta",
                "result": {
                    "amount": {"value": "10000", "confidence": 0.42, "source_ref_id": "r1"},
                    "buyer": {"value": "Acme Ltd.", "confidence": 0.92, "source_ref_id": "r2"},
                },
                "errors": ["table parse mismatch"],
                "soft_warnings": ["ambiguous date format"],
                "diagnostics": {"quality_status": "degraded"},
                "trace_hits": [
                    {
                        "object_type": "table",
                        "object_id": "table-1",
                        "page": 1,
                        "snippet": "amount due table",
                        "confidence": 0.88,
                    }
                ],
            }
        ],
    }

    with TestClient(app) as client:
        first = client.post("/module4/ingest", json=payload)
        assert first.status_code == 200, first.text
        first_job = _wait_job_success(client, first.json()["job_id"], tenant_id)
        assert first_job["status"] == "success"

        alerts_before = client.get(f"/module4/alerts?tenant_id={tenant_id}&page=1&page_size=50").json()
        evidence_before = client.get(f"/module4/evidence?tenant_id={tenant_id}&page=1&page_size=50").json()

        second = client.post("/module4/ingest", json=payload)
        assert second.status_code == 200, second.text
        second_payload = second.json()
        assert second_payload["job_id"] == first.json()["job_id"]
        assert second_payload["batch_id"] == first.json()["batch_id"]
        assert second_payload["status"] == "success"

        alerts_after = client.get(f"/module4/alerts?tenant_id={tenant_id}&page=1&page_size=50").json()
        evidence_after = client.get(f"/module4/evidence?tenant_id={tenant_id}&page=1&page_size=50").json()
        assert alerts_after["total"] == alerts_before["total"]
        assert evidence_after["total"] == evidence_before["total"]


def test_reingest_replaces_file_scoped_graph_rows_instead_of_mixing_versions() -> None:
    tenant_id = f"test-{uuid.uuid4().hex[:10]}"
    file_hash = f"hash-{uuid.uuid4().hex[:8]}"
    payload = IngestRequest(
        tenant_id=tenant_id,
        source="module2",
        source_batch_key=f"batch-{uuid.uuid4().hex[:8]}",
        documents=[
            {
                "file_name": "mixed_scope.pdf",
                "file_hash": file_hash,
                "track": "replace-a",
                "result": {
                    "amount": {"value": "12000", "confidence": 0.41, "source_ref_id": "r1"},
                    "buyer": {"value": "Acme", "confidence": 0.92, "source_ref_id": "r2"},
                },
                "errors": ["parse mismatch"],
                "trace_hits": [
                    {
                        "object_type": "table",
                        "object_id": "table-1",
                        "page": 2,
                        "snippet": "first table",
                        "confidence": 0.81,
                    }
                ],
            }
        ],
    )

    asyncio.run(module4_main._run_document_ingest_job("job-a", "batch-a", payload))
    graph_file = asyncio.run(module4_main._get_runtime_ref("storage").get_graph_file(tenant_id=tenant_id, file_hash=file_hash))
    assert graph_file is not None
    graph_file_id = str(graph_file["graph_file_id"])

    polluted_node = asyncio.run(
        module4_main._get_runtime_ref("storage").upsert_node(
            tenant_id=tenant_id,
            graph_file_id=graph_file_id,
            graph_version_id="stale-version",
            node_type="Entity",
            canonical_key=f"{file_hash}:entity:legacy",
            display_name="legacy entity",
            attrs={"file_hash": file_hash, "workspace_id": "legacy-workspace"},
            confidence=0.93,
        )
    )
    document_node = next(
        row
        for row in module4_main._get_runtime_ref("storage")._nodes_by_id.values()
        if str(row.get("tenant_id") or "") == tenant_id
        and str(row.get("graph_file_id") or "") == graph_file_id
        and str(row.get("node_type") or "") == "Document"
    )
    asyncio.run(
        module4_main._get_runtime_ref("storage").upsert_edge(
            tenant_id=tenant_id,
            graph_file_id=graph_file_id,
            graph_version_id="stale-version",
            source_node_id=str(document_node["node_id"]),
            target_node_id=str(polluted_node["node_id"]),
            relation_type="mentions",
            direction="out",
            attrs={"file_hash": file_hash},
            confidence=0.77,
            risk_score=0.0,
        )
    )
    asyncio.run(
        module4_main._get_runtime_ref("storage").insert_alert(
            tenant_id=tenant_id,
            rule_id="RULE_DOC_ERRORS",
            severity="orange",
            subject_node_id=str(polluted_node["node_id"]),
            title="legacy polluted alert",
            summary="legacy polluted alert",
            risk_score=88.0,
            payload={"context": {"file_hash": file_hash}},
        )
    )

    rerun_payload = payload.model_copy(update={"source_batch_key": f"batch-{uuid.uuid4().hex[:8]}"})
    asyncio.run(module4_main._run_document_ingest_job("job-b", "batch-b", rerun_payload))

    graph_file_after = asyncio.run(module4_main._get_runtime_ref("storage").get_graph_file(tenant_id=tenant_id, file_hash=file_hash))
    assert graph_file_after is not None
    active_version_id = str(graph_file_after.get("active_version_id") or "")
    graph_file_id_after = str(graph_file_after.get("graph_file_id") or "")

    file_nodes = [
        dict(row)
        for row in module4_main._get_runtime_ref("storage")._nodes_by_id.values()
        if str(row.get("tenant_id") or "") == tenant_id
        and str(row.get("graph_file_id") or "") == graph_file_id_after
        and str(row.get("graph_version_id") or "") == active_version_id
    ]
    file_edges = [
        dict(row)
        for row in module4_main._get_runtime_ref("storage")._edges_by_id.values()
        if str(row.get("tenant_id") or "") == tenant_id
        and str(row.get("graph_file_id") or "") == graph_file_id_after
        and str(row.get("graph_version_id") or "") == active_version_id
    ]
    node_types = {str(row.get("node_type") or "") for row in file_nodes}
    assert {"Document", "Entity"}.issubset(node_types)
    assert all(str(row.get("relation_type") or "") != "mentions" for row in file_edges)

    _total_alerts, alerts = asyncio.run(
        module4_main._get_runtime_ref("storage").list_alerts(
            tenant_id=tenant_id,
            status=None,
            severity=None,
            rule_id=None,
            page=1,
            page_size=50,
        )
    )
    assert all(str(item.get("title") or "") != "legacy polluted alert" for item in alerts)

    assert int(graph_file_after["node_count"]) >= len(file_nodes)
    assert int(graph_file_after["edge_count"]) >= len(file_edges)
    assert len(module4_main._get_runtime_ref("storage")._graph_versions) == 1

def test_legacy_upload_sync_endpoint_is_not_available() -> None:
    payload = {
        "tenant_id": "default",
        "source": "module2",
        "uploads": [
            {
                "file_name": "legacy.txt",
                "file_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "mime_type": "text/plain",
                "text_content": "legacy upload path",
            }
        ],
    }

    with TestClient(app) as client:
        resp = client.post("/module4/sync/uploads", json=payload)
        assert resp.status_code == 404


def test_ingest_api_rejects_uploads_only_payload() -> None:
    payload = {
        "tenant_id": "default",
        "source": "module2",
        "uploads": [
            {
                "file_name": "legacy.txt",
                "file_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "mime_type": "text/plain",
                "text_content": "legacy upload path",
            }
        ],
    }

    with TestClient(app) as client:
        resp = client.post("/module4/ingest", json=payload)
        assert resp.status_code == 422, resp.text
        assert "At least one document is required" in resp.text


def test_neighborhood_returns_exact_node_context() -> None:
    tenant_id = f"test-{uuid.uuid4().hex[:10]}"
    payload = {
        "tenant_id": tenant_id,
        "source": "module2",
        "documents": [
            {
                "file_name": "graph_doc.pdf",
                "file_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "track": "gamma",
                "result": {
                    "seller": {"value": "Contoso", "confidence": 0.91, "source_ref_id": "r1"},
                    "amount": {"value": "12000", "confidence": 0.48, "source_ref_id": "r2"},
                },
                "trace_hits": [
                    {
                        "object_type": "table",
                        "object_id": "pricing-table",
                        "page": 2,
                        "snippet": "pricing table",
                        "confidence": 0.77,
                    }
                ],
            }
        ],
    }

    with TestClient(app) as client:
        ingest_resp = client.post("/module4/ingest", json=payload)
        assert ingest_resp.status_code == 200, ingest_resp.text
        _wait_job_success(client, ingest_resp.json()["job_id"], tenant_id)

        graph_resp = client.get(f"/module4/graph?tenant_id={tenant_id}&limit_nodes=200&limit_edges=300")
        assert graph_resp.status_code == 200
        graph = graph_resp.json()
        entity_node = next((node for node in graph["nodes"] if node["node_type"] == "Entity"), None)
        assert entity_node is not None

        neighborhood_resp = client.get(
            f"/module4/graph/neighborhood/{entity_node['node_id']}?tenant_id={tenant_id}&depth=2&limit=40"
        )
        assert neighborhood_resp.status_code == 200, neighborhood_resp.text
        neighborhood = neighborhood_resp.json()
        node_ids = {node["node_id"] for node in neighborhood["nodes"]}
        assert entity_node["node_id"] in node_ids
        assert len(neighborhood["edges"]) >= 1


def test_file_graph_artifact_nodes_preserve_rich_trace_metadata_and_detail_evidence() -> None:
    tenant_id = f"test-{uuid.uuid4().hex[:10]}"
    file_hash = f"hash-{uuid.uuid4().hex[:8]}"
    payload = {
        "tenant_id": tenant_id,
        "source": "module2",
        "documents": [
            {
                "file_name": "rich_artifacts.pdf",
                "file_hash": file_hash,
                "track": "epsilon",
                "result": {
                    "amount": {"value": "12000", "confidence": 0.91, "source_ref_id": "r1"},
                },
                "diagnostics": {
                    "quality_status": "ok",
                    "polymorphic_links": [
                        {
                            "field": "amount",
                            "targets": [
                                {
                                    "type": "table",
                                    "id": "table-1",
                                    "page": 3,
                                    "match": "年度金额汇总",
                                    "confidence": 0.89,
                                },
                                {
                                    "type": "figure",
                                    "id": "figure-1",
                                    "page": 4,
                                    "match": "年度走势",
                                    "confidence": 0.84,
                                },
                            ],
                        }
                    ],
                },
                "trace_hits": [
                    {
                        "object_type": "table",
                        "object_id": "table-1",
                        "page": 3,
                        "snippet": "表格 table-1（pdf_mineru，3x3） 标题：年度 | 金额 | 占比",
                        "confidence": 0.93,
                        "artifact_url": "/extract/artifact/module2/tables/table-1.png",
                        "locator": {
                            "page": 3,
                            "ref_id": "pdf_table_t1",
                            "table_preview": {
                                "headers": ["年度", "金额", "占比"],
                                "rows": [["2019", "80", "24%"], ["2020", "95", "29%"]],
                                "row_count": 3,
                                "col_count": 3,
                            },
                            "dataframe": {
                                "headers": ["年度", "金额", "占比"],
                                "rows": [["2019", "80", "24%"], ["2020", "95", "29%"], ["2021", "120", "36%"]],
                                "row_count": 3,
                                "col_count": 3,
                            },
                            "dataframe_source": "gemini_vision_table",
                            "artifact_source": "pdf_roi_crop",
                        },
                    },
                    {
                        "object_type": "figure",
                        "object_id": "figure-1",
                        "page": 4,
                        "snippet": "chart:2021年年度走势 (gemini_vision_figure)",
                        "confidence": 0.9,
                        "artifact_url": "/extract/artifact/module2/figures/figure-1.png",
                        "locator": {
                            "page": 4,
                            "caption": "2021年年度走势",
                            "figure_type": "chart",
                            "key_points": ["金额逐年上升", "2021年达到峰值"],
                            "content_modes": ["dataframe", "visual"],
                            "dataframe": {
                                "headers": ["年度", "金额"],
                                "rows": [["2019", "80"], ["2020", "95"], ["2021", "120"]],
                                "row_count": 3,
                                "col_count": 2,
                            },
                        },
                    },
                ],
            }
        ],
    }

    with TestClient(app) as client:
        ingest_resp = client.post("/module4/ingest", json=payload)
        assert ingest_resp.status_code == 200, ingest_resp.text
        _wait_job_success(client, ingest_resp.json()["job_id"], tenant_id)

        file_graph_resp = client.get(f"/module4/graph/files/{file_hash}/view?tenant_id={tenant_id}&limit_nodes=200&limit_edges=300")
        assert file_graph_resp.status_code == 200, file_graph_resp.text
        file_graph = file_graph_resp.json()

        node_types = {node["node_type"] for node in file_graph["nodes"]}
        relation_types = {edge["relation_type"] for edge in file_graph["edges"]}
        assert {"Document", "Entity", "Community", "CommunityReport"}.issubset(node_types)
        assert {"has_entity", "related_to", "in_community", "has_report"}.issubset(relation_types)

        report_node = next((node for node in file_graph["nodes"] if node["node_type"] == "CommunityReport"), None)
        assert report_node is not None

        report_detail_resp = client.get(
            f"/module4/graph/files/{file_hash}/node/{report_node['node_id']}?tenant_id={tenant_id}&depth=1&limit=40"
        )
        assert report_detail_resp.status_code == 200, report_detail_resp.text
        report_detail = report_detail_resp.json()
        assert len(report_detail["evidence"]) >= 1


def test_file_graph_artifact_nodes_fall_back_to_page_when_titles_are_low_signal() -> None:
    tenant_id = f"test-{uuid.uuid4().hex[:10]}"
    file_hash = f"hash-{uuid.uuid4().hex[:8]}"
    payload = {
        "tenant_id": tenant_id,
        "source": "module2",
        "documents": [
            {
                "file_name": "low_signal_artifacts.pdf",
                "file_hash": file_hash,
                "track": "zeta",
                "result": {},
                "trace_hits": [
                    {
                        "object_type": "table",
                        "object_id": "table-1",
                        "page": 7,
                        "snippet": "table-1 (pdf_mineru, 3x3)",
                        "confidence": 0.88,
                        "locator": {
                            "page": 7,
                            "table_preview": {
                                "headers": ["??", "??", "??"],
                                "rows": [["1", "2", "3"]],
                                "row_count": 1,
                                "col_count": 3,
                            },
                            "dataframe": {
                                "headers": ["??", "??", "??"],
                                "rows": [["1", "2", "3"]],
                                "row_count": 1,
                                "col_count": 3,
                            },
                        },
                    }
                ],
            }
        ],
    }

    with TestClient(app) as client:
        ingest_resp = client.post("/module4/ingest", json=payload)
        assert ingest_resp.status_code == 200, ingest_resp.text
        _wait_job_success(client, ingest_resp.json()["job_id"], tenant_id)

        file_graph_resp = client.get(f"/module4/graph/files/{file_hash}/view?tenant_id={tenant_id}&limit_nodes=200&limit_edges=300")
        assert file_graph_resp.status_code == 200, file_graph_resp.text
        file_graph = file_graph_resp.json()
        node_types = {node["node_type"] for node in file_graph["nodes"]}
        assert {"Document", "Chunk", "Entity", "Community"}.issubset(node_types)
        assert len(file_graph["edges"]) >= 1


def test_file_graph_artifact_nodes_prefer_locator_title_and_summary_when_headers_are_low_signal() -> None:
    tenant_id = f"test-{uuid.uuid4().hex[:10]}"
    file_hash = f"hash-{uuid.uuid4().hex[:8]}"
    payload = {
        "tenant_id": tenant_id,
        "source": "module2",
        "documents": [
            {
                "file_name": "semantic_table_title.pdf",
                "file_hash": file_hash,
                "track": "omega",
                "result": {},
                "trace_hits": [
                    {
                        "object_type": "table",
                        "object_id": "table-1",
                        "page": 5,
                        "snippet": "table-1 (pdf_mineru, 3x3)",
                        "confidence": 0.91,
                        "locator": {
                            "page": 5,
                            "title": "\u57ce\u4e61\u4f4e\u4fdd\u652f\u51fa\u7edf\u8ba1",
                            "summary": "\u57ce\u4e61\u4f4e\u4fdd\u652f\u51fa\u7edf\u8ba1\uff1b\u8868\u5934\uff1a\u57ce\u5e02 | \u519c\u6751 | \u5408\u8ba1",
                            "table_preview": {
                                "headers": ["??", "??", "??"],
                                "rows": [["120", "80", "200"]],
                                "row_count": 1,
                                "col_count": 3,
                            },
                            "dataframe": {
                                "headers": ["??", "??", "??"],
                                "rows": [["120", "80", "200"], ["132", "85", "217"]],
                                "row_count": 2,
                                "col_count": 3,
                            },
                            "dataframe_source": "gemini_vision_table",
                            "artifact_source": "pdf_roi_crop",
                        },
                    }
                ],
            }
        ],
    }

    with TestClient(app) as client:
        ingest_resp = client.post("/module4/ingest", json=payload)
        assert ingest_resp.status_code == 200, ingest_resp.text
        _wait_job_success(client, ingest_resp.json()["job_id"], tenant_id)

        file_graph_resp = client.get(f"/module4/graph/files/{file_hash}/view?tenant_id={tenant_id}&limit_nodes=200&limit_edges=300")
        assert file_graph_resp.status_code == 200, file_graph_resp.text
        file_graph = file_graph_resp.json()

        node_types = {node["node_type"] for node in file_graph["nodes"]}
        relation_types = {edge["relation_type"] for edge in file_graph["edges"]}
        assert {"Document", "Chunk", "Entity", "Community", "CommunityReport"}.issubset(node_types)
        assert {"has_chunk", "has_entity", "related_to", "in_community", "has_report"}.issubset(relation_types)


def test_nonpdf_semantic_graph_creates_business_context_claims_and_business_alerts() -> None:
    tenant_id = f"test-{uuid.uuid4().hex[:10]}"
    file_hash = f"hash-{uuid.uuid4().hex[:8]}"
    payload = {
        "tenant_id": tenant_id,
        "source": "module2",
        "documents": [
            {
                "file_name": "hangzhou_environment_report.docx",
                "file_hash": file_hash,
                "track": "semantic-nonpdf",
                "result": {
                    "report_year": {"value": 2024, "confidence": 0.99, "source_ref_id": "r-year"},
                    "city": {"value": "Hangzhou", "confidence": 0.97, "source_ref_id": "r-city"},
                    "good_air_rate": {"value": 81.7, "confidence": 0.94, "source_ref_id": "r-air-rate"},
                    "ozone_value": {"value": 164, "confidence": 0.93, "source_ref_id": "r-ozone"},
                    "main_pollutant": {"value": "Ozone", "confidence": 0.96, "source_ref_id": "r-pollutant"},
                },
                "diagnostics": {
                    "nonpdf_profile": "chart_heavy",
                    "polymorphic_links": [
                        {
                            "field": "good_air_rate",
                            "targets": [
                                {
                                    "type": "figure",
                                    "id": "figure-1",
                                    "page": 4,
                                    "match": "regional comparison",
                                    "confidence": 0.92,
                                }
                            ],
                        },
                        {
                            "field": "main_pollutant",
                            "targets": [
                                {
                                    "type": "figure",
                                    "id": "figure-1",
                                    "page": 4,
                                    "match": "pollutant trend",
                                    "confidence": 0.92,
                                }
                            ],
                        },
                    ],
                },
                "trace_hits": [
                    {
                        "object_type": "field",
                        "object_id": "good_air_rate",
                        "page": 4,
                        "ref_id": "r-air-rate",
                        "snippet": "good_air_rate: 81.7%",
                        "confidence": 0.94,
                    },
                    {
                        "object_type": "field",
                        "object_id": "main_pollutant",
                        "page": 4,
                        "ref_id": "r-pollutant",
                        "snippet": "main pollutant: ozone",
                        "confidence": 0.96,
                    },
                    {
                        "object_type": "figure",
                        "object_id": "figure-1",
                        "page": 4,
                        "ref_id": "figure-1-caption",
                        "snippet": "chart:regional air quality comparison",
                        "confidence": 0.93,
                        "artifact_url": "/extract/artifact/module2/figures/figure-1.png",
                        "locator": {
                            "page": 4,
                            "title": "Regional Air Quality Comparison",
                            "summary": "Regional good-air-rate comparison across Hangzhou districts",
                            "key_points": [
                                "Jiande has the highest good-air-rate at 97.0%",
                                "Urban Hangzhou has the lowest good-air-rate at 81.7%",
                            ],
                            "dataframe": {
                                "headers": ["region", "good_air_rate"],
                                "rows": [["Urban Hangzhou", "81.7%"], ["Jiande", "97.0%"]],
                                "row_count": 2,
                                "col_count": 2,
                            },
                            "dataframe_source": "gemini_vision_figure",
                            "artifact_source": "pdf_roi_crop",
                            "figure_type": "chart",
                        },
                    },
                ],
            }
        ],
    }

    with TestClient(app) as client:
        ingest_resp = client.post("/module4/ingest", json=payload)
        assert ingest_resp.status_code == 200, ingest_resp.text
        _wait_job_success(client, ingest_resp.json()["job_id"], tenant_id)

        file_graph_resp = client.get(
            f"/module4/graph/files/{file_hash}/view?tenant_id={tenant_id}&limit_nodes=400&limit_edges=800"
        )
        assert file_graph_resp.status_code == 200, file_graph_resp.text
        graph = file_graph_resp.json()
        node_types = {node["node_type"] for node in graph["nodes"]}
        relation_types = {edge["relation_type"] for edge in graph["edges"]}

        assert {"Document", "Chunk", "Entity", "Community", "CommunityReport"}.issubset(node_types)
        assert {"has_chunk", "has_entity", "related_to", "in_community", "has_report"}.issubset(relation_types)

        report_node = next((node for node in graph["nodes"] if node["node_type"] == "CommunityReport"), None)
        assert report_node is not None

        report_detail_resp = client.get(
            f"/module4/graph/files/{file_hash}/node/{report_node['node_id']}?tenant_id={tenant_id}&depth=1&limit=120"
        )
        assert report_detail_resp.status_code == 200, report_detail_resp.text
        report_detail = report_detail_resp.json()
        assert len(report_detail["evidence"]) >= 1


def test_rebuild_replays_saved_batches_for_tenant() -> None:
    tenant_id = f"test-{uuid.uuid4().hex[:10]}"
    payload = {
        "tenant_id": tenant_id,
        "source": "module2",
        "documents": [
            {
                "file_name": "rebuild_doc.pdf",
                "file_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "track": "delta",
                "result": {
                    "party": {"value": "Northwind", "confidence": 0.93, "source_ref_id": "r1"},
                    "amount": {"value": "23000", "confidence": 0.41, "source_ref_id": "r2"},
                },
                "errors": ["parse mismatch"],
                "soft_warnings": ["weak date pattern"],
                "diagnostics": {"quality_status": "degraded"},
                "trace_hits": [
                    {
                        "object_type": "table",
                        "object_id": "summary-table",
                        "page": 3,
                        "snippet": "summary table",
                        "confidence": 0.84,
                    }
                ],
            }
        ],
    }

    with TestClient(app) as client:
        ingest_resp = client.post("/module4/ingest", json=payload)
        assert ingest_resp.status_code == 200, ingest_resp.text
        _wait_job_success(client, ingest_resp.json()["job_id"], tenant_id)

        graph_before = client.get(f"/module4/graph?tenant_id={tenant_id}&limit_nodes=500&limit_edges=1000").json()
        alerts_before = client.get(f"/module4/alerts?tenant_id={tenant_id}&page=1&page_size=50").json()
        evidence_before = client.get(f"/module4/evidence?tenant_id={tenant_id}&page=1&page_size=50").json()

        rebuild_resp = client.post("/module4/rebuild", json={"tenant_id": tenant_id})
        assert rebuild_resp.status_code == 200, rebuild_resp.text
        rebuild_payload = rebuild_resp.json()
        assert rebuild_payload["batches"] == 1
        assert rebuild_payload["documents"] == 1

        rebuild_job = _wait_job_success(client, rebuild_payload["job_id"], tenant_id)
        assert rebuild_job["status"] == "success", rebuild_job
        assert rebuild_job["result"]["batches"] == 1
        assert rebuild_job["result"]["documents"] == 1

        graph_after = client.get(f"/module4/graph?tenant_id={tenant_id}&limit_nodes=500&limit_edges=1000").json()
        alerts_after = client.get(f"/module4/alerts?tenant_id={tenant_id}&page=1&page_size=50").json()
        evidence_after = client.get(f"/module4/evidence?tenant_id={tenant_id}&page=1&page_size=50").json()

        assert len(graph_after["nodes"]) == len(graph_before["nodes"])
        assert len(graph_after["edges"]) == len(graph_before["edges"])
        assert alerts_after["total"] == alerts_before["total"]
        assert evidence_after["total"] == evidence_before["total"]


def test_job_and_alert_actions_are_tenant_scoped() -> None:
    tenant_id = f"test-{uuid.uuid4().hex[:10]}"
    wrong_tenant = f"test-{uuid.uuid4().hex[:10]}"
    payload = {
        "tenant_id": tenant_id,
        "source": "module2",
        "documents": [
            {
                "file_name": "tenant_scope.pdf",
                "file_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "track": "omega",
                "result": {
                    "amount": {"value": "5000", "confidence": 0.33, "source_ref_id": "r1"},
                },
                "errors": ["mismatch"],
                "diagnostics": {"quality_status": "degraded"},
            }
        ],
    }

    with TestClient(app) as client:
        ingest_resp = client.post("/module4/ingest", json=payload)
        assert ingest_resp.status_code == 200, ingest_resp.text
        job_id = ingest_resp.json()["job_id"]
        _wait_job_success(client, job_id, tenant_id)

        wrong_job = client.get(f"/module4/jobs/{job_id}?tenant_id={wrong_tenant}")
        assert wrong_job.status_code == 404

        graph_ok = client.get(f"/module4/graph?tenant_id={tenant_id}&limit_nodes=50&limit_edges=80")
        assert graph_ok.status_code == 200
        graph_wrong = client.get(f"/module4/graph?tenant_id={wrong_tenant}&limit_nodes=50&limit_edges=80")
        assert graph_wrong.status_code == 200
        assert len(graph_wrong.json().get("nodes", [])) == 0


def test_healthz_reports_failed_when_database_is_not_connected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        module4_main._get_runtime_ref("graphrag_indexer"),
        "probe",
        lambda *_args, **_kwargs: GraphRAGRuntimeProbe(
            ready=False,
            check_mode="basic",
            python_bin="python",
            python_bin_exists=False,
            graphrag_module_available=False,
            module_error_message="Configured python executable not found: python",
            prompt_assets_root=str(MODULE4_DIR / "assets" / "prompts"),
            prompt_assets_ok=True,
            missing_prompt_assets=[],
            config_missing_fields=[],
            provider_api=GraphRAGDependencyProbe(configured=True, reachable=None),
            neo4j=GraphRAGDependencyProbe(configured=False, reachable=None, missing_fields=["MODULE4_NEO4J_URI"]),
        ),
    )
    with TestClient(app) as client:
        resp = client.get("/module4/healthz")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["status"] == "failed"
        assert payload["db_connected"] is False
        assert "degraded_memory_mode" not in payload
        assert payload["jobs_in_queue"] >= 0
        assert payload["graphrag"]["ready"] is False
        assert payload["graphrag"]["graphrag_module_available"] is False
        assert "runtime_profile" in payload["graphrag"]
        assert "env_mapping" in payload["graphrag"]
        assert "projection_runtime" in payload
        assert payload["projection_runtime"]["relationship_type"] == "MODULE4_EDGE"
        assert payload["projection_runtime"]["max_nodes"] >= 1


def test_healthz_exposes_projection_runtime_configuration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runtime = GraphRAGRuntimeSettings(
        module4_root=MODULE4_DIR,
        workspaces_root=tmp_path / "workspaces",
        prompt_assets_root=(MODULE4_DIR / "assets" / "prompts").resolve(),
        api_base="http://oneapi.example/v1",
        chat_api_key="chat-secret",
        chat_model="qwen-turbo",
        embedding_api_key="embed-secret",
        embedding_model="text-embedding-v1",
    )
    builder = GraphRAGWorkspaceBuilder(
        runtime=runtime,
        prompt_registry=PromptRegistry(
            asset_root=runtime.prompt_assets_root,
            overrides=runtime.prompt_overrides(),
        ),
        neo4j=Neo4jSettings(uri="neo4j+s://example.databases.neo4j.io:7687", username="neo4j", password="secret", database="neo4j"),
    )
    module4_main._set_runtime_ref("workspace_builder", builder)
    monkeypatch.setattr(module4_main._get_runtime_ref("neo4j_graph_projector"), "enabled", True)
    monkeypatch.setattr(module4_main._get_runtime_ref("neo4j_graph_projector"), "max_nodes", 321)
    monkeypatch.setattr(module4_main._get_runtime_ref("neo4j_graph_projector"), "max_edges", 654)
    monkeypatch.setattr(module4_main._get_runtime_ref("neo4j_graph_projector"), "timeout_sec", 1.75)
    monkeypatch.setattr(
        module4_main._get_runtime_ref("graphrag_indexer"),
        "probe",
            lambda *_args, **_kwargs: GraphRAGRuntimeProbe(
                ready=True,
                check_mode="deep",
                python_bin="python",
                python_bin_exists=True,
                graphrag_module_available=True,
                module_error_message=None,
                prompt_assets_root=str(runtime.prompt_assets_root),
                prompt_assets_ok=True,
                missing_prompt_assets=[],
                config_missing_fields=[],
                runtime_profile={"indexing_method": "standard"},
                env_mapping={"runtime": {"MODULE4_GRAPHRAG_API_BASE": "GRAPHRAG_API_BASE"}},
                provider_api=GraphRAGDependencyProbe(configured=True, reachable=True),
                neo4j=GraphRAGDependencyProbe(configured=True, reachable=True),
            ),
        )

    with TestClient(app) as client:
        resp = client.get("/module4/healthz?probe=deep")
        assert resp.status_code == 200, resp.text
        payload = resp.json()
        assert payload["graphrag"]["runtime_profile"]["indexing_method"] == "standard"
        assert payload["graphrag"]["env_mapping"]["runtime"]["MODULE4_GRAPHRAG_API_BASE"] == "GRAPHRAG_API_BASE"
        assert payload["projection_runtime"]["enabled"] is True
        assert payload["projection_runtime"]["configured"] is True
        assert payload["projection_runtime"]["can_project"] is True
        assert payload["projection_runtime"]["database"] == "neo4j"
        assert payload["projection_runtime"]["max_nodes"] == 321
        assert payload["projection_runtime"]["max_edges"] == 654
        assert payload["projection_runtime"]["timeout_sec"] == 1.75
        assert payload["projection_runtime"]["labels"] == ["Module4Node"]


def test_rule_upsert_rejects_unsupported_rule_kind() -> None:
    with TestClient(app) as client:
        resp = client.put(
            "/module4/rules/RULE_SEMANTIC_TRIAL",
            json={
                "name": "Semantic Trial",
                "severity": "yellow",
                "rule_kind": "semantic",
                "expr": {"scope": "document", "path": "diagnostics.quality_status", "op": "eq", "value": "degraded"},
                "enabled": True,
            },
        )
        assert resp.status_code == 422, resp.text
        assert "deterministic" in resp.text


def test_simulate_evaluates_deterministic_rules_against_inline_contexts() -> None:
    tenant_id = f"test-{uuid.uuid4().hex[:10]}"
    payload = {
        "tenant_id": tenant_id,
        "scenario_name": "inline-deterministic",
        "params": {
            "document_context": {
                "file_name": "contract.pdf",
                "file_hash": "hash-inline",
                "track": "gamma",
                "errors": ["parse mismatch"],
                "errors_count": 1,
                "soft_warnings": [],
                "soft_warning_count": 0,
                "diagnostics": {"quality_status": "degraded"},
                "field_count": 1,
            },
            "field_contexts": [
                {
                    "file_name": "contract.pdf",
                    "file_hash": "hash-inline",
                    "track": "gamma",
                    "field_name": "amount",
                    "value": "1000",
                    "confidence": 0.31,
                    "diagnostics": {"quality_status": "degraded"},
                }
            ],
        },
    }

    with TestClient(app) as client:
        resp = client.post("/module4/simulate", json=payload)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert str(body["summary"]).strip()
        rule_ids = {item["rule_id"] for item in body["changed_alerts"]}
        assert "RULE_LOW_CONFIDENCE" in rule_ids
        assert "RULE_DOC_ERRORS" in rule_ids
        assert "RULE_QUALITY_DEGRADED" in rule_ids
        metrics = {item["metric"]: item["value"] for item in body["impacts"]}
        assert metrics["simulated_contexts"] == 2
        assert metrics["simulated_hits"] >= 3


def test_simulate_can_reuse_alert_payload_context() -> None:
    tenant_id = f"test-{uuid.uuid4().hex[:10]}"
    ingest_payload = {
        "tenant_id": tenant_id,
        "source": "module2",
        "documents": [
            {
                "file_name": "risk.pdf",
                "file_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "track": "omega",
                "result": {
                    "amount": {"value": "5000", "confidence": 0.33, "source_ref_id": "r1"},
                },
                "errors": ["mismatch"],
                "diagnostics": {"quality_status": "degraded"},
            }
        ],
    }

    with TestClient(app) as client:
        ingest_resp = client.post("/module4/ingest", json=ingest_payload)
        assert ingest_resp.status_code == 200, ingest_resp.text
        _wait_job_success(client, ingest_resp.json()["job_id"], tenant_id)

        simulate_resp = client.post(
            "/module4/simulate",
            json={
                "tenant_id": tenant_id,
                "scenario_name": "alert-context-reuse",
                "scope": {"alert_id": f"missing-{uuid.uuid4().hex[:8]}"},
            },
        )
        assert simulate_resp.status_code == 200, simulate_resp.text
        body = simulate_resp.json()
        assert isinstance(body.get("changed_alerts"), list)
        assert str(body.get("summary") or "").strip()


def test_cancelled_ingest_job_is_requeued_for_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = f"test-{uuid.uuid4().hex[:10]}"
    payload = IngestRequest(
        tenant_id=tenant_id,
        source="module2",
        documents=[
            {
                "file_name": "recovery.pdf",
                "file_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "track": "recover",
                "result": {"amount": {"value": "1200", "confidence": 0.4}},
                "diagnostics": {},
            }
        ],
    )

    async def slow_process_document(**_: object) -> dict[str, int]:
        await asyncio.sleep(10)
        return {"nodes": 0, "edges": 0, "alerts": 0, "evidence": 0}

    monkeypatch.setattr(module4_main.module4_app_runtime, "_process_document_fn", slow_process_document)

    async def scenario() -> None:
        job = await module4_main._get_runtime_ref("storage").create_job(
            tenant_id=tenant_id,
            job_type="ingest",
            status="queued",
            payload={"source": "module2", "documents": len(payload.documents)},
        )
        batch = await module4_main._get_runtime_ref("storage").create_ingest_batch(
            tenant_id=tenant_id,
            source="module2",
            source_batch_key=f"recovery-{uuid.uuid4().hex[:8]}",
            job_id=str(job["job_id"]),
            raw_payload=payload.model_dump(mode="json"),
        )

        task = asyncio.create_task(module4_main._run_ingest_job(str(job["job_id"]), str(batch["batch_id"]), payload))
        await asyncio.sleep(0.05)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        recovered = await module4_main._get_runtime_ref("storage").get_job(str(job["job_id"]), tenant_id=tenant_id)
        assert recovered is not None
        assert recovered["status"] == "queued"
        assert "queued for recovery" in str(recovered.get("error_message") or "")

    asyncio.run(scenario())

