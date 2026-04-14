from __future__ import annotations

from pathlib import Path


def test_module2_native_backend_shell_removed() -> None:
    native_backend_dir = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module2"
        / "native_backend"
    )
    assert not native_backend_dir.exists()


def test_module2_router_uses_canonical_api_endpoints() -> None:
    router_source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module2"
        / "api"
        / "router.py"
    ).read_text(encoding="utf-8")
    assert "from .endpoints.assistant import router as assistant_router" in router_source
    assert "from .endpoints.extraction import router as extraction_router" in router_source
