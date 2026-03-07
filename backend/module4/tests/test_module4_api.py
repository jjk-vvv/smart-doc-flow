from __future__ import annotations

import time
import uuid
from pathlib import Path
import sys
import os

from fastapi.testclient import TestClient

MODULE4_DIR = Path(__file__).resolve().parents[1]
if str(MODULE4_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE4_DIR))
os.environ["MODULE4_FORCE_MEMORY_MODE"] = "1"

from app.main import app  # noqa: E402


def _wait_job_success(client: TestClient, job_id: str, timeout_s: float = 6.0) -> dict:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        resp = client.get(f"/module4/jobs/{job_id}")
        assert resp.status_code == 200
        row = resp.json()
        if row["status"] in {"success", "failed", "cancelled"}:
            return row
        time.sleep(0.05)
    raise AssertionError("job timeout")


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

        final_job = _wait_job_success(client, job_id)
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
