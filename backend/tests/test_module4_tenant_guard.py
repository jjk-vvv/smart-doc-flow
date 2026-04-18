from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


module4_runtime = import_module("app.modules.module4.core.app_runtime")


def _build_request(*, headers: dict[str, str] | None = None) -> Request:
    normalized_headers = [
        (str(key).strip().lower().encode("latin-1"), str(value or "").encode("utf-8"))
        for key, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/module4/graph",
        "headers": normalized_headers,
    }
    return Request(scope)


@pytest.mark.parametrize("runtime_module", [module4_runtime])
def test_module4_tenant_guard_strict_mode_requires_authenticated_headers(monkeypatch, runtime_module) -> None:
    monkeypatch.setenv("MODULE4_TENANT_GUARD_MODE", "authenticated_required")
    monkeypatch.setenv("MODULE4_DEFAULT_TENANT", "default")

    with pytest.raises(HTTPException) as exc_info:
        runtime_module.tenant_from_request(_build_request(), "")

    assert exc_info.value.status_code == 401
    assert str(exc_info.value.detail) == "authenticated tenant headers required"


@pytest.mark.parametrize("runtime_module", [module4_runtime])
def test_module4_tenant_guard_strict_mode_accepts_authenticated_identity(monkeypatch, runtime_module) -> None:
    monkeypatch.setenv("MODULE4_TENANT_GUARD_MODE", "strict")

    request = _build_request(headers={"x-authenticated-user-id": "user-tenant-001"})
    resolved = runtime_module.tenant_from_request(request, "")

    assert resolved == "user-tenant-001"


@pytest.mark.parametrize("runtime_module", [module4_runtime])
def test_module4_tenant_guard_compat_mode_keeps_legacy_fallback(monkeypatch, runtime_module) -> None:
    monkeypatch.setenv("MODULE4_TENANT_GUARD_MODE", "compat_default")
    monkeypatch.setenv("MODULE4_DEFAULT_TENANT", "default-tenant")

    by_candidate = runtime_module.tenant_from_request(_build_request(), "candidate-tenant")
    by_header = runtime_module.tenant_from_request(_build_request(headers={"x-tenant-id": "header-tenant"}), "")
    by_default = runtime_module.tenant_from_request(_build_request(), "")

    assert by_candidate == "candidate-tenant"
    assert by_header == "header-tenant"
    assert by_default == "default-tenant"


@pytest.mark.parametrize("runtime_module", [module4_runtime])
def test_module4_tenant_guard_default_mode_is_authenticated_required(monkeypatch, runtime_module) -> None:
    monkeypatch.delenv("MODULE4_TENANT_GUARD_MODE", raising=False)
    monkeypatch.setenv("MODULE4_DEFAULT_TENANT", "default")

    with pytest.raises(HTTPException) as exc_info:
        runtime_module.tenant_from_request(_build_request(), "")

    assert exc_info.value.status_code == 401
    assert str(exc_info.value.detail) == "authenticated tenant headers required"


@pytest.mark.parametrize("runtime_module", [module4_runtime])
def test_module4_internal_token_guard_off_mode_is_compatible(monkeypatch, runtime_module) -> None:
    monkeypatch.delenv("MODULE4_INTERNAL_TOKEN_MODE", raising=False)
    monkeypatch.delenv("MODULE4_INTERNAL_TOKEN", raising=False)

    runtime_module.validate_internal_request(_build_request())


@pytest.mark.parametrize("runtime_module", [module4_runtime])
def test_module4_internal_token_guard_required_mode_rejects_missing_token(monkeypatch, runtime_module) -> None:
    monkeypatch.setenv("MODULE4_INTERNAL_TOKEN_MODE", "required")
    monkeypatch.setenv("MODULE4_INTERNAL_TOKEN", "internal-secret")

    with pytest.raises(HTTPException) as exc_info:
        runtime_module.validate_internal_request(_build_request())

    assert exc_info.value.status_code == 401
    assert str(exc_info.value.detail) == "invalid module4 internal token"


@pytest.mark.parametrize("runtime_module", [module4_runtime])
def test_module4_internal_token_guard_required_mode_accepts_matching_token(monkeypatch, runtime_module) -> None:
    monkeypatch.setenv("MODULE4_INTERNAL_TOKEN_MODE", "required")
    monkeypatch.setenv("MODULE4_INTERNAL_TOKEN", "internal-secret")

    runtime_module.validate_internal_request(
        _build_request(headers={"x-module4-internal-token": "internal-secret"})
    )
