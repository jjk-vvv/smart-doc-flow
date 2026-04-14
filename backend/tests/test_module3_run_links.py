from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.responses import FileResponse
from starlette.requests import Request


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


fusion_routes = import_module("app.modules.module3.api.endpoints.fusion")


def _build_request() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/module3/run/run_1",
        "query_string": b"",
        "headers": [],
    }
    return Request(scope)


def test_augment_run_record_for_client_prefers_file_id_links() -> None:
    payload = fusion_routes._augment_run_record_for_client(
        {
            "run_id": "run_1",
            "output_file_id": "fa_abc",
            "output_name": "result.xlsx",
        }
    )

    assert payload["status_url"] == "/module3/run/run_1"
    assert payload["download_url"] == "/module3/run/run_1/download"
    assert payload["output_download_url"] == "/download/fa_abc"
    assert payload["output_preview_url"] == "/module3/documents/preview?file_id=fa_abc"


def test_augment_run_record_for_client_derives_name_from_file_asset(monkeypatch) -> None:
    monkeypatch.setattr(
        fusion_routes,
        "resolve_file_for_owner",
        lambda file_id, owner_id: (
            {"file_id": file_id, "filename": "asset_name.xlsx"},
            Path(r"D:\tmp\resolved.xlsx"),
        ),
    )
    payload = fusion_routes._augment_run_record_for_client(
        {
            "run_id": "run_1a",
            "owner_id": "tenant-a",
            "output_file_id": "fa_derive",
        }
    )
    assert payload["output_name"] == "asset_name.xlsx"
    assert payload["output_download_url"] == "/download/fa_derive"
    assert payload["output_preview_url"] == "/module3/documents/preview?file_id=fa_derive"


def test_augment_run_record_for_client_without_file_id_does_not_emit_legacy_preview_link() -> None:
    payload = fusion_routes._augment_run_record_for_client(
        {
            "run_id": "run_2",
            "output_file_id": "",
            "output_name": "result.xlsx",
        }
    )

    assert payload["status_url"] == "/module3/run/run_2"
    assert payload["download_url"] == "/module3/run/run_2/download"
    assert payload["output_name"] == "result.xlsx"
    assert "output_preview_url" not in payload
    assert "output_filename" not in payload


def test_get_run_status_returns_augmented_payload(monkeypatch) -> None:
    monkeypatch.setattr(fusion_routes, "_resolve_request_owner_id", lambda request, explicit_owner_id=None: "tenant-a")
    monkeypatch.setattr(
        fusion_routes,
        "load_run_record",
        lambda run_id, owner_id=None: {
            "run_id": run_id,
            "status": "done",
            "output_file_id": "fa_done",
            "output_name": "out.xlsx",
        },
    )

    payload = fusion_routes.get_run_status("run_3", _build_request())
    assert payload["run_id"] == "run_3"
    assert payload["download_url"] == "/module3/run/run_3/download"
    assert payload["output_download_url"] == "/download/fa_done"


def test_augment_template_record_for_client_adds_download_link() -> None:
    payload = fusion_routes._augment_template_record_for_client(
        {
            "template_id": "tpl_1",
            "filename": "template.docx",
            "template_file_id": "fa_tpl",
        }
    )

    assert payload["template_file_id"] == "fa_tpl"
    assert payload["template_download_url"] == "/download/fa_tpl"


def test_augment_docset_record_for_client_adds_file_links() -> None:
    payload = fusion_routes._augment_docset_record_for_client(
        {
            "doc_set_id": "doc_1",
            "count": 2,
            "files": [
                {
                    "filename": "a.docx",
                    "file_id": "fa_a",
                },
                {
                    "filename": "b.txt",
                    "file_id": "",
                },
            ],
        }
    )

    first = payload["files"][0]
    second = payload["files"][1]
    assert first["download_url"] == "/download/fa_a"
    assert first["preview_url"] == "/module3/documents/preview?file_id=fa_a"
    assert "download_url" not in second
    assert "preview_url" not in second


def test_build_run_save_response_includes_run_and_download_links() -> None:
    payload = fusion_routes._build_run_save_response(
        run_id="run_save_1",
        message="saved",
        updated_record={
            "status": "completed",
            "output_file_id": "fa_save",
            "output_name": "result.xlsx",
        },
    )

    assert payload["status"] == "ok"
    assert payload["run_status"] == "completed"
    assert payload["run_id"] == "run_save_1"
    assert payload["status_url"] == "/module3/run/run_save_1"
    assert payload["download_url"] == "/module3/run/run_save_1/download"
    assert payload["output_download_url"] == "/download/fa_save"
    assert payload["output_preview_url"] == "/module3/documents/preview?file_id=fa_save"
    assert payload["output_name"] == "result.xlsx"
    assert "output_filename" not in payload


def test_download_run_output_uses_file_id_resolution(monkeypatch, tmp_path: Path) -> None:
    output_path = (tmp_path / "result.xlsx").resolve()
    output_path.write_bytes(b"demo")

    monkeypatch.setattr(fusion_routes, "_resolve_request_owner_id", lambda request, explicit_owner_id=None: "tenant-a")
    monkeypatch.setattr(
        fusion_routes,
        "load_run_record",
        lambda run_id, owner_id=None: {
            "run_id": run_id,
            "output_file_id": "fa_asset",
            "output_name": "legacy.xlsx",
        },
    )
    monkeypatch.setattr(
        fusion_routes,
        "resolve_file_for_owner",
        lambda file_id, owner_id: (
            {
                "file_id": file_id,
                "filename": "friendly.xlsx",
                "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            },
            output_path,
        ),
    )

    response = fusion_routes.download_run_output("run_asset", _build_request())
    assert isinstance(response, FileResponse)
    assert Path(response.path).resolve() == output_path
    assert response.filename == "legacy.xlsx"


def test_preview_document_with_file_id_uses_file_assets_preview(monkeypatch) -> None:
    monkeypatch.setattr(fusion_routes, "_resolve_request_owner_id", lambda request, explicit_owner_id=None: "tenant-a")
    monkeypatch.setattr(
        fusion_routes,
        "build_preview_text_for_owner",
        lambda file_id, owner_id, max_lines=0, max_chars=0: f"preview:{file_id}:{owner_id}",
    )
    response = fusion_routes.preview_document(_build_request(), file_id="fa_preview")
    assert response.body.decode("utf-8") == "preview:fa_preview:tenant-a"


def test_preview_document_requires_file_id(monkeypatch) -> None:
    monkeypatch.setattr(fusion_routes, "_resolve_request_owner_id", lambda request, explicit_owner_id=None: "tenant-a")
    with pytest.raises(HTTPException) as exc_info:
        fusion_routes.preview_document(_build_request())

    assert exc_info.value.status_code == 400
