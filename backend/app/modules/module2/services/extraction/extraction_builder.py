from __future__ import annotations

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Tuple

from ...core.pipeline.stream_router_runtime import StreamRouterRuntime


_EXTRACTION_RUNTIME_FINGERPRINT_FILES: Tuple[str, ...] = (
    "app/main.py",
    "app/services/extraction/extraction_builder.py",
    "app/agent/graph.py",
    "app/assets/field_naming_rules_v1.json",
    "app/assets/schema_coverage_profiles_v1.json",
    "app/assets/schema_noise_rules_v1.json",
    "app/assets/schema_selection_rules_v1.json",
    "app/assets/schema_semantic_rules_v1.json",
    "app/core/parsers/native_document_parser.py",
    "app/core/format/plain_text_parser.py",
    "app/core/format/xlsx_artifact_io.py",
    "app/core/integration/cached_extraction_restore_runtime.py",
    "app/core/parsers/parser_document_table_bootstrap_runtime.py",
    "app/core/pdf/pdf_fitz_table_runtime.py",
    "app/core/schema/field_naming.py",
    "app/core/schema/schema_rule_assets.py",
    "app/core/table/ocr_table_utils.py",
    "app/core/table/ocr_table_inference.py",
    "app/core/table/table_header_runtime.py",
    "app/core/table/table_merge_runtime.py",
    "app/core/visual/figure_inference.py",
    "app/core/visual/figure_vision_payload.py",
    "app/core/table/table_metadata.py",
    "app/core/visual/vision_extractor.py",
    "app/core/format/nonpdf_budget_runtime.py",
    "app/core/format/word_input_preparation_runtime.py",
    "app/core/pipeline/document_flow_runtime.py",
    "app/core/pipeline/document_pipeline_runtime.py",
    "app/core/pipeline/document_postprocess_runtime.py",
    "app/core/pipeline/document_parse_recovery_runtime.py",
    "app/core/format/docx_native_recovery_runtime.py",
    "app/core/pipeline/extraction_graph_runtime.py",
    "app/core/schema/schema_session_runtime.py",
    "app/services/extraction/document_io_builder.py",
    "app/services/extraction/geometry_builder.py",
    "app/services/extraction/nonpdf_builder.py",
    "app/services/extraction/platform_builder.py",
    "app/services/extraction/policy_builder.py",
    "app/services/extraction/progress_builder.py",
    "app/services/extraction/quality_builder.py",
    "app/services/extraction/quick_extract_builder.py",
    "app/services/extraction/service_builder.py",
    "app/services/extraction/support_builder.py",
    "app/services/schema/schema_pipeline_builder.py",
    "app/services/schema/result_filter_builder.py",
    "app/services/schema/schema_context_builder.py",
    "app/services/schema/schema_fields_builder.py",
    "app/services/schema/schema_inference_builder.py",
    "app/services/schema/schema_llm_builder.py",
    "app/services/schema/schema_primitives_builder.py",
    "app/services/schema/schema_resolution_builder.py",
    "app/services/schema/schema_selection_builder.py",
    "app/services/schema/schema_semantics_builder.py",
    "app/runtime/xlsx_workbook_artifact_runtime.py",
)


BoundedEnvIntFn = Callable[..., int]
GetEnvFn = Callable[[str, str | None], str | None]


@dataclass(frozen=True)
class Module2MainExtractionBundle:
    extraction_cache_version: str
    runtime_code_fingerprint: str
    extraction_word_pdf_semaphore: asyncio.Semaphore
    extraction_parse_semaphore: asyncio.Semaphore
    extraction_visual_parse_semaphore: asyncio.Semaphore
    extraction_llm_semaphore: asyncio.Semaphore
    current_extraction_logic_components: Callable[[], Dict[str, Any]]
    current_extraction_logic_version: Callable[[], str]
    current_extraction_cache_version: Callable[[], str]
    build_stream_router: Callable[[], StreamRouterRuntime]
    acquire_parse_execution_slots: Callable[[Any], Any]


def _compute_extraction_runtime_code_fingerprint(
    *,
    module2_root: Path,
    fingerprint_files: Tuple[str, ...],
) -> str:
    digest = hashlib.sha256()
    for relative_path in fingerprint_files:
        normalized = str(relative_path or "").replace("\\", "/").strip()
        digest.update(normalized.encode("utf-8"))
        file_path = module2_root / normalized
        try:
            payload = file_path.read_bytes()
        except Exception as exc:
            digest.update(f"missing:{type(exc).__name__}".encode("utf-8"))
            continue
        digest.update(hashlib.sha256(payload).digest())
    return digest.hexdigest()[:20]


def build_module2_main_extraction_bundle(
    *,
    module2_root: Path,
    check_cache,
    find_recent_document_caches,
    graph: Any,
    getenv: GetEnvFn,
    bounded_env_int: BoundedEnvIntFn,
    schema_target_fields,
    field_naming_version: str,
    schema_rule_versions: Dict[str, Any],
    auto_schema_logic_revision: str,
    fingerprint_files: Tuple[str, ...] | None = None,
) -> Module2MainExtractionBundle:
    extraction_cache_version = (
        str(getenv("MODULE2_EXTRACTION_CACHE_VERSION", "20260318-strict-visual-chain-v1")).strip()
        or "20260318-strict-visual-chain-v1"
    )
    runtime_code_fingerprint = _compute_extraction_runtime_code_fingerprint(
        module2_root=module2_root,
        fingerprint_files=fingerprint_files or _EXTRACTION_RUNTIME_FINGERPRINT_FILES,
    )

    extraction_word_pdf_semaphore = asyncio.Semaphore(
        bounded_env_int("MODULE2_WORD_PDF_CONCURRENCY", 1, maximum=3)
    )
    extraction_parse_semaphore = asyncio.Semaphore(
        bounded_env_int("MODULE2_PARSE_CONCURRENCY", 2, maximum=6)
    )
    extraction_visual_parse_semaphore = asyncio.Semaphore(
        bounded_env_int("MODULE2_VISION_CONCURRENCY", 2, maximum=6)
    )
    extraction_llm_semaphore = asyncio.Semaphore(
        bounded_env_int("MODULE2_LLM_EXTRACT_CONCURRENCY", 2, maximum=6)
    )

    def _current_extraction_logic_components() -> Dict[str, Any]:
        graph_diagnostics: Dict[str, Any] = {}
        try:
            graph_diagnostics = dict(graph.diagnostics() or {})
        except Exception:
            graph_diagnostics = {}
        return {
            "cache_version": extraction_cache_version,
            "auto_schema_logic_revision": auto_schema_logic_revision,
            "prompt_version": str(graph_diagnostics.get("prompt_version") or ""),
            "prompt_versions": dict(graph_diagnostics.get("prompt_versions") or {}),
            "schema_rule_versions": dict(schema_rule_versions),
            "field_naming_version": field_naming_version,
            "runtime_code_fingerprint": runtime_code_fingerprint,
        }

    def _current_extraction_logic_version() -> str:
        payload = json.dumps(
            _current_extraction_logic_components(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]

    def _current_extraction_cache_version() -> str:
        return f"{extraction_cache_version}:{_current_extraction_logic_version()}"

    def _build_stream_router() -> StreamRouterRuntime:
        return StreamRouterRuntime(
            check_cache=check_cache,
            find_recent_document_caches=find_recent_document_caches,
            current_extraction_cache_version=_current_extraction_cache_version,
            current_extraction_logic_components=_current_extraction_logic_components,
            current_extraction_logic_version=_current_extraction_logic_version,
            schema_target_fields=schema_target_fields,
            getenv=getenv,
        )

    def _parse_track_uses_visual_budget(track: Any) -> bool:
        normalized = str(track or "").strip().lower()
        return "visualtrack" in normalized or "gemini_vision" in normalized or "mineru" in normalized

    @asynccontextmanager
    async def _acquire_parse_execution_slots(track: Any):
        async with extraction_parse_semaphore:
            if _parse_track_uses_visual_budget(track):
                async with extraction_visual_parse_semaphore:
                    yield
                return
            yield

    return Module2MainExtractionBundle(
        extraction_cache_version=extraction_cache_version,
        runtime_code_fingerprint=runtime_code_fingerprint,
        extraction_word_pdf_semaphore=extraction_word_pdf_semaphore,
        extraction_parse_semaphore=extraction_parse_semaphore,
        extraction_visual_parse_semaphore=extraction_visual_parse_semaphore,
        extraction_llm_semaphore=extraction_llm_semaphore,
        current_extraction_logic_components=_current_extraction_logic_components,
        current_extraction_logic_version=_current_extraction_logic_version,
        current_extraction_cache_version=_current_extraction_cache_version,
        build_stream_router=_build_stream_router,
        acquire_parse_execution_slots=_acquire_parse_execution_slots,
    )
