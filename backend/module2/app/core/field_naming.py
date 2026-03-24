from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


APP_ROOT = Path(__file__).resolve().parents[1]
RULES_PATH = APP_ROOT / "assets" / "field_naming_rules_v1.json"
FIELD_NAMING_VERSION = "field-naming-rules-v1.2"

_DIMENSION_LABEL_ORDER = ("region_type", "age_band", "stage", "stream", "basis")
_LABEL_DIMENSION_KEYS = {"region_type", "age_band", "stage", "stream"}
_BRACKET_TRANSLATION = str.maketrans(
    {
        "（": "(",
        "）": ")",
        "【": "[",
        "】": "]",
        "：": ":",
        "，": ",",
        "／": "/",
        "－": "-",
        "％": "%",
    }
)
_GENERIC_SUFFIX_UNITS = (
    {
        "norm": "per_100k",
        "label": "10万分之",
        "tokens": ("10万分之", "十万分之"),
    },
    {
        "norm": "per_10000",
        "label": "万分之",
        "tokens": ("万分之",),
    },
    {
        "norm": "per_thousand",
        "label": "千分之",
        "tokens": ("千分之",),
    },
    {
        "norm": "percent",
        "label": "百分之",
        "tokens": ("百分之",),
    },
    {
        "norm": "hundred_million",
        "label": "亿",
        "tokens": ("亿",),
    },
    {
        "norm": "years",
        "label": "岁",
        "tokens": ("岁",),
    },
)


def _extract_type_hint(type_hint: Any) -> Any:
    if isinstance(type_hint, dict):
        nested = type_hint.get("type")
        if nested is not None:
            return nested
    return type_hint


def _coerce_field_type(type_hint: Any) -> str:
    text = str(_extract_type_hint(type_hint) or "").strip().lower()
    if text in {"int", "integer"}:
        return "integer"
    if text in {"number", "float", "double", "numeric", "decimal", "ratio", "percent"}:
        return "number"
    if text in {"date", "datetime", "time", "timestamp"}:
        return "date"
    if text in {"bool", "boolean"}:
        return "boolean"
    return "string"


def _field_type_priority(type_hint: Any) -> int:
    return {
        "string": 0,
        "number": 1,
        "integer": 2,
        "date": 2,
        "boolean": 2,
    }.get(_coerce_field_type(type_hint), 0)


@lru_cache(maxsize=1)
def _load_rules() -> Dict[str, Any]:
    return json.loads(RULES_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _forbidden_aliases() -> set[str]:
    out: set[str] = set()
    for alias in _load_rules().get("forbidden_aliases", []):
        compact = _compact_text(alias)
        if compact:
            out.add(compact)
    return out


def _surface_text(value: Any) -> str:
    text = str(value or "").translate(_BRACKET_TRANSLATION)
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return re.sub(r"\s+", " ", text).strip()


def _compact_text(value: Any) -> str:
    text = _surface_text(value).lower()
    text = re.sub(r"[\s_\-/:,.;|()\[\]{}<>]+", "", text)
    return text


def _detect_generic_suffix_unit(text: str) -> Tuple[Optional[Dict[str, str]], str]:
    original = _surface_text(text)
    if not original:
        return None, original

    for item in _GENERIC_SUFFIX_UNITS:
        norm = str(item.get("norm") or "").strip()
        label = str(item.get("label") or "").strip()
        for token in item.get("tokens", ()):
            raw_token = _surface_text(token)
            if not raw_token:
                continue

            patterns = [
                rf"^(?P<body>.+?)\s*[（(]\s*{re.escape(raw_token)}\s*[)）]\s*$",
                rf"^(?P<body>.+?)[\s:/_-]+{re.escape(raw_token)}\s*$",
            ]
            if len(raw_token) >= 2:
                patterns.append(rf"^(?P<body>.+?){re.escape(raw_token)}\s*$")

            for pattern in patterns:
                match = re.match(pattern, original, flags=re.IGNORECASE)
                if not match:
                    continue
                body = _strip_wrapper_tokens(match.group("body"))
                if len(body) < 2:
                    continue
                return {
                    "norm": norm,
                    "label": label or raw_token,
                    "raw": raw_token,
                }, body

    return None, original


def _simple_ascii_key(text: str) -> str:
    lowered = _surface_text(text).lower()
    lowered = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
    if lowered:
        return lowered[:72]
    digest = hashlib.sha1(_surface_text(text).encode("utf-8")).hexdigest()[:10]
    return f"field_{digest}"


def _looks_like_numeric_text(value: Any) -> bool:
    text = _surface_text(value)
    if not text:
        return False
    return bool(re.fullmatch(r"[-+]?\d[\d\s,.;:%/%]*", text))


def _collect_figure_text_parts(
    figure_blocks: Optional[List[Dict[str, Any]]],
    *,
    max_figures: int = 8,
) -> List[str]:
    parts: List[str] = []
    for figure in (figure_blocks or [])[:max_figures]:
        if not isinstance(figure, dict):
            continue
        caption = _surface_text(figure.get("caption"))
        if caption:
            parts.append(caption)
        for key in ("key_points", "text_blocks", "insights"):
            values = figure.get(key)
            if not isinstance(values, list):
                continue
            for item in values[:6]:
                text = _surface_text(item)
                if text:
                    parts.append(text)
        dataframe = figure.get("dataframe")
        if not isinstance(dataframe, dict):
            continue
        headers = dataframe.get("headers")
        if isinstance(headers, list):
            header_text = " ".join(_surface_text(item) for item in headers[:10] if _surface_text(item))
            if header_text:
                parts.append(header_text)
        rows = dataframe.get("rows")
        if isinstance(rows, list):
            row_labels: List[str] = []
            for row in rows[:8]:
                if not isinstance(row, list):
                    continue
                label = _surface_text(row[0] if row else "")
                if not label or _looks_like_numeric_text(label):
                    continue
                row_labels.append(label)
            if row_labels:
                parts.append(" ".join(row_labels[:8]))
    return parts


def _looks_like_generic_rule_fallback_alias(alias_text: str, aliases: List[Any]) -> bool:
    alias_compact = _compact_text(alias_text)
    if not alias_compact or len(alias_compact) > 8:
        return False
    if re.search(r"\d", alias_compact):
        return False
    if re.search(r"[a-z]{2,}", alias_compact):
        return False
    longer_aliases = [
        _compact_text(candidate)
        for candidate in aliases
        if len(_compact_text(candidate)) >= len(alias_compact) + 2
    ]
    return bool(longer_aliases)


def _preferred_dimension_order(items: Dict[str, Dict[str, str]]) -> List[Tuple[str, Dict[str, str]]]:
    ranked: List[Tuple[str, Dict[str, str]]] = []
    seen = set()
    for key in _DIMENSION_LABEL_ORDER:
        if key in items:
            ranked.append((key, items[key]))
            seen.add(key)
    for key, value in items.items():
        if key not in seen:
            ranked.append((key, value))
    return ranked


def _append_dimensions_to_label(base_label: str, dimensions: Dict[str, Dict[str, str]]) -> str:
    if not dimensions:
        return base_label
    suffixes: List[str] = []
    for dim_key, payload in _preferred_dimension_order(dimensions):
        if dim_key not in _LABEL_DIMENSION_KEYS:
            continue
        label = str(payload.get("label") or "").strip()
        if label:
            suffixes.append(label)
    if not suffixes:
        return base_label
    return f"{base_label}（{' / '.join(suffixes)}）"


def _append_dimensions_to_key(base_key: str, dimensions: Dict[str, Dict[str, str]]) -> str:
    if not dimensions:
        return base_key
    parts = [base_key]
    for dim_key, payload in _preferred_dimension_order(dimensions):
        value = _simple_ascii_key(payload.get("value") or payload.get("label") or dim_key)
        parts.extend((dim_key, value))
    return "__".join(part for part in parts if part)


def _strip_wrapper_tokens(text: str) -> str:
    out = _surface_text(text)
    out = re.sub(r"[\[\]{}<>]", " ", out)
    out = re.sub(r"\(\s*\)", " ", out)
    out = re.sub(r"\s+", " ", out).strip(" ,;:-_/")
    return re.sub(r"\s+", " ", out).strip()


def _dedupe_aliases(
    aliases: List[str],
    *,
    keep_compacts: Optional[set[str]] = None,
    limit: int = 32,
) -> List[str]:
    forbidden = _forbidden_aliases()
    keep_compacts = keep_compacts or set()
    seen: set[str] = set()
    unique: List[str] = []
    for alias in aliases:
        alias_surface = _surface_text(alias)
        compact = _compact_text(alias_surface)
        if not alias_surface or not compact or compact in seen:
            continue
        if compact in forbidden and compact not in keep_compacts:
            continue
        seen.add(compact)
        unique.append(alias_surface)
        if len(unique) >= limit:
            break
    return unique


def detect_domain_template(
    *,
    file_name: str,
    markdown: str = "",
    table_blocks: Optional[List[Dict[str, Any]]] = None,
    figure_blocks: Optional[List[Dict[str, Any]]] = None,
) -> str:
    text_parts = [_surface_text(file_name), _surface_text(markdown)[:4000]]
    for table in (table_blocks or [])[:6]:
        headers = table.get("headers")
        if isinstance(headers, list):
            text_parts.append(" ".join(_surface_text(item) for item in headers[:12] if _surface_text(item)))
    text_parts.extend(_collect_figure_text_parts(figure_blocks, max_figures=6))
    haystack = " ".join(part for part in text_parts if part).lower()
    for item in _load_rules().get("templates", []):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        match_any = item.get("match_any")
        if not name or not isinstance(match_any, list):
            continue
        if any(str(token or "").strip().lower() in haystack for token in match_any if str(token or "").strip()):
            return name
    return "common_document"


def _is_strong_rule_alias(alias_text: str, alias_compact: str) -> bool:
    if len(alias_compact) >= 4:
        return True
    if re.search(r"\d", alias_compact):
        return True
    if re.search(r"[A-Z]{2,}", str(alias_text or "")):
        return True
    return False


def _rule_match_support_ok(
    *,
    template: str,
    best_len: int,
    matched_alias_count: int,
    strong_alias_count: int,
) -> bool:
    normalized_template = str(template or "").strip()
    if normalized_template == "government_statistical_bulletin":
        return best_len >= 4 or strong_alias_count >= 1 or matched_alias_count >= 2
    if normalized_template == "xlsx_business_ledger":
        return best_len >= 3 or strong_alias_count >= 1 or matched_alias_count >= 2
    return best_len >= 3 or matched_alias_count >= 2


def infer_rule_backed_schema_fields(
    *,
    file_name: str,
    markdown: str = "",
    table_blocks: Optional[List[Dict[str, Any]]] = None,
    figure_blocks: Optional[List[Dict[str, Any]]] = None,
    template_hint: str = "",
    max_fields: int = 12,
) -> Dict[str, str]:
    template = str(template_hint or "").strip() or detect_domain_template(
        file_name=file_name,
        markdown=markdown,
        table_blocks=table_blocks,
        figure_blocks=figure_blocks,
    )
    text_parts = [_surface_text(file_name), _surface_text(markdown)[:12000]]
    for table in (table_blocks or [])[:10]:
        headers = table.get("headers")
        if isinstance(headers, list):
            text_parts.append(" ".join(_surface_text(item) for item in headers[:18] if _surface_text(item)))
        header_meta = table.get("header_meta")
        if isinstance(header_meta, list):
            header_bits: List[str] = []
            for item in header_meta[:18]:
                if not isinstance(item, dict):
                    continue
                header_bits.append(_surface_text(item.get("name")))
                header_bits.append(_surface_text(item.get("unit")))
            text_parts.append(" ".join(bit for bit in header_bits if bit))
    text_parts.extend(_collect_figure_text_parts(figure_blocks, max_figures=10))

    haystack_compact = _compact_text(" ".join(part for part in text_parts if part))
    candidates: Dict[str, Tuple[int, str]] = {}

    for item in _load_rules().get("field_rules", []):
        if not isinstance(item, dict):
            continue
        rule_templates = item.get("templates")
        if isinstance(rule_templates, list):
            normalized_templates = {str(value or "").strip() for value in rule_templates if str(value or "").strip()}
            if normalized_templates and template and template not in normalized_templates:
                continue
        aliases = item.get("aliases")
        if not isinstance(aliases, list):
            continue

        matched_alias = ""
        matched_len = 0
        matched_alias_count = 0
        strong_alias_count = 0
        for alias in aliases:
            alias_text = _surface_text(alias)
            alias_compact = _compact_text(alias_text)
            if not alias_compact or len(alias_compact) < 2:
                continue
            if alias_compact in haystack_compact and len(alias_compact) > matched_len:
                matched_alias = alias_text
                matched_len = len(alias_compact)
            if alias_compact in haystack_compact:
                matched_alias_count += 1
                if _is_strong_rule_alias(alias_text, alias_compact):
                    strong_alias_count += 1

        if not matched_alias:
            continue
        if not _rule_match_support_ok(
            template=template,
            best_len=matched_len,
            matched_alias_count=matched_alias_count,
            strong_alias_count=strong_alias_count,
        ):
            continue
        if (
            _looks_like_generic_rule_fallback_alias(matched_alias, aliases)
            and matched_alias_count < 2
            and strong_alias_count < 1
        ):
            continue

        meta = normalize_field_name(
            matched_alias,
            type_hint=item.get("type"),
            template_hint=template,
        )
        canonical_label = str(meta.get("canonical_label") or "").strip()
        canonical_type = str(meta.get("field_type") or "string").strip() or "string"
        if not canonical_label:
            continue

        support_score = matched_len + min(6, max(0, matched_alias_count - 1) * 2) + min(4, strong_alias_count * 2)
        existing = candidates.get(canonical_label)
        if existing is None or support_score > existing[0]:
            candidates[canonical_label] = (support_score, canonical_type)

    ranked = sorted(candidates.items(), key=lambda entry: (-entry[1][0], entry[0]))
    return {
        label: field_type
        for label, (_score, field_type) in ranked[:max_fields]
    }


def _detect_unit(text: str) -> Tuple[Optional[Dict[str, str]], str]:
    original = str(text or "")
    lowered = original.lower()
    best_match: Optional[Dict[str, str]] = None
    best_item: Optional[Dict[str, Any]] = None
    best_len = -1

    for item in _load_rules().get("units", []):
        if not isinstance(item, dict):
            continue
        for token in item.get("tokens", []):
            needle = str(token or "").strip().lower()
            if not needle or needle not in lowered:
                continue
            if len(needle) > best_len:
                best_len = len(needle)
                best_item = item
                best_match = {
                    "norm": str(item.get("norm") or "").strip(),
                    "label": str(item.get("label") or token).strip(),
                    "raw": str(token).strip(),
                }

    if best_match is None or best_item is None:
        return _detect_generic_suffix_unit(original)

    cleaned = original
    for token in best_item.get("strip_tokens", []):
        raw_token = str(token or "").strip()
        if raw_token:
            cleaned = re.sub(re.escape(raw_token), " ", cleaned, flags=re.IGNORECASE)
    cleaned = _strip_wrapper_tokens(cleaned)
    return best_match, cleaned


def _detect_dimensions(text: str) -> Tuple[Dict[str, Dict[str, str]], str]:
    original = str(text or "")
    working = original
    lowered = working.lower()
    dimensions: Dict[str, Dict[str, str]] = {}

    for dim_key, values in (_load_rules().get("dimensions") or {}).items():
        if not isinstance(values, list):
            continue
        best_payload: Optional[Dict[str, str]] = None
        best_token = ""
        best_len = -1
        for item in values:
            if not isinstance(item, dict):
                continue
            for token in item.get("tokens", []):
                raw_token = str(token or "").strip()
                lowered_token = raw_token.lower()
                if not lowered_token or lowered_token not in lowered:
                    continue
                if len(lowered_token) > best_len:
                    best_len = len(lowered_token)
                    best_token = raw_token
                    best_payload = {
                        "value": str(item.get("value") or "").strip(),
                        "label": str(item.get("label") or raw_token).strip(),
                        "raw": raw_token,
                    }
        if best_payload is None:
            continue
        dimensions[str(dim_key)] = best_payload
        working = re.sub(re.escape(best_token), " ", working, flags=re.IGNORECASE)
        lowered = working.lower()

    return dimensions, _strip_wrapper_tokens(working)


def _match_field_rule(raw_name: str, cleaned_name: str, template_hint: str = "") -> Optional[Dict[str, Any]]:
    raw_compact = _compact_text(raw_name)
    cleaned_compact = _compact_text(cleaned_name)
    template = str(template_hint or "").strip()
    best_rule: Optional[Dict[str, Any]] = None
    best_score = 0

    for item in _load_rules().get("field_rules", []):
        if not isinstance(item, dict):
            continue
        rule_templates = item.get("templates")
        if isinstance(rule_templates, list):
            normalized_templates = {str(value or "").strip() for value in rule_templates if str(value or "").strip()}
            if normalized_templates and template and template not in normalized_templates:
                continue
        aliases = item.get("aliases")
        if not isinstance(aliases, list):
            continue

        score = 0
        for alias in aliases:
            alias_compact = _compact_text(alias)
            if not alias_compact:
                continue
            allow_partial = len(alias_compact) >= 4
            if alias_compact == raw_compact or alias_compact == cleaned_compact:
                score = max(score, 100 + len(alias_compact))
            elif allow_partial and alias_compact in cleaned_compact:
                score = max(score, 82 + len(alias_compact))
            elif allow_partial and alias_compact in raw_compact:
                score = max(score, 76 + len(alias_compact))

        if score <= 0:
            continue
        if template and template in str(item.get("id") or ""):
            score += 1
        if score > best_score:
            best_score = score
            best_rule = item

    return dict(best_rule) if best_rule is not None and best_score >= 80 else None


def _fallback_label(cleaned_name: str, raw_name: str) -> str:
    candidate = _strip_wrapper_tokens(cleaned_name)
    if not candidate:
        candidate = _surface_text(raw_name)
    candidate = candidate.replace("_", " ")
    candidate = re.sub(r"\s+", " ", candidate).strip()
    if len(candidate) > 48:
        candidate = candidate[:48].rstrip()
    return candidate


def normalize_field_name(
    raw_name: Any,
    *,
    type_hint: Any = None,
    template_hint: str = "",
) -> Dict[str, Any]:
    raw_surface = _surface_text(raw_name)
    template = str(template_hint or "common_document").strip() or "common_document"
    field_type = _coerce_field_type(type_hint)

    if not raw_surface:
        return {
            "raw_name": "",
            "canonical_key": "",
            "canonical_label": "",
            "canonical_base_label": "",
            "canonical_base_key": "",
            "field_type": field_type,
            "unit_raw": "",
            "unit_norm": "",
            "dimensions": {},
            "domain_template": template,
            "normalization_confidence": 0.0,
            "normalization_rule_id": "",
            "aliases": [],
        }

    unit_meta, without_unit = _detect_unit(raw_surface)
    dimensions, without_dims = _detect_dimensions(without_unit)
    cleaned_name = _strip_wrapper_tokens(without_dims) or _strip_wrapper_tokens(without_unit) or raw_surface
    rule = _match_field_rule(raw_surface, cleaned_name, template)

    aliases: List[str] = [raw_surface, cleaned_name]
    if unit_meta is not None:
        aliases.extend((str(unit_meta.get("label") or "").strip(), str(unit_meta.get("raw") or "").strip()))
    for payload in dimensions.values():
        aliases.extend((str(payload.get("label") or "").strip(), str(payload.get("raw") or "").strip()))

    if rule is not None:
        base_key = str(rule.get("key") or "").strip() or _simple_ascii_key(cleaned_name)
        base_label = str(rule.get("label") or "").strip() or _fallback_label(cleaned_name, raw_surface)
        aliases.extend(str(alias or "").strip() for alias in rule.get("aliases", []) if str(alias or "").strip())
        field_type = _coerce_field_type(rule.get("type") or type_hint)
        confidence = 0.95
        rule_id = str(rule.get("id") or "").strip()
    else:
        base_label = _fallback_label(cleaned_name, raw_surface)
        base_key = _simple_ascii_key(base_label)
        confidence = 0.62 if cleaned_name != raw_surface or unit_meta or dimensions else 0.55
        rule_id = ""

    canonical_label = _append_dimensions_to_label(base_label, dimensions)
    canonical_key = _append_dimensions_to_key(base_key, dimensions)
    keep_compacts = {
        _compact_text(raw_surface),
        _compact_text(canonical_label),
        _compact_text(base_label),
        _compact_text(canonical_key),
        _compact_text(base_key),
    }
    unique_aliases = _dedupe_aliases(aliases, keep_compacts=keep_compacts, limit=24)

    return {
        "raw_name": raw_surface,
        "canonical_key": canonical_key,
        "canonical_label": canonical_label,
        "canonical_base_label": base_label,
        "canonical_base_key": base_key,
        "field_type": field_type,
        "unit_raw": str(unit_meta.get("raw") or "").strip() if unit_meta else "",
        "unit_norm": str(unit_meta.get("norm") or "").strip() if unit_meta else "",
        "dimensions": dimensions,
        "domain_template": template,
        "normalization_confidence": round(confidence, 4),
        "normalization_rule_id": rule_id,
        "aliases": unique_aliases,
    }


def canonicalize_schema_fields(
    fields: Dict[str, Any],
    *,
    template_hint: str = "",
) -> Tuple[Dict[str, str], Dict[str, Dict[str, Any]], Dict[str, str], Dict[str, str], Dict[str, Any]]:
    canonical_fields: Dict[str, str] = {}
    field_meta: Dict[str, Dict[str, Any]] = {}
    raw_to_canonical: Dict[str, str] = {}
    canonical_to_raw: Dict[str, str] = {}
    template = str(template_hint or "common_document").strip() or "common_document"

    mapped = 0
    unmatched = 0
    unit_split = 0
    dimension_split = 0

    for raw_name, type_hint in fields.items():
        normalized_type_hint = _extract_type_hint(type_hint)
        meta = normalize_field_name(raw_name, type_hint=normalized_type_hint, template_hint=template)
        canonical_label = str(meta.get("canonical_label") or "").strip()
        if not canonical_label:
            continue

        raw_name_text = str(raw_name)
        raw_to_canonical[raw_name_text] = canonical_label
        canonical_to_raw.setdefault(canonical_label, raw_name_text)

        if meta.get("normalization_rule_id"):
            mapped += 1
        else:
            unmatched += 1
        if meta.get("unit_norm"):
            unit_split += 1
        if meta.get("dimensions"):
            dimension_split += 1

        next_type = _coerce_field_type(normalized_type_hint or meta.get("field_type"))
        if canonical_label not in canonical_fields:
            canonical_fields[canonical_label] = next_type
            field_meta[canonical_label] = {
                **meta,
                "raw_names": [raw_name_text],
            }
            continue

        existing_type = canonical_fields.get(canonical_label, "string")
        if _field_type_priority(next_type) > _field_type_priority(existing_type):
            canonical_fields[canonical_label] = next_type

        existing_meta = dict(field_meta.get(canonical_label, {}))
        merged_raw_names = list(existing_meta.get("raw_names", []))
        if raw_name_text not in merged_raw_names:
            merged_raw_names.append(raw_name_text)

        merged_aliases = list(existing_meta.get("aliases", []))
        merged_aliases.extend(meta.get("aliases", []))
        keep_compacts = {
            _compact_text(canonical_label),
            _compact_text(existing_meta.get("canonical_base_label") or meta.get("canonical_base_label") or ""),
        }
        existing_meta.update(
            {
                "aliases": _dedupe_aliases(merged_aliases, keep_compacts=keep_compacts, limit=32),
                "raw_names": merged_raw_names,
                "field_type": canonical_fields[canonical_label],
                "normalization_confidence": max(
                    float(existing_meta.get("normalization_confidence", 0.0) or 0.0),
                    float(meta.get("normalization_confidence", 0.0) or 0.0),
                ),
                "unit_norm": str(existing_meta.get("unit_norm") or meta.get("unit_norm") or "").strip(),
                "unit_raw": str(existing_meta.get("unit_raw") or meta.get("unit_raw") or "").strip(),
                "dimensions": existing_meta.get("dimensions") or meta.get("dimensions") or {},
                "normalization_rule_id": str(
                    existing_meta.get("normalization_rule_id")
                    or meta.get("normalization_rule_id")
                    or ""
                ).strip(),
            }
        )
        field_meta[canonical_label] = existing_meta

    stats = {
        "version": FIELD_NAMING_VERSION,
        "domain_template": template,
        "raw_field_count": len(fields),
        "canonical_field_count": len(canonical_fields),
        "mapped_field_count": mapped,
        "unmapped_field_count": unmatched,
        "unit_split_count": unit_split,
        "dimension_split_count": dimension_split,
    }
    return canonical_fields, field_meta, raw_to_canonical, canonical_to_raw, stats


def normalize_schema_contracts(
    schema: Dict[str, Any],
    raw_to_canonical: Dict[str, str],
    *,
    template_hint: str = "",
) -> Dict[str, Any]:
    normalized = dict(schema or {})
    template = str(template_hint or "common_document").strip() or "common_document"

    def map_field(name: Any) -> str:
        raw = str(name or "").strip()
        if not raw:
            return ""
        mapped = raw_to_canonical.get(raw)
        if mapped:
            return mapped
        meta = normalize_field_name(raw, template_hint=template)
        return str(meta.get("canonical_label") or raw).strip()

    required_raw = normalized.get("required")
    if isinstance(required_raw, list):
        normalized_required: List[str] = []
        seen_required = set()
        for item in required_raw:
            mapped = map_field(item)
            compact = _compact_text(mapped)
            if mapped and compact and compact not in seen_required:
                seen_required.add(compact)
                normalized_required.append(mapped)
        normalized["required"] = normalized_required

    deps_raw = normalized.get("dependencies")
    if isinstance(deps_raw, dict):
        normalized_deps: Dict[str, List[str]] = {}
        for key, values in deps_raw.items():
            mapped_key = map_field(key)
            if not mapped_key:
                continue
            iterable = values if isinstance(values, list) else [values]
            mapped_values: List[str] = []
            seen_values = set()
            for item in iterable:
                mapped_value = map_field(item)
                compact = _compact_text(mapped_value)
                if mapped_value and compact and compact not in seen_values:
                    seen_values.add(compact)
                    mapped_values.append(mapped_value)
            if mapped_values:
                normalized_deps[mapped_key] = mapped_values
        normalized["dependencies"] = normalized_deps

    validations_raw = normalized.get("validations")
    if isinstance(validations_raw, list):
        normalized_rules: List[Dict[str, Any]] = []
        for item in validations_raw:
            if not isinstance(item, dict):
                continue
            cloned = dict(item)
            for key in ("field", "target"):
                if key in cloned:
                    cloned[key] = map_field(cloned.get(key))
            operands = cloned.get("operands")
            if isinstance(operands, list):
                cloned["operands"] = [mapped for mapped in (map_field(value) for value in operands) if mapped]
            normalized_rules.append(cloned)
        normalized["validations"] = normalized_rules

    return normalized


def build_field_aliases(field_name: str, extra_aliases: Optional[List[str]] = None) -> List[str]:
    meta = normalize_field_name(field_name)
    aliases: List[str] = []
    aliases.extend(meta.get("aliases", []))
    aliases.extend(
        (
            str(meta.get("canonical_label") or "").strip(),
            str(meta.get("canonical_base_label") or "").strip(),
            str(meta.get("canonical_key") or "").strip(),
            str(meta.get("canonical_base_key") or "").strip(),
        )
    )
    for payload in (meta.get("dimensions") or {}).values():
        aliases.extend((str(payload.get("label") or "").strip(), str(payload.get("raw") or "").strip()))
    if extra_aliases:
        aliases.extend(extra_aliases)

    keep_compacts = {
        _compact_text(field_name),
        _compact_text(meta.get("canonical_label") or ""),
        _compact_text(meta.get("canonical_base_label") or ""),
    }
    return _dedupe_aliases(aliases, keep_compacts=keep_compacts, limit=32)
