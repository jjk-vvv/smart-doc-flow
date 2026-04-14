from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from .ref_table_parser import build_ref_focus_preview


_DATE_PATTERNS = (
    re.compile(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b"),
    re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日?"),
)
_LATIN_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9._-]{2,}")
_CJK_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]{2,12}")

_GENERIC_TERMS = {
    "这份文档",
    "这个文档",
    "当前文档",
    "这个文件",
    "这份文件",
    "当前文件",
    "这张表",
    "这个表",
    "表格",
    "表格里",
    "表中",
    "文档里",
    "文件里",
    "记录",
    "这条记录",
    "这一行",
    "多少",
    "是多少",
    "什么",
    "哪些",
    "如何",
    "please",
    "table",
    "document",
    "file",
    "current",
    "record",
    "row",
    "value",
}

_LATIN_STOPWORDS = {
    "what",
    "which",
    "that",
    "this",
    "those",
    "with",
    "from",
    "into",
    "about",
    "please",
    "there",
    "their",
    "them",
    "show",
    "tell",
    "give",
    "current",
    "table",
    "document",
    "file",
    "record",
    "value",
}

_METRIC_ALIASES: dict[str, tuple[str, ...]] = {
    "confirmed": ("confirmed", "case count", "cases", "病例数", "确诊", "确诊数", "病例"),
    "deaths": ("deaths", "death", "死亡数", "死亡"),
    "tests": ("daily tests", "daily test", "tests", "test count", "检测数", "每日检测数", "检测"),
    "pm10": ("pm10",),
    "pm2.5": ("pm2.5", "pm25"),
    "aqi": ("aqi",),
    "so2": ("so2",),
    "no2": ("no2",),
    "o3": ("o3",),
    "co": ("co",),
}


@dataclass(frozen=True)
class Assistant1QuerySignals:
    text: str
    lowered: str
    dates: tuple[str, ...]
    entity_terms: tuple[str, ...]
    metric_keys: tuple[str, ...]
    metric_hints: tuple[str, ...]
    keyword_terms: tuple[str, ...]

    @property
    def wants_metric_lookup(self) -> bool:
        return bool(self.metric_keys)


def analyze_query(query: str) -> Assistant1QuerySignals:
    text = str(query or "").strip()
    lowered = text.lower()

    dates = tuple(sorted(_extract_dates(text)))

    metric_keys: list[str] = []
    metric_hints: list[str] = []
    for key, aliases in _METRIC_ALIASES.items():
        if any(_alias_present(text, lowered, alias) for alias in aliases):
            metric_keys.append(key)
            metric_hints.extend(alias.lower() for alias in aliases)

    latin_tokens = {
        token
        for token in _LATIN_TOKEN_RE.findall(lowered)
        if token not in _LATIN_STOPWORDS and token not in _GENERIC_TERMS and not token.startswith("202")
    }
    cjk_tokens = {
        token
        for token in _CJK_TOKEN_RE.findall(text)
        if token not in _GENERIC_TERMS and len(token.strip()) >= 2
    }

    keyword_terms = tuple(sorted(set(latin_tokens) | {token.lower() for token in cjk_tokens}))
    entity_terms = tuple(
        token
        for token in keyword_terms
        if token not in set(metric_hints) and token not in _GENERIC_TERMS and not token.isdigit()
    )

    return Assistant1QuerySignals(
        text=text,
        lowered=lowered,
        dates=dates,
        entity_terms=entity_terms,
        metric_keys=tuple(metric_keys),
        metric_hints=tuple(sorted(set(metric_hints))),
        keyword_terms=keyword_terms,
    )


def rerank_matches(query: str, matches: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    signals = analyze_query(query)
    enriched: list[dict[str, Any]] = []

    for original_rank, item in enumerate(matches, start=1):
        if not isinstance(item, dict):
            continue
        enriched.append(_enrich_match(item, signals=signals, original_rank=original_rank))

    enriched.sort(
        key=lambda item: (
            -float(item.get("rerank_score") or 0.0),
            float(item.get("distance") or 999.0),
            int(item.get("original_rank") or 0),
        )
    )

    selected = enriched[: max(1, int(limit or 1))]
    if signals.wants_metric_lookup:
        selected = _ensure_metric_header_context(selected, enriched, limit=max(1, int(limit or 1)))
    return selected[: max(1, int(limit or 1))]


def _ensure_metric_header_context(
    selected: list[dict[str, Any]],
    all_matches: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if any(_has_header_context(item) for item in selected):
        return selected
    header_candidate = next((item for item in all_matches if _has_header_context(item)), None)
    if header_candidate is None:
        return selected
    if any(str(item.get("id") or "") == str(header_candidate.get("id") or "") for item in selected):
        return selected
    if len(selected) < limit:
        return selected + [header_candidate]
    if not selected:
        return [header_candidate]
    return selected[:-1] + [header_candidate]


def _has_header_context(item: dict[str, Any]) -> bool:
    preview = item.get("ref_table_preview")
    return isinstance(preview, dict) and bool(preview.get("header_rows"))


def _enrich_match(item: dict[str, Any], *, signals: Assistant1QuerySignals, original_rank: int) -> dict[str, Any]:
    content = str(item.get("content") or "")
    title = str(item.get("title") or "")
    unit_meta_json = item.get("unit_meta_json") if isinstance(item.get("unit_meta_json"), dict) else {}
    meta_text = json.dumps(unit_meta_json, ensure_ascii=False, sort_keys=True) if unit_meta_json else ""
    haystack = " ".join(part for part in (title, content, meta_text) if part)
    lowered = haystack.lower()

    reasons: list[str] = []
    score = 0.0

    exact_dates = _extract_dates(haystack)
    for value in signals.dates:
        if value in exact_dates or value in lowered:
            score += 12.0
            reasons.append(f"date:{value}")

    for entity in signals.entity_terms:
        if entity and entity in lowered:
            score += 4.0
            reasons.append(f"entity:{entity}")

    for key in signals.metric_keys:
        aliases = _METRIC_ALIASES.get(key, ())
        if any(_alias_present(haystack, lowered, alias) for alias in aliases):
            score += 2.5
            reasons.append(f"metric:{key}")

    for token in signals.keyword_terms:
        if token and token in lowered:
            score += 0.35

    ref_preview = build_ref_focus_preview(
        content,
        entity_hints=list(signals.entity_terms),
        date_hints=list(signals.dates),
        metric_hints=list(signals.metric_hints),
    )
    if ref_preview:
        matched_rows = ref_preview.get("matched_row_indices") if isinstance(ref_preview.get("matched_row_indices"), list) else []
        if matched_rows:
            score += 5.0
            reasons.append("matching_row")
        if ref_preview.get("header_rows") and signals.wants_metric_lookup:
            score += 2.0
            reasons.append("header_row")

    enriched = dict(item)
    enriched["original_rank"] = original_rank
    enriched["rerank_score"] = round(score, 4)
    enriched["matched_signals"] = reasons[:10]
    if ref_preview:
        enriched["ref_table_preview"] = ref_preview
    return enriched


def _extract_dates(text: str) -> set[str]:
    hits: set[str] = set()
    source = str(text or "")
    for pattern in _DATE_PATTERNS:
        for year, month, day in pattern.findall(source):
            hits.add(f"{int(year):04d}-{int(month):02d}-{int(day):02d}")
    return hits


def _alias_present(raw_text: str, lowered_text: str, alias: str) -> bool:
    raw_alias = str(alias or "").strip()
    if not raw_alias:
        return False
    lowered_alias = raw_alias.lower()
    if re.search(r"[\u4e00-\u9fff]", raw_alias):
        return raw_alias in raw_text or lowered_alias in lowered_text
    if len(lowered_alias) <= 3:
        return re.search(rf"(?<![a-z0-9]){re.escape(lowered_alias)}(?![a-z0-9])", lowered_text) is not None
    return lowered_alias in lowered_text
