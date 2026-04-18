from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.auth_deps import AuthenticatedUser, require_authenticated_user
from app.factory import create_app
from app.modules.module2.services.api.extraction_service import get_extraction_service
from app.services.auth_service import get_auth_service


def _fake_user() -> AuthenticatedUser:
    return AuthenticatedUser(
        user_id="user-123",
        name="Tester",
        email="tester@example.com",
        phone="13900000000",
        status="active",
        session_id="sess-123",
    )


class _FakeModule4AuthService:
    def __init__(self, payload: dict[str, str] | None = None) -> None:
        self.payload = dict(payload or {})

    async def authenticate_request(self, request):
        del request
        return dict(self.payload)


def test_extract_cache_clear_requires_auth() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post("/extract/cache/clear")

    assert response.status_code == 401


def test_assistant_chat_requires_auth() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/api/platform-assistant/chat",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 401


def test_platform_assistant_diagnostics_requires_auth() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/platform-assistant/diagnostics")

    assert response.status_code == 401


def test_auth_sessions_requires_auth() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/api/sessions")

    assert response.status_code == 401


def test_module1_convert_requires_auth() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/module1/convert/docx-to-pdf",
        files={"file": ("sample.docx", b"fake-docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert response.status_code == 401


def test_module1_save_requires_auth() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/module1/save-edited-document",
        data={"content": "updated"},
        files={"file": ("sample.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 401


def test_module1_apply_modifications_requires_auth() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/module1/apply-modifications",
        data={"modifications": "[]", "instruction": "replace title"},
        files={"file": ("sample.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 401


def test_module1_stream_requires_auth() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/module1/operate-stream",
        data={"instruction": "analyze this file"},
        files={"file": ("sample.txt", b"hello", "text/plain")},
    )

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


def test_module4_graph_uses_authenticated_user_tenant(monkeypatch) -> None:
    app = create_app()
    captured: dict[str, str] = {}

    async def _fake_graph_response_service(
        storage,
        helpers,
        tenant_id,
        node_types,
        relation_types,
        limit_nodes,
        limit_edges,
    ):
        del storage, helpers, node_types, relation_types, limit_nodes, limit_edges
        captured["tenant_id"] = tenant_id
        return {"nodes": [], "edges": [], "stats": {}}

    monkeypatch.setattr(
        "app.modules.module4.api.v1.endpoints.module4.graph_response_service",
        _fake_graph_response_service,
    )
    app.dependency_overrides[get_auth_service] = lambda: _FakeModule4AuthService({})

    client = TestClient(app)
    response = client.get(
        "/module4/graph",
        headers={
            "x-authenticated-user-id": "user-123",
            "x-authenticated-tenant-id": "user-123",
        },
    )

    assert response.status_code == 200
    assert captured["tenant_id"] == "user-123"


def test_module4_graph_uses_default_tenant_in_compat_mode_without_authenticated_identity(monkeypatch) -> None:
    monkeypatch.setenv("MODULE4_TENANT_GUARD_MODE", "compat_default")
    monkeypatch.setenv("MODULE4_DEFAULT_TENANT", "default")

    app = create_app()
    captured: dict[str, str] = {}

    async def _fake_graph_response_service(
        storage,
        helpers,
        tenant_id,
        node_types,
        relation_types,
        limit_nodes,
        limit_edges,
    ):
        del storage, helpers, node_types, relation_types, limit_nodes, limit_edges
        captured["tenant_id"] = tenant_id
        return {"nodes": [], "edges": [], "stats": {}}

    monkeypatch.setattr(
        "app.modules.module4.api.v1.endpoints.module4.graph_response_service",
        _fake_graph_response_service,
    )
    app.dependency_overrides[get_auth_service] = lambda: _FakeModule4AuthService({})

    client = TestClient(app)
    response = client.get("/module4/graph")

    assert response.status_code == 200
    assert captured["tenant_id"] == "default"


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


def test_module4_graph_rejects_mismatched_tenant_in_authenticated_request(monkeypatch) -> None:
    monkeypatch.setenv("MODULE4_TENANT_GUARD_MODE", "authenticated_required")

    app = create_app()
    app.dependency_overrides[get_auth_service] = lambda: _FakeModule4AuthService({})

    client = TestClient(app)
    response = client.get(
        "/module4/graph?tenant_id=other-tenant",
        headers={
            "x-authenticated-user-id": "user-123",
            "x-authenticated-tenant-id": "user-123",
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "tenant mismatch for authenticated request"
