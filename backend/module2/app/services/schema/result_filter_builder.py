from __future__ import annotations

"""Schema result-filter bundle builder for module2 service layer."""

from dataclasses import dataclass
import re
from typing import Any, Callable, Dict, Set, Tuple


SanitizeFieldNameFn = Callable[[Any], str]
IsLowValueFieldNameFn = Callable[[Any], bool]
ShouldPruneShadowedFieldNameFn = Callable[[str, str], bool]
ToNumberOrNoneFn = Callable[[Any], float | None]


@dataclass(frozen=True)
class Module2MainResultFilterBundle:
    normalize_semantic_text: Callable[[Any], str]
    is_low_value_result_value: Callable[[Any, Any], bool]
    filter_low_value_auto_results: Callable[[Dict[str, Any]], Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]]
    effective_quality_schema_fields: Callable[[Dict[str, Any], Dict[str, str]], Dict[str, Any]]
    prune_shadowed_auto_results: Callable[[Dict[str, Dict[str, Any]]], Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]]


def build_module2_main_result_filter_bundle(
    *,
    sanitize_field_name: SanitizeFieldNameFn,
    is_low_value_auto_schema_field_name: IsLowValueFieldNameFn,
    should_prune_shadowed_auto_field_name: ShouldPruneShadowedFieldNameFn,
    to_number_or_none: ToNumberOrNoneFn,
    auto_schema_stopwords_en: Set[str],
    low_value_result_generic_en: Set[str],
    low_value_result_generic_zh: Set[str],
) -> Module2MainResultFilterBundle:
    ratio_text_pattern = re.compile(r"^\d+(?:\.\d+)?\s*[:：]\s*\d+(?:\.\d+)?$")

    def _normalize_semantic_text(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        text = re.sub(r"[\s_:/\\\-|()\[\]{}<>]+", "", text)
        text = re.sub(r"[^\w\u4e00-\u9fff.%]+", "", text)
        return text

    def _is_low_value_result_value(field_name: Any, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return False

        text = str(value).strip()
        if not text:
            return True
        if to_number_or_none(text) is not None:
            return False
        if ratio_text_pattern.fullmatch(text):
            return False

        normalized_value = _normalize_semantic_text(text)
        normalized_field = _normalize_semantic_text(sanitize_field_name(field_name))
        if not normalized_value:
            return True
        if normalized_field and normalized_value == normalized_field:
            return True
        if normalized_value in low_value_result_generic_en or normalized_value in low_value_result_generic_zh:
            return True
        if normalized_value.startswith(("legend", "xaxis", "yaxis", "xaxislabel", "yaxislabel")):
            return True
        if normalized_value.startswith(
            (
                "\u56fe\u4f8b",
                "\u6a2a\u8f74",
                "\u7eb5\u8f74",
                "\u5750\u6807\u8f74",
            )
        ):
            return True

        alpha_tokens = [tok.lower() for tok in re.findall(r"[A-Za-z]+", normalized_value)]
        if alpha_tokens and all(tok in auto_schema_stopwords_en or tok in low_value_result_generic_en for tok in alpha_tokens):
            return True
        if len(normalized_value) <= 2 and not re.search(r"[\u4e00-\u9fff]", normalized_value):
            return True
        return False

    def _prune_shadowed_auto_results(
        results: Dict[str, Dict[str, Any]],
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
        kept = dict(results)
        removed: Dict[str, str] = {}
        ordered_keys = list(kept.keys())
        longer_keys = sorted(ordered_keys, key=lambda item: (-len(item), item))
        normalized_values = {
            key: _normalize_semantic_text(entity.get("value"))
            for key, entity in kept.items()
            if isinstance(entity, dict)
        }
        for short_key in ordered_keys:
            if short_key not in kept:
                continue
            short_value = normalized_values.get(short_key, "")
            if not short_value:
                continue
            for long_key in longer_keys:
                if long_key not in kept or long_key == short_key:
                    continue
                if not should_prune_shadowed_auto_field_name(short_key, long_key):
                    continue
                long_value = normalized_values.get(long_key, "")
                if not long_value or long_value != short_value:
                    continue
                removed[short_key] = f"shadowed_by_more_specific_field:{long_key}"
                kept.pop(short_key, None)
                break
        return kept, removed

    def _filter_low_value_auto_results(
        results: Dict[str, Any],
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
        filtered: Dict[str, Dict[str, Any]] = {}
        removed: Dict[str, str] = {}
        for field_name, entity in results.items():
            key = sanitize_field_name(field_name)
            if not key:
                removed[str(field_name)] = "empty_field_name"
                continue
            if not isinstance(entity, dict):
                removed[key] = "invalid_entity"
                continue
            if is_low_value_auto_schema_field_name(key):
                removed[key] = "low_value_field_name"
                continue
            if _is_low_value_result_value(key, entity.get("value")):
                removed[key] = "low_value_result_value"
                continue
            filtered[str(field_name)] = entity
        pruned, shadowed_removed = _prune_shadowed_auto_results(filtered)
        removed.update(shadowed_removed)
        return pruned, removed

    def _effective_quality_schema_fields(
        schema_fields: Dict[str, Any],
        removed_auto_results: Dict[str, str],
    ) -> Dict[str, Any]:
        if not schema_fields:
            return {}
        if not removed_auto_results:
            return dict(schema_fields)

        adjusted: Dict[str, Any] = {}
        for field_name, field_type in schema_fields.items():
            sanitized_name = sanitize_field_name(field_name)
            removal_reason = removed_auto_results.get(sanitized_name) or removed_auto_results.get(str(field_name))
            if removal_reason in {"empty_field_name", "low_value_field_name"}:
                continue
            if str(removal_reason or "").startswith("shadowed_by_more_specific_field:"):
                continue
            adjusted[str(field_name)] = field_type
        return adjusted

    return Module2MainResultFilterBundle(
        normalize_semantic_text=_normalize_semantic_text,
        is_low_value_result_value=_is_low_value_result_value,
        filter_low_value_auto_results=_filter_low_value_auto_results,
        effective_quality_schema_fields=_effective_quality_schema_fields,
        prune_shadowed_auto_results=_prune_shadowed_auto_results,
    )
