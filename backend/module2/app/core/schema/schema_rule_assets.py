from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict


APP_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = APP_ROOT / "assets"


def _asset_path(file_name: str) -> Path:
    return ASSETS_DIR / str(file_name).strip()


@lru_cache(maxsize=4)
def _load_json_asset(file_name: str) -> Dict[str, Any]:
    return json.loads(_asset_path(file_name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_schema_noise_rules() -> Dict[str, Any]:
    raw = _load_json_asset("schema_noise_rules_v1.json")
    generic_en = frozenset(str(item).strip().lower() for item in raw.get("auto_schema_generic_en", []) if str(item).strip())
    generic_zh = frozenset(str(item).strip() for item in raw.get("auto_schema_generic_zh", []) if str(item).strip())
    generic_zh_exact = frozenset(str(item).strip() for item in raw.get("auto_schema_generic_zh_exact", []) if str(item).strip())
    return {
        "version": str(raw.get("version") or "schema-noise-rules-v1"),
        "auto_schema_stopwords_en": frozenset(
            str(item).strip().lower() for item in raw.get("auto_schema_stopwords_en", []) if str(item).strip()
        ),
        "auto_schema_generic_en": generic_en,
        "auto_schema_generic_zh": generic_zh,
        "auto_schema_generic_zh_exact": generic_zh_exact,
        "auto_schema_generic_zh_unit_tokens": frozenset(
            str(item).strip() for item in raw.get("auto_schema_generic_zh_unit_tokens", []) if str(item).strip()
        ),
        "auto_schema_generic_ja_exact": frozenset(
            str(item).strip() for item in raw.get("auto_schema_generic_ja_exact", []) if str(item).strip()
        ),
        "low_value_result_generic_en": frozenset(
            set(generic_en)
            | {
                str(item).strip().lower()
                for item in raw.get("low_value_result_generic_en_extra", [])
                if str(item).strip()
            }
        ),
        "low_value_result_generic_zh": frozenset(
            set(generic_zh)
            | set(generic_zh_exact)
            | {
                str(item).strip()
                for item in raw.get("low_value_result_generic_zh_extra", [])
                if str(item).strip()
            }
        ),
        "schema_heuristic_stop_tokens": frozenset(
            str(item).strip().lower() for item in raw.get("schema_heuristic_stop_tokens", []) if str(item).strip()
        ),
    }


@lru_cache(maxsize=1)
def load_field_type_rules() -> Dict[str, Any]:
    raw = _load_json_asset("field_type_rules_v1.json")
    return {
        "version": str(raw.get("version") or "field-type-rules-v1"),
        "date_tokens": tuple(str(item).strip().lower() for item in raw.get("date_tokens", []) if str(item).strip()),
        "integer_tokens": tuple(str(item).strip().lower() for item in raw.get("integer_tokens", []) if str(item).strip()),
        "number_tokens": tuple(str(item).strip().lower() for item in raw.get("number_tokens", []) if str(item).strip()),
    }


@lru_cache(maxsize=1)
def load_schema_selection_rules() -> Dict[str, Any]:
    raw = _load_json_asset("schema_selection_rules_v1.json")
    return {
        "version": str(raw.get("version") or "schema-selection-rules-v1"),
        "rule_candidate_templates": tuple(
            str(item).strip() for item in raw.get("rule_candidate_templates", []) if str(item).strip()
        ),
        "xlsx_or_table_heavy_max_fields": int(raw.get("xlsx_or_table_heavy_max_fields", 6) or 6),
        "pdf_max_fields_env": str(raw.get("pdf_max_fields_env") or "MODULE2_AUTO_SCHEMA_PDF_MAX_FIELDS"),
        "pdf_max_fields_default": int(raw.get("pdf_max_fields_default", 8) or 8),
        "candidate_pool_multiplier": int(raw.get("candidate_pool_multiplier", 3) or 3),
        "candidate_pool_extra_cap": int(raw.get("candidate_pool_extra_cap", 10) or 10),
        "candidate_pool_max": int(raw.get("candidate_pool_max", 36) or 36),
    }


@lru_cache(maxsize=1)
def load_schema_semantic_rules() -> Dict[str, Any]:
    raw = _load_json_asset("schema_semantic_rules_v1.json")
    return {
        "version": str(raw.get("version") or "schema-semantic-rules-v1"),
        "weak_exact_en": frozenset(
            str(item).strip().lower() for item in raw.get("weak_exact_en", []) if str(item).strip()
        ),
        "weak_exact_zh": frozenset(
            str(item).strip() for item in raw.get("weak_exact_zh", []) if str(item).strip()
        ),
        "weak_contains_en": tuple(
            str(item).strip().lower() for item in raw.get("weak_contains_en", []) if str(item).strip()
        ),
        "weak_contains_zh": tuple(
            str(item).strip() for item in raw.get("weak_contains_zh", []) if str(item).strip()
        ),
        "metric_tokens_en": frozenset(
            str(item).strip().lower() for item in raw.get("metric_tokens_en", []) if str(item).strip()
        ),
        "metric_tokens_zh": frozenset(
            str(item).strip() for item in raw.get("metric_tokens_zh", []) if str(item).strip()
        ),
        "identifier_tokens_en": frozenset(
            str(item).strip().lower() for item in raw.get("identifier_tokens_en", []) if str(item).strip()
        ),
        "identifier_tokens_zh": frozenset(
            str(item).strip() for item in raw.get("identifier_tokens_zh", []) if str(item).strip()
        ),
        "time_tokens_en": frozenset(
            str(item).strip().lower() for item in raw.get("time_tokens_en", []) if str(item).strip()
        ),
        "time_tokens_zh": frozenset(
            str(item).strip() for item in raw.get("time_tokens_zh", []) if str(item).strip()
        ),
        "category_tokens_en": frozenset(
            str(item).strip().lower() for item in raw.get("category_tokens_en", []) if str(item).strip()
        ),
        "category_tokens_zh": frozenset(
            str(item).strip() for item in raw.get("category_tokens_zh", []) if str(item).strip()
        ),
        "closure_min_score": int(raw.get("closure_min_score", 8) or 8),
        "closure_min_gain": int(raw.get("closure_min_gain", 8) or 8),
        "closure_min_unique_gap": int(raw.get("closure_min_unique_gap", 3) or 3),
        "selection_min_score": int(raw.get("selection_min_score", 0) or 0),
    }


@lru_cache(maxsize=1)
def load_schema_coverage_profiles() -> Dict[str, Any]:
    raw = _load_json_asset("schema_coverage_profiles_v1.json")
    templates: Dict[str, Any] = {}
    for template_name, profile in dict(raw.get("templates") or {}).items():
        normalized_template = str(template_name or "").strip()
        if not normalized_template or not isinstance(profile, dict):
            continue
        templates[normalized_template] = {
            "critical_fields": tuple(
                str(item).strip() for item in profile.get("critical_fields", []) if str(item).strip()
            ),
            "preferred_fields": tuple(
                str(item).strip() for item in profile.get("preferred_fields", []) if str(item).strip()
            ),
            "text_target_fields": int(profile.get("text_target_fields", 0) or 0),
            "table_target_fields": int(profile.get("table_target_fields", 0) or 0),
            "freeze_rule_field_count": int(profile.get("freeze_rule_field_count", 0) or 0),
        }
    return {
        "version": str(raw.get("version") or "schema-coverage-profiles-v1"),
        "templates": templates,
    }


def schema_rule_versions() -> Dict[str, str]:
    return {
        "noise_rules": str(load_schema_noise_rules().get("version") or ""),
        "field_type_rules": str(load_field_type_rules().get("version") or ""),
        "selection_rules": str(load_schema_selection_rules().get("version") or ""),
        "semantic_rules": str(load_schema_semantic_rules().get("version") or ""),
        "coverage_profiles": str(load_schema_coverage_profiles().get("version") or ""),
    }
