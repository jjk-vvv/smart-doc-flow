from __future__ import annotations

import asyncio
import io
import sys
from importlib import import_module
from pathlib import Path

from starlette.datastructures import UploadFile
from starlette.requests import Request


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


fusion_routes = import_module("app.modules.module3.api.endpoints.fusion")


def _build_request() -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/module3/run/run_1/save-file",
        "query_string": b"",
        "headers": [],
    }
    return Request(scope)


def test_save_run_output_file_updates_output_file_id(monkeypatch, tmp_path: Path) -> None:
    output_path = (tmp_path / "result.xlsx").resolve()
    output_path.write_bytes(b"before")

    status_updates: list[dict] = []
    monkeypatch.setattr(fusion_routes, "_resolve_request_owner_id", lambda request: "tenant-a")
    monkeypatch.setattr(fusion_routes, "_require_run_output_path", lambda run_id, owner_id: ({"run_id": run_id}, output_path))
    monkeypatch.setattr(fusion_routes, "register_run_output_file_asset", lambda path, owner_id, filename=None: "fa_new")
    monkeypatch.setattr(fusion_routes, "set_run_status", lambda run_id, **updates: status_updates.append(updates))

    request = _build_request()
    upload = UploadFile(file=io.BytesIO(b"after"), filename="result.xlsx")
    result = asyncio.run(fusion_routes.save_run_output_file("run_1", request, upload))

    assert result["status"] == "ok"
    assert output_path.read_bytes() == b"after"
    assert status_updates
    assert status_updates[-1]["output_file_id"] == "fa_new"
