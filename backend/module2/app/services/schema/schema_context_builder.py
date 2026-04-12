from __future__ import annotations

"""Schema context bundle builder for module2 service layer."""

from dataclasses import dataclass
import re
from typing import Any, Callable, Dict, List, Optional, Sequence


SanitizeFieldNameFn = Callable[[Any], str]


@dataclass(frozen=True)
class Module2MainSchemaContextBundle:
    schema_context_clean_text: Callable[[Any], str]
    schema_context_texts_from_figures: Callable[[List[Dict[str, Any]]], List[str]]
    extract_text_for_schema: Callable[[str, List[Dict[str, Any]], Optional[List[Dict[str, Any]]], int], str]
    looks_like_schema_figure_title: Callable[[str], bool]
    looks_like_schema_sentence_fragment: Callable[[str], bool]


def build_module2_main_schema_context_bundle(
    *,
    sanitize_field_name: SanitizeFieldNameFn,
    schema_figure_title_tokens: Sequence[str],
    schema_sentence_cue_tokens_zh: Sequence[str],
    schema_sentence_cue_tokens_en: Sequence[str],
) -> Module2MainSchemaContextBundle:
    tag_re = re.compile(r"<[^>]+>")

    def _schema_context_clean_text(value: Any) -> str:
        text = tag_re.sub(" ", str(value or ""))
        return re.sub(r"\s+", " ", text).strip()

    def _schema_context_texts_from_figures(
        figure_blocks: List[Dict[str, Any]],
        *,
        max_figures: int = 10,
    ) -> List[str]:
        out: List[str] = []
        for figure in figure_blocks[:max_figures]:
            if not isinstance(figure, dict):
                continue
            caption = _schema_context_clean_text(figure.get("caption"))
            if caption:
                out.append(caption)
            for key in ("key_points", "text_blocks", "insights"):
                values = figure.get(key)
                if not isinstance(values, list):
                    continue
                for item in values[:6]:
                    text = _schema_context_clean_text(item)
                    if text:
                        out.append(text)
            dataframe = figure.get("dataframe")
            if not isinstance(dataframe, dict):
                continue
            headers = dataframe.get("headers")
            if isinstance(headers, list):
                header_text = " | ".join(
                    _schema_context_clean_text(item)
                    for item in headers[:10]
                    if _schema_context_clean_text(item)
                )
                if header_text:
                    out.append(header_text)
            rows = dataframe.get("rows")
            if isinstance(rows, list):
                row_labels: List[str] = []
                for row in rows[:8]:
                    if not isinstance(row, list):
                        continue
                    first_cell = _schema_context_clean_text(row[0] if row else "")
                    if not first_cell or re.fullmatch(r"[-+]?\d[\d\s,.;:%/]*", first_cell):
                        continue
                    row_labels.append(first_cell)
                if row_labels:
                    out.append(" | ".join(row_labels[:8]))
        return out

    def _extract_text_for_schema(
        markdown: str,
        table_blocks: List[Dict[str, Any]],
        figure_blocks: Optional[List[Dict[str, Any]]] = None,
        max_chars: int = 16000,
    ) -> str:
        compact_md = _schema_context_clean_text(markdown)
        table_context_bits: List[str] = []
        for table in table_blocks[:10]:
            if not isinstance(table, dict):
                continue
            caption = _schema_context_clean_text(table.get("caption"))
            if caption:
                table_context_bits.append(caption)
            headers = table.get("headers")
            if not isinstance(headers, list):
                continue
            header_text = " | ".join(
                _schema_context_clean_text(item)
                for item in headers[:10]
                if _schema_context_clean_text(item)
            )
            if header_text:
                table_context_bits.append(header_text)
        figure_context_bits = _schema_context_texts_from_figures(figure_blocks or [], max_figures=10)
        merged_parts = [compact_md]
        if table_context_bits:
            merged_parts.append(f"表格语义: {' | '.join(table_context_bits)}")
        if figure_context_bits:
            merged_parts.append(f"图表语义: {' | '.join(figure_context_bits)}")
        merged = "\n".join(part for part in merged_parts if part).strip()
        if len(merged) > max_chars:
            merged = merged[:max_chars]
        return merged

    def _looks_like_schema_figure_title(candidate: str) -> bool:
        text = str(candidate or "").strip()
        if not text:
            return False
        lowered = text.lower()
        if lowered.startswith("figure") or lowered.startswith("chart"):
            return True
        return any(token in text for token in schema_figure_title_tokens)

    def _looks_like_schema_sentence_fragment(candidate: str) -> bool:
        text = sanitize_field_name(candidate)
        if not text:
            return False
        lowered = text.lower()
        if any(token in lowered for token in schema_sentence_cue_tokens_en):
            return True
        if any(token in text for token in schema_sentence_cue_tokens_zh):
            return True
        return len(text) >= 12 and any(token in text for token in ("\u7684", "\u5728", "\u4e3a"))

    return Module2MainSchemaContextBundle(
        schema_context_clean_text=_schema_context_clean_text,
        schema_context_texts_from_figures=_schema_context_texts_from_figures,
        extract_text_for_schema=_extract_text_for_schema,
        looks_like_schema_figure_title=_looks_like_schema_figure_title,
        looks_like_schema_sentence_fragment=_looks_like_schema_sentence_fragment,
    )
