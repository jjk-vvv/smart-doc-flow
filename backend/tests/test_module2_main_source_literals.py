from __future__ import annotations

from pathlib import Path


def test_module2_schema_pipeline_builder_keeps_utf8_chinese_literals() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "modules"
        / "module2"
        / "services"
        / "schema"
        / "schema_pipeline_builder.py"
    ).read_text(encoding="utf-8")

    # Keep a lightweight guard that multilingual fallback token dictionaries
    # remain in place after migration, without hard-coding every token variant.
    assert "_DEFAULT_AUTO_SCHEMA_GENERIC_ZH" in source
    assert "_DEFAULT_AUTO_SCHEMA_GENERIC_ZH_EXACT" in source

