from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_schema_context_bundle_module = import_module("module2.app.bootstrap.schema_context")


def _build_bundle():
    return main_schema_context_bundle_module.build_module2_main_schema_context_bundle(
        sanitize_field_name=lambda value: str(value or "").strip().lower().replace(" ", "_"),
        schema_figure_title_tokens=("示意图", "趋势图"),
        schema_sentence_cue_tokens_zh=("说明", "显示"),
        schema_sentence_cue_tokens_en=("shows", "indicates"),
    )


def test_build_module2_main_schema_context_bundle_cleans_text_and_detects_titles() -> None:
    bundle = _build_bundle()

    assert bundle.schema_context_clean_text("<b>Hello</b>\n world ") == "Hello world"
    assert bundle.looks_like_schema_figure_title("Figure 1 Revenue Trend") is True
    assert bundle.looks_like_schema_figure_title("示意图收入走势") is True
    assert bundle.looks_like_schema_figure_title("invoice_total_amount") is False
    assert bundle.looks_like_schema_sentence_fragment("chart shows monthly growth") is True
    assert bundle.looks_like_schema_sentence_fragment("报表显示销售增长") is True
    assert bundle.looks_like_schema_sentence_fragment("invoice_total_amount") is False


def test_module2_main_schema_context_bundle_collects_figure_texts_and_extracts_schema_context() -> None:
    bundle = _build_bundle()

    figure_texts = bundle.schema_context_texts_from_figures(
        [
            {
                "caption": "<p>Revenue by Region</p>",
                "key_points": ["North America leads", "EMEA follows"],
                "dataframe": {
                    "headers": ["Region", "Revenue"],
                    "rows": [["North America", "120"], ["EMEA", "110"]],
                },
            }
        ]
    )

    assert figure_texts == [
        "Revenue by Region",
        "North America leads",
        "EMEA follows",
        "Region | Revenue",
        "North America | EMEA",
    ]

    context = bundle.extract_text_for_schema(
        "Main <b>document</b> body",
        table_blocks=[
            {"caption": "Summary Table", "headers": ["Customer", "Amount"]},
        ],
        figure_blocks=[
            {
                "caption": "Revenue by Region",
                "dataframe": {
                    "headers": ["Region", "Revenue"],
                    "rows": [["North America", "120"]],
                },
            }
        ],
        max_chars=500,
    )

    assert "Main document body" in context
    assert "Summary Table" in context
    assert "Customer | Amount" in context
    assert "Revenue by Region" in context
    assert "Region | Revenue" in context
    assert "表格语义" in context
    assert "图表语义" in context
    assert len(context) <= 500
