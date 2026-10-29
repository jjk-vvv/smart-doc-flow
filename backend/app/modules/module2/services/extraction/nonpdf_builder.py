from __future__ import annotations

"""Non-PDF profile and budget helpers for module2 extraction service layer."""

from dataclasses import dataclass
import io
import os
import re
from typing import Any, Callable, Dict, List
import zipfile


GetEnvFn = Callable[[str, str | None], str | None]


@dataclass(frozen=True)
class Module2MainNonPdfBundle:
    decode_text_with_fallback: Callable[[bytes], str]
    preflight_nonpdf_profile: Callable[[str, bytes], Dict[str, Any]]
    resolve_nonpdf_budgets: Callable[[str], Dict[str, float]]
    normalize_soft_warnings: Callable[[Any], List[str]]
    strip_recovered_extract_warnings: Callable[..., List[str]]
    promote_visual_diagnostics: Callable[[Dict[str, Any]], Dict[str, Any]]
    is_recoverable_timeout_error: Callable[[str], bool]


def build_module2_main_nonpdf_bundle(
    *,
    getenv: GetEnvFn,
) -> Module2MainNonPdfBundle:
    def _decode_text_with_fallback(file_bytes: bytes) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
            try:
                return file_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        return file_bytes.decode("latin-1", errors="ignore")

    def _preflight_nonpdf_profile(file_name: str, file_bytes: bytes) -> Dict[str, Any]:
        name = (file_name or "").lower()
        _, ext = os.path.splitext(name)
        ext = ext or ""
        size_mb = round(len(file_bytes) / (1024.0 * 1024.0), 3)

        signals: Dict[str, Any] = {
            "ext": ext,
            "size_mb": size_mb,
            "docx_media_count": 0,
            "docx_chart_xml_count": 0,
            "md_image_links": 0,
            "md_table_rows": 0,
            "txt_table_lines": 0,
            "figure_keyword_hits": 0,
            "figure_cue_lines": 0,
        }

        profile = "text_heavy"
        # Keep a Unicode-escaped canonical pattern to avoid source encoding drift.
        figure_pattern = re.compile(
            r"(\u56fe\u8868|\u56fe\d+|\u8868\d+|figure|chart|diagram|\u67f1\u72b6\u56fe|\u6298\u7ebf\u56fe|\u997c\u56fe)",
            re.IGNORECASE,
        )

        if ext in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}:
            profile = "chart_heavy"
            return {"profile": profile, "signals": signals}

        if ext == ".docx":
            try:
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                    names = zf.namelist()
                media_count = sum(1 for n in names if n.startswith("word/media/"))
                chart_xml_count = sum(1 for n in names if n.startswith("word/charts/") and n.endswith(".xml"))
                signals["docx_media_count"] = media_count
                signals["docx_chart_xml_count"] = chart_xml_count
                if chart_xml_count >= 1 or media_count >= 3:
                    profile = "chart_heavy"
                elif media_count >= 1:
                    profile = "mixed"
            except Exception:
                profile = "mixed" if size_mb >= 4 else "text_heavy"
            return {"profile": profile, "signals": signals}

        if ext == ".xlsx":
            profile = "table_heavy"
            try:
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                    names = zf.namelist()
                sheet_count = sum(
                    1
                    for n in names
                    if n.startswith("xl/worksheets/") and n.endswith(".xml")
                )
                chart_count = sum(
                    1
                    for n in names
                    if n.startswith("xl/charts/") and n.endswith(".xml")
                )
                signals["xlsx_sheet_count"] = sheet_count
                signals["xlsx_chart_count"] = chart_count
                if chart_count >= 2 and sheet_count <= 2:
                    profile = "chart_heavy"
                elif sheet_count <= 2 and size_mb <= 0.9:
                    profile = "mixed"
            except Exception:
                profile = "table_heavy" if size_mb >= 0.6 else "mixed"
            return {"profile": profile, "signals": signals}

        if ext in {".md", ".markdown", ".txt"}:
            text = _decode_text_with_fallback(file_bytes)
            lines = [line.rstrip("\n") for line in text.splitlines()]
            kw_hits = len(figure_pattern.findall(text[:120000]))
            figure_cue_lines = sum(
                1
                for line in lines
                if 0 < len(line.strip()) <= 80 and figure_pattern.search(line)
            )
            signals["figure_keyword_hits"] = kw_hits
            signals["figure_cue_lines"] = figure_cue_lines

            if ext in {".md", ".markdown"}:
                md_images = len(re.findall(r"!\[[^\]]*]\(([^)]+)\)", text))
                md_table_rows = sum(1 for line in lines if line.count("|") >= 2 and len(line.strip()) >= 6)
                signals["md_image_links"] = md_images
                signals["md_table_rows"] = md_table_rows
                if md_images >= 2 or (md_images >= 1 and md_table_rows >= 3) or kw_hits >= 6:
                    profile = "chart_heavy"
                elif md_images >= 1 or md_table_rows >= 2 or kw_hits >= 2:
                    profile = "mixed"
                return {"profile": profile, "signals": signals}

            txt_table_lines = sum(
                1
                for line in lines
                if ("\t" in line and len([p for p in line.split("\t") if p.strip()]) >= 3)
                or (line.count(",") >= 2 and len([p for p in line.split(",") if p.strip()]) >= 3)
                or len(re.findall(r"\s{2,}", line)) >= 2
            )
            signals["txt_table_lines"] = txt_table_lines
            if txt_table_lines >= 8 and figure_cue_lines >= 1:
                profile = "chart_heavy"
            elif txt_table_lines >= 4 or (txt_table_lines >= 2 and figure_cue_lines >= 1):
                profile = "mixed"
            return {"profile": profile, "signals": signals}

        if size_mb >= 8:
            profile = "mixed"
        return {"profile": profile, "signals": signals}

    def _resolve_nonpdf_budgets(profile: str) -> Dict[str, float]:
        parse_default = max(5.0, float(getenv("MODULE2_PARSE_TIMEOUT_SEC", "120") or "120"))
        extract_default = max(8.0, float(getenv("MODULE2_EXTRACT_TIMEOUT_SEC", "150") or "150"))
        total_cap = max(30.0, float(getenv("MODULE2_NONPDF_TOTAL_BUDGET_SEC", "90") or "90"))

        profile_key = (profile or "text_heavy").strip().lower()
        if profile_key not in {"text_heavy", "mixed", "chart_heavy", "table_heavy"}:
            profile_key = "mixed"
        if profile_key == "table_heavy":
            total_cap = max(total_cap, float(getenv("MODULE2_NONPDF_TOTAL_BUDGET_TABLE_SEC", "88") or "88"))

        parse_cap_map = {
            "text_heavy": max(10.0, float(getenv("MODULE2_NONPDF_PARSE_TEXT_SEC", "24") or "24")),
            "mixed": max(12.0, float(getenv("MODULE2_NONPDF_PARSE_MIXED_SEC", "34") or "34")),
            "chart_heavy": max(15.0, float(getenv("MODULE2_NONPDF_PARSE_CHART_SEC", "42") or "42")),
            "table_heavy": max(14.0, float(getenv("MODULE2_NONPDF_PARSE_TABLE_SEC", "24") or "24")),
        }
        extract_cap_map = {
            "text_heavy": max(12.0, float(getenv("MODULE2_NONPDF_EXTRACT_TEXT_SEC", "34") or "34")),
            "mixed": max(15.0, float(getenv("MODULE2_NONPDF_EXTRACT_MIXED_SEC", "44") or "44")),
            "chart_heavy": max(18.0, float(getenv("MODULE2_NONPDF_EXTRACT_CHART_SEC", "52") or "52")),
            "table_heavy": max(24.0, float(getenv("MODULE2_NONPDF_EXTRACT_TABLE_SEC", "64") or "64")),
        }

        parse_timeout = min(parse_default, parse_cap_map[profile_key])
        extract_timeout = min(extract_default, extract_cap_map[profile_key])
        total = parse_timeout + extract_timeout
        if total > total_cap:
            ratio = total_cap / max(total, 1e-6)
            parse_timeout = max(5.0, parse_timeout * ratio)
            extract_timeout = max(8.0, extract_timeout * ratio)

        return {
            "profile": profile_key,
            "parse_timeout_sec": round(parse_timeout, 3),
            "extract_timeout_sec": round(extract_timeout, 3),
            "total_budget_sec": round(total_cap, 3),
        }

    def _sanitize_soft_warning(item: Any) -> str:
        raw = str(item or "").strip()
        if not raw:
            return ""
        lowered = raw.lower()

        def _is_rate_limited(text: str) -> bool:
            quota_limited = ("quota" in text) and ("exceed" in text or "limit" in text)
            return (
                " 429" in f" {text}"
                or "http error 429" in text
                or "rate limit" in text
                or "too many requests" in text
                or quota_limited
            )

        if raw.startswith("table_extract_error:"):
            if _is_rate_limited(lowered):
                return "table_extract_error:rate_limited_retryable"
            if "timeout" in lowered:
                return "table_extract_error:timeout_retryable"
            return "table_extract_error:upstream_retryable"

        if raw.startswith("field_extract_error:"):
            if _is_rate_limited(lowered):
                return "field_extract_error:rate_limited_retryable"
            if "timeout" in lowered:
                return "field_extract_error:timeout_retryable"
            return "field_extract_error:upstream_retryable"

        if raw.startswith("table_extract_timeout:"):
            return "table_extract_timeout"
        if raw.startswith("field_extract_timeout:"):
            return "field_extract_timeout"

        if raw.startswith("downgraded:"):
            detail = raw.split(":", 1)[1].lower() if ":" in raw else lowered
            if _is_rate_limited(detail):
                return "downgraded:rate_limited_retryable"
            if "timeout" in detail:
                return "downgraded:timeout_retryable"
            return "downgraded:recoverable_upstream"

        if _is_rate_limited(lowered) and ("llm" in lowered or "provider" in lowered):
            return "upstream_rate_limited_retryable"
        if "connection error" in lowered and ("llm" in lowered or "provider" in lowered):
            return "upstream_connection_retryable"

        return raw

    def _normalize_soft_warnings(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        out: List[str] = []
        for item in value:
            msg = _sanitize_soft_warning(item)
            if msg and msg not in out:
                out.append(msg)
        return out

    def _strip_recovered_extract_warnings(
        warnings: List[str],
        *,
        quality_ok: bool,
        quick_fallback: bool,
    ) -> List[str]:
        if not quality_ok or quick_fallback:
            return _normalize_soft_warnings(warnings)
        noisy_prefixes = (
            "table_extract_error:",
            "field_extract_error:",
            "table_extract_timeout:",
            "field_extract_timeout:",
            "auto_result_filter_removed:",
        )
        noisy_exact = {
            "quality_gate_ok",
        }
        return _normalize_soft_warnings(
            [
                item
                for item in warnings
                if str(item or "").strip() not in noisy_exact
                and not any(str(item or "").startswith(prefix) for prefix in noisy_prefixes)
            ]
        )

    def _promote_visual_diagnostics(diagnostics: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(diagnostics, dict):
            return {}
        merged = dict(diagnostics)
        parse_stats = merged.get("parse_stats") if isinstance(merged.get("parse_stats"), dict) else {}
        for key in (
            "chain_status",
            "artifact_status",
            "vision_status",
            "visual_baseline_artifact_ready",
            "mineru_item_count",
            "mineru_image_asset_count",
            "mineru_content_list_present",
            "mineru_markdown_present",
            "visual_selected_object_count",
            "visual_vision_candidate_count",
            "visual_vision_attempted_count",
            "visual_vision_success_count",
            "visual_vision_empty_count",
            "xlsx_workbook_manifest_path",
            "xlsx_workbook_manifest_url",
            "xlsx_sheet_rows_artifact_version",
            "xlsx_source_sheet_count",
            "xlsx_source_total_rows",
            "xlsx_source_total_cols",
            "xlsx_source_total_nonempty_rows",
            "xlsx_source_total_nonempty_cells",
            "xlsx_workbook_extract_ms",
            "xlsx_workbook_persist_ms",
            "xlsx_workbook_total_ms",
        ):
            if key in parse_stats and key not in merged:
                merged[key] = parse_stats.get(key)

        if "mineru_status" not in merged:
            mineru_status = ""
            mineru_run = parse_stats.get("mineru_run") if isinstance(parse_stats.get("mineru_run"), dict) else {}
            if mineru_run:
                mineru_status = str(mineru_run.get("status", "") or "").strip()
            if not mineru_status:
                chain_contract = merged.get("chain_contract") if isinstance(merged.get("chain_contract"), dict) else {}
                mineru_status = str(chain_contract.get("mineru_status", "") or "").strip()
            if mineru_status:
                merged["mineru_status"] = mineru_status
        return merged

    def _is_recoverable_timeout_error(message: str) -> bool:
        text = str(message or "").lower()
        return ("timeout" in text) and (
            "table_extract" in text or "field_extract" in text or "llm" in text or "vision" in text
        )

    return Module2MainNonPdfBundle(
        decode_text_with_fallback=_decode_text_with_fallback,
        preflight_nonpdf_profile=_preflight_nonpdf_profile,
        resolve_nonpdf_budgets=_resolve_nonpdf_budgets,
        normalize_soft_warnings=_normalize_soft_warnings,
        strip_recovered_extract_warnings=_strip_recovered_extract_warnings,
        promote_visual_diagnostics=_promote_visual_diagnostics,
        is_recoverable_timeout_error=_is_recoverable_timeout_error,
    )
