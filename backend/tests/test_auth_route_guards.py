from __future__ import annotations

from types import SimpleNamespace

from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.create_app import create_app
from app.modules.auth.deps import AuthenticatedUser, require_authenticated_user
from app.modules.auth.service import get_auth_service
from app.services.extraction_service import get_extraction_service


def _fake_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id="user-123",
        name="Tester",
        email="tester@example.com",
        phone="13900000000",
        status="active",
        session_id="sess-123",
    )


def test_extract_cache_clear_requires_auth() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post("/extract/cache/clear")

    assert response.status_code == 401


def test_assistant_chat_requires_auth() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/api/chat",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 401


def test_auth_sessions_requires_auth() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/sessions")

    assert response.status_code == 401


def test_extract_batch_injects_authenticated_user_into_request_state() -> None:
    app = create_app()
    captured: dict[str, str] = {}

    class _FakeExtractionService:
        async def extract_batch(self, settings, request, uploads, schema_form, tenant_id=""):
            authenticated_user = getattr(request.state, "authenticated_user", None)
            captured["user_id"] = getattr(authenticated_user, "user_id", "")
            captured["email"] = getattr(authenticated_user, "email", "")
            captured["tenant_id"] = str(tenant_id or "")
            captured["schema_form"] = str(schema_form or "")
            return {"documents": []}

    app.dependency_overrides[require_authenticated_user] = _fake_user
    app.dependency_overrides[get_extraction_service] = lambda: _FakeExtractionService()

    client = TestClient(app)
    response = client.post(
        "/extract/batch",
        data={"schema": '{"fields":["title"]}', "tenant_id": ""},
        files={"files": ("sample.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 200
    assert captured["user_id"] == "user-123"
    assert captured["email"] == "tester@example.com"
    assert captured["tenant_id"] == ""
    assert captured["schema_form"] == '{"fields":["title"]}'


def test_extract_jobs_create_injects_authenticated_user_into_request_state() -> None:
    app = create_app()
    captured: dict[str, str] = {}

    class _FakeExtractionService:
        async def create_job(self, settings, request, uploads, schema_form, tenant_id=""):
            del settings, uploads
            authenticated_user = getattr(request.state, "authenticated_user", None)
            captured["user_id"] = getattr(authenticated_user, "user_id", "")
            captured["email"] = getattr(authenticated_user, "email", "")
            captured["tenant_id"] = str(tenant_id or "")
            captured["schema_form"] = str(schema_form or "")
            return {"job_id": "extract_job_demo123", "status": "queued", "terminal": False}

    app.dependency_overrides[require_authenticated_user] = _fake_user
    app.dependency_overrides[get_extraction_service] = lambda: _FakeExtractionService()

    client = TestClient(app)
    response = client.post(
        "/extract/jobs/create",
        data={"schema": '{"fields":["title"]}', "tenant_id": ""},
        files={"files": ("sample.txt", b"hello world", "text/plain")},
    )

    assert response.status_code == 200
    assert captured["user_id"] == "user-123"
    assert captured["email"] == "tester@example.com"
    assert captured["tenant_id"] == ""
    assert captured["schema_form"] == '{"fields":["title"]}'


def test_module4_proxy_forwards_authenticated_headers(monkeypatch) -> None:
    app = create_app()
    captured: dict[str, str] = {}

    async def _fake_proxy_module4_request(request, settings, upstream_path, *, additional_headers=None):
        captured["upstream_path"] = upstream_path
        captured.update(additional_headers or {})
        return JSONResponse({"ok": True})

    monkeypatch.setattr(
        "app.services.gateway_service.proxy_module4_request",
        _fake_proxy_module4_request,
    )
    app.dependency_overrides[require_authenticated_user] = _fake_user

    client = TestClient(app)
    response = client.get("/module4/healthz")

    assert response.status_code == 200
    assert captured["upstream_path"] == "/module4/healthz"
    assert captured["X-Authenticated-User-Id"] == "user-123"
    assert captured["X-Authenticated-User-Email"] == "tester@example.com"
    assert captured["X-Authenticated-Session-Id"] == "sess-123"


def test_module4_proxy_injects_default_tenant_header_in_compat_mode(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_TENANT_MODE", "compat_default")
    monkeypatch.setenv("AUTH_TENANT_DEFAULT_ID", "default")

    app = create_app()
    captured: dict[str, str] = {}

    async def _fake_proxy_request(
        request,
        settings,
        upstream_base_url,
        upstream_path,
        *,
        additional_headers=None,
    ):
        del request, settings, upstream_base_url, upstream_path
        captured.update(additional_headers or {})
        return JSONResponse({"ok": True})

    monkeypatch.setattr(
        "app.services.gateway_service.resolve_live_module4_upstream_url",
        lambda settings, ensure_sidecar=False: "http://127.0.0.1:8100",
    )
    monkeypatch.setattr("app.services.gateway_service.proxy_request", _fake_proxy_request)
    app.dependency_overrides[require_authenticated_user] = _fake_user

    client = TestClient(app)
    response = client.get("/module4/graph")

    assert response.status_code == 200
    assert captured["X-Tenant-Id"] == "default"
    assert captured["X-Authenticated-Tenant-Id"] == "user-123"


def test_auth_sessions_route_returns_service_payload() -> None:
    app = create_app()

    class _FakeAuthService:
        async def list_sessions(self, request, current_user):
            del request
            return {
                "sessions": [
                    {
                        "sessionId": str(current_user.session_id),
                        "current": True,
                        "ipAddress": "127.0.0.1",
                        "userAgent": "pytest",
                        "createdAt": None,
                        "lastSeenAt": None,
                        "expiresAt": None,
                        "revokedAt": None,
                        "status": "active",
                    }
                ],
                "supportsPersistentSessions": True,
            }

    app.dependency_overrides[require_authenticated_user] = _fake_user
    app.dependency_overrides[get_auth_service] = lambda: _FakeAuthService()

    client = TestClient(app)
    response = client.get("/api/sessions")

    assert response.status_code == 200
    payload = response.json()
    assert payload["supportsPersistentSessions"] is True
    assert payload["sessions"][0]["sessionId"] == "sess-123"


def test_module4_proxy_uses_authenticated_user_tenant_in_strict_mode(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_TENANT_MODE", "user_strict")
    monkeypatch.setenv("AUTH_TENANT_DEFAULT_ID", "default")

    app = create_app()
    captured: dict[str, str] = {}

    async def _fake_proxy_request(
        request,
        settings,
        upstream_base_url,
        upstream_path,
        *,
        additional_headers=None,
    ):
        del request, settings, upstream_base_url, upstream_path
        captured.update(additional_headers or {})
        return JSONResponse({"ok": True})

    monkeypatch.setattr(
        "app.services.gateway_service.resolve_live_module4_upstream_url",
        lambda settings, ensure_sidecar=False: "http://127.0.0.1:8100",
    )
    monkeypatch.setattr("app.services.gateway_service.proxy_request", _fake_proxy_request)
    app.dependency_overrides[require_authenticated_user] = _fake_user

    client = TestClient(app)
    response = client.get("/module4/graph")

    assert response.status_code == 200
    assert captured["X-Tenant-Id"] == "user-123"


def test_module4_proxy_rejects_mismatched_tenant_in_strict_mode(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_TENANT_MODE", "user_strict")

    app = create_app()
    app.dependency_overrides[require_authenticated_user] = _fake_user

    client = TestClient(app)
    response = client.get("/module4/graph?tenant_id=other-tenant")

    assert response.status_code == 403
    assert response.json()["detail"] == "Tenant mismatch for authenticated user"
