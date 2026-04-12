from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple


Bootstrap = Callable[..., Dict[str, Any]]
PrepareContext = Callable[..., Dict[str, Any]]
BuildInitialRefs = Callable[..., Dict[str, Any]]
PrioritizeLayoutObjects = Callable[..., Tuple[List[Dict[str, Any]], Dict[str, Any]]]
ExecuteVisual = Callable[..., Dict[str, Any]]
ResolveNoLayoutObjects = Callable[..., Dict[str, Any]]
ResolveNoSelectedObjects = Callable[..., Dict[str, Any]]
FinalizeParse = Callable[..., Dict[str, Any]]


class PdfVisualParseRuntime:
    """Coordinate the visual-first PDF parse entry using existing focused runtimes."""

    def __init__(
        self,
        *,
        bootstrap: Bootstrap,
        prepare_context: PrepareContext,
        build_initial_refs: BuildInitialRefs,
        prioritize_layout_objects: PrioritizeLayoutObjects,
        execute_visual: ExecuteVisual,
        resolve_no_layout_objects: ResolveNoLayoutObjects,
        resolve_no_selected_objects: ResolveNoSelectedObjects,
        finalize_parse: FinalizeParse,
    ) -> None:
        self._bootstrap = bootstrap
        self._prepare_context = prepare_context
        self._build_initial_refs = build_initial_refs
        self._prioritize_layout_objects = prioritize_layout_objects
        self._execute_visual = execute_visual
        self._resolve_no_layout_objects = resolve_no_layout_objects
        self._resolve_no_selected_objects = resolve_no_selected_objects
        self._finalize_parse = finalize_parse

    def parse_pdf_visual_first(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        reader: Any,
        page_count: int,
        layout_extractor: Any,
        vision: Any,
        source_cache_identity: str = "",
        source_file_name: Optional[str] = None,
        source_file_bytes: Optional[bytes] = None,
    ) -> Optional[Dict[str, Any]]:
        if page_count <= 0:
            return None
        visual_t0 = time.perf_counter()

        vision_ready = bool(getattr(vision, "ready", False))
        if vision_ready:
            try:
                vision.reset_stats()
            except Exception:
                pass

        bootstrap = self._bootstrap(
            file_name=file_name,
            file_bytes=file_bytes,
            reader=reader,
            page_count=page_count,
            layout_extractor=layout_extractor,
            source_cache_identity=source_cache_identity,
            source_file_name=source_file_name,
            source_file_bytes=source_file_bytes,
        )
        native_page_count = int(bootstrap.get("native_page_count", 1) or 1)
        objects = list(bootstrap.get("objects") or [])
        mineru_page_lines = dict(bootstrap.get("mineru_page_lines") or {})
        layout_extract_ms = int(bootstrap.get("layout_extract_ms", 0) or 0)
        mineru_run_meta = dict(bootstrap.get("mineru_run_meta") or {})
        mineru_status = str(bootstrap.get("mineru_status", "") or "").strip().lower()
        runtime_limits = dict(bootstrap.get("runtime_limits") or {})
        visual_method_stats = dict(bootstrap.get("visual_method_stats") or {})

        prepared_context = self._prepare_context(
            reader=reader,
            page_count=native_page_count,
            mineru_page_lines=mineru_page_lines,
        )
        native_page_chunks = dict(prepared_context.get("native_page_chunks") or {})
        page_lines = dict(prepared_context.get("page_lines") or {})
        native_context_ms = int(prepared_context.get("native_context_ms", 0) or 0)
        merge_context_ms = int(prepared_context.get("merge_context_ms", 0) or 0)

        if not objects:
            return {
                "outcome": self._resolve_no_layout_objects(
                    native_page_count=native_page_count,
                    mineru_status=mineru_status,
                    runtime_limits=runtime_limits,
                    visual_method_stats=visual_method_stats,
                    layout_extract_ms=layout_extract_ms,
                    native_context_ms=native_context_ms,
                    merge_context_ms=merge_context_ms,
                    visual_t0=visual_t0,
                    page_lines=page_lines,
                    mineru_run_meta=mineru_run_meta,
                ),
                "mineru_run_meta": mineru_run_meta,
            }

        initial_refs = self._build_initial_refs(
            reader=reader,
            page_count=native_page_count,
            native_page_chunks=native_page_chunks,
        )
        parts = list(initial_refs.get("parts") or [])
        bbox_map = dict(initial_refs.get("bbox_map") or {})
        page_dims = dict(initial_refs.get("page_dims") or {})

        select_t0 = time.perf_counter()
        selected_objects, object_selection_stats = self._prioritize_layout_objects(
            objects,
            file_name=file_name,
            page_count=native_page_count,
            page_lines=page_lines,
            runtime_limits=runtime_limits,
        )
        select_ms = int((time.perf_counter() - select_t0) * 1000)
        if not selected_objects:
            return {
                "outcome": self._resolve_no_selected_objects(
                    native_page_count=native_page_count,
                    object_count=len(objects),
                    runtime_limits=runtime_limits,
                    visual_method_stats=visual_method_stats,
                    object_selection_stats=object_selection_stats,
                    layout_extract_ms=layout_extract_ms,
                    native_context_ms=native_context_ms,
                    merge_context_ms=merge_context_ms,
                    select_ms=select_ms,
                    visual_t0=visual_t0,
                    page_lines=page_lines,
                    mineru_run_meta=mineru_run_meta,
                ),
                "mineru_run_meta": mineru_run_meta,
            }

        visual_execution = self._execute_visual(
            selected_objects=selected_objects,
            object_selection_stats=object_selection_stats,
            file_name=file_name,
            file_bytes=file_bytes,
            page_lines=page_lines,
            parts=parts,
            bbox_map=bbox_map,
            page_dims=page_dims,
            runtime_limits=runtime_limits,
            vision=vision,
            vision_ready=vision_ready,
        )

        return {
            "outcome": self._finalize_parse(
                parts=parts,
                bbox_map=bbox_map,
                table_blocks=list(visual_execution.get("table_blocks") or []),
                figure_blocks=list(visual_execution.get("figure_blocks") or []),
                native_page_count=native_page_count,
                selected_objects=selected_objects,
                objects=objects,
                runtime_limits=runtime_limits,
                visual_method_stats=visual_method_stats,
                selected_table_candidates=int(visual_execution.get("selected_table_candidates", 0) or 0),
                selected_figure_candidates=int(visual_execution.get("selected_figure_candidates", 0) or 0),
                object_selection_stats=object_selection_stats,
                table_source=str(visual_execution.get("table_source") or "pdf_mineru"),
                figure_source=str(visual_execution.get("figure_source") or "pdf_mineru"),
                vision_jobs=list(visual_execution.get("vision_jobs") or []),
                vision_job_error_count=int(visual_execution.get("vision_job_error_count", 0) or 0),
                vision_serial_recovery_retry_count=int(
                    visual_execution.get("vision_serial_recovery_retry_count", 0) or 0
                ),
                vision_serial_recovery_success_count=int(
                    visual_execution.get("vision_serial_recovery_success_count", 0) or 0
                ),
                figure_refine_grants=int(visual_execution.get("figure_refine_grants", 0) or 0),
                layout_extract_ms=layout_extract_ms,
                native_context_ms=native_context_ms,
                merge_context_ms=merge_context_ms,
                select_ms=select_ms,
                table_crop_ms=int(visual_execution.get("table_crop_ms", 0) or 0),
                table_vision_ms=int(visual_execution.get("table_vision_ms", 0) or 0),
                figure_crop_ms=int(visual_execution.get("figure_crop_ms", 0) or 0),
                figure_vision_ms=int(visual_execution.get("figure_vision_ms", 0) or 0),
                visual_vision_wall_ms=int(visual_execution.get("visual_vision_wall_ms", 0) or 0),
                visual_t0=visual_t0,
                page_lines=page_lines,
                vision_ready=vision_ready,
                vision_candidate_count=int(visual_execution.get("vision_candidate_count", 0) or 0),
                vision_attempted_count=int(visual_execution.get("vision_attempted_count", 0) or 0),
                vision_success_count=int(visual_execution.get("vision_success_count", 0) or 0),
                vision_empty_count=int(visual_execution.get("vision_empty_count", 0) or 0),
                mineru_run_meta=mineru_run_meta,
                vision=vision,
            ),
            "mineru_run_meta": mineru_run_meta,
        }
