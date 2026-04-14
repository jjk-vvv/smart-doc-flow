from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

import pytest
from fastapi import HTTPException


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_schema_request_bundle_module = import_module("app.modules.module2.bootstrap.schema_primitives")


def _build_bundle():
    return main_schema_request_bundle_module.build_module2_main_schema_request_bundle(
        schema_target_fields=lambda schema: schema.get("fields", {}) if isinstance(schema, dict) else {},
        normalize_schema_fields=lambda fields, max_fields: {
            str(name).strip().lower().replace(" ", "_"): str(type_hint).strip().lower()
            for idx, (name, type_hint) in enumerate(fields.items())
            if idx < max_fields
        },
    )


def test_build_module2_main_schema_request_bundle_repairs_mojibake_and_scores_payloads() -> None:
    bundle = _build_bundle()

    assert bundle.repair_latin1_utf8_mojibake("cafÃ©") == "café"
    assert bundle.schema_payload_score(
        {"fields": {"Invoice Total": "number", "Date": "date"}}
    ) == (2, 0, 2)


def test_module2_main_schema_request_bundle_parses_valid_schema_object() -> None:
    bundle = _build_bundle()

    parsed = bundle.parse_schema_form_json('{"fields": {"Invoice Total": "number", "Date": "date"}}')

    assert parsed == {"fields": {"Invoice Total": "number", "Date": "date"}}


def test_module2_main_schema_request_bundle_rejects_non_object_and_invalid_json() -> None:
    bundle = _build_bundle()

    with pytest.raises(HTTPException) as non_object_exc:
        bundle.parse_schema_form_json('["bad"]')
    assert non_object_exc.value.status_code == 400
    assert "JSON object" in str(non_object_exc.value.detail)

    with pytest.raises(HTTPException) as invalid_exc:
        bundle.parse_schema_form_json("{bad json")
    assert invalid_exc.value.status_code == 400
    assert "Invalid schema JSON" in str(invalid_exc.value.detail)
