from __future__ import annotations

"""Schema inference bundle builder for module2 service layer."""

from dataclasses import dataclass
import re
from typing import Any, Callable, Dict, List, Optional, Sequence, Set


SanitizeFieldNameFn = Callable[[Any], str]
IsLowValueFieldNameFn = Callable[[Any], bool]
FilterAutoSchemaFieldsFn = Callable[[Dict[str, Any], int], Dict[str, str]]
SchemaFieldTypePriorityFn = Callable[[str], int]
SchemaContextCleanTextFn = Callable[[Any], str]
LooksLikeTitleFn = Callable[[str], bool]
LooksLikeSentenceFn = Callable[[str], bool]


@dataclass(frozen=True)
class Module2MainSchemaInferenceBundle:
    field_name_prefers_date: Callable[[str], bool]
    field_name_prefers_integer: Callable[[str], bool]
    field_name_prefers_number: Callable[[str], bool]
    infer_field_type_from_name: Callable[[str], str]
    infer_schema_fields_heuristic: Callable[
        [str, List[Dict[str, Any]], Optional[List[Dict[str, Any]]], int],
        Dict[str, str],
    ]


def build_module2_main_schema_inference_bundle(
    *,
    sanitize_field_name: SanitizeFieldNameFn,
    is_low_value_auto_schema_field_name: IsLowValueFieldNameFn,
    filter_auto_schema_fields: FilterAutoSchemaFieldsFn,
    schema_field_type_priority: SchemaFieldTypePriorityFn,
    schema_context_clean_text: SchemaContextCleanTextFn,
    looks_like_schema_figure_title: LooksLikeTitleFn,
    looks_like_schema_sentence_fragment: LooksLikeSentenceFn,
    date_field_tokens: Sequence[str],
    integer_field_tokens: Sequence[str],
    number_field_tokens: Sequence[str],
    schema_heuristic_stop_tokens: Set[str],
) -> Module2MainSchemaInferenceBundle:
    ratio_text_pattern = re.compile(r"^\d+(?:\.\d+)?\s*[:：]\s*\d+(?:\.\d+)?$")
    ratio_field_tokens = ("\u6bd4\u4f8b", "\u6bd4\u7387", "\u5360\u6bd4", "ratio", "rate")

    cjk_metric_heading_fragments = (
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
        "\u589e\u957f\u7387",
        "\u589e\u901f",
        "\u5e73\u5747",
        "\u4eba\u5747",
        "\u6237\u5747",
        "\u95e8\u8bca\u91cf",
        "\u4f4f\u9662\u91cf",
        "\u5b8c\u6210\u7387",
        "\u5408\u683c\u7387",
        "\u8f6c\u5316\u7387",
        "\u8fde\u9501\u7387",
        "\u5468\u8f6c\u5929\u6570",
        "\u56de\u6b3e\u5929\u6570",
        "\u65e5\u671f",
        "\u65f6\u95f4",
        "\u6295\u8d44",
        "\u4ef7\u683c",
        "\u6307\u6570",
        "\u4ea7\u91cf",
        "\u9762\u79ef",
    )
    metric_noise_candidates = {
        "\u589e\u957f",
        "\u4e0b\u964d",
        "\u589e\u52a0",
        "\u51cf\u5c11",
        "\u63d0\u9ad8",
        "\u63d0\u5347",
        "\u4e0a\u5347",
        "\u964d\u4f4e",
        "\u540c\u6bd4\u589e\u957f",
        "\u540c\u6bd4\u4e0b\u964d",
        "\u73af\u6bd4\u589e\u957f",
        "\u73af\u6bd4\u4e0b\u964d",
    }
    generic_metric_trend_pattern = re.compile(
        r"^(?:(?:\d+(?:\.\d+)?)?(?:\u4e07|\u4ebf|\u5343)?(?:\u4eba\u6b21|\u4eba|\u5f20|\u4e2a|\u4f8b|\u6237|\u5143|%)?)(?:\u589e\u957f|\u4e0b\u964d|\u589e\u52a0|\u51cf\u5c11|\u63d0\u9ad8|\u63d0\u5347|\u4e0a\u5347|\u964d\u4f4e)$"
    )
    metric_sentence_suffixes = tuple(
        dict.fromkeys(
            sorted(
                (
                    *cjk_metric_heading_fragments,
                    "\u9500\u552e\u603b\u989d",
                    "\u9500\u552e\u989d",
                    "\u9500\u552e\u89c4\u6a21",
                    "\u4e3b\u8425\u4e1a\u52a1\u6536\u5165",
                    "\u8425\u4e1a\u6536\u5165",
                    "\u5229\u6da6\u603b\u989d",
                    "\u51c0\u5229\u6da6\u7387",
                    "\u6bdb\u5229\u7387",
                    "\u8d39\u7528\u7387",
                    "\u56de\u6b3e\u5929\u6570",
                    "\u8ba2\u5355\u603b\u6570",
                    "\u8ba2\u5355\u6570",
                    "\u6d3b\u8dc3\u7528\u6237\u91cf",
                    "\u5ba2\u5355\u4ef7",
                    "\u914d\u9001\u8d27\u503c",
                    "\u7269\u6d41\u4e2d\u5fc3",
                    "\u4ed3\u5e93\u9762\u79ef",
                    "\u914d\u9001\u4ef6\u6570\u5360\u6bd4",
                    "\u51b7\u85cf\u836f\u54c1\u6e29\u5ea6\u5408\u683c\u7387",
                    "\u5b8c\u6210\u7387",
                    "\u5408\u683c\u7387",
                    "\u8fde\u9501\u7387",
                    "\u5e02\u503c",
                    "\u6301\u8bc1\u4f01\u4e1a",
                    "\u6279\u53d1\u4f01\u4e1a",
                    "\u96f6\u552e\u8fde\u9501\u4f01\u4e1a",
                    "\u96f6\u552e\u836f\u5e97\u603b\u6570",
                    "\u6267\u4e1a\u836f\u5e08",
                    "\u4ece\u4e1a\u4eba\u6570",
                ),
                key=len,
                reverse=True,
            )
        )
    )
    metric_sentence_value_pattern = re.compile(
        r"[-+]?\d[\d,]*(?:\.\d+)?(?:%|％|亿元|万亿元|万元|元|万家|家|万人|人|天|笔|辆|个|次|台|项|平方米|立方米|个百分点)?"
    )
    metric_sentence_prefix_cleanup = re.compile(
        r"^(?:"
        r"\d{4}年(?:底|末)?(?:全国)?|"
        r"\d{4}年|"
        r"截至\d{4}年(?:底|末)?|"
        r"截至目前|"
        r"统计显示|"
        r"数据显示|"
        r"据[^，,；;]{0,18}(?:显示|统计)|"
        r"其中|"
        r"此外|"
        r"同时|"
        r"全国|"
        r"全行业"
        r")[\s,，、:：]*"
    )
    metric_sentence_trailing_connector = re.compile(
        r"(?:"
        r"\s+|"
        r"[,:：，、（）()\-]|"
        r"\u540c\u6bd4|"
        r"\u73af\u6bd4|"
        r"\u5e73\u5747|"
        r"\u7ea6\u4e3a|"
        r"\u7ea6|"
        r"\u4e3a|"
        r"\u8fbe\u5230|"
        r"\u8fbe|"
        r"\u5b9e\u73b0|"
        r"\u5171\u6709|"
        r"\u5171|"
        r"\u62e5\u6709|"
        r"\u5360\u6bd4\u4e3a|"
        r"\u6bd4\u91cd\u4e3a|"
        r"\u5360|"
        r"\u63d0\u5347\u81f3|"
        r"\u4e0a\u5347\u81f3|"
        r"\u4e0b\u964d\u81f3|"
        r"\u589e\u957f\u81f3"
        r")+$"
    )
    metric_sentence_label_pattern = re.compile(
        rf"([A-Za-z\u4e00-\u9fff][A-Za-z0-9_ \u4e00-\u9fff()\uFF08\uFF09/%\u00b7/\\-]{{1,40}}?(?:{'|'.join(re.escape(item) for item in metric_sentence_suffixes)}))$"
    )

    def _field_name_prefers_date(field_name: str) -> bool:
        text = str(field_name or "").strip().lower()
        if not text:
            return False
        return any(tok in text for tok in date_field_tokens)

    def _field_name_prefers_integer(field_name: str) -> bool:
        text = str(field_name or "").strip().lower()
        if not text:
            return False
        if _field_name_prefers_date(text):
            return False
        return any(tok in text for tok in integer_field_tokens)

    def _field_name_prefers_number(field_name: str) -> bool:
        text = str(field_name or "").strip().lower()
        if not text:
            return False
        if _field_name_prefers_date(text):
            return False
        return any(tok in text for tok in number_field_tokens)

    def _infer_field_type_from_name(field_name: str) -> str:
        if _field_name_prefers_date(field_name):
            return "date"
        if _field_name_prefers_integer(field_name):
            return "integer"
        if _field_name_prefers_number(field_name):
            return "number"
        return "string"

    def _normalized_compact(text: Any) -> str:
        return re.sub(r"[\s_\-/:,().\uFF08\uFF09\u3000]+", "", str(text or "").strip().lower())

    def _field_name_matches_table_header(field_name: str, header_text: Any) -> bool:
        compact_field = _normalized_compact(field_name)
        compact_header = _normalized_compact(header_text)
        if not compact_field or not compact_header:
            return False
        return (
            compact_field == compact_header
            or compact_field in compact_header
            or compact_header in compact_field
        )

    def _table_column_contains_ratio_text(field_name: str, table_blocks: List[Dict[str, Any]]) -> bool:
        lowered_field = str(field_name or "").strip().lower()
        if not lowered_field or not any(token in lowered_field for token in ratio_field_tokens):
            return False

        for table in table_blocks[:12]:
            candidate_cols: Set[int] = set()
            headers = table.get("headers")
            if isinstance(headers, list):
                for col_idx, header in enumerate(headers[:40], start=1):
                    if _field_name_matches_table_header(field_name, header):
                        candidate_cols.add(col_idx)

            header_meta = table.get("header_meta")
            if isinstance(header_meta, list):
                for item in header_meta[:40]:
                    if not isinstance(item, dict):
                        continue
                    try:
                        col_idx = int(item.get("col_index") or 0)
                    except (TypeError, ValueError):
                        continue
                    if col_idx <= 0:
                        continue
                    if _field_name_matches_table_header(field_name, item.get("name")):
                        candidate_cols.add(col_idx)

            if not candidate_cols:
                continue

            for row in table.get("rows", [])[:48]:
                if not isinstance(row, dict):
                    continue
                for cell in row.get("cells", []):
                    if not isinstance(cell, dict):
                        continue
                    try:
                        col_idx = int(cell.get("col_index") or 0)
                    except (TypeError, ValueError):
                        continue
                    if col_idx not in candidate_cols:
                        continue
                    text = schema_context_clean_text(cell.get("text"))
                    if text and ratio_text_pattern.fullmatch(text):
                        return True
        return False

    def _looks_like_structured_metric_candidate(raw_text: Any) -> bool:
        candidate = schema_context_clean_text(raw_text)
        if not candidate:
            return False
        if looks_like_schema_figure_title(candidate):
            return False
        if looks_like_schema_sentence_fragment(candidate):
            return False
        lower_candidate = candidate.lower()
        if any(tok and tok in lower_candidate for tok in integer_field_tokens):
            return True
        if any(tok and tok in lower_candidate for tok in number_field_tokens):
            return True
        if any(token in lower_candidate for token in ratio_field_tokens):
            return True
        return any(fragment in candidate for fragment in cjk_metric_heading_fragments)

    def _infer_schema_fields_heuristic(
        markdown: str,
        table_blocks: List[Dict[str, Any]],
        figure_blocks: Optional[List[Dict[str, Any]]],
        max_fields: int,
    ) -> Dict[str, str]:
        stop_tokens = set(schema_heuristic_stop_tokens)
        score_map: Dict[str, int] = {}
        type_map: Dict[str, str] = {}

        def push_candidate(raw_name: Any, score: int) -> None:
            key = sanitize_field_name(raw_name)
            if not key:
                return
            lower_key = key.lower()
            if lower_key == "dataframe":
                return
            if lower_key in stop_tokens:
                return
            if is_low_value_auto_schema_field_name(key):
                return
            if re.search(r"\d{4}年", key) and not key.endswith(("\u5e74\u4efd", "\u5e74\u5ea6", "\u65e5\u671f", "\u65f6\u95f4")):
                return
            if key in metric_noise_candidates or generic_metric_trend_pattern.fullmatch(key):
                return
            if len(key) <= 2 and not re.search(r"[\u4e00-\u9fff]", key):
                return
            prev_score = score_map.get(key, 0)
            if score > prev_score:
                score_map[key] = score
            inferred = _infer_field_type_from_name(key)
            prev_type = type_map.get(key)
            if prev_type is None or schema_field_type_priority(inferred) > schema_field_type_priority(prev_type):
                type_map[key] = inferred

        def looks_like_metric_heading_candidate(raw_text: Any) -> bool:
            candidate = schema_context_clean_text(raw_text)
            if not candidate:
                return False
            lower_candidate = candidate.lower()
            if any(tok and tok in lower_candidate for tok in date_field_tokens):
                return True
            if any(tok and tok in lower_candidate for tok in integer_field_tokens):
                return True
            if any(tok and tok in lower_candidate for tok in number_field_tokens):
                return True
            return any(fragment in candidate for fragment in cjk_metric_heading_fragments)

        def push_heading_candidate(raw_text: Any, score: int) -> None:
            candidate = schema_context_clean_text(raw_text)
            if not candidate:
                return
            candidate = re.sub(r"^#+\s*", "", candidate).strip()
            candidate = re.sub(
                r"^\u7b2c[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343\u4e07\d]+[\u7ae0\u8282\u90e8\u5206\u7bc7]\s*",
                "",
                candidate,
            )
            candidate = re.sub(
                r"^[\uff08(][\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\d]+[\uff09)]\s*",
                "",
                candidate,
            )
            candidate = re.sub(
                r"^[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343\u4e07\d]+[\u3001.\-]\s*",
                "",
                candidate,
            )
            candidate = candidate.strip(":-\uff1a")
            if not candidate or len(candidate) > 28:
                return
            if looks_like_schema_figure_title(candidate):
                return
            if looks_like_schema_sentence_fragment(candidate):
                return
            if re.search(r"[\u3002\uff01\uff1f?!]", candidate):
                return
            if re.fullmatch(r"[-+]?\d[\d\s,.;:%/]*", candidate):
                return
            if any(token in candidate for token in ("\u3001", "\u548c", "\u53ca")) and any(
                candidate.endswith(suffix)
                for suffix in ("\u91cf", "\u6570", "\u8d39\u7528", "\u6536\u5165", "\u652f\u51fa")
            ):
                return
            if not looks_like_metric_heading_candidate(candidate):
                return
            push_candidate(candidate, score)

        def looks_like_heading_line(raw_text: Any) -> bool:
            raw = str(raw_text or "").strip()
            if not raw:
                return False
            if raw.startswith("#"):
                return True
            cleaned = schema_context_clean_text(raw)
            if not cleaned:
                return False
            if re.match(
                r"^\u7b2c[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343\u4e07\d]+[\u7ae0\u8282\u90e8\u5206\u7bc7]",
                cleaned,
            ):
                return True
            if re.match(
                r"^[\uff08(][\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\d]+[\uff09)]",
                cleaned,
            ):
                return True
            if re.match(
                r"^[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341\u767e\u5343\u4e07\d]+[\u3001.\-]",
                cleaned,
            ):
                return True
            if len(cleaned) <= 24 and not re.search(r"[\u3002\uff01\uff1f?!:\uff1a]", cleaned):
                return True
            return False

        def push_text_fragments(raw_text: Any, score: int, *, require_metric: bool = False) -> None:
            text = schema_context_clean_text(raw_text)
            if not text:
                return
            text = re.sub(
                r"^(?:(?:figure|chart|\u56fe|\u56fe\u8868)\s*[\dA-Za-z\-_.()\uFF08\uFF09]*\s*[:\uFF1A]?\s*)",
                "",
                text,
                flags=re.IGNORECASE,
            )
            for fragment in re.split(r"[|,;:()\[\]\u3001\uFF0C\uFF1B\uFF1A\uFF08\uFF09]", text):
                candidate = sanitize_field_name(fragment)
                if not candidate or len(candidate) > 24:
                    continue
                if re.fullmatch(r"[-+]?\d[\d\s,.;:%/]*", candidate):
                    continue
                if looks_like_schema_figure_title(candidate):
                    continue
                if looks_like_schema_sentence_fragment(candidate):
                    continue
                digit_count = len(re.findall(r"\d", candidate))
                if digit_count and (digit_count / max(len(candidate), 1)) >= 0.3 and not re.search(
                    r"[A-Za-z]{2,}",
                    candidate,
                ):
                    continue
                if require_metric and not _looks_like_structured_metric_candidate(candidate):
                    continue
                push_candidate(candidate, score)

        def push_metric_sentence_candidates(raw_text: Any, score: int) -> None:
            text = schema_context_clean_text(raw_text)
            if not text or not re.search(r"\d", text):
                return
            clauses = re.split(r"[。\uff01\uff1f!?；;]", text)
            for clause_idx, clause in enumerate(clauses[:6], start=1):
                normalized_clause = schema_context_clean_text(clause)
                if not normalized_clause or not re.search(r"\d", normalized_clause):
                    continue
                normalized_clause = metric_sentence_prefix_cleanup.sub("", normalized_clause).strip()
                if not normalized_clause:
                    continue
                for match in metric_sentence_value_pattern.finditer(normalized_clause):
                    prefix = normalized_clause[: match.start()].strip()
                    if not prefix:
                        continue
                    prefix = metric_sentence_trailing_connector.sub("", prefix).strip()
                    if not prefix:
                        continue
                    label_match = metric_sentence_label_pattern.search(prefix)
                    if not label_match:
                        continue
                    candidate = schema_context_clean_text(label_match.group(1))
                    if not candidate:
                        continue
                    candidate = re.sub(r"^(?:\d{4}年(?:底|末)?|截至\d{4}年(?:底|末)?|其中|全国|全行业)", "", candidate).strip()
                    if not candidate or len(candidate) > 32:
                        continue
                    if looks_like_schema_figure_title(candidate):
                        continue
                    if looks_like_schema_sentence_fragment(candidate):
                        continue
                    if not looks_like_metric_heading_candidate(candidate):
                        continue
                    push_candidate(candidate, score - min(10, clause_idx * 2))

        for table_idx, table in enumerate(table_blocks[:12], start=1):
            base_score = max(20, 140 - table_idx * 8)
            table_source = str(table.get("source") or "").strip().lower()
            allow_generic_headers = table_source == "xlsx"
            headers = table.get("headers")
            if isinstance(headers, list):
                for col_idx, header in enumerate(headers[:24], start=1):
                    if not allow_generic_headers and not _looks_like_structured_metric_candidate(header):
                        continue
                    push_candidate(header, base_score - col_idx)

            header_meta = table.get("header_meta")
            if isinstance(header_meta, list):
                for item in header_meta[:24]:
                    if not isinstance(item, dict):
                        continue
                    if allow_generic_headers or _looks_like_structured_metric_candidate(item.get("name")):
                        push_candidate(item.get("name"), base_score + 4)
                    unit = str(item.get("unit", "") or "").strip()
                    if unit and (allow_generic_headers or _looks_like_structured_metric_candidate(f"{item.get('name')}_{unit}")):
                        push_candidate(f"{item.get('name')}_{unit}", base_score)

        for figure_idx, figure in enumerate((figure_blocks or [])[:12], start=1):
            if not isinstance(figure, dict):
                continue
            base_score = max(24, 128 - figure_idx * 6)
            push_text_fragments(figure.get("caption"), base_score + 6, require_metric=True)
            for key in ("key_points", "text_blocks", "insights"):
                values = figure.get(key)
                if not isinstance(values, list):
                    continue
                for item_idx, item in enumerate(values[:6], start=1):
                    push_text_fragments(item, base_score - item_idx, require_metric=True)
            dataframe = figure.get("dataframe")
            if not isinstance(dataframe, dict):
                continue
            headers = dataframe.get("headers")
            if isinstance(headers, list):
                for col_idx, header in enumerate(headers[:16], start=1):
                    if not _looks_like_structured_metric_candidate(header):
                        continue
                    push_candidate(header, base_score + 8 - col_idx)

        plain = schema_context_clean_text(markdown)
        if plain:
            kv_pattern = re.compile(
                r"^([A-Za-z\u4e00-\u9fff][A-Za-z0-9_ \u4e00-\u9fff()\uFF08\uFF09\\/-]{1,40})\s*[:\uFF1A]\s*(.{1,80})$"
            )
            seen_hits: Dict[str, int] = {}
            raw_lines = re.split(r"[\r\n]+", str(markdown or ""))
            for line_idx, raw_line in enumerate(raw_lines[:400], start=1):
                line = schema_context_clean_text(raw_line)
                if not line:
                    continue
                match = kv_pattern.match(line)
                if not match:
                    if looks_like_heading_line(raw_line):
                        push_heading_candidate(raw_line, max(42, 108 - min(32, line_idx)))
                    push_metric_sentence_candidates(raw_line, max(54, 112 - min(44, line_idx)))
                    continue
                candidate = sanitize_field_name(match.group(1))
                if candidate:
                    seen_hits[candidate] = seen_hits.get(candidate, 0) + 1
            for name, hit_count in seen_hits.items():
                push_candidate(name, 90 + min(18, hit_count * 4))

        if not score_map:
            return {}

        ranked = sorted(
            score_map.keys(),
            key=lambda name: (
                -score_map.get(name, 0),
                -schema_field_type_priority(type_map.get(name, "string")),
                len(name),
                name,
            ),
        )
        out: Dict[str, str] = {}
        for name in ranked:
            inferred_type = type_map.get(name, "string")
            if inferred_type == "number" and _table_column_contains_ratio_text(name, table_blocks):
                inferred_type = "string"
            out[name] = inferred_type
            if len(out) >= max_fields:
                break
        return filter_auto_schema_fields(out, max_fields=max_fields)

    return Module2MainSchemaInferenceBundle(
        field_name_prefers_date=_field_name_prefers_date,
        field_name_prefers_integer=_field_name_prefers_integer,
        field_name_prefers_number=_field_name_prefers_number,
        infer_field_type_from_name=_infer_field_type_from_name,
        infer_schema_fields_heuristic=_infer_schema_fields_heuristic,
    )
