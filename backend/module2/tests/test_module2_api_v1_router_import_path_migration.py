from __future__ import annotations

from pathlib import Path


def test_module2_api_v1_router_uses_endpoint_builders_instead_of_legacy_routes_bundle() -> None:
    api_router = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "router_bundle.py"
    source = api_router.read_text(encoding="utf-8")

    assert "from .endpoints.extraction_assistant import build_router as build_extraction_assistant_router" in source
    assert "from app.routes.router_bundle import build_module2_routers" not in source

