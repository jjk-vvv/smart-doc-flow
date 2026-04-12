from __future__ import annotations

from pathlib import Path


def test_module2_foundation_builder_prefers_composition_http_runtime_bundle() -> None:
    source_path = Path(__file__).resolve().parents[1] / "app" / "services" / "extraction" / "foundation_builder.py"
    source = source_path.read_text(encoding="utf-8")

    assert "from ...composition.http_runtime_bundle import" in source
    assert "from ...runtime.http_runtime_bundle import" not in source


def test_module2_entry_builder_prefers_composition_app_callback_bundle() -> None:
    source_path = Path(__file__).resolve().parents[1] / "app" / "services" / "extraction" / "entry_builder.py"
    source = source_path.read_text(encoding="utf-8")

    assert "from ...composition.app_callback_bundle import" in source
    assert "from ...runtime.app_callback_bundle import" not in source

