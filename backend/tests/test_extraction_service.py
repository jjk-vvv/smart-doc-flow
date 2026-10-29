from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import asyncio
import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.core.auth_deps import AuthenticatedUser
from app.modules.module2.schemas.extraction import TraceLocateRequest
from app.modules.module2.services.api.extraction_service import ExtractionService


def _settings(
    tmp_path: Path,
    *,
    auth_tenant_mode: str = "compat_default",
    auth_tenant_default_id: str = "default",
) -> Settings:
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
        auth_tenant_mode=auth_tenant_mode,
        auth_tenant_default_id=auth_tenant_default_id,
    )


def _fake_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id="user-123",
        name="Tester",
        email="tester@example.com",
        phone="13900000000",
        status="active",
        session_id="sess-123",
    )


def test_extraction_service_health_payload_reports_local_routes(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    service = ExtractionService()

    fake_facade = SimpleNamespace(
        health_payload=lambda _settings: {
            "ok": True,
            "configured": True,
            "requested_mode": "legacy",
            "active_mode": "legacy",
            "fallback_to_legacy": True,
            "fallback_active": False,
            "model": "test-chat-model",
            "base_url": "https://example.test",
            "endpoint_path": "/v1/responses",
            "tavily_configured": True,
        }
    )

    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_assistant1_facade",
        lambda: fake_facade,
    )
    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.build_embedded_module2_health_payload",
        lambda: {"status": "ok", "storage_db_connected": True},
    )

    payload = service.health_payload(settings)

    assert payload["ok"] is True
    assert payload["assistant1"]["configured"] is True
    assert payload["assistant1"]["active_mode"] == "legacy"
    assert payload["module2_upstream"]["resolved_url"] == "embedded://module2"
    assert payload["module2_upstream"]["mode"] == "embedded"
    assert payload["module2_sidecar"]["active_mode"] == "embedded"
    assert payload["routes"]["local"]["extract_batch"] == "local"
    assert payload["routes"]["local"]["extract_assistant1_session"] == "local"


def test_extraction_service_get_assistant1_session_forwards_auth_context(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path, auth_tenant_mode="user_preferred")
    service = ExtractionService()
    captured: dict[str, object] = {}

    def _fake_fetch_session_response(
        _settings,
        *,
        request,
        session_id,
        limit=40,
        additional_headers=None,
    ):
        captured["request"] = request
        captured["session_id"] = session_id
        captured["limit"] = limit
        captured["additional_headers"] = dict(additional_headers or {})
        return {"ok": True, "session_id": session_id}

    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_assistant1_facade",
        lambda: SimpleNamespace(
            upstream_runtime=SimpleNamespace(fetch_session_response=_fake_fetch_session_response),
        ),
    )
    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_extraction_settings",
        lambda: SimpleNamespace(assistant1_mode="upstream"),
    )

    request = SimpleNamespace(
        headers={},
        query_params={},
        state=SimpleNamespace(authenticated_user=_fake_user()),
    )

    payload = service.get_assistant1_session(settings, request, "sess-xyz", limit=12)

    assert payload == {"ok": True, "session_id": "sess-xyz"}
    assert captured["session_id"] == "sess-xyz"
    assert captured["limit"] == 12
    assert captured["additional_headers"] == {
        "X-Authenticated-User-Id": "user-123",
        "X-Authenticated-Tenant-Id": "user-123",
        "X-Authenticated-User-Name": "Tester",
        "X-Authenticated-User-Email": "tester@example.com",
        "X-Authenticated-User-Phone": "13900000000",
        "X-Authenticated-Session-Id": "sess-123",
        "X-Tenant-Id": "user-123",
    }


def test_extraction_service_clear_cache_merges_runtime_counters(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    service = ExtractionService()

    async def fake_clear_cache(_settings, *, scope: str) -> dict:
        return {
            "ok": True,
            "message": "module2 cache cleared",
            "scope": scope,
            "cache_counts": {"module2_memory": 2},
            "removed_artifacts": 1,
            "removed_runtime_models": 0,
            "removed_materialized": {"module2_artifacts": 3},
            "process_pool_reset_generation": 4,
        }

    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_module2_execution_facade",
        lambda: SimpleNamespace(
            clear_cache=fake_clear_cache
        ),
    )
    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.clear_shadow_extraction_runtime_state",
        lambda _settings, *, remove_snapshots: {
            "cleared_shadow_jobs_memory": 5,
            "cleared_shadow_pollers_memory": 6,
            "removed_shadow_snapshots": 7 if remove_snapshots else 0,
        },
    )
    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_extraction_artifact_runtime",
        lambda: SimpleNamespace(
            clear_office_preview_runtime_state=lambda: {
                "cleared_office_preview_jobs_memory": 8,
            }
        ),
    )

    payload = asyncio.run(service.clear_cache(settings, scope="all"))

    assert payload["scope"] == "all"
    assert payload["cache_counts"]["module2_memory"] == 2
    assert payload["cache_counts"]["unified_shadow_jobs_memory"] == 5
    assert payload["cache_counts"]["unified_shadow_pollers_memory"] == 6
    assert payload["cache_counts"]["unified_office_preview_jobs_memory"] == 8
    assert payload["removed_materialized"]["module2_artifacts"] == 3
    assert payload["removed_materialized"]["removed_shadow_snapshots"] == 7
    assert payload["process_pool_reset_generation"] == 4


def test_extraction_service_create_job_resolves_user_preferred_tenant(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path, auth_tenant_mode="user_preferred")
    service = ExtractionService()
    captured: dict[str, str] = {}

    async def fake_start_shadow_extraction_job(
        _settings,
        uploads,
        schema_form,
        *,
        parse_schema_form_json,
        read_uploads_for_upstream,
        execution_facade_factory,
        tenant_id="",
    ) -> dict:
        del _settings, uploads, parse_schema_form_json, read_uploads_for_upstream, execution_facade_factory
        captured["schema_form"] = str(schema_form or "")
        captured["tenant_id"] = str(tenant_id or "")
        return {"job_id": "extract_job_demo123", "status": "queued", "terminal": False}

    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.start_shadow_extraction_job",
        fake_start_shadow_extraction_job,
    )

    request = SimpleNamespace(
        headers={},
        query_params={},
        state=SimpleNamespace(authenticated_user=_fake_user()),
    )

    payload = asyncio.run(service.create_job(settings, request, [], '{"fields":["title"]}', ""))

    assert payload["job_id"] == "extract_job_demo123"
    assert captured["schema_form"] == '{"fields":["title"]}'
    assert captured["tenant_id"] == "user-123"


def test_extraction_service_status_only_uses_shadow_snapshot_and_compacts_payload(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    service = ExtractionService()
    captured: dict[str, object] = {}

    def fake_snapshot_status(
        _settings,
        job_id: str,
        *,
        include_documents: bool = False,
        expected_tenant_id: str = "",
    ) -> dict[str, object]:
        del _settings
        captured["job_id"] = job_id
        captured["include_documents"] = include_documents
        captured["expected_tenant_id"] = expected_tenant_id
        return {
            "ok": True,
            "job_id": job_id,
            "status": "completed",
            "terminal": True,
            "created_at": 1,
            "updated_at": 2,
            "progress": {
                "total_files": 1,
                "completed_files": 1,
                "failed_files": 0,
                "current_file_index": 1,
                "current_file_name": "demo.txt",
                "current_stage": "completed",
                "progress_ratio": 1.0,
                "queued_files": 0,
                "active_stages": {"completed": 1},
            },
            "errors": [],
            "files": [
                {
                    "file_name": "demo.txt",
                    "status": "completed",
                }
            ],
            "documents": [
                {
                    "file_name": "demo.txt",
                }
            ],
    }

    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_shadow_extraction_job_status_snapshot",
        fake_snapshot_status,
    )
    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_module2_execution_facade",
        lambda: SimpleNamespace(),
    )

    result = service.get_job_status(
        settings,
        request=None,
        job_id="extract_job_demo123",
        include_documents=True,
        status_only=True,
        tenant_id="tenant-a",
    )

    assert captured == {
        "job_id": "extract_job_demo123",
        "include_documents": False,
        "expected_tenant_id": "tenant-a",
    }
    assert result == {
        "ok": True,
        "job_id": "extract_job_demo123",
        "status": "completed",
        "terminal": True,
        "created_at": 1,
        "updated_at": 2,
        "progress": {
            "total_files": 1,
            "completed_files": 1,
            "failed_files": 0,
            "current_file_index": 1,
            "current_file_name": "demo.txt",
            "current_stage": "completed",
            "progress_ratio": 1.0,
            "queued_files": 0,
            "active_stages": {"completed": 1},
        },
        "errors": [],
    }


def test_extraction_service_status_only_falls_back_to_live_status_when_snapshot_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    service = ExtractionService()
    captured: dict[str, object] = {}

    def fake_snapshot_status(*_args, **_kwargs):
        raise HTTPException(status_code=404, detail="snapshot missing")

    def fake_live_status(
        _settings,
        job_id: str,
        *,
        execution_facade_factory,
        include_documents: bool = False,
        expected_tenant_id: str = "",
    ) -> dict[str, object]:
        del _settings, execution_facade_factory
        captured["job_id"] = job_id
        captured["include_documents"] = include_documents
        captured["expected_tenant_id"] = expected_tenant_id
        return {
            "ok": True,
            "job_id": job_id,
            "status": "running",
            "terminal": False,
            "created_at": 1,
            "updated_at": 2,
            "progress": {
                "total_files": 1,
                "completed_files": 0,
                "failed_files": 0,
                "current_file_index": 1,
                "current_file_name": "demo.txt",
                "current_stage": "extracting",
                "progress_ratio": 0.5,
                "queued_files": 0,
                "active_stages": {"extracting": 1},
            },
            "errors": [],
        }

    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_shadow_extraction_job_status_snapshot",
        fake_snapshot_status,
    )
    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_shadow_extraction_job_status",
        fake_live_status,
    )
    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_module2_execution_facade",
        lambda: SimpleNamespace(),
    )

    result = service.get_job_status(
        settings,
        request=None,
        job_id="extract_job_demo123",
        include_documents=True,
        status_only=True,
        tenant_id="tenant-a",
    )

    assert captured == {
        "job_id": "extract_job_demo123",
        "include_documents": False,
        "expected_tenant_id": "tenant-a",
    }
    assert result["status"] == "running"
    assert result["progress"]["current_stage"] == "extracting"


def test_extraction_service_extract_batch_forwards_resolved_tenant_header(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path, auth_tenant_mode="user_preferred")
    service = ExtractionService()
    captured: dict[str, object] = {}

    async def fake_extract_batch(
        _settings,
        *,
        request_headers,
        files_payload,
        schema_form,
        tenant_id="",
    ) -> dict:
        del _settings, files_payload
        captured["request_headers"] = dict(request_headers or {})
        captured["schema_form"] = str(schema_form or "")
        captured["tenant_id"] = str(tenant_id or "")
        return {"documents": []}

    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_module2_execution_facade",
        lambda: SimpleNamespace(extract_batch=fake_extract_batch),
    )
    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.read_uploads_for_upstream",
        lambda uploads: asyncio.sleep(
            0,
            result=[("files", ("demo.pdf", b"%PDF-1.4", "application/pdf"))],
        ),
    )

    request = SimpleNamespace(
        headers={"x-request-id": "req-1"},
        query_params={},
        state=SimpleNamespace(authenticated_user=_fake_user()),
    )

    payload = asyncio.run(service.extract_batch(settings, request, [], '{"fields":["title"]}', ""))

    assert payload == {"documents": []}
    assert captured["schema_form"] == '{"fields":["title"]}'
    assert captured["tenant_id"] == ""
    assert captured["request_headers"] == {
        "X-Authenticated-User-Id": "user-123",
        "X-Authenticated-Tenant-Id": "user-123",
        "X-Authenticated-User-Name": "Tester",
        "X-Authenticated-User-Email": "tester@example.com",
        "X-Authenticated-User-Phone": "13900000000",
        "X-Authenticated-Session-Id": "sess-123",
        "X-Tenant-Id": "user-123",
        "x-request-id": "req-1",
    }


def test_extraction_service_extract_batch_rejects_mismatched_tenant_in_strict_mode(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path, auth_tenant_mode="user_strict")
    service = ExtractionService()

    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.read_uploads_for_upstream",
        lambda uploads: asyncio.sleep(
            0,
            result=[("files", ("demo.pdf", b"%PDF-1.4", "application/pdf"))],
        ),
    )

    request = SimpleNamespace(
        headers={"x-tenant-id": "other-tenant"},
        query_params={},
        state=SimpleNamespace(authenticated_user=_fake_user()),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(service.extract_batch(settings, request, [], '{"fields":["title"]}', ""))

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Tenant mismatch for authenticated user"


def test_extraction_service_get_job_status_augments_artifact_file_links(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    service = ExtractionService()

    artifact_pdf = (tmp_path / "artifacts" / "preview" / "pdf" / "doc.pdf").resolve()
    artifact_pdf.parent.mkdir(parents=True, exist_ok=True)
    artifact_pdf.write_bytes(b"%PDF-1.4")
    assistant_payload = (tmp_path / "artifacts" / "payloads" / "assistant.json").resolve()
    assistant_payload.parent.mkdir(parents=True, exist_ok=True)
    assistant_payload.write_text('{"ok": true}', encoding="utf-8")

    payload = {
        "job_id": "extract_job_demo123",
        "status": "done",
        "documents": [
            {
                "file_name": "demo.pdf",
                "trace_hits": [
                    {
                        "artifact_path": "preview/pdf/doc.pdf",
                    }
                ],
                "diagnostics": {
                    "assistant_payload_artifact_path": "payloads/assistant.json",
                },
            }
        ],
    }

    def _resolve_existing_artifact_path(_settings, fragment: str) -> Path:
        mapping = {
            "preview/pdf/doc.pdf": artifact_pdf,
            "payloads/assistant.json": assistant_payload,
        }
        return mapping[fragment]

    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_shadow_extraction_job_status",
        lambda *_args, **_kwargs: payload,
    )
    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_extraction_artifact_runtime",
        lambda: SimpleNamespace(resolve_existing_artifact_path=_resolve_existing_artifact_path),
    )
    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.register_file",
        lambda **kwargs: {"file_id": f"fa_{Path(str(kwargs['path'])).stem}"},
    )

    result = service.get_job_status(settings, request=None, job_id="extract_job_demo123", include_documents=True, tenant_id="tenant-a")
    document = result["documents"][0]
    trace_hit = document["trace_hits"][0]
    diagnostics = document["diagnostics"]

    assert trace_hit["artifact_file_id"] == "fa_doc"
    assert trace_hit["artifact_download_url"] == "/download/fa_doc"
    assert trace_hit["artifact_by_file_url"] == "/extract/artifact/by-file/fa_doc"
    assert trace_hit["artifact_url"] == "/extract/artifact/by-file/fa_doc"
    assert diagnostics["assistant_payload_artifact_file_id"] == "fa_assistant"
    assert diagnostics["assistant_payload_artifact_download_url"] == "/download/fa_assistant"
    assert diagnostics["assistant_payload_artifact_by_file_url"] == "/extract/artifact/by-file/fa_assistant"
    assert diagnostics["assistant_payload_artifact_url"] == "/extract/artifact/by-file/fa_assistant"


def test_extraction_service_trigger_graph_sync_recovers_document_from_shadow_snapshot(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, auth_tenant_mode="user_preferred")
    service = ExtractionService()
    captured: dict[str, object] = {}

    def _fake_snapshot_status(
        _settings,
        job_id: str,
        *,
        include_documents: bool = False,
        expected_tenant_id: str = "",
    ) -> dict[str, object]:
        captured["snapshot_job_id"] = job_id
        captured["snapshot_include_documents"] = include_documents
        captured["snapshot_expected_tenant_id"] = expected_tenant_id
        return {
            "job_id": job_id,
            "documents": [
                {
                    "file_name": "demo.pdf",
                    "file_hash": "hash-demo",
                    "track": "VisualTrack",
                    "cached": False,
                    "result": {},
                    "errors": [],
                    "diagnostics": {},
                }
            ],
        }

    async def _fake_trigger_embedded_graph_sync(*, request, payload=None, background_tasks=None):
        del request, background_tasks
        captured["forwarded_payload"] = dict(payload or {})
        return {
            "ok": True,
            "enqueued": True,
            "file_name": str((payload or {}).get("file_name") or ""),
            "file_hash": str((payload or {}).get("file_hash") or ""),
        }

    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_shadow_extraction_job_status_snapshot",
        _fake_snapshot_status,
    )
    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.trigger_embedded_graph_sync",
        _fake_trigger_embedded_graph_sync,
    )

    request = SimpleNamespace(
        headers={},
        query_params={},
        state=SimpleNamespace(authenticated_user=_fake_user()),
    )

    result = asyncio.run(
        service.trigger_graph_sync(
            settings,
            request,
            {
                "job_id": "extract_job_demo123",
                "file_hash": "hash-demo",
            },
        )
    )

    assert result == {
        "ok": True,
        "enqueued": True,
        "file_name": "demo.pdf",
        "file_hash": "hash-demo",
    }
    assert captured["snapshot_job_id"] == "extract_job_demo123"
    assert captured["snapshot_include_documents"] is True
    assert captured["snapshot_expected_tenant_id"] == "user-123"
    forwarded_payload = captured["forwarded_payload"]
    assert isinstance(forwarded_payload, dict)
    assert forwarded_payload["file_name"] == "demo.pdf"
    assert forwarded_payload["file_hash"] == "hash-demo"
    assert forwarded_payload["document"]["file_name"] == "demo.pdf"


def test_extraction_service_trigger_graph_sync_falls_back_to_live_status_when_shadow_snapshot_missing(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, auth_tenant_mode="user_preferred")
    service = ExtractionService()
    captured: dict[str, object] = {}

    def _fake_snapshot_status(*_args, **_kwargs):
        raise HTTPException(status_code=404, detail="shadow snapshot missing")

    def _fake_get_job_status(
        _self,
        _settings,
        _request,
        job_id: str,
        *,
        include_documents: bool = False,
        status_only: bool = False,
        tenant_id: str = "",
    ) -> dict[str, object]:
        captured["live_job_id"] = job_id
        captured["live_include_documents"] = include_documents
        captured["live_status_only"] = status_only
        captured["live_tenant_id"] = tenant_id
        return {
            "job_id": job_id,
            "documents": [
                {
                    "file_name": "demo.txt",
                    "file_hash": "hash-live",
                    "track": "FastTrack",
                    "cached": True,
                    "result": {},
                    "errors": [],
                    "diagnostics": {},
                }
            ],
        }

    async def _fake_trigger_embedded_graph_sync(*, request, payload=None, background_tasks=None):
        del request, background_tasks
        captured["forwarded_payload"] = dict(payload or {})
        return {
            "ok": True,
            "enqueued": True,
            "file_name": str((payload or {}).get("file_name") or ""),
            "file_hash": str((payload or {}).get("file_hash") or ""),
        }

    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_shadow_extraction_job_status_snapshot",
        _fake_snapshot_status,
    )
    monkeypatch.setattr(
        ExtractionService,
        "get_job_status",
        _fake_get_job_status,
    )
    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.trigger_embedded_graph_sync",
        _fake_trigger_embedded_graph_sync,
    )

    request = SimpleNamespace(
        headers={},
        query_params={},
        state=SimpleNamespace(authenticated_user=_fake_user()),
    )

    result = asyncio.run(
        service.trigger_graph_sync(
            settings,
            request,
            {
                "job_id": "extract_job_demo456",
                "file_hash": "hash-live",
            },
        )
    )

    assert result == {
        "ok": True,
        "enqueued": True,
        "file_name": "demo.txt",
        "file_hash": "hash-live",
    }
    assert captured["live_job_id"] == "extract_job_demo456"
    assert captured["live_include_documents"] is True
    assert captured["live_status_only"] is False
    assert captured["live_tenant_id"] == ""
    forwarded_payload = captured["forwarded_payload"]
    assert isinstance(forwarded_payload, dict)
    assert forwarded_payload["file_name"] == "demo.txt"
    assert forwarded_payload["file_hash"] == "hash-live"
    assert forwarded_payload["document"]["file_name"] == "demo.txt"


def test_extraction_service_office_preview_status_augments_file_link(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    service = ExtractionService()

    preview_pdf = (tmp_path / "artifacts" / "preview" / "op" / "demo.pdf").resolve()
    preview_pdf.parent.mkdir(parents=True, exist_ok=True)
    preview_pdf.write_bytes(b"%PDF-1.4")

    async def _fake_get_office_preview_status(_settings, job_id: str, *, expected_tenant_id: str = "") -> dict:
        del _settings, expected_tenant_id
        return {
            "job_id": job_id,
            "status": "done",
            "artifact_path": "preview/op/demo.pdf",
            "artifact_url": "/extract/artifact/preview/op/demo.pdf",
        }

    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_extraction_artifact_runtime",
        lambda: SimpleNamespace(
            get_office_preview_status=_fake_get_office_preview_status,
            resolve_existing_artifact_path=lambda _settings, fragment: preview_pdf if fragment == "preview/op/demo.pdf" else preview_pdf,
        ),
    )
    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.register_file",
        lambda **_kwargs: {"file_id": "fa_preview"},
    )

    result = asyncio.run(service.get_office_preview_status(settings, request=None, job_id="preview_job_1", tenant_id="tenant-a"))

    assert result["artifact_file_id"] == "fa_preview"
    assert result["artifact_download_url"] == "/download/fa_preview"
    assert result["artifact_by_file_url"] == "/extract/artifact/by-file/fa_preview"
    assert result["artifact_url"] == "/extract/artifact/by-file/fa_preview"


def test_extraction_service_trace_locate_augments_artifact_file_links(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path, auth_tenant_mode="user_preferred")
    service = ExtractionService()

    trace_image = (tmp_path / "artifacts" / "trace" / "hit.png").resolve()
    trace_image.parent.mkdir(parents=True, exist_ok=True)
    trace_image.write_bytes(b"\x89PNG\r\n\x1a\n")

    register_calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_extraction_artifact_runtime",
        lambda: SimpleNamespace(
            resolve_existing_artifact_path=lambda _settings, fragment: trace_image if fragment == "trace/hit.png" else trace_image,
        ),
    )
    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.register_file",
        lambda **kwargs: register_calls.append(dict(kwargs)) or {"file_id": "fa_hit"},
    )

    payload = TraceLocateRequest.model_validate(
        {
            "document": {
                "file_name": "demo.pdf",
                "file_hash": "hash-demo",
                "track": "done",
                "cached": False,
                "result": {},
                "errors": [],
                "soft_warnings": [],
                "trace_hits": [
                    {
                        "file_name": "demo.pdf",
                        "file_hash": "hash-demo",
                        "object_type": "figure",
                        "object_id": "fig-1",
                        "ref_id": "ref-1",
                        "page": 1,
                        "snippet": "figure snippet",
                        "confidence": 0.92,
                        "locator": {},
                        "bbox": [],
                        "artifact_path": "trace/hit.png",
                        "artifact_url": "/extract/artifact/trace/hit.png",
                        "match_reason": "figure_match",
                    }
                ],
                "trace_stats": {},
                "diagnostics": {},
            },
            "top_k": 8,
        }
    )
    request = SimpleNamespace(
        headers={},
        query_params={},
        state=SimpleNamespace(authenticated_user=_fake_user()),
    )

    response = service.trace_locate(payload, settings=settings, request=request)

    assert response.hit_count == 1
    assert response.hits[0].artifact_file_id == "fa_hit"
    assert response.hits[0].artifact_download_url == "/download/fa_hit"
    assert response.hits[0].artifact_by_file_url == "/extract/artifact/by-file/fa_hit"
    assert response.hits[0].artifact_url == "/extract/artifact/by-file/fa_hit"
    assert register_calls and register_calls[0]["owner_id"] == "user-123"


def test_extraction_service_trace_locate_augments_artifact_file_links_from_artifact_url(
    monkeypatch,
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path, auth_tenant_mode="user_preferred")
    service = ExtractionService()

    trace_image = (tmp_path / "artifacts" / "trace" / "url-hit.png").resolve()
    trace_image.parent.mkdir(parents=True, exist_ok=True)
    trace_image.write_bytes(b"\x89PNG\r\n\x1a\n")

    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_extraction_artifact_runtime",
        lambda: SimpleNamespace(
            resolve_existing_artifact_path=lambda _settings, fragment: trace_image if fragment == "trace/url-hit.png" else trace_image,
        ),
    )
    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.register_file",
        lambda **_kwargs: {"file_id": "fa_url_hit"},
    )

    payload = TraceLocateRequest.model_validate(
        {
            "document": {
                "file_name": "demo.pdf",
                "file_hash": "hash-demo",
                "track": "done",
                "cached": False,
                "result": {},
                "errors": [],
                "soft_warnings": [],
                "trace_hits": [
                    {
                        "file_name": "demo.pdf",
                        "file_hash": "hash-demo",
                        "object_type": "figure",
                        "object_id": "fig-2",
                        "ref_id": "ref-2",
                        "page": 2,
                        "snippet": "figure snippet from url",
                        "confidence": 0.88,
                        "locator": {},
                        "bbox": [],
                        "artifact_url": "/extract/artifact/trace/url-hit.png?token=abc#view",
                        "match_reason": "figure_match",
                    }
                ],
                "trace_stats": {},
                "diagnostics": {},
            },
            "top_k": 8,
        }
    )
    request = SimpleNamespace(
        headers={},
        query_params={},
        state=SimpleNamespace(authenticated_user=_fake_user()),
    )

    response = service.trace_locate(payload, settings=settings, request=request)

    assert response.hit_count == 1
    assert response.hits[0].artifact_file_id == "fa_url_hit"
    assert response.hits[0].artifact_download_url == "/download/fa_url_hit"
    assert response.hits[0].artifact_by_file_url == "/extract/artifact/by-file/fa_url_hit"
    assert response.hits[0].artifact_url == "/extract/artifact/by-file/fa_url_hit"


def test_extraction_service_start_office_preview_augments_file_link(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path, auth_tenant_mode="user_preferred")
    service = ExtractionService()
    captured: dict[str, object] = {}

    preview_pdf = (tmp_path / "artifacts" / "preview" / "op" / "start.pdf").resolve()
    preview_pdf.parent.mkdir(parents=True, exist_ok=True)
    preview_pdf.write_bytes(b"%PDF-1.4")

    async def _fake_start(_settings, upload, *, tenant_id: str = "") -> dict:
        captured["upload_name"] = getattr(upload, "filename", "")
        captured["tenant_id"] = tenant_id
        return {
            "job_id": "preview_job_cached",
            "status": "completed",
            "artifact_url": "/extract/artifact/preview/op/start.pdf",
        }

    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.get_extraction_artifact_runtime",
        lambda: SimpleNamespace(
            start_office_preview=_fake_start,
            resolve_existing_artifact_path=lambda _settings, fragment: preview_pdf if fragment == "preview/op/start.pdf" else preview_pdf,
        ),
    )
    monkeypatch.setattr(
        "app.modules.module2.services.api.extraction_service.register_file",
        lambda **_kwargs: {"file_id": "fa_start_preview"},
    )

    request = SimpleNamespace(
        headers={},
        query_params={},
        state=SimpleNamespace(authenticated_user=_fake_user()),
    )
    upload = SimpleNamespace(filename="demo.docx")

    result = asyncio.run(service.start_office_preview(settings, request, upload))

    assert captured["upload_name"] == "demo.docx"
    assert captured["tenant_id"] == "user-123"
    assert result["artifact_file_id"] == "fa_start_preview"
    assert result["artifact_download_url"] == "/download/fa_start_preview"
    assert result["artifact_by_file_url"] == "/extract/artifact/by-file/fa_start_preview"
    assert result["artifact_url"] == "/extract/artifact/by-file/fa_start_preview"
