from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_schema_timeout_bundle_module = import_module("app.modules.module2.bootstrap.schema_primitives")


def _build_bundle():
    env = {
        "MODULE2_WORD_DYNAMIC_EXTRACT_TRIGGER_SCORE": "10.0",
        "MODULE2_WORD_DYNAMIC_EXTRACT_TIMEOUT_MAX_SEC": "420",
        "MODULE2_WORD_DYNAMIC_EXTRACT_BONUS_PER_SCORE": "6.0",
    }
    return main_schema_timeout_bundle_module.build_module2_main_schema_timeout_bundle(
        getenv=lambda key, default="": env.get(key, default),
        is_word_file=lambda file_name: str(file_name).lower().endswith(".docx"),
        schema_context_clean_text=lambda value: " ".join(str(value or "").split()),
        count_table_cells=lambda tables: sum(len(table.get("cells", [])) for table in tables if isinstance(table, dict)),
        count_figure_dataframe_cells=lambda figures: sum(
            int(figure.get("dataframe_cells", 0)) for figure in figures if isinstance(figure, dict)
        ),
    )


def test_build_module2_main_schema_timeout_bundle_returns_base_timeout_for_non_word_file() -> None:
    bundle = _build_bundle()

    timeout_sec, meta = bundle.resolve_dynamic_extract_timeout_sec(
        file_name="report.pdf",
        extract_timeout_sec=120.0,
        markdown="hello world",
        schema_fields={"invoice_total": "number"},
        table_blocks=[],
        figure_blocks=[],
    )

    assert timeout_sec == 120.0
    assert meta == {
        "applied": False,
        "reason": "not_word_file",
        "resolved_timeout_sec": 120.0,
    }


def test_module2_main_schema_timeout_bundle_keeps_base_timeout_when_below_trigger() -> None:
    bundle = _build_bundle()

    timeout_sec, meta = bundle.resolve_dynamic_extract_timeout_sec(
        file_name="report.docx",
        extract_timeout_sec=90.0,
        markdown="short text",
        schema_fields={"invoice_total": "number"},
        table_blocks=[],
        figure_blocks=[],
    )

    assert timeout_sec == 90.0
    assert meta["applied"] is False
    assert meta["reason"] == "below_trigger"
    assert meta["resolved_timeout_sec"] == 90.0


def test_module2_main_schema_timeout_bundle_scales_timeout_for_complex_word_file() -> None:
    bundle = _build_bundle()

    timeout_sec, meta = bundle.resolve_dynamic_extract_timeout_sec(
        file_name="report.docx",
        extract_timeout_sec=90.0,
        markdown=("complex text " * 1500).strip(),
        schema_fields={f"field_{index}": "string" for index in range(12)},
        table_blocks=[{"cells": list(range(300))} for _ in range(3)],
        figure_blocks=[{"dataframe_cells": 240} for _ in range(2)],
    )

    assert timeout_sec > 90.0
    assert timeout_sec <= 420.0
    assert meta["applied"] is True
    assert meta["reason"] == "word_complexity_scale"
    assert meta["resolved_timeout_sec"] == round(timeout_sec, 3)
