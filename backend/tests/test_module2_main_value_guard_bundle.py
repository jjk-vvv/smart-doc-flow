from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_value_guard_bundle_module = import_module("module2.app.bootstrap.quick_extract")


def test_build_module2_main_value_guard_bundle_identifies_low_value_quick_fallback_values() -> None:
    bundle = main_value_guard_bundle_module.build_module2_main_value_guard_bundle(
        to_number_or_none=lambda value: float(value) if str(value).strip().isdigit() else None,
        auto_schema_stopwords_en={"the", "and", "of"},
    )

    assert bundle.is_low_value_quick_fallback_value(None) is True
    assert bundle.is_low_value_quick_fallback_value("") is True
    assert bundle.is_low_value_quick_fallback_value("42") is False
    assert bundle.is_low_value_quick_fallback_value("the") is True
    assert bundle.is_low_value_quick_fallback_value("Figure 1") is True
    assert bundle.is_low_value_quick_fallback_value("Revenue") is False
