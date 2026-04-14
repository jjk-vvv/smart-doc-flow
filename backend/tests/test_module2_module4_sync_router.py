from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _load_module(path_parts: list[str], module_name: str):
    module_path = Path(__file__).resolve().parents[1]
    for part in path_parts:
        module_path = module_path / part
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


router_module = _load_module(
    ["app", "modules", "module2", "api", "v1", "endpoints", "module4_sync.py"],
    "_smart_doc_flow_module2_api_v1_module4_sync_endpoint",
)

build_module4_sync_router = router_module.build_router


def _build_app():
    list_calls: list[dict[str, object]] = []
    detail_calls: list[str] = []
    serialize_calls: list[dict[str, object]] = []
    metrics_calls: list[str] = []

    async def _list_outbox_rows(**kwargs):
        list_calls.append(dict(kwargs))
        return [{"outbox_id": "outbox-1", "status": "queued"}]

    async def _get_outbox_row(outbox_id: str):
        detail_calls.append(outbox_id)
        if outbox_id == "missing":
            return None
        return {"outbox_id": outbox_id, "status": "queued"}

    def _build_list_response(**kwargs):
        return {"items": kwargs["rows"], "count": len(kwargs["rows"]), "metrics": kwargs["metrics_snapshot"]}

    def _serialize_outbox_row(row, *, include_payload: bool = False):
        serialize_calls.append({"row": dict(row), "include_payload": include_payload})
        return {"outbox_id": row["outbox_id"], "include_payload": include_payload}

    def _metrics_snapshot():
        metrics_calls.append("metrics")
        return {"attempted_batches": 1}

    app = FastAPI()
    app.include_router(
        build_module4_sync_router(
            list_outbox_rows=_list_outbox_rows,
            get_outbox_row=_get_outbox_row,
            build_list_response=_build_list_response,
            serialize_outbox_row=_serialize_outbox_row,
            metrics_snapshot=_metrics_snapshot,
        )
    )
    return app, list_calls, detail_calls, serialize_calls, metrics_calls


def test_module4_sync_router_lists_outbox_rows() -> None:
    app, list_calls, _, _, metrics_calls = _build_app()

    with TestClient(app) as client:
        response = client.get("/module4-sync/outbox?tenant_id=tenant-a&status=queued,failed&limit=10")

    assert response.status_code == 200
    assert response.json() == {
        "items": [{"outbox_id": "outbox-1", "status": "queued"}],
        "count": 1,
        "metrics": {"attempted_batches": 1},
    }
    assert list_calls == [
        {
            "tenant_id": "tenant-a",
            "source": "module2",
            "source_batch_key": None,
            "endpoint": None,
            "statuses": ["queued", "failed"],
            "limit": 10,
            "include_future": True,
        }
    ]
    assert metrics_calls == ["metrics"]


def test_module4_sync_router_gets_outbox_detail() -> None:
    app, _, detail_calls, serialize_calls, _ = _build_app()

    with TestClient(app) as client:
        response = client.get("/module4-sync/outbox/outbox-1?include_payload=false")

    assert response.status_code == 200
    assert response.json() == {"outbox_id": "outbox-1", "include_payload": False}
    assert detail_calls == ["outbox-1"]
    assert serialize_calls == [
        {
            "row": {"outbox_id": "outbox-1", "status": "queued"},
            "include_payload": False,
        }
    ]


def test_module4_sync_router_returns_404_for_missing_row() -> None:
    app, _, detail_calls, _, _ = _build_app()

    with TestClient(app) as client:
        response = client.get("/module4-sync/outbox/missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "Module4 sync outbox row not found"
    assert detail_calls == ["missing"]
