from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import asyncio
import pytest
from fastapi import HTTPException

from app.core.config import Settings
from app.modules.auth.deps import AuthenticatedUser
from app.modules.extraction.service import ExtractionService


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
            "model": "gpt-5-mini",
            "base_url": "https://example.test",
            "endpoint_path": "/v1/responses",
            "tavily_configured": True,
        }
    )

    monkeypatch.setattr(
        "app.modules.extraction.service.get_assistant1_facade",
        lambda: fake_facade,
    )
    monkeypatch.setattr(
        "app.modules.extraction.service.resolve_live_module2_upstream_url",
        lambda _settings: "http://127.0.0.1:8010",
    )
    monkeypatch.setattr(
        "app.modules.extraction.service.probe_module2_upstream",
        lambda base_url, timeout_sec: {
            "ok": True,
            "base_url": base_url,
            "health_url": f"{base_url}/healthz",
            "payload": {"status": "ok"},
        },
    )
    monkeypatch.setattr(
        "app.modules.extraction.service.get_module2_sidecar_manager",
        lambda: SimpleNamespace(
            health_payload=lambda _settings: {
                "requested_mode": "auto",
                "active_mode": "external",
                "healthy": True,
                "running": False,
                "preferred_base_url": "http://127.0.0.1:8010",
            }
        ),
    )

    payload = service.health_payload(settings)

    assert payload["ok"] is True
    assert payload["assistant1"]["configured"] is True
    assert payload["assistant1"]["active_mode"] == "legacy"
    assert payload["module2_upstream"]["resolved_url"] == "http://127.0.0.1:8010"
    assert payload["module2_sidecar"]["active_mode"] == "external"
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
        "app.services.extraction_service.get_assistant1_facade",
        lambda: SimpleNamespace(
            upstream_runtime=SimpleNamespace(fetch_session_response=_fake_fetch_session_response),
        ),
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
        "app.modules.extraction.service.get_module2_execution_facade",
        lambda: SimpleNamespace(
            clear_cache=fake_clear_cache
        ),
    )
    monkeypatch.setattr(
        "app.modules.extraction.service.clear_shadow_extraction_runtime_state",
        lambda _settings, *, remove_snapshots: {
            "cleared_shadow_jobs_memory": 5,
            "cleared_shadow_pollers_memory": 6,
            "removed_shadow_snapshots": 7 if remove_snapshots else 0,
        },
    )
    monkeypatch.setattr(
        "app.modules.extraction.service.get_extraction_artifact_runtime",
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
        "app.modules.extraction.service.start_shadow_extraction_job",
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
        "app.modules.extraction.service.get_module2_execution_facade",
        lambda: SimpleNamespace(extract_batch=fake_extract_batch),
    )
    monkeypatch.setattr(
        "app.modules.extraction.service.read_uploads_for_upstream",
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
        "app.modules.extraction.service.read_uploads_for_upstream",
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
