from __future__ import annotations

"""Schema fields bundle builder for module2 service layer."""

from dataclasses import dataclass
import re
from typing import Any, Callable, Dict, List, Set, Tuple


SanitizeFieldNameFn = Callable[[Any], str]
CoerceFieldTypeFn = Callable[[Any], str]
SchemaFieldTypePriorityFn = Callable[[str], int]
SchemaFieldTypeHintFn = Callable[[Any], Any]


@dataclass(frozen=True)
class Module2MainSchemaFieldsBundle:
    field_name_word_tokens: Callable[[Any], List[str]]
    schema_field_dedup_key: Callable[[Any], str]
    schema_field_name_sort_key: Callable[[Any], Tuple[int, int, int, str]]
    upsert_schema_field_candidate: Callable[..., None]
    is_low_value_auto_schema_field_name: Callable[[Any], bool]
    filter_auto_schema_fields: Callable[[Dict[str, Any], int], Dict[str, str]]
    should_prune_shadowed_auto_field_name: Callable[[str, str], bool]
    prune_shadowed_auto_schema_fields: Callable[[Dict[str, str]], Tuple[Dict[str, str], Dict[str, str]]]
    normalize_schema_fields: Callable[[Dict[str, Any], int], Dict[str, str]]


def build_module2_main_schema_fields_bundle(
    *,
    sanitize_field_name: SanitizeFieldNameFn,
    coerce_field_type: CoerceFieldTypeFn,
    schema_field_type_priority: SchemaFieldTypePriorityFn,
    schema_field_type_hint: SchemaFieldTypeHintFn,
    auto_schema_stopwords_en: Set[str],
    auto_schema_generic_en: Set[str],
    auto_schema_generic_zh: Set[str],
    auto_schema_generic_zh_exact: Set[str],
    auto_schema_generic_zh_unit_tokens: Set[str],
    auto_schema_generic_ja_exact: Set[str],
) -> Module2MainSchemaFieldsBundle:
    title_suffixes_cjk = (
        "\u516c\u62a5",
        "\u7edf\u8ba1\u516c\u62a5",
        "\u62a5\u544a",
        "\u5e74\u62a5",
        "\u5b63\u62a5",
        "\u6708\u62a5",
        "\u5468\u62a5",
        "\u767d\u76ae\u4e66",
        "\u901a\u62a5",
        "\u516c\u544a",
    )
    title_suffixes_en = (
        "report",
        "annual_report",
        "monthly_report",
        "quarterly_report",
        "white_paper",
        "bulletin",
        "notice",
    )
    abstract_heading_suffixes_cjk = (
        "\u8d44\u6e90",
        "\u670d\u52a1",
        "\u60c5\u51b5",
        "\u5de5\u4f5c",
        "\u6982\u51b5",
        "\u6982\u8ff0",
        "\u6982\u8981",
        "\u6982\u89c8",
        "\u73b0\u72b6",
        "\u8d8b\u52bf",
        "\u5206\u6790",
        "\u53d1\u5c55",
        "\u7edf\u8ba1",
        "\u603b\u7ed3",
        "\u603b\u89c8",
    )
    abstract_heading_suffixes_en = (
        "summary",
        "overview",
        "analysis",
        "status",
        "profile",
        "resource",
        "resources",
        "service",
        "services",
        "operations",
        "work",
    )
    metric_fragments_cjk = (
        "\u603b\u6570",
        "\u6570\u91cf",
        "\u6570\u76ee",
        "\u4eba\u6570",
        "\u4eba\u6b21",
        "\u5e8a\u4f4d",
        "\u8d39\u7528",
        "\u603b\u8d39\u7528",
        "\u91d1\u989d",
        "\u603b\u989d",
        "\u6536\u5165",
        "\u652f\u51fa",
        "\u6bd4\u7387",
        "\u6bd4\u91cd",
        "\u5360\u6bd4",
        "\u6bd4\u4f8b",
        "\u589e\u957f",
        "\u589e\u901f",
        "\u91cf",
        "\u7387",
        "\u5747",
        "\u5e73\u5747",
        "\u65e5\u671f",
        "\u65f6\u95f4",
        "\u6b21\u6570",
    )
    metric_tokens_en = {
        "amount",
        "average",
        "balance",
        "bed",
        "beds",
        "charge",
        "charges",
        "cost",
        "count",
        "date",
        "duration",
        "expenditure",
        "expense",
        "expenses",
        "fee",
        "fees",
        "income",
        "institution",
        "institutions",
        "number",
        "patient",
        "patients",
        "payment",
        "payments",
        "percent",
        "price",
        "qty",
        "quantity",
        "rate",
        "ratio",
        "revenue",
        "time",
        "total",
        "volume",
        "year",
    }
    generic_heading_tokens_cjk = {
        "\u8d44\u6e90",
        "\u670d\u52a1",
        "\u60c5\u51b5",
        "\u5de5\u4f5c",
        "\u6982\u51b5",
        "\u6982\u8ff0",
        "\u5206\u6790",
        "\u53d1\u5c55",
        "\u7edf\u8ba1",
        "\u516c\u62a5",
        "\u62a5\u544a",
    }
    generic_heading_tokens_en = {
        "analysis",
        "overview",
        "profile",
        "report",
        "resource",
        "resources",
        "service",
        "services",
        "status",
        "summary",
        "work",
    }
    generic_metric_trend_pattern = re.compile(
        r"^(?:(?:\d+(?:\.\d+)?)?(?:\u4e07|\u4ebf|\u5343)?(?:\u4eba\u6b21|\u4eba|\u5f20|\u4e2a|\u4f8b|\u6237|\u5143|%)?)(?:\u589e\u957f|\u4e0b\u964d|\u589e\u52a0|\u51cf\u5c11|\u63d0\u9ad8|\u63d0\u5347|\u4e0a\u5347|\u964d\u4f4e)$"
    )
    separated_trend_tail_pattern = re.compile(
        r"^.+(?:\s|_+|/+|-+)(?:\u540c\u6bd4|\u73af\u6bd4|\u6bd4\u4e0a\u5e74|\u8f83\u4e0a\u5e74|\u8f83\u53bb\u5e74|\u8f83\u540c\u671f)(?:\u589e\u957f|\u4e0b\u964d|\u589e\u52a0|\u51cf\u5c11|\u63d0\u9ad8|\u56de\u843d)$"
    )
    compact_cjk_visual_title_pattern = re.compile(
        r"^(?:\u8868|\u56fe|\u9644\u8868|\u9644\u56fe)[\d\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+.*$"
    )
    compact_generic_zh = {
        compact
        for compact in (
            re.sub(r"[\s_]+", "", str(item or "").strip())
            for item in auto_schema_generic_zh
        )
        if compact
    }
    compact_generic_zh_exact = {
        compact
        for compact in (
            re.sub(r"[\s_]+", "", str(item or "").strip())
            for item in auto_schema_generic_zh_exact
        )
        if compact
    }
    compact_generic_ja_exact = {
        compact
        for compact in (
            re.sub(r"[\s_]+", "", str(item or "").strip())
            for item in auto_schema_generic_ja_exact
        )
        if compact
    }
    geo_dimension_allowlist = {
        "城市",
        "城市名",
        "城市名称",
        "地区",
        "地市",
        "区域",
        "行政区",
        "行政区划",
        "省",
        "省份",
        "市",
        "区",
        "县",
        "区县",
        "街道",
        "乡镇",
    }
    compact_geo_dimension_allowlist = {
        re.sub(r"[\s_]+", "", str(item or "").strip())
        for item in geo_dimension_allowlist
        if str(item or "").strip()
    }

    def _semantic_connector_fold(text: str) -> str:
        compact = re.sub(r"[\s_]+", "", str(text or "").strip())
        if not compact:
            return ""
        return compact.replace("\u7684", "")

    def _has_metric_semantics(key: str, lower_key: str, alpha_tokens: List[str]) -> bool:
        if any(fragment in key for fragment in metric_fragments_cjk):
            return True
        if any(token in metric_tokens_en for token in alpha_tokens):
            return True
        if any(token in lower_key for token in metric_tokens_en if len(token) >= 5):
            return True
        return False

    def _field_name_word_tokens(text: Any) -> List[str]:
        return re.findall(r"[\u4e00-\u9fff]+|[A-Za-z]+|\d+", str(text or ""))

    def _schema_field_dedup_key(field_name: Any) -> str:
        key = sanitize_field_name(field_name)
        if not key:
            return ""
        normalized = re.sub(r"_+", "_", key).strip(" _")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        connector_folded = _semantic_connector_fold(normalized)
        return connector_folded.lower() if connector_folded else normalized.lower()

    def _schema_field_name_sort_key(field_name: Any) -> Tuple[int, int, int, str]:
        key = sanitize_field_name(field_name)
        if not key:
            return (9, 9, 999, "")
        return (
            1 if key.endswith("_") else 0,
            key.count("_"),
            len(key),
            key.lower(),
        )

    def _is_low_value_auto_schema_field_name(field_name: Any) -> bool:
        key = sanitize_field_name(field_name)
        if not key:
            return True
        compact_key = re.sub(r"[\s_]+", "", key)
        if compact_key in compact_geo_dimension_allowlist:
            return False
        if compact_key in {"城市"}:
            return False
        if key in auto_schema_generic_zh:
            return True
        if key in auto_schema_generic_zh_exact:
            return True
        if key in auto_schema_generic_ja_exact:
            return True
        if compact_key in compact_generic_zh:
            return True
        if compact_key in compact_generic_zh_exact:
            return True
        if compact_key in compact_generic_ja_exact:
            return True
        if compact_cjk_visual_title_pattern.fullmatch(compact_key):
            return True
        if generic_metric_trend_pattern.fullmatch(key):
            return True
        if separated_trend_tail_pattern.fullmatch(key):
            return True

        lower_key = key.lower().strip()
        if not lower_key:
            return True
        if re.fullmatch(r"\d+(?:\s+\d+)*", lower_key):
            return True
        if re.fullmatch(r"[\u4e00-\u9fff]{2,32}(?:[_ ]\d+(?:\.\d+)?)", key):
            return True
        if re.fullmatch(r"(?:fig(?:ure)?|eqn|equation|table|appendix|chapter|section|exercise)\s*[A-Za-z0-9. ]*", lower_key):
            return True
        if re.fullmatch(r"[A-Za-z]{1,4}\s+[A-Za-z]?\d+(?:\.\d+)?", key):
            return True

        has_cjk = bool(re.search(r"[\u4e00-\u9fff]", key))
        tokens = _field_name_word_tokens(key)
        if not tokens:
            return True
        cjk_tokens = [tok for tok in tokens if re.search(r"[\u4e00-\u9fff]", tok)]
        raw_alpha_tokens = re.findall(r"[A-Za-z]+", key)
        alpha_tokens = [tok.lower() for tok in raw_alpha_tokens]
        has_metric_semantics = _has_metric_semantics(key, lower_key, alpha_tokens)

        if any(key.endswith(suffix) for suffix in title_suffixes_cjk):
            return True
        if any(lower_key.endswith(suffix) for suffix in title_suffixes_en):
            return True
        if not has_metric_semantics:
            if any(key.endswith(suffix) for suffix in abstract_heading_suffixes_cjk):
                return True
            if any(lower_key.endswith(suffix) for suffix in abstract_heading_suffixes_en):
                return True

        if cjk_tokens and all(
            tok in auto_schema_generic_zh
            or tok in auto_schema_generic_zh_exact
            or tok in auto_schema_generic_ja_exact
            or tok in auto_schema_generic_zh_unit_tokens
            for tok in cjk_tokens
        ):
            return True
        if (
            not has_metric_semantics
            and has_cjk
            and cjk_tokens
            and len(cjk_tokens) <= 4
            and all(
                tok in generic_heading_tokens_cjk
                or tok in auto_schema_generic_zh
                or tok in auto_schema_generic_zh_exact
                for tok in cjk_tokens
            )
        ):
            return True
        if alpha_tokens and all(tok in auto_schema_stopwords_en for tok in alpha_tokens):
            return True
        if (
            not has_metric_semantics
            and (not has_cjk)
            and alpha_tokens
            and len(alpha_tokens) <= 4
            and all(
                tok in generic_heading_tokens_en
                or tok in auto_schema_generic_en
                or tok in auto_schema_stopwords_en
                for tok in alpha_tokens
            )
        ):
            return True

        informative_alpha: List[str] = []
        for raw_tok, tok in zip(raw_alpha_tokens, alpha_tokens):
            if tok in auto_schema_stopwords_en or tok in auto_schema_generic_en:
                continue
            if len(tok) >= 3 or raw_tok.isupper():
                informative_alpha.append(tok)

        if not has_cjk:
            if not informative_alpha and alpha_tokens:
                return True
            if len(alpha_tokens) == 1 and alpha_tokens[0] in auto_schema_generic_en:
                return True
            if any(tok.isdigit() for tok in tokens) and len(informative_alpha) <= 1 and len(tokens) <= 3:
                return True
            if len(tokens) <= 3 and any(tok in {"eqn", "fig", "figure", "table"} for tok in alpha_tokens):
                return True

        return False

    def _upsert_schema_field_candidate(
        out: Dict[str, str],
        raw_name: Any,
        type_hint: Any,
        skip_low_value: bool = False,
    ) -> None:
        key = sanitize_field_name(raw_name)
        if not key:
            return
        if skip_low_value and _is_low_value_auto_schema_field_name(key):
            return

        dedup_key = _schema_field_dedup_key(key)
        if not dedup_key:
            return

        normalized_type = coerce_field_type(type_hint)
        existing_name = ""
        for current_name in list(out.keys()):
            if _schema_field_dedup_key(current_name) == dedup_key:
                existing_name = current_name
                break

        if not existing_name:
            out[key] = normalized_type
            return

        chosen_name = existing_name
        if _schema_field_name_sort_key(key) < _schema_field_name_sort_key(existing_name):
            chosen_name = key

        merged_type = out.get(existing_name, "string")
        if schema_field_type_priority(normalized_type) > schema_field_type_priority(merged_type):
            merged_type = normalized_type

        if chosen_name != existing_name:
            out.pop(existing_name, None)
        out[chosen_name] = merged_type

    def _should_prune_shadowed_auto_field_name(short_name: str, long_name: str) -> bool:
        short_key = sanitize_field_name(short_name)
        long_key = sanitize_field_name(long_name)
        if not short_key or not long_key or short_key == long_key:
            return False
        short_compact = re.sub(r"[\s_]+", "", short_key)
        long_compact = re.sub(r"[\s_]+", "", long_key)
        if short_compact in compact_geo_dimension_allowlist or long_compact in compact_geo_dimension_allowlist:
            return False
        if _semantic_connector_fold(short_key) and _semantic_connector_fold(short_key) == _semantic_connector_fold(long_key):
            return True
        if len(long_key) <= len(short_key) + 1:
            return False

        shadow_roots = [short_key]
        if "_" in short_key:
            prefix = sanitize_field_name(short_key.split("_", 1)[0])
            if prefix and prefix not in shadow_roots:
                shadow_roots.append(prefix)

        short_has_cjk = bool(re.search(r"[\u4e00-\u9fff]", short_key))
        long_has_cjk = bool(re.search(r"[\u4e00-\u9fff]", long_key))
        if short_has_cjk and long_has_cjk:
            if len(short_key) > 8:
                return False
            return any(root and len(root) <= 4 and root in long_key for root in shadow_roots)

        short_alpha_tokens = [tok.lower() for tok in re.findall(r"[A-Za-z]+", short_key)]
        long_alpha_tokens = [tok.lower() for tok in re.findall(r"[A-Za-z]+", long_key)]
        if short_alpha_tokens and long_alpha_tokens:
            if len(short_alpha_tokens) > 2 or len(short_key) > 12:
                return False
            return any(root.lower() in long_key.lower() for root in shadow_roots) and len(long_alpha_tokens) > len(short_alpha_tokens)

        return False

    def _prune_shadowed_auto_schema_fields(
        fields: Dict[str, str],
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        kept = dict(fields)
        removed: Dict[str, str] = {}
        ordered_keys = list(kept.keys())
        longer_keys = sorted(ordered_keys, key=lambda item: (-len(item), item))
        for short_key in ordered_keys:
            if short_key not in kept:
                continue
            for long_key in longer_keys:
                if long_key not in kept or long_key == short_key:
                    continue
                if not _should_prune_shadowed_auto_field_name(short_key, long_key):
                    continue
                removed[short_key] = f"shadowed_by_more_specific_field:{long_key}"
                kept.pop(short_key, None)
                break
        return kept, removed

    def _filter_auto_schema_fields(fields: Dict[str, Any], max_fields: int) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for name, type_hint in fields.items():
            _upsert_schema_field_candidate(out, name, type_hint, skip_low_value=True)
            if len(out) >= max_fields:
                break
        pruned, _ = _prune_shadowed_auto_schema_fields(out)
        return dict(list(pruned.items())[:max_fields])

    def _normalize_schema_fields(fields: Dict[str, Any], max_fields: int) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for name, type_hint in fields.items():
            _upsert_schema_field_candidate(
                out,
                name,
                schema_field_type_hint(type_hint),
                skip_low_value=False,
            )
            if len(out) >= max_fields:
                break
        return out

    return Module2MainSchemaFieldsBundle(
        field_name_word_tokens=_field_name_word_tokens,
        schema_field_dedup_key=_schema_field_dedup_key,
        schema_field_name_sort_key=_schema_field_name_sort_key,
        upsert_schema_field_candidate=_upsert_schema_field_candidate,
        is_low_value_auto_schema_field_name=_is_low_value_auto_schema_field_name,
        filter_auto_schema_fields=_filter_auto_schema_fields,
        should_prune_shadowed_auto_field_name=_should_prune_shadowed_auto_field_name,
        prune_shadowed_auto_schema_fields=_prune_shadowed_auto_schema_fields,
        normalize_schema_fields=_normalize_schema_fields,
    )
