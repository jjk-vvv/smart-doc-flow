from __future__ import annotations

from pathlib import Path


def test_module2_schema_pipeline_builder_keeps_utf8_chinese_literals() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "module2"
        / "app"
        / "services"
        / "schema"
        / "schema_pipeline_builder.py"
    ).read_text(encoding="utf-8")

    for token in ("日期", "时间", "年份", "年月", "季度", "时点"):
        assert token in source
