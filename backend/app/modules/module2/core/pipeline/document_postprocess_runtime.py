from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List


@dataclass(frozen=True)
class PostParseQualityOutcome:
    final_results: Dict[str, Any]
    final_errors: List[str]
    soft_warnings: List[str]
    semantic_removed: Dict[str, str]
    quality_schema_fields: Dict[str, Any]
    quality_snapshot: Dict[str, Any]
    degraded_reasons: List[str]
    business_extraction_status: str


class PostParseQualityRuntime:
    """Finalize extraction results and warnings after graph execution."""

    def __init__(self, *, getenv=os.getenv) -> None:
        self._getenv = getenv

    def process(
        self,
        *,
        final_state: Dict[str, Any],
        file_name: str,
        parse_warning: str,
        nonpdf_total_budget_sec: float | None,
        total_ms: int,
        used_quick_fallback: bool,
        schema_meta: Dict[str, Any],
        effective_schema_fields: Dict[str, Any],
        normalize_soft_warnings: Callable[[Any], List[str]],
        is_low_value_auto_schema_field_name: Callable[[Any], bool],
        has_meaningful_value: Callable[[Any], bool],
        is_low_value_quick_fallback_value: Callable[[Any], bool],
        is_recoverable_timeout_error: Callable[[str], bool],
        filter_low_value_auto_results: Callable[[Dict[str, Any]], tuple[Dict[str, Dict[str, Any]], Dict[str, str]]],
        effective_quality_schema_fields: Callable[[Dict[str, Any], Dict[str, str]], Dict[str, Any]],
        result_quality_snapshot: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
        strip_recovered_extract_warnings: Callable[..., List[str]],
    ) -> PostParseQualityOutcome:
        final_results = final_state.get("results", {})
        if not isinstance(final_results, dict):
            final_results = {}
        final_errors = list(final_state.get("errors", []))
        soft_warnings = normalize_soft_warnings(final_state.get("soft_warnings", []))
        if parse_warning:
            soft_warnings.append(parse_warning)
        if nonpdf_total_budget_sec is not None and total_ms > int(nonpdf_total_budget_sec * 1000):
            over_ms = total_ms - int(nonpdf_total_budget_sec * 1000)
            soft_warnings.append(f"nonpdf_budget_exceeded:{over_ms}")

        if used_quick_fallback:
            min_conf = max(0.35, min(0.95, float(self._getenv("MODULE2_QUICK_FALLBACK_MIN_CONF", "0.58"))))
            filtered_results: Dict[str, Dict[str, Any]] = {}
            dropped = 0
            for field_name, entity in final_results.items():
                if not isinstance(entity, dict):
                    dropped += 1
                    continue
                if is_low_value_auto_schema_field_name(field_name):
                    dropped += 1
                    continue
                try:
                    confidence = float(entity.get("confidence", 0.0) or 0.0)
                except (TypeError, ValueError):
                    confidence = 0.0
                if (
                    confidence < min_conf
                    or not has_meaningful_value(entity.get("value"))
                    or is_low_value_quick_fallback_value(entity.get("value"))
                ):
                    dropped += 1
                    continue
                filtered_results[str(field_name)] = entity
            if dropped > 0:
                soft_warnings.append(f"quick_table_fallback_filtered:{dropped}")
            hint = f"quick_table_fallback_used:{file_name}"
            if hint not in soft_warnings:
                soft_warnings.append(hint)
            final_results = filtered_results

        if final_results and final_errors:
            retained_errors: List[str] = []
            for err in final_errors:
                if is_recoverable_timeout_error(err):
                    downgraded = f"downgraded:{err}"
                    if downgraded not in soft_warnings:
                        soft_warnings.append(downgraded)
                else:
                    retained_errors.append(err)
            final_errors = retained_errors

        semantic_removed: Dict[str, str] = {}
        if str(schema_meta.get("mode", "")) == "auto" and final_results:
            filtered_results, semantic_removed = filter_low_value_auto_results(final_results)
            if semantic_removed:
                final_results = filtered_results
                soft_warnings.append(f"auto_result_filter_removed:{len(semantic_removed)}")

        quality_schema_fields = effective_quality_schema_fields(effective_schema_fields, semantic_removed)
        quality_snapshot = result_quality_snapshot(final_results, quality_schema_fields)
        coverage_ratio = float(quality_snapshot.get("coverage_ratio", 0.0) or 0.0)
        avg_conf = float(quality_snapshot.get("avg_confidence", 0.0) or 0.0)
        min_coverage = max(0.15, min(1.0, float(self._getenv("MODULE2_MIN_COVERAGE_RATIO", "0.35"))))
        min_confidence = max(0.2, min(1.0, float(self._getenv("MODULE2_MIN_AVG_CONFIDENCE", "0.55"))))
        degraded_reasons: List[str] = []
        if quality_snapshot.get("target_fields", 0) and coverage_ratio < min_coverage:
            degraded_reasons.append(f"low_coverage:{coverage_ratio:.3f}")
        if quality_snapshot.get("filled_fields", 0) > 0 and avg_conf < min_confidence:
            degraded_reasons.append(f"low_confidence:{avg_conf:.3f}")
        if used_quick_fallback:
            degraded_reasons.append("quick_fallback")
        if semantic_removed and not final_results:
            degraded_reasons.append("auto_results_all_filtered")
        if degraded_reasons:
            soft_warnings.append(f"quality_gate_degraded:{'|'.join(degraded_reasons)}")
        else:
            soft_warnings.append("quality_gate_ok")
        soft_warnings = strip_recovered_extract_warnings(
            soft_warnings,
            quality_ok=not degraded_reasons,
            quick_fallback=used_quick_fallback,
        )
        soft_warnings = normalize_soft_warnings(soft_warnings)

        if final_results:
            business_extraction_status = "nonempty"
        elif final_errors:
            business_extraction_status = "failed"
        else:
            business_extraction_status = "empty_valid"

        return PostParseQualityOutcome(
            final_results=final_results,
            final_errors=final_errors,
            soft_warnings=soft_warnings,
            semantic_removed=semantic_removed,
            quality_schema_fields=quality_schema_fields,
            quality_snapshot=quality_snapshot,
            degraded_reasons=degraded_reasons,
            business_extraction_status=business_extraction_status,
        )


@dataclass(frozen=True)
class PostParseArtifactContextOutcome:
    soft_warnings: List[str]
    conversion_diag: Dict[str, Any]
    trace_hits: List[Dict[str, Any]]
    trace_stats: Dict[str, Any]
    polymorphic_links: List[Dict[str, Any]]


class PostParseArtifactRuntime:
    """Handle post-parse preview caching, trace materialization, and diagnostics artifact enrichment."""

    @staticmethod
    def _table_bbox5(table: Dict[str, Any]) -> List[float]:
        page_no = 0
        try:
            page_no = int(table.get("page", 0) or 0)
        except (TypeError, ValueError):
            page_no = 0

        bbox_norm = table.get("bbox_norm")
        if isinstance(bbox_norm, list) and len(bbox_norm) == 4 and page_no > 0:
            try:
                return [
                    float(page_no),
                    float(bbox_norm[0]),
                    float(bbox_norm[1]),
                    float(bbox_norm[2]),
                    float(bbox_norm[3]),
                ]
            except (TypeError, ValueError):
                pass

        bbox = table.get("bbox")
        if isinstance(bbox, list) and len(bbox) == 5:
            try:
                return [float(item) for item in bbox[:5]]
            except (TypeError, ValueError):
                pass

        for row in table.get("rows", []) if isinstance(table.get("rows"), list) else []:
            if not isinstance(row, dict):
                continue
            for cell in row.get("cells", []) if isinstance(row.get("cells"), list) else []:
                if not isinstance(cell, dict):
                    continue
                cell_bbox = cell.get("bbox")
                if not isinstance(cell_bbox, list) or len(cell_bbox) != 5:
                    continue
                try:
                    return [float(item) for item in cell_bbox[:5]]
                except (TypeError, ValueError):
                    continue
        return []

    def materialize_pdf_table_artifacts(
        self,
        *,
        file_name: str,
        file_hash: str,
        parse_input_name: str,
        parse_input_bytes: bytes,
        table_blocks: List[Dict[str, Any]],
        crop_pdf_region_png: Callable[[bytes, List[float], int], bytes | None] | None,
        write_artifact_bytes: Callable[..., tuple[str, str]],
    ) -> None:
        fallback_enabled = str(
            os.getenv("MODULE2_TRACE_TABLE_PDF_ROI_FALLBACK_ENABLED", "false") or ""
        ).strip().lower() in {"1", "true", "yes", "on"}
        if not fallback_enabled:
            return
        if not callable(crop_pdf_region_png):
            return
        if not str(parse_input_name or "").lower().endswith(".pdf"):
            return
        if not parse_input_bytes or not table_blocks:
            return

        dpi = max(144, int(os.getenv("MODULE2_TRACE_TABLE_CROP_DPI", "220") or 220))
        max_tables = max(1, int(os.getenv("MODULE2_TRACE_TABLE_ARTIFACT_MAX", "80") or 80))
        persisted = 0

        for idx, table in enumerate(table_blocks):
            if persisted >= max_tables:
                break
            if not isinstance(table, dict):
                continue
            if any(str(table.get(key) or "").strip() for key in ("image_path", "artifact_path", "artifact_url")):
                continue

            bbox5 = self._table_bbox5(table)
            if len(bbox5) != 5:
                continue

            if "bbox_norm" not in table:
                table["bbox_norm"] = [bbox5[1], bbox5[2], bbox5[3], bbox5[4]]

            try:
                cropped_png = crop_pdf_region_png(parse_input_bytes, bbox5, dpi)
            except Exception:
                cropped_png = None
            if not cropped_png:
                continue

            table_id = str(table.get("table_id") or f"table_{idx + 1}").strip() or f"table_{idx + 1}"
            try:
                artifact_path, artifact_url = write_artifact_bytes(
                    data=cropped_png,
                    file_name=f"{Path(file_name).stem}_{table_id}",
                    sub_dir=f"trace/table/{str(file_hash or '')[:12] or 'runtime'}",
                    ext=".png",
                )
            except Exception:
                continue
            if artifact_path:
                table["artifact_path"] = artifact_path
            if artifact_url:
                table["artifact_url"] = artifact_url
            persisted += 1

    def build_context(
        self,
        *,
        file_name: str,
        file_hash: str,
        parse_input_name: str,
        parse_input_bytes: bytes,
        final_results: Dict[str, Any],
        table_blocks: List[Dict[str, Any]],
        figure_blocks: List[Dict[str, Any]],
        markdown: str,
        bbox_map: Dict[str, Any],
        conversion_diag: Dict[str, Any],
        soft_warnings: List[str],
        write_artifact_bytes: Callable[..., tuple[str, str]],
        crop_pdf_region_png: Callable[[bytes, List[float], int], bytes | None] | None,
        build_document_trace_hits: Callable[..., List[Dict[str, Any]]],
        trace_stats_builder: Callable[[List[Dict[str, Any]]], Dict[str, Any]],
        build_polymorphic_links: Callable[..., List[Dict[str, Any]]],
        normalize_soft_warnings: Callable[[Any], List[str]],
    ) -> PostParseArtifactContextOutcome:
        resolved_soft_warnings = list(soft_warnings)
        resolved_conversion_diag = dict(conversion_diag)

        if parse_input_name.lower().endswith(".pdf"):
            try:
                pdf_preview_frag, pdf_preview_url = write_artifact_bytes(
                    data=parse_input_bytes,
                    file_name=f"{Path(file_name).stem}.pdf",
                    sub_dir="preview/pdf",
                    ext=".pdf",
                )
                resolved_conversion_diag.setdefault("pdf_preview_path", pdf_preview_frag)
                resolved_conversion_diag.setdefault("pdf_preview_url", pdf_preview_url)
            except Exception as exc:
                resolved_soft_warnings.append(f"pdf_preview_cache_failed:{type(exc).__name__}")
                resolved_soft_warnings = normalize_soft_warnings(resolved_soft_warnings)

        self.materialize_pdf_table_artifacts(
            file_name=file_name,
            file_hash=file_hash,
            parse_input_name=parse_input_name,
            parse_input_bytes=parse_input_bytes,
            table_blocks=table_blocks,
            crop_pdf_region_png=crop_pdf_region_png,
            write_artifact_bytes=write_artifact_bytes,
        )

        trace_hits = build_document_trace_hits(
            file_name=file_name,
            file_hash=file_hash,
            results=final_results,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
            markdown=markdown,
            bbox_map=bbox_map,
        )
        trace_stats = trace_stats_builder(trace_hits)
        polymorphic_links = build_polymorphic_links(results=final_results, trace_hits=trace_hits)
        return PostParseArtifactContextOutcome(
            soft_warnings=resolved_soft_warnings,
            conversion_diag=resolved_conversion_diag,
            trace_hits=trace_hits,
            trace_stats=trace_stats,
            polymorphic_links=polymorphic_links,
        )

    def enrich_diagnostics(
        self,
        *,
        file_name: str,
        file_hash: str,
        markdown_text: str,
        track: str,
        final_results: Dict[str, Any] | None = None,
        table_blocks: List[Dict[str, Any]],
        figure_blocks: List[Dict[str, Any]],
        diagnostics: Dict[str, Any],
        persist_assistant1_source_markdown_artifact: Callable[..., tuple[str, str, str, str]],
        persist_assistant_payload_artifact: Callable[..., tuple[str, str]],
        persist_field_results_artifact: Callable[..., tuple[str, str]] | None = None,
        promote_visual_diagnostics: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> Dict[str, Any]:
        merged = dict(diagnostics)
        (
            assistant1_markdown_path,
            assistant1_markdown_url,
            assistant1_source_manifest_path,
            assistant1_source_manifest_url,
        ) = persist_assistant1_source_markdown_artifact(
            file_name=file_name,
            file_hash=file_hash,
            markdown_text=markdown_text,
            track=track,
        )
        if assistant1_markdown_path:
            merged["assistant1_source_markdown_artifact_path"] = assistant1_markdown_path
            merged["assistant1_source_markdown_artifact_url"] = assistant1_markdown_url
        if assistant1_source_manifest_path:
            merged["assistant1_source_manifest_path"] = assistant1_source_manifest_path
            merged["assistant1_source_manifest_url"] = assistant1_source_manifest_url

        if callable(persist_field_results_artifact) and isinstance(final_results, dict) and final_results:
            artifact_path, artifact_url = persist_field_results_artifact(
                file_name=file_name,
                file_hash=file_hash,
                track=track,
                final_results=final_results,
            )
            if artifact_path:
                merged["field_results_artifact_path"] = artifact_path
                merged["field_results_artifact_url"] = artifact_url
                merged["field_results_artifact_version"] = "module2-field-results-v1"
                merged["field_results_artifact_count"] = len(final_results)

        if table_blocks or figure_blocks:
            artifact_path, artifact_url = persist_assistant_payload_artifact(
                file_name=file_name,
                file_hash=file_hash,
                table_blocks=table_blocks,
                figure_blocks=figure_blocks,
            )
            if artifact_path:
                merged["assistant_payload_artifact_path"] = artifact_path
                merged["assistant_payload_artifact_url"] = artifact_url
                merged["assistant_payload_version"] = "module2-assistant-payload-v1"

        return promote_visual_diagnostics(merged)


@dataclass(frozen=True)
class DiagnosticsBuildOutcome:
    parse_contract: Dict[str, Any]
    business_extraction_contract: Dict[str, Any]
    diagnostics: Dict[str, Any]


class DiagnosticsBuilderRuntime:
    """Assemble extraction diagnostics and contracts without touching side effects."""

    def build(
        self,
        *,
        parse_ms: int,
        extract_ms: int,
        total_ms: int,
        parse_input_name: str,
        parse_input_bytes: bytes,
        markdown: str,
        bbox_map: Dict[str, Any],
        table_blocks: List[Dict[str, Any]],
        figure_blocks: List[Dict[str, Any]],
        soft_warnings: List[str],
        parse_timeout_sec: float,
        extract_timeout_sec: float,
        nonpdf_total_budget_sec: float | None,
        word_parse_via_pdf: bool,
        word_parse_extract_budget_sec: float | None,
        word_convert_budget_sec: float | None,
        dynamic_extract_timeout_meta: Dict[str, Any],
        schema_meta: Dict[str, Any],
        allow_schema_llm: bool,
        schema_context_preview: str,
        file_size_mb: float,
        naming_template: str,
        graph_diagnostics: Dict[str, Any],
        used_quick_fallback: bool,
        quality_schema_fields: Dict[str, Any],
        semantic_removed: Dict[str, str],
        degraded_reasons: List[str],
        quality_snapshot: Dict[str, Any],
        polymorphic_links: List[Dict[str, Any]],
        business_extraction_status: str,
        chain_contract: Dict[str, Any],
        conversion_diag: Dict[str, Any],
        trace_stats: Dict[str, Any],
        parse_stats: Dict[str, Any] | None,
        nonpdf_preflight: Dict[str, Any] | None,
        nonpdf_budget: Dict[str, Any] | None,
        current_extraction_logic_version: Callable[[], str],
        current_extraction_logic_components: Callable[[], Dict[str, Any]],
        count_table_cells: Callable[[List[Dict[str, Any]]], int],
        table_quality_avg: Callable[[List[Dict[str, Any]]], float],
        table_source_counts: Callable[[List[Dict[str, Any]]], Dict[str, int]],
        count_figure_dataframe_cells: Callable[[List[Dict[str, Any]]], int],
        figure_pages: Callable[[List[Dict[str, Any]]], List[int]],
        figure_source_counts: Callable[[List[Dict[str, Any]]], Dict[str, int]],
        field_naming_version: str,
        schema_rule_versions: Dict[str, Any],
        is_word_document: bool,
    ) -> DiagnosticsBuildOutcome:
        parse_contract = {
            "status": "success" if chain_contract.get("satisfied") else "failed",
            "required": bool(chain_contract.get("required")),
            "satisfied": bool(chain_contract.get("satisfied")),
            "artifact_status": str(chain_contract.get("artifact_status") or "").strip(),
            "vision_status": str(chain_contract.get("vision_status") or "").strip(),
            "mineru_status": str(chain_contract.get("mineru_status") or "").strip(),
            "parse_track": str(chain_contract.get("parse_track") or "").strip(),
            "pipeline": str(chain_contract.get("pipeline") or "").strip(),
            "reasons": list(chain_contract.get("reasons") or [])[:12],
        }
        business_extraction_contract = {
            "status": business_extraction_status,
            "quality_status": "degraded" if degraded_reasons else "ok",
            "quality_reasons": degraded_reasons[:12],
            "filled_fields": int(quality_snapshot.get("filled_fields", 0) or 0),
            "target_fields": int(quality_snapshot.get("target_fields", 0) or 0),
            "coverage_ratio": float(quality_snapshot.get("coverage_ratio", 0.0) or 0.0),
            "avg_confidence": float(quality_snapshot.get("avg_confidence", 0.0) or 0.0),
        }
        diagnostics = {
            "parse_ms": parse_ms,
            "extract_ms": extract_ms,
            "total_ms": total_ms,
            "parse_input_name": parse_input_name,
            "parse_input_bytes": len(parse_input_bytes),
            "markdown_len": len(markdown),
            "refs": len(bbox_map),
            "table_count": len(table_blocks),
            "table_cells": count_table_cells(table_blocks),
            "table_quality_avg": table_quality_avg(table_blocks),
            "table_sources": table_source_counts(table_blocks),
            "figure_count": len(figure_blocks),
            "figure_dataframe_cells": count_figure_dataframe_cells(figure_blocks),
            "figure_pages": figure_pages(figure_blocks),
            "figure_sources": figure_source_counts(figure_blocks),
            "soft_warning_count": len(soft_warnings),
            "parse_timeout_sec": parse_timeout_sec,
            "extract_timeout_sec": extract_timeout_sec,
            "nonpdf_total_budget_sec": nonpdf_total_budget_sec,
            "word_pdf_required": bool(word_parse_via_pdf) if is_word_document else False,
            "word_parse_via_pdf": bool(word_parse_via_pdf) if is_word_document else False,
            "word_parse_extract_budget_sec": word_parse_extract_budget_sec,
            "word_convert_budget_sec": word_convert_budget_sec,
            "dynamic_extract_timeout": dynamic_extract_timeout_meta,
            "schema_mode": schema_meta.get("mode", "manual"),
            "schema_source": schema_meta.get("source", "request"),
            "schema_field_count": int(schema_meta.get("field_count", 0) or 0),
            "schema_fields": list(schema_meta.get("fields", []))[:24],
            "schema_raw_fields": list(schema_meta.get("raw_fields", []))[:24],
            "schema_llm_planner_enabled": bool(allow_schema_llm) and str(schema_meta.get("mode", "manual")) == "auto",
            "schema_llm_planner_attempted": bool(schema_meta.get("llm_attempted", False)),
            "schema_llm_planner_used": bool(schema_meta.get("llm_used", False)),
            "schema_rule_field_count": int(schema_meta.get("rule_field_count", 0) or 0),
            "schema_heuristic_field_count": int(schema_meta.get("heuristic_field_count", 0) or 0),
            "schema_deterministic_field_count": int(schema_meta.get("deterministic_field_count", 0) or 0),
            "schema_llm_context_chars": len(schema_context_preview),
            "schema_llm_file_size_mb": round(file_size_mb, 4),
            "prompt_version": str(graph_diagnostics.get("prompt_version") or ""),
            "prompt_names": list(graph_diagnostics.get("prompt_names") or []),
            "prompt_versions": dict(graph_diagnostics.get("prompt_versions") or {}),
            "extraction_logic_version": current_extraction_logic_version(),
            "extraction_logic_components": current_extraction_logic_components(),
            "field_naming_version": field_naming_version,
            "field_naming_template": str(schema_meta.get("naming_template") or naming_template or "common_document"),
            "field_naming_stats": dict(schema_meta.get("naming_stats") or {}),
            "field_name_mappings_preview": {
                str(raw): str(mapped)
                for raw, mapped in list((schema_meta.get("field_name_mappings") or {}).items())[:24]
            },
            "schema_rule_versions": dict(schema_rule_versions),
            "quick_fallback_used": bool(used_quick_fallback),
            "quality_target_field_count": len(quality_schema_fields),
            "quality_target_fields": list(quality_schema_fields.keys())[:24],
            "auto_result_filter_removed_count": len(semantic_removed),
            "auto_result_filter_removed_fields": list(semantic_removed.keys())[:24],
            "quality_status": "degraded" if degraded_reasons else "ok",
            "quality_reasons": degraded_reasons,
            "quality_snapshot": quality_snapshot,
            "polymorphic_link_count": len(polymorphic_links),
            "polymorphic_links": polymorphic_links[:40],
            "business_extraction_status": business_extraction_status,
            "chain_contract": chain_contract,
            "parse_contract": parse_contract,
            "business_extraction_contract": business_extraction_contract,
        }
        if conversion_diag:
            diagnostics.update(conversion_diag)
        diagnostics.update(trace_stats)

        if parse_stats:
            parse_stats_payload = dict(parse_stats)
            parse_stats_payload["business_extraction_status"] = business_extraction_status
            diagnostics["parse_stats"] = parse_stats_payload
            for key in (
                "chain_status",
                "artifact_status",
                "vision_status",
                "visual_pdf_profile",
                "visual_pdf_cue_hits",
                "visual_probe_chars_per_page",
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
                "visual_text_only_short_circuit_enabled",
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
                if key in parse_stats_payload:
                    diagnostics[key] = parse_stats_payload.get(key)
            mineru_run = parse_stats_payload.get("mineru_run") if isinstance(parse_stats_payload.get("mineru_run"), dict) else {}
            mineru_status = str(mineru_run.get("status", "") or "").strip()
            if mineru_status:
                diagnostics["mineru_status"] = mineru_status
            if "text_only_short_circuit" in mineru_run:
                diagnostics["text_only_short_circuit"] = bool(mineru_run.get("text_only_short_circuit"))
                parse_contract["text_only_short_circuit"] = bool(mineru_run.get("text_only_short_circuit"))
                parse_contract["text_only_short_circuit_method"] = str(
                    mineru_run.get("text_only_short_circuit_method") or ""
                ).strip()
            if "visual_mode" in parse_stats_payload:
                parse_contract["visual_mode"] = str(parse_stats_payload.get("visual_mode") or "").strip()
            if "visual_text_only_recovery" in parse_stats_payload:
                parse_contract["text_only_recovery"] = str(
                    parse_stats_payload.get("visual_text_only_recovery") or ""
                ).strip()
            if "visual_pdf_profile" in parse_stats_payload:
                parse_contract["visual_pdf_profile"] = str(parse_stats_payload.get("visual_pdf_profile") or "").strip()
            for key in (
                "plain_ext",
                "docx_chart_xml_seen",
                "docx_chart_xml_parsed",
                "docx_chart_xml_merged",
                "docx_chart_xml_unmatched",
                "docx_media_seen",
                "docx_media_used",
                "docx_media_parsed",
                "docx_media_parse_errors",
                "docx_media_skipped_duplicate",
                "docx_source_chart_merge_applied",
                "docx_source_chart_merge_ms",
            ):
                if key in parse_stats_payload:
                    diagnostics[key] = parse_stats_payload.get(key)

        if nonpdf_preflight is not None:
            diagnostics["nonpdf_profile"] = nonpdf_preflight.get("profile", "mixed")
            diagnostics["nonpdf_signals"] = nonpdf_preflight.get("signals", {})
        if nonpdf_budget is not None:
            diagnostics["nonpdf_budget"] = nonpdf_budget
            diagnostics["nonpdf_elapsed_ms"] = total_ms

        return DiagnosticsBuildOutcome(
            parse_contract=parse_contract,
            business_extraction_contract=business_extraction_contract,
            diagnostics=diagnostics,
        )


@dataclass(frozen=True)
class ExtractionResponseBundle:
    response: Any
    cache_payload: Dict[str, Any]


class ExtractionResponseRuntime:
    """Build the final extraction response and the cache payload persisted alongside it."""

    @staticmethod
    def _json_dump(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return value

    def build_bundle(
        self,
        *,
        file_name: str,
        file_hash: str,
        schema_hash: str,
        cache_key: str,
        track: str,
        cached: bool,
        final_results: Dict[str, Any],
        final_errors: List[str],
        soft_warnings: List[str],
        trace_hits: List[Any],
        trace_stats: Dict[str, Any],
        diagnostics: Dict[str, Any],
        table_blocks: List[Dict[str, Any]],
        figure_blocks: List[Dict[str, Any]],
        extraction_result_factory: Callable[[Dict[str, Any]], Any],
        document_response_factory: Callable[..., Any],
    ) -> ExtractionResponseBundle:
        response = document_response_factory(
            file_name=file_name,
            file_hash=file_hash,
            track=track,
            cached=cached,
            result=extraction_result_factory(final_results),
            errors=final_errors,
            soft_warnings=soft_warnings,
            trace_hits=trace_hits,
            trace_stats=trace_stats,
            diagnostics=diagnostics,
        )
        cache_payload = {
            "file_name": file_name,
            "file_hash": file_hash,
            "schema_hash": schema_hash,
            "cache_key": cache_key,
            "track": track,
            "cached": cached,
            "result": self._json_dump(response.result),
            "errors": response.errors,
            "soft_warnings": response.soft_warnings,
            "trace_hits": [self._json_dump(item) for item in response.trace_hits],
            "trace_stats": response.trace_stats,
            "diagnostics": diagnostics,
            "metrics": diagnostics,
            "tables": table_blocks,
            "figures": figure_blocks,
        }
        return ExtractionResponseBundle(response=response, cache_payload=cache_payload)


@dataclass(frozen=True)
class DocumentPostprocessDependencyBundle:
    post_parse_quality_runtime: Any
    post_parse_artifact_runtime: Any
    diagnostics_builder_runtime: Any
    extraction_response_runtime: Any
    graph_diagnostics_factory: Any
    is_word_file: Any
    current_extraction_logic_version: Any
    current_extraction_logic_components: Any
    field_naming_version: str
    schema_rule_versions: Dict[str, Any]
    normalize_soft_warnings: Any
    is_low_value_auto_schema_field_name: Any
    has_meaningful_value: Any
    is_low_value_quick_fallback_value: Any
    is_recoverable_timeout_error: Any
    filter_low_value_auto_results: Any
    effective_quality_schema_fields: Any
    result_quality_snapshot: Any
    strip_recovered_extract_warnings: Any
    write_artifact_bytes: Any
    build_document_trace_hits: Any
    trace_stats_builder: Any
    build_polymorphic_links: Any
    count_table_cells: Any
    table_quality_avg: Any
    table_source_counts: Any
    count_figure_dataframe_cells: Any
    figure_pages: Any
    figure_source_counts: Any
    persist_assistant1_source_markdown_artifact: Any
    persist_assistant_payload_artifact: Any
    promote_visual_diagnostics: Any
    extraction_result_factory: Any
    document_response_factory: Any
    crop_pdf_region_png: Any = None
    persist_field_results_artifact: Any = None


class DocumentPostprocessRuntime:
    """Coordinate post-parse quality, artifact enrichment, diagnostics, and response assembly."""

    @staticmethod
    def _require_dependency(name: str, value: Any) -> Any:
        if value is None:
            raise ValueError(f"DocumentPostprocessRuntime requires dependency '{name}'.")
        return value

    @staticmethod
    def _noop_crop_pdf_region_png(_parse_input_bytes: bytes, _bbox5: List[float], _dpi: int) -> bytes | None:
        return None

    @staticmethod
    def _noop_persist_field_results_artifact(**_kwargs) -> tuple[str, str]:
        return "", ""

    def __init__(
        self,
        *,
        post_parse_quality_runtime: Any = None,
        post_parse_artifact_runtime: Any = None,
        diagnostics_builder_runtime: Any = None,
        extraction_response_runtime: Any = None,
        graph_diagnostics_factory: Any = None,
        is_word_file: Any = None,
        current_extraction_logic_version: Any = None,
        current_extraction_logic_components: Any = None,
        field_naming_version: str | None = None,
        schema_rule_versions: Dict[str, Any] | None = None,
        normalize_soft_warnings: Any = None,
        is_low_value_auto_schema_field_name: Any = None,
        has_meaningful_value: Any = None,
        is_low_value_quick_fallback_value: Any = None,
        is_recoverable_timeout_error: Any = None,
        filter_low_value_auto_results: Any = None,
        effective_quality_schema_fields: Any = None,
        result_quality_snapshot: Any = None,
        strip_recovered_extract_warnings: Any = None,
        write_artifact_bytes: Any = None,
        crop_pdf_region_png: Any = None,
        build_document_trace_hits: Any = None,
        trace_stats_builder: Any = None,
        build_polymorphic_links: Any = None,
        count_table_cells: Any = None,
        table_quality_avg: Any = None,
        table_source_counts: Any = None,
        count_figure_dataframe_cells: Any = None,
        figure_pages: Any = None,
        figure_source_counts: Any = None,
        persist_assistant1_source_markdown_artifact: Any = None,
        persist_assistant_payload_artifact: Any = None,
        persist_field_results_artifact: Any = None,
        promote_visual_diagnostics: Any = None,
        extraction_result_factory: Any = None,
        document_response_factory: Any = None,
        dependency_bundle: DocumentPostprocessDependencyBundle | None = None,
    ) -> None:
        bundle = dependency_bundle or DocumentPostprocessDependencyBundle(
            post_parse_quality_runtime=self._require_dependency(
                "post_parse_quality_runtime",
                post_parse_quality_runtime,
            ),
            post_parse_artifact_runtime=self._require_dependency(
                "post_parse_artifact_runtime",
                post_parse_artifact_runtime,
            ),
            diagnostics_builder_runtime=self._require_dependency(
                "diagnostics_builder_runtime",
                diagnostics_builder_runtime,
            ),
            extraction_response_runtime=self._require_dependency(
                "extraction_response_runtime",
                extraction_response_runtime,
            ),
            graph_diagnostics_factory=self._require_dependency(
                "graph_diagnostics_factory",
                graph_diagnostics_factory,
            ),
            is_word_file=self._require_dependency("is_word_file", is_word_file),
            current_extraction_logic_version=self._require_dependency(
                "current_extraction_logic_version",
                current_extraction_logic_version,
            ),
            current_extraction_logic_components=self._require_dependency(
                "current_extraction_logic_components",
                current_extraction_logic_components,
            ),
            field_naming_version=str(self._require_dependency("field_naming_version", field_naming_version)),
            schema_rule_versions=dict(
                self._require_dependency("schema_rule_versions", schema_rule_versions)
            ),
            normalize_soft_warnings=self._require_dependency("normalize_soft_warnings", normalize_soft_warnings),
            is_low_value_auto_schema_field_name=self._require_dependency(
                "is_low_value_auto_schema_field_name",
                is_low_value_auto_schema_field_name,
            ),
            has_meaningful_value=self._require_dependency("has_meaningful_value", has_meaningful_value),
            is_low_value_quick_fallback_value=self._require_dependency(
                "is_low_value_quick_fallback_value",
                is_low_value_quick_fallback_value,
            ),
            is_recoverable_timeout_error=self._require_dependency(
                "is_recoverable_timeout_error",
                is_recoverable_timeout_error,
            ),
            filter_low_value_auto_results=self._require_dependency(
                "filter_low_value_auto_results",
                filter_low_value_auto_results,
            ),
            effective_quality_schema_fields=self._require_dependency(
                "effective_quality_schema_fields",
                effective_quality_schema_fields,
            ),
            result_quality_snapshot=self._require_dependency(
                "result_quality_snapshot",
                result_quality_snapshot,
            ),
            strip_recovered_extract_warnings=self._require_dependency(
                "strip_recovered_extract_warnings",
                strip_recovered_extract_warnings,
            ),
            write_artifact_bytes=self._require_dependency("write_artifact_bytes", write_artifact_bytes),
            build_document_trace_hits=self._require_dependency(
                "build_document_trace_hits",
                build_document_trace_hits,
            ),
            trace_stats_builder=self._require_dependency("trace_stats_builder", trace_stats_builder),
            build_polymorphic_links=self._require_dependency(
                "build_polymorphic_links",
                build_polymorphic_links,
            ),
            count_table_cells=self._require_dependency("count_table_cells", count_table_cells),
            table_quality_avg=self._require_dependency("table_quality_avg", table_quality_avg),
            table_source_counts=self._require_dependency("table_source_counts", table_source_counts),
            count_figure_dataframe_cells=self._require_dependency(
                "count_figure_dataframe_cells",
                count_figure_dataframe_cells,
            ),
            figure_pages=self._require_dependency("figure_pages", figure_pages),
            figure_source_counts=self._require_dependency("figure_source_counts", figure_source_counts),
            persist_assistant1_source_markdown_artifact=self._require_dependency(
                "persist_assistant1_source_markdown_artifact",
                persist_assistant1_source_markdown_artifact,
            ),
            persist_assistant_payload_artifact=self._require_dependency(
                "persist_assistant_payload_artifact",
                persist_assistant_payload_artifact,
            ),
            promote_visual_diagnostics=self._require_dependency(
                "promote_visual_diagnostics",
                promote_visual_diagnostics,
            ),
            extraction_result_factory=self._require_dependency(
                "extraction_result_factory",
                extraction_result_factory,
            ),
            document_response_factory=self._require_dependency(
                "document_response_factory",
                document_response_factory,
            ),
            crop_pdf_region_png=(
                crop_pdf_region_png
                if callable(crop_pdf_region_png)
                else self._noop_crop_pdf_region_png
            ),
            persist_field_results_artifact=(
                persist_field_results_artifact
                if callable(persist_field_results_artifact)
                else self._noop_persist_field_results_artifact
            ),
        )
        self._post_parse_quality_runtime = bundle.post_parse_quality_runtime
        self._post_parse_artifact_runtime = bundle.post_parse_artifact_runtime
        self._diagnostics_builder_runtime = bundle.diagnostics_builder_runtime
        self._extraction_response_runtime = bundle.extraction_response_runtime
        self._graph_diagnostics_factory = bundle.graph_diagnostics_factory
        self._is_word_file = bundle.is_word_file
        self._current_extraction_logic_version = bundle.current_extraction_logic_version
        self._current_extraction_logic_components = bundle.current_extraction_logic_components
        self._field_naming_version = bundle.field_naming_version
        self._schema_rule_versions = bundle.schema_rule_versions
        self._normalize_soft_warnings = bundle.normalize_soft_warnings
        self._is_low_value_auto_schema_field_name = bundle.is_low_value_auto_schema_field_name
        self._has_meaningful_value = bundle.has_meaningful_value
        self._is_low_value_quick_fallback_value = bundle.is_low_value_quick_fallback_value
        self._is_recoverable_timeout_error = bundle.is_recoverable_timeout_error
        self._filter_low_value_auto_results = bundle.filter_low_value_auto_results
        self._effective_quality_schema_fields = bundle.effective_quality_schema_fields
        self._result_quality_snapshot = bundle.result_quality_snapshot
        self._strip_recovered_extract_warnings = bundle.strip_recovered_extract_warnings
        self._write_artifact_bytes = bundle.write_artifact_bytes
        self._crop_pdf_region_png = (
            bundle.crop_pdf_region_png
            if callable(bundle.crop_pdf_region_png)
            else self._noop_crop_pdf_region_png
        )
        self._build_document_trace_hits = bundle.build_document_trace_hits
        self._trace_stats_builder = bundle.trace_stats_builder
        self._build_polymorphic_links = bundle.build_polymorphic_links
        self._count_table_cells = bundle.count_table_cells
        self._table_quality_avg = bundle.table_quality_avg
        self._table_source_counts = bundle.table_source_counts
        self._count_figure_dataframe_cells = bundle.count_figure_dataframe_cells
        self._figure_pages = bundle.figure_pages
        self._figure_source_counts = bundle.figure_source_counts
        self._persist_assistant1_source_markdown_artifact = bundle.persist_assistant1_source_markdown_artifact
        self._persist_assistant_payload_artifact = bundle.persist_assistant_payload_artifact
        self._persist_field_results_artifact = (
            bundle.persist_field_results_artifact
            if callable(bundle.persist_field_results_artifact)
            else self._noop_persist_field_results_artifact
        )
        self._promote_visual_diagnostics = bundle.promote_visual_diagnostics
        self._extraction_result_factory = bundle.extraction_result_factory
        self._document_response_factory = bundle.document_response_factory

    def build_pipeline_response_bundle(
        self,
        *,
        file_name: str,
        file_hash: str,
        schema_hash: str,
        cache_key: str,
        pipeline_outcome: Any,
        total_ms: int,
    ):
        return self.build_response_bundle(
            file_name=file_name,
            file_hash=file_hash,
            schema_hash=schema_hash,
            cache_key=cache_key,
            parse_input_name=getattr(pipeline_outcome, "parse_input_name", ""),
            parse_input_bytes=getattr(pipeline_outcome, "parse_input_bytes", b""),
            parse_track=getattr(pipeline_outcome, "parse_track", ""),
            parse_ms=int(getattr(pipeline_outcome, "parse_ms", 0) or 0),
            extract_ms=int(getattr(pipeline_outcome, "extract_ms", 0) or 0),
            total_ms=total_ms,
            parse_warning=str(getattr(pipeline_outcome, "parse_warning", "") or ""),
            parse_timeout_sec=float(getattr(pipeline_outcome, "parse_timeout_sec", 0.0) or 0.0),
            extract_timeout_sec=float(getattr(pipeline_outcome, "extract_timeout_sec", 0.0) or 0.0),
            nonpdf_total_budget_sec=getattr(pipeline_outcome, "nonpdf_total_budget_sec", None),
            word_parse_via_pdf=bool(getattr(pipeline_outcome, "word_parse_via_pdf", False)),
            word_parse_extract_budget_sec=getattr(pipeline_outcome, "word_parse_extract_budget_sec", None),
            word_convert_budget_sec=getattr(pipeline_outcome, "word_convert_budget_sec", None),
            dynamic_extract_timeout_meta=dict(getattr(pipeline_outcome, "dynamic_extract_timeout_meta", {}) or {}),
            schema_meta=dict(getattr(pipeline_outcome, "schema_meta", {}) or {}),
            allow_schema_llm=bool(getattr(pipeline_outcome, "allow_schema_llm", False)),
            schema_context_preview=str(getattr(pipeline_outcome, "schema_context_preview", "") or ""),
            file_size_mb=float(getattr(pipeline_outcome, "file_size_mb", 0.0) or 0.0),
            naming_template=str(getattr(pipeline_outcome, "naming_template", "") or ""),
            used_quick_fallback=bool(getattr(pipeline_outcome, "used_quick_fallback", False)),
            chain_contract=dict(getattr(pipeline_outcome, "chain_contract", {}) or {}),
            final_state=dict(getattr(pipeline_outcome, "final_state", {}) or {}),
            effective_schema_fields=dict(getattr(pipeline_outcome, "effective_schema_fields", {}) or {}),
            marked_markdown=str(getattr(pipeline_outcome, "marked_markdown", "") or ""),
            bbox_map=dict(getattr(pipeline_outcome, "bbox_map", {}) or {}),
            table_blocks=list(getattr(pipeline_outcome, "table_blocks", []) or []),
            figure_blocks=list(getattr(pipeline_outcome, "figure_blocks", []) or []),
            conversion_diag=dict(getattr(pipeline_outcome, "conversion_diag", {}) or {}),
            parse_stats=getattr(pipeline_outcome, "parse_stats", None),
            nonpdf_preflight=getattr(pipeline_outcome, "nonpdf_preflight", None),
            nonpdf_budget=getattr(pipeline_outcome, "nonpdf_budget", None),
        )

    def build_response_bundle(
        self,
        *,
        file_name: str,
        file_hash: str,
        schema_hash: str,
        cache_key: str,
        parse_input_name: str,
        parse_input_bytes: bytes,
        parse_track: str,
        parse_ms: int,
        extract_ms: int,
        total_ms: int,
        parse_warning: str,
        parse_timeout_sec: float,
        extract_timeout_sec: float,
        nonpdf_total_budget_sec: float | None,
        word_parse_via_pdf: bool,
        word_parse_extract_budget_sec: float | None,
        word_convert_budget_sec: float | None,
        dynamic_extract_timeout_meta: Dict[str, Any],
        schema_meta: Dict[str, Any],
        allow_schema_llm: bool,
        schema_context_preview: str,
        file_size_mb: float,
        naming_template: str,
        used_quick_fallback: bool,
        chain_contract: Dict[str, Any],
        final_state: Dict[str, Any],
        effective_schema_fields: Dict[str, Any],
        marked_markdown: str,
        bbox_map: Dict[str, Any],
        table_blocks: List[Dict[str, Any]],
        figure_blocks: List[Dict[str, Any]],
        conversion_diag: Dict[str, Any],
        parse_stats: Dict[str, Any] | None,
        nonpdf_preflight: Dict[str, Any] | None,
        nonpdf_budget: Dict[str, Any] | None,
    ):
        post_parse_quality = self._post_parse_quality_runtime.process(
            final_state=final_state,
            file_name=file_name,
            parse_warning=parse_warning,
            nonpdf_total_budget_sec=nonpdf_total_budget_sec,
            total_ms=total_ms,
            used_quick_fallback=used_quick_fallback,
            schema_meta=schema_meta,
            effective_schema_fields=effective_schema_fields,
            normalize_soft_warnings=self._normalize_soft_warnings,
            is_low_value_auto_schema_field_name=self._is_low_value_auto_schema_field_name,
            has_meaningful_value=self._has_meaningful_value,
            is_low_value_quick_fallback_value=self._is_low_value_quick_fallback_value,
            is_recoverable_timeout_error=self._is_recoverable_timeout_error,
            filter_low_value_auto_results=self._filter_low_value_auto_results,
            effective_quality_schema_fields=self._effective_quality_schema_fields,
            result_quality_snapshot=self._result_quality_snapshot,
            strip_recovered_extract_warnings=self._strip_recovered_extract_warnings,
        )

        post_parse_artifact_context = self._post_parse_artifact_runtime.build_context(
            file_name=file_name,
            file_hash=file_hash,
            parse_input_name=parse_input_name,
            parse_input_bytes=parse_input_bytes,
            final_results=post_parse_quality.final_results,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
            markdown=marked_markdown,
            bbox_map=bbox_map,
            conversion_diag=conversion_diag,
            soft_warnings=post_parse_quality.soft_warnings,
            write_artifact_bytes=self._write_artifact_bytes,
            crop_pdf_region_png=self._crop_pdf_region_png,
            build_document_trace_hits=self._build_document_trace_hits,
            trace_stats_builder=self._trace_stats_builder,
            build_polymorphic_links=self._build_polymorphic_links,
            normalize_soft_warnings=self._normalize_soft_warnings,
        )
        business_extraction_status = post_parse_quality.business_extraction_status

        diagnostics_outcome = self._diagnostics_builder_runtime.build(
            parse_ms=parse_ms,
            extract_ms=extract_ms,
            total_ms=total_ms,
            parse_input_name=parse_input_name,
            parse_input_bytes=parse_input_bytes,
            markdown=marked_markdown,
            bbox_map=bbox_map,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
            soft_warnings=post_parse_artifact_context.soft_warnings,
            parse_timeout_sec=parse_timeout_sec,
            extract_timeout_sec=extract_timeout_sec,
            nonpdf_total_budget_sec=nonpdf_total_budget_sec,
            word_parse_via_pdf=word_parse_via_pdf,
            word_parse_extract_budget_sec=word_parse_extract_budget_sec,
            word_convert_budget_sec=word_convert_budget_sec,
            dynamic_extract_timeout_meta=dynamic_extract_timeout_meta,
            schema_meta=schema_meta,
            allow_schema_llm=allow_schema_llm,
            schema_context_preview=schema_context_preview,
            file_size_mb=file_size_mb,
            naming_template=naming_template,
            graph_diagnostics=self._graph_diagnostics_factory(),
            used_quick_fallback=used_quick_fallback,
            quality_schema_fields=post_parse_quality.quality_schema_fields,
            semantic_removed=post_parse_quality.semantic_removed,
            degraded_reasons=post_parse_quality.degraded_reasons,
            quality_snapshot=post_parse_quality.quality_snapshot,
            polymorphic_links=post_parse_artifact_context.polymorphic_links,
            business_extraction_status=business_extraction_status,
            chain_contract=chain_contract,
            conversion_diag=post_parse_artifact_context.conversion_diag,
            trace_stats=post_parse_artifact_context.trace_stats,
            parse_stats=parse_stats if isinstance(parse_stats, dict) else None,
            nonpdf_preflight=nonpdf_preflight if isinstance(nonpdf_preflight, dict) else None,
            nonpdf_budget=nonpdf_budget if isinstance(nonpdf_budget, dict) else None,
            current_extraction_logic_version=self._current_extraction_logic_version,
            current_extraction_logic_components=self._current_extraction_logic_components,
            count_table_cells=self._count_table_cells,
            table_quality_avg=self._table_quality_avg,
            table_source_counts=self._table_source_counts,
            count_figure_dataframe_cells=self._count_figure_dataframe_cells,
            figure_pages=self._figure_pages,
            figure_source_counts=self._figure_source_counts,
            field_naming_version=self._field_naming_version,
            schema_rule_versions=self._schema_rule_versions,
            is_word_document=self._is_word_file(file_name),
        )

        diagnostics = self._post_parse_artifact_runtime.enrich_diagnostics(
            file_name=file_name,
            file_hash=file_hash,
            markdown_text=marked_markdown,
            track=parse_track,
            final_results=post_parse_quality.final_results,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
            diagnostics=diagnostics_outcome.diagnostics,
            persist_assistant1_source_markdown_artifact=self._persist_assistant1_source_markdown_artifact,
            persist_assistant_payload_artifact=self._persist_assistant_payload_artifact,
            persist_field_results_artifact=self._persist_field_results_artifact,
            promote_visual_diagnostics=self._promote_visual_diagnostics,
        )

        return self._extraction_response_runtime.build_bundle(
            file_name=file_name,
            file_hash=file_hash,
            schema_hash=schema_hash,
            cache_key=cache_key,
            track=parse_track,
            cached=False,
            final_results=post_parse_quality.final_results,
            final_errors=post_parse_quality.final_errors,
            soft_warnings=post_parse_artifact_context.soft_warnings,
            trace_hits=post_parse_artifact_context.trace_hits,
            trace_stats=post_parse_artifact_context.trace_stats,
            diagnostics=diagnostics,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
            extraction_result_factory=self._extraction_result_factory,
            document_response_factory=self._document_response_factory,
        )
