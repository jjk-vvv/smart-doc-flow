from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.auth_tenant import normalize_tenant_mode, resolve_authenticated_tenant
from app.core.config import Settings


def _settings(*, mode: str = "user_strict", default_tenant: str = "default") -> Settings:
    return Settings(
        gateway_host="0.0.0.0",
        gateway_port=3001,
        cors_origins=("http://localhost:3000",),
        request_timeout_sec=60.0,
        stream_chunk_size=4096,
        runtime_root_dir=BACKEND_ROOT,
        config_root_dir=BACKEND_ROOT,
        data_root_dir=BACKEND_ROOT / "runtime-data",
        frontend_dist_dir=BACKEND_ROOT / "frontend" / "dist",
        module2_upstream_url="http://127.0.0.1:8010",
        module4_upstream_url="http://127.0.0.1:8100",
        auth_tenant_mode=mode,
        auth_tenant_default_id=default_tenant,
    )


def _request(*, headers: dict[str, str] | None = None, query_string: str = "") -> Request:
    normalized_headers = [
        (str(key).strip().lower().encode("latin-1"), str(value or "").encode("utf-8"))
        for key, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/extract/batch",
        "query_string": str(query_string or "").encode("utf-8"),
        "headers": normalized_headers,
    }
    return Request(scope)


def test_normalize_tenant_mode_invalid_defaults_to_user_strict() -> None:
    assert normalize_tenant_mode("unexpected-mode") == "user_strict"


def test_resolve_authenticated_tenant_user_strict_requires_authenticated_identity(monkeypatch) -> None:
    monkeypatch.delenv("AUTH_TENANT_STRICT_ALLOW_LEGACY_FALLBACK", raising=False)
    settings = _settings(mode="user_strict")
    request = _request(query_string="tenant_id=tenant-explicit")

    with pytest.raises(HTTPException) as exc_info:
        resolve_authenticated_tenant(settings, request=request, additional_headers={})

    assert exc_info.value.status_code == 401
    assert str(exc_info.value.detail) == "Authenticated tenant identity is required in user_strict mode"


def test_resolve_authenticated_tenant_user_strict_can_temporarily_allow_legacy_fallback(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_TENANT_STRICT_ALLOW_LEGACY_FALLBACK", "1")
    settings = _settings(mode="user_strict")
    request = _request(query_string="tenant_id=tenant-explicit")

    resolved = resolve_authenticated_tenant(settings, request=request, additional_headers={})

    assert resolved.tenant_id == "tenant-explicit"
    assert resolved.source == "request_legacy_fallback"


def test_resolve_authenticated_tenant_user_strict_rejects_authenticated_mismatch() -> None:
    settings = _settings(mode="user_strict")
    request = _request(
        headers={
            "x-authenticated-user-id": "tenant-auth",
            "x-tenant-id": "tenant-other",
        }
    )

    with pytest.raises(HTTPException) as exc_info:
        resolve_authenticated_tenant(settings, request=request, additional_headers={})

    assert exc_info.value.status_code == 403
    assert str(exc_info.value.detail) == "Tenant mismatch for authenticated user"


def test_resolve_authenticated_tenant_user_strict_uses_authenticated_identity() -> None:
    settings = _settings(mode="user_strict")
    request = _request(headers={"x-authenticated-tenant-id": "tenant-auth"})

    resolved = resolve_authenticated_tenant(settings, request=request, additional_headers={})

    assert resolved.tenant_id == "tenant-auth"
    assert resolved.source == "authenticated_user"
