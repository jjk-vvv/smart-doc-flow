from __future__ import annotations

from pathlib import Path


def test_module4_native_router_shim_is_removed() -> None:
    router_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module4"
        / "router.py"
    )
    assert not router_path.exists()


def test_module4_native_backend_shell_removed() -> None:
    native_backend_dir = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module4"
        / "native_backend"
    )
    assert not native_backend_dir.exists()
