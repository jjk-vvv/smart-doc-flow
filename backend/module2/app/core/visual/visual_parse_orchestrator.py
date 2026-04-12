from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple


TableBlocks = List[Dict[str, Any]]
FigureBlocks = List[Dict[str, Any]]
PageLines = Dict[int, List[str]]
AppendRef = Callable[[List[str], Dict[str, List[float]], str, str, List[float]], None]
SplitPageText = Callable[[str], List[str]]
BuildVisualParseStatusFields = Callable[..., Dict[str, Any]]
MergeSamePageTables = Callable[[TableBlocks], TableBlocks]
MergeCrossPageTables = Callable[[TableBlocks], TableBlocks]
PruneFragmentTables = Callable[[TableBlocks], TableBlocks]
MergeFigureBlocks = Callable[[FigureBlocks, FigureBlocks], FigureBlocks]
NormalizeText = Callable[[str], str]
BuildTextOnlyResult = Callable[..., Optional[Tuple[str, Dict[str, List[float]], TableBlocks, Dict[str, Any]]]]
FinalizeNoBlocks = Callable[..., Dict[str, Any]]
FinalizeSuccess = Callable[..., Dict[str, Any]]


class VisualStatusBuilderRuntime:
    """Build normalized visual-first status fields from MinerU and vision counters."""

    @staticmethod
    def _resolve_baseline_artifact_ready(
        *,
        visual_mode: str,
        text_char_count: int,
        mineru_status: str,
        mineru_item_count: int,
        mineru_image_asset_count: int,
        content_list_path: str,
        markdown_path: str,
    ) -> bool:
        if mineru_status == "ok":
            return True
        if content_list_path or markdown_path:
            return True
        if mineru_item_count > 0 or mineru_image_asset_count > 0:
            return True
        return visual_mode == "text_only" and text_char_count > 0

    def build_status_fields(
        self,
        *,
        visual_mode: str,
        layout_object_count: int,
        selected_object_count: int,
        table_count: int,
        figure_count: int,
        text_char_count: int,
        vision_ready: bool,
        vision_candidate_count: int,
        vision_attempted_count: int,
        vision_success_count: int,
        vision_empty_count: int,
        mineru_run_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        mineru_run = mineru_run_meta if isinstance(mineru_run_meta, dict) else {}
        mineru_status = str(mineru_run.get("status", "") or "").strip().lower()
        mineru_item_count = int(mineru_run.get("content_list_item_count", 0) or 0)
        mineru_image_asset_count = int(mineru_run.get("images_count", 0) or 0)
        content_list_path = str(mineru_run.get("content_list_path", "") or "").strip()
        markdown_path = str(mineru_run.get("markdown_path", "") or "").strip()
        baseline_artifact_ready = self._resolve_baseline_artifact_ready(
            visual_mode=visual_mode,
            text_char_count=int(text_char_count or 0),
            mineru_status=mineru_status,
            mineru_item_count=mineru_item_count,
            mineru_image_asset_count=mineru_image_asset_count,
            content_list_path=content_list_path,
            markdown_path=markdown_path,
        )

        if visual_mode == "text_only":
            artifact_status = "artifact_text_only" if text_char_count > 0 else "artifact_empty"
        elif table_count + figure_count >= 4 or layout_object_count >= 8 or mineru_image_asset_count >= 6:
            artifact_status = "artifact_rich"
        elif (
            layout_object_count > 0
            or selected_object_count > 0
            or mineru_item_count > 0
            or mineru_image_asset_count > 0
            or text_char_count > 0
        ):
            artifact_status = "artifact_sparse"
        else:
            artifact_status = "artifact_empty"

        if not vision_ready:
            vision_status = "not_needed"
        elif vision_candidate_count <= 0 or vision_attempted_count <= 0:
            vision_status = "skipped_no_assets"
        elif vision_success_count <= 0:
            vision_status = "attempted_empty"
        elif vision_success_count < vision_attempted_count:
            vision_status = "attempted_partial"
        else:
            vision_status = "attempted_success"

        return {
            "chain_status": "success" if (baseline_artifact_ready or artifact_status != "artifact_empty") else "failed",
            "artifact_status": artifact_status,
            "vision_status": vision_status,
            "visual_baseline_artifact_ready": bool(baseline_artifact_ready),
            "mineru_item_count": int(mineru_item_count),
            "mineru_image_asset_count": int(mineru_image_asset_count),
            "mineru_content_list_present": bool(content_list_path),
            "mineru_markdown_present": bool(markdown_path),
            "visual_selected_object_count": int(selected_object_count),
            "visual_vision_candidate_count": int(vision_candidate_count),
            "visual_vision_attempted_count": int(vision_attempted_count),
            "visual_vision_success_count": int(vision_success_count),
            "visual_vision_empty_count": int(vision_empty_count),
        }


class VisualTextOnlyBuilderRuntime:
    """Build the text-only visual-first recovery result while preserving parser outputs."""

    def __init__(
        self,
        *,
        visual_text_only_min_chars: int,
        normalize_text: NormalizeText,
        append_ref: AppendRef,
        split_page_text: SplitPageText,
        build_visual_parse_status_fields: BuildVisualParseStatusFields,
    ) -> None:
        self.visual_text_only_min_chars = max(0, int(visual_text_only_min_chars or 0))
        self._normalize_text = normalize_text
        self._append_ref = append_ref
        self._split_page_text = split_page_text
        self._build_visual_parse_status_fields = build_visual_parse_status_fields

    def build_result(
        self,
        *,
        page_lines: PageLines,
        page_count: int,
        visual_t0: float,
        layout_extract_ms: int,
        native_context_ms: int,
        merge_context_ms: int,
        failure_reason: str,
        layout_object_count: int,
        mineru_run_meta: Dict[str, Any],
        select_ms: int = 0,
        object_selection_stats: Optional[Dict[str, Any]] = None,
        extra_stats: Optional[Dict[str, Any]] = None,
        runtime_limits: Optional[Dict[str, Any]] = None,
    ) -> Optional[Tuple[str, Dict[str, List[float]], TableBlocks, Dict[str, Any]]]:
        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        text_char_count = 0

        for page_no in range(1, max(1, int(page_count)) + 1):
            lines = [self._normalize_text(item) for item in page_lines.get(page_no, [])]
            lines = [item for item in lines if item]
            if not lines:
                placeholder = f"[Page {page_no}] No extractable visual text."
                self._append_ref(parts, bbox_map, f"p{page_no}_c1", placeholder, [float(page_no), 0.0, 0.0, 1.0, 1.0])
                continue

            merged_text = "\n".join(lines)
            chunks = self._split_page_text(merged_text)
            if not chunks:
                chunks = [merged_text[:700]]
            for chunk_idx, chunk in enumerate(chunks, start=1):
                text_char_count += len(chunk)
                ref_id = f"p{page_no}_c{chunk_idx}"
                self._append_ref(parts, bbox_map, ref_id, chunk, [float(page_no), 0.0, 0.0, 1.0, 1.0])

        mineru_status = str(mineru_run_meta.get("status", "") or "").strip().lower()
        if text_char_count < self.visual_text_only_min_chars and mineru_status != "ok":
            return None

        stats: Dict[str, Any] = {
            "pipeline": "visual_first",
            "visual_mode": "text_only",
            "visual_text_only": True,
            "visual_text_only_recovery": failure_reason,
            "visual_page_count": int(page_count),
            "visual_layout_object_count": int(layout_object_count),
            "visual_ref_count": len(bbox_map),
            "visual_text_char_count": int(text_char_count),
            "visual_table_count": 0,
            "visual_figure_count": 0,
            "visual_phase_ms": {
                "layout_extract_ms": layout_extract_ms,
                "native_context_ms": native_context_ms,
                "context_merge_ms": merge_context_ms,
                "object_select_ms": select_ms,
                "total_ms": int((time.perf_counter() - visual_t0) * 1000),
            },
        }
        if runtime_limits:
            stats["visual_runtime_limits"] = dict(runtime_limits)
        if extra_stats:
            stats.update(dict(extra_stats))
        if object_selection_stats:
            stats.update(dict(object_selection_stats))
        stats.update(
            self._build_visual_parse_status_fields(
                visual_mode="text_only",
                layout_object_count=layout_object_count,
                selected_object_count=0,
                table_count=0,
                figure_count=0,
                text_char_count=text_char_count,
                vision_ready=False,
                vision_candidate_count=0,
                vision_attempted_count=0,
                vision_success_count=0,
                vision_empty_count=0,
            )
        )
        if mineru_run_meta:
            stats["mineru_run"] = dict(mineru_run_meta)
        return "\n".join(parts), bbox_map, [], stats


class VisualParseFinalizerRuntime:
    """Finalize visual-first parse outputs and assemble stable parse stats."""

    def __init__(
        self,
        *,
        table_merge_enable: bool,
        visual_vision_concurrency: int,
        default_figure_refine_budget: int,
        build_visual_parse_status_fields: BuildVisualParseStatusFields,
        merge_same_page_tables: MergeSamePageTables,
        merge_cross_page_tables: MergeCrossPageTables,
        prune_fragment_tables: PruneFragmentTables,
        merge_figure_blocks: MergeFigureBlocks,
    ) -> None:
        self.table_merge_enable = bool(table_merge_enable)
        self.visual_vision_concurrency = max(1, int(visual_vision_concurrency or 1))
        self.default_figure_refine_budget = max(0, int(default_figure_refine_budget or 0))
        self._build_visual_parse_status_fields = build_visual_parse_status_fields
        self._merge_same_page_tables = merge_same_page_tables
        self._merge_cross_page_tables = merge_cross_page_tables
        self._prune_fragment_tables = prune_fragment_tables
        self._merge_figure_blocks = merge_figure_blocks

    def finalize_no_blocks(
        self,
        *,
        native_page_count: int,
        selected_objects: List[Dict[str, Any]],
        objects: List[Dict[str, Any]],
        runtime_limits: Dict[str, Any],
        visual_method_stats: Dict[str, Any],
        selected_table_candidates: int,
        selected_figure_candidates: int,
        object_selection_stats: Dict[str, Any],
        vision_jobs: List[Dict[str, Any]],
        vision_job_error_count: int,
        vision_serial_recovery_retry_count: int,
        vision_serial_recovery_success_count: int,
        figure_refine_grants: int,
        layout_extract_ms: int,
        native_context_ms: int,
        merge_context_ms: int,
        select_ms: int,
        table_crop_ms: int,
        table_vision_ms: int,
        figure_crop_ms: int,
        figure_vision_ms: int,
        visual_vision_wall_ms: int,
        visual_t0: float,
        page_lines: PageLines,
        vision_ready: bool,
        vision_candidate_count: int,
        vision_attempted_count: int,
        vision_success_count: int,
        vision_empty_count: int,
        mineru_run_meta: Dict[str, Any],
        vision: Any = None,
    ) -> Dict[str, Any]:
        stats = {
            "pipeline": "visual_first",
            "visual_page_count": int(native_page_count),
            "visual_layout_object_count": len(selected_objects),
            "visual_runtime_limits": runtime_limits,
            **visual_method_stats,
            "visual_selected_table_candidates": selected_table_candidates,
            "visual_selected_figure_candidates": selected_figure_candidates,
            **object_selection_stats,
            "visual_failure": "no_visual_blocks",
            "visual_vision_concurrency": int(self.visual_vision_concurrency),
            "visual_vision_job_count": len(vision_jobs),
            "visual_vision_job_error_count": int(vision_job_error_count),
            "visual_vision_serial_recovery_retry_count": int(vision_serial_recovery_retry_count),
            "visual_vision_serial_recovery_success_count": int(vision_serial_recovery_success_count),
            "visual_figure_refine_slots_total": int(
                runtime_limits.get("figure_refine_budget", self.default_figure_refine_budget)
                or self.default_figure_refine_budget
            ),
            "visual_figure_refine_slots_used": int(figure_refine_grants),
            "visual_phase_ms": {
                "layout_extract_ms": layout_extract_ms,
                "native_context_ms": native_context_ms,
                "context_merge_ms": merge_context_ms,
                "object_select_ms": select_ms,
                "table_crop_ms": table_crop_ms,
                "table_vision_ms": table_vision_ms,
                "figure_crop_ms": figure_crop_ms,
                "figure_vision_ms": figure_vision_ms,
                "vision_wall_ms": visual_vision_wall_ms,
                "total_ms": int((time.perf_counter() - visual_t0) * 1000),
            },
        }
        stats.update(
            self._build_visual_parse_status_fields(
                visual_mode="artifact_only",
                layout_object_count=len(objects),
                selected_object_count=len(selected_objects),
                table_count=0,
                figure_count=0,
                text_char_count=self._count_text_chars(page_lines),
                vision_ready=vision_ready,
                vision_candidate_count=vision_candidate_count,
                vision_attempted_count=vision_attempted_count,
                vision_success_count=vision_success_count,
                vision_empty_count=vision_empty_count,
            )
        )
        self._attach_optional_debug(
            stats=stats,
            vision_ready=vision_ready,
            vision=vision,
            mineru_run_meta=mineru_run_meta,
        )
        return {"stats": stats, "figure_blocks": []}

    def finalize_success(
        self,
        *,
        native_page_count: int,
        selected_objects: List[Dict[str, Any]],
        objects: List[Dict[str, Any]],
        runtime_limits: Dict[str, Any],
        visual_method_stats: Dict[str, Any],
        selected_table_candidates: int,
        selected_figure_candidates: int,
        object_selection_stats: Dict[str, Any],
        bbox_map: Dict[str, List[float]],
        table_blocks: TableBlocks,
        figure_blocks: FigureBlocks,
        table_source: str,
        figure_source: str,
        vision_jobs: List[Dict[str, Any]],
        vision_job_error_count: int,
        vision_serial_recovery_retry_count: int,
        vision_serial_recovery_success_count: int,
        figure_refine_grants: int,
        layout_extract_ms: int,
        native_context_ms: int,
        merge_context_ms: int,
        select_ms: int,
        table_crop_ms: int,
        table_vision_ms: int,
        figure_crop_ms: int,
        figure_vision_ms: int,
        visual_vision_wall_ms: int,
        visual_t0: float,
        page_lines: PageLines,
        vision_ready: bool,
        vision_candidate_count: int,
        vision_attempted_count: int,
        vision_success_count: int,
        vision_empty_count: int,
        mineru_run_meta: Dict[str, Any],
        vision: Any = None,
    ) -> Dict[str, Any]:
        postprocess_t0 = time.perf_counter()
        if table_blocks and self.table_merge_enable:
            table_blocks = self._merge_same_page_tables(table_blocks)
            table_blocks = self._merge_cross_page_tables(table_blocks)
        table_blocks = self._prune_fragment_tables(table_blocks)
        figure_blocks = self._merge_figure_blocks([], figure_blocks)
        postprocess_ms = int((time.perf_counter() - postprocess_t0) * 1000)

        stats = {
            "pipeline": "visual_first",
            "visual_page_count": int(native_page_count),
            "visual_layout_object_count": len(selected_objects),
            "visual_runtime_limits": runtime_limits,
            **visual_method_stats,
            "visual_selected_table_candidates": selected_table_candidates,
            "visual_selected_figure_candidates": selected_figure_candidates,
            **object_selection_stats,
            "visual_ref_count": len(bbox_map),
            "visual_table_count": len(table_blocks),
            "visual_figure_count": len(figure_blocks),
            "visual_table_source": table_source,
            "visual_figure_source": figure_source,
            "visual_vision_concurrency": int(self.visual_vision_concurrency),
            "visual_vision_job_count": len(vision_jobs),
            "visual_vision_job_error_count": int(vision_job_error_count),
            "visual_vision_serial_recovery_retry_count": int(vision_serial_recovery_retry_count),
            "visual_vision_serial_recovery_success_count": int(vision_serial_recovery_success_count),
            "visual_figure_refine_slots_total": int(
                runtime_limits.get("figure_refine_budget", self.default_figure_refine_budget)
                or self.default_figure_refine_budget
            ),
            "visual_figure_refine_slots_used": int(figure_refine_grants),
            "visual_phase_ms": {
                "layout_extract_ms": layout_extract_ms,
                "native_context_ms": native_context_ms,
                "context_merge_ms": merge_context_ms,
                "object_select_ms": select_ms,
                "table_crop_ms": table_crop_ms,
                "table_vision_ms": table_vision_ms,
                "figure_crop_ms": figure_crop_ms,
                "figure_vision_ms": figure_vision_ms,
                "vision_wall_ms": visual_vision_wall_ms,
                "postprocess_ms": postprocess_ms,
                "total_ms": int((time.perf_counter() - visual_t0) * 1000),
            },
        }
        stats.update(
            self._build_visual_parse_status_fields(
                visual_mode="visual_blocks",
                layout_object_count=len(objects),
                selected_object_count=len(selected_objects),
                table_count=len(table_blocks),
                figure_count=len(figure_blocks),
                text_char_count=self._count_text_chars(page_lines),
                vision_ready=vision_ready,
                vision_candidate_count=vision_candidate_count,
                vision_attempted_count=vision_attempted_count,
                vision_success_count=vision_success_count,
                vision_empty_count=vision_empty_count,
            )
        )
        self._attach_optional_debug(
            stats=stats,
            vision_ready=vision_ready,
            vision=vision,
            mineru_run_meta=mineru_run_meta,
        )
        return {
            "table_blocks": table_blocks,
            "figure_blocks": figure_blocks,
            "stats": stats,
            "postprocess_ms": int(postprocess_ms),
        }

    def _attach_optional_debug(
        self,
        *,
        stats: Dict[str, Any],
        vision_ready: bool,
        vision: Any,
        mineru_run_meta: Dict[str, Any],
    ) -> None:
        if vision_ready and vision is not None:
            try:
                stats["visual_vision_stats"] = vision.get_stats_snapshot()
                stats["visual_vision_last_debug"] = vision.get_last_debug()
            except Exception:
                pass
        if mineru_run_meta:
            stats["mineru_run"] = dict(mineru_run_meta)

    @staticmethod
    def _count_text_chars(page_lines: PageLines) -> int:
        return sum(len(str(item or "")) for lines in page_lines.values() for item in lines)


class VisualParseOrchestratorRuntime:
    """Compose text-only recovery and final visual parse outcomes."""

    def __init__(
        self,
        *,
        build_text_only_result: BuildTextOnlyResult,
        finalize_no_blocks: FinalizeNoBlocks,
        finalize_success: FinalizeSuccess,
    ) -> None:
        self._build_text_only_result = build_text_only_result
        self._finalize_no_blocks = finalize_no_blocks
        self._finalize_success = finalize_success

    def resolve_no_layout_objects(
        self,
        *,
        native_page_count: int,
        mineru_status: str,
        runtime_limits: Dict[str, Any],
        visual_method_stats: Dict[str, Any],
        layout_extract_ms: int,
        native_context_ms: int,
        merge_context_ms: int,
        visual_t0: float,
        page_lines: PageLines,
        mineru_run_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        if mineru_status and mineru_status != "ok":
            stats = {
                "pipeline": "visual_first",
                "visual_page_count": int(native_page_count),
                "visual_failure": "no_layout_objects",
                "visual_runtime_limits": runtime_limits,
                **visual_method_stats,
                "visual_phase_ms": {
                    "layout_extract_ms": layout_extract_ms,
                    "native_context_ms": native_context_ms,
                    "context_merge_ms": merge_context_ms,
                    "total_ms": int((time.perf_counter() - visual_t0) * 1000),
                },
                "chain_status": "failed",
                "artifact_status": "artifact_empty",
                "vision_status": "skipped_no_assets",
                "visual_baseline_artifact_ready": False,
            }
            if mineru_run_meta:
                stats["mineru_run"] = dict(mineru_run_meta)
            return self._build_outcome(result=None, stats=stats, figure_blocks=[])

        built = self._build_text_only_result(
            page_lines=page_lines,
            page_count=native_page_count,
            visual_t0=visual_t0,
            layout_extract_ms=layout_extract_ms,
            native_context_ms=native_context_ms,
            merge_context_ms=merge_context_ms,
            failure_reason="no_layout_objects",
            layout_object_count=0,
            mineru_run_meta=mineru_run_meta,
            extra_stats=visual_method_stats,
            runtime_limits=runtime_limits,
        )
        if built is not None:
            markdown, bbox_map, table_blocks, stats = built
            return self._build_outcome(
                result=(markdown, bbox_map, table_blocks),
                stats=stats,
                figure_blocks=[],
            )

        stats = {
            "pipeline": "visual_first",
            "visual_page_count": int(native_page_count),
            "visual_failure": "no_layout_objects",
            "visual_runtime_limits": runtime_limits,
            **visual_method_stats,
            "visual_phase_ms": {
                "layout_extract_ms": layout_extract_ms,
                "total_ms": int((time.perf_counter() - visual_t0) * 1000),
            },
        }
        return self._build_outcome(result=None, stats=stats, figure_blocks=[])

    def resolve_no_selected_objects(
        self,
        *,
        native_page_count: int,
        object_count: int,
        runtime_limits: Dict[str, Any],
        visual_method_stats: Dict[str, Any],
        object_selection_stats: Dict[str, Any],
        layout_extract_ms: int,
        native_context_ms: int,
        merge_context_ms: int,
        select_ms: int,
        visual_t0: float,
        page_lines: PageLines,
        mineru_run_meta: Dict[str, Any],
    ) -> Dict[str, Any]:
        built = self._build_text_only_result(
            page_lines=page_lines,
            page_count=native_page_count,
            visual_t0=visual_t0,
            layout_extract_ms=layout_extract_ms,
            native_context_ms=native_context_ms,
            merge_context_ms=merge_context_ms,
            select_ms=select_ms,
            failure_reason="no_selected_objects",
            layout_object_count=object_count,
            mineru_run_meta=mineru_run_meta,
            object_selection_stats=object_selection_stats,
            extra_stats=visual_method_stats,
            runtime_limits=runtime_limits,
        )
        if built is not None:
            markdown, bbox_map, table_blocks, stats = built
            return self._build_outcome(
                result=(markdown, bbox_map, table_blocks),
                stats=stats,
                figure_blocks=[],
            )

        stats = {
            "pipeline": "visual_first",
            "visual_page_count": int(native_page_count),
            "visual_failure": "no_selected_objects",
            "visual_runtime_limits": runtime_limits,
            **visual_method_stats,
            **object_selection_stats,
            "visual_phase_ms": {
                "layout_extract_ms": layout_extract_ms,
                "native_context_ms": native_context_ms,
                "context_merge_ms": merge_context_ms,
                "object_select_ms": select_ms,
                "total_ms": int((time.perf_counter() - visual_t0) * 1000),
            },
        }
        return self._build_outcome(result=None, stats=stats, figure_blocks=[])

    def finalize_parse(
        self,
        *,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        table_blocks: TableBlocks,
        figure_blocks: FigureBlocks,
        native_page_count: int,
        selected_objects: List[Dict[str, Any]],
        objects: List[Dict[str, Any]],
        runtime_limits: Dict[str, Any],
        visual_method_stats: Dict[str, Any],
        selected_table_candidates: int,
        selected_figure_candidates: int,
        object_selection_stats: Dict[str, Any],
        table_source: str,
        figure_source: str,
        vision_jobs: List[Dict[str, Any]],
        vision_job_error_count: int,
        vision_serial_recovery_retry_count: int,
        vision_serial_recovery_success_count: int,
        figure_refine_grants: int,
        layout_extract_ms: int,
        native_context_ms: int,
        merge_context_ms: int,
        select_ms: int,
        table_crop_ms: int,
        table_vision_ms: int,
        figure_crop_ms: int,
        figure_vision_ms: int,
        visual_vision_wall_ms: int,
        visual_t0: float,
        page_lines: PageLines,
        vision_ready: bool,
        vision_candidate_count: int,
        vision_attempted_count: int,
        vision_success_count: int,
        vision_empty_count: int,
        mineru_run_meta: Dict[str, Any],
        vision: Any = None,
    ) -> Dict[str, Any]:
        markdown = "\n".join(parts)
        if not table_blocks and not figure_blocks:
            finalized_empty = self._finalize_no_blocks(
                native_page_count=native_page_count,
                selected_objects=selected_objects,
                objects=objects,
                runtime_limits=runtime_limits,
                visual_method_stats=visual_method_stats,
                selected_table_candidates=selected_table_candidates,
                selected_figure_candidates=selected_figure_candidates,
                object_selection_stats=object_selection_stats,
                vision_jobs=vision_jobs,
                vision_job_error_count=vision_job_error_count,
                vision_serial_recovery_retry_count=vision_serial_recovery_retry_count,
                vision_serial_recovery_success_count=vision_serial_recovery_success_count,
                figure_refine_grants=figure_refine_grants,
                layout_extract_ms=layout_extract_ms,
                native_context_ms=native_context_ms,
                merge_context_ms=merge_context_ms,
                select_ms=select_ms,
                table_crop_ms=table_crop_ms,
                table_vision_ms=table_vision_ms,
                figure_crop_ms=figure_crop_ms,
                figure_vision_ms=figure_vision_ms,
                visual_vision_wall_ms=visual_vision_wall_ms,
                visual_t0=visual_t0,
                page_lines=page_lines,
                vision_ready=vision_ready,
                vision_candidate_count=vision_candidate_count,
                vision_attempted_count=vision_attempted_count,
                vision_success_count=vision_success_count,
                vision_empty_count=vision_empty_count,
                mineru_run_meta=mineru_run_meta,
                vision=vision,
            )
            return self._build_outcome(
                result=(markdown, bbox_map, []),
                stats=dict(finalized_empty.get("stats") or {}),
                figure_blocks=[],
            )

        finalized_success = self._finalize_success(
            native_page_count=native_page_count,
            selected_objects=selected_objects,
            objects=objects,
            runtime_limits=runtime_limits,
            visual_method_stats=visual_method_stats,
            selected_table_candidates=selected_table_candidates,
            selected_figure_candidates=selected_figure_candidates,
            object_selection_stats=object_selection_stats,
            bbox_map=bbox_map,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
            table_source=table_source,
            figure_source=figure_source,
            vision_jobs=vision_jobs,
            vision_job_error_count=vision_job_error_count,
            vision_serial_recovery_retry_count=vision_serial_recovery_retry_count,
            vision_serial_recovery_success_count=vision_serial_recovery_success_count,
            figure_refine_grants=figure_refine_grants,
            layout_extract_ms=layout_extract_ms,
            native_context_ms=native_context_ms,
            merge_context_ms=merge_context_ms,
            select_ms=select_ms,
            table_crop_ms=table_crop_ms,
            table_vision_ms=table_vision_ms,
            figure_crop_ms=figure_crop_ms,
            figure_vision_ms=figure_vision_ms,
            visual_vision_wall_ms=visual_vision_wall_ms,
            visual_t0=visual_t0,
            page_lines=page_lines,
            vision_ready=vision_ready,
            vision_candidate_count=vision_candidate_count,
            vision_attempted_count=vision_attempted_count,
            vision_success_count=vision_success_count,
            vision_empty_count=vision_empty_count,
            mineru_run_meta=mineru_run_meta,
            vision=vision,
        )
        success_table_blocks = list(finalized_success.get("table_blocks") or [])
        success_figure_blocks = list(finalized_success.get("figure_blocks") or [])
        return self._build_outcome(
            result=(markdown, bbox_map, success_table_blocks),
            stats=dict(finalized_success.get("stats") or {}),
            figure_blocks=success_figure_blocks,
        )

    @staticmethod
    def _build_outcome(
        *,
        result: Optional[Tuple[str, Dict[str, List[float]], TableBlocks]],
        stats: Dict[str, Any],
        figure_blocks: FigureBlocks,
    ) -> Dict[str, Any]:
        return {
            "result": result,
            "stats": dict(stats or {}),
            "figure_blocks": list(figure_blocks or []),
        }
