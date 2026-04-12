from __future__ import annotations

from typing import Any, Callable, Dict

from ..pdf.pdf_parse_runtime import PdfParseRuntime
from ..pdf.pdf_visual_parse_runtime import PdfVisualParseRuntime
from ..schema.reference_runtime import ReferenceRuntime
from ..visual.visual_execution_runtime import (
    VisualExecutionRuntime,
    VisualResultMaterializerRuntime,
    VisualVisionJobsRuntime,
)
from ..visual.visual_planning_runtime import VisualJobPlannerRuntime
from ..visual.visual_parse_orchestrator import (
    VisualParseFinalizerRuntime,
    VisualParseOrchestratorRuntime,
    VisualTextOnlyBuilderRuntime,
)


RuntimeCallback = Callable[..., Any]


class ParserVisualExecutionBundleRuntime:
    """Build pure kwargs for parser-owned visual execution and PDF entry runtimes."""

    def build_visual_job_planner_kwargs(
        self,
        *,
        build_visual_object_context: RuntimeCallback,
        get_cropper: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "build_visual_object_context": build_visual_object_context,
            "get_cropper": get_cropper,
        }

    def build_visual_result_materializer_kwargs(
        self,
        *,
        table_cell_cap: int,
        build_table_from_visual_payload: RuntimeCallback,
        table_payload_has_content: RuntimeCallback,
        build_figure_from_visual_payload: RuntimeCallback,
        figure_payload_has_content: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "table_cell_cap": table_cell_cap,
            "build_table_from_visual_payload": build_table_from_visual_payload,
            "table_payload_has_content": table_payload_has_content,
            "build_figure_from_visual_payload": build_figure_from_visual_payload,
            "figure_payload_has_content": figure_payload_has_content,
        }

    def build_visual_execution_kwargs(
        self,
        *,
        default_table_max_per_page: int,
        default_figure_max_per_page: int,
        default_figure_refine_budget: int,
        default_figure_refine_min_score: int,
        plan_visual_vision_jobs: RuntimeCallback,
        run_visual_vision_jobs: RuntimeCallback,
        materialize_visual_results: RuntimeCallback,
        extract_native_tables_with_fitz: RuntimeCallback | None = None,
    ) -> Dict[str, Any]:
        return {
            "default_table_max_per_page": default_table_max_per_page,
            "default_figure_max_per_page": default_figure_max_per_page,
            "default_figure_refine_budget": default_figure_refine_budget,
            "default_figure_refine_min_score": default_figure_refine_min_score,
            "plan_visual_vision_jobs": plan_visual_vision_jobs,
            "run_visual_vision_jobs": run_visual_vision_jobs,
            "materialize_visual_results": materialize_visual_results,
            "extract_native_tables_with_fitz": extract_native_tables_with_fitz,
        }

    def build_visual_parse_finalizer_kwargs(
        self,
        *,
        table_merge_enable: bool,
        visual_vision_concurrency: int,
        default_figure_refine_budget: int,
        build_visual_parse_status_fields: RuntimeCallback,
        merge_same_page_tables: RuntimeCallback,
        merge_cross_page_tables: RuntimeCallback,
        prune_fragment_tables: RuntimeCallback,
        merge_figure_blocks: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "table_merge_enable": table_merge_enable,
            "visual_vision_concurrency": visual_vision_concurrency,
            "default_figure_refine_budget": default_figure_refine_budget,
            "build_visual_parse_status_fields": build_visual_parse_status_fields,
            "merge_same_page_tables": merge_same_page_tables,
            "merge_cross_page_tables": merge_cross_page_tables,
            "prune_fragment_tables": prune_fragment_tables,
            "merge_figure_blocks": merge_figure_blocks,
        }

    def build_visual_text_only_builder_kwargs(
        self,
        *,
        visual_text_only_min_chars: int,
        normalize_text: RuntimeCallback,
        append_ref: RuntimeCallback,
        split_page_text: RuntimeCallback,
        build_visual_parse_status_fields: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "visual_text_only_min_chars": visual_text_only_min_chars,
            "normalize_text": normalize_text,
            "append_ref": append_ref,
            "split_page_text": split_page_text,
            "build_visual_parse_status_fields": build_visual_parse_status_fields,
        }

    def build_visual_parse_orchestrator_kwargs(
        self,
        *,
        build_text_only_result: RuntimeCallback,
        finalize_no_blocks: RuntimeCallback,
        finalize_success: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "build_text_only_result": build_text_only_result,
            "finalize_no_blocks": finalize_no_blocks,
            "finalize_success": finalize_success,
        }

    def build_pdf_visual_parse_kwargs(
        self,
        *,
        bootstrap: RuntimeCallback,
        prepare_context: RuntimeCallback,
        build_initial_refs: RuntimeCallback,
        prioritize_layout_objects: RuntimeCallback,
        execute_visual: RuntimeCallback,
        resolve_no_layout_objects: RuntimeCallback,
        resolve_no_selected_objects: RuntimeCallback,
        finalize_parse: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "bootstrap": bootstrap,
            "prepare_context": prepare_context,
            "build_initial_refs": build_initial_refs,
            "prioritize_layout_objects": prioritize_layout_objects,
            "execute_visual": execute_visual,
            "resolve_no_layout_objects": resolve_no_layout_objects,
            "resolve_no_selected_objects": resolve_no_selected_objects,
            "finalize_parse": finalize_parse,
        }

    def build_pdf_parse_kwargs(
        self,
        *,
        enable_mineru_layout: bool,
        pipeline_mode: str,
        visual_first_allow_legacy_fallback: bool,
        parse_pdf_visual_first: RuntimeCallback,
        visual_backend_available: RuntimeCallback,
        parse_pdf_native: RuntimeCallback,
        get_last_mineru_run_meta: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "enable_mineru_layout": enable_mineru_layout,
            "pipeline_mode": pipeline_mode,
            "visual_first_allow_legacy_fallback": visual_first_allow_legacy_fallback,
            "parse_pdf_visual_first": parse_pdf_visual_first,
            "visual_backend_available": visual_backend_available,
            "parse_pdf_native": parse_pdf_native,
            "get_last_mineru_run_meta": get_last_mineru_run_meta,
        }

    def build_visual_vision_jobs_kwargs(
        self,
        *,
        visual_vision_concurrency: int,
    ) -> Dict[str, Any]:
        return {
            "visual_vision_concurrency": visual_vision_concurrency,
        }


class ParserVisualExecutionBootstrapRuntime:
    """Build visual execution/finalize runtimes so parser.py only coordinates phases."""

    def build_visual_execution_runtime_attrs(
        self,
        *,
        parser_visual_execution_bundle_runtime: Any,
        table_cell_cap: int,
        visual_table_max_per_page: int,
        visual_figure_max_per_page: int,
        visual_figure_refine_budget: int,
        visual_figure_refine_min_score: int,
        visual_vision_concurrency: int,
        visual_text_only_min_chars: int,
        table_merge_enable: bool,
        enable_mineru_layout: bool,
        pipeline_mode: str,
        visual_first_allow_legacy_fallback: bool,
        build_visual_object_context: RuntimeCallback,
        get_cropper: RuntimeCallback,
        build_table_from_visual_payload: RuntimeCallback,
        table_payload_has_content: RuntimeCallback,
        build_figure_from_visual_payload: RuntimeCallback,
        figure_payload_has_content: RuntimeCallback,
        build_visual_parse_status_fields: RuntimeCallback,
        merge_same_page_tables: RuntimeCallback,
        merge_cross_page_tables: RuntimeCallback,
        prune_fragment_tables: RuntimeCallback,
        merge_figure_blocks: RuntimeCallback,
        normalize_text: RuntimeCallback,
        split_page_text: RuntimeCallback,
        bootstrap: RuntimeCallback,
        prepare_context: RuntimeCallback,
        build_initial_refs: RuntimeCallback,
        prioritize_layout_objects: RuntimeCallback,
        extract_native_tables_with_fitz: RuntimeCallback | None,
        parse_pdf_visual_first: RuntimeCallback,
        visual_backend_available: RuntimeCallback,
        parse_pdf_native: RuntimeCallback,
        get_last_mineru_run_meta: RuntimeCallback,
    ) -> Dict[str, Any]:
        visual_vision_jobs_runtime = VisualVisionJobsRuntime(
            **parser_visual_execution_bundle_runtime.build_visual_vision_jobs_kwargs(
                visual_vision_concurrency=visual_vision_concurrency,
            )
        )
        visual_job_planner_runtime = VisualJobPlannerRuntime(
            **parser_visual_execution_bundle_runtime.build_visual_job_planner_kwargs(
                build_visual_object_context=build_visual_object_context,
                get_cropper=get_cropper,
            )
        )
        visual_result_materializer_runtime = VisualResultMaterializerRuntime(
            **parser_visual_execution_bundle_runtime.build_visual_result_materializer_kwargs(
                table_cell_cap=table_cell_cap,
                build_table_from_visual_payload=build_table_from_visual_payload,
                table_payload_has_content=table_payload_has_content,
                build_figure_from_visual_payload=build_figure_from_visual_payload,
                figure_payload_has_content=figure_payload_has_content,
            )
        )
        visual_execution_runtime = VisualExecutionRuntime(
            **parser_visual_execution_bundle_runtime.build_visual_execution_kwargs(
                default_table_max_per_page=visual_table_max_per_page,
                default_figure_max_per_page=visual_figure_max_per_page,
                default_figure_refine_budget=visual_figure_refine_budget,
                default_figure_refine_min_score=visual_figure_refine_min_score,
                plan_visual_vision_jobs=visual_job_planner_runtime.plan_jobs,
                run_visual_vision_jobs=visual_vision_jobs_runtime.run_jobs,
                materialize_visual_results=visual_result_materializer_runtime.materialize,
                extract_native_tables_with_fitz=extract_native_tables_with_fitz,
            )
        )
        visual_parse_finalizer_runtime = VisualParseFinalizerRuntime(
            **parser_visual_execution_bundle_runtime.build_visual_parse_finalizer_kwargs(
                table_merge_enable=table_merge_enable,
                visual_vision_concurrency=visual_vision_concurrency,
                default_figure_refine_budget=visual_figure_refine_budget,
                build_visual_parse_status_fields=build_visual_parse_status_fields,
                merge_same_page_tables=merge_same_page_tables,
                merge_cross_page_tables=merge_cross_page_tables,
                prune_fragment_tables=prune_fragment_tables,
                merge_figure_blocks=merge_figure_blocks,
            )
        )
        visual_text_only_builder_runtime = VisualTextOnlyBuilderRuntime(
            **parser_visual_execution_bundle_runtime.build_visual_text_only_builder_kwargs(
                visual_text_only_min_chars=visual_text_only_min_chars,
                normalize_text=normalize_text,
                append_ref=ReferenceRuntime.append_ref,
                split_page_text=split_page_text,
                build_visual_parse_status_fields=build_visual_parse_status_fields,
            )
        )
        visual_parse_orchestrator_runtime = VisualParseOrchestratorRuntime(
            **parser_visual_execution_bundle_runtime.build_visual_parse_orchestrator_kwargs(
                build_text_only_result=visual_text_only_builder_runtime.build_result,
                finalize_no_blocks=visual_parse_finalizer_runtime.finalize_no_blocks,
                finalize_success=visual_parse_finalizer_runtime.finalize_success,
            )
        )
        pdf_visual_parse_runtime = PdfVisualParseRuntime(
            **parser_visual_execution_bundle_runtime.build_pdf_visual_parse_kwargs(
                bootstrap=bootstrap,
                prepare_context=prepare_context,
                build_initial_refs=build_initial_refs,
                prioritize_layout_objects=prioritize_layout_objects,
                execute_visual=visual_execution_runtime.execute,
                resolve_no_layout_objects=visual_parse_orchestrator_runtime.resolve_no_layout_objects,
                resolve_no_selected_objects=visual_parse_orchestrator_runtime.resolve_no_selected_objects,
                finalize_parse=visual_parse_orchestrator_runtime.finalize_parse,
            )
        )
        pdf_parse_runtime = PdfParseRuntime(
            **parser_visual_execution_bundle_runtime.build_pdf_parse_kwargs(
                enable_mineru_layout=enable_mineru_layout,
                pipeline_mode=pipeline_mode,
                visual_first_allow_legacy_fallback=visual_first_allow_legacy_fallback,
                parse_pdf_visual_first=parse_pdf_visual_first,
                visual_backend_available=visual_backend_available,
                parse_pdf_native=parse_pdf_native,
                get_last_mineru_run_meta=get_last_mineru_run_meta,
            )
        )
        return {
            "_visual_vision_jobs_runtime": visual_vision_jobs_runtime,
            "_visual_job_planner_runtime": visual_job_planner_runtime,
            "_visual_result_materializer_runtime": visual_result_materializer_runtime,
            "_visual_execution_runtime": visual_execution_runtime,
            "_visual_parse_finalizer_runtime": visual_parse_finalizer_runtime,
            "_visual_text_only_builder_runtime": visual_text_only_builder_runtime,
            "_visual_parse_orchestrator_runtime": visual_parse_orchestrator_runtime,
            "_pdf_visual_parse_runtime": pdf_visual_parse_runtime,
            "_pdf_parse_runtime": pdf_parse_runtime,
        }
