from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_schema_semantics_bundle_module = import_module("app.modules.module2.bootstrap.schema_semantics")


def _build_bundle():
    rules = {
        "metric_tokens_en": ("amount", "total", "score"),
        "metric_tokens_zh": ("金额", "总额"),
        "identifier_tokens_en": ("id", "code"),
        "identifier_tokens_zh": ("编号",),
        "time_tokens_en": ("date", "year"),
        "time_tokens_zh": ("日期",),
        "category_tokens_en": ("type", "category"),
        "category_tokens_zh": ("类别",),
        "weak_exact_en": {"chart", "figure", "table"},
        "weak_exact_zh": {"图表"},
        "weak_contains_en": ("chart", "figure", "table"),
        "weak_contains_zh": ("图", "表"),
    }
    return main_schema_semantics_bundle_module.build_module2_main_schema_semantics_bundle(
        sanitize_field_name=lambda value: str(value or "").strip().lower().replace(" ", "_"),
        field_name_word_tokens=lambda value: [
            token for token in str(value or "").strip().lower().replace("_", " ").split() if token
        ],
        coerce_field_type=lambda value: str(value or "string").strip().lower(),
        schema_semantic_rules=rules,
        looks_like_schema_figure_title=lambda candidate: str(candidate).strip().lower().startswith("figure"),
        looks_like_schema_sentence_fragment=lambda candidate: "shows" in str(candidate).strip().lower(),
    )


def test_build_module2_main_schema_semantics_bundle_detects_signals_and_weak_labels() -> None:
    bundle = _build_bundle()

    flags = bundle.semantic_signal_flags("invoice_total_amount")
    assert flags["metric"] is True
    assert flags["identifier"] is False
    assert flags["visual"] is False

    assert bundle.is_semantically_weak_field_label("chart") is True
    assert bundle.is_semantically_weak_field_label("invoice_total_amount") is False


def test_module2_main_schema_semantics_bundle_scores_strong_labels_above_visual_noise() -> None:
    bundle = _build_bundle()

    strong_score = bundle.schema_semantic_label_strength(
        "invoice_total_amount",
        "number",
        {
            "unit_norm": "usd",
            "dimensions": {"region": {"label": "APAC"}},
            "normalization_rule_id": "finance.amount",
        },
    )
    weak_score = bundle.schema_semantic_label_strength(
        "figure shows trend",
        "string",
        {},
    )

    assert strong_score > weak_score

    alias_keys = bundle.semantic_closure_fragment_alias_keys(
        {
            "dimensions": {"region": {"label": "APAC", "raw": "Asia Pacific", "value": "APAC"}},
            "unit_raw": "USD",
            "unit_norm": "usd",
        }
    )
    assert alias_keys == {"apac", "asia_pacific", "usd"}
