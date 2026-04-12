from __future__ import annotations

from pathlib import Path


def test_module4_api_v1_router_uses_endpoint_builder_instead_of_legacy_router() -> None:
    api_router = Path(__file__).resolve().parents[1] / "app" / "api" / "v1" / "router.py"
    source = api_router.read_text(encoding="utf-8")

    assert "from .endpoints.graph import build_router as build_graph_endpoint_router" in source
    assert "from .endpoints.module4 import build_router as build_module4_endpoint_router" not in source
    assert "from app.router import build_module4_router" not in source
