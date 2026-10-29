from __future__ import annotations

"""Extraction quality helpers for module2 service layer."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List


BoolFactory = Callable[[], bool]


@dataclass(frozen=True)
class Module2MainQualityBundle:
    count_table_cells: Callable[[List[Dict[str, Any]]], int]
    count_figure_dataframe_cells: Callable[[List[Dict[str, Any]]], int]
    has_meaningful_value: Callable[[Any], bool]
    result_quality_snapshot: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
    table_quality_avg: Callable[[List[Dict[str, Any]]], float]
    table_source_counts: Callable[[List[Dict[str, Any]]], Dict[str, int]]
    figure_source_counts: Callable[[List[Dict[str, Any]]], Dict[str, int]]
    figure_pages: Callable[[List[Dict[str, Any]]], List[int]]
    source_counts_have_vision: Callable[[Dict[str, int]], bool]
    source_counts_all_vision: Callable[[Dict[str, int]], bool]
    build_visual_chain_contract: Callable[..., Dict[str, Any]]


def build_module2_main_quality_bundle(
    *,
    visual_chain_required: BoolFactory,
) -> Module2MainQualityBundle:
    def _count_table_cells(table_blocks: List[Dict[str, Any]]) -> int:
        count = 0
        for table in table_blocks:
            for row in table.get("rows", []):
                count += len(row.get("cells", []))
        return count

    def _count_figure_dataframe_cells(figure_blocks: List[Dict[str, Any]]) -> int:
        count = 0
        for figure in figure_blocks:
            dataframe = figure.get("dataframe") if isinstance(figure, dict) else {}
            if not isinstance(dataframe, dict):
                continue
            headers = dataframe.get("headers")
            if isinstance(headers, list):
                count += len(headers)
            rows = dataframe.get("rows")
            if isinstance(rows, list):
                for row in rows:
                    if isinstance(row, list):
                        count += len(row)
        return count

    def _has_meaningful_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        text = str(value).strip()
        if not text:
            return False
        return text.lower() not in {"null", "none", "nan", "n/a", "-"}

    def _result_quality_snapshot(results: Dict[str, Any], schema_fields: Dict[str, Any]) -> Dict[str, Any]:
        target_total = len(schema_fields)
        filled = 0
        confidence_vals: List[float] = []
        traceable = 0
        for field_name in schema_fields.keys():
            entity = results.get(field_name)
            if not isinstance(entity, dict):
                continue
            if _has_meaningful_value(entity.get("value")):
                filled += 1
            ref_id = str(entity.get("source_ref_id") or "").strip()
            if ref_id:
                traceable += 1
            try:
                conf = float(entity.get("confidence", 0.0) or 0.0)
            except (TypeError, ValueError):
                conf = 0.0
            if conf > 0:
                confidence_vals.append(conf)

        all_keys = list(results.keys())
        all_filled = sum(
            1
            for key in all_keys
            if isinstance(results.get(key), dict) and _has_meaningful_value(results[key].get("value"))
        )
        coverage = (filled / float(target_total)) if target_total > 0 else (1.0 if all_filled > 0 else 0.0)
        trace_ratio = (traceable / float(max(target_total, 1))) if target_total > 0 else 0.0
        avg_conf = (sum(confidence_vals) / len(confidence_vals)) if confidence_vals else 0.0
        return {
            "target_fields": target_total,
            "filled_fields": filled,
            "all_result_fields": len(all_keys),
            "all_filled_fields": all_filled,
            "coverage_ratio": round(coverage, 4),
            "trace_ratio": round(trace_ratio, 4),
            "avg_confidence": round(avg_conf, 4),
        }

    def _table_quality_avg(table_blocks: List[Dict[str, Any]]) -> float:
        scores = []
        for table in table_blocks:
            try:
                scores.append(float(table.get("quality", 0.0)))
            except (TypeError, ValueError):
                continue
        if not scores:
            return 0.0
        return round(sum(scores) / len(scores), 4)

    def _table_source_counts(table_blocks: List[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for table in table_blocks:
            source = str(table.get("source", "unknown") or "unknown")
            counts[source] = counts.get(source, 0) + 1
        return counts

    def _figure_source_counts(figure_blocks: List[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for figure in figure_blocks:
            source = str(figure.get("source", "unknown") or "unknown")
            counts[source] = counts.get(source, 0) + 1
        return counts

    def _figure_pages(figure_blocks: List[Dict[str, Any]]) -> List[int]:
        pages = set()
        for figure in figure_blocks:
            try:
                page_no = int(figure.get("page", 0) or 0)
            except (TypeError, ValueError):
                continue
            if page_no > 0:
                pages.add(page_no)
        return sorted(pages)

    def _source_counts_have_vision(source_counts: Dict[str, int]) -> bool:
        return any("vision" in str(source or "").strip().lower() for source in source_counts.keys())

    def _source_counts_all_vision(source_counts: Dict[str, int]) -> bool:
        non_empty = [str(source or "").strip().lower() for source in source_counts.keys() if str(source or "").strip()]
        return bool(non_empty) and all("vision" in source for source in non_empty)

    def _source_counts_have_keyword(source_counts: Dict[str, int], keyword: str) -> bool:
        target = str(keyword or "").strip().lower()
        if not target:
            return False
        return any(target in str(source or "").strip().lower() for source in source_counts.keys())

    def _coerce_non_negative_int(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    def _build_visual_chain_contract(
        *,
        file_name: str,
        parse_input_name: str,
        parse_track: str,
        word_parse_via_pdf: bool,
        conversion_diag: Dict[str, Any],
        parse_stats: Dict[str, Any],
        table_blocks: List[Dict[str, Any]],
        figure_blocks: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        file_ext = Path(file_name or "").suffix.lower()
        parse_input_is_pdf = str(parse_input_name or "").lower().endswith(".pdf")
        requires_word_pdf = file_ext in {".doc", ".docx"} and bool(word_parse_via_pdf)
        required = bool(visual_chain_required() and (file_ext == ".pdf" or requires_word_pdf))
        parse_track_text = str(parse_track or "").strip()
        parse_track_lower = parse_track_text.lower()
        pipeline = str(parse_stats.get("pipeline", "") or "").strip().lower()
        chain_status = str(parse_stats.get("chain_status", "") or "").strip().lower()
        artifact_status = str(parse_stats.get("artifact_status", "") or "").strip().lower()
        vision_status = str(parse_stats.get("vision_status", "") or "").strip().lower()
        baseline_artifact_ready = bool(parse_stats.get("visual_baseline_artifact_ready", False))
        mineru_run = parse_stats.get("mineru_run") if isinstance(parse_stats.get("mineru_run"), dict) else {}
        mineru_status = str(mineru_run.get("status", "") or "").strip().lower()
        fallback_reason = str(parse_stats.get("visual_first_fallback_reason", "") or "").strip()
        visual_mode = str(parse_stats.get("visual_mode", "") or "").strip().lower()
        visual_text_only = bool(parse_stats.get("visual_text_only"))
        visual_layout_object_count = _coerce_non_negative_int(parse_stats.get("visual_layout_object_count"))
        visual_ref_count = _coerce_non_negative_int(parse_stats.get("visual_ref_count"))
        visual_text_char_count = _coerce_non_negative_int(parse_stats.get("visual_text_char_count"))
        mineru_content_list_present = bool(parse_stats.get("mineru_content_list_present"))
        mineru_markdown_present = bool(parse_stats.get("mineru_markdown_present"))
        table_sources = _table_source_counts(table_blocks)
        figure_sources = _figure_source_counts(figure_blocks)
        reasons: List[str] = []
        inferred_visual_contract = False

        if required:
            visual_sources_ready = (
                parse_input_is_pdf
                and parse_track_text == "VisualTrack"
                and mineru_status == "ok"
                and (
                    _source_counts_have_keyword(table_sources, "mineru")
                    or _source_counts_have_keyword(figure_sources, "mineru")
                )
                and (
                    _source_counts_have_vision(table_sources)
                    or _source_counts_have_vision(figure_sources)
                )
                and (
                    file_ext == ".pdf"
                    or (
                        requires_word_pdf
                        and bool(conversion_diag.get("office_pdf_converted"))
                    )
                )
            )
            visual_stats_ready = (
                parse_input_is_pdf
                and parse_track_text == "VisualTrack"
                and (
                    mineru_status == "ok"
                    or baseline_artifact_ready
                    or mineru_content_list_present
                    or mineru_markdown_present
                    or visual_layout_object_count > 0
                    or visual_ref_count > 0
                    or visual_text_char_count > 0
                )
                and (
                    file_ext == ".pdf"
                    or (
                        requires_word_pdf
                        and bool(conversion_diag.get("office_pdf_converted"))
                    )
                )
            )
            visual_contract_ready = visual_sources_ready or visual_stats_ready
            if visual_contract_ready and not pipeline:
                pipeline = "visual_first"
                inferred_visual_contract = True
            if visual_contract_ready and chain_status != "success":
                chain_status = "success"
                inferred_visual_contract = True
            if visual_contract_ready and not baseline_artifact_ready:
                baseline_artifact_ready = True
                inferred_visual_contract = True
            if visual_contract_ready and not artifact_status:
                artifact_status = (
                    "artifact_text_only"
                    if (
                        visual_text_only
                        or visual_mode == "text_only"
                        or (visual_text_char_count > 0 and not table_blocks and not figure_blocks)
                    )
                    else "ready"
                )
                inferred_visual_contract = True
            if visual_contract_ready and not vision_status:
                vision_status = "not_needed" if (visual_text_only or visual_mode == "text_only") else "ok"
                inferred_visual_contract = True

        if requires_word_pdf and not bool(conversion_diag.get("office_pdf_converted")):
            reasons.append("word_pdf_conversion_missing")
        if requires_word_pdf and not parse_input_is_pdf:
            reasons.append("word_parse_input_not_pdf")

        if required:
            if parse_track_text != "VisualTrack":
                reasons.append(f"parse_track_not_visual:{parse_track_text or 'missing'}")
            if "fasttrack" in parse_track_lower:
                reasons.append("fasttrack_fallback_detected")
            if "nativedocxrecovery" in parse_track_lower:
                reasons.append("native_docx_recovery_detected")
            if pipeline != "visual_first":
                reasons.append(f"pipeline_not_visual_first:{pipeline or 'missing'}")
            if mineru_status != "ok":
                reasons.append(f"mineru_status_not_ok:{mineru_status or 'missing'}")
            if chain_status and chain_status != "success":
                reasons.append(f"chain_status_not_success:{chain_status}")
            if not baseline_artifact_ready:
                reasons.append("baseline_artifact_missing")
            if fallback_reason:
                reasons.append(f"visual_first_fallback:{fallback_reason}")

        return {
            "required": required,
            "satisfied": not reasons,
            "reasons": reasons,
            "requires_word_pdf": requires_word_pdf,
            "parse_input_is_pdf": parse_input_is_pdf,
            "parse_track": parse_track_text,
            "pipeline": pipeline,
            "chain_status": chain_status,
            "artifact_status": artifact_status,
            "vision_status": vision_status,
            "baseline_artifact_ready": baseline_artifact_ready,
            "mineru_status": mineru_status,
            "visual_first_fallback_reason": fallback_reason,
            "inferred_visual_contract": inferred_visual_contract,
            "table_source_counts": table_sources,
            "figure_source_counts": figure_sources,
        }

    return Module2MainQualityBundle(
        count_table_cells=_count_table_cells,
        count_figure_dataframe_cells=_count_figure_dataframe_cells,
        has_meaningful_value=_has_meaningful_value,
        result_quality_snapshot=_result_quality_snapshot,
        table_quality_avg=_table_quality_avg,
        table_source_counts=_table_source_counts,
        figure_source_counts=_figure_source_counts,
        figure_pages=_figure_pages,
        source_counts_have_vision=_source_counts_have_vision,
        source_counts_all_vision=_source_counts_all_vision,
        build_visual_chain_contract=_build_visual_chain_contract,
    )
