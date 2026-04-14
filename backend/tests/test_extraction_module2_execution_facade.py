from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest
from starlette.requests import Request
from starlette.datastructures import UploadFile

from app.core.config import Settings
from app.modules.module2.core.config import ExtractionSettings
from app.modules.module2.core.module2_execution_facade import Module2ExecutionFacade
from app.modules.module2.core.module2_request_runtime import (
    forward_module2_context_headers,
    normalize_cache_clear_scope,
    parse_schema_form_json,
    read_uploads_for_upstream,
)


def _settings(tmp_path: Path) -> Settings:
    frontend_dist_dir = tmp_path / "frontend" / "dist"
    frontend_dist_dir.mkdir(parents=True, exist_ok=True)
    (frontend_dist_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    return Settings(
        gateway_host="0.0.0.0",
        gateway_port=3001,
        cors_origins=("http://localhost:3000",),
        request_timeout_sec=60.0,
        stream_chunk_size=4096,
        runtime_root_dir=tmp_path,
        config_root_dir=tmp_path,
        data_root_dir=tmp_path / "data",
        frontend_dist_dir=frontend_dist_dir,
        module2_upstream_url="http://127.0.0.1:8000",
        module4_upstream_url="http://127.0.0.1:8100",
    )


def _extraction_settings(*, mode: str, fallback_to_upstream: bool = True) -> ExtractionSettings:
    return ExtractionSettings(
        module2_port_hint="",
        artifact_root_dir="",
        module2_execution_mode=mode,
        module2_fallback_to_upstream=fallback_to_upstream,
        module2_worker_timeout_sec=900.0,
        module2_worker_python="",
        module2_sidecar_mode="auto",
        module2_sidecar_python="",
        module2_sidecar_startup_timeout_sec=120.0,
        max_file_mb=25,
        doc_to_pdf_enable=True,
        office_preview_timeout_sec=120.0,
        office_preview_job_ttl_sec=1800.0,
        office_preview_job_cap=240,
        extract_job_ttl_sec=7200.0,
        extract_job_cap=240,
        shadow_poll_timeout_sec=2700.0,
        shadow_poll_interval_sec=1.2,
        assistant1_mode="legacy",
        assistant1_fallback_to_legacy=True,
        assistant1_context_max_source_chars=12000,
        assistant1_context_max_refs=6,
        assistant1_history_window=12,
    )


def test_extract_batch_prefers_subprocess_in_auto_mode(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    facade = Module2ExecutionFacade(_extraction_settings(mode="auto"))
    calls: list[str] = []

    async def fake_subprocess(*args, **kwargs):
        del args, kwargs
        calls.append("subprocess")
        return {"documents": []}

    async def fake_upstream(*args, **kwargs):
        del args, kwargs
        calls.append("upstream")
        return {"documents": [{"file_name": "bad"}]}

    monkeypatch.setattr(facade, "_extract_batch_subprocess", fake_subprocess)
    monkeypatch.setattr(facade, "_extract_batch_upstream", fake_upstream)

    payload = asyncio.run(
        facade.extract_batch(
            settings,
            request_headers={"x-tenant-id": "tenant-a"},
            files_payload=[("files", ("demo.pdf", b"%PDF", "application/pdf"))],
            schema_form='{"fields":["contract_amount"]}',
            tenant_id="tenant-a",
        )
    )

    assert payload == {"documents": []}
    assert calls == ["subprocess"]


def test_extract_batch_falls_back_to_upstream_when_subprocess_fails(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    facade = Module2ExecutionFacade(_extraction_settings(mode="auto", fallback_to_upstream=True))
    calls: list[str] = []

    async def fake_subprocess(*args, **kwargs):
        del args, kwargs
        calls.append("subprocess")
        raise RuntimeError("worker failed")

    async def fake_upstream(*args, **kwargs):
        del args, kwargs
        calls.append("upstream")
        return {"documents": [{"file_name": "demo.pdf"}]}

    monkeypatch.setattr(facade, "_extract_batch_subprocess", fake_subprocess)
    monkeypatch.setattr(facade, "_extract_batch_upstream", fake_upstream)

    payload = asyncio.run(
        facade.extract_batch(
            settings,
            request_headers={},
            files_payload=[("files", ("demo.pdf", b"%PDF", "application/pdf"))],
            schema_form="{}",
            tenant_id="",
        )
    )

    assert payload["documents"][0]["file_name"] == "demo.pdf"
    assert calls == ["subprocess", "upstream"]


def test_clear_cache_auto_mode_merges_subprocess_and_upstream(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    facade = Module2ExecutionFacade(_extraction_settings(mode="auto"))

    async def fake_subprocess(*args, **kwargs):
        del args, kwargs
        return {
            "ok": True,
            "message": "subprocess cleared",
            "scope": "all",
            "cache_counts": {"subprocess_memory": 2},
            "removed_artifacts": 1,
            "removed_runtime_models": 0,
            "removed_materialized": {"worker_artifacts": 3},
            "process_pool_reset_generation": 2,
        }

    async def fake_upstream(*args, **kwargs):
        del args, kwargs
        return {
            "ok": True,
            "message": "upstream cleared",
            "scope": "all",
            "cache_counts": {"upstream_memory": 4},
            "removed_artifacts": 5,
            "removed_runtime_models": 1,
            "removed_materialized": {"upstream_artifacts": 6},
            "process_pool_reset_generation": 1,
        }

    monkeypatch.setattr(facade, "_clear_cache_subprocess", fake_subprocess)
    monkeypatch.setattr(facade, "_clear_cache_upstream", fake_upstream)

    payload = asyncio.run(facade.clear_cache(settings, scope="all"))

    assert payload["cache_counts"]["subprocess_memory"] == 2
    assert payload["cache_counts"]["upstream_memory"] == 4
    assert payload["removed_artifacts"] == 6
    assert payload["removed_runtime_models"] == 1
    assert payload["removed_materialized"]["worker_artifacts"] == 3
    assert payload["removed_materialized"]["upstream_artifacts"] == 6
    assert payload["process_pool_reset_generation"] == 2


def test_health_payload_reports_subprocess_active_when_worker_exists(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    worker_path = (
        settings.runtime_root_dir / "backend" / "app" / "modules" / "module2" / "core" / "module2_compat_worker.py"
    )
    worker_path.parent.mkdir(parents=True, exist_ok=True)
    worker_path.write_text("print('ok')", encoding="utf-8")
    facade = Module2ExecutionFacade(_extraction_settings(mode="auto"))

    payload = facade.health_payload(settings)

    assert payload["requested_mode"] == "auto"
    assert payload["active_mode"] == "subprocess"
    assert payload["worker_available"] is True


def test_parse_schema_form_json_requires_json_object() -> None:
    parsed = parse_schema_form_json('{"fields": ["contract_amount"]}')

    assert parsed["fields"] == ["contract_amount"]

    with pytest.raises(Exception):
        parse_schema_form_json('["bad"]')


def test_read_uploads_for_upstream_serializes_uploads() -> None:
    upload = UploadFile(filename="demo.pdf", file=io.BytesIO(b"%PDF-1.4"), headers={"content-type": "application/pdf"})

    payload = asyncio.run(read_uploads_for_upstream([upload]))

    assert len(payload) == 1
    field_name, file_tuple = payload[0]
    assert field_name == "files"
    assert file_tuple[0] == "demo.pdf"
    assert file_tuple[1] == b"%PDF-1.4"
    assert file_tuple[2] == "application/pdf"


def test_forward_module2_context_headers_filters_hop_by_hop_headers() -> None:
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/extract/batch",
            "headers": [
                (b"x-tenant-trace", b"trace-001"),
                (b"content-length", b"123"),
                (b"content-type", b"multipart/form-data"),
                (b"connection", b"keep-alive"),
                (b"x-request-id", b"req-1"),
            ],
        }
    )

    forwarded = forward_module2_context_headers(request)

    assert forwarded["x-tenant-trace"] == "trace-001"
    assert forwarded["x-request-id"] == "req-1"
    assert "content-length" not in forwarded
    assert "content-type" not in forwarded
    assert "connection" not in forwarded


def test_normalize_cache_clear_scope_rejects_invalid_value() -> None:
    assert normalize_cache_clear_scope(" runtime ") == "runtime"

    with pytest.raises(Exception):
        normalize_cache_clear_scope("bad-scope")


def test_create_job_uses_sidecar_request_path(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    facade = Module2ExecutionFacade(_extraction_settings(mode="upstream"))
    request_calls: list[dict[str, object]] = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"job_id": "extract_job_demo123", "status": "queued", "terminal": False}

    monkeypatch.setattr(
        "app.modules.module2.core.module2_upstream_runtime.request_module2",
        lambda *args, **kwargs: request_calls.append(dict(kwargs)) or FakeResponse(),
    )

    payload = asyncio.run(
        facade.create_job(
            settings,
            files_payload=[("files", ("demo.pdf", b"%PDF", "application/pdf"))],
            schema_form='{"fields":["contract_amount"]}',
            tenant_id="tenant-a",
        )
    )

    assert payload["job_id"] == "extract_job_demo123"
    assert request_calls[0]["path"] == "/extract/jobs/create"
    assert request_calls[0]["ensure_sidecar"] is True


def test_get_job_status_uses_sidecar_request_path(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    facade = Module2ExecutionFacade(_extraction_settings(mode="upstream"))
    request_calls: list[dict[str, object]] = []

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"job_id": "extract_job_demo123", "status": "completed", "terminal": True}

    monkeypatch.setattr(
        "app.modules.module2.core.module2_upstream_runtime.request_module2",
        lambda *args, **kwargs: request_calls.append(dict(kwargs)) or FakeResponse(),
    )

    payload = facade.get_job_status(settings, job_id="extract_job_demo123", include_documents=True)

    assert payload["job_id"] == "extract_job_demo123"
    assert request_calls[0]["path"] == "/extract/jobs/status/extract_job_demo123"
    assert request_calls[0]["params"] == {"include_documents": "true"}
    assert request_calls[0]["ensure_sidecar"] is True
