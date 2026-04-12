from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Set


SummarizeDocumentPayloadFn = Callable[[Any], str]
BuildDocumentTraceHitsFn = Callable[..., List[Dict[str, Any]]]
FilterTraceHitsFn = Callable[..., List[Dict[str, Any]]]
SummarizeResponseFactory = Callable[..., Any]
TraceLocateResponseFactory = Callable[..., Any]
TraceDisplayKindFn = Callable[[Dict[str, Any]], str]
_TRACE_TAG_RE = re.compile(r"<[^>]+>")


class DocumentToolsRuntime:
    def __init__(
        self,
        *,
        summarize_document_payload: SummarizeDocumentPayloadFn,
        build_document_trace_hits: BuildDocumentTraceHitsFn,
        filter_trace_hits: FilterTraceHitsFn,
        summarize_response_factory: SummarizeResponseFactory,
        trace_locate_response_factory: TraceLocateResponseFactory,
    ) -> None:
        self._summarize_document_payload = summarize_document_payload
        self._build_document_trace_hits = build_document_trace_hits
        self._filter_trace_hits = filter_trace_hits
        self._summarize_response_factory = summarize_response_factory
        self._trace_locate_response_factory = trace_locate_response_factory

    def summarize(self, payload: Any) -> Any:
        return self._summarize_response_factory(
            summary=self._summarize_document_payload(payload)
        )

    def trace_locate(self, payload: Any) -> Any:
        doc = payload.document
        source_hits_raw = doc.trace_hits if isinstance(doc.trace_hits, list) else []
        source_hits: List[Dict[str, Any]] = []
        for item in source_hits_raw:
            if isinstance(item, dict):
                source_hits.append(dict(item))
            elif hasattr(item, "model_dump"):
                source_hits.append(item.model_dump(mode="json"))

        if not source_hits:
            result_payload = doc.result.model_dump(mode="json")
            if (
                isinstance(result_payload, dict)
                and "root" in result_payload
                and isinstance(result_payload.get("root"), dict)
                and len(result_payload) == 1
            ):
                result_payload = result_payload["root"]
            source_hits = self._build_document_trace_hits(
                file_name=doc.file_name,
                file_hash=doc.file_hash,
                results=result_payload if isinstance(result_payload, dict) else {},
                table_blocks=[],
                figure_blocks=[],
                markdown="",
            )

        all_hits = self._filter_trace_hits(
            source_hits,
            field_name=payload.field_name or "",
            file_name=payload.file_name or "",
            file_hash=payload.file_hash or "",
            ref_id=payload.ref_id or "",
            object_type=payload.object_type or "",
            keyword=payload.keyword or "",
        )
        top_k = int(payload.top_k)
        hits = all_hits[:top_k]
        return self._trace_locate_response_factory(
            hit_count=len(all_hits),
            truncated=len(all_hits) > len(hits),
            hits=hits,
        )


class TraceSemanticsRuntime:
    def display_kind_from_hit(self, hit: Dict[str, Any]) -> str:
        object_type = str(hit.get("object_type", "") or "").strip().lower()
        if object_type in {"field", "table", "chart"}:
            return object_type
        if object_type != "figure":
            return "other"

        locator = hit.get("locator") if isinstance(hit.get("locator"), dict) else {}
        figure_type = str(locator.get("figure_type", "")).strip().lower()
        if figure_type in {"table", "spreadsheet"}:
            return "table"

        content_modes = [
            str(item).strip().lower()
            for item in (locator.get("content_modes") if isinstance(locator.get("content_modes"), list) else [])
            if str(item).strip()
        ]
        dataframe = locator.get("dataframe") if isinstance(locator.get("dataframe"), dict) else {}
        headers = dataframe.get("headers") if isinstance(dataframe.get("headers"), list) else []
        rows = dataframe.get("rows") if isinstance(dataframe.get("rows"), list) else []
        has_headers = any(str(cell).strip() for cell in headers)
        has_rows = any(isinstance(row, list) and any(str(cell).strip() for cell in row) for row in rows[:3])
        if (has_headers or has_rows) and "visual" not in content_modes and "topology" not in content_modes:
            return "table"
        return "image"

    def build_trace_stats(self, trace_hits: List[Dict[str, Any]]) -> Dict[str, Any]:
        count_by_type: Dict[str, int] = {}
        count_by_display_kind: Dict[str, int] = {}
        page_set = set()
        for hit in trace_hits:
            typ = str(hit.get("object_type", "unknown") or "unknown")
            count_by_type[typ] = count_by_type.get(typ, 0) + 1
            display_kind = self.display_kind_from_hit(hit)
            count_by_display_kind[display_kind] = count_by_display_kind.get(display_kind, 0) + 1
            try:
                page_no = int(hit.get("page", 0) or 0)
            except (TypeError, ValueError):
                page_no = 0
            if page_no > 0:
                page_set.add(page_no)
        return {
            "trace_hit_count": len(trace_hits),
            "trace_object_counts": count_by_type,
            "trace_display_counts": count_by_display_kind,
            "trace_pages": sorted(page_set),
        }


class TraceLocatorTextRuntime:
    @staticmethod
    def _table_header_semantic_key(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        normalized = (
            text.replace("\u3000", " ")
            .replace("（", "(")
            .replace("）", ")")
            .replace("【", "[")
            .replace("】", "]")
        )
        normalized = re.sub(r"\s+", "", normalized)
        normalized = re.sub(r"(?<=[\u4e00-\u9fffA-Za-z0-9])\(([^()]*)\)", r"(\1)", normalized)
        return normalized

    def clean_text(self, value: Any, max_len: int = 0) -> str:
        text = _TRACE_TAG_RE.sub(" ", str(value or ""))
        text = re.sub(r"\s+", " ", text).strip(" |:;,\u3002\uff0c\uff1a\uff1b")
        if max_len > 0:
            text = text[:max_len].strip()
        return text

    def unique_texts(self, values: List[Any], limit: int = 4, max_len: int = 80) -> List[str]:
        out: List[str] = []
        seen: Set[str] = set()
        for value in values:
            cleaned = self.clean_text(value, max_len=max_len)
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(cleaned)
            if len(out) >= limit:
                break
        return out

    def looks_placeholder_text(self, value: Any) -> bool:
        text = self.clean_text(value)
        if not text:
            return True
        meaningful = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", text)
        if not meaningful:
            return True
        placeholder_count = text.count("?") + text.count("\uff1f") + text.count("\ufffd")
        return placeholder_count >= max(2, len(text) // 3)

    def strip_artifact_noise(
        self,
        value: Any,
        *,
        object_type: str = "",
        object_id: str = "",
        max_len: int = 0,
    ) -> str:
        text = self.clean_text(value)
        if not text:
            return ""
        text = re.sub(r"^(chart|table|figure|image)\s*:\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(
            "[\\(\uff08](?:pdf|mineru|gemini|vision|roi)[^\\)\uff09]*[\\)\uff09]",
            "",
            text,
            flags=re.IGNORECASE,
        )
        text = re.sub(
            r"\b(?:pdf_mineru|gemini_vision_[a-z_]+|pdf_roi_crop|mineru_out)\b",
            "",
            text,
            flags=re.IGNORECASE,
        )
        if object_id:
            text = re.sub(rf"\b{re.escape(object_id)}\b", "", text, flags=re.IGNORECASE)
        if object_type == "table":
            text = re.sub("^\\s*\u8868\u683c\\s*", "", text)
        elif object_type in {"figure", "image"}:
            text = re.sub("^\\s*(?:\u56fe\u50cf|\u56fe\u7247|\u63d2\u56fe)\\s*", "", text)
        text = re.sub(r"\b(?:table|figure|image|fig)[\s_-]*\d+\b", "", text, flags=re.IGNORECASE)
        text = re.sub("^\\s*(?:title|\u6807\u9898)[:\uff1a]\\s*", "", text, flags=re.IGNORECASE)
        text = self.clean_text(text)
        if max_len > 0:
            text = text[:max_len].strip()
        return text

    def is_low_signal_artifact_text(
        self,
        value: Any,
        *,
        object_type: str = "",
        object_id: str = "",
    ) -> bool:
        cleaned = self.strip_artifact_noise(
            value,
            object_type=object_type,
            object_id=object_id,
            max_len=120,
        )
        if not cleaned or self.looks_placeholder_text(cleaned):
            return True
        lowered = cleaned.lower()
        object_id_lower = self.clean_text(object_id).lower()
        if object_id_lower and lowered == object_id_lower:
            return True
        if object_id_lower and object_id_lower in lowered and len(cleaned) <= len(object_id_lower) + 6:
            return True
        if re.fullmatch(r"(?:table|figure|image|fig)[\s_-]*\d+", lowered):
            return True
        if re.fullmatch(r"col[_\s-]*\d+", lowered):
            return True
        if re.fullmatch(
            "(?:\u5355\u4f4d|unit)\\s*[:\uff1a]\\s*[A-Za-z0-9\u4e00-\u9fff%\uff05\xb0\u2103/ -]{1,24}",
            cleaned,
            flags=re.IGNORECASE,
        ):
            return True
        if lowered.startswith("the unit of measurement is"):
            return True
        if lowered.startswith("the image contains the text"):
            return True
        if object_type == "table" and lowered in {"table", "\u8868\u683c"}:
            return True
        if object_type in {"figure", "image"} and lowered in {
            "image",
            "figure",
            "fig",
            "\u56fe\u50cf",
            "\u56fe\u7247",
            "\u63d2\u56fe",
        }:
            return True
        return False

    def table_header_labels(self, table: Dict[str, Any], *, max_items: int = 4) -> List[str]:
        object_id = str(table.get("table_id") or "").strip()
        candidates: List[str] = []
        semantic_seen: Set[str] = set()

        def append_candidate(raw_value: Any) -> None:
            text = self.strip_artifact_noise(
                raw_value,
                object_type="table",
                object_id=object_id,
                max_len=32,
            )
            if not text or self.is_low_signal_artifact_text(
                text,
                object_type="table",
                object_id=object_id,
            ):
                return
            semantic_key = self._table_header_semantic_key(text)
            if semantic_key and semantic_key in semantic_seen:
                return
            if semantic_key:
                semantic_seen.add(semantic_key)
            candidates.append(text)

        for item in table.get("headers", []) if isinstance(table.get("headers"), list) else []:
            append_candidate(item)
        for meta in table.get("header_meta", []) if isinstance(table.get("header_meta"), list) else []:
            if not isinstance(meta, dict):
                continue
            name = self.clean_text(meta.get("name"), max_len=24)
            unit = self.clean_text(meta.get("unit"), max_len=16)
            label = name
            if name and unit and unit not in name:
                label = f"{name} ({unit})"
            elif unit and not name:
                label = unit
            append_candidate(label)
        return self.unique_texts(candidates, limit=max_items, max_len=32)

    def table_row_samples(self, table: Dict[str, Any], *, max_items: int = 3) -> List[str]:
        samples: List[str] = []
        for row in table.get("rows", []) if isinstance(table.get("rows"), list) else []:
            if not isinstance(row, dict):
                continue
            pieces: List[str] = []
            for cell in row.get("cells", []) if isinstance(row.get("cells"), list) else []:
                if not isinstance(cell, dict):
                    continue
                text = self.clean_text(cell.get("text"), max_len=24)
                if text:
                    pieces.append(text)
                if len(pieces) >= 2:
                    break
            if not pieces:
                continue
            sample = " / ".join(pieces[:2])
            if self.looks_placeholder_text(sample):
                continue
            if sample not in samples:
                samples.append(sample)
            if len(samples) >= max_items:
                break
        return samples

    def table_locator_texts(self, table: Dict[str, Any]) -> Dict[str, Any]:
        object_id = str(table.get("table_id") or "").strip()
        caption = self.strip_artifact_noise(
            table.get("caption"),
            object_type="table",
            object_id=object_id,
            max_len=120,
        )
        if self.is_low_signal_artifact_text(caption, object_type="table", object_id=object_id):
            caption = ""
        header_labels = self.table_header_labels(table, max_items=4)
        header_text = " | ".join(header_labels)
        row_samples = self.table_row_samples(table, max_items=3)

        title = ""
        for candidate in [caption, header_text]:
            if candidate and not self.is_low_signal_artifact_text(
                candidate,
                object_type="table",
                object_id=object_id,
            ):
                title = candidate
                break

        summary_candidates: List[str] = []
        if title and header_text and header_text != title:
            summary_candidates.append(f"{title}\uff1b\u8868\u5934\uff1a{header_text}")
        if title and row_samples:
            summary_candidates.append(f"{title}\uff1b\u6837\u4f8b\uff1a{' / '.join(row_samples)}")
        elif header_text and row_samples:
            summary_candidates.append(f"\u8868\u5934\uff1a{header_text}\uff1b\u6837\u4f8b\uff1a{' / '.join(row_samples)}")
        elif header_text:
            summary_candidates.append(f"\u8868\u5934\uff1a{header_text}")
        elif caption:
            summary_candidates.append(caption)

        summary = ""
        for candidate in summary_candidates:
            if candidate and not self.is_low_signal_artifact_text(
                candidate,
                object_type="table",
                object_id=object_id,
            ):
                summary = self.clean_text(candidate, max_len=200)
                break

        return {
            "title": title,
            "caption": caption,
            "summary": summary,
            "header_labels": header_labels,
        }

    def figure_locator_texts(self, figure: Dict[str, Any]) -> Dict[str, Any]:
        object_id = str(figure.get("figure_id") or "").strip()
        title_raw = self.strip_artifact_noise(
            figure.get("title"),
            object_type="figure",
            object_id=object_id,
            max_len=120,
        )
        caption = self.strip_artifact_noise(
            figure.get("caption"),
            object_type="figure",
            object_id=object_id,
            max_len=120,
        )
        if self.is_low_signal_artifact_text(title_raw, object_type="figure", object_id=object_id):
            title_raw = ""
        if self.is_low_signal_artifact_text(caption, object_type="figure", object_id=object_id):
            caption = ""

        key_points = self.unique_texts(
            figure.get("key_points") if isinstance(figure.get("key_points"), list) else [],
            limit=2,
            max_len=72,
        )
        text_blocks = self.unique_texts(
            figure.get("text_blocks") if isinstance(figure.get("text_blocks"), list) else [],
            limit=2,
            max_len=96,
        )
        legend = self.unique_texts(
            figure.get("legend") if isinstance(figure.get("legend"), list) else [],
            limit=2,
            max_len=40,
        )
        axes = figure.get("axes") if isinstance(figure.get("axes"), dict) else {}
        axis_labels = self.unique_texts([axes.get("x"), axes.get("y")], limit=2, max_len=32)
        key_values_raw = figure.get("key_values") if isinstance(figure.get("key_values"), list) else []
        key_value_texts: List[str] = []
        for item in key_values_raw[:2]:
            if not isinstance(item, dict):
                continue
            name = self.clean_text(item.get("name"), max_len=36)
            value = self.clean_text(item.get("value"), max_len=36)
            unit = self.clean_text(item.get("unit"), max_len=16)
            if not name and not value:
                continue
            key_value_text = f"{name}:{value}".strip(":")
            if unit:
                key_value_text = f"{key_value_text} {unit}".strip()
            key_value_texts.append(key_value_text)
        dataframe = figure.get("dataframe") if isinstance(figure.get("dataframe"), dict) else {}
        dataframe_headers = self.unique_texts(
            dataframe.get("headers") if isinstance(dataframe.get("headers"), list) else [],
            limit=4,
            max_len=32,
        )
        dataframe_header_text = " | ".join(
            header
            for header in dataframe_headers
            if not self.is_low_signal_artifact_text(
                header,
                object_type="figure",
                object_id=object_id,
            )
        )

        title = ""
        for candidate in [
            title_raw,
            caption,
            key_points[0] if key_points else "",
            dataframe_header_text,
            " / ".join(legend[:2]) if legend else "",
            " / ".join(axis_labels[:2]) if axis_labels else "",
        ]:
            if candidate and not self.is_low_signal_artifact_text(
                candidate,
                object_type="figure",
                object_id=object_id,
            ):
                title = candidate
                break

        summary = ""
        for candidate in [
            caption if caption and caption != title else "",
            "\uff1b".join(key_points[:2]) if key_points else "",
            text_blocks[0] if text_blocks else "",
            f"\u6570\u636e\u5b57\u6bb5\uff1a{dataframe_header_text}" if dataframe_header_text else "",
            f"\u56fe\u4f8b\uff1a{' / '.join(legend[:2])}" if legend else "",
            f"\u8f74\uff1a{' / '.join(axis_labels[:2])}" if axis_labels else "",
            f"\u6570\u503c\uff1a{' / '.join(key_value_texts[:2])}" if key_value_texts else "",
        ]:
            if candidate and not self.is_low_signal_artifact_text(
                candidate,
                object_type="figure",
                object_id=object_id,
            ):
                summary = self.clean_text(candidate, max_len=200)
                break

        return {
            "title": title,
            "caption": caption,
            "summary": summary,
        }


class TraceLocatorPayloadRuntime:
    @staticmethod
    def _positive_int(value: Any) -> int:
        try:
            parsed = int(value or 0)
        except (TypeError, ValueError):
            return 0
        return parsed if parsed > 0 else 0

    def nonpdf_locator_from_ref(self, ref_id: str | None, file_name: str) -> Dict[str, Any]:
        if not ref_id:
            return {}
        ref = str(ref_id).strip()
        if not ref:
            return {}
        ext = Path(file_name or "").suffix.lower()
        locator: Dict[str, Any] = {}

        if ext == ".xlsx":
            match = re.match(r"^(xlsx(?:_formula)?)_t(\d+)_r(\d+)_c(\d+)$", ref, flags=re.IGNORECASE)
            if match:
                locator.update(
                    {
                        "sheet_index": int(match.group(2)),
                        "row_index": int(match.group(3)),
                        "col_index": int(match.group(4)),
                        "ref_scope": "cell",
                    }
                )
                return locator
            match = re.match(r"^xlsx_sheet_(\d+)$", ref, flags=re.IGNORECASE)
            if match:
                locator.update({"sheet_index": int(match.group(1)), "ref_scope": "sheet"})
                return locator

        if ext == ".docx":
            match = re.match(r"^(docx(?:_relaxed)?)_t(\d+)_r(\d+)_c(\d+)$", ref, flags=re.IGNORECASE)
            if match:
                locator.update(
                    {
                        "table_index": int(match.group(2)),
                        "row_index": int(match.group(3)),
                        "col_index": int(match.group(4)),
                        "ref_scope": "cell",
                    }
                )
                return locator
            match = re.match(r"^docx(?:_relaxed)?_(\d+)$", ref, flags=re.IGNORECASE)
            if match:
                locator.update({"paragraph_index": int(match.group(1)), "ref_scope": "paragraph"})
                return locator

        if ext in {".txt", ".md", ".markdown"}:
            match = re.match(r"^text_(\d+)$", ref, flags=re.IGNORECASE)
            if match:
                chunk_index = int(match.group(1))
                line_start = max(1, (chunk_index - 1) * 12 + 1)
                line_end = line_start + 11
                locator.update(
                    {
                        "chunk_index": chunk_index,
                        "line_start": line_start,
                        "line_end": line_end,
                        "ref_scope": "text_chunk",
                    }
                )
                return locator
            match = re.match(r"^(md|txt)_t(\d+)_r(\d+)_c(\d+)$", ref, flags=re.IGNORECASE)
            if match:
                locator.update(
                    {
                        "table_index": int(match.group(2)),
                        "row_index": int(match.group(3)),
                        "col_index": int(match.group(4)),
                        "ref_scope": "cell",
                    }
                )
                return locator
            match = re.match(r"^(md|txt)_fig_(\d+)$", ref, flags=re.IGNORECASE)
            if match:
                locator.update({"figure_index": int(match.group(2)), "ref_scope": "figure_cue"})
                return locator

        return locator

    def table_locator_hint(self, table: Dict[str, Any], file_name: str) -> Dict[str, Any]:
        ext = Path(file_name or "").suffix.lower()
        if ext == ".xlsx":
            sheet_name = str(table.get("sheet_name") or "").strip()
            out = {
                "sheet_index": int(table.get("sheet_index", table.get("page", 0)) or 0),
                "sheet_name": sheet_name,
            }
            return {key: value for key, value in out.items() if value not in ("", 0, None)}

        if ext == ".docx":
            table_id = str(table.get("table_id") or "")
            match = re.search(r"_t(\d+)", table_id)
            table_index = int(match.group(1)) if match else 0
            return {"table_index": table_index} if table_index > 0 else {}

        return {}

    def figure_locator_hint(self, figure: Dict[str, Any], file_name: str) -> Dict[str, Any]:
        ext = Path(file_name or "").suffix.lower()
        if ext == ".docx":
            fig_id = str(figure.get("figure_id") or "")
            match = re.search(r"_f(\d+)", fig_id)
            if match:
                return {"figure_index": int(match.group(1))}
        if ext in {".md", ".txt", ".markdown"}:
            fig_id = str(figure.get("figure_id") or "")
            match = re.search(r"_f(\d+)", fig_id)
            if match:
                return {"figure_index": int(match.group(1))}
        return {}

    def table_dataframe_payload(self, table: Dict[str, Any]) -> Dict[str, Any]:
        headers = [str(x or "").strip() for x in table.get("headers", []) if str(x or "").strip()]
        rows_full: List[List[str]] = []
        for row in table.get("rows", []):
            if not isinstance(row, dict):
                continue
            values: List[str] = []
            for cell in row.get("cells", []):
                if not isinstance(cell, dict):
                    values.append("")
                    continue
                text = str(cell.get("text") or "").strip()
                values.append(text[:200])
            if any(value for value in values):
                rows_full.append(values)
        col_count = max((len(row) for row in rows_full), default=len(headers))
        projected_row_count = max(
            len(rows_full),
            self._positive_int(table.get("projected_row_count")),
            self._positive_int(table.get("row_count")),
        )
        projected_col_count = max(
            col_count,
            self._positive_int(table.get("projected_col_count")),
            self._positive_int(table.get("col_count")),
        )
        source_used_col_count = self._positive_int(table.get("source_used_col_count"))
        source_nonempty_row_count = self._positive_int(table.get("source_nonempty_row_count"))
        source_nonempty_cell_count = self._positive_int(table.get("source_nonempty_cell_count"))
        xlsx_projection_truncated = bool(
            table.get("xlsx_projection_truncated")
            or (source_nonempty_row_count > 0 and source_nonempty_row_count > projected_row_count)
            or (source_used_col_count > 0 and source_used_col_count > projected_col_count)
        )
        return {
            "headers": headers,
            "rows": rows_full,
            "row_count": projected_row_count,
            "col_count": projected_col_count,
            "projected_row_count": projected_row_count,
            "projected_col_count": projected_col_count,
            "source_used_col_count": source_used_col_count,
            "source_nonempty_row_count": source_nonempty_row_count,
            "source_nonempty_cell_count": source_nonempty_cell_count,
            "xlsx_projection_truncated": xlsx_projection_truncated,
            "sheet_index": self._positive_int(table.get("sheet_index")),
            "sheet_name": str(table.get("sheet_name") or "").strip(),
            "xlsx_sheet_rows_artifact_url": str(table.get("xlsx_sheet_rows_artifact_url") or "").strip(),
            "xlsx_workbook_manifest_url": str(table.get("xlsx_workbook_manifest_url") or "").strip(),
        }

    def table_preview_payload(
        self,
        table: Dict[str, Any],
        max_rows: int = 5,
        max_cols: int = 6,
    ) -> Dict[str, Any]:
        dataframe = self.table_dataframe_payload(table)
        headers = [str(x or "").strip() for x in dataframe.get("headers", [])][:max_cols]
        rows_preview: List[List[str]] = []
        for row in dataframe.get("rows", [])[:max_rows]:
            if not isinstance(row, list):
                continue
            values = [str(cell or "").strip()[:80] for cell in row[:max_cols]]
            if any(value for value in values):
                rows_preview.append(values)
        return {
            "headers": headers,
            "rows": rows_preview,
            "row_count": int(dataframe.get("row_count", 0) or 0),
            "col_count": int(dataframe.get("col_count", 0) or 0),
            "projected_row_count": int(dataframe.get("projected_row_count", 0) or 0),
            "projected_col_count": int(dataframe.get("projected_col_count", 0) or 0),
            "source_used_col_count": int(dataframe.get("source_used_col_count", 0) or 0),
            "source_nonempty_row_count": int(dataframe.get("source_nonempty_row_count", 0) or 0),
            "source_nonempty_cell_count": int(dataframe.get("source_nonempty_cell_count", 0) or 0),
            "xlsx_projection_truncated": bool(dataframe.get("xlsx_projection_truncated")),
            "sheet_index": int(dataframe.get("sheet_index", 0) or 0),
            "sheet_name": str(dataframe.get("sheet_name") or "").strip(),
            "xlsx_sheet_rows_artifact_url": str(dataframe.get("xlsx_sheet_rows_artifact_url") or "").strip(),
            "xlsx_workbook_manifest_url": str(dataframe.get("xlsx_workbook_manifest_url") or "").strip(),
        }

    def figure_dataframe_payload(self, figure: Dict[str, Any]) -> Dict[str, Any]:
        dataframe_raw = figure.get("dataframe") if isinstance(figure.get("dataframe"), dict) else {}
        headers = [
            str(x).strip()
            for x in (dataframe_raw.get("headers") if isinstance(dataframe_raw.get("headers"), list) else [])
            if str(x).strip()
        ]
        rows_full: List[List[str]] = []
        rows_raw = dataframe_raw.get("rows") if isinstance(dataframe_raw.get("rows"), list) else []
        for row in rows_raw:
            if not isinstance(row, list):
                continue
            values = [str(value).strip()[:200] for value in row]
            if any(values):
                rows_full.append(values)
        col_count = max((len(row) for row in rows_full), default=len(headers))
        return {
            "headers": headers,
            "rows": rows_full,
            "row_count": len(rows_full),
            "col_count": col_count,
        }

    def artifact_source_key(self, payload: Dict[str, Any]) -> str:
        if str(payload.get("image_path") or "").strip():
            return "pdf_mineru"
        if str(payload.get("artifact_path") or "").strip() or str(payload.get("artifact_url") or "").strip():
            source = str(payload.get("source") or "").strip().lower()
            if source.startswith("docx_media"):
                return source
            if source.startswith("docx_chart"):
                return source
            if source in {"pdf_fitz", "pdf_mineru", "pdf_mineru_gemini"} or source.startswith("pdf_fitz_"):
                return "pdf_roi_crop"
            return source or "artifact_output"
        return ""

    def table_dataframe_source_key(self, table: Dict[str, Any]) -> str:
        source = str(table.get("source") or "").strip().lower()
        if "gemini" in source or "vision" in source:
            return "gemini_vision_table"
        return "table_structured"

    def figure_dataframe_source_key(self, figure: Dict[str, Any]) -> str:
        dataframe_source = str(figure.get("dataframe_source") or "").strip().lower()
        if dataframe_source:
            return dataframe_source
        source = str(figure.get("source") or "").strip().lower()
        if "gemini" in source or "vision" in source:
            return "gemini_vision_figure"
        return "none"


class PolymorphicLinksRuntime:
    def __init__(self, *, normalize_bbox, page_from_bbox) -> None:
        self._normalize_bbox = normalize_bbox
        self._page_from_bbox = page_from_bbox

    def build_links(
        self,
        *,
        results: Dict[str, Any],
        trace_hits: List[Dict[str, Any]],
        max_links: int = 80,
    ) -> List[Dict[str, Any]]:
        links: List[Dict[str, Any]] = []
        if not isinstance(results, dict) or not trace_hits:
            return links

        table_hits = [hit for hit in trace_hits if str(hit.get("object_type", "")).lower() == "table"]
        figure_hits = [hit for hit in trace_hits if str(hit.get("object_type", "")).lower() == "figure"]

        for field_name, entity in results.items():
            if not isinstance(entity, dict):
                continue
            ref_id = str(entity.get("source_ref_id") or "").strip()
            bbox = self._normalize_bbox(entity.get("bbox"), page_hint=1)
            page = self._page_from_bbox(bbox)
            related_targets: List[Dict[str, Any]] = []

            for hit in table_hits:
                hit_ref = str(hit.get("ref_id") or "").strip()
                hit_page = int(hit.get("page", 0) or 0)
                ref_match = bool(ref_id and hit_ref and ref_id == hit_ref)
                page_match = bool(page and hit_page and page == hit_page)
                if not ref_match and not page_match:
                    continue
                related_targets.append(
                    {
                        "type": "table",
                        "id": str(hit.get("object_id") or ""),
                        "page": hit_page or None,
                        "confidence": float(hit.get("confidence", 0.0) or 0.0),
                        "match": "ref_id" if ref_match else "page",
                    }
                )

            for hit in figure_hits:
                hit_page = int(hit.get("page", 0) or 0)
                if not (page and hit_page and page == hit_page):
                    continue
                related_targets.append(
                    {
                        "type": "figure",
                        "id": str(hit.get("object_id") or ""),
                        "page": hit_page or None,
                        "confidence": float(hit.get("confidence", 0.0) or 0.0),
                        "match": "page",
                    }
                )

            if not related_targets:
                continue
            related_targets.sort(key=lambda item: float(item.get("confidence", 0.0) or 0.0), reverse=True)
            links.append(
                {
                    "field": str(field_name),
                    "ref_id": ref_id or None,
                    "page": page,
                    "targets": related_targets[:8],
                }
            )
            if len(links) >= max_links:
                break
        return links

FIELD_LABELS = {
    "contract_amount": "合同金额",
    "start_date": "开始日期",
    "end_date": "结束日期",
    "tax_rate": "税率",
    "region": "地区",
    "invoice_number": "发票号码",
    "invoice_date": "开票日期",
    "buyer_name": "购买方名称",
    "seller_name": "销售方名称",
    "total_amount": "合计金额",
}

SUMMARY_NOTICE_SKIP = {
    "quality_gate_ok",
}

SUMMARY_NOTICE_MAP = {
    "table_extract_timeout": "复杂表格抽取超时，当前表格结果可能仍有遗漏。",
    "table_extract_error": "复杂表格抽取阶段出现异常，当前表格结果可能不完整。",
    "field_extract_timeout": "字段抽取超时，部分字段可能尚未完全识别。",
    "field_extract_error": "字段抽取阶段出现异常，部分字段可能尚未完全识别。",
    "word_pdf_parse_timeout_fallback_fasttrack": "Word 转 PDF 后的深度版面解析超时，当前已切换为快速解析链路，图表完整度可能受影响。",
    "pdf_visual_timeout_fallback_fasttrack": "PDF 视觉解析超时，当前已切换为快速解析链路，复杂版面定位可能不够完整。",
}


class DocumentToolsSupportRuntime:
    def __init__(self, *, trace_display_kind_from_hit: TraceDisplayKindFn) -> None:
        self._trace_display_kind_from_hit = trace_display_kind_from_hit

    def filter_trace_hits(
        self,
        hits: List[Dict[str, Any]],
        *,
        field_name: str = "",
        file_name: str = "",
        file_hash: str = "",
        ref_id: str = "",
        object_type: str = "",
        keyword: str = "",
    ) -> List[Dict[str, Any]]:
        normalized_field_name = str(field_name or "").strip().lower()
        normalized_file_name = str(file_name or "").strip().lower()
        normalized_file_hash = str(file_hash or "").strip().lower()
        normalized_ref_id = str(ref_id or "").strip()
        normalized_object_type = str(object_type or "").strip().lower()
        normalized_keyword = str(keyword or "").strip().lower()

        out: List[Dict[str, Any]] = []
        for hit in hits:
            if normalized_file_name and str(hit.get("file_name", "")).lower() != normalized_file_name:
                continue
            if normalized_file_hash and str(hit.get("file_hash", "")).lower() != normalized_file_hash:
                continue
            if normalized_object_type and str(hit.get("object_type", "")).lower() != normalized_object_type:
                continue
            if normalized_ref_id and str(hit.get("ref_id", "") or "") != normalized_ref_id:
                continue
            snippet = str(hit.get("snippet", "")).lower()
            if normalized_field_name:
                object_id = str(hit.get("object_id", "")).lower()
                if object_id != normalized_field_name and f"{normalized_field_name}:" not in snippet:
                    continue
            if normalized_keyword and normalized_keyword not in snippet:
                continue
            out.append(hit)
        out.sort(key=lambda item: float(item.get("confidence", 0.0) or 0.0), reverse=True)
        return out

    def summarize_document_payload(self, req: Any) -> str:
        lines: List[str] = [f"文档《{req.file_name}》已完成内容解析。"]

        result_items: List[str] = []
        result_payload = req.result if isinstance(getattr(req, "result", None), dict) else {}
        for key, value in result_payload.items():
            if not isinstance(value, dict):
                continue
            field_val = value.get("value")
            if field_val in (None, "", [], {}):
                continue
            field_text = self._summary_clean_text(field_val, max_len=42)
            if not field_text:
                continue
            label = FIELD_LABELS.get(key, key)
            conf = value.get("confidence")
            try:
                conf_pct = int(round(float(conf or 0.0) * 100))
            except Exception:
                conf_pct = 0
            if conf_pct > 0:
                result_items.append(f"{label}为{field_text}（置信度{conf_pct}%）")
            else:
                result_items.append(f"{label}为{field_text}")
            if len(result_items) >= 6:
                break
        if result_items:
            lines.append("已抽取的关键信息包括：" + "；".join(result_items) + "。")

        trace_hits = self._summary_trace_hit_dicts(req)
        content_focus_raw: List[str] = []
        table_focus_raw: List[str] = []
        image_focus_raw: List[str] = []
        trace_table_ids: Set[str] = set()
        trace_image_ids: Set[str] = set()

        for hit in trace_hits:
            kind = self._trace_display_kind_from_hit(hit)
            locator = hit.get("locator") if isinstance(hit.get("locator"), dict) else {}
            object_id = str(hit.get("object_id", "")).strip()
            object_key = object_id.lower()
            object_unique_key = (
                object_key
                or str(hit.get("ref_id", "")).strip()
                or self._summary_clean_text(hit.get("snippet"), max_len=48)
            )
            snippet = self._summary_clean_text(hit.get("snippet"), max_len=72)

            if kind == "field":
                if snippet:
                    label = FIELD_LABELS.get(object_key, object_id) if object_key else object_id
                    content_focus_raw.append(f"{label}：{snippet}" if label else snippet)
                continue

            if kind == "table":
                if object_unique_key:
                    trace_table_ids.add(object_unique_key)
                sheet_name = self._summary_clean_text(locator.get("sheet_name"), max_len=24)
                table_preview = locator.get("table_preview") if isinstance(locator.get("table_preview"), dict) else {}
                headers_raw = table_preview.get("headers") if isinstance(table_preview.get("headers"), list) else []
                headers = self._summary_unique_texts(headers_raw, limit=3, max_len=18)
                if headers:
                    header_text = " / ".join(headers)
                    table_focus_raw.append(
                        f"{sheet_name}表格包含 {header_text}" if sheet_name else f"表格包含 {header_text}"
                    )
                elif snippet:
                    table_focus_raw.append(snippet)
                continue

            if kind == "image":
                if object_unique_key:
                    trace_image_ids.add(object_unique_key)
                caption = self._summary_clean_text(locator.get("caption"), max_len=64)
                key_points = self._summary_unique_texts(
                    locator.get("key_points") if isinstance(locator.get("key_points"), list) else [],
                    limit=2,
                    max_len=48,
                )
                text_blocks = self._summary_unique_texts(
                    locator.get("text_blocks") if isinstance(locator.get("text_blocks"), list) else [],
                    limit=2,
                    max_len=48,
                )
                image_focus_raw.append(
                    caption
                    or (key_points[0] if key_points else "")
                    or (text_blocks[0] if text_blocks else "")
                    or snippet
                )

        content_focus = self._summary_unique_texts(content_focus_raw, limit=3, max_len=78)
        if content_focus:
            lines.append("从原文与溯源片段看，文档重点涉及：" + "；".join(content_focus) + "。")

        table_focus = self._summary_unique_texts(table_focus_raw, limit=2, max_len=54)
        image_focus = self._summary_unique_texts(image_focus_raw, limit=2, max_len=54)

        diag = req.diagnostics if isinstance(getattr(req, "diagnostics", None), dict) else {}
        trace_display_counts = diag.get("trace_display_counts") if isinstance(diag.get("trace_display_counts"), dict) else {}
        table_count = int(diag.get("table_count", 0) or 0)
        image_count = int(diag.get("figure_count", 0) or 0)
        table_count = max(table_count, len(trace_table_ids), int(trace_display_counts.get("table", 0) or 0))
        image_count = max(image_count, len(trace_image_ids), int(trace_display_counts.get("image", 0) or 0))

        structure_parts: List[str] = []
        if table_count > 0:
            table_part = f"{table_count} 个表格"
            if table_focus:
                table_part += f"（如：{'；'.join(table_focus)}）"
            structure_parts.append(table_part)
        if image_count > 0:
            image_part = f"{image_count} 处图片"
            if image_focus:
                image_part += f"（如：{'；'.join(image_focus)}）"
            structure_parts.append(image_part)
        if structure_parts:
            lines.append("识别到的结构内容包括" + "，".join(structure_parts) + "。")

        if not result_items and not content_focus and not structure_parts:
            lines.append("当前已完成基础解析，但尚未形成足够稳定的内容摘要，建议结合抽取结果与溯源定位继续查看。")

        notices: List[str] = []
        errors = list(getattr(req, "errors", []) or [])
        soft_warnings = list(getattr(req, "soft_warnings", []) or [])
        error_items = self._summary_unique_texts(
            [self._summary_notice_text(item) for item in errors if self._summary_notice_text(item)],
            limit=2,
            max_len=64,
        )
        warning_items = self._summary_unique_texts(
            [self._summary_notice_text(item) for item in soft_warnings if self._summary_notice_text(item)],
            limit=2,
            max_len=64,
        )
        if error_items:
            notices.append("需关注：" + "；".join(error_items))
        if warning_items:
            notices.append("提示：" + "；".join(warning_items))
        if notices:
            lines.append(" ".join(notices) + "。")

        summary = " ".join(line.strip() for line in lines if line and line.strip()).strip()
        max_chars = int(getattr(req, "max_chars", 400) or 400)
        if len(summary) > max_chars:
            summary = summary[: max_chars - 1].rstrip() + "…"
        return summary

    @staticmethod
    def _summary_clean_text(value: Any, max_len: int = 80) -> str:
        text = re.sub(r"\s+", " ", str(value or "")).strip()
        if not text:
            return ""
        if len(text) <= max_len:
            return text
        return text[: max_len - 1].rstrip("，,；;。 ") + "…"

    def _summary_unique_texts(self, values: List[Any], limit: int = 4, max_len: int = 80) -> List[str]:
        out: List[str] = []
        seen: Set[str] = set()
        for value in values:
            cleaned = self._summary_clean_text(value, max_len=max_len)
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(cleaned)
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _summary_trace_hit_dicts(req: Any) -> List[Dict[str, Any]]:
        hits: List[Dict[str, Any]] = []
        for item in getattr(req, "trace_hits", []) or []:
            if isinstance(item, dict):
                hits.append(dict(item))
                continue
            if hasattr(item, "model_dump"):
                payload = item.model_dump(mode="json")
                if isinstance(payload, dict):
                    hits.append(payload)
        return hits

    def _summary_notice_text(self, raw_notice: Any) -> str:
        text = str(raw_notice or "").strip()
        if not text or text in SUMMARY_NOTICE_SKIP:
            return ""
        for prefix, mapped in SUMMARY_NOTICE_MAP.items():
            if text == prefix or text.startswith(f"{prefix}:"):
                return mapped
        return self._summary_clean_text(text, max_len=64)
