from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from pypdf import PdfReader

MODULE2_ROOT = Path(__file__).resolve().parents[2]
CUSTOM_MODULE2_ENV_FILE = str(os.getenv("MODULE2_ENV_FILE", "") or "").strip()
load_dotenv(dotenv_path=MODULE2_ROOT / ".env", override=False)
if CUSTOM_MODULE2_ENV_FILE:
    load_dotenv(dotenv_path=CUSTOM_MODULE2_ENV_FILE, override=True)

from ...integrations.llm.provider import resolve_llm_api_key
from ..format.plain_text_parser import (
    normalize_text as plain_normalize_text,
    parse_plain_payload,
    split_page_text as plain_split_page_text,
)
from ..pdf.ocr_engine_runtime import OcrEngineRuntime
from ..pipeline.document_process_pool_runtime import parse_document_in_subprocess_runtime
from ..table.table_metadata import build_header_meta, decorate_rows_with_meta, normalize_token_for_compare
from .parser_bootstrap_runtime import ParserBootstrapRuntime, ParserDependencyBundleRuntime
from .parser_initialization_runtime import ParserInitializationRuntime
from .parser_state_runtime import ParserRunStateRuntime, ParserStateRuntime


TableBlocks = List[Dict[str, Any]]
FigureBlocks = List[Dict[str, Any]]
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json", ".xml", ".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


def _limit_env_value(name: str, default: int, *, minimum: int = 0, unlimited_value: Optional[int] = None) -> int:
    raw = str(os.getenv(name, str(default)) or str(default)).strip()
    try:
        value = int(raw)
    except Exception:
        value = int(default)
    if value <= 0 and unlimited_value is not None:
        return max(minimum, int(unlimited_value))
    return max(minimum, value)


class NativeDocumentParser:
    """Native parser pipeline (PDF/DOCX/XLSX) with built-in libraries only."""

    _ocr_engine = None
    _ocr_engine_init_error: Optional[str] = None

    def __init__(self, max_pages: int | None = None) -> None:
        self._normalize_text = plain_normalize_text
        self._split_page_text = plain_split_page_text
        self._normalize_token_for_compare = normalize_token_for_compare
        self._getenv = os.getenv
        self._parser_run_state = ParserRunStateRuntime()
        self._parser_initialization_runtime = ParserInitializationRuntime()
        self._parser_bootstrap_runtime = ParserBootstrapRuntime()
        self._parser_dependency_bundle_runtime = ParserDependencyBundleRuntime()
        self._parser_initialization_runtime.initialize(
            parser=self,
            max_pages=max_pages,
            text_extensions=TEXT_EXTENSIONS,
            image_extensions=IMAGE_EXTENSIONS,
            limit_env_value=_limit_env_value,
        )

    @staticmethod
    def _gemini_api_key() -> str:
        return resolve_llm_api_key()

    def _gemini_native_api_key(self) -> str:
        return self._parser_provider_bundle_runtime.resolve_native_api_key(getenv=os.getenv)

    def _visual_backend_available(self) -> Tuple[bool, str]:
        return self._parser_provider_bundle_runtime.visual_backend_available()

    def parse_document(
        self,
        file_name: str,
        file_bytes: bytes,
        track: str = "FastTrack",
        source_file_name: Optional[str] = None,
        source_file_bytes: Optional[bytes] = None,
        source_cache_identity: str = "",
    ) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        self._parser_run_state.reset()
        runtime_result = self._document_dispatch_runtime.parse_document(
            file_name=file_name,
            file_bytes=file_bytes,
            track=track,
            source_file_name=source_file_name,
            source_file_bytes=source_file_bytes,
            source_cache_identity=source_cache_identity,
        )
        self._parser_run_state.apply_runtime_stats_patch(runtime_result.get("stats_patch"))
        result = runtime_result.get("result")
        if result is None:
            raise ValueError("Document dispatch runtime returned no result.")
        return result

    def get_last_figure_blocks(self) -> FigureBlocks:
        return self._parser_run_state.get_last_figure_blocks()

    def get_last_parse_stats(self) -> Dict[str, Any]:
        return self._parser_run_state.get_last_parse_stats()

    def _overlay_last_parse_stats(self, stats_patch: Any) -> None:
        self._parser_run_state.overlay_last_parse_stats(stats_patch)

    def _merge_docx_chart_xml_into_pdf_figures(self, *, file_bytes: bytes) -> None:
        self._parser_docx_pdf_entry_runtime.merge_docx_chart_xml_into_pdf_figures(
            docx_chart_merge_runtime=self._docx_chart_merge_runtime,
            file_bytes=file_bytes,
            overlay_last_parse_stats=self._parser_run_state.overlay_last_parse_stats,
            peek_last_figure_blocks=self._parser_run_state.peek_last_figure_blocks,
            set_last_figure_blocks=self._parser_run_state.set_last_figure_blocks,
        )

    def _mineru_layout_extractor_kwargs(self) -> Dict[str, Any]:
        return self._parser_provider_bundle_runtime.build_mineru_layout_kwargs(
            backend=self.mineru_backend,
            method=self.mineru_method,
            timeout_sec=self.mineru_timeout_sec,
            cache_dir=self.mineru_cache_dir,
            enable_cache=self.mineru_enable_cache,
            enable_formula=self.mineru_enable_formula,
            enable_table=self.mineru_enable_table,
            device=self.mineru_device,
            method_fallbacks=self.mineru_method_fallbacks,
        )

    def _roi_cropper_kwargs(self) -> Dict[str, Any]:
        return self._parser_provider_bundle_runtime.build_roi_cropper_kwargs(
            table_dpi=self.visual_crop_table_dpi,
            figure_dpi=self.visual_crop_figure_dpi,
            expand_ratio=self.visual_crop_expand_ratio,
            max_side_px=self.visual_crop_max_side_px,
        )

    def _visual_vision_extractor_kwargs(self) -> Dict[str, Any]:
        return self._parser_provider_bundle_runtime.build_visual_vision_kwargs(
            api_key=self._gemini_api_key(),
            native_api_key=self._gemini_native_api_key(),
            model=self.gemini_vision_model,
            base_url=self.gemini_vision_base_url,
            endpoint_style=self.gemini_vision_endpoint_style,
            timeout_sec=self.gemini_vision_timeout_sec,
            max_output_tokens=self.gemini_vision_max_output_tokens,
            retry_count=self.visual_vision_retry_count,
            cache_dir=self.gemini_cache_dir,
            enable_cache=self.gemini_cache_enable,
            reasoning_effort=self.gemini_vision_reasoning_effort,
            native_fallback_enabled=self.gemini_native_fallback_enabled,
        )

    def _parse_pdf(
        self,
        file_name: str,
        file_bytes: bytes,
        track: str,
        source_file_name: Optional[str] = None,
        source_file_bytes: Optional[bytes] = None,
        source_cache_identity: str = "",
    ) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        return self._parser_pdf_entry_runtime.parse_pdf(
            file_name=file_name,
            file_bytes=file_bytes,
            track=track,
            pdf_reader_factory=lambda pdf_bytes: PdfReader(io.BytesIO(pdf_bytes)),
            set_runtime_page_count=self._parser_run_state.set_runtime_page_count,
            pdf_parse_runtime=self._pdf_parse_runtime,
            source_cache_identity=source_cache_identity,
            source_file_name=source_file_name,
            source_file_bytes=source_file_bytes,
            last_figure_blocks=self._parser_run_state.peek_last_figure_blocks(),
            parse_pdf_with_ocr=self._parse_pdf_with_ocr,
            current_stats=self._parser_run_state.peek_last_parse_stats(),
            get_current_stats=self._parser_run_state.get_last_parse_stats,
            build_pdf_runtime_state=ParserStateRuntime.build_pdf_runtime_state,
            apply_state_update=self._parser_run_state.apply_state_update,
        )

    def _parse_docx_via_pdf(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
    ) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        return self._parser_docx_pdf_entry_runtime.parse_docx_via_pdf(
            docx_via_pdf_runtime=self._docx_via_pdf_runtime,
            docx_chart_merge_runtime=self._docx_chart_merge_runtime,
            file_name=file_name,
            file_bytes=file_bytes,
            word_pdf_docx_chart_xml_merge_enable=self.word_pdf_docx_chart_xml_merge_enable,
            overlay_last_parse_stats=self._parser_run_state.overlay_last_parse_stats,
            peek_last_figure_blocks=self._parser_run_state.peek_last_figure_blocks,
            set_last_figure_blocks=self._parser_run_state.set_last_figure_blocks,
        )

    def _parse_pdf_visual_first(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        reader: PdfReader,
        page_count: int,
        source_cache_identity: str = "",
        source_file_name: Optional[str] = None,
        source_file_bytes: Optional[bytes] = None,
    ) -> Optional[Tuple[str, Dict[str, List[float]], TableBlocks]]:
        return self._parser_pdf_entry_runtime.parse_pdf_visual_first(
            pdf_visual_parse_runtime=self._pdf_visual_parse_runtime,
            file_name=file_name,
            file_bytes=file_bytes,
            reader=reader,
            page_count=page_count,
            layout_extractor=self._parser_provider_state_runtime.get_mineru_layout_extractor(),
            vision=self._parser_provider_state_runtime.get_visual_vision_extractor(),
            set_last_mineru_run_meta=self._parser_run_state.set_last_mineru_run_meta,
            build_visual_parse_state=ParserStateRuntime.build_visual_parse_state,
            apply_state_update=self._parser_run_state.apply_state_update,
            source_cache_identity=source_cache_identity,
            source_file_name=source_file_name,
            source_file_bytes=source_file_bytes,
        )

    def _parse_pdf_with_ocr(
        self,
        file_bytes: bytes,
        page_count: int,
        cue_pages: List[int] | None = None,
    ) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        return self._parser_pdf_entry_runtime.parse_pdf_with_ocr(
            pdf_ocr_runtime=self._pdf_ocr_runtime,
            file_bytes=file_bytes,
            page_count=page_count,
            set_last_figure_blocks=self._parser_run_state.set_last_figure_blocks,
            cue_pages=cue_pages,
        )

    @classmethod
    def _get_ocr_engine(cls):
        if cls._ocr_engine is not None:
            return cls._ocr_engine
        if cls._ocr_engine_init_error:
            raise RuntimeError(cls._ocr_engine_init_error)
        try:
            cls._ocr_engine = OcrEngineRuntime.get_ocr_engine()
        except RuntimeError as exc:
            cls._ocr_engine_init_error = str(exc)
            raise
        return cls._ocr_engine

    def _parse_docx(self, file_bytes: bytes) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        return self._parser_nonpdf_entry_runtime.parse_docx(
            docx_document_runtime=self._docx_document_runtime,
            file_bytes=file_bytes,
            build_named_runtime_state=ParserStateRuntime.build_named_runtime_state,
            apply_state_update=self._parser_run_state.apply_state_update,
        )

    def _parse_docx_relaxed(self, file_bytes: bytes) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        return self._parser_nonpdf_entry_runtime.parse_docx_relaxed(
            docx_document_runtime=self._docx_document_runtime,
            file_bytes=file_bytes,
            build_named_runtime_state=ParserStateRuntime.build_named_runtime_state,
            apply_state_update=self._parser_run_state.apply_state_update,
        )

    def _parse_xlsx(self, file_bytes: bytes) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        return self._parser_nonpdf_entry_runtime.parse_xlsx(
            xlsx_parse_runtime=self._xlsx_parse_runtime,
            file_bytes=file_bytes,
            build_xlsx_state=ParserStateRuntime.build_xlsx_state,
            apply_state_update=self._parser_run_state.apply_state_update,
        )

    def _parse_image(
        self,
        file_name: str,
        file_bytes: bytes,
        *,
        enable_gemini_enhance: bool | None = None,
    ) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        return self._parser_nonpdf_entry_runtime.parse_image(
            image_document_runtime=self._image_document_runtime,
            file_name=file_name,
            file_bytes=file_bytes,
            last_figure_blocks=self._parser_run_state.peek_last_figure_blocks(),
            build_named_runtime_state=ParserStateRuntime.build_named_runtime_state,
            apply_state_update=self._parser_run_state.apply_state_update,
            enable_gemini_enhance=enable_gemini_enhance,
        )

    def _enhance_low_quality_pages_with_gemini_vision(
        self,
        file_bytes: bytes,
        filetype: str,
        page_lines: Dict[int, List[str]],
        table_blocks: TableBlocks,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        source_prefix: str,
    ) -> Tuple[TableBlocks, FigureBlocks]:
        return self._image_vision_runtime.enhance_low_quality_pages_with_gemini_vision(
            file_bytes=file_bytes,
            filetype=filetype,
            page_lines=page_lines,
            table_blocks=table_blocks,
            last_figure_blocks=self._parser_run_state.peek_last_figure_blocks(),
            parts=parts,
            bbox_map=bbox_map,
            source_prefix=source_prefix,
        )

    def _parse_plain(self, file_bytes: bytes, ext: str = ".txt") -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        return self._parser_nonpdf_entry_runtime.parse_plain(
            file_bytes=file_bytes,
            ext=ext,
            table_max_rows=self.table_max_rows,
            table_max_cols=self.table_max_cols,
            nonpdf_figure_max=self.nonpdf_figure_max,
            parse_plain_payload=parse_plain_payload,
            build_header_meta=build_header_meta,
            decorate_rows_with_meta=decorate_rows_with_meta,
            looks_like_figure_cue_text=self._figure_inference.looks_like_figure_cue_text,
            merge_figure_blocks=self._figure_inference.merge_figure_blocks,
            build_plain_text_state=ParserStateRuntime.build_plain_text_state,
            apply_state_update=self._parser_run_state.apply_state_update,
        )

    def _looks_like_false_table(self, headers: List[str], data_rows: List[Dict[str, Any]]) -> bool:
        return self._ocr_table_utils.looks_like_false_table(
            headers,
            data_rows,
            runtime_page_count=self._parser_run_state.runtime_page_count(),
        )

def parse_document_in_subprocess(
    file_bytes: bytes,
    file_name: str = "document.pdf",
    track: str = "FastTrack",
    source_file_name: Optional[str] = None,
    source_file_bytes: Optional[bytes] = None,
) -> Tuple[str, Dict[str, List[float]], TableBlocks, FigureBlocks, Dict[str, Any]]:
    """ProcessPool entrypoint (must be top-level and picklable)."""
    return parse_document_in_subprocess_runtime(
        parser_factory=NativeDocumentParser,
        file_bytes=file_bytes,
        file_name=file_name,
        track=track,
        source_file_name=source_file_name,
        source_file_bytes=source_file_bytes,
    )
