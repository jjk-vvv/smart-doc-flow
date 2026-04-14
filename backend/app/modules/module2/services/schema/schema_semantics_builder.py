from __future__ import annotations

"""Schema semantics bundle builder for module2 service layer."""

from dataclasses import dataclass
import re
from typing import Any, Callable, Dict, Set, Tuple


SanitizeFieldNameFn = Callable[[Any], str]
FieldNameWordTokensFn = Callable[[Any], list[str]]
CoerceFieldTypeFn = Callable[[Any], str]
LooksLikeTitleFn = Callable[[str], bool]
LooksLikeSentenceFn = Callable[[str], bool]


@dataclass(frozen=True)
class Module2MainSchemaSemanticsBundle:
    semantic_contains_exact_token: Callable[..., bool]
    semantic_contains_fragment: Callable[..., bool]
    semantic_signal_flags: Callable[[str], Dict[str, bool]]
    is_semantically_weak_field_label: Callable[[str], bool]
    schema_semantic_label_strength: Callable[[str, Any, Dict[str, Any]], int]
    semantic_closure_fragment_alias_keys: Callable[[Dict[str, Any]], set[str]]


def build_module2_main_schema_semantics_bundle(
    *,
    sanitize_field_name: SanitizeFieldNameFn,
    field_name_word_tokens: FieldNameWordTokensFn,
    coerce_field_type: CoerceFieldTypeFn,
    schema_semantic_rules: Dict[str, Any],
    looks_like_schema_figure_title: LooksLikeTitleFn,
    looks_like_schema_sentence_fragment: LooksLikeSentenceFn,
) -> Module2MainSchemaSemanticsBundle:
    def _semantic_contains_exact_token(
        label: str,
        *,
        en_tokens: Set[str],
        zh_tokens: Set[str],
    ) -> bool:
        key = sanitize_field_name(label)
        if not key:
            return False
        return key.lower() in en_tokens or key in zh_tokens

    def _semantic_contains_fragment(
        label: str,
        *,
        en_tokens: Tuple[str, ...],
        zh_tokens: Tuple[str, ...],
    ) -> bool:
        key = sanitize_field_name(label)
        if not key:
            return False
        lowered = key.lower()
        return any(token in lowered for token in en_tokens) or any(token in key for token in zh_tokens)

    def _semantic_signal_flags(label: str) -> Dict[str, bool]:
        key = sanitize_field_name(label)
        if not key:
            return {
                "metric": False,
                "identifier": False,
                "time": False,
                "category": False,
                "visual": False,
            }
        lowered = key.lower()
        rules = schema_semantic_rules
        return {
            "metric": any(token in lowered for token in rules["metric_tokens_en"])
            or any(token in key for token in rules["metric_tokens_zh"]),
            "identifier": any(token in lowered for token in rules["identifier_tokens_en"])
            or any(token in key for token in rules["identifier_tokens_zh"]),
            "time": any(token in lowered for token in rules["time_tokens_en"])
            or any(token in key for token in rules["time_tokens_zh"]),
            "category": any(token in lowered for token in rules["category_tokens_en"])
            or any(token in key for token in rules["category_tokens_zh"]),
            "visual": _semantic_contains_fragment(
                key,
                en_tokens=rules["weak_contains_en"],
                zh_tokens=rules["weak_contains_zh"],
            ),
        }

    def _is_semantically_weak_field_label(label: str) -> bool:
        key = sanitize_field_name(label)
        if not key:
            return True
        rules = schema_semantic_rules
        if _semantic_contains_exact_token(
            key,
            en_tokens=rules["weak_exact_en"],
            zh_tokens=rules["weak_exact_zh"],
        ):
            return True
        if _semantic_contains_fragment(
            key,
            en_tokens=rules["weak_contains_en"],
            zh_tokens=rules["weak_contains_zh"],
        ):
            return True

        tokens = field_name_word_tokens(key)
        if len(tokens) != 1:
            return False

        token = tokens[0]
        token_lower = token.lower()
        return (
            token_lower in rules["metric_tokens_en"]
            or token in rules["metric_tokens_zh"]
            or token_lower in rules["time_tokens_en"]
            or token in rules["time_tokens_zh"]
            or token_lower in rules["category_tokens_en"]
            or token in rules["category_tokens_zh"]
        )

    def _schema_semantic_label_strength(
        field_name: str,
        field_type: Any,
        field_meta: Dict[str, Any],
    ) -> int:
        key = sanitize_field_name(field_name)
        if not key:
            return -40

        score = 0
        tokens = field_name_word_tokens(key)
        token_count = len(tokens)
        flags = _semantic_signal_flags(key)

        score += min(12, token_count * 3)
        score += min(10, max(0, len(key) // 4))

        if coerce_field_type(field_type) != "string":
            score += 3
        if field_meta.get("unit_norm"):
            score += 4
        if field_meta.get("dimensions"):
            score += 5
        if field_meta.get("normalization_rule_id"):
            score += 6

        if flags["metric"]:
            score += 6
        if flags["identifier"]:
            score += 8 if token_count >= 2 else 2
        if flags["time"]:
            score += 4 if token_count >= 2 else -3
        if flags["category"]:
            score += 3 if token_count >= 2 else -4
        if (
            re.search(r"[\u4e00-\u9fff]", key)
            and len(key) >= 8
            and token_count <= 2
            and not flags["metric"]
            and not flags["identifier"]
            and not flags["time"]
            and not flags["category"]
        ):
            # Long CJK labels without metric/identifier/time/category semantics
            # are usually title fragments rather than extractable fields.
            score -= 16

        if _is_semantically_weak_field_label(key):
            score -= 18
        if flags["visual"]:
            score -= 16
        if looks_like_schema_figure_title(key):
            score -= 26
        if looks_like_schema_sentence_fragment(key):
            score -= 24
        if token_count == 1 and flags["metric"]:
            score -= 10
        if len(key) <= 2:
            score -= 8

        return score

    def _semantic_closure_fragment_alias_keys(field_meta: Dict[str, Any]) -> set[str]:
        blocked: set[str] = set()
        dimensions = field_meta.get("dimensions")
        if isinstance(dimensions, dict):
            for payload in dimensions.values():
                if not isinstance(payload, dict):
                    continue
                for key in ("label", "raw", "value"):
                    normalized = sanitize_field_name(payload.get(key))
                    if normalized:
                        blocked.add(normalized)
        for key in ("unit_raw", "unit_norm", "unit_label"):
            normalized = sanitize_field_name(field_meta.get(key))
            if normalized:
                blocked.add(normalized)
        return blocked

    return Module2MainSchemaSemanticsBundle(
        semantic_contains_exact_token=_semantic_contains_exact_token,
        semantic_contains_fragment=_semantic_contains_fragment,
        semantic_signal_flags=_semantic_signal_flags,
        is_semantically_weak_field_label=_is_semantically_weak_field_label,
        schema_semantic_label_strength=_schema_semantic_label_strength,
        semantic_closure_fragment_alias_keys=_semantic_closure_fragment_alias_keys,
    )
