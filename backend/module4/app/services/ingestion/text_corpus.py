from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable

_REF_TAG_PATTERN = re.compile(r"<ref[^>]*>(.*?)</ref>", flags=re.IGNORECASE | re.DOTALL)
_MULTI_SPACE_PATTERN = re.compile(r"[ \t]+")
_ARTIFACT_ID_PATTERN = re.compile(
    r"\b(?:page[_-]?\d+[_-]?(?:table|figure|chart|image)?[_-]?\d*|(?:table|figure|chart|image|fig|img)[_-]?\d+|pdf_mineru_gemini_t\d+)\b",
    flags=re.IGNORECASE,
)
_XLSX_REF_ID_PATTERN = re.compile(r"\bxlsx_[a-z0-9_]+\b", flags=re.IGNORECASE)
_MARKDOWN_TABLE_DIVIDER_PATTERN = re.compile(r"^\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?$")

_MOJIBAKE_MARKERS: tuple[str, ...] = (
    "锛",
    "銆",
    "鈥",
    "鈩",
    "锟",
    "鍙",
    "鍚",
    "鍥",
    "鍒",
    "涓",
    "鏂",
    "闂",
    "绔",
    "鐨",
    "甯",
    "棰",
    "鎺",
    "鑺",
    "鍩庡",
    "鐩戞祴",
    "鏃堕棿",
    "绌烘皵",
    "璐ㄩ噺",
    "绔欑偣",
    "姹℃煋",
    "棰楃矑",
)

_JSON_TEXT_KEYS: tuple[str, ...] = (
    "summary",
    "caption",
    "title",
    "description",
    "analysis",
    "conclusion",
    "observation",
    "observations",
    "insight",
    "insights",
    "narrative",
    "text",
    "content",
)

_JSON_STRUCTURAL_KEYS: tuple[str, ...] = (
    "tables",
    "figures",
    "rows",
    "cells",
    "headers",
    "header_meta",
    "table_preview",
    "dataframe",
)

_EMPTY_CELL_VALUES = {"", "-", "--", "—", "N/A", "n/a", "null", "None", "nan"}

_XLSX_ROW_LIMIT = max(1, int(os.getenv("MODULE4_XLSX_CORPUS_ROW_LIMIT", "24")))
_XLSX_COL_LIMIT = max(1, int(os.getenv("MODULE4_XLSX_CORPUS_COL_LIMIT", "12")))
_XLSX_HEADER_LIMIT = max(1, int(os.getenv("MODULE4_XLSX_CORPUS_HEADER_LIMIT", "24")))


def _module4_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _repo_root() -> Path:
    configured = str(os.getenv("SMART_DOC_FLOW_RUNTIME_ROOT", "") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return _module4_root().parents[1]


def _runtime_data_root() -> Path:
    configured = str(os.getenv("SMART_DOC_FLOW_DATA_ROOT", "") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    repo_root = _repo_root()
    candidate = (repo_root / "runtime-data").resolve()
    if candidate.exists():
        return candidate
    return repo_root


def _module2_artifact_root() -> Path:
    configured = str(os.getenv("MODULE2_ARTIFACT_ROOT_DIR", "") or "").strip()
    if configured:
        candidate = Path(configured)
        if candidate.is_absolute():
            return candidate.resolve()
        normalized = configured.replace("\\", "/").strip().lstrip("/")
        repo_candidate = (_repo_root() / normalized).resolve()
        runtime_candidate = (_runtime_data_root() / normalized).resolve()
        if repo_candidate.exists():
            return repo_candidate
        if runtime_candidate.exists():
            return runtime_candidate
        return repo_candidate
    return (_runtime_data_root() / "module2" / "artifacts").resolve()


def _resolve_artifact_path(path_value: Any) -> Path | None:
    raw = str(path_value or "").strip()
    if not raw:
        return None

    direct = Path(raw)
    if direct.is_absolute():
        try:
            resolved = direct.resolve()
        except Exception:
            return None
        return resolved if resolved.exists() and resolved.is_file() else None

    normalized = raw.replace("\\", "/").strip().lstrip("/")
    repo_root = _repo_root()
    runtime_data_root = _runtime_data_root()
    module2_artifact_root = _module2_artifact_root()

    candidates = [
        (Path.cwd() / normalized).resolve(),
        (module2_artifact_root / normalized).resolve(),
        (runtime_data_root / normalized).resolve(),
        (runtime_data_root / "module2" / normalized).resolve(),
        (runtime_data_root / "module2" / "artifacts" / normalized).resolve(),
        (repo_root / normalized).resolve(),
        (repo_root / "runtime-data" / "module2" / "artifacts" / normalized).resolve(),
    ]
    for candidate in candidates:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate
        except Exception:
            continue
    return None


def _read_text(path_value: str) -> str:
    path = _resolve_artifact_path(path_value)
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _read_json(path_value: str) -> dict[str, Any]:
    raw = _read_text(path_value)
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _strip_ref_tags(text: str) -> str:
    return _REF_TAG_PATTERN.sub(r"\1", str(text or ""))


def _normalize_scalar(value: Any) -> str:
    text = str(value or "").replace("\x00", " ").strip()
    return _MULTI_SPACE_PATTERN.sub(" ", text).strip()


def _looks_like_mojibake(text: Any) -> bool:
    value = _normalize_scalar(text)
    if not value:
        return False
    if "\ufffd" in value:
        return True
    hit_count = sum(value.count(marker) for marker in _MOJIBAKE_MARKERS)
    threshold = max(2, len(value) // 24)
    return hit_count >= threshold


def _is_empty_or_placeholder(value: Any) -> bool:
    return _normalize_scalar(value) in _EMPTY_CELL_VALUES


def _has_language_signal(text: str) -> bool:
    return any(ch.isalpha() or ("\u4e00" <= ch <= "\u9fff") for ch in text)


def _looks_like_display_shell_line(line: str) -> bool:
    normalized = _normalize_scalar(line)
    if not normalized:
        return True
    lowered = normalized.lower()
    if _MARKDOWN_TABLE_DIVIDER_PATTERN.fullmatch(normalized):
        return True
    if _XLSX_REF_ID_PATTERN.fullmatch(normalized):
        return True
    if _ARTIFACT_ID_PATTERN.fullmatch(lowered):
        return True
    if lowered in {
        "artifact_path",
        "artifact_url",
        "bbox",
        "ref_id",
        "page",
        "table_id",
        "figure_id",
        "image_id",
        "rows",
        "cells",
        "headers",
        "header_meta",
    }:
        return True
    if lowered.startswith(("artifact_path:", "artifact_url:", "bbox:", "ref_id:", "page:")):
        return True
    if lowered.startswith(("图 ", "图表", "图像", "图片", "figure ", "table ", "表 ")) and not any(
        token in normalized for token in ("增长", "下降", "达到", "同比", "环比", "增加", "减少", "显示", "表明", "指出", "摘要", "分析")
    ):
        return True
    if normalized.startswith("{") or normalized.startswith("}") or normalized.startswith("[") or normalized.startswith("]"):
        return True
    if "|" in normalized and not _has_language_signal(normalized.replace("|", "")):
        return True
    return False


def _normalize_fragment_text(value: Any, *, keep_structured: bool = True) -> str:
    text = _strip_ref_tags(str(value or ""))
    if not text.strip():
        return ""

    lines: list[str] = []
    for raw_line in text.splitlines():
        line = _normalize_scalar(raw_line)
        if not line:
            continue
        if _looks_like_mojibake(line):
            continue
        if _looks_like_display_shell_line(line):
            continue
        line = _ARTIFACT_ID_PATTERN.sub("", line).strip()
        if not line:
            continue
        line = _XLSX_REF_ID_PATTERN.sub("", line).strip()
        if not line or _looks_like_display_shell_line(line):
            continue
        if line.count("|") >= 2:
            if not any(token in line for token in ("增长", "下降", "达到", "同比", "环比", "增加", "减少")):
                continue
            line = "，".join(part.strip() for part in line.split("|") if part.strip())
        if line:
            lines.append(line)

    if not lines:
        return ""

    merged = "\n".join(lines)
    if not keep_structured:
        merged = merged.replace("\n", " ")
    merged = _MULTI_SPACE_PATTERN.sub(" ", merged)
    return merged.strip()


def _push_unique(
    out: list[tuple[str, str]],
    seen: set[str],
    text: Any,
    *,
    bucket: str,
    keep_structured: bool = True,
) -> None:
    cleaned = _normalize_fragment_text(text, keep_structured=keep_structured)
    if not cleaned:
        return
    dedupe_key = cleaned.casefold()
    if dedupe_key in seen:
        return
    seen.add(dedupe_key)
    out.append((cleaned, bucket))


def _stringify_cell_value(value: Any) -> str:
    text = _normalize_scalar(value)
    if _is_empty_or_placeholder(text):
        return ""
    return text


def _format_fact_pairs(pairs: Iterable[tuple[str, str]], *, prefix: str | None = None) -> str:
    parts = [f"{key}为{value}" for key, value in pairs if key and value]
    if not parts:
        return ""
    base = "，".join(parts)
    if prefix:
        return f"{prefix}：{base}。"
    return f"{base}。"


def _table_row_pairs_from_cells(cells: list[dict[str, Any]], *, limit: int) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        header = _normalize_scalar(cell.get("header") or cell.get("header_norm"))
        value = _stringify_cell_value(cell.get("text") or cell.get("value") or cell.get("normalized_text"))
        if not header or not value:
            continue
        if _XLSX_REF_ID_PATTERN.fullmatch(value):
            continue
        pairs.append((header, value))
        if len(pairs) >= limit:
            break
    return pairs


def _table_row_pairs_from_dataframe(
    headers: list[str],
    rows: list[Any],
    *,
    limit_rows: int,
    limit_cols: int,
) -> list[list[tuple[str, str]]]:
    collected: list[list[tuple[str, str]]] = []
    for row in rows[:limit_rows]:
        if not isinstance(row, list):
            continue
        pairs: list[tuple[str, str]] = []
        for index, value in enumerate(row[:limit_cols]):
            header = _normalize_scalar(headers[index] if index < len(headers) else f"列{index + 1}")
            cell_value = _stringify_cell_value(value)
            if not header or not cell_value:
                continue
            pairs.append((header, cell_value))
        if pairs:
            collected.append(pairs)
    return collected


def _table_row_sentences(table: dict[str, Any]) -> list[str]:
    context_title = _normalize_fragment_text(table.get("sheet_name") or table.get("title") or table.get("caption"), keep_structured=False)
    sentences: list[str] = []

    rows = table.get("rows")
    if isinstance(rows, list):
        for row in rows[:_XLSX_ROW_LIMIT]:
            if not isinstance(row, dict):
                continue
            cells = row.get("cells")
            if not isinstance(cells, list):
                continue
            pairs = _table_row_pairs_from_cells(cells, limit=_XLSX_COL_LIMIT)
            sentence = _format_fact_pairs(
                pairs,
                prefix=f"{context_title}中的记录" if context_title else "表格记录",
            )
            if sentence:
                sentences.append(sentence)

    for frame_key in ("table_preview", "dataframe"):
        frame = table.get(frame_key)
        if not isinstance(frame, dict):
            continue
        headers = [_normalize_scalar(item) for item in list(frame.get("headers") or []) if _normalize_scalar(item)]
        frame_rows = frame.get("rows")
        if not isinstance(frame_rows, list):
            continue
        for pairs in _table_row_pairs_from_dataframe(
            headers,
            frame_rows,
            limit_rows=_XLSX_ROW_LIMIT,
            limit_cols=_XLSX_COL_LIMIT,
        ):
            sentence = _format_fact_pairs(
                pairs,
                prefix=f"{context_title}中的记录" if context_title else "表格记录",
            )
            if sentence:
                sentences.append(sentence)

    return sentences


def _collect_text_values_from_selected_keys(value: Any) -> list[str]:
    out: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, item in node.items():
                key_value = str(key or "").strip().lower()
                if key_value in _JSON_STRUCTURAL_KEYS:
                    continue
                if key_value not in _JSON_TEXT_KEYS:
                    if isinstance(item, (dict, list)):
                        walk(item)
                    continue
                if isinstance(item, list):
                    for entry in item:
                        walk(entry)
                    continue
                cleaned = _normalize_fragment_text(item, keep_structured=False)
                if cleaned:
                    out.append(cleaned)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        cleaned = _normalize_fragment_text(node, keep_structured=False)
        if cleaned:
            out.append(cleaned)

    walk(value)
    return out


def _collect_payload_text_fragments(payload: Dict[str, Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    tables = payload.get("tables")
    if isinstance(tables, list):
        for table in tables[:64]:
            if not isinstance(table, dict):
                continue
            _push_unique(out, seen, table.get("summary"), bucket="primary", keep_structured=False)
            _push_unique(out, seen, table.get("caption"), bucket="secondary", keep_structured=False)
            _push_unique(out, seen, table.get("title"), bucket="secondary", keep_structured=False)

            headers = [_normalize_scalar(item) for item in list(table.get("headers") or []) if _normalize_scalar(item)]
            if headers:
                _push_unique(out, seen, f"表格字段：{'，'.join(headers[:_XLSX_HEADER_LIMIT])}", bucket="secondary")

            for sentence in _table_row_sentences(table):
                _push_unique(out, seen, sentence, bucket="primary")

    figures = payload.get("figures")
    if isinstance(figures, list):
        for figure in figures[:64]:
            if not isinstance(figure, dict):
                continue
            _push_unique(out, seen, figure.get("summary"), bucket="primary", keep_structured=False)
            _push_unique(out, seen, figure.get("caption"), bucket="secondary", keep_structured=False)
            _push_unique(out, seen, figure.get("title"), bucket="secondary", keep_structured=False)
            key_points = figure.get("key_points")
            if isinstance(key_points, list):
                for point in key_points[:24]:
                    _push_unique(out, seen, point, bucket="primary", keep_structured=False)

    for text in _collect_text_values_from_selected_keys(payload):
        _push_unique(out, seen, text, bucket="secondary", keep_structured=False)

    return out


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _inflate_compact_xlsx_rows_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    version = str(payload.get("version") or "").strip().lower()
    rows = payload.get("rows")
    if version != "module2-xlsx-sheet-rows-v2" or not isinstance(rows, list):
        return payload

    headers = list(payload.get("headers") or [])
    inflated_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 3:
            continue
        row_index = _coerce_int(row[0], 0)
        source_row_index = _coerce_int(row[1], row_index)
        cells_blob = row[2]
        if not isinstance(cells_blob, list):
            continue

        inflated_cells: list[dict[str, Any]] = []
        for cell in cells_blob:
            if not isinstance(cell, list) or len(cell) < 2:
                continue
            col_index = _coerce_int(cell[0], 0)
            if col_index <= 0:
                continue
            text = _normalize_scalar(cell[1])
            if not text:
                continue
            header = _normalize_scalar(headers[col_index - 1] if col_index <= len(headers) else f"列{col_index}")
            cell_ref = _normalize_scalar(cell[2]) if len(cell) >= 3 else ""
            inflated_cells.append(
                {
                    "col_index": col_index,
                    "header": header,
                    "text": text,
                    "ref_id": cell_ref,
                }
            )

        if inflated_cells:
            inflated_rows.append(
                {
                    "row_index": row_index,
                    "source_row_index": source_row_index,
                    "cells": inflated_cells,
                }
            )

    inflated_payload = dict(payload)
    inflated_payload["rows"] = inflated_rows
    return inflated_payload


def _append_xlsx_sheet_rows_artifact(path_value: Any, *, push: Callable[..., None]) -> None:
    payload = _inflate_compact_xlsx_rows_payload(_read_json(str(path_value or "")))
    if not payload:
        return

    sheet_name = _normalize_scalar(payload.get("sheet_name"))
    headers = [_normalize_scalar(item) for item in list(payload.get("headers") or []) if _normalize_scalar(item)]
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return

    if sheet_name:
        push(f"工作表名称：{sheet_name}", bucket="secondary")
    if headers:
        push(f"工作表字段：{'，'.join(headers[:_XLSX_HEADER_LIMIT])}", bucket="secondary")

    for row in rows[:_XLSX_ROW_LIMIT]:
        if not isinstance(row, dict):
            continue
        cells = row.get("cells")
        if not isinstance(cells, list):
            continue
        pairs = _table_row_pairs_from_cells(cells, limit=_XLSX_COL_LIMIT)
        sentence = _format_fact_pairs(
            pairs,
            prefix=f"工作表“{sheet_name}”中的记录" if sheet_name else "工作表记录",
        )
        if sentence:
            push(sentence, bucket="primary")


def _append_xlsx_workbook_manifest_artifact(path_value: Any, *, push: Callable[..., None]) -> None:
    manifest = _read_json(str(path_value or ""))
    if not manifest:
        return

    file_name = _normalize_scalar(manifest.get("file_name"))
    sheet_count = _coerce_int(manifest.get("sheet_count"), 0)
    total_rows = _coerce_int(manifest.get("source_total_rows"), 0)
    if file_name:
        push(f"工作簿文件：{file_name}", bucket="secondary")
    if sheet_count > 0 or total_rows > 0:
        push(f"工作簿概览：工作表 {sheet_count} 个，源数据行数 {total_rows}", bucket="secondary")

    sheets = manifest.get("sheets")
    if not isinstance(sheets, list):
        return

    for sheet in sheets[: max(1, _XLSX_HEADER_LIMIT)]:
        if not isinstance(sheet, dict):
            continue
        sheet_index = _coerce_int(sheet.get("sheet_index"), 0)
        sheet_name = _normalize_scalar(sheet.get("sheet_name"))
        headers = [_normalize_scalar(item) for item in list(sheet.get("headers") or []) if _normalize_scalar(item)]
        non_empty_rows = _coerce_int(sheet.get("source_nonempty_row_count"), 0)
        label = sheet_name or f"工作表 {sheet_index}"

        push(f"工作表：{label}", bucket="secondary")
        if headers:
            push(f"{label}字段：{'，'.join(headers[:_XLSX_HEADER_LIMIT])}", bucket="secondary")
        if non_empty_rows > 0:
            push(f"{label}非空行数：{non_empty_rows}", bucket="secondary")

        rows_artifact_path = _normalize_scalar(sheet.get("rows_artifact_path"))
        if rows_artifact_path:
            _append_xlsx_sheet_rows_artifact(rows_artifact_path, push=push)


def _append_xlsx_artifact_texts(doc: Dict[str, Any], *, push: Callable[..., None]) -> None:
    diagnostics = doc.get("diagnostics") if isinstance(doc.get("diagnostics"), dict) else {}
    source_texts = doc.get("source_texts") if isinstance(doc.get("source_texts"), list) else []

    manifest_paths: list[str] = []
    sheet_rows_paths: list[str] = []
    seen_manifest_paths: set[str] = set()
    seen_sheet_paths: set[str] = set()

    def register_manifest(path_value: Any) -> None:
        path = _normalize_scalar(path_value)
        if not path or path in seen_manifest_paths:
            return
        seen_manifest_paths.add(path)
        manifest_paths.append(path)

    def register_sheet(path_value: Any) -> None:
        path = _normalize_scalar(path_value)
        if not path or path in seen_sheet_paths:
            return
        seen_sheet_paths.add(path)
        sheet_rows_paths.append(path)

    register_manifest(diagnostics.get("xlsx_workbook_manifest_path"))
    register_manifest(diagnostics.get("xlsx_workbook_manifest_artifact_path"))
    register_sheet(diagnostics.get("xlsx_sheet_rows_artifact_path"))
    register_sheet(diagnostics.get("xlsx_sheet_rows_path"))

    for entry in source_texts:
        if not isinstance(entry, dict):
            continue
        kind = _normalize_scalar(entry.get("kind") or entry.get("source_kind")).lower()
        artifact_path = _normalize_scalar(entry.get("artifact_path"))
        if not artifact_path:
            continue
        if "xlsx_workbook_manifest" in kind:
            register_manifest(artifact_path)
        elif "xlsx_sheet_rows" in kind:
            register_sheet(artifact_path)

    for path in manifest_paths:
        _append_xlsx_workbook_manifest_artifact(path, push=push)
    for path in sheet_rows_paths:
        _append_xlsx_sheet_rows_artifact(path, push=push)


def _append_field_results_artifact(doc: Dict[str, Any], *, push: Callable[..., None]) -> None:
    diagnostics = doc.get("diagnostics") if isinstance(doc.get("diagnostics"), dict) else {}
    payload = _read_json(_normalize_scalar(diagnostics.get("field_results_artifact_path")))
    fields = payload.get("fields")
    if not isinstance(fields, list):
        return
    for field in fields[:64]:
        if not isinstance(field, dict):
            continue
        field_name = _normalize_fragment_text(field.get("field_name"), keep_structured=False)
        value = _normalize_fragment_text(field.get("value"), keep_structured=False)
        if not field_name or not value:
            continue
        push(f"字段抽取结果：{field_name}为{value}。", bucket="secondary")


def _append_source_text_entries(doc: Dict[str, Any], *, push: Callable[..., None]) -> None:
    source_texts = doc.get("source_texts")
    if not isinstance(source_texts, list):
        return
    for item in source_texts[:24]:
        if not isinstance(item, dict):
            continue
        source_kind = _normalize_scalar(item.get("kind") or item.get("source_kind")).lower()
        bucket = "secondary" if source_kind in {"trace", "locator", "artifact_meta"} else "primary"
        push(item.get("text"), bucket=bucket)

        artifact_path = _normalize_scalar(item.get("artifact_path"))
        suffix = Path(artifact_path).suffix.lower()
        if artifact_path and suffix in {".txt", ".md"}:
            push(_read_text(artifact_path), bucket=bucket)


def _append_module2_artifact_texts(doc: Dict[str, Any], *, push: Callable[..., None]) -> None:
    diagnostics = doc.get("diagnostics") if isinstance(doc.get("diagnostics"), dict) else {}

    markdown_path = _normalize_scalar(
        diagnostics.get("assistant1_source_markdown_artifact_path") or diagnostics.get("markdown_artifact_path")
    )
    markdown_text = _read_text(markdown_path)
    if markdown_text and not _looks_like_mojibake(markdown_text):
        push(_strip_ref_tags(markdown_text), bucket="primary")

    assistant_payload_path = _normalize_scalar(diagnostics.get("assistant_payload_artifact_path"))
    payload = _read_json(assistant_payload_path)
    for fragment, bucket in _collect_payload_text_fragments(payload):
        push(fragment, bucket=bucket)

    _append_xlsx_artifact_texts(doc, push=push)
    _append_field_results_artifact(doc, push=push)


def _compose_document_text(doc: Dict[str, Any]) -> str:
    title_fragments: list[str] = []
    primary_fragments: list[str] = []
    secondary_fragments: list[str] = []
    seen: set[str] = set()

    def push(text: Any, *, bucket: str = "primary") -> None:
        cleaned = _normalize_fragment_text(text, keep_structured=(bucket != "title"))
        if not cleaned:
            return
        dedupe_key = cleaned.casefold()
        if dedupe_key in seen:
            return
        seen.add(dedupe_key)
        if bucket == "title":
            title_fragments.append(cleaned)
        elif bucket == "secondary":
            secondary_fragments.append(cleaned)
        else:
            primary_fragments.append(cleaned)

    file_name = _normalize_scalar(doc.get("file_name"))
    if file_name:
        push(f"文档标题：{file_name}", bucket="title")

    push(doc.get("text_corpus"), bucket="primary")
    _append_source_text_entries(doc, push=push)
    _append_module2_artifact_texts(doc, push=push)

    for key in ("normalized_text", "text", "content", "markdown", "raw_text"):
        push(doc.get(key), bucket="primary")

    result = doc.get("result")
    if isinstance(result, dict):
        for field_name, entity in result.items():
            value = entity.get("value") if isinstance(entity, dict) else entity
            field_name_text = _normalize_fragment_text(field_name, keep_structured=False)
            value_text = _normalize_fragment_text(value, keep_structured=False)
            if field_name_text and value_text:
                push(f"字段抽取结果：{field_name_text}为{value_text}。", bucket="secondary")

    trace_hits = doc.get("trace_hits")
    if isinstance(trace_hits, list):
        for hit in trace_hits[:24]:
            if not isinstance(hit, dict):
                continue
            push(hit.get("snippet"), bucket="secondary")
            locator = hit.get("locator")
            if isinstance(locator, dict):
                for locator_key in ("summary", "caption", "title"):
                    push(locator.get(locator_key), bucket="secondary")

    fragments = title_fragments + primary_fragments + secondary_fragments
    return "\n".join(fragment for fragment in fragments if fragment).strip()
