from __future__ import annotations

from app.create_app import create_app


def test_create_app_registers_unified_fastapi_routes() -> None:
    app = create_app()
    route_paths = {route.path for route in app.routes}

    assert "/api/auth/health" in route_paths
    assert "/api/sessions" in route_paths
    assert "/api/sessions/revoke-others" in route_paths
    assert "/api/sessions/{session_id}" in route_paths
    assert "/api/chat" in route_paths
    assert "/extract/batch" in route_paths
    assert "/gateway/health" in route_paths
    assert "/module1-placeholder/info" in route_paths
    assert "/" in route_paths
