from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_schema_primitives_bundle_module = import_module("app.modules.module2.bootstrap.schema_primitives")


def test_build_module2_main_schema_primitives_bundle_exposes_stable_schema_helpers() -> None:
    bundle = main_schema_primitives_bundle_module.build_module2_main_schema_primitives_bundle()

    schema_hash_a = bundle.schema_hash({"fields": {"Invoice Total": "number"}})
    schema_hash_b = bundle.schema_hash({"fields": {"Invoice Total": "number"}})
    assert schema_hash_a == schema_hash_b

    assert bundle.schema_target_fields({"fields": {"Invoice Total": "number"}}) == {
        "Invoice Total": "number",
    }
    assert bundle.schema_target_fields({"Invoice Total": "number", "auto_infer": True}) == {
        "Invoice Total": "number",
    }

    assert bundle.schema_field_type_hint({"type": "integer"}) == "integer"
    assert bundle.schema_field_type_hint("date") == "date"

    assert bundle.coerce_field_type({"type": "int"}) == "integer"
    assert bundle.coerce_field_type("decimal") == "number"
    assert bundle.coerce_field_type("timestamp") == "date"
    assert bundle.coerce_field_type("boolean") == "boolean"
    assert bundle.coerce_field_type("unknown") == "string"

    assert bundle.sanitize_field_name("  Invoice / Total  ") == "Invoice  Total"
    assert bundle.sanitize_field_name("x") == ""
    assert bundle.schema_field_type_priority("string") == 0
    assert bundle.schema_field_type_priority("number") == 1
    assert bundle.schema_field_type_priority("integer") == 2
