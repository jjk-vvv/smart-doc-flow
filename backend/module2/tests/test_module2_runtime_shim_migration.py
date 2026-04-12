from __future__ import annotations

from pathlib import Path


def test_module2_runtime_http_runtime_bundle_is_shim() -> None:
    source_path = Path(__file__).resolve().parents[1] / "app" / "runtime" / "http_runtime_bundle.py"
    source = source_path.read_text(encoding="utf-8")
    assert "from ..composition.http_runtime_bundle import *" in source


def test_module2_runtime_app_callback_bundle_is_shim() -> None:
    source_path = Path(__file__).resolve().parents[1] / "app" / "runtime" / "app_callback_bundle.py"
    source = source_path.read_text(encoding="utf-8")
    assert "from ..composition.app_callback_bundle import *" in source


def test_module2_runtime_cache_clear_is_shim() -> None:
    source_path = Path(__file__).resolve().parents[1] / "app" / "runtime" / "cache_clear.py"
    source = source_path.read_text(encoding="utf-8")
    assert "from ..composition.cache_clear import *" in source

