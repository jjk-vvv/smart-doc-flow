from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import urllib.parse
from pathlib import Path
from typing import Any

from app.modules.module2.schemas.extraction import (
    DocumentExtractionResponse,
    SummarizeRequest,
    SummarizeResponse,
    TraceHit,
    TraceLocateRequest,
    TraceLocateResponse,
)


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
    "word_pdf_parse_timeout_fallback_fasttrack": (
        "Word 转 PDF 后的深度版面解析超时，当前已切换为快速解析链路，图表完整度可能受影响。"
    ),
    "pdf_visual_timeout_fallback_fasttrack": (
        "PDF 视觉解析超时，当前已切换为快速解析链路，复杂版面定位可能不够完整。"
    ),
}


def summarize_document(payload: SummarizeRequest) -> SummarizeResponse:
    return SummarizeResponse(summary=_summarize_document_payload(payload))


def trace_locate(payload: TraceLocateRequest) -> TraceLocateResponse:
    document = payload.document
    source_hits = _trace_hits_from_document(document)
    all_hits = _filter_trace_hits(
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
    return TraceLocateResponse(
        hit_count=len(all_hits),
        truncated=len(all_hits) > len(hits),
        hits=[TraceHit.model_validate(item) for item in hits],
    )


def _trace_hits_from_document(document: DocumentExtractionResponse) -> list[dict[str, Any]]:
    source_hits = [item.model_dump(mode="json") for item in document.trace_hits]
    enriched_hits = _enrich_trace_hits_from_assistant_payload(document)
    if source_hits:
        if enriched_hits:
            return _merge_trace_hits(source_hits, enriched_hits)
        return source_hits

    result_map = document.result.root if isinstance(document.result.root, dict) else {}
    field_hits: list[dict[str, Any]] = []
    for field_name, entity in result_map.items():
        ref_id = str(entity.source_ref_id or "").strip() or None
        bbox = list(entity.bbox or []) if isinstance(entity.bbox, list) else []
        page = _page_from_bbox(bbox)
        value_text = entity.value if entity.value is not None else "null"
        field_hits.append(
            {
                "file_name": document.file_name,
                "file_hash": document.file_hash,
                "object_type": "field",
                "object_id": str(field_name),
                "ref_id": ref_id,
                "page": page,
                "snippet": f"{field_name}: {value_text}",
                "confidence": _safe_confidence(entity.confidence),
                "locator": {"page": page, "ref_id": ref_id},
                "bbox": bbox if len(bbox) == 5 else [],
                "artifact_path": None,
                "artifact_url": None,
                "match_reason": "field_match",
            }
        )
    if enriched_hits:
        return _merge_trace_hits(field_hits, enriched_hits)
    return field_hits


def _filter_trace_hits(
    hits: list[dict[str, Any]],
    *,
    field_name: str = "",
    file_name: str = "",
    file_hash: str = "",
    ref_id: str = "",
    object_type: str = "",
    keyword: str = "",
) -> list[dict[str, Any]]:
    normalized_field_name = str(field_name or "").strip().lower()
    normalized_file_name = str(file_name or "").strip().lower()
    normalized_file_hash = str(file_hash or "").strip().lower()
    normalized_ref_id = str(ref_id or "").strip()
    normalized_object_type = str(object_type or "").strip().lower()
    normalized_keyword = str(keyword or "").strip().lower()

    out: list[dict[str, Any]] = []
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


def _summarize_document_payload(req: SummarizeRequest) -> str:
    lines: list[str] = [f"文档《{req.file_name}》已完成内容解析。"]

    result_items: list[str] = []
    result_payload = req.result if isinstance(getattr(req, "result", None), dict) else {}
    for key, value in result_payload.items():
        entity = value if isinstance(value, dict) else {}
        field_val = entity.get("value")
        if field_val in (None, "", [], {}):
            continue

        field_text = _summary_clean_text(field_val, max_len=42)
        if not field_text:
            continue

        label = FIELD_LABELS.get(str(key).lower(), str(key))
        conf = entity.get("confidence")
        try:
            conf_pct = int(round(float(conf or 0.0) * 100))
        except (TypeError, ValueError):
            conf_pct = 0

        if conf_pct > 0:
            result_items.append(f"{label}为{field_text}（置信度{conf_pct}%）")
        else:
            result_items.append(f"{label}为{field_text}")
        if len(result_items) >= 6:
            break

    if result_items:
        lines.append("已抽取的关键信息包括：" + "；".join(result_items) + "。")

    trace_hits = _summary_trace_hit_dicts(req)
    content_focus_raw: list[str] = []
    table_focus_raw: list[str] = []
    image_focus_raw: list[str] = []
    trace_table_ids: set[str] = set()
    trace_image_ids: set[str] = set()

    for hit in trace_hits:
        kind = _trace_display_kind_from_hit(hit)
        locator = hit.get("locator") if isinstance(hit.get("locator"), dict) else {}
        object_id = str(hit.get("object_id", "")).strip()
        object_key = object_id.lower()
        object_unique_key = (
            object_key
            or str(hit.get("ref_id", "")).strip()
            or _summary_clean_text(hit.get("snippet"), max_len=48)
        )
        snippet = _summary_clean_text(hit.get("snippet"), max_len=72)

        if kind == "field":
            if snippet:
                label = FIELD_LABELS.get(object_key, object_id) if object_key else object_id
                content_focus_raw.append(f"{label}：{snippet}" if label else snippet)
            continue

        if kind == "table":
            if object_unique_key:
                trace_table_ids.add(object_unique_key)
            sheet_name = _summary_clean_text(locator.get("sheet_name"), max_len=24)
            table_preview = locator.get("table_preview") if isinstance(locator.get("table_preview"), dict) else {}
            headers_raw = table_preview.get("headers") if isinstance(table_preview.get("headers"), list) else []
            headers = _summary_unique_texts(headers_raw, limit=3, max_len=18)
            if headers:
                header_text = " / ".join(headers)
                if sheet_name:
                    table_focus_raw.append(f"{sheet_name}表格包含 {header_text}")
                else:
                    table_focus_raw.append(f"表格包含 {header_text}")
            elif snippet:
                table_focus_raw.append(snippet)
            continue

        if kind == "image":
            if object_unique_key:
                trace_image_ids.add(object_unique_key)
            caption = _summary_clean_text(locator.get("caption"), max_len=64)
            key_points = _summary_unique_texts(
                locator.get("key_points") if isinstance(locator.get("key_points"), list) else [],
                limit=2,
                max_len=48,
            )
            text_blocks = _summary_unique_texts(
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

    content_focus = _summary_unique_texts(content_focus_raw, limit=3, max_len=78)
    if content_focus:
        lines.append("从原文与溯源片段看，文档重点涉及：" + "；".join(content_focus) + "。")

    table_focus = _summary_unique_texts(table_focus_raw, limit=2, max_len=54)
    image_focus = _summary_unique_texts(image_focus_raw, limit=2, max_len=54)

    diag = req.diagnostics if isinstance(getattr(req, "diagnostics", None), dict) else {}
    trace_display_counts = diag.get("trace_display_counts") if isinstance(diag.get("trace_display_counts"), dict) else {}
    table_count = int(diag.get("table_count", 0) or 0)
    image_count = int(diag.get("figure_count", 0) or 0)
    table_count = max(table_count, len(trace_table_ids), int(trace_display_counts.get("table", 0) or 0))
    image_count = max(image_count, len(trace_image_ids), int(trace_display_counts.get("image", 0) or 0))

    structure_parts: list[str] = []
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
        lines.append("识别到的结构内容包括" + "、".join(structure_parts) + "。")

    if not result_items and not content_focus and not structure_parts:
        lines.append("当前已完成基础解析，但尚未形成足够稳定的内容摘要，建议结合抽取结果与溯源定位继续查看。")

    notices: list[str] = []
    errors = list(getattr(req, "errors", []) or [])
    soft_warnings = list(getattr(req, "soft_warnings", []) or [])
    error_items = _summary_unique_texts(
        [_summary_notice_text(item) for item in errors if _summary_notice_text(item)],
        limit=2,
        max_len=64,
    )
    warning_items = _summary_unique_texts(
        [_summary_notice_text(item) for item in soft_warnings if _summary_notice_text(item)],
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
        summary = summary[: max_chars - 1].rstrip("；，。 ") + "…"
    return summary


def _trace_display_kind_from_hit(hit: dict[str, Any]) -> str:
    object_type = str(hit.get("object_type") or "").strip().lower()
    if object_type in {"field", "table"}:
        return object_type
    if object_type != "figure":
        return "other"

    locator = hit.get("locator") if isinstance(hit.get("locator"), dict) else {}
    figure_type = str(locator.get("figure_type") or "").strip().lower()
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


def _summary_clean_text(value: Any, max_len: int = 80) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip("；，。 ") + "…"


def _summary_unique_texts(values: list[Any], limit: int = 4, max_len: int = 80) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _summary_clean_text(value, max_len=max_len)
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


def _summary_trace_hit_dicts(req: SummarizeRequest) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for item in getattr(req, "trace_hits", []) or []:
        if isinstance(item, dict):
            hits.append(dict(item))
            continue
        if hasattr(item, "model_dump"):
            payload = item.model_dump(mode="json")
            if isinstance(payload, dict):
                hits.append(payload)
    return hits


def _summary_notice_text(raw_notice: Any) -> str:
    text = str(raw_notice or "").strip()
    if not text or text in SUMMARY_NOTICE_SKIP:
        return ""
    for prefix, mapped in SUMMARY_NOTICE_MAP.items():
        if text == prefix or text.startswith(f"{prefix}:"):
            return mapped
    return _summary_clean_text(text, max_len=64)


def _project_root_dir() -> Path:
    return Path(__file__).resolve().parents[5]


def _artifact_root_dir() -> Path | None:
    env_candidates = [
        os.getenv("MODULE2_ARTIFACT_ROOT", ""),
        os.getenv("EXTRACTION_ARTIFACT_ROOT", ""),
    ]
    for raw in env_candidates:
        candidate = str(raw or "").strip()
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.exists() and path.is_dir():
            return path.resolve()

    default_candidates = [
        _project_root_dir() / "runtime-data" / "module2" / "artifacts",
        _project_root_dir() / "backend" / "app" / "modules" / "module2" / "runtime-data" / "module2" / "artifacts",
        # Legacy fallback path (kept during migration window).
        _project_root_dir() / "backend" / "module2" / "runtime-data" / "module2" / "artifacts",
    ]
    for candidate in default_candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()
    return None


def _safe_link_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name or "").strip()).strip("._")
    if not safe:
        return "artifact.bin"
    if len(safe) > 120:
        stem = Path(safe).stem[:96].rstrip("._-") or "artifact"
        ext = Path(safe).suffix[:16]
        safe = f"{stem}{ext}" if ext else stem
    return safe


def _artifact_url_from_fragment(fragment: str) -> str:
    cleaned = str(fragment or "").strip().strip("/")
    if not cleaned:
        return ""
    encoded = "/".join(urllib.parse.quote(seg, safe="") for seg in cleaned.split("/") if seg)
    return f"/extract/artifact/{encoded}" if encoded else ""


def _extract_fragment_from_artifact_url(raw_url: str) -> str:
    value = str(raw_url or "").strip()
    if not value:
        return ""
    if value.startswith("/extract/artifact/"):
        encoded = value.split("/extract/artifact/", 1)[1]
        return "/".join(urllib.parse.unquote(seg) for seg in encoded.split("/") if seg)
    if not value.lower().startswith(("http://", "https://")):
        return ""
    try:
        parsed = urllib.parse.urlparse(value)
    except Exception:
        return ""
    if not str(parsed.path or "").startswith("/extract/artifact/"):
        return ""
    encoded = str(parsed.path).split("/extract/artifact/", 1)[1]
    return "/".join(urllib.parse.unquote(seg) for seg in encoded.split("/") if seg)


def _link_absolute_artifact(path_value: str, *, file_hash: str) -> str:
    artifact_root = _artifact_root_dir()
    if artifact_root is None:
        return ""
    try:
        candidate = Path(path_value).resolve()
    except Exception:
        return ""
    if not candidate.exists() or not candidate.is_file():
        return ""
    try:
        relative = candidate.relative_to(artifact_root)
        return str(relative).replace("\\", "/")
    except Exception:
        pass

    bucket = str(file_hash or "").strip().lower()[:12]
    if not bucket:
        bucket = hashlib.sha1(str(candidate.parent).encode("utf-8", "ignore")).hexdigest()[:12]
    digest = hashlib.sha1(str(candidate).encode("utf-8", "ignore")).hexdigest()[:16]
    safe_name = _safe_link_name(candidate.name)
    mirror_rel = Path("linked") / bucket / f"{digest}_{safe_name}"
    mirror_path = (artifact_root / mirror_rel).resolve()
    try:
        mirror_path.relative_to(artifact_root)
    except Exception:
        return ""
    try:
        copy_required = True
        if mirror_path.exists():
            src_stat = candidate.stat()
            dst_stat = mirror_path.stat()
            copy_required = (
                int(src_stat.st_size) != int(dst_stat.st_size)
                or int(src_stat.st_mtime) != int(dst_stat.st_mtime)
            )
        if copy_required:
            mirror_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, mirror_path)
        return str(mirror_rel).replace("\\", "/")
    except Exception:
        return ""


def _resolve_artifact_ref(payload: dict[str, Any], *, file_hash: str) -> tuple[str | None, str | None]:
    candidate_url = str(payload.get("artifact_url") or "").strip()
    if candidate_url:
        fragment = _extract_fragment_from_artifact_url(candidate_url)
        if fragment:
            return fragment, _artifact_url_from_fragment(fragment)
        return None, candidate_url

    for key in ("artifact_path", "image_path"):
        raw = str(payload.get(key) or "").strip()
        if not raw:
            continue
        fragment_from_url = _extract_fragment_from_artifact_url(raw)
        if fragment_from_url:
            return fragment_from_url, _artifact_url_from_fragment(fragment_from_url)
        if raw.startswith("/extract/artifact/"):
            fragment = _extract_fragment_from_artifact_url(raw)
            if fragment:
                return fragment, _artifact_url_from_fragment(fragment)
        linked = _link_absolute_artifact(raw, file_hash=file_hash)
        if linked:
            return linked, _artifact_url_from_fragment(linked)
        if not Path(raw).is_absolute():
            fragment = raw.replace("\\", "/").strip().lstrip("/")
            if fragment:
                return fragment, _artifact_url_from_fragment(fragment)
    return None, None


def _table_rows_matrix(table: dict[str, Any], *, max_rows: int = 160, max_cols: int = 80) -> list[list[str]]:
    rows_out: list[list[str]] = []
    rows_raw = table.get("rows") if isinstance(table.get("rows"), list) else []
    for row in rows_raw[:max_rows]:
        if isinstance(row, list):
            values = [str(cell or "").strip()[:200] for cell in row[:max_cols]]
            if any(values):
                rows_out.append(values)
            continue
        if not isinstance(row, dict):
            continue
        cells_raw = row.get("cells") if isinstance(row.get("cells"), list) else []
        values = [str((cell or {}).get("text") or "").strip()[:200] for cell in cells_raw[:max_cols] if isinstance(cell, dict)]
        if any(values):
            rows_out.append(values)
    return rows_out


def _first_table_ref_id(table: dict[str, Any]) -> str | None:
    rows_raw = table.get("rows") if isinstance(table.get("rows"), list) else []
    for row in rows_raw:
        if not isinstance(row, dict):
            continue
        cells_raw = row.get("cells") if isinstance(row.get("cells"), list) else []
        for cell in cells_raw:
            if not isinstance(cell, dict):
                continue
            ref_id = str(cell.get("ref_id") or "").strip()
            if ref_id:
                return ref_id
    return None


def _first_figure_ref_id(figure: dict[str, Any]) -> str | None:
    ref_ids = figure.get("ref_ids") if isinstance(figure.get("ref_ids"), list) else []
    for item in ref_ids:
        ref_id = str(item or "").strip()
        if ref_id:
            return ref_id
    return None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return default


def _table_hit_from_payload(document: DocumentExtractionResponse, table: dict[str, Any]) -> dict[str, Any] | None:
    table_id = str(table.get("table_id") or "").strip()
    if not table_id:
        return None
    ref_id = _first_table_ref_id(table)
    page = _safe_int(table.get("page"), 0) or None
    headers = [str(item or "").strip() for item in (table.get("headers") if isinstance(table.get("headers"), list) else [])]
    rows = _table_rows_matrix(table)
    dataframe = {
        "headers": headers,
        "rows": rows,
        "row_count": max(_safe_int(table.get("row_count"), 0), len(rows)),
        "col_count": max(_safe_int(table.get("col_count"), 0), max((len(r) for r in rows), default=len(headers))),
        "sheet_index": _safe_int(table.get("sheet_index"), 0),
        "sheet_name": str(table.get("sheet_name") or "").strip(),
        "xlsx_sheet_rows_artifact_url": str(table.get("xlsx_sheet_rows_artifact_url") or "").strip(),
        "xlsx_workbook_manifest_url": str(table.get("xlsx_workbook_manifest_url") or "").strip(),
    }
    table_preview = {
        "headers": headers[:6],
        "rows": [row[:6] for row in rows[:5]],
        "row_count": int(dataframe["row_count"]),
        "col_count": int(dataframe["col_count"]),
        "sheet_index": int(dataframe["sheet_index"]),
        "sheet_name": str(dataframe["sheet_name"]),
        "xlsx_sheet_rows_artifact_url": str(dataframe["xlsx_sheet_rows_artifact_url"]),
        "xlsx_workbook_manifest_url": str(dataframe["xlsx_workbook_manifest_url"]),
    }
    artifact_path, artifact_url = _resolve_artifact_ref(table, file_hash=document.file_hash)
    locator: dict[str, Any] = {
        "page": page,
        "ref_id": ref_id,
        "title": str(table.get("title") or table.get("caption") or "").strip(),
        "caption": str(table.get("caption") or "").strip(),
        "table_preview": table_preview,
        "dataframe": dataframe,
        "sheet_index": _safe_int(table.get("sheet_index"), 0),
        "sheet_name": str(table.get("sheet_name") or "").strip(),
    }
    if artifact_path:
        locator["artifact_path"] = artifact_path
    if artifact_url:
        locator["artifact_url"] = artifact_url
    locator = {key: value for key, value in locator.items() if value not in ("", None, [], {})}
    snippet = str(table.get("caption") or "").strip() or f"table:{table_id}"
    return {
        "file_name": document.file_name,
        "file_hash": document.file_hash,
        "object_type": "table",
        "object_id": table_id,
        "ref_id": ref_id,
        "page": page,
        "snippet": snippet[:260],
        "confidence": _safe_confidence(table.get("quality")),
        "locator": locator,
        "bbox": [],
        "artifact_path": artifact_path,
        "artifact_url": artifact_url,
        "match_reason": "assistant_payload",
    }


def _figure_hit_from_payload(document: DocumentExtractionResponse, figure: dict[str, Any]) -> dict[str, Any] | None:
    figure_id = str(figure.get("figure_id") or "").strip()
    if not figure_id:
        return None
    ref_id = _first_figure_ref_id(figure)
    page = _safe_int(figure.get("page"), 0) or None
    figure_type = str(figure.get("figure_type") or "figure").strip() or "figure"
    dataframe_raw = figure.get("dataframe") if isinstance(figure.get("dataframe"), dict) else {}
    dataframe = {
        "headers": [
            str(item or "").strip()
            for item in (dataframe_raw.get("headers") if isinstance(dataframe_raw.get("headers"), list) else [])
            if str(item or "").strip()
        ],
        "rows": [
            [str(cell or "").strip()[:200] for cell in row]
            for row in (dataframe_raw.get("rows") if isinstance(dataframe_raw.get("rows"), list) else [])
            if isinstance(row, list)
        ],
    }
    dataframe["row_count"] = len(dataframe["rows"])
    dataframe["col_count"] = max((len(row) for row in dataframe["rows"]), default=len(dataframe["headers"]))

    artifact_path, artifact_url = _resolve_artifact_ref(figure, file_hash=document.file_hash)
    locator: dict[str, Any] = {
        "page": page,
        "ref_id": ref_id,
        "figure_type": figure_type.lower(),
        "title": str(figure.get("title") or "").strip(),
        "caption": str(figure.get("caption") or "").strip(),
        "summary": str(figure.get("caption") or figure.get("title") or "").strip(),
        "key_points": [str(item or "").strip() for item in (figure.get("key_points") if isinstance(figure.get("key_points"), list) else []) if str(item or "").strip()],
        "content_modes": [str(item or "").strip().lower() for item in (figure.get("content_modes") if isinstance(figure.get("content_modes"), list) else []) if str(item or "").strip()],
        "text_blocks": [str(item or "").strip() for item in (figure.get("text_blocks") if isinstance(figure.get("text_blocks"), list) else []) if str(item or "").strip()],
        "dataframe": dataframe,
        "dataframe_source": str(figure.get("dataframe_source") or "").strip().lower(),
    }
    if artifact_path:
        locator["artifact_path"] = artifact_path
    if artifact_url:
        locator["artifact_url"] = artifact_url
    locator = {key: value for key, value in locator.items() if value not in ("", None, [], {})}
    snippet_seed = str(figure.get("caption") or figure.get("title") or "").strip() or figure_id
    snippet = f"{figure_type.lower()}:{snippet_seed}"
    return {
        "file_name": document.file_name,
        "file_hash": document.file_hash,
        "object_type": "figure",
        "object_id": figure_id,
        "ref_id": ref_id,
        "page": page,
        "snippet": snippet[:260],
        "confidence": _safe_confidence(figure.get("quality") or 0.66),
        "locator": locator,
        "bbox": [],
        "artifact_path": artifact_path,
        "artifact_url": artifact_url,
        "match_reason": "assistant_payload",
    }


def _decode_assistant_payload_fragment(raw_value: Any) -> str:
    value = str(raw_value or "").strip()
    if not value:
        return ""
    fragment = _extract_fragment_from_artifact_url(value)
    if fragment:
        return fragment
    return value.replace("\\", "/").strip().lstrip("/")


def _load_assistant_payload(document: DocumentExtractionResponse) -> dict[str, Any]:
    diagnostics = document.diagnostics if isinstance(document.diagnostics, dict) else {}
    artifact_root = _artifact_root_dir()
    if artifact_root is None:
        return {}

    candidate_paths: list[Path] = []
    diag_fragment = _decode_assistant_payload_fragment(diagnostics.get("assistant_payload_artifact_path"))
    if not diag_fragment:
        diag_fragment = _decode_assistant_payload_fragment(diagnostics.get("assistant_payload_artifact_url"))
    if diag_fragment:
        candidate_paths.append((artifact_root / diag_fragment).resolve())

    hash_bucket = str(document.file_hash or "").strip().lower()[:12]
    if hash_bucket:
        payload_dir = (artifact_root / "assistant_payload" / hash_bucket).resolve()
        if payload_dir.exists() and payload_dir.is_dir():
            candidate_paths.extend(sorted(payload_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True))

    seen: set[str] = set()
    for candidate in candidate_paths:
        try:
            candidate_key = str(candidate.resolve())
        except Exception:
            candidate_key = str(candidate)
        if candidate_key in seen:
            continue
        seen.add(candidate_key)
        try:
            if not candidate.exists() or not candidate.is_file():
                continue
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return payload
        except Exception:
            continue
    return {}


def _enrich_trace_hits_from_assistant_payload(document: DocumentExtractionResponse) -> list[dict[str, Any]]:
    payload = _load_assistant_payload(document)
    if not payload:
        return []
    tables = payload.get("tables") if isinstance(payload.get("tables"), list) else []
    figures = payload.get("figures") if isinstance(payload.get("figures"), list) else []
    hits: list[dict[str, Any]] = []
    for table in tables:
        if not isinstance(table, dict):
            continue
        hit = _table_hit_from_payload(document, table)
        if hit is not None:
            hits.append(hit)
    for figure in figures:
        if not isinstance(figure, dict):
            continue
        hit = _figure_hit_from_payload(document, figure)
        if hit is not None:
            hits.append(hit)
    hits.sort(key=lambda item: float(item.get("confidence", 0.0) or 0.0), reverse=True)
    return hits


def _is_visual_hit(hit: dict[str, Any]) -> bool:
    object_type = str(hit.get("object_type") or "").strip().lower()
    return object_type in {"table", "figure", "image"}


def _hit_ref_key(hit: dict[str, Any]) -> tuple[str, str]:
    return (
        str(hit.get("object_type") or "").strip().lower(),
        str(hit.get("ref_id") or "").strip(),
    )


def _hit_object_key(hit: dict[str, Any]) -> tuple[str, str]:
    return (
        str(hit.get("object_type") or "").strip().lower(),
        str(hit.get("object_id") or "").strip().lower(),
    )


def _hit_has_rich_visual_data(hit: dict[str, Any]) -> bool:
    if not _is_visual_hit(hit):
        return False
    if str(hit.get("artifact_path") or "").strip() or str(hit.get("artifact_url") or "").strip():
        return True
    if str(hit.get("object_id") or "").strip():
        return True
    locator = hit.get("locator")
    if isinstance(locator, dict) and any(locator.keys()):
        return True
    return False


def _merge_trace_hits(source_hits: list[dict[str, Any]], enriched_hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not source_hits:
        return list(enriched_hits)
    if not enriched_hits:
        return list(source_hits)

    enriched_by_object: dict[tuple[str, str], dict[str, Any]] = {}
    enriched_by_ref: dict[tuple[str, str], dict[str, Any]] = {}
    for hit in enriched_hits:
        object_key = _hit_object_key(hit)
        ref_key = _hit_ref_key(hit)
        if object_key[1]:
            enriched_by_object[object_key] = hit
        if ref_key[1]:
            enriched_by_ref[ref_key] = hit

    merged: list[dict[str, Any]] = []
    used_ids: set[int] = set()
    for source_hit in source_hits:
        if not isinstance(source_hit, dict):
            continue
        chosen = None
        object_key = _hit_object_key(source_hit)
        ref_key = _hit_ref_key(source_hit)
        if object_key[1] and object_key in enriched_by_object:
            chosen = enriched_by_object[object_key]
        elif ref_key[1] and ref_key in enriched_by_ref:
            chosen = enriched_by_ref[ref_key]
        if chosen is None or not _is_visual_hit(source_hit):
            merged.append(source_hit)
            continue
        used_ids.add(id(chosen))
        if _hit_has_rich_visual_data(source_hit):
            merged.append(source_hit)
            continue
        merged.append(chosen)

    merged_ref_keys = {_hit_ref_key(item) for item in merged if isinstance(item, dict)}
    merged_obj_keys = {_hit_object_key(item) for item in merged if isinstance(item, dict)}
    for enriched_hit in enriched_hits:
        if id(enriched_hit) in used_ids:
            continue
        if _hit_ref_key(enriched_hit) in merged_ref_keys and _hit_ref_key(enriched_hit)[1]:
            continue
        if _hit_object_key(enriched_hit) in merged_obj_keys and _hit_object_key(enriched_hit)[1]:
            continue
        merged.append(enriched_hit)
    merged.sort(key=lambda item: float(item.get("confidence", 0.0) or 0.0), reverse=True)
    return merged


def _page_from_bbox(bbox: list[Any]) -> int | None:
    if not isinstance(bbox, list) or len(bbox) != 5:
        return None
    try:
        return int(round(float(bbox[0])))
    except (TypeError, ValueError):
        return None


def _safe_confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value or 0.0)))
    except (TypeError, ValueError):
        return 0.0
