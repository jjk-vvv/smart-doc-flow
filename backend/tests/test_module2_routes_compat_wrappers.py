from __future__ import annotations

from pathlib import Path


def test_module2_legacy_routes_shell_removed() -> None:
    routes_dir = Path(__file__).resolve().parents[1] / "app" / "modules" / "module2" / "routes"
    assert not routes_dir.exists()


def test_module2_canonical_endpoints_exist_after_routes_shell_removal() -> None:
    endpoints_dir = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module2"
        / "api"
        / "v1"
        / "endpoints"
    )
    for name in (
        "extraction_request.py",
        "extraction_support.py",
        "extraction_assistant.py",
        "sync.py",
    ):
        assert (endpoints_dir / name).exists()
