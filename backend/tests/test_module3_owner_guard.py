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


fusion_routes = import_module("app.modules.module3.api.endpoints.fusion")


def _build_request(*, headers: dict[str, str] | None = None, query_string: str = "") -> Request:
    normalized_headers = [
        (str(key).strip().lower().encode("latin-1"), str(value or "").encode("utf-8"))
        for key, value in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/module3/run",
        "query_string": str(query_string or "").encode("utf-8"),
        "headers": normalized_headers,
    }
    return Request(scope)


def test_module3_owner_guard_rejects_explicit_owner_mismatch(monkeypatch) -> None:
    monkeypatch.setenv("MODULE3_OWNER_MODE", "strict_required")
    request = _build_request(headers={"x-authenticated-user-id": "tenant-auth"})

    with pytest.raises(HTTPException) as exc_info:
        fusion_routes._resolve_request_owner_id(request, explicit_owner_id="tenant-other")

    assert exc_info.value.status_code == 403
    assert str(exc_info.value.detail) == "owner mismatch for authenticated request"


def test_module3_owner_guard_rejects_query_owner_mismatch(monkeypatch) -> None:
    monkeypatch.setenv("MODULE3_OWNER_MODE", "strict_required")
    request = _build_request(
        headers={"x-authenticated-user-id": "tenant-auth"},
        query_string="owner_id=tenant-other",
    )

    with pytest.raises(HTTPException) as exc_info:
        fusion_routes._resolve_request_owner_id(request)

    assert exc_info.value.status_code == 403
    assert str(exc_info.value.detail) == "owner mismatch for authenticated request"


def test_module3_owner_guard_keeps_authenticated_owner(monkeypatch) -> None:
    monkeypatch.setenv("MODULE3_OWNER_MODE", "strict_required")
    request = _build_request(headers={"x-authenticated-user-id": "tenant-auth"})

    resolved = fusion_routes._resolve_request_owner_id(request, explicit_owner_id=None)

    assert resolved == "tenant-auth"


def test_module3_owner_guard_strict_mode_requires_authenticated_identity(monkeypatch) -> None:
    monkeypatch.setenv("MODULE3_OWNER_MODE", "strict_required")
    monkeypatch.delenv("MODULE3_OWNER_STRICT_ALLOW_LEGACY_IDENTITY", raising=False)
    request = _build_request()

    with pytest.raises(HTTPException) as exc_info:
        fusion_routes._resolve_request_owner_id(request, explicit_owner_id="tenant-explicit")

    assert exc_info.value.status_code == 401
    assert str(exc_info.value.detail) == "authenticated owner headers required in strict mode"


def test_module3_owner_guard_strict_mode_can_temporarily_allow_legacy_identity(monkeypatch) -> None:
    monkeypatch.setenv("MODULE3_OWNER_MODE", "strict_required")
    monkeypatch.setenv("MODULE3_OWNER_STRICT_ALLOW_LEGACY_IDENTITY", "1")
    request = _build_request(query_string="owner_id=tenant-from-query")

    resolved = fusion_routes._resolve_request_owner_id(request, explicit_owner_id=None)

    assert resolved == "tenant-from-query"
