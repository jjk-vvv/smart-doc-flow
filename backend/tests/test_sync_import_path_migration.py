from __future__ import annotations

import re
from pathlib import Path


def test_module2_runtime_main_bundle_shims_no_longer_import_bootstrap_directly() -> None:
    runtime_dir = Path(__file__).resolve().parents[1] / "app" / "modules" / "module2" / "runtime"
    assert list(runtime_dir.glob("main*_bundle.py")) == []


def test_module2_api_v1_router_bundle_prefers_sync_endpoint_name() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module2"
        / "api"
        / "v1"
        / "router_bundle.py"
    ).read_text(encoding="utf-8")

    assert "from .endpoints.sync import build_router as build_sync_router" in source
    assert "from .endpoints.module4_sync import build_router as build_module4_sync_router" not in source


def test_module2_runtime_sync_callback_compat_module_is_removed() -> None:
    compat_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module2"
        / "runtime"
        / "module4_sync_callback_bundle.py"
    )
    assert not compat_path.exists()


def test_module2_endpoint_sync_compat_module_is_removed() -> None:
    compat_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module2"
        / "api"
        / "v1"
        / "endpoints"
        / "module4_sync.py"
    )
    assert not compat_path.exists()


def test_module2_bootstrap_non_builder_surfaces_prefer_canonical_layers_directly() -> None:
    bootstrap_dir = Path(__file__).resolve().parents[1] / "app" / "modules" / "module2" / "bootstrap"
    allowed_special_import = "from ..composition.foundation import ("
    for file_path in sorted(bootstrap_dir.glob("*.py")):
        if file_path.name.endswith("_builder.py") or file_path.name == "__init__.py":
            continue
        source = file_path.read_text(encoding="utf-8")
        if file_path.name == "foundation.py":
            assert allowed_special_import in source
            continue
        assert "from ..services." in source
        assert re.search(r"from \.[^.]", source) is None

