from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


endpoint_module = import_module("app.modules.module4.api.v1.endpoints.module4")
deps_module = import_module("app.modules.module4.api.deps")
query_runtime = import_module("app.modules.module4.services.query.runtime")


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def test_module4_query_search_endpoint_augments_context_artifact_links(monkeypatch, tmp_path: Path) -> None:
    artifact = (tmp_path / "module2" / "artifacts" / "preview" / "pdf" / "demo.pdf").resolve()
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_bytes(b"%PDF-1.4")

    def _resolve(reference: str) -> Path | None:
        if reference == "/extract/artifact/preview/pdf/demo.pdf":
            return artifact
        return None

    def _register(**_kwargs) -> Dict[str, Any]:
        return {"file_id": "fa_demo"}

    query_helpers = query_runtime.Module4QueryRuntimeHelpers(
        default_tenant=lambda: "default",
        risk_key=lambda seed: f"rk-{abs(hash(seed))}",
        to_float=_to_float,
        to_int=_to_int,
        as_dict=_as_dict,
        as_list=_as_list,
        artifact_summary_snippet=lambda **kwargs: str(kwargs.get("raw_snippet") or ""),
        normalize_artifact_attrs_for_response=lambda _node_type, attrs: dict(attrs),
        artifact_display_name_from_attrs=lambda display_name, **_kwargs: display_name,
        edge_direction={"out", "bi"},
        alert_severity={"yellow", "orange", "red"},
        alert_status={"open", "ack", "resolved", "false_positive"},
        rule_kind={"deterministic"},
        resolve_artifact_local_path=_resolve,
        register_file_asset=_register,
    )

    async def _fake_search_graph(**_kwargs) -> Dict[str, Any]:
        return {
            "answer": "ok",
            "mode": "local",
            "query": "demo",
            "response_type": "multiple paragraphs",
            "community_level": 2,
            "dynamic_community_selection": False,
            "file_hash": "hash_1",
            "graph_file_id": "gf_1",
            "active_version_id": "gv_1",
            "workspace_id": "ws_1",
            "context_data": {
                "reports": [],
                "entities": [],
                "relationships": [],
                "claims": [],
                "sources": [
                    {
                        "id": "src_1",
                        "artifact_url": "/extract/artifact/preview/pdf/demo.pdf",
                    }
                ],
            },
            "linked_node_ids": [],
            "linked_node_resolution": {},
            "source": "graphrag:query:local",
        }

    monkeypatch.setattr(endpoint_module, "graphrag_query_response_service", _fake_search_graph)

    deps = deps_module.Module4RouterDeps(
        storage_getter=lambda: object(),
        query_helpers=query_helpers,
        insight_helpers=object(),
        workspace_builder_getter=lambda: object(),
        neo4j_graph_projector_getter=lambda: object(),
        graphrag_indexer_getter=lambda: object(),
        tenant_from_request=lambda _request, candidate=None: str(candidate or "tenant-a"),
        parse_csv_list=lambda value: [item.strip() for item in str(value or "").split(",") if item.strip()],
        submit_ingest_job=lambda *_args, **_kwargs: None,  # not used in this test
        schedule_rebuild_job=lambda *_args, **_kwargs: None,
        now_utc=lambda: None,
    )

    app = FastAPI()
    app.include_router(endpoint_module.build_router(deps=deps))
    client = TestClient(app)

    response = client.post(
        "/module4/query/search",
        json={
            "tenant_id": "tenant-a",
            "file_hash": "hash_1",
            "query": "demo",
            "mode": "local",
            "response_type": "multiple paragraphs",
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    source_row = payload["context_data"]["sources"][0]
    assert source_row["artifact_file_id"] == "fa_demo"
    assert source_row["artifact_download_url"] == "/download/fa_demo"
