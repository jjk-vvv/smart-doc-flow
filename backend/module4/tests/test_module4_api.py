from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi.testclient import TestClient

MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))
os.environ["MODULE4_FORCE_MEMORY_MODE"] = "1"

import app.main as module4_main  # noqa: E402
from app.main import app  # noqa: E402
from app.schemas import IngestRequest  # noqa: E402
from app.services import (  # noqa: E402
    GraphRAGDependencyProbe,
    GraphRAGRuntimeProbe,
    GraphRAGRuntimeSettings,
    GraphRAGWorkspaceBuilder,
    Neo4jSettings,
    PromptRegistry,
)


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


def _write_parquet(path: Path, rows: list[dict]) -> None:
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


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
        assert alerts["total"] >= 2

        evidence_resp = client.get(f"/module4/evidence?tenant_id={tenant_id}&page=1&page_size=50")
        assert evidence_resp.status_code == 200
        evidence = evidence_resp.json()
        assert evidence["total"] >= 1

        contains_edge = next((e for e in graph["edges"] if e.get("relation_type") == "contains"), None)
        assert contains_edge is not None
        edge_evidence_resp = client.get(
            f"/module4/evidence/edge/{contains_edge['edge_id']}?tenant_id={tenant_id}&page=1&page_size=20"
        )
        assert edge_evidence_resp.status_code == 200
        edge_evidence = edge_evidence_resp.json()
        assert edge_evidence["total"] >= 1


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


def test_upload_sync_endpoint_is_idempotent_for_same_uploads(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = f"test-{uuid.uuid4().hex[:10]}"
    payload = {
        "tenant_id": tenant_id,
        "source": "module2",
        "graph_mode": "hybrid",
        "uploads": [
            {
                "file_name": "upload.txt",
                "file_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "artifact_path": "D:/artifacts/upload.txt",
                "artifact_url": "/artifacts/upload.txt",
                "mime_type": "text/plain",
            }
        ],
    }

    async def fake_run_upload_ingest_job(job_id: str, batch_id: str, ingest_payload: IngestRequest) -> dict:
        return {
            "stage": "ready",
            "workspace_id": f"ws-{batch_id[:8]}",
            "workspace_dir": "D:/module4/workspaces/test",
            "uploads": len(ingest_payload.uploads),
            "documents": 0,
            "nodes": 3,
            "edges": 2,
            "communities": 1,
        }

    monkeypatch.setattr(module4_main, "_run_upload_ingest_job", fake_run_upload_ingest_job)

    with TestClient(app) as client:
        first = client.post("/module4/sync/uploads", json=payload)
        assert first.status_code == 200, first.text
        first_job = _wait_job_success(client, first.json()["job_id"], tenant_id)
        assert first_job["status"] == "success"
        assert first_job["result"]["uploads"] == 1
        assert first_job["result"]["workspace_id"].startswith("ws-")

        second = client.post("/module4/sync/uploads", json=payload)
        assert second.status_code == 200, second.text
        second_payload = second.json()
        assert second_payload["job_id"] == first.json()["job_id"]
        assert second_payload["batch_id"] == first.json()["batch_id"]
        assert second_payload["status"] == "success"


def test_upload_sync_falls_back_to_partial_artifacts_when_indexing_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    tenant_id = f"test-{uuid.uuid4().hex[:10]}"

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
        neo4j=Neo4jSettings(uri="neo4j://example", username="neo4j", password="secret", database="neo4j"),
    )
    monkeypatch.setattr(module4_main, "workspace_builder", builder)

    monkeypatch.setattr(
        module4_main.graphrag_indexer,
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
            oneapi=GraphRAGDependencyProbe(configured=True, reachable=True),
            neo4j=GraphRAGDependencyProbe(configured=True, reachable=True),
        ),
    )

    def fake_run(workspace_dir: Path) -> object:
        artifacts_dir = workspace_dir / "output" / "20260101-000000" / "artifacts"
        reports_dir = workspace_dir / "output" / "20260101-000000" / "reports"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        reports_dir.mkdir(parents=True, exist_ok=True)

        _write_parquet(
            artifacts_dir / "create_base_text_units.parquet",
            [
                {
                    "id": "chunk-1",
                    "chunk": "Qingniu Town is located in Linhai New District.",
                    "chunk_id": "chunk-1",
                    "document_ids": ["doc-1"],
                    "n_tokens": 16,
                }
            ],
        )
        graphml = """
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="d0" for="node" attr.name="type" attr.type="string" />
  <key id="d1" for="node" attr.name="description" attr.type="string" />
  <key id="d2" for="node" attr.name="source_id" attr.type="string" />
  <key id="d3" for="edge" attr.name="description" attr.type="string" />
  <key id="d4" for="edge" attr.name="weight" attr.type="double" />
  <key id="d5" for="edge" attr.name="source_id" attr.type="string" />
  <graph edgedefault="undirected">
    <node id="QINGNIU TOWN">
      <data key="d0">GEO</data>
      <data key="d1">A town in Linhai New District</data>
      <data key="d2">chunk-1</data>
    </node>
    <node id="LINHAI NEW DISTRICT">
      <data key="d0">GEO</data>
      <data key="d1">A district that contains Qingniu Town</data>
      <data key="d2">chunk-1</data>
    </node>
    <edge source="QINGNIU TOWN" target="LINHAI NEW DISTRICT">
      <data key="d3">Qingniu Town is located in Linhai New District</data>
      <data key="d4">2</data>
      <data key="d5">chunk-1</data>
    </edge>
  </graph>
</graphml>
""".strip()
        _write_parquet(artifacts_dir / "create_summarized_entities.parquet", [{"entity_graph": graphml}])
        raise RuntimeError(f"GraphRAG index failed with exit code 1. See {workspace_dir / 'graphrag-index.log'}")

    monkeypatch.setattr(module4_main.graphrag_indexer, "run", fake_run)

    payload = {
        "tenant_id": tenant_id,
        "source": "module2",
        "graph_mode": "hybrid",
        "uploads": [
            {
                "file_name": "sample.txt",
                "file_hash": f"hash-{uuid.uuid4().hex[:8]}",
                "mime_type": "text/plain",
                "text_content": "Qingniu Town is located in Linhai New District.",
            }
        ],
    }

    with TestClient(app) as client:
        ingest_resp = client.post("/module4/sync/uploads", json=payload)
        assert ingest_resp.status_code == 200, ingest_resp.text
        final_job = _wait_job_success(client, ingest_resp.json()["job_id"], tenant_id)
        assert final_job["status"] == "success", final_job
        assert final_job["result"]["partial"] is True
        assert final_job["result"]["mode"] == "partial"
        assert final_job["result"]["index_status"] == "partial"

        graph_resp = client.get(f"/module4/graph?tenant_id={tenant_id}&limit_nodes=100&limit_edges=100")
        assert graph_resp.status_code == 200
        graph = graph_resp.json()
        node_types = {node["node_type"] for node in graph["nodes"]}
        relation_types = {edge["relation_type"] for edge in graph["edges"]}
        assert {"Document", "Chunk", "Entity"}.issubset(node_types)
        assert {"PART_OF", "HAS_ENTITY", "RELATED"}.issubset(relation_types)


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
        field_node = next((node for node in graph["nodes"] if node["node_type"] == "Field"), None)
        assert field_node is not None

        neighborhood_resp = client.get(
            f"/module4/graph/neighborhood/{field_node['node_id']}?tenant_id={tenant_id}&depth=2&limit=40"
        )
        assert neighborhood_resp.status_code == 200, neighborhood_resp.text
        neighborhood = neighborhood_resp.json()
        node_ids = {node["node_id"] for node in neighborhood["nodes"]}
        assert field_node["node_id"] in node_ids
        assert len(neighborhood["edges"]) >= 1


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

        alerts_resp = client.get(f"/module4/alerts?tenant_id={tenant_id}&page=1&page_size=20")
        assert alerts_resp.status_code == 200
        alert_id = alerts_resp.json()["items"][0]["alert_id"]

        wrong_ack = client.post(
            f"/module4/alerts/{alert_id}/ack",
            json={"tenant_id": wrong_tenant, "actor": "tester", "comment": "wrong tenant"},
        )
        assert wrong_ack.status_code == 404

        correct_ack = client.post(
            f"/module4/alerts/{alert_id}/ack",
            json={"tenant_id": tenant_id, "actor": "tester", "comment": "correct tenant"},
        )
        assert correct_ack.status_code == 200
        assert correct_ack.json()["alert"]["status"] == "ack"


def test_healthz_reports_degraded_in_memory_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        module4_main.graphrag_indexer,
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
            oneapi=GraphRAGDependencyProbe(configured=True, reachable=None),
            neo4j=GraphRAGDependencyProbe(configured=False, reachable=None, missing_fields=["MODULE4_NEO4J_URI"]),
        ),
    )
    with TestClient(app) as client:
        resp = client.get("/module4/healthz")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["status"] == "degraded"
        assert payload["db_connected"] is False
        assert payload["degraded_memory_mode"] is True
        assert payload["last_connect_error"]
        assert payload["graphrag"]["ready"] is False
        assert payload["graphrag"]["graphrag_module_available"] is False


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

    monkeypatch.setattr(module4_main, "_process_document", slow_process_document)

    async def scenario() -> None:
        job = await module4_main.storage.create_job(
            tenant_id=tenant_id,
            job_type="ingest",
            status="queued",
            payload={"source": "module2", "documents": len(payload.documents)},
        )
        batch = await module4_main.storage.create_ingest_batch(
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

        recovered = await module4_main.storage.get_job(str(job["job_id"]), tenant_id=tenant_id)
        assert recovered is not None
        assert recovered["status"] == "queued"
        assert "queued for recovery" in str(recovered.get("error_message") or "")

    asyncio.run(scenario())
