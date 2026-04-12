from __future__ import annotations

import concurrent.futures
import time
from typing import Any, Callable, Dict, List, Optional, Tuple


LayoutObject = Dict[str, Any]
PageLines = Dict[int, List[str]]
PlanVisualVisionJobs = Callable[..., Dict[str, Any]]
RunVisualVisionJobs = Callable[..., Dict[int, Dict[str, Any]]]
MaterializeVisualResults = Callable[..., Dict[str, Any]]
VisualVisionJob = Dict[str, Any]
VisualVisionResult = Dict[str, Any]
TableBlocks = List[Dict[str, Any]]
FigureBlocks = List[Dict[str, Any]]
BuildTableFromVisualPayload = Callable[..., Tuple[Optional[Dict[str, Any]], int]]
TablePayloadHasContent = Callable[[Dict[str, Any]], bool]
BuildFigureFromVisualPayload = Callable[..., Optional[Dict[str, Any]]]
FigurePayloadHasContent = Callable[[Dict[str, Any]], bool]
ExtractNativeTablesWithFitz = Callable[..., TableBlocks]


class VisualVisionJobsRuntime:
    """Execute visual ROI vision jobs while keeping parser-facing results stable."""

    def __init__(self, *, visual_vision_concurrency: int) -> None:
        self.visual_vision_concurrency = max(1, int(visual_vision_concurrency or 1))

    def run_jobs(
        self,
        *,
        jobs: List[VisualVisionJob],
        vision: Any,
        vision_ready: bool,
        runtime_vision_concurrency: Optional[int] = None,
    ) -> Dict[int, VisualVisionResult]:
        results: Dict[int, VisualVisionResult] = {}
        if not jobs:
            return results

        requested_concurrency = max(1, int(runtime_vision_concurrency or self.visual_vision_concurrency or 1))
        max_workers = min(len(jobs), requested_concurrency)
        if (not vision_ready) or max_workers <= 1 or len(jobs) <= 1:
            for job in jobs:
                result = self._execute_job(job=job, vision=vision, vision_ready=vision_ready)
                results[self._coerce_index(result.get("index", -1))] = result
            return self._retry_transport_failures(
                jobs=jobs,
                results=results,
                vision=vision,
                vision_ready=vision_ready,
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(
                    self._execute_job,
                    job=job,
                    vision=vision,
                    vision_ready=vision_ready,
                ): job
                for job in jobs
            }
            for future in concurrent.futures.as_completed(future_map):
                job = future_map.get(future) or {}
                job_index = self._coerce_index(job.get("index", -1))
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "index": job_index,
                        "kind": str(job.get("kind", "") or ""),
                        "payload": {},
                        "attempted": bool(vision_ready),
                        "elapsed_ms": 0,
                        "error": f"{type(exc).__name__}: {exc}"[:400],
                    }
                results[self._coerce_index(result.get("index", -1))] = result

        return self._retry_transport_failures(
            jobs=jobs,
            results=results,
            vision=vision,
            vision_ready=vision_ready,
        )

    def _retry_transport_failures(
        self,
        *,
        jobs: List[VisualVisionJob],
        results: Dict[int, VisualVisionResult],
        vision: Any,
        vision_ready: bool,
    ) -> Dict[int, VisualVisionResult]:
        retry_indexes = [
            idx
            for idx, result in results.items()
            if self.is_retryable_transport_error(str(result.get("error", "") or ""))
        ]
        if not retry_indexes:
            return results

        job_by_index = {
            self._coerce_index(job.get("index", -1)): job
            for job in jobs
            if isinstance(job, dict)
        }
        for idx in sorted(retry_indexes):
            job = job_by_index.get(idx)
            if not isinstance(job, dict):
                continue
            retry_result = self._execute_job(job=job, vision=vision, vision_ready=vision_ready)
            retry_result["serial_recovery_retry"] = True
            results[idx] = retry_result
        return results

    def _execute_job(
        self,
        *,
        job: VisualVisionJob,
        vision: Any,
        vision_ready: bool,
    ) -> VisualVisionResult:
        job_index = self._coerce_index(job.get("index", -1))
        kind = str(job.get("kind", "") or "")
        t0 = time.perf_counter()
        attempted = False
        payload: Dict[str, Any] = {}
        error = ""
        if vision_ready:
            attempted = True
            try:
                context = job.get("context") if isinstance(job.get("context"), dict) else {}
                if kind == "table":
                    payload = (
                        vision.extract_table(
                            image_bytes=bytes(job.get("roi_bytes") or b""),
                            mime_type=str(job.get("roi_mime", "") or "image/png"),
                            context=context,
                        )
                        or {}
                    )
                elif kind == "figure":
                    payload = (
                        vision.extract_figure(
                            image_bytes=bytes(job.get("roi_bytes") or b""),
                            mime_type=str(job.get("roi_mime", "") or "image/png"),
                            context=context,
                            allow_refine=bool(job.get("allow_refine", False)),
                        )
                        or {}
                    )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
        return {
            "index": job_index,
            "kind": kind,
            "payload": payload or {},
            "attempted": attempted,
            "elapsed_ms": int((time.perf_counter() - t0) * 1000),
            "error": error[:400],
        }

    @staticmethod
    def is_retryable_transport_error(error_text: str) -> bool:
        raw = str(error_text or "").strip().lower()
        if not raw:
            return False
        retry_markers = (
            "ssleoferror",
            "unexpected eof",
            "eof occurred in violation of protocol",
            "connection aborted",
            "connection reset",
            "remote disconnected",
            "temporarily unavailable",
            "timed out",
            "timeout",
        )
        return any(marker in raw for marker in retry_markers)

    @staticmethod
    def _coerce_index(raw_index: Any) -> int:
        try:
            return int(raw_index)
        except Exception:
            return -1


class VisualResultMaterializerRuntime:
    """Materialize visual vision jobs into table and figure blocks."""

    def __init__(
        self,
        *,
        table_cell_cap: int,
        build_table_from_visual_payload: BuildTableFromVisualPayload,
        table_payload_has_content: TablePayloadHasContent,
        build_figure_from_visual_payload: BuildFigureFromVisualPayload,
        figure_payload_has_content: FigurePayloadHasContent,
    ) -> None:
        self.table_cell_cap = max(1, int(table_cell_cap or 1))
        self._build_table_from_visual_payload = build_table_from_visual_payload
        self._table_payload_has_content = table_payload_has_content
        self._build_figure_from_visual_payload = build_figure_from_visual_payload
        self._figure_payload_has_content = figure_payload_has_content

    def materialize(
        self,
        *,
        vision_jobs: List[VisualVisionJob],
        vision_results: Dict[int, VisualVisionResult],
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        page_dims: Dict[int, Tuple[float, float]],
        runtime_table_max_per_page: int,
        runtime_figure_max_per_page: int,
        table_source: str,
        figure_source: str,
        vision_ready: bool,
    ) -> Dict[str, Any]:
        table_blocks: TableBlocks = []
        figure_blocks: FigureBlocks = []
        table_count_by_page: Dict[int, int] = {}
        figure_count_by_page: Dict[int, int] = {}
        table_idx = 1
        figure_idx = 1
        emitted_cells = 0
        table_vision_ms = 0
        figure_vision_ms = 0
        vision_attempted_count = 0
        vision_success_count = 0
        vision_empty_count = 0
        vision_job_error_count = 0
        vision_serial_recovery_retry_count = 0
        vision_serial_recovery_success_count = 0

        for job in vision_jobs:
            job_index = self._coerce_index(job.get("index", -1))
            result = vision_results.get(job_index) if isinstance(vision_results, dict) else None
            if not isinstance(result, dict):
                result = {
                    "index": job_index,
                    "kind": str(job.get("kind", "") or ""),
                    "payload": {},
                    "attempted": False,
                    "elapsed_ms": 0,
                }

            kind = str(job.get("kind", "") or "")
            page_no = int(job.get("page_no", 0) or 0)
            item = job.get("item") if isinstance(job.get("item"), dict) else {}
            payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
            attempted = bool(result.get("attempted"))
            elapsed_ms = int(result.get("elapsed_ms", 0) or 0)
            recovered_retry = bool(result.get("serial_recovery_retry"))
            if str(result.get("error", "") or "").strip():
                vision_job_error_count += 1
            if recovered_retry:
                vision_serial_recovery_retry_count += 1
            if attempted:
                vision_attempted_count += 1

            if kind == "table":
                table_vision_ms += elapsed_ms
                table_count_by_page[page_no] = table_count_by_page.get(page_no, 0)
                if table_count_by_page[page_no] >= runtime_table_max_per_page:
                    continue
                if emitted_cells >= self.table_cell_cap:
                    break

                table_id = f"pdf_mineru_gemini_t{table_idx}"
                built_table, emitted_cells = self._build_table_from_visual_payload(
                    table_id=table_id,
                    page_no=page_no,
                    payload=payload or {},
                    item=item,
                    parts=parts,
                    bbox_map=bbox_map,
                    page_dims=page_dims,
                    emitted_cells=emitted_cells,
                    source=table_source,
                )
                if built_table is None:
                    continue
                table_payload_has_content = self._table_payload_has_content(payload or {})
                built_table["vision_status"] = (
                    "attempted_success"
                    if vision_ready and table_payload_has_content
                    else "attempted_empty"
                    if vision_ready
                    else "not_needed"
                )
                if attempted:
                    if table_payload_has_content:
                        vision_success_count += 1
                        if recovered_retry:
                            vision_serial_recovery_success_count += 1
                    else:
                        vision_empty_count += 1
                table_blocks.append(built_table)
                table_count_by_page[page_no] = table_count_by_page.get(page_no, 0) + 1
                table_idx += 1
                continue

            if kind == "figure":
                figure_vision_ms += elapsed_ms
                figure_count_by_page[page_no] = figure_count_by_page.get(page_no, 0)
                if figure_count_by_page[page_no] >= runtime_figure_max_per_page:
                    continue
                figure_id = f"pdf_mineru_gemini_f{figure_idx}"
                built_figure = self._build_figure_from_visual_payload(
                    figure_id=figure_id,
                    page_no=page_no,
                    payload=payload or {},
                    item=item,
                    parts=parts,
                    bbox_map=bbox_map,
                    page_dims=page_dims,
                    source=figure_source,
                )
                if built_figure is None:
                    continue
                figure_payload_has_content = self._figure_payload_has_content(payload or {})
                built_figure["vision_status"] = (
                    "attempted_success"
                    if vision_ready and figure_payload_has_content
                    else "attempted_empty"
                    if vision_ready
                    else "not_needed"
                )
                if attempted:
                    if figure_payload_has_content:
                        vision_success_count += 1
                        if recovered_retry:
                            vision_serial_recovery_success_count += 1
                    else:
                        vision_empty_count += 1
                figure_blocks.append(built_figure)
                figure_count_by_page[page_no] = figure_count_by_page.get(page_no, 0) + 1
                figure_idx += 1

        return {
            "table_blocks": table_blocks,
            "figure_blocks": figure_blocks,
            "table_vision_ms": int(table_vision_ms),
            "figure_vision_ms": int(figure_vision_ms),
            "vision_attempted_count": int(vision_attempted_count),
            "vision_success_count": int(vision_success_count),
            "vision_empty_count": int(vision_empty_count),
            "vision_job_error_count": int(vision_job_error_count),
            "vision_serial_recovery_retry_count": int(vision_serial_recovery_retry_count),
            "vision_serial_recovery_success_count": int(vision_serial_recovery_success_count),
        }

    @staticmethod
    def _coerce_index(raw_index: Any) -> int:
        try:
            return int(raw_index)
        except Exception:
            return -1


class VisualExecutionRuntime:
    """Orchestrate visual vision planning, execution, and materialization."""

    def __init__(
        self,
        *,
        default_table_max_per_page: int,
        default_figure_max_per_page: int,
        default_figure_refine_budget: int,
        default_figure_refine_min_score: int,
        plan_visual_vision_jobs: PlanVisualVisionJobs,
        run_visual_vision_jobs: RunVisualVisionJobs,
        materialize_visual_results: MaterializeVisualResults,
        extract_native_tables_with_fitz: Optional[ExtractNativeTablesWithFitz] = None,
    ) -> None:
        self.default_table_max_per_page = int(default_table_max_per_page or 0)
        self.default_figure_max_per_page = int(default_figure_max_per_page or 0)
        self.default_figure_refine_budget = int(default_figure_refine_budget or 0)
        self.default_figure_refine_min_score = int(default_figure_refine_min_score or 0)
        self._plan_visual_vision_jobs = plan_visual_vision_jobs
        self._run_visual_vision_jobs = run_visual_vision_jobs
        self._materialize_visual_results = materialize_visual_results
        self._extract_native_tables_with_fitz = extract_native_tables_with_fitz

    def execute(
        self,
        *,
        selected_objects: List[LayoutObject],
        object_selection_stats: Dict[str, Any],
        file_name: str,
        file_bytes: bytes,
        page_lines: PageLines,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        page_dims: Dict[int, Tuple[float, float]],
        runtime_limits: Dict[str, Any],
        vision: Any,
        vision_ready: bool,
    ) -> Dict[str, Any]:
        visual_table_source = "pdf_mineru_gemini" if vision_ready else "pdf_mineru"
        figure_source = "pdf_mineru_gemini" if vision_ready else "pdf_mineru"
        selected_table_candidates = int(object_selection_stats.get("visual_selected_table_candidates", 0) or 0)
        selected_figure_candidates = int(object_selection_stats.get("visual_selected_figure_candidates", 0) or 0)
        runtime_table_max_per_page = max(
            1,
            int(runtime_limits.get("table_max_per_page", self.default_table_max_per_page) or self.default_table_max_per_page),
        )
        runtime_figure_max_per_page = max(
            0,
            int(
                runtime_limits.get("figure_max_per_page", self.default_figure_max_per_page)
                or self.default_figure_max_per_page
            ),
        )
        figure_refine_budget = max(
            0,
            int(runtime_limits.get("figure_refine_budget", self.default_figure_refine_budget) or self.default_figure_refine_budget),
        )
        figure_refine_min_score = int(
            runtime_limits.get("figure_refine_min_score", self.default_figure_refine_min_score)
            or self.default_figure_refine_min_score
        )
        runtime_vision_concurrency = self._resolve_runtime_vision_concurrency(
            runtime_limits=runtime_limits,
            vision_job_count=max(selected_table_candidates + selected_figure_candidates, 0),
        )
        native_table_prefill = self._prefill_native_tables(
            selected_objects=selected_objects,
            file_bytes=file_bytes,
            parts=parts,
            bbox_map=bbox_map,
            page_dims=page_dims,
            runtime_limits=runtime_limits,
        )
        planned_selected_objects = list(native_table_prefill.get("remaining_selected_objects") or selected_objects)
        native_table_blocks = list(native_table_prefill.get("table_blocks") or [])

        planned_jobs = self._plan_visual_vision_jobs(
            selected_objects=planned_selected_objects,
            file_name=file_name,
            file_bytes=file_bytes,
            page_lines=page_lines,
            runtime_figure_max_per_page=runtime_figure_max_per_page,
            figure_refine_budget=figure_refine_budget,
            figure_refine_min_score=figure_refine_min_score,
        )
        vision_jobs = list(planned_jobs.get("vision_jobs") or [])
        vision_candidate_count = int(planned_jobs.get("vision_candidate_count", 0) or 0)
        table_crop_ms = int(planned_jobs.get("table_crop_ms", 0) or 0)
        figure_crop_ms = int(planned_jobs.get("figure_crop_ms", 0) or 0)
        figure_refine_grants = int(planned_jobs.get("figure_refine_grants", 0) or 0)

        if vision_jobs:
            runtime_vision_concurrency = self._resolve_runtime_vision_concurrency(
                runtime_limits=runtime_limits,
                vision_job_count=len(vision_jobs),
            )
            vision_jobs_t0 = time.perf_counter()
            vision_results = self._run_visual_vision_jobs(
                jobs=vision_jobs,
                vision=vision,
                vision_ready=vision_ready,
                runtime_vision_concurrency=runtime_vision_concurrency,
            )
            visual_vision_wall_ms = int((time.perf_counter() - vision_jobs_t0) * 1000)
        else:
            vision_results = {}
            visual_vision_wall_ms = 0

        materialized_results = self._materialize_visual_results(
            vision_jobs=vision_jobs,
            vision_results=vision_results if isinstance(vision_results, dict) else {},
            parts=parts,
            bbox_map=bbox_map,
            page_dims=page_dims,
            runtime_table_max_per_page=runtime_table_max_per_page,
            runtime_figure_max_per_page=runtime_figure_max_per_page,
            table_source=visual_table_source,
            figure_source=figure_source,
            vision_ready=vision_ready,
        )
        visual_table_blocks = list(materialized_results.get("table_blocks") or [])
        table_blocks = native_table_blocks + visual_table_blocks
        table_source = self._resolve_table_source(
            native_table_blocks=native_table_blocks,
            visual_table_blocks=visual_table_blocks,
            visual_table_source=visual_table_source,
        )
        return {
            "table_source": table_source,
            "figure_source": figure_source,
            "selected_table_candidates": int(selected_table_candidates),
            "selected_figure_candidates": int(selected_figure_candidates),
            "runtime_table_max_per_page": int(runtime_table_max_per_page),
            "runtime_figure_max_per_page": int(runtime_figure_max_per_page),
            "runtime_vision_concurrency": int(runtime_vision_concurrency),
            "figure_refine_budget": int(figure_refine_budget),
            "vision_jobs": vision_jobs,
            "vision_candidate_count": int(vision_candidate_count),
            "table_crop_ms": int(table_crop_ms),
            "figure_crop_ms": int(figure_crop_ms),
            "figure_refine_grants": int(figure_refine_grants),
            "visual_vision_wall_ms": int(visual_vision_wall_ms),
            "table_blocks": table_blocks,
            "figure_blocks": list(materialized_results.get("figure_blocks") or []),
            "table_vision_ms": int(materialized_results.get("table_vision_ms", 0) or 0),
            "figure_vision_ms": int(materialized_results.get("figure_vision_ms", 0) or 0),
            "vision_attempted_count": int(materialized_results.get("vision_attempted_count", 0) or 0),
            "vision_success_count": int(materialized_results.get("vision_success_count", 0) or 0),
            "vision_empty_count": int(materialized_results.get("vision_empty_count", 0) or 0),
            "vision_job_error_count": int(materialized_results.get("vision_job_error_count", 0) or 0),
            "vision_serial_recovery_retry_count": int(
                materialized_results.get("vision_serial_recovery_retry_count", 0) or 0
            ),
            "vision_serial_recovery_success_count": int(
                materialized_results.get("vision_serial_recovery_success_count", 0) or 0
            ),
            "native_table_prefill_count": int(native_table_prefill.get("table_count", 0) or 0),
            "native_table_prefill_page_count": int(native_table_prefill.get("page_count", 0) or 0),
            "native_table_prefill_elapsed_ms": int(native_table_prefill.get("elapsed_ms", 0) or 0),
            "native_table_prefill_skipped_visual_count": int(
                native_table_prefill.get("skipped_visual_count", 0) or 0
            ),
        }

    def _prefill_native_tables(
        self,
        *,
        selected_objects: List[LayoutObject],
        file_bytes: bytes,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        page_dims: Dict[int, Tuple[float, float]],
        runtime_limits: Dict[str, Any],
    ) -> Dict[str, Any]:
        empty = {
            "table_blocks": [],
            "remaining_selected_objects": list(selected_objects or []),
            "table_count": 0,
            "page_count": 0,
            "elapsed_ms": 0,
            "skipped_visual_count": 0,
        }
        if self._extract_native_tables_with_fitz is None:
            return empty
        if not self._should_prefill_native_tables(
            selected_objects=selected_objects,
            runtime_limits=runtime_limits,
        ):
            return empty

        selected_table_counts = self._count_selected_tables_by_page(selected_objects)
        if not selected_table_counts:
            return empty

        page_count = self._resolve_page_count(runtime_limits=runtime_limits, page_dims=page_dims)
        if page_count <= 0:
            return empty

        prefill_t0 = time.perf_counter()
        try:
            native_table_blocks = list(
                self._extract_native_tables_with_fitz(
                    file_bytes=file_bytes,
                    page_count=page_count,
                    parts=parts,
                    bbox_map=bbox_map,
                )
                or []
            )
        except Exception:
            return empty
        elapsed_ms = int((time.perf_counter() - prefill_t0) * 1000)
        if not native_table_blocks:
            empty["elapsed_ms"] = elapsed_ms
            return empty

        native_table_counts = self._count_table_blocks_by_page(native_table_blocks)
        accepted_pages = {
            page_no
            for page_no, selected_count in selected_table_counts.items()
            if selected_count > 0 and native_table_counts.get(page_no, 0) >= selected_count
        }
        if not accepted_pages:
            empty["elapsed_ms"] = elapsed_ms
            return empty

        accepted_native_tables: TableBlocks = []
        accepted_native_pages = set()
        for table in native_table_blocks:
            covered_pages = set(self._covered_pages(table))
            if covered_pages and covered_pages.issubset(accepted_pages):
                accepted_native_tables.append(table)
                accepted_native_pages.update(covered_pages)
        if not accepted_native_tables or not accepted_native_pages:
            empty["elapsed_ms"] = elapsed_ms
            return empty
        accepted_native_tables = self._attach_selected_table_artifacts(
            table_blocks=accepted_native_tables,
            selected_objects=selected_objects,
            page_dims=page_dims,
        )

        remaining_selected_objects: List[LayoutObject] = []
        skipped_visual_count = 0
        for item in selected_objects:
            if (
                str(item.get("object_type", "") or "") == "table"
                and int(item.get("page", 0) or 0) in accepted_native_pages
            ):
                skipped_visual_count += 1
                continue
            remaining_selected_objects.append(item)

        return {
            "table_blocks": accepted_native_tables,
            "remaining_selected_objects": remaining_selected_objects,
            "table_count": len(accepted_native_tables),
            "page_count": len(accepted_native_pages),
            "elapsed_ms": elapsed_ms,
            "skipped_visual_count": skipped_visual_count,
        }

    def _attach_selected_table_artifacts(
        self,
        *,
        table_blocks: TableBlocks,
        selected_objects: List[LayoutObject],
        page_dims: Dict[int, Tuple[float, float]],
    ) -> TableBlocks:
        if not table_blocks or not selected_objects:
            return list(table_blocks or [])

        candidates: List[Dict[str, Any]] = []
        for item_index, item in enumerate(selected_objects or []):
            if str(item.get("object_type", "") or "") != "table":
                continue
            page_no = int(item.get("page", 0) or 0)
            if page_no <= 0:
                continue
            image_path = str(item.get("img_path", "") or "").strip()
            if not image_path:
                continue
            bbox_norm = self._normalize_selected_table_bbox(item=item, page_dims=page_dims)
            if bbox_norm is None:
                continue
            candidates.append(
                {
                    "item_index": item_index,
                    "page_no": page_no,
                    "bbox_norm": bbox_norm,
                    "item": item,
                }
            )

        if not candidates:
            return [dict(table) for table in table_blocks]

        used_candidate_indexes: set[int] = set()
        enriched_tables: TableBlocks = []
        for table in table_blocks:
            copied = dict(table)
            if str(copied.get("image_path", "") or "").strip():
                enriched_tables.append(copied)
                continue

            table_bbox_norm = self._extract_table_bbox_norm(copied)
            covered_pages = set(self._covered_pages(copied))
            if table_bbox_norm is None or not covered_pages:
                enriched_tables.append(copied)
                continue

            best_candidate: Dict[str, Any] | None = None
            best_score = 0.0
            for candidate in candidates:
                candidate_index = int(candidate.get("item_index", -1) or -1)
                if candidate_index in used_candidate_indexes:
                    continue
                if int(candidate.get("page_no", 0) or 0) not in covered_pages:
                    continue
                score = self._bbox_overlap_score(
                    table_bbox_norm,
                    candidate.get("bbox_norm"),
                )
                if score > best_score:
                    best_candidate = candidate
                    best_score = score

            if best_candidate is None or best_score < 0.45:
                enriched_tables.append(copied)
                continue

            selected_item = best_candidate.get("item") if isinstance(best_candidate.get("item"), dict) else {}
            image_path = str(selected_item.get("img_path", "") or "").strip()
            if image_path:
                copied["image_path"] = image_path
            copied.setdefault(
                "artifact_subtype",
                str(
                    selected_item.get("object_subtype", "")
                    or selected_item.get("source_object_type", "")
                    or "table"
                ),
            )
            copied.setdefault(
                "source_object_type",
                str(selected_item.get("source_object_type", "") or selected_item.get("object_type", "") or "table"),
            )
            if not str(copied.get("caption", "") or "").strip():
                caption_values = selected_item.get("caption")
                if isinstance(caption_values, list):
                    caption_text = " ".join(str(value).strip() for value in caption_values if str(value).strip())
                    if caption_text:
                        copied["caption"] = caption_text[:240]
            if not copied.get("notes"):
                footnotes = selected_item.get("footnote")
                if isinstance(footnotes, list):
                    copied["notes"] = [
                        str(value).strip()[:180]
                        for value in footnotes
                        if str(value).strip()
                    ][:4]

            used_candidate_indexes.add(int(best_candidate.get("item_index", -1) or -1))
            enriched_tables.append(copied)

        return enriched_tables

    @staticmethod
    def _count_selected_tables_by_page(selected_objects: List[LayoutObject]) -> Dict[int, int]:
        counts: Dict[int, int] = {}
        for item in selected_objects or []:
            if str(item.get("object_type", "") or "") != "table":
                continue
            page_no = int(item.get("page", 0) or 0)
            if page_no <= 0:
                continue
            counts[page_no] = counts.get(page_no, 0) + 1
        return counts

    def _should_prefill_native_tables(
        self,
        *,
        selected_objects: List[LayoutObject],
        runtime_limits: Dict[str, Any],
    ) -> bool:
        selected_table_count = sum(
            1 for item in selected_objects or [] if str(item.get("object_type", "") or "") == "table"
        )
        if selected_table_count <= 0:
            return False
        visual_pdf_profile = str(runtime_limits.get("visual_pdf_profile", "") or "").strip().lower()
        runtime_profile = str(runtime_limits.get("profile", "") or "").strip().lower()
        probe_chars = int(runtime_limits.get("visual_probe_chars", 0) or 0)
        page_count = int(runtime_limits.get("page_count", 0) or 0)
        office_like = bool(runtime_limits.get("visual_pdf_office_like"))
        if visual_pdf_profile == "office_text_pdf":
            return runtime_profile in {"large_visual_doc", "extreme_visual_doc", "docx_chart_heavy"}
        if runtime_profile not in {"large_visual_doc", "extreme_visual_doc", "docx_chart_heavy"}:
            return False
        if visual_pdf_profile in {"mixed_text_pref_pdf", "mixed_visual_pdf"}:
            return office_like or probe_chars > 0 or selected_table_count >= 3
        if visual_pdf_profile == "visual_scanned_pdf":
            if runtime_profile != "extreme_visual_doc" and selected_table_count < 3:
                return False
            return page_count <= 180 or page_count <= 0
        return False

    def _resolve_runtime_vision_concurrency(
        self,
        *,
        runtime_limits: Dict[str, Any],
        vision_job_count: int,
    ) -> int:
        base_concurrency = self._base_vision_concurrency()
        if vision_job_count <= 1:
            return min(max(base_concurrency, 1), max(1, vision_job_count or 1))

        runtime_profile = str(runtime_limits.get("profile", "") or "").strip().lower()
        visual_pdf_profile = str(runtime_limits.get("visual_pdf_profile", "") or "").strip().lower()
        page_count = int(runtime_limits.get("page_count", 0) or 0)
        image_object_count = int(runtime_limits.get("image_object_count", 0) or 0)
        table_object_count = int(runtime_limits.get("table_object_count", 0) or 0)

        resolved = base_concurrency
        if vision_job_count >= max(6, base_concurrency * 3):
            resolved = max(resolved, min(4, base_concurrency + 1))

        dense_scanned_doc = visual_pdf_profile == "visual_scanned_pdf" and (
            vision_job_count >= 6 or image_object_count >= 12 or page_count >= 40
        )
        if runtime_profile == "extreme_visual_doc" or (dense_scanned_doc and vision_job_count >= 10):
            resolved = max(resolved, min(4, base_concurrency + 2))
        elif runtime_profile in {"large_visual_doc", "docx_chart_heavy"} or dense_scanned_doc:
            resolved = max(resolved, min(4, base_concurrency + 1))

        if table_object_count >= 6 and vision_job_count >= 8:
            resolved = max(resolved, min(4, base_concurrency + 1))
        return min(max(resolved, 1), max(1, vision_job_count))

    def _base_vision_concurrency(self) -> int:
        runner_owner = getattr(self._run_visual_vision_jobs, "__self__", None)
        try:
            return max(1, int(getattr(runner_owner, "visual_vision_concurrency", 1) or 1))
        except Exception:
            return 1

    @staticmethod
    def _resolve_page_count(
        *,
        runtime_limits: Dict[str, Any],
        page_dims: Dict[int, Tuple[float, float]],
    ) -> int:
        try:
            page_count = int(runtime_limits.get("page_count", 0) or 0)
        except Exception:
            page_count = 0
        if page_count > 0:
            return page_count
        if not page_dims:
            return 0
        return max(int(page_no) for page_no in page_dims.keys())

    def _count_table_blocks_by_page(self, table_blocks: TableBlocks) -> Dict[int, int]:
        counts: Dict[int, int] = {}
        for table in table_blocks or []:
            for page_no in self._covered_pages(table):
                counts[page_no] = counts.get(page_no, 0) + 1
        return counts

    @staticmethod
    def _covered_pages(table_block: Dict[str, Any]) -> List[int]:
        page_span = table_block.get("page_span")
        if isinstance(page_span, list) and len(page_span) >= 2:
            try:
                start = int(page_span[0] or 0)
                end = int(page_span[1] or 0)
            except Exception:
                start = 0
                end = 0
            if start > 0 and end >= start:
                return list(range(start, end + 1))
        try:
            page_no = int(table_block.get("page", 0) or 0)
        except Exception:
            page_no = 0
        return [page_no] if page_no > 0 else []

    @staticmethod
    def _extract_table_bbox_norm(table_block: Dict[str, Any]) -> Optional[List[float]]:
        bbox_norm = table_block.get("bbox_norm")
        if isinstance(bbox_norm, list) and len(bbox_norm) >= 4:
            try:
                return [
                    float(bbox_norm[0]),
                    float(bbox_norm[1]),
                    float(bbox_norm[2]),
                    float(bbox_norm[3]),
                ]
            except Exception:
                return None

        bbox = table_block.get("bbox")
        if isinstance(bbox, list) and len(bbox) >= 5:
            try:
                return [
                    float(bbox[1]),
                    float(bbox[2]),
                    float(bbox[3]),
                    float(bbox[4]),
                ]
            except Exception:
                return None
        return None

    @staticmethod
    def _normalize_selected_table_bbox(
        *,
        item: Dict[str, Any],
        page_dims: Dict[int, Tuple[float, float]],
    ) -> Optional[List[float]]:
        raw_bbox = item.get("bbox")
        if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) < 4:
            return None
        try:
            x1, y1, x2, y2 = [float(raw_bbox[idx]) for idx in range(4)]
        except Exception:
            return None

        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1

        if max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 1.5:
            width = 1.0
            height = 1.0
        else:
            page_no = int(item.get("page", 0) or 0)
            width, height = page_dims.get(page_no, (1.0, 1.0))
            width = max(float(width or 1.0), 1.0)
            height = max(float(height or 1.0), 1.0)
            x1 /= width
            x2 /= width
            y1 /= height
            y2 /= height

        x1 = max(0.0, min(1.0, x1))
        x2 = max(0.0, min(1.0, x2))
        y1 = max(0.0, min(1.0, y1))
        y2 = max(0.0, min(1.0, y2))
        if x2 <= x1 or y2 <= y1:
            return None
        return [x1, y1, x2 - x1, y2 - y1]

    @staticmethod
    def _bbox_overlap_score(left: Any, right: Any) -> float:
        if not isinstance(left, list) or not isinstance(right, list) or len(left) < 4 or len(right) < 4:
            return 0.0
        try:
            lx, ly, lw, lh = [float(left[idx]) for idx in range(4)]
            rx, ry, rw, rh = [float(right[idx]) for idx in range(4)]
        except Exception:
            return 0.0

        if lw <= 0 or lh <= 0 or rw <= 0 or rh <= 0:
            return 0.0

        left_x2 = lx + lw
        left_y2 = ly + lh
        right_x2 = rx + rw
        right_y2 = ry + rh

        inter_w = max(0.0, min(left_x2, right_x2) - max(lx, rx))
        inter_h = max(0.0, min(left_y2, right_y2) - max(ly, ry))
        if inter_w <= 0 or inter_h <= 0:
            return 0.0

        intersection = inter_w * inter_h
        left_area = lw * lh
        right_area = rw * rh
        smaller_area = min(left_area, right_area)
        if smaller_area <= 0:
            return 0.0
        return intersection / smaller_area

    @staticmethod
    def _resolve_table_source(
        *,
        native_table_blocks: TableBlocks,
        visual_table_blocks: TableBlocks,
        visual_table_source: str,
    ) -> str:
        if native_table_blocks and visual_table_blocks:
            return f"pdf_fitz+{visual_table_source}"
        if native_table_blocks:
            return "pdf_fitz"
        return visual_table_source
