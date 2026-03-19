from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from dotenv import load_dotenv
from pypdf import PdfReader

MODULE2_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(dotenv_path=MODULE2_ROOT / ".env", override=False)

from app.assistant.provider import OpenAICompatibleChatProvider, resolve_llm_api_key, resolve_llm_base_url
from app.core.layout_mineru import MineruLayoutExtractor
from app.core.office_pdf import convert_word_bytes_to_pdf
from app.core.roi_cropper import RoiCropper
from app.core.vision_extractor import GeminiVisionExtractor


TableBlocks = List[Dict[str, Any]]
FigureBlocks = List[Dict[str, Any]]
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json", ".xml", ".html", ".htm"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}


class NativeDocumentParser:
    """Native parser pipeline (PDF/DOCX/XLSX) with built-in libraries only."""

    _ocr_engine = None
    _ocr_engine_init_error: Optional[str] = None

    def __init__(self, max_pages: int | None = None) -> None:
        self._runtime_page_count = 0
        self._last_figure_blocks: FigureBlocks = []
        self._last_parse_stats: Dict[str, Any] = {}
        self._last_mineru_run_meta: Dict[str, Any] = {}

        module2_root = Path(__file__).resolve().parents[2]
        repo_root = module2_root.parents[1]
        module2_cache_root = (module2_root / ".cache").resolve()

        def _resolve_cache_dir(raw_value: str, default_path: Path) -> str:
            raw = str(raw_value or "").strip()
            if not raw:
                return str(default_path.resolve())
            p = Path(raw)
            if p.is_absolute():
                return str(p.resolve())
            candidate_module2 = (module2_root / p).resolve()
            candidate_repo = (repo_root / p).resolve()
            normalized = raw.replace("\\", "/").lower()
            if normalized.startswith("backend/module2/"):
                return str(candidate_repo)
            if candidate_repo.exists() and not candidate_module2.exists():
                return str(candidate_repo)
            return str(candidate_module2)

        self.artifact_root_dir = Path(
            _resolve_cache_dir(
                os.getenv("MODULE2_ARTIFACT_ROOT_DIR", ""),
                module2_cache_root,
            )
        ).resolve()
        self.artifact_root_dir.mkdir(parents=True, exist_ok=True)
        self.office_convert_enabled = (
            os.getenv("MODULE2_DOC_TO_PDF_ENABLE", "true").lower() in {"1", "true", "yes"}
        )
        self.word_parse_via_pdf = (
            os.getenv(
                "MODULE2_WORD_PARSE_VIA_PDF",
                os.getenv("MODULE2_WORD_REQUIRE_PDF_PARSE", "true"),
            ).lower()
            in {"1", "true", "yes"}
        )
        self.word_convert_allow_native_fallback = (
            os.getenv("MODULE2_WORD_CONVERT_ALLOW_NATIVE_FALLBACK", "false").lower() in {"1", "true", "yes"}
        )
        self.word_pdf_timeout_sec = max(20.0, float(os.getenv("MODULE2_DOC_TO_PDF_TIMEOUT_SEC", "60")))
        self.max_pages = max_pages or max(1, int(os.getenv("MODULE2_MAX_PARSE_PAGES", "120")))
        self.max_pages_visual = max(
            self.max_pages,
            int(os.getenv("MODULE2_MAX_PARSE_PAGES_VISUAL", "480")),
        )
        self.visual_probe_pages = max(1, int(os.getenv("MODULE2_VISUAL_PROBE_PAGES", "12")))
        self.native_text_threshold = max(120, int(os.getenv("MODULE2_NATIVE_TEXT_THRESHOLD", "200")))
        self.ocr_max_pages = max(1, int(os.getenv("MODULE2_OCR_MAX_PAGES", "4")))
        self.ocr_extra_sample_pages = max(0, int(os.getenv("MODULE2_OCR_EXTRA_SAMPLE_PAGES", "10")))
        self.ocr_time_budget_sec = max(10.0, float(os.getenv("MODULE2_OCR_TIME_BUDGET_SEC", "90")))
        self.ocr_time_budget_per_page = max(0.2, float(os.getenv("MODULE2_OCR_TIME_BUDGET_PER_PAGE", "2.8")))
        self.ocr_time_budget_max_sec = max(
            self.ocr_time_budget_sec,
            float(os.getenv("MODULE2_OCR_TIME_BUDGET_MAX_SEC", "300")),
        )
        self.ocr_budget_guard_ratio = max(
            0.5,
            min(0.98, float(os.getenv("MODULE2_OCR_BUDGET_GUARD_RATIO", "0.90"))),
        )
        self.ocr_min_pages_before_budget = max(3, int(os.getenv("MODULE2_OCR_MIN_PAGES_BEFORE_BUDGET", "22")))
        self.ocr_cue_scan_pages = max(
            self.visual_probe_pages,
            int(os.getenv("MODULE2_OCR_CUE_SCAN_PAGES", str(self.max_pages_visual))),
        )
        self.ocr_cue_max_pages = max(0, int(os.getenv("MODULE2_OCR_CUE_MAX_PAGES", "220")))
        self.ocr_cue_boost_max_pages = max(1, int(os.getenv("MODULE2_OCR_CUE_BOOST_MAX_PAGES", "110")))
        self.ocr_cue_neighbor = max(0, int(os.getenv("MODULE2_OCR_CUE_NEIGHBOR", "1")))
        self.visual_weak_table_min = max(1, int(os.getenv("MODULE2_VISUAL_WEAK_TABLE_MIN", "4")))
        self.visual_weak_table_quality = max(
            0.0,
            min(1.0, float(os.getenv("MODULE2_VISUAL_WEAK_TABLE_QUALITY", "0.35"))),
        )
        self.visual_force_ocr_on_weak_native = (
            os.getenv("MODULE2_VISUAL_FORCE_OCR_ON_WEAK_NATIVE", "true").lower() in {"1", "true", "yes"}
        )
        self.ocr_min_coverage_ratio = min(
            1.0,
            max(0.02, float(os.getenv("MODULE2_OCR_MIN_COVERAGE_RATIO", "0.14"))),
        )
        self.ocr_max_scan_pages = max(1, int(os.getenv("MODULE2_OCR_MAX_SCAN_PAGES", "96")))
        self.ocr_min_scan_pages = max(1, int(os.getenv("MODULE2_OCR_MIN_SCAN_PAGES", "28")))
        self.ocr_front_scan_pages = max(0, int(os.getenv("MODULE2_OCR_FRONT_SCAN_PAGES", "72")))
        self.ocr_large_doc_page_threshold = max(50, int(os.getenv("MODULE2_OCR_LARGE_DOC_PAGE_THRESHOLD", "220")))
        self.ocr_large_doc_dpi = max(72, int(os.getenv("MODULE2_OCR_LARGE_DOC_DPI", "96")))
        self.ocr_low_priority_dpi = max(72, int(os.getenv("MODULE2_OCR_LOW_PRIORITY_DPI", "84")))
        self.ocr_high_priority_pages = max(1, int(os.getenv("MODULE2_OCR_HIGH_PRIORITY_PAGES", "14")))
        self.ocr_dense_cue_threshold = max(20, int(os.getenv("MODULE2_OCR_DENSE_CUE_THRESHOLD", "160")))
        self.ocr_max_attempt_pages_dense_cue = max(16, int(os.getenv("MODULE2_OCR_MAX_ATTEMPT_PAGES_DENSE_CUE", "72")))
        self.ocr_max_attempt_pages_mid_cue = max(
            self.ocr_max_attempt_pages_dense_cue,
            int(os.getenv("MODULE2_OCR_MAX_ATTEMPT_PAGES_MID_CUE", "84")),
        )
        self.ocr_dynamic_neighbor_pages = max(0, int(os.getenv("MODULE2_OCR_DYNAMIC_NEIGHBOR_PAGES", "0")))
        self.ocr_dynamic_neighbor_auto_enable = (
            os.getenv("MODULE2_OCR_DYNAMIC_NEIGHBOR_AUTO_ENABLE", "true").lower() in {"1", "true", "yes"}
        )
        self.ocr_dynamic_neighbor_auto_max = max(0, int(os.getenv("MODULE2_OCR_DYNAMIC_NEIGHBOR_AUTO_MAX", "8")))
        self.ocr_dynamic_early_stop_enable = (
            os.getenv("MODULE2_OCR_DYNAMIC_EARLY_STOP_ENABLE", "true").lower() in {"1", "true", "yes"}
        )
        self.ocr_dynamic_early_stop_min_pages = max(
            12,
            int(os.getenv("MODULE2_OCR_DYNAMIC_EARLY_STOP_MIN_PAGES", "34")),
        )
        self.ocr_dynamic_early_stop_streak = max(
            4,
            int(os.getenv("MODULE2_OCR_DYNAMIC_EARLY_STOP_STREAK", "14")),
        )
        self.ocr_dynamic_early_stop_min_signal_pages = max(
            2,
            int(os.getenv("MODULE2_OCR_DYNAMIC_EARLY_STOP_MIN_SIGNAL_PAGES", "8")),
        )
        self.ocr_low_cue_boost_enable = (
            os.getenv("MODULE2_OCR_LOW_CUE_BOOST_ENABLE", "false").lower() in {"1", "true", "yes"}
        )
        self.ocr_low_cue_min_pages_cap = max(
            24,
            int(os.getenv("MODULE2_OCR_LOW_CUE_MIN_PAGES_CAP", "44")),
        )
        self.enable_fitz_table = os.getenv("MODULE2_ENABLE_FITZ_TABLE", "true").lower() in {"1", "true", "yes"}
        self.ocr_table_min_cols = max(2, int(os.getenv("MODULE2_OCR_TABLE_MIN_COLS", "2")))
        self.ocr_table_min_rows = max(2, int(os.getenv("MODULE2_OCR_TABLE_MIN_ROWS", "2")))
        self.ocr_table_row_tol = max(0.006, float(os.getenv("MODULE2_OCR_TABLE_ROW_TOL", "0.018")))
        self.ocr_table_col_tol = max(0.01, float(os.getenv("MODULE2_OCR_TABLE_COL_TOL", "0.04")))
        self.ocr_table_row_gap = max(0.02, float(os.getenv("MODULE2_OCR_TABLE_ROW_GAP", "0.08")))
        self.ocr_table_relaxed_row_gap_scale = max(
            1.0,
            float(os.getenv("MODULE2_OCR_TABLE_RELAXED_ROW_GAP_SCALE", "1.5")),
        )
        self.ocr_table_relaxed_align_min = max(
            0.1,
            min(0.9, float(os.getenv("MODULE2_OCR_TABLE_RELAXED_ALIGN_MIN", "0.36"))),
        )
        self.ocr_table_relaxed_overlap_min = max(
            0.1,
            min(0.9, float(os.getenv("MODULE2_OCR_TABLE_RELAXED_OVERLAP_MIN", "0.3"))),
        )
        self.ocr_table_relaxed_col_diff_max = max(
            1,
            int(os.getenv("MODULE2_OCR_TABLE_RELAXED_COL_DIFF_MAX", "2")),
        )
        self.ocr_table_min_quality = max(0.1, float(os.getenv("MODULE2_OCR_TABLE_MIN_QUALITY", "0.52")))
        self.ocr_table_relaxed_min_quality = max(
            0.1,
            min(
                self.ocr_table_min_quality,
                float(os.getenv("MODULE2_OCR_TABLE_RELAXED_MIN_QUALITY", "0.42")),
            ),
        )
        self.ocr_relaxed_trigger_table_count = max(
            1,
            int(os.getenv("MODULE2_OCR_RELAXED_TRIGGER_TABLE_COUNT", "6")),
        )
        self.ocr_line_aug_max_extra_cue_pages = max(
            0,
            int(os.getenv("MODULE2_OCR_LINE_AUG_MAX_EXTRA_CUE_PAGES", "24")),
        )
        self.ocr_uncovered_line_aug_pages = max(
            0,
            int(os.getenv("MODULE2_OCR_UNCOVERED_LINE_AUG_PAGES", "8")),
        )
        self.table_max_rows = max(1, int(os.getenv("MODULE2_TABLE_MAX_ROWS", "120")))
        self.table_max_cols = max(1, int(os.getenv("MODULE2_TABLE_MAX_COLS", "20")))
        self.table_cell_cap = max(200, int(os.getenv("MODULE2_TABLE_CELL_CAP", "3000")))
        self.xlsx_sheet_limit = max(1, int(os.getenv("MODULE2_XLSX_SHEET_LIMIT", "8")))
        self.xlsx_cell_cap = max(200, int(os.getenv("MODULE2_XLSX_CELL_CAP", "1600")))
        self.docx_chart_xml_enable = os.getenv("MODULE2_DOCX_CHART_XML_ENABLE", "true").lower() in {
            "1",
            "true",
            "yes",
        }
        self.docx_media_probe_enable = os.getenv("MODULE2_DOCX_MEDIA_PROBE_ENABLE", "true").lower() in {
            "1",
            "true",
            "yes",
        }
        self.docx_media_max_assets = max(0, int(os.getenv("MODULE2_DOCX_MEDIA_MAX_ASSETS", "24")))
        self.docx_media_vision_enable = os.getenv("MODULE2_DOCX_MEDIA_VISION_ENABLE", "true").lower() in {
            "1",
            "true",
            "yes",
        }
        self.docx_media_vision_max_assets = max(
            0,
            min(
                self.docx_media_max_assets,
                int(os.getenv("MODULE2_DOCX_MEDIA_VISION_MAX_ASSETS", "6")),
            ),
        )
        self.docx_media_vision_max_bytes = max(
            200 * 1024,
            int(os.getenv("MODULE2_DOCX_MEDIA_VISION_MAX_BYTES", str(6 * 1024 * 1024))),
        )
        self.docx_media_vision_chart_only = os.getenv("MODULE2_DOCX_MEDIA_VISION_CHART_ONLY", "true").lower() in {
            "1",
            "true",
            "yes",
        }
        self.docx_media_vision_allow_noncue = os.getenv("MODULE2_DOCX_MEDIA_VISION_ALLOW_NONCUE", "true").lower() in {
            "1",
            "true",
            "yes",
        }
        self.nonpdf_figure_max = max(0, int(os.getenv("MODULE2_NONPDF_FIGURE_MAX", "24")))
        self.table_merge_enable = os.getenv("MODULE2_TABLE_MERGE_ENABLE", "true").lower() in {"1", "true", "yes"}
        self.table_merge_max_page_gap = max(1, int(os.getenv("MODULE2_TABLE_MERGE_MAX_PAGE_GAP", "1")))
        self.table_merge_header_sim = max(
            0.0,
            min(1.0, float(os.getenv("MODULE2_TABLE_MERGE_HEADER_SIM_THRESHOLD", "0.58"))),
        )
        self.table_merge_col_overlap = max(
            0.3,
            min(1.0, float(os.getenv("MODULE2_TABLE_MERGE_COL_OVERLAP_THRESHOLD", "0.55"))),
        )
        self.enable_gemini_vision_enhance = (
            os.getenv("MODULE2_ENABLE_GEMINI_VISION_ENHANCE", "true").lower() in {"1", "true", "yes"}
        )
        self.gemini_vision_model = os.getenv(
            "MODULE2_GEMINI_VISION_MODEL",
            os.getenv("MODULE2_GEMINI_MODEL", "gemini-3-flash-preview"),
        )
        self.gemini_vision_timeout_sec = max(5.0, float(os.getenv("MODULE2_GEMINI_VISION_TIMEOUT_SEC", "25")))
        self.gemini_vision_dpi = max(96, int(os.getenv("MODULE2_GEMINI_VISION_DPI", "150")))
        self.gemini_vision_max_side_px = max(768, int(os.getenv("MODULE2_GEMINI_VISION_MAX_SIDE_PX", "1800")))
        self.gemini_vision_max_pages = max(0, int(os.getenv("MODULE2_GEMINI_VISION_MAX_PAGES", "24")))
        self.gemini_vision_max_tables_per_page = max(
            1,
            int(os.getenv("MODULE2_GEMINI_VISION_MAX_TABLES_PER_PAGE", "5")),
        )
        self.gemini_vision_max_figures_per_page = max(
            0,
            int(os.getenv("MODULE2_GEMINI_VISION_MAX_FIGURES_PER_PAGE", "8")),
        )
        self.gemini_vision_enable_figures = (
            os.getenv("MODULE2_GEMINI_VISION_ENABLE_FIGURES", "true").lower() in {"1", "true", "yes"}
        )
        self.gemini_vision_min_table_quality = max(
            0.1,
            min(1.0, float(os.getenv("MODULE2_GEMINI_VISION_MIN_TABLE_QUALITY", "0.72"))),
        )
        self.gemini_vision_min_figure_quality = max(
            0.1,
            min(1.0, float(os.getenv("MODULE2_GEMINI_VISION_MIN_FIGURE_QUALITY", "0.56"))),
        )
        self.gemini_vision_max_output_tokens = max(
            512,
            int(os.getenv("MODULE2_GEMINI_VISION_MAX_OUTPUT_TOKENS", "4096")),
        )
        self.gemini_vision_reasoning_effort = str(
            os.getenv("MODULE2_GEMINI_VISION_REASONING_EFFORT", "minimal") or "minimal"
        ).strip().lower() or "minimal"
        if self.gemini_vision_reasoning_effort not in {"minimal", "low", "medium", "high"}:
            self.gemini_vision_reasoning_effort = "minimal"
        self.gemini_native_fallback_enabled = (
            os.getenv("MODULE2_GEMINI_NATIVE_FALLBACK", "false").lower() in {"1", "true", "yes"}
        )
        self.gemini_vision_consecutive_fail_stop = max(
            1,
            int(os.getenv("MODULE2_GEMINI_VISION_CONSECUTIVE_FAIL_STOP", "2")),
        )
        self.pipeline_mode = (os.getenv("MODULE2_PIPELINE_MODE", "visual_first") or "visual_first").strip().lower()
        if self.pipeline_mode not in {"legacy", "hybrid", "visual_first"}:
            self.pipeline_mode = "hybrid"
        self.enable_mineru_layout = (
            os.getenv("MODULE2_ENABLE_MINERU_LAYOUT", "true").lower() in {"1", "true", "yes"}
        )
        self.visual_first_allow_legacy_fallback = (
            os.getenv("MODULE2_VISUAL_FIRST_ALLOW_LEGACY_FALLBACK", "true").lower() in {"1", "true", "yes"}
        )
        self.visual_first_max_pages = min(
            self.max_pages_visual,
            max(1, int(os.getenv("MODULE2_VISUAL_FIRST_MAX_PAGES", "120"))),
        )
        self.visual_first_max_pages_scanned = min(
            self.visual_first_max_pages,
            max(1, int(os.getenv("MODULE2_VISUAL_FIRST_MAX_PAGES_SCANNED", "72"))),
        )
        self.visual_text_only_min_chars = max(
            20,
            int(os.getenv("MODULE2_VISUAL_TEXT_ONLY_MIN_CHARS", "80")),
        )
        self.visual_max_objects = max(8, int(os.getenv("MODULE2_VISUAL_MAX_OBJECTS", "220")))
        self.visual_table_max_per_page = max(
            1,
            int(os.getenv("MODULE2_VISUAL_TABLE_MAX_PER_PAGE", "6")),
        )
        self.visual_figure_max_per_page = max(
            0,
            int(os.getenv("MODULE2_VISUAL_FIGURE_MAX_PER_PAGE", "8")),
        )
        self.visual_table_min_confidence = max(
            0.0,
            min(1.0, float(os.getenv("MODULE2_VISUAL_TABLE_MIN_CONFIDENCE", "0.45"))),
        )
        self.visual_figure_min_confidence = max(
            0.0,
            min(1.0, float(os.getenv("MODULE2_VISUAL_FIGURE_MIN_CONFIDENCE", "0.35"))),
        )
        self.visual_figure_chart_only = (
            os.getenv("MODULE2_VISUAL_FIGURE_CHART_ONLY", "true").lower() in {"1", "true", "yes"}
        )
        self.visual_figure_allow_cueless_fallback = (
            os.getenv("MODULE2_VISUAL_FIGURE_ALLOW_CUELESS_FALLBACK", "true").lower() in {"1", "true", "yes"}
        )
        self.visual_figure_cueless_fallback_max = max(
            0,
            int(os.getenv("MODULE2_VISUAL_FIGURE_CUELESS_FALLBACK_MAX", "2")),
        )
        self.visual_figure_chart_score_min = max(
            1,
            int(os.getenv("MODULE2_VISUAL_FIGURE_CHART_SCORE_MIN", "3")),
        )
        self.visual_context_max_chars = max(600, int(os.getenv("MODULE2_VISUAL_CONTEXT_MAX_CHARS", "2400")))
        self.visual_use_table_html_fallback = (
            os.getenv("MODULE2_VISUAL_USE_TABLE_HTML_FALLBACK", "true").lower() in {"1", "true", "yes"}
        )
        self.mineru_backend = os.getenv("MODULE2_MINERU_BACKEND", "pipeline")
        self.mineru_method = os.getenv("MODULE2_MINERU_METHOD", "auto")
        self.mineru_scanned_method = os.getenv("MODULE2_MINERU_SCANNED_METHOD", "auto")
        self.mineru_timeout_sec = max(120, int(os.getenv("MODULE2_MINERU_TIMEOUT_SEC", "3600")))
        self.mineru_cache_dir = _resolve_cache_dir(
            os.getenv("MODULE2_MINERU_CACHE_DIR", ""),
            module2_cache_root / "mineru",
        )
        self.mineru_device = os.getenv("MODULE2_MINERU_DEVICE", "cpu")
        self.mineru_method_fallbacks = os.getenv("MODULE2_MINERU_METHOD_FALLBACKS", "auto,ocr,txt")
        self.mineru_enable_cache = os.getenv("MODULE2_MINERU_ENABLE_CACHE", "true").lower() in {"1", "true", "yes"}
        self.mineru_enable_formula = os.getenv("MODULE2_MINERU_ENABLE_FORMULA", "false").lower() in {
            "1",
            "true",
            "yes",
        }
        # Module 2 relies on Gemini ROI enhancement for table structure recovery, so
        # MinerU only needs stable layout/table-region detection here.
        self.mineru_enable_table = os.getenv("MODULE2_MINERU_ENABLE_TABLE", "false").lower() in {"1", "true", "yes"}
        self.visual_crop_table_dpi = max(120, int(os.getenv("MODULE2_VISUAL_TABLE_CROP_DPI", "260")))
        self.visual_crop_figure_dpi = max(120, int(os.getenv("MODULE2_VISUAL_FIGURE_CROP_DPI", "220")))
        self.visual_crop_expand_ratio = max(
            0.0,
            min(0.2, float(os.getenv("MODULE2_VISUAL_CROP_EXPAND_RATIO", "0.03"))),
        )
        self.visual_crop_max_side_px = max(1200, int(os.getenv("MODULE2_VISUAL_CROP_MAX_SIDE_PX", "2800")))
        self.visual_vision_retry_count = max(0, int(os.getenv("MODULE2_VISUAL_VISION_RETRY_COUNT", "1")))
        self.gemini_cache_dir = _resolve_cache_dir(
            os.getenv("MODULE2_GEMINI_CACHE_DIR", ""),
            module2_cache_root / "gemini",
        )
        self.gemini_cache_enable = os.getenv("MODULE2_GEMINI_CACHE_ENABLE", "true").lower() in {"1", "true", "yes"}
        self._mineru_layout_extractor: Optional[MineruLayoutExtractor] = None
        self._roi_cropper: Optional[RoiCropper] = None
        self._gemini_visual_extractor: Optional[GeminiVisionExtractor] = None

    @staticmethod
    def _gemini_api_key() -> str:
        return resolve_llm_api_key()

    @staticmethod
    def _gemini_native_api_key() -> str:
        for raw in (
            os.getenv("MODULE2_GEMINI_NATIVE_API_KEY", ""),
            os.getenv("GOOGLE_API_KEY", ""),
            os.getenv("GEMINI_API_KEY", ""),
        ):
            key = str(raw or "").strip()
            if key.startswith("AIza"):
                return key
        return ""

    @staticmethod
    def _visual_backend_available() -> Tuple[bool, str]:
        missing: List[str] = []
        try:
            fitz_available = importlib.util.find_spec("fitz") is not None
        except Exception:
            fitz_available = False
        if not fitz_available:
            missing.append("pymupdf")
        try:
            rapidocr_available = importlib.util.find_spec("rapidocr_onnxruntime") is not None
        except Exception:
            rapidocr_available = False
        if not rapidocr_available:
            missing.append("rapidocr-onnxruntime")
        if missing:
            return False, ", ".join(missing)
        return True, ""

    def parse_document(
        self,
        file_name: str,
        file_bytes: bytes,
        track: str = "FastTrack",
        source_file_name: Optional[str] = None,
        source_file_bytes: Optional[bytes] = None,
    ) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        self._last_figure_blocks = []
        self._last_parse_stats = {}
        self._last_mineru_run_meta = {}
        name = (file_name or "unknown").lower()
        _, ext = os.path.splitext(name)
        track_key = str(track or "").strip().lower()
        if ext == ".pdf":
            return self._parse_pdf(
                file_name,
                file_bytes,
                track,
                source_file_name=source_file_name,
                source_file_bytes=source_file_bytes,
            )
        if ext == ".docx":
            force_native_docx = track_key in {"nativedocx", "docxnative", "docx_native"}
            docx_fallback_stats: Dict[str, Any] | None = None
            if self.word_parse_via_pdf and self.office_convert_enabled and not force_native_docx:
                try:
                    return self._parse_docx_via_pdf(file_name=file_name, file_bytes=file_bytes)
                except Exception as exc:
                    if not self.word_convert_allow_native_fallback:
                        raise ValueError(f"DOCX->PDF parse route failed for {file_name}: {type(exc).__name__}: {exc}") from exc
                    docx_fallback_stats = {
                        "docx_pdf_conversion_failed": True,
                        "docx_pdf_conversion_error": f"{type(exc).__name__}: {exc}",
                        "docx_pdf_native_fallback": True,
                    }
            markdown, bbox_map, table_blocks = self._parse_docx(file_bytes)
            if docx_fallback_stats:
                merged_stats = dict(docx_fallback_stats)
                merged_stats.update(self._last_parse_stats)
                self._last_parse_stats = merged_stats
            if force_native_docx:
                merged_stats = dict(self._last_parse_stats)
                merged_stats["docx_native_forced"] = True
                merged_stats["docx_native_forced_track"] = track
                self._last_parse_stats = merged_stats
            return markdown, bbox_map, table_blocks
        if ext == ".xlsx":
            return self._parse_xlsx(file_bytes)
        if ext in TEXT_EXTENSIONS:
            return self._parse_plain(file_bytes, ext=ext)
        if ext in IMAGE_EXTENSIONS:
            return self._parse_image(file_name, file_bytes)
        raise ValueError(f"Unsupported file type: {ext or 'unknown'}")

    def get_last_figure_blocks(self) -> FigureBlocks:
        return [dict(item) for item in self._last_figure_blocks]

    def get_last_parse_stats(self) -> Dict[str, Any]:
        stats = dict(self._last_parse_stats)
        if self._last_mineru_run_meta:
            stats["mineru_run"] = dict(self._last_mineru_run_meta)
        return stats

    def _get_mineru_layout_extractor(self) -> MineruLayoutExtractor:
        if self._mineru_layout_extractor is None:
            self._mineru_layout_extractor = MineruLayoutExtractor(
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
        return self._mineru_layout_extractor

    def _get_roi_cropper(self) -> RoiCropper:
        if self._roi_cropper is None:
            self._roi_cropper = RoiCropper(
                table_dpi=self.visual_crop_table_dpi,
                figure_dpi=self.visual_crop_figure_dpi,
                expand_ratio=self.visual_crop_expand_ratio,
                max_side_px=self.visual_crop_max_side_px,
            )
        return self._roi_cropper

    def _get_visual_vision_extractor(self) -> GeminiVisionExtractor:
        if self._gemini_visual_extractor is None:
            self._gemini_visual_extractor = GeminiVisionExtractor(
                api_key=self._gemini_api_key(),
                native_api_key=self._gemini_native_api_key(),
                model=self.gemini_vision_model,
                timeout_sec=self.gemini_vision_timeout_sec,
                max_output_tokens=self.gemini_vision_max_output_tokens,
                retry_count=self.visual_vision_retry_count,
                cache_dir=self.gemini_cache_dir,
                enable_cache=self.gemini_cache_enable,
                reasoning_effort=self.gemini_vision_reasoning_effort,
                native_fallback_enabled=self.gemini_native_fallback_enabled,
            )
        return self._gemini_visual_extractor

    def _parse_pdf(
        self,
        file_name: str,
        file_bytes: bytes,
        track: str,
        source_file_name: Optional[str] = None,
        source_file_bytes: Optional[bytes] = None,
    ) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        reader = PdfReader(io.BytesIO(file_bytes))
        total_pages = len(reader.pages)
        self._runtime_page_count = total_pages
        if total_pages == 0:
            raise ValueError(f"PDF has no pages: {file_name}")

        source_cache_identity = ""
        source_cache_file_name = ""
        source_suffix = Path(source_file_name or "").suffix.lower()
        if source_suffix == ".docx" and isinstance(source_file_bytes, (bytes, bytearray)) and source_file_bytes:
            source_cache_identity = hashlib.sha256(bytes(source_file_bytes)).hexdigest()
            source_cache_file_name = str(source_file_name or "")

        if (
            track == "VisualTrack"
            and self.enable_mineru_layout
            and self.pipeline_mode in {"visual_first", "hybrid"}
        ):
            visual_page_count = min(total_pages, self.visual_first_max_pages)
            visual_error: Exception | None = None
            visual_fallback_stats: Dict[str, Any] = {}
            try:
                visual_result = self._parse_pdf_visual_first(
                    file_name=file_name,
                    file_bytes=file_bytes,
                    reader=reader,
                    page_count=visual_page_count,
                    source_cache_identity=source_cache_identity,
                )
            except Exception as exc:
                visual_error = exc
                visual_result = None
            if visual_result is not None:
                if source_cache_identity:
                    self._last_parse_stats["source_cache_identity_applied"] = True
                    self._last_parse_stats["source_cache_identity_file_name"] = source_cache_file_name
                return visual_result
            if self._last_mineru_run_meta:
                visual_status = str(self._last_mineru_run_meta.get("status", "") or "").strip()
                if visual_status:
                    visual_fallback_stats["visual_first_fallback_reason"] = visual_status
                runtime_error = str(self._last_mineru_run_meta.get("runtime_error", "") or "").strip()
                fatal_runtime_error = str(self._last_mineru_run_meta.get("fatal_runtime_error", "") or "").strip()
                if runtime_error:
                    visual_fallback_stats["visual_first_runtime_error"] = runtime_error[:240]
                elif fatal_runtime_error:
                    visual_fallback_stats["visual_first_runtime_error"] = fatal_runtime_error[:240]
            if self.pipeline_mode == "visual_first" and not self.visual_first_allow_legacy_fallback:
                if visual_error is not None:
                    raise visual_error
                raise ValueError("Visual-first pipeline returned no usable result.")
        visual_backend_ready, _ = self._visual_backend_available()

        cue_pages: List[int] = []
        visual_page_count = min(total_pages, self.max_pages_visual)
        if track == "VisualTrack":
            cue_scan_pages = min(visual_page_count, self.ocr_cue_scan_pages)
            cue_pages = self._collect_table_cue_pages(reader, cue_scan_pages)

        if track == "VisualTrack":
            probe_pages = min(total_pages, self.visual_probe_pages)
            probe_chars = 0
            for page_idx in range(probe_pages):
                page = reader.pages[page_idx]
                probe_chars += len(self._normalize_text(page.extract_text() or ""))
            if probe_chars < self.native_text_threshold:
                if visual_backend_ready:
                    return self._parse_pdf_with_ocr(file_bytes, visual_page_count, cue_pages=cue_pages)

        page_count = min(total_pages, self.max_pages)

        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        page_texts: List[str] = []
        total_chars = 0

        for page_idx in range(page_count):
            page_no = float(page_idx + 1)
            page = reader.pages[page_idx]
            text = self._normalize_text(page.extract_text() or "")
            page_texts.append(text)
            total_chars += len(text)

            chunks = self._split_page_text(text)
            if not chunks:
                ref_id = f"p{page_idx + 1}_c1"
                placeholder = f"[Page {page_idx + 1}] No extractable native text."
                parts.append(f'<ref id="{ref_id}">{escape(placeholder)}</ref>')
                bbox_map[ref_id] = [page_no, 0.0, 0.0, 1.0, 1.0]
                continue

            for chunk_idx, chunk in enumerate(chunks, start=1):
                ref_id = f"p{page_idx + 1}_c{chunk_idx}"
                parts.append(f'<ref id="{ref_id}">{escape(chunk)}</ref>')
                bbox_map[ref_id] = [page_no, 0.0, 0.0, 1.0, 1.0]

        if track == "VisualTrack" and total_chars < self.native_text_threshold and visual_backend_ready:
            return self._parse_pdf_with_ocr(file_bytes, page_count, cue_pages=cue_pages)

        native_page_lines: Dict[int, List[str]] = {}
        for idx, text in enumerate(page_texts, start=1):
            lines = [self._normalize_text(line) for line in text.splitlines()]
            lines = [line for line in lines if line]
            if lines:
                native_page_lines[idx] = lines

        fitz_tables: TableBlocks = []
        if self.enable_fitz_table:
            fitz_tables = self._extract_pdf_tables_with_fitz(file_bytes, page_count, parts, bbox_map)
        if fitz_tables:
            weak_fitz = self._is_weak_native_table_result(fitz_tables, cue_pages)
            if weak_fitz:
                line_page_lines = self._select_line_augmentation_pages(native_page_lines, fitz_tables, cue_pages=cue_pages)
                line_tables = self._infer_tables_from_page_lines(line_page_lines, parts, bbox_map, source="pdf_native")
            else:
                line_tables = []
        else:
            line_tables = self._infer_tables_from_page_lines(native_page_lines, parts, bbox_map, source="pdf_native")
        if fitz_tables and line_tables:
            table_blocks = self._augment_with_line_tables(fitz_tables, line_tables)
        elif fitz_tables:
            table_blocks = fitz_tables
        else:
            table_blocks = line_tables
        if table_blocks and self.table_merge_enable:
            table_blocks = self._merge_same_page_tables(table_blocks)
            table_blocks = self._merge_cross_page_tables(table_blocks)

        weak_native_tables = self._is_weak_native_table_result(table_blocks, cue_pages)
        if (
            track == "VisualTrack"
            and self.visual_force_ocr_on_weak_native
            and weak_native_tables
            and visual_backend_ready
        ):
            return self._parse_pdf_with_ocr(file_bytes, visual_page_count, cue_pages=cue_pages)

        figure_blocks: FigureBlocks = self._infer_figures_from_page_lines(
            page_lines=native_page_lines,
            parts=parts,
            bbox_map=bbox_map,
            source_prefix="pdf_caption",
        )

        shallow_native_figures = self._figure_blocks_need_vision(figure_blocks)
        native_vision_reasons: List[str] = []
        if not visual_backend_ready:
            native_vision_reasons.append("visual_backend_unavailable")
        if weak_native_tables:
            native_vision_reasons.append("weak_native_tables")
        if shallow_native_figures:
            native_vision_reasons.append("shallow_native_figures")
        if self.gemini_vision_enable_figures and page_count >= 20:
            native_vision_reasons.append("large_doc_figure_enrichment")
        should_run_native_vision = track == "VisualTrack" and bool(native_vision_reasons)
        if should_run_native_vision:
            vision_page_lines = dict(native_page_lines)
            for idx in range(1, page_count + 1):
                if idx not in vision_page_lines:
                    vision_page_lines[idx] = [f"[Page {idx}] vision probe"]
            table_blocks, vision_figures = self._enhance_low_quality_pages_with_gemini_vision(
                file_bytes=file_bytes,
                filetype="pdf",
                page_lines=vision_page_lines,
                table_blocks=table_blocks,
                parts=parts,
                bbox_map=bbox_map,
                source_prefix="pdf_gemini_vision_native",
            )
            if vision_figures:
                figure_blocks = self._merge_figure_blocks(figure_blocks, vision_figures)

        table_blocks = self._prune_fragment_tables(table_blocks)
        self._last_parse_stats = {
            "image_pages": int(self._runtime_page_count or 0),
            "image_ref_count": len(bbox_map),
            "image_table_count": len(table_blocks),
            "image_figure_count": len(figure_blocks),
            "native_vision_requested": should_run_native_vision,
            "native_vision_reasons": native_vision_reasons,
            "native_figure_blocks_shallow": shallow_native_figures,
            "native_visual_backend_ready": bool(visual_backend_ready),
            "source_cache_identity_applied": bool(source_cache_identity),
            "source_cache_identity_file_name": source_cache_file_name,
        }
        if track == "VisualTrack" and 'visual_fallback_stats' in locals() and visual_fallback_stats:
            self._last_parse_stats.update(visual_fallback_stats)
        self._last_figure_blocks = figure_blocks
        return "\n".join(parts), bbox_map, table_blocks

    def _parse_docx_via_pdf(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
    ) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        pdf_bytes, convert_meta = convert_word_bytes_to_pdf(
            file_name=file_name,
            file_bytes=file_bytes,
            timeout_sec=self.word_pdf_timeout_sec,
        )
        pdf_name = f"{Path(file_name).stem}.pdf"
        markdown, bbox_map, table_blocks = self._parse_pdf(
            pdf_name,
            pdf_bytes,
            "VisualTrack",
            source_file_name=file_name,
            source_file_bytes=file_bytes,
        )
        stats = dict(self._last_parse_stats)
        stats.update(
            {
                "word_via_pdf": True,
                "office_pdf_converted": True,
                "office_pdf_converter": str(convert_meta.get("converter", "")),
                "office_pdf_elapsed_ms": int(convert_meta.get("elapsed_ms", 0) or 0),
                "office_pdf_parse_input_name": pdf_name,
                "office_pdf_bytes": len(pdf_bytes),
            }
        )
        self._last_parse_stats = stats
        try:
            self._merge_docx_chart_xml_into_pdf_figures(file_bytes=file_bytes)
        except Exception as exc:
            self._last_parse_stats["docx_chart_xml_merge_error"] = f"{type(exc).__name__}: {exc}"
        return markdown, bbox_map, table_blocks

    def _merge_docx_chart_xml_into_pdf_figures(self, *, file_bytes: bytes) -> None:
        chart_tables, chart_stats = self._extract_docx_chart_xml_tables(file_bytes)
        if chart_stats:
            self._last_parse_stats.update(chart_stats)
        if not chart_tables or not self._last_figure_blocks:
            self._last_parse_stats["docx_chart_xml_merged"] = int(chart_stats.get("docx_chart_xml_merged", 0) or 0)
            return

        merged_figures: FigureBlocks = [dict(item) for item in self._last_figure_blocks]
        merged_count = 0
        unmatched_count = 0
        for table in chart_tables:
            chart_title = self._normalize_text(str(table.get("chart_title", "") or ""))
            figure_idx = self._find_matching_pdf_figure_index(chart_title=chart_title, figure_blocks=merged_figures)
            if figure_idx is None:
                unmatched_count += 1
                continue
            headers, rows = self._table_block_to_dataframe(table)
            if not headers or not rows:
                unmatched_count += 1
                continue
            figure = dict(merged_figures[figure_idx])
            dataframe = figure.get("dataframe") if isinstance(figure.get("dataframe"), dict) else {}
            existing_rows = dataframe.get("rows") if isinstance(dataframe.get("rows"), list) else []
            if existing_rows:
                continue
            figure["dataframe"] = {"headers": headers, "rows": rows}
            figure["dataframe_source"] = "docx_chart_xml_merge"
            modes = [
                self._normalize_text(str(item or "")).lower()
                for item in (figure.get("content_modes") if isinstance(figure.get("content_modes"), list) else [])
            ]
            modes = [item for item in modes if item in {"dataframe", "topology", "text", "visual"}]
            if "visual" not in modes:
                modes.append("visual")
            if "dataframe" not in modes:
                modes.insert(0, "dataframe")
            figure["content_modes"] = modes[:4]
            figure["quality"] = max(0.72, float(figure.get("quality", 0.0) or 0.0))
            insights = self._safe_text_list(figure.get("insights"), max_items=8, max_len=180)
            insights.append(f"dataframe: {len(rows)}x{max(len(row) for row in rows)}")
            figure["insights"] = insights[:8]
            merged_figures[figure_idx] = figure
            merged_count += 1

        self._last_figure_blocks = merged_figures
        self._last_parse_stats["docx_chart_xml_merged"] = merged_count
        self._last_parse_stats["docx_chart_xml_unmatched"] = unmatched_count

    def _extract_docx_chart_xml_tables(self, file_bytes: bytes) -> Tuple[TableBlocks, Dict[str, Any]]:
        stats: Dict[str, Any] = {
            "docx_chart_xml_seen": 0,
            "docx_chart_xml_parsed": 0,
            "docx_chart_xml_merged": 0,
        }
        if not self.docx_chart_xml_enable:
            return [], stats
        try:
            zf = zipfile.ZipFile(io.BytesIO(file_bytes))
        except Exception:
            return [], stats

        tables: TableBlocks = []
        with zf:
            chart_files = sorted(
                [name for name in zf.namelist() if name.startswith("word/charts/") and name.endswith(".xml")]
            )
            stats["docx_chart_xml_seen"] = len(chart_files)
            if not chart_files:
                return tables, stats

            ns = {
                "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
                "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
            }
            chart_max_series = max(2, int(os.getenv("MODULE2_DOCX_CHART_XML_MAX_SERIES", "10")))
            chart_max_points = max(6, int(os.getenv("MODULE2_DOCX_CHART_XML_MAX_POINTS", "40")))
            chart_table_max_rows = max(24, int(os.getenv("MODULE2_DOCX_CHART_XML_TABLE_MAX_ROWS", "220")))
            for chart_idx, chart_path in enumerate(chart_files, start=1):
                try:
                    root = ET.fromstring(zf.read(chart_path))
                except Exception:
                    continue

                title_tokens = [
                    self._normalize_text(str(node.text or ""))
                    for node in root.findall(".//c:title//a:t", ns)
                ]
                title = self._normalize_text(" ".join(item for item in title_tokens if item))
                if not title:
                    title = f"DOCX图表 {chart_idx}"

                series_payload = self._extract_docx_chart_series_payload(
                    root=root,
                    ns=ns,
                    max_series=chart_max_series,
                    max_points=chart_max_points,
                )
                if not series_payload:
                    continue

                chart_table = self._build_docx_chart_table_block(
                    chart_idx=chart_idx,
                    title=title,
                    series_payload=series_payload,
                    parts=[],
                    bbox_map={},
                    max_rows=chart_table_max_rows,
                )
                if not chart_table:
                    continue
                tables.append(chart_table)
                stats["docx_chart_xml_parsed"] = int(stats.get("docx_chart_xml_parsed", 0) or 0) + 1
        return tables, stats

    def _find_matching_pdf_figure_index(self, *, chart_title: str, figure_blocks: FigureBlocks) -> Optional[int]:
        title_norm = self._normalize_token_for_compare(chart_title)
        if not title_norm:
            return None
        title_marker = self._extract_figure_marker(chart_title)
        best_idx: Optional[int] = None
        best_score = 0
        for idx, figure in enumerate(figure_blocks):
            caption = self._normalize_text(str(figure.get("caption", "") or ""))
            caption_norm = self._normalize_token_for_compare(caption)
            if not caption_norm:
                continue
            score = 0
            if title_norm == caption_norm:
                score += 100
            elif title_norm in caption_norm or caption_norm in title_norm:
                score += 85
            if title_marker and title_marker == self._extract_figure_marker(caption):
                score += 35
            overlap = len(set(title_norm) & set(caption_norm))
            score += min(20, overlap)
            if score > best_score:
                best_score = score
                best_idx = idx
        if best_score < 40:
            return None
        return best_idx

    @staticmethod
    def _extract_figure_marker(text: str) -> str:
        match = re.search(
            r"(?:图|fig(?:ure)?)[\s._:-]*([0-9A-Za-z一二三四五六七八九十百千]+)",
            str(text or ""),
            flags=re.IGNORECASE,
        )
        if not match:
            return ""
        return str(match.group(1) or "").strip().lower()

    def _table_block_to_dataframe(self, table: Dict[str, Any]) -> Tuple[List[str], List[List[str]]]:
        headers = [self._normalize_text(str(item or "")) for item in (table.get("headers") if isinstance(table.get("headers"), list) else [])]
        headers = [item for item in headers if item]
        rows_out: List[List[str]] = []
        for row in table.get("rows") if isinstance(table.get("rows"), list) else []:
            if not isinstance(row, dict):
                continue
            cells = row.get("cells") if isinstance(row.get("cells"), list) else []
            ordered = sorted(
                [cell for cell in cells if isinstance(cell, dict)],
                key=lambda item: int(item.get("col_index", 0) or 0),
            )
            values = [self._normalize_text(str(cell.get("text", "") or "")) for cell in ordered]
            if any(values):
                rows_out.append(values)
        return headers, rows_out

    def _normalize_dataframe_headers(self, headers: Any, *, max_len: int = 120) -> List[str]:
        if not isinstance(headers, list):
            return []
        out: List[str] = []
        for item in headers:
            text = self._normalize_text(str(item or ""))
            if not text:
                continue
            if len(text) > max_len:
                text = text[:max_len]
            out.append(text)
        return out

    def _normalize_dataframe_matrix(self, rows: Any, *, max_cell_len: int = 160) -> List[List[str]]:
        if not isinstance(rows, list):
            return []
        out: List[List[str]] = []
        for row in rows:
            if not isinstance(row, list):
                continue
            vals: List[str] = []
            for cell in row:
                text = self._normalize_text(str(cell or ""))
                if len(text) > max_cell_len:
                    text = text[:max_cell_len]
                vals.append(text)
            if any(vals):
                out.append(vals)
        return out

    def _parse_pdf_visual_first(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        reader: PdfReader,
        page_count: int,
        source_cache_identity: str = "",
    ) -> Optional[Tuple[str, Dict[str, List[float]], TableBlocks]]:
        if page_count <= 0:
            return None
        visual_t0 = time.perf_counter()

        vision = self._get_visual_vision_extractor()
        vision_ready = bool(vision.ready)
        if vision_ready:
            try:
                vision.reset_stats()
            except Exception:
                pass

        probe_pages = min(page_count, max(3, self.visual_probe_pages))
        probe_chars = 0
        for page_idx in range(probe_pages):
            try:
                probe_chars += len(self._normalize_text(reader.pages[page_idx].extract_text() or ""))
            except Exception:
                continue
        mineru_method = self.mineru_method
        if probe_chars < self.native_text_threshold:
            mineru_method = self.mineru_scanned_method or self.mineru_method
            page_count = min(page_count, self.visual_first_max_pages_scanned)

        layout = self._get_mineru_layout_extractor()
        layout_t0 = time.perf_counter()
        objects, mineru_page_lines = layout.extract_layout(
            pdf_bytes=file_bytes,
            file_name=file_name,
            start_page=1,
            end_page=page_count,
            method=mineru_method,
            source_cache_identity=source_cache_identity,
        )
        layout_extract_ms = int((time.perf_counter() - layout_t0) * 1000)
        self._last_mineru_run_meta = layout.get_last_run_meta()
        native_page_lines: Dict[int, List[str]] = {}
        native_page_chunks: Dict[int, List[str]] = {}
        native_context_t0 = time.perf_counter()
        for page_idx in range(page_count):
            page_no = page_idx + 1
            try:
                raw_text = reader.pages[page_idx].extract_text() or ""
            except Exception:
                raw_text = ""
            text = self._normalize_text(raw_text)
            chunks = self._split_page_text(text)
            if chunks:
                native_page_chunks[page_no] = list(chunks)

            lines = [self._normalize_text(x) for x in raw_text.splitlines()]
            lines = [x for x in lines if x]
            if lines:
                native_page_lines[page_no] = lines[:120]
        native_context_ms = int((time.perf_counter() - native_context_t0) * 1000)
        merge_context_t0 = time.perf_counter()
        page_lines = self._merge_page_line_context(native_page_lines, mineru_page_lines)
        merge_context_ms = int((time.perf_counter() - merge_context_t0) * 1000)

        if not objects:
            text_only_result = self._build_visual_text_only_result(
                page_lines=page_lines,
                page_count=page_count,
                visual_t0=visual_t0,
                layout_extract_ms=layout_extract_ms,
                native_context_ms=native_context_ms,
                merge_context_ms=merge_context_ms,
                failure_reason="no_layout_objects",
                layout_object_count=0,
            )
            if text_only_result is not None:
                return text_only_result
            self._last_parse_stats = {
                "pipeline": "visual_first",
                "visual_page_count": int(page_count),
                "visual_failure": "no_layout_objects",
                "visual_phase_ms": {
                    "layout_extract_ms": layout_extract_ms,
                    "total_ms": int((time.perf_counter() - visual_t0) * 1000),
                },
            }
            return None

        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        page_dims = self._build_page_dimensions(reader=reader, page_count=page_count)
        for page_no in range(1, page_count + 1):
            chunks = native_page_chunks.get(page_no, [])
            if chunks:
                for chunk_idx, chunk in enumerate(chunks, start=1):
                    ref_id = f"p{page_no}_c{chunk_idx}"
                    self._append_ref(parts, bbox_map, ref_id, chunk, [float(page_no), 0.0, 0.0, 1.0, 1.0])
                continue
            ref_id = f"p{page_no}_c1"
            placeholder = f"[Page {page_no}] No extractable native text."
            self._append_ref(parts, bbox_map, ref_id, placeholder, [float(page_no), 0.0, 0.0, 1.0, 1.0])

        select_t0 = time.perf_counter()
        selected_objects, object_selection_stats = self._prioritize_layout_objects(
            objects,
            file_name=file_name,
            page_count=page_count,
            page_lines=page_lines,
        )
        select_ms = int((time.perf_counter() - select_t0) * 1000)
        if not selected_objects:
            text_only_result = self._build_visual_text_only_result(
                page_lines=page_lines,
                page_count=page_count,
                visual_t0=visual_t0,
                layout_extract_ms=layout_extract_ms,
                native_context_ms=native_context_ms,
                merge_context_ms=merge_context_ms,
                select_ms=select_ms,
                failure_reason="no_selected_objects",
                layout_object_count=len(objects),
                object_selection_stats=object_selection_stats,
            )
            if text_only_result is not None:
                return text_only_result
            self._last_parse_stats = {
                "pipeline": "visual_first",
                "visual_page_count": int(page_count),
                "visual_failure": "no_selected_objects",
                **object_selection_stats,
                "visual_phase_ms": {
                    "layout_extract_ms": layout_extract_ms,
                    "native_context_ms": native_context_ms,
                    "context_merge_ms": merge_context_ms,
                    "object_select_ms": select_ms,
                    "total_ms": int((time.perf_counter() - visual_t0) * 1000),
                },
            }
            return None

        table_source = "pdf_mineru_gemini" if vision_ready else "pdf_mineru"
        figure_source = "pdf_mineru_gemini" if vision_ready else "pdf_mineru"
        selected_table_candidates = int(object_selection_stats.get("visual_selected_table_candidates", 0) or 0)
        selected_figure_candidates = int(object_selection_stats.get("visual_selected_figure_candidates", 0) or 0)

        cropper = self._get_roi_cropper()
        table_blocks: TableBlocks = []
        figure_blocks: FigureBlocks = []
        table_count_by_page: Dict[int, int] = {}
        figure_count_by_page: Dict[int, int] = {}
        table_idx = 1
        figure_idx = 1
        emitted_cells = 0
        table_crop_ms = 0
        table_vision_ms = 0
        figure_crop_ms = 0
        figure_vision_ms = 0

        for item in selected_objects:
            obj_type = str(item.get("object_type", "") or "")
            page_no = int(item.get("page", 0) or 0)
            if page_no <= 0:
                continue

            if obj_type == "table":
                table_count_by_page[page_no] = table_count_by_page.get(page_no, 0)
                if table_count_by_page[page_no] >= self.visual_table_max_per_page:
                    continue
                if emitted_cells >= self.table_cell_cap:
                    break

                crop_t0 = time.perf_counter()
                roi_bytes, roi_mime, _ = cropper.load_or_crop(item=item, pdf_bytes=file_bytes, is_table=True)
                table_crop_ms += int((time.perf_counter() - crop_t0) * 1000)
                if not roi_bytes:
                    continue
                context = self._build_visual_object_context(
                    file_name=file_name,
                    page_no=page_no,
                    object_type="table",
                    item=item,
                    page_lines=page_lines,
                )
                vision_t0 = time.perf_counter()
                table_payload = (
                    vision.extract_table(
                        image_bytes=roi_bytes,
                        mime_type=roi_mime,
                        context=context,
                    )
                    if vision_ready
                    else {}
                )
                table_vision_ms += int((time.perf_counter() - vision_t0) * 1000)
                table_id = f"pdf_mineru_gemini_t{table_idx}"
                built_table, emitted_cells = self._build_table_from_visual_payload(
                    table_id=table_id,
                    page_no=page_no,
                    payload=table_payload or {},
                    item=item,
                    parts=parts,
                    bbox_map=bbox_map,
                    page_dims=page_dims,
                    emitted_cells=emitted_cells,
                    source=table_source,
                )
                if built_table is None:
                    continue
                try:
                    quality_val = float(built_table.get("quality", 0.0) or 0.0)
                except (TypeError, ValueError):
                    quality_val = 0.0
                if quality_val < self.visual_table_min_confidence:
                    continue
                table_blocks.append(built_table)
                table_count_by_page[page_no] = table_count_by_page.get(page_no, 0) + 1
                table_idx += 1
                continue

            if obj_type == "image" and self.visual_figure_max_per_page > 0:
                figure_count_by_page[page_no] = figure_count_by_page.get(page_no, 0)
                if figure_count_by_page[page_no] >= self.visual_figure_max_per_page:
                    continue

                crop_t0 = time.perf_counter()
                roi_bytes, roi_mime, _ = cropper.load_or_crop(item=item, pdf_bytes=file_bytes, is_table=False)
                figure_crop_ms += int((time.perf_counter() - crop_t0) * 1000)
                if not roi_bytes:
                    continue
                context = self._build_visual_object_context(
                    file_name=file_name,
                    page_no=page_no,
                    object_type="figure",
                    item=item,
                    page_lines=page_lines,
                )
                vision_t0 = time.perf_counter()
                figure_payload = (
                    vision.extract_figure(
                        image_bytes=roi_bytes,
                        mime_type=roi_mime,
                        context=context,
                    )
                    if vision_ready
                    else {}
                )
                figure_vision_ms += int((time.perf_counter() - vision_t0) * 1000)
                figure_id = f"pdf_mineru_gemini_f{figure_idx}"
                built_figure = self._build_figure_from_visual_payload(
                    figure_id=figure_id,
                    page_no=page_no,
                    payload=figure_payload or {},
                    item=item,
                    parts=parts,
                    bbox_map=bbox_map,
                    page_dims=page_dims,
                    source=figure_source,
                )
                if built_figure is None:
                    continue
                try:
                    quality_val = float(built_figure.get("quality", 0.0) or 0.0)
                except (TypeError, ValueError):
                    quality_val = 0.0
                if quality_val < self.visual_figure_min_confidence:
                    continue
                figure_blocks.append(built_figure)
                figure_count_by_page[page_no] = figure_count_by_page.get(page_no, 0) + 1
                figure_idx += 1

        if not table_blocks and not figure_blocks:
            self._last_parse_stats = {
                "pipeline": "visual_first",
                "visual_page_count": int(page_count),
                "visual_layout_object_count": len(selected_objects),
                "visual_selected_table_candidates": selected_table_candidates,
                "visual_selected_figure_candidates": selected_figure_candidates,
                **object_selection_stats,
                "visual_failure": "no_visual_blocks",
                "visual_phase_ms": {
                    "layout_extract_ms": layout_extract_ms,
                    "native_context_ms": native_context_ms,
                    "context_merge_ms": merge_context_ms,
                    "object_select_ms": select_ms,
                    "table_crop_ms": table_crop_ms,
                    "table_vision_ms": table_vision_ms,
                    "figure_crop_ms": figure_crop_ms,
                    "figure_vision_ms": figure_vision_ms,
                    "total_ms": int((time.perf_counter() - visual_t0) * 1000),
                },
            }
            return None

        postprocess_t0 = time.perf_counter()
        if table_blocks and self.table_merge_enable:
            table_blocks = self._merge_same_page_tables(table_blocks)
            table_blocks = self._merge_cross_page_tables(table_blocks)
        table_blocks = self._prune_fragment_tables(table_blocks)
        figure_blocks = self._merge_figure_blocks([], figure_blocks)
        postprocess_ms = int((time.perf_counter() - postprocess_t0) * 1000)
        self._last_parse_stats = {
            "pipeline": "visual_first",
            "visual_page_count": int(page_count),
            "visual_layout_object_count": len(selected_objects),
            "visual_selected_table_candidates": selected_table_candidates,
            "visual_selected_figure_candidates": selected_figure_candidates,
            **object_selection_stats,
            "visual_ref_count": len(bbox_map),
            "visual_table_count": len(table_blocks),
            "visual_figure_count": len(figure_blocks),
            "visual_table_source": table_source,
            "visual_figure_source": figure_source,
            "visual_phase_ms": {
                "layout_extract_ms": layout_extract_ms,
                "native_context_ms": native_context_ms,
                "context_merge_ms": merge_context_ms,
                "object_select_ms": select_ms,
                "table_crop_ms": table_crop_ms,
                "table_vision_ms": table_vision_ms,
                "figure_crop_ms": figure_crop_ms,
                "figure_vision_ms": figure_vision_ms,
                "postprocess_ms": postprocess_ms,
                "total_ms": int((time.perf_counter() - visual_t0) * 1000),
            },
        }
        if vision_ready:
            try:
                self._last_parse_stats["visual_vision_stats"] = vision.get_stats_snapshot()
                self._last_parse_stats["visual_vision_last_debug"] = vision.get_last_debug()
            except Exception:
                pass
        if self._last_mineru_run_meta:
            self._last_parse_stats["mineru_run"] = dict(self._last_mineru_run_meta)
        self._last_figure_blocks = figure_blocks
        return "\n".join(parts), bbox_map, table_blocks

    def _build_visual_text_only_result(
        self,
        *,
        page_lines: Dict[int, List[str]],
        page_count: int,
        visual_t0: float,
        layout_extract_ms: int,
        native_context_ms: int,
        merge_context_ms: int,
        failure_reason: str,
        layout_object_count: int,
        select_ms: int = 0,
        object_selection_stats: Dict[str, Any] | None = None,
    ) -> Optional[Tuple[str, Dict[str, List[float]], TableBlocks]]:
        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        text_char_count = 0
        for page_no in range(1, max(1, int(page_count)) + 1):
            lines = [self._normalize_text(x) for x in page_lines.get(page_no, [])]
            lines = [x for x in lines if x]
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

        if text_char_count < self.visual_text_only_min_chars:
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
        if object_selection_stats:
            stats.update(object_selection_stats)
        if self._last_mineru_run_meta:
            stats["mineru_run"] = dict(self._last_mineru_run_meta)
        self._last_parse_stats = stats
        self._last_figure_blocks = []
        return "\n".join(parts), bbox_map, []

    @staticmethod
    def _merge_page_line_context(
        native_lines: Dict[int, List[str]],
        mineru_lines: Dict[int, List[str]],
    ) -> Dict[int, List[str]]:
        merged: Dict[int, List[str]] = {}
        pages = set(native_lines.keys()) | set(mineru_lines.keys())
        for page_no in pages:
            out: List[str] = []
            seen = set()
            for source in (native_lines.get(page_no, []), mineru_lines.get(page_no, [])):
                for line in source:
                    text = " ".join(str(line or "").split())
                    if not text:
                        continue
                    key = text[:220].lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(text)
                    if len(out) >= 160:
                        break
                if len(out) >= 160:
                    break
            if out:
                merged[page_no] = out
        return merged

    def _prioritize_layout_objects(
        self,
        objects: List[Dict[str, Any]],
        *,
        file_name: str,
        page_count: int,
        page_lines: Dict[int, List[str]],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        if not objects:
            return [], {
                "visual_selected_table_candidates": 0,
                "visual_selected_figure_candidates": 0,
                "visual_figure_candidates_chart_like": 0,
                "visual_figure_candidates_filtered_nonchart": 0,
                "visual_figure_fallback_selected": 0,
                "visual_figure_chart_only": bool(self.visual_figure_chart_only),
            }
        cleaned = []
        for item in objects:
            obj_type = str(item.get("object_type", "") or "")
            if obj_type not in {"table", "image"}:
                continue
            page_no = int(item.get("page", 0) or 0)
            if page_no <= 0 or page_no > page_count:
                continue
            area = 0.0
            try:
                area = float(item.get("area", 0.0) or 0.0)
            except (TypeError, ValueError):
                area = 0.0
            cap_len = len(item.get("caption", [])) if isinstance(item.get("caption"), list) else 0
            figure_eval = None
            if obj_type == "image":
                figure_eval = self._evaluate_visual_figure_candidate(
                    file_name=file_name,
                    page_no=page_no,
                    item=item,
                    page_lines=page_lines,
                )
            cleaned.append((item, page_no, obj_type, cap_len, area, figure_eval))
        if not cleaned:
            return [], {
                "visual_selected_table_candidates": 0,
                "visual_selected_figure_candidates": 0,
                "visual_figure_candidates_chart_like": 0,
                "visual_figure_candidates_filtered_nonchart": 0,
                "visual_figure_fallback_selected": 0,
                "visual_figure_chart_only": bool(self.visual_figure_chart_only),
            }

        cleaned.sort(
            key=lambda x: (
                x[1],
                0 if x[2] == "table" else 1,
                0 if (x[5] or {}).get("chart_like") else 1,
                -int((x[5] or {}).get("score", 0) or 0),
                -x[3],
                -x[4],
            )
        )

        selected: List[Dict[str, Any]] = []
        summary: Dict[str, Any] = {
            "visual_selected_table_candidates": 0,
            "visual_selected_figure_candidates": 0,
            "visual_figure_candidates_chart_like": 0,
            "visual_figure_candidates_filtered_nonchart": 0,
            "visual_figure_fallback_selected": 0,
            "visual_figure_chart_only": bool(self.visual_figure_chart_only),
        }
        table_count_by_page: Dict[int, int] = {}
        figure_count_by_page: Dict[int, int] = {}
        fallback_images: List[Tuple[int, int, float, Dict[str, Any]]] = []
        selected_chart_figures = 0
        for item, page_no, obj_type, cap_len, area, figure_eval in cleaned:
            if len(selected) >= self.visual_max_objects:
                break
            if obj_type == "table":
                table_count_by_page[page_no] = table_count_by_page.get(page_no, 0)
                if table_count_by_page[page_no] >= self.visual_table_max_per_page:
                    continue
                table_count_by_page[page_no] += 1
                summary["visual_selected_table_candidates"] = int(summary.get("visual_selected_table_candidates", 0)) + 1
            else:
                summary["visual_selected_figure_candidates"] = int(summary.get("visual_selected_figure_candidates", 0)) + 1
                chart_like = bool((figure_eval or {}).get("chart_like"))
                if chart_like:
                    summary["visual_figure_candidates_chart_like"] = int(summary.get("visual_figure_candidates_chart_like", 0)) + 1
                if self.visual_figure_chart_only and not chart_like:
                    summary["visual_figure_candidates_filtered_nonchart"] = int(
                        summary.get("visual_figure_candidates_filtered_nonchart", 0)
                    ) + 1
                    if self.visual_figure_allow_cueless_fallback and self.visual_figure_cueless_fallback_max > 0:
                        fallback_images.append((page_no, cap_len, area, item))
                    continue
                if self.visual_figure_max_per_page <= 0:
                    continue
                figure_count_by_page[page_no] = figure_count_by_page.get(page_no, 0)
                if figure_count_by_page[page_no] >= self.visual_figure_max_per_page:
                    continue
                figure_count_by_page[page_no] += 1
                if chart_like:
                    selected_chart_figures += 1
            selected.append(item)

        if (
            self.visual_figure_chart_only
            and selected_chart_figures == 0
            and self.visual_figure_allow_cueless_fallback
            and self.visual_figure_cueless_fallback_max > 0
        ):
            fallback_images.sort(key=lambda item: (-item[1], -item[2], item[0]))
            fallback_used = 0
            for page_no, _cap_len, _area, item in fallback_images:
                if len(selected) >= self.visual_max_objects:
                    break
                if fallback_used >= self.visual_figure_cueless_fallback_max:
                    break
                if self.visual_figure_max_per_page <= 0:
                    break
                figure_count_by_page[page_no] = figure_count_by_page.get(page_no, 0)
                if figure_count_by_page[page_no] >= self.visual_figure_max_per_page:
                    continue
                figure_count_by_page[page_no] += 1
                selected.append(item)
                fallback_used += 1
            summary["visual_figure_fallback_selected"] = fallback_used

        return selected, summary

    def _evaluate_visual_figure_candidate(
        self,
        *,
        file_name: str,
        page_no: int,
        item: Dict[str, Any],
        page_lines: Dict[int, List[str]],
    ) -> Dict[str, Any]:
        caption_text = self._normalize_text(
            " ".join(self._safe_text_list(item.get("caption"), max_items=4, max_len=200))
        )
        footnote_text = self._normalize_text(
            " ".join(self._safe_text_list(item.get("footnote"), max_items=4, max_len=180))
        )
        page_hint = ""
        if not caption_text and not footnote_text:
            page_hint = self._normalize_text(" ".join(page_lines.get(page_no, [])[:24]))
        cue_text = self._normalize_text(" ".join(part for part in [file_name, caption_text, footnote_text, page_hint] if part))
        inferred_type = self._infer_figure_type_from_text(cue_text)
        score = 0
        reasons: List[str] = []

        if caption_text and self._contains_figure_marker(caption_text):
            score += 3
            reasons.append("caption_marker")
        elif cue_text and self._contains_figure_marker(cue_text):
            score += 2
            reasons.append("context_marker")

        if caption_text and self._looks_like_figure_cue_text(caption_text):
            score += 3
            reasons.append("caption_cue")
        elif cue_text and self._looks_like_figure_cue_text(cue_text):
            score += 1
            reasons.append("context_cue")

        if inferred_type == "chart":
            score += 3
            reasons.append("type_chart")
        elif inferred_type == "diagram":
            score += 2
            reasons.append("type_diagram")

        if caption_text and re.search(r"\d{2,}", caption_text):
            score += 1
            reasons.append("caption_numeric")

        chart_like = score >= self.visual_figure_chart_score_min or inferred_type in {"chart", "diagram"}
        return {
            "chart_like": bool(chart_like),
            "score": int(score),
            "reasons": reasons[:6],
            "inferred_type": inferred_type,
            "caption_text": caption_text[:240],
            "footnote_text": footnote_text[:240],
        }

    def _build_visual_object_context(
        self,
        *,
        file_name: str,
        page_no: int,
        object_type: str,
        item: Dict[str, Any],
        page_lines: Dict[int, List[str]],
    ) -> Dict[str, Any]:
        caption = self._normalize_text(" ".join(self._safe_text_list(item.get("caption"), max_items=4, max_len=200)))
        page_text = " ".join(page_lines.get(page_no, [])[:90]).strip()
        if len(page_text) > self.visual_context_max_chars:
            page_text = page_text[: self.visual_context_max_chars]
        domain_hints = self._infer_domain_hints(f"{file_name} {caption} {page_text[:900]}")
        return {
            "doc_name": file_name,
            "page": page_no,
            "object_type": object_type,
            "caption_hint": caption,
            "footnote_hint": self._safe_text_list(item.get("footnote"), max_items=4, max_len=180),
            "nearby_text": page_text,
            "domain_hints": domain_hints,
        }

    def _infer_domain_hints(self, text: str) -> List[str]:
        probe = self._normalize_text(text).lower()
        hints = [
            "Preserve table hierarchy and merged-header semantics.",
            "Do not fabricate missing cell values.",
            "Keep number formats and units exactly as shown.",
        ]
        if any(k in probe for k in ["compound", "chem", "cts", "reagent"]):
            hints.extend(
                [
                    "Keep chemical formulas verbatim, including parentheses and charge notation.",
                    "Do not split element symbols from subscripts/superscripts.",
                ]
            )
        if any(k in probe for k in ["nuclear", "fuel", "reactor", "isotope"]):
            hints.extend(
                [
                    "Preserve nuclide and isotope notation exactly.",
                    "Keep engineering symbols and scientific notation unchanged.",
                ]
            )
        if any(k in probe for k in ["gdp", "economic", "statistical", "bulletin"]):
            hints.extend(
                [
                    "Treat percentage, year-over-year, and unit columns as structured numeric fields.",
                    "Keep Chinese unit markers such as %, 万, 亿, 吨 when present.",
                ]
            )
        return hints[:10]

    @staticmethod
    def _append_ref(
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        ref_id: str,
        text: str,
        bbox: List[float],
    ) -> None:
        if not ref_id or ref_id in bbox_map:
            return
        parts.append(f'<ref id="{ref_id}">{escape(str(text or ""))}</ref>')
        bbox_map[ref_id] = [float(x) for x in bbox[:5]]

    @staticmethod
    def _build_page_dimensions(reader: PdfReader, page_count: int) -> Dict[int, Tuple[float, float]]:
        out: Dict[int, Tuple[float, float]] = {}
        for idx in range(page_count):
            page_no = idx + 1
            try:
                page = reader.pages[idx]
                width = float(page.mediabox.width)
                height = float(page.mediabox.height)
            except Exception:
                width = 1.0
                height = 1.0
            out[page_no] = (max(width, 1.0), max(height, 1.0))
        return out

    def _layout_bbox_to_ref_bbox(
        self,
        *,
        page_no: int,
        raw_bbox: Any,
        page_dims: Dict[int, Tuple[float, float]],
    ) -> List[float]:
        width, height = page_dims.get(page_no, (1.0, 1.0))
        if not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) < 4:
            return [float(page_no), 0.0, 0.0, 1.0, 1.0]
        try:
            x1, y1, x2, y2 = [float(raw_bbox[i]) for i in range(4)]
        except Exception:
            return [float(page_no), 0.0, 0.0, 1.0, 1.0]
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1

        if max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 1.5:
            x1 *= width
            x2 *= width
            y1 *= height
            y2 *= height
        else:
            sx = 1.0
            sy = 1.0
            if x2 > width * 1.2 and x2 > 1:
                sx = width / float(x2)
            if y2 > height * 1.2 and y2 > 1:
                sy = height / float(y2)
            x1 *= sx
            x2 *= sx
            y1 *= sy
            y2 *= sy

        x1 = max(0.0, min(width, x1))
        x2 = max(0.0, min(width, x2))
        y1 = max(0.0, min(height, y1))
        y2 = max(0.0, min(height, y2))
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        nx = x1 / width
        ny = y1 / height
        nw = max(0.0, (x2 - x1) / width)
        nh = max(0.0, (y2 - y1) / height)
        return [float(page_no), nx, ny, nw, nh]

    def _build_table_from_visual_payload(
        self,
        *,
        table_id: str,
        page_no: int,
        payload: Dict[str, Any],
        item: Dict[str, Any],
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        page_dims: Dict[int, Tuple[float, float]],
        emitted_cells: int,
        source: str = "pdf_mineru_gemini",
    ) -> Tuple[Optional[Dict[str, Any]], int]:
        headers = self._extract_headers_from_table_payload(payload)
        rows = self._extract_rows_from_table_payload(payload)
        if not rows and self.visual_use_table_html_fallback:
            rows = self._matrix_from_html_table(str(item.get("table_body_html", "") or ""))
        if not headers and len(rows) >= 2:
            headers = rows[0]
            rows = rows[1:]
        if not headers and rows:
            max_cols = max(len(r) for r in rows)
            headers = [f"col_{i}" for i in range(1, max_cols + 1)]
        headers = [self._normalize_text(x) or f"col_{i}" for i, x in enumerate(headers, start=1)]
        if not headers or not rows:
            return None, emitted_cells

        col_count = min(
            self.table_max_cols,
            max(len(headers), max((len(r) for r in rows), default=0)),
        )
        headers = (headers + [f"col_{i}" for i in range(len(headers) + 1, col_count + 1)])[:col_count]
        row_bbox = self._layout_bbox_to_ref_bbox(page_no=page_no, raw_bbox=item.get("bbox"), page_dims=page_dims)

        raw_rows_payload: List[Dict[str, Any]] = []
        row_index = 1
        for raw_row in rows[: self.table_max_rows]:
            cells_payload: List[Dict[str, Any]] = []
            for col_idx in range(1, col_count + 1):
                if emitted_cells >= self.table_cell_cap:
                    break
                text = self._normalize_text(str(raw_row[col_idx - 1] if col_idx - 1 < len(raw_row) else ""))
                if not text:
                    continue
                ref_id = f"{table_id}_r{row_index}_c{col_idx}"
                self._append_ref(parts, bbox_map, ref_id, text, row_bbox)
                cells_payload.append(
                    {
                        "col_index": col_idx,
                        "text": text,
                        "ref_id": ref_id,
                        "bbox": row_bbox,
                    }
                )
                emitted_cells += 1
            if cells_payload:
                raw_rows_payload.append({"row_index": row_index, "cells": cells_payload})
                row_index += 1
            if emitted_cells >= self.table_cell_cap:
                break

        if not raw_rows_payload:
            return None, emitted_cells
        data_rows = self._decorate_rows_with_meta(raw_rows_payload, headers)
        if len(data_rows) < self.ocr_table_min_rows:
            if len(data_rows) != 1:
                return None, emitted_cells
            first_cells = data_rows[0].get("cells", [])
            numeric_hits = sum(
                1
                for c in first_cells
                if c.get("numeric_value") is not None or re.search(r"\d", str(c.get("text", "")))
            )
            if len(first_cells) < 3 or numeric_hits < 2:
                return None, emitted_cells
        if self._looks_like_false_table(headers, data_rows):
            return None, emitted_cells

        confidence = self._to_float_or_none(payload.get("confidence"))
        if confidence is None:
            confidence = 0.72
        confidence = max(0.1, min(1.0, float(confidence)))
        caption = self._normalize_text(
            str(payload.get("caption") or payload.get("title") or " ".join(self._safe_text_list(item.get("caption")))
            )
        )
        notes = self._safe_text_list(payload.get("notes"), max_items=6, max_len=180)
        if not notes:
            notes = self._safe_text_list(item.get("footnote"), max_items=6, max_len=180)

        if caption:
            self._append_ref(parts, bbox_map, f"{table_id}_caption", caption, row_bbox)
        for idx, note in enumerate(notes[:4], start=1):
            self._append_ref(parts, bbox_map, f"{table_id}_note{idx}", note, row_bbox)

        table = {
            "table_id": table_id,
            "source": source,
            "page": page_no,
            "headers": headers,
            "header_meta": self._build_header_meta(headers),
            "rows": data_rows,
            "row_count": len(data_rows),
            "col_count": max((len(r.get("cells", [])) for r in data_rows), default=0),
            "quality": round(confidence, 4),
            "caption": caption,
            "notes": notes,
            "bbox_raw": item.get("bbox"),
            "bbox_norm": row_bbox,
            "image_path": str(item.get("img_path", "") or ""),
            "extraction_mode": "visual_first",
        }
        return table, emitted_cells

    def _build_figure_from_visual_payload(
        self,
        *,
        figure_id: str,
        page_no: int,
        payload: Dict[str, Any],
        item: Dict[str, Any],
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        page_dims: Dict[int, Tuple[float, float]],
        source: str = "pdf_mineru_gemini",
    ) -> Optional[Dict[str, Any]]:
        caption = self._normalize_text(
            str(payload.get("caption") or payload.get("title") or " ".join(self._safe_text_list(item.get("caption"))))
        )
        figure_type = self._normalize_text(str(payload.get("type", "") or ""))
        if figure_type not in {"chart", "diagram", "photo", "other"}:
            figure_type = self._infer_figure_type_from_text(f"{caption} {figure_type}")
        axes = payload.get("axes")
        x_axis = ""
        y_axis = ""
        if isinstance(axes, dict):
            x_axis = self._normalize_text(str(axes.get("x", "") or ""))
            y_axis = self._normalize_text(str(axes.get("y", "") or ""))
        legend = self._safe_text_list(payload.get("legend"), max_items=8, max_len=120)
        insights = self._safe_text_list(payload.get("insights"), max_items=8, max_len=180)
        content_modes = [
            self._normalize_text(str(x or "")).lower()
            for x in (payload.get("content_modes") if isinstance(payload.get("content_modes"), list) else [])
        ]
        content_modes = [x for x in content_modes if x in {"dataframe", "topology", "text", "visual"}]
        if not content_modes:
            content_modes = ["visual"]

        dataframe = payload.get("dataframe") if isinstance(payload.get("dataframe"), dict) else {}
        df_headers = self._normalize_dataframe_headers(dataframe.get("headers"), max_len=120)
        df_rows = self._normalize_dataframe_matrix(dataframe.get("rows"), max_cell_len=160)

        topology = payload.get("topology") if isinstance(payload.get("topology"), dict) else {}
        topo_nodes = topology.get("nodes") if isinstance(topology.get("nodes"), list) else []
        topo_edges = topology.get("edges") if isinstance(topology.get("edges"), list) else []
        text_blocks = self._safe_text_list(payload.get("text_blocks"), max_items=10, max_len=180)
        key_values = self._normalize_figure_key_values(payload.get("key_values"), max_items=6)
        for item_raw in key_values:
            name = self._normalize_text(item_raw.get("name", ""))
            value = self._normalize_text(item_raw.get("value", ""))
            unit = self._normalize_text(item_raw.get("unit", ""))
            if unit:
                insights.append(f"{name}: {value} {unit}".strip())
            else:
                insights.append(f"{name}: {value}".strip())
        df_headers, df_rows, dataframe_source = self._coerce_figure_dataframe(
            headers=df_headers,
            rows=df_rows,
            key_values=key_values,
            fallback_texts=text_blocks + insights,
            x_axis=x_axis,
            y_axis=y_axis,
        )
        if x_axis:
            insights.append(f"x-axis: {x_axis}")
        if y_axis:
            insights.append(f"y-axis: {y_axis}")
        for lg in legend[:4]:
            insights.append(f"legend: {lg}")
        for tb in text_blocks[:3]:
            insights.append(f"text: {tb}")
        if df_headers and df_rows:
            insights.append(f"dataframe: {len(df_rows)}x{max(len(r) for r in df_rows)}")
        if topo_nodes or topo_edges:
            insights.append(f"topology: nodes={len(topo_nodes)}, edges={len(topo_edges)}")
        if (df_headers and df_rows) and "dataframe" not in content_modes:
            content_modes.append("dataframe")
        if (topo_nodes or topo_edges) and "topology" not in content_modes:
            content_modes.append("topology")
        if text_blocks and "text" not in content_modes:
            content_modes.append("text")
        insights = [self._normalize_text(x) for x in insights if self._normalize_text(x)]
        if len(insights) > 8:
            insights = insights[:8]

        if not caption and not insights:
            return None
        confidence = self._to_float_or_none(payload.get("confidence"))
        if confidence is None:
            confidence = 0.68
        confidence = max(0.1, min(1.0, float(confidence)))

        figure_bbox = self._layout_bbox_to_ref_bbox(page_no=page_no, raw_bbox=item.get("bbox"), page_dims=page_dims)
        ref_ids: List[str] = []
        if caption:
            cap_ref = f"{figure_id}_caption"
            self._append_ref(parts, bbox_map, cap_ref, caption, figure_bbox)
            ref_ids.append(cap_ref)
        for idx, insight in enumerate(insights[:6], start=1):
            ref_id = f"{figure_id}_k{idx}"
            self._append_ref(parts, bbox_map, ref_id, insight, figure_bbox)
            ref_ids.append(ref_id)
        return {
            "figure_id": figure_id,
            "source": source,
            "page": page_no,
            "figure_type": figure_type or "other",
            "caption": caption,
            "insights": insights[:6],
            "quality": round(confidence, 4),
            "ref_ids": ref_ids,
            "bbox_raw": item.get("bbox"),
            "bbox_norm": figure_bbox,
            "image_path": str(item.get("img_path", "") or ""),
            "content_modes": content_modes,
            "dataframe": {
                "headers": df_headers,
                "rows": df_rows,
            },
            "dataframe_source": dataframe_source,
            "topology": {
                "nodes": topo_nodes[:20],
                "edges": topo_edges[:30],
            },
            "text_blocks": text_blocks[:8],
            "extraction_mode": "visual_first",
        }

    def _extract_headers_from_table_payload(self, payload: Dict[str, Any]) -> List[str]:
        headers = self._safe_text_list(payload.get("headers"), max_items=self.table_max_cols, max_len=200)
        if headers:
            return headers
        header_rows_raw = payload.get("header_rows")
        if not isinstance(header_rows_raw, list):
            return []
        header_rows: List[List[str]] = []
        for row in header_rows_raw[:4]:
            if not isinstance(row, list):
                continue
            vals = [self._normalize_text(str(x or "")) for x in row[: self.table_max_cols]]
            if any(vals):
                header_rows.append(vals)
        if not header_rows:
            return []
        max_cols = max(len(r) for r in header_rows)
        merged: List[str] = []
        for col_idx in range(max_cols):
            parts: List[str] = []
            seen = set()
            for row in header_rows:
                val = self._normalize_text(str(row[col_idx] if col_idx < len(row) else ""))
                if not val:
                    continue
                key = self._normalize_token_for_compare(val)
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                parts.append(val)
            merged.append(" / ".join(parts))
        return [h for h in merged if h]

    def _extract_rows_from_table_payload(self, payload: Dict[str, Any]) -> List[List[str]]:
        rows_raw = payload.get("rows")
        if not isinstance(rows_raw, list):
            return []
        matrix: List[List[str]] = []
        for row in rows_raw[: self.table_max_rows]:
            vals: List[str] = []
            if isinstance(row, list):
                vals = [self._normalize_text(str(x or "")) for x in row[: self.table_max_cols]]
            elif isinstance(row, dict):
                row_cells = row.get("cells")
                if isinstance(row_cells, list):
                    vals = [self._normalize_text(str(x or "")) for x in row_cells[: self.table_max_cols]]
                else:
                    keys = [k for k in row.keys() if str(k).lower() not in {"row_index", "id"}]
                    keys.sort()
                    vals = [self._normalize_text(str(row.get(k) or "")) for k in keys[: self.table_max_cols]]
            if any(vals):
                matrix.append(vals)
        return matrix

    def _matrix_from_html_table(self, table_html: str) -> List[List[str]]:
        html = str(table_html or "")
        if not html:
            return []
        row_chunks = re.findall(r"<tr[^>]*>([\s\S]*?)</tr>", html, flags=re.IGNORECASE)
        matrix: List[List[str]] = []
        for row_chunk in row_chunks[: self.table_max_rows + 1]:
            cell_chunks = re.findall(r"<t[dh][^>]*>([\s\S]*?)</t[dh]>", row_chunk, flags=re.IGNORECASE)
            vals: List[str] = []
            for cell in cell_chunks[: self.table_max_cols]:
                text = re.sub(r"<[^>]+>", " ", str(cell or ""))
                text = self._normalize_text(text)
                vals.append(text)
            if any(vals):
                matrix.append(vals)
        return matrix

    def _collect_table_cue_pages(self, reader: PdfReader, page_count: int) -> List[int]:
        limit = min(max(page_count, 0), len(reader.pages))
        if limit <= 0:
            return []

        hits: List[int] = []
        for page_idx in range(limit):
            try:
                raw = reader.pages[page_idx].extract_text() or ""
            except Exception:
                continue
            text = self._normalize_text(raw)
            if not text:
                continue
            if self._looks_like_table_cue_text(text):
                hits.append(page_idx)

        if not hits:
            return []
        if self.ocr_cue_max_pages <= 0 or len(hits) <= self.ocr_cue_max_pages:
            return hits

        if self.ocr_cue_max_pages == 1:
            return [hits[len(hits) // 2]]

        step = (len(hits) - 1) / float(self.ocr_cue_max_pages - 1)
        sampled = [hits[int(round(i * step))] for i in range(self.ocr_cue_max_pages)]
        seen = set()
        out: List[int] = []
        for idx in sampled:
            if idx in seen:
                continue
            seen.add(idx)
            out.append(idx)
        return out

    @staticmethod
    def _looks_like_table_cue_text(text: str) -> bool:
        t = str(text or "")
        if not t:
            return False
        cue_pattern = re.compile(
            r"\btable\b|\btab\.\b|list of tables|table of contents|\bannex\b|\bappendix\b|"
            r"\u9644\u8868|\u8868\s*[A-Za-z0-9\u4e00-\u9fa5]+",
            re.IGNORECASE,
        )
        return bool(cue_pattern.search(t))

    def _is_weak_native_table_result(self, table_blocks: TableBlocks, cue_pages: List[int]) -> bool:
        cue_count = len(cue_pages or [])
        if not table_blocks:
            return cue_count > 0

        table_count = len(table_blocks)
        sources = {str(t.get("source", "")).strip().lower() for t in table_blocks}
        quality_vals: List[float] = []
        for t in table_blocks:
            try:
                q = float(t.get("quality"))
                quality_vals.append(q)
            except (TypeError, ValueError):
                continue
        avg_quality = (sum(quality_vals) / float(len(quality_vals))) if quality_vals else 0.0

        weak_by_count = table_count < self.visual_weak_table_min
        weak_by_quality = bool(quality_vals) and (avg_quality <= self.visual_weak_table_quality)
        fitz_only = bool(sources) and all(src == "pdf_fitz" for src in sources)

        if cue_count >= 20 and table_count <= max(2, self.visual_weak_table_min):
            return True
        if cue_count >= 8 and weak_by_count and fitz_only:
            return True
        if cue_count >= 8 and weak_by_quality and fitz_only:
            return True
        if cue_count >= 12 and weak_by_count and weak_by_quality:
            return True
        return False

    @staticmethod
    def _header_token_is_generic(text: str) -> bool:
        t = str(text or "").strip().lower()
        if not t:
            return True
        return bool(re.fullmatch(r"col[_\s\-]?\d{1,3}", t))

    def _effective_header_tokens(self, table: Dict[str, Any]) -> List[str]:
        tokens: List[str] = []
        header_meta = table.get("header_meta", [])
        if isinstance(header_meta, list) and header_meta:
            for item in header_meta:
                name = self._normalize_text(str(item.get("name", "")))
                if not name:
                    continue
                if self._header_token_is_generic(name) or self._is_page_number_token(name):
                    continue
                tokens.append(name)
        if not tokens:
            for raw in table.get("headers", []):
                name = self._normalize_text(str(raw or ""))
                if not name:
                    continue
                if self._header_token_is_generic(name) or self._is_page_number_token(name):
                    continue
                tokens.append(name)
        return tokens

    def _header_similarity(self, left: List[str], right: List[str]) -> float:
        if not left or not right:
            return 0.0

        l = [self._normalize_token_for_compare(x) for x in left]
        r = [self._normalize_token_for_compare(x) for x in right]
        l = [x for x in l if x]
        r = [x for x in r if x]
        if not l or not r:
            return 0.0

        lset = set(l)
        rset = set(r)
        inter = len(lset & rset)
        union = len(lset | rset)
        jaccard = (inter / float(union)) if union else 0.0

        short, long = (l, r) if len(l) <= len(r) else (r, l)
        order_hit = 0
        for idx, tok in enumerate(short):
            if idx < len(long) and tok == long[idx]:
                order_hit += 1
        order_score = order_hit / float(max(len(short), 1))

        return (0.65 * jaccard) + (0.35 * order_score)

    def _table_col_overlap(self, left: Dict[str, Any], right: Dict[str, Any]) -> float:
        lc = int(left.get("col_count", 0) or 0)
        rc = int(right.get("col_count", 0) or 0)
        if lc <= 0:
            lc = max((len(r.get("cells", [])) for r in left.get("rows", [])), default=0)
        if rc <= 0:
            rc = max((len(r.get("cells", [])) for r in right.get("rows", [])), default=0)
        if lc <= 0 or rc <= 0:
            return 0.0
        return min(lc, rc) / float(max(lc, rc))

    @staticmethod
    def _table_vertical_span(table: Dict[str, Any]) -> Tuple[float, float]:
        y0 = 1.0
        y1 = 0.0
        hit = False
        for row in table.get("rows", []):
            for cell in row.get("cells", []):
                bbox = cell.get("bbox", [])
                if not isinstance(bbox, list) or len(bbox) < 5:
                    continue
                try:
                    y = float(bbox[2])
                    h = float(bbox[4])
                except (TypeError, ValueError):
                    continue
                if h < 0:
                    continue
                y0 = min(y0, y)
                y1 = max(y1, y + h)
                hit = True
        if not hit:
            return 0.0, 1.0
        return max(0.0, min(1.0, y0)), max(0.0, min(1.0, y1))

    @staticmethod
    def _table_row_count(table: Dict[str, Any]) -> int:
        try:
            rv = int(table.get("row_count", 0) or 0)
        except (TypeError, ValueError):
            rv = 0
        if rv > 0:
            return rv
        return len(table.get("rows", []))

    def _should_merge_same_page_tables(self, prev: Dict[str, Any], curr: Dict[str, Any]) -> bool:
        if str(prev.get("source", "")) != str(curr.get("source", "")):
            return False
        p_page = int(prev.get("page", 0) or 0)
        c_page = int(curr.get("page", 0) or 0)
        if p_page <= 0 or c_page <= 0 or p_page != c_page:
            return False

        h_sim = self._header_similarity(self._effective_header_tokens(prev), self._effective_header_tokens(curr))
        col_overlap = self._table_col_overlap(prev, curr)
        if col_overlap < 0.5:
            return False

        p_top, p_bottom = self._table_vertical_span(prev)
        c_top, c_bottom = self._table_vertical_span(curr)
        if c_bottom <= p_top:
            gap = p_top - c_bottom
        elif c_top >= p_bottom:
            gap = c_top - p_bottom
        else:
            gap = 0.0
        if gap > 0.09:
            return False

        continuation = self._table_has_continuation_marker(prev) or self._table_has_continuation_marker(curr)
        tiny_fragment = self._table_row_count(prev) <= 2 or self._table_row_count(curr) <= 2

        if col_overlap >= 0.86 and gap <= 0.035 and (h_sim >= 0.16 or continuation or tiny_fragment):
            return True
        if col_overlap >= 0.74 and gap <= 0.06 and (h_sim >= 0.32 or continuation or tiny_fragment):
            return True
        return False

    def _merge_same_page_tables(self, table_blocks: TableBlocks) -> TableBlocks:
        if not table_blocks:
            return table_blocks
        ordered = sorted(
            table_blocks,
            key=lambda t: (
                int(t.get("page", 0) or 0),
                self._table_vertical_span(t)[0],
                str(t.get("table_id", "")),
            ),
        )
        merged: TableBlocks = []
        for table in ordered:
            if not merged:
                merged.append(table)
                continue
            prev = merged[-1]
            if self._should_merge_same_page_tables(prev, table):
                merged[-1] = self._merge_table_pair(prev, table)
            else:
                merged.append(table)
        return merged

    def _table_has_continuation_marker(self, table: Dict[str, Any]) -> bool:
        headers = [str(h or "").strip().lower() for h in table.get("headers", []) if str(h or "").strip()]
        if not headers:
            return False
        text = " ".join(headers)
        return ("continued" in text) or ("cont." in text) or ("\u7eed\u8868" in text)

    def _extract_table_label(self, table: Dict[str, Any]) -> str:
        headers = [str(h or "").strip() for h in table.get("headers", []) if str(h or "").strip()]
        if not headers:
            return ""
        text = " ".join(headers)
        m = re.search(r"\btable\s+([A-Za-z]?[0-9]+(?:[-.][A-Za-z0-9]+)?)\b", text, re.IGNORECASE)
        if not m:
            return ""
        return m.group(1).lower()

    def _should_merge_tables(self, prev: Dict[str, Any], curr: Dict[str, Any]) -> bool:
        if str(prev.get("source", "")) != str(curr.get("source", "")):
            return False
        p_page = int(prev.get("page", 0) or 0)
        c_page = int(curr.get("page", 0) or 0)
        if p_page <= 0 or c_page <= 0:
            return False
        if c_page < p_page:
            return False

        left_h = self._effective_header_tokens(prev)
        right_h = self._effective_header_tokens(curr)
        h_sim = self._header_similarity(left_h, right_h)
        col_overlap = self._table_col_overlap(prev, curr)
        page_gap = c_page - p_page
        _, p_bottom = self._table_vertical_span(prev)
        c_top, _ = self._table_vertical_span(curr)

        if page_gap <= self.table_merge_max_page_gap:
            if h_sim >= self.table_merge_header_sim and col_overlap >= self.table_merge_col_overlap:
                return True

            continuation = self._table_has_continuation_marker(prev) or self._table_has_continuation_marker(curr)
            if continuation and h_sim >= (self.table_merge_header_sim * 0.75) and col_overlap >= 0.5:
                return True
            if (
                p_bottom >= 0.78
                and c_top <= 0.26
                and col_overlap >= 0.72
            ):
                prev_label = self._extract_table_label(prev)
                curr_label = self._extract_table_label(curr)
                same_label = bool(prev_label and curr_label and prev_label == curr_label)
                if continuation or same_label:
                    return True
                if h_sim >= max(0.58, self.table_merge_header_sim + 0.08):
                    return True
                if self._table_row_count(curr) <= 3 and h_sim >= 0.68:
                    return True

        relaxed_gap = max(self.table_merge_max_page_gap, (self.table_merge_max_page_gap * 4))
        if page_gap <= relaxed_gap and h_sim >= 0.9 and col_overlap >= 0.8:
            return True

        if page_gap <= max(10, relaxed_gap):
            prev_label = self._extract_table_label(prev)
            curr_label = self._extract_table_label(curr)
            if prev_label and curr_label and prev_label == curr_label and col_overlap >= 0.5:
                return True

        return False

    def _merge_table_pair(self, prev: Dict[str, Any], curr: Dict[str, Any]) -> Dict[str, Any]:
        merged = dict(prev)
        prev_rows = prev.get("rows", []) if isinstance(prev.get("rows", []), list) else []
        curr_rows = curr.get("rows", []) if isinstance(curr.get("rows", []), list) else []
        p_page = int(prev.get("page", 0) or 0)
        c_page = int(curr.get("page", 0) or 0)

        if p_page > 0 and c_page > 0 and p_page != c_page:
            prev_headers = [str(h) for h in prev.get("headers", [])]
            if prev_headers:
                curr_rows = self._drop_redundant_header_like_rows(curr_rows, prev_headers)

        out_rows: List[Dict[str, Any]] = []
        row_idx = 1
        for row in (prev_rows + curr_rows):
            cells = row.get("cells", []) if isinstance(row.get("cells", []), list) else []
            cells_out = [dict(c) for c in cells if isinstance(c, dict)]
            if not cells_out:
                continue
            out_rows.append({"row_index": row_idx, "cells": cells_out})
            row_idx += 1

        merged["rows"] = out_rows
        merged["row_count"] = len(out_rows)
        merged["col_count"] = max(
            int(prev.get("col_count", 0) or 0),
            int(curr.get("col_count", 0) or 0),
            max((len(r.get("cells", [])) for r in out_rows), default=0),
        )

        left_h = self._effective_header_tokens(prev)
        right_h = self._effective_header_tokens(curr)
        if len(right_h) > len(left_h):
            merged["headers"] = curr.get("headers", merged.get("headers", []))
            merged["header_meta"] = curr.get("header_meta", merged.get("header_meta", []))

        try:
            q_prev = float(prev.get("quality", 0.0) or 0.0)
        except (TypeError, ValueError):
            q_prev = 0.0
        try:
            q_curr = float(curr.get("quality", 0.0) or 0.0)
        except (TypeError, ValueError):
            q_curr = 0.0
        if (q_prev > 0.0) or (q_curr > 0.0):
            merged["quality"] = round((q_prev + q_curr) / 2.0, 4)

        start = min(x for x in [p_page, c_page] if x > 0) if (p_page > 0 or c_page > 0) else 0
        end = max(p_page, c_page)
        if start > 0 and end >= start:
            merged["page"] = start
            merged["page_span"] = [start, end]

        merged_from = []
        for item in prev.get("merged_from", []):
            if item:
                merged_from.append(str(item))
        prev_id = str(prev.get("table_id", ""))
        curr_id = str(curr.get("table_id", ""))
        if prev_id and prev_id not in merged_from:
            merged_from.append(prev_id)
        if curr_id and curr_id not in merged_from:
            merged_from.append(curr_id)
        if merged_from:
            merged["merged_from"] = merged_from

        return merged

    def _merge_cross_page_tables(self, table_blocks: TableBlocks) -> TableBlocks:
        if not table_blocks:
            return table_blocks
        ordered = sorted(
            table_blocks,
            key=lambda t: (int(t.get("page", 0) or 0), str(t.get("table_id", ""))),
        )
        merged: TableBlocks = []
        for table in ordered:
            if not merged:
                merged.append(table)
                continue
            prev = merged[-1]
            if self._should_merge_tables(prev, table):
                merged[-1] = self._merge_table_pair(prev, table)
            else:
                merged.append(table)
        return merged

    def _parse_pdf_with_ocr(
        self,
        file_bytes: bytes,
        page_count: int,
        cue_pages: List[int] | None = None,
    ) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        try:
            import fitz  # pymupdf
            import numpy as np
        except Exception as exc:
            raise ValueError(
                "VisualTrack OCR backend is unavailable. Install pymupdf and rapidocr-onnxruntime."
            ) from exc

        base_dpi = max(96, int(os.getenv("MODULE2_OCR_DPI", "120")))
        self._runtime_page_count = page_count
        dpi = min(base_dpi, self.ocr_large_doc_dpi) if page_count >= self.ocr_large_doc_page_threshold else base_dpi
        low_dpi = min(dpi, self.ocr_low_priority_dpi)
        min_conf = float(os.getenv("MODULE2_OCR_MIN_CONF", "0.45"))
        mat_high = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        mat_low = fitz.Matrix(low_dpi / 72.0, low_dpi / 72.0)
        engine = self._get_ocr_engine()

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        page_lines: Dict[int, List[str]] = {}
        page_cells: Dict[int, List[Dict[str, Any]]] = {}

        page_indices = self._build_ocr_page_indices(
            page_count=min(page_count, len(doc)),
            cue_pages=cue_pages,
        )
        queue: List[int] = list(page_indices)
        queued = set(queue)
        processed_idx = set()
        dynamic_added = 0
        cue_count = len(cue_pages or [])
        cue_set = {
            int(p)
            for p in (cue_pages or [])
            if isinstance(p, int)
        }
        dense_cue = cue_count >= self.ocr_dense_cue_threshold
        max_attempt_pages: int | None = None
        if dense_cue:
            max_attempt_pages = min(len(queue), self.ocr_max_attempt_pages_dense_cue)
        elif cue_count >= max(40, self.ocr_dense_cue_threshold // 2):
            max_attempt_pages = min(len(queue), self.ocr_max_attempt_pages_mid_cue)
        dynamic_neighbor_budget = self.ocr_dynamic_neighbor_pages
        if dynamic_neighbor_budget <= 0 and self.ocr_dynamic_neighbor_auto_enable and self.ocr_dynamic_neighbor_auto_max > 0:
            if cue_count <= 0:
                if len(queue) <= 72:
                    dynamic_neighbor_budget = min(self.ocr_dynamic_neighbor_auto_max, 8)
                elif len(queue) <= 110:
                    dynamic_neighbor_budget = min(self.ocr_dynamic_neighbor_auto_max, 6)
                else:
                    dynamic_neighbor_budget = min(self.ocr_dynamic_neighbor_auto_max, 4)
            elif cue_count < max(10, self.ocr_dense_cue_threshold // 12):
                dynamic_neighbor_budget = min(self.ocr_dynamic_neighbor_auto_max, 4)
        base_min_pages_before_budget = max(self.ocr_min_pages_before_budget, 3)
        if len(queue) >= 60:
            if cue_count <= 0:
                ratio = 0.60 if self.ocr_low_cue_boost_enable else 0.48
            elif cue_count < 20:
                ratio = 0.42
            else:
                ratio = 0.34
            base_min_pages_before_budget = max(base_min_pages_before_budget, int(round(len(queue) * ratio)))
        elif len(queue) >= 40:
            if cue_count <= 0:
                ratio = 0.54 if self.ocr_low_cue_boost_enable else 0.44
            elif cue_count < 15:
                ratio = 0.38
            else:
                ratio = 0.30
            base_min_pages_before_budget = max(base_min_pages_before_budget, int(round(len(queue) * ratio)))
        if cue_count <= 0 and self.ocr_low_cue_boost_enable:
            base_min_pages_before_budget = min(
                base_min_pages_before_budget,
                min(len(queue), self.ocr_low_cue_min_pages_cap),
            )
        if cue_count >= 80:
            base_min_pages_before_budget = max(base_min_pages_before_budget, 30)
        elif cue_count >= 40:
            base_min_pages_before_budget = max(base_min_pages_before_budget, 26)
        min_pages_before_budget = min(len(queue), base_min_pages_before_budget)
        if cue_count <= 0 and self.ocr_front_scan_pages > 0:
            min_pages_before_budget = max(
                min_pages_before_budget,
                min(len(queue), self.ocr_front_scan_pages),
            )
        adaptive_budget = min(
            self.ocr_time_budget_max_sec,
            max(self.ocr_time_budget_sec, len(queue) * self.ocr_time_budget_per_page),
        )
        effective_guard = self.ocr_budget_guard_ratio
        if cue_count >= 120:
            effective_guard = max(effective_guard, 0.98)
        elif cue_count >= 40:
            effective_guard = max(effective_guard, 0.94)
        budget_cutoff = adaptive_budget * effective_guard
        if cue_count >= 80:
            min_pages_before_budget = min(len(queue), max(min_pages_before_budget, 30))
        start_t = time.perf_counter()
        try:
            attempted_pages = 0
            table_signal_pages = 0
            no_signal_streak = 0
            qpos = 0
            while qpos < len(queue):
                if max_attempt_pages is not None and attempted_pages >= max_attempt_pages:
                    break
                if attempted_pages >= min_pages_before_budget and time.perf_counter() - start_t > budget_cutoff:
                    break
                page_idx = queue[qpos]
                qpos += 1
                if page_idx in processed_idx:
                    continue
                processed_idx.add(page_idx)
                attempted_pages += 1

                page_no = page_idx + 1
                page = doc.load_page(page_idx)
                use_high_dpi = attempted_pages <= self.ocr_high_priority_pages
                if not dense_cue and page_idx in cue_set:
                    use_high_dpi = True
                pix = page.get_pixmap(matrix=(mat_high if use_high_dpi else mat_low), alpha=False)
                raw = np.frombuffer(pix.samples, dtype=np.uint8)
                if pix.n == 1:
                    image = raw.reshape(pix.height, pix.width)
                else:
                    image = raw.reshape(pix.height, pix.width, pix.n)
                    if pix.n > 3:
                        image = image[:, :, :3]

                ocr_result, _ = engine(image)
                if not ocr_result:
                    ref_id = f"p{page_no}_ocr1"
                    placeholder = f"[Page {page_no}] OCR found no text."
                    parts.append(f'<ref id="{ref_id}">{escape(placeholder)}</ref>')
                    bbox_map[ref_id] = [float(page_no), 0.0, 0.0, 1.0, 1.0]
                    continue

                lines: List[str] = []
                item_idx = 1
                for item in ocr_result:
                    if not isinstance(item, (list, tuple)) or len(item) < 3:
                        continue
                    box, text, score = item[0], str(item[1]).strip(), float(item[2] or 0.0)
                    if not text or score < min_conf:
                        continue

                    normalized = self._normalize_text(text)
                    if not normalized:
                        continue

                    ref_id = f"p{page_no}_ocr{item_idx}"
                    parts.append(f'<ref id="{ref_id}">{escape(normalized)}</ref>')
                    x, y, w, h = self._normalize_box(box, pix.width, pix.height)
                    bbox_map[ref_id] = [float(page_no), x, y, w, h]
                    lines.append(normalized)
                    page_cells.setdefault(page_no, []).append(
                        {
                            "ref_id": ref_id,
                            "text": normalized,
                            "bbox": [float(page_no), x, y, w, h],
                            "x_center": x + (w / 2.0),
                            "y_center": y + (h / 2.0),
                        }
                    )
                    item_idx += 1

                has_table_cue = False
                has_numeric_table_rows = False
                if lines:
                    page_lines[page_no] = lines
                    cue_text = " ".join(lines[:48])
                    has_table_cue = self._looks_like_table_cue_text(cue_text)
                    numeric_row_hits = 0
                    for line in lines[:40]:
                        digit_hits = sum(1 for ch in line if ch.isdigit())
                        if digit_hits >= 2:
                            numeric_row_hits += 1
                        if numeric_row_hits >= 3:
                            break
                    has_numeric_table_rows = numeric_row_hits >= 3
                    if dynamic_neighbor_budget > 0 and dynamic_added < dynamic_neighbor_budget:
                        cells_cur = page_cells.get(page_no, [])
                        top_dense = sum(1 for c in cells_cur if float(c.get("y_center", 0.0)) <= 0.14) >= 3
                        bottom_dense = sum(1 for c in cells_cur if float(c.get("y_center", 0.0)) >= 0.86) >= 3
                        if has_table_cue or has_numeric_table_rows or top_dense or bottom_dense:
                            neighbor_order: List[int] = []
                            if bottom_dense:
                                neighbor_order.append(page_idx + 1)
                            if top_dense:
                                neighbor_order.append(page_idx - 1)
                            if not neighbor_order:
                                neighbor_order = [page_idx + 1, page_idx - 1]
                            for cand in neighbor_order:
                                if dynamic_added >= dynamic_neighbor_budget:
                                    break
                                if 0 <= cand < len(doc) and cand not in queued and cand not in processed_idx:
                                    queue.append(cand)
                                    queued.add(cand)
                                    dynamic_added += 1
                has_signal = has_table_cue or has_numeric_table_rows
                if has_signal:
                    table_signal_pages += 1
                    no_signal_streak = 0
                else:
                    no_signal_streak += 1
                if attempted_pages >= 3:
                    elapsed = time.perf_counter() - start_t
                    avg_page_sec = elapsed / float(max(attempted_pages, 1))
                    if attempted_pages >= min_pages_before_budget and elapsed + avg_page_sec > budget_cutoff:
                        break
                    if (
                        self.ocr_dynamic_early_stop_enable
                        and cue_count >= max(40, self.ocr_dense_cue_threshold // 2)
                        and attempted_pages >= max(min_pages_before_budget, self.ocr_dynamic_early_stop_min_pages)
                        and table_signal_pages >= self.ocr_dynamic_early_stop_min_signal_pages
                        and no_signal_streak >= self.ocr_dynamic_early_stop_streak
                    ):
                        break
        finally:
            doc.close()

        if not parts:
            raise ValueError(
                "VisualTrack OCR completed but no text was extracted. "
                "Try increasing MODULE2_OCR_MAX_PAGES or MODULE2_OCR_TIME_BUDGET_SEC."
            )

        enable_relaxed_second_pass = cue_count <= max(40, self.ocr_dense_cue_threshold // 2)
        table_blocks = self._infer_tables_from_ocr_cells(
            page_cells,
            enable_relaxed_second_pass=enable_relaxed_second_pass,
        )
        if (
            page_cells
            and len(table_blocks) < self.ocr_relaxed_trigger_table_count
            and self.ocr_table_relaxed_min_quality < self.ocr_table_min_quality
        ):
            relaxed_tables = self._infer_tables_from_ocr_cells(
                page_cells,
                min_quality=self.ocr_table_relaxed_min_quality,
                enable_relaxed_second_pass=enable_relaxed_second_pass,
            )
            if table_blocks:
                table_blocks = self._augment_with_line_tables(table_blocks, relaxed_tables)
            else:
                table_blocks = relaxed_tables
        need_line_aug = self._need_line_table_augmentation(table_blocks, page_lines)
        if not table_blocks or need_line_aug:
            aug_lines = self._select_line_augmentation_pages(page_lines, table_blocks, cue_pages=cue_pages)
            line_tables = self._infer_tables_from_page_lines(aug_lines, parts, bbox_map, source="pdf_ocr_line")
            if table_blocks:
                table_blocks = self._augment_with_line_tables(table_blocks, line_tables)
            else:
                table_blocks = line_tables
        if table_blocks and self.ocr_uncovered_line_aug_pages > 0:
            aggressive_uncovered = (cue_count <= 0) and (len(table_blocks) < 40)
            uncovered_lines = self._select_uncovered_table_like_pages(
                page_lines,
                table_blocks,
                aggressive=aggressive_uncovered,
            )
            if uncovered_lines:
                uncovered_tables = self._infer_tables_from_page_lines(
                    uncovered_lines,
                    parts,
                    bbox_map,
                    source="pdf_ocr_line_extra",
                )
                table_blocks = self._augment_with_line_tables(table_blocks, uncovered_tables)

        figure_blocks = self._infer_figures_from_page_lines(
            page_lines=page_lines,
            parts=parts,
            bbox_map=bbox_map,
            source_prefix="pdf_ocr_caption",
        )

        table_blocks, vision_figures = self._enhance_low_quality_pages_with_gemini_vision(
            file_bytes=file_bytes,
            filetype="pdf",
            page_lines=page_lines,
            table_blocks=table_blocks,
            parts=parts,
            bbox_map=bbox_map,
            source_prefix="pdf_gemini_vision",
        )
        if vision_figures:
            figure_blocks = self._merge_figure_blocks(figure_blocks, vision_figures)
        table_blocks = self._prune_fragment_tables(table_blocks)
        self._last_figure_blocks = figure_blocks
        return "\n".join(parts), bbox_map, table_blocks

    @classmethod
    def _get_ocr_engine(cls):
        if cls._ocr_engine is None:
            if cls._ocr_engine_init_error:
                raise RuntimeError(cls._ocr_engine_init_error)

            timeout_sec = max(2.0, float(os.getenv("MODULE2_OCR_ENGINE_INIT_TIMEOUT_SEC", "15")))

            def _build_engine():
                from rapidocr_onnxruntime import RapidOCR

                return RapidOCR()

            executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
            future = executor.submit(_build_engine)
            try:
                cls._ocr_engine = future.result(timeout=timeout_sec)
            except Exception as exc:
                future.cancel()
                executor.shutdown(wait=False, cancel_futures=True)
                cls._ocr_engine_init_error = (
                    f"OCR engine init failed within {timeout_sec:.1f}s: {type(exc).__name__}: {exc}"
                )
                raise RuntimeError(cls._ocr_engine_init_error) from exc
            executor.shutdown(wait=False, cancel_futures=True)
        return cls._ocr_engine

    @staticmethod
    def _normalize_box(box: object, width: int, height: int) -> Tuple[float, float, float, float]:
        if not isinstance(box, (list, tuple)) or not box:
            return 0.0, 0.0, 1.0, 1.0

        points: List[Tuple[float, float]] = []
        for p in box:
            if isinstance(p, (list, tuple)) and len(p) >= 2:
                try:
                    points.append((float(p[0]), float(p[1])))
                except (TypeError, ValueError):
                    continue

        if not points:
            return 0.0, 0.0, 1.0, 1.0

        x0 = max(0.0, min(pt[0] for pt in points)) / max(width, 1)
        y0 = max(0.0, min(pt[1] for pt in points)) / max(height, 1)
        x1 = max(0.0, max(pt[0] for pt in points)) / max(width, 1)
        y1 = max(0.0, max(pt[1] for pt in points)) / max(height, 1)
        return x0, y0, max(0.0, x1 - x0), max(0.0, y1 - y0)

    def _parse_docx(self, file_bytes: bytes) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        from docx import Document

        try:
            doc = Document(io.BytesIO(file_bytes))
        except Exception:
            # Fallback for partially broken DOCX archives (e.g. missing footnotes.xml)
            return self._parse_docx_relaxed(file_bytes)
        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        table_blocks: TableBlocks = []
        figure_blocks: FigureBlocks = []
        ref_idx = 1

        for para in doc.paragraphs:
            text = self._normalize_text(para.text or "")
            if not text:
                continue
            ref_id = f"docx_{ref_idx}"
            parts.append(f'<ref id="{ref_id}">{escape(text)}</ref>')
            bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]
            ref_idx += 1

        for table_idx, table in enumerate(doc.tables, start=1):
            table_id = f"docx_t{table_idx}"
            rows_payload: List[Dict[str, Any]] = []
            for row_idx, row in enumerate(table.rows[: self.table_max_rows], start=1):
                cells_payload: List[Dict[str, Any]] = []
                for col_idx, cell in enumerate(row.cells[: self.table_max_cols], start=1):
                    cell_text = self._normalize_text(cell.text or "")
                    cell_ref = None
                    bbox = [1.0, 0.0, 0.0, 1.0, 1.0]
                    if cell_text:
                        cell_ref = f"{table_id}_r{row_idx}_c{col_idx}"
                        parts.append(f'<ref id="{cell_ref}">{escape(cell_text)}</ref>')
                        bbox_map[cell_ref] = bbox
                    cells_payload.append(
                        {
                            "col_index": col_idx,
                            "text": cell_text,
                            "ref_id": cell_ref,
                            "bbox": bbox,
                        }
                    )
                if any(cell.get("text") for cell in cells_payload):
                    rows_payload.append({"row_index": row_idx, "cells": cells_payload})

            if not rows_payload:
                continue

            headers, data_rows = self._infer_headers_and_data_rows(rows_payload)
            data_rows = self._drop_redundant_header_like_rows(data_rows, headers)
            data_rows = self._decorate_rows_with_meta(data_rows, headers)
            if not data_rows:
                continue

            table_blocks.append(
                {
                    "table_id": table_id,
                    "source": "docx",
                    "page": 1,
                    "headers": headers,
                    "header_meta": self._build_header_meta(headers),
                    "rows": data_rows,
                    "row_count": len(data_rows),
                    "col_count": max((len(r.get("cells", [])) for r in data_rows), default=0),
                }
            )

        extra_figures, extra_tables, docx_stats, ref_idx = self._extract_docx_chart_and_media(
            file_bytes=file_bytes,
            parts=parts,
            bbox_map=bbox_map,
            start_ref_idx=ref_idx,
        )
        if extra_tables:
            table_blocks.extend(extra_tables)
        if extra_figures:
            figure_blocks.extend(extra_figures[: self.nonpdf_figure_max])

        self._last_parse_stats = dict(docx_stats)
        self._last_figure_blocks = self._merge_figure_blocks([], figure_blocks)
        if not parts:
            raise ValueError("DOCX contains no extractable text.")
        return "\n".join(parts), bbox_map, table_blocks

    def _parse_docx_relaxed(self, file_bytes: bytes) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        table_blocks: TableBlocks = []
        ref_idx = 1
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                raw_xml = zf.read("word/document.xml")
        except Exception as exc:
            raise ValueError(f"DOCX fallback parsing failed: {exc}") from exc

        try:
            root = ET.fromstring(raw_xml)
        except Exception as exc:
            raise ValueError(f"DOCX XML decode failed: {exc}") from exc

        for para in root.findall(".//w:p", ns):
            tokens = [self._normalize_text(str(node.text or "")) for node in para.findall(".//w:t", ns)]
            text = self._normalize_text("".join(tok for tok in tokens if tok))
            if not text:
                continue
            ref_id = f"docx_relaxed_{ref_idx}"
            parts.append(f'<ref id="{ref_id}">{escape(text)}</ref>')
            bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]
            ref_idx += 1

        for table_idx, table in enumerate(root.findall(".//w:tbl", ns), start=1):
            table_id = f"docx_relaxed_t{table_idx}"
            rows_payload: List[Dict[str, Any]] = []
            rows = table.findall("./w:tr", ns)[: self.table_max_rows]
            for row_idx, row in enumerate(rows, start=1):
                cells_payload: List[Dict[str, Any]] = []
                cells = row.findall("./w:tc", ns)[: self.table_max_cols]
                for col_idx, cell in enumerate(cells, start=1):
                    cell_tokens = [self._normalize_text(str(node.text or "")) for node in cell.findall(".//w:t", ns)]
                    cell_text = self._normalize_text("".join(tok for tok in cell_tokens if tok))
                    cell_ref = None
                    bbox = [1.0, 0.0, 0.0, 1.0, 1.0]
                    if cell_text:
                        cell_ref = f"{table_id}_r{row_idx}_c{col_idx}"
                        parts.append(f'<ref id="{cell_ref}">{escape(cell_text)}</ref>')
                        bbox_map[cell_ref] = bbox
                    cells_payload.append(
                        {
                            "col_index": col_idx,
                            "text": cell_text,
                            "ref_id": cell_ref,
                            "bbox": bbox,
                        }
                    )
                if any(cell.get("text") for cell in cells_payload):
                    rows_payload.append({"row_index": row_idx, "cells": cells_payload})

            if not rows_payload:
                continue
            headers, data_rows = self._infer_headers_and_data_rows(rows_payload)
            data_rows = self._drop_redundant_header_like_rows(data_rows, headers)
            data_rows = self._decorate_rows_with_meta(data_rows, headers)
            if not data_rows:
                continue
            table_blocks.append(
                {
                    "table_id": table_id,
                    "source": "docx_relaxed",
                    "page": 1,
                    "headers": headers,
                    "header_meta": self._build_header_meta(headers),
                    "rows": data_rows,
                    "row_count": len(data_rows),
                    "col_count": max((len(r.get("cells", [])) for r in data_rows), default=0),
                }
            )

        if not parts:
            ref_id = "docx_relaxed_empty"
            msg = "文档未识别到可提取正文，可能为图片版或仅包含对象元素。"
            parts.append(f'<ref id="{ref_id}">{escape(msg)}</ref>')
            bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]

        self._last_parse_stats = {"docx_relaxed_mode": True}
        self._last_figure_blocks = []
        return "\n".join(parts), bbox_map, table_blocks

    def _extract_docx_chart_and_media(
        self,
        file_bytes: bytes,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        start_ref_idx: int,
    ) -> Tuple[FigureBlocks, TableBlocks, Dict[str, Any], int]:
        figures: FigureBlocks = []
        table_blocks: TableBlocks = []
        stats: Dict[str, Any] = {
            "docx_chart_xml_seen": 0,
            "docx_chart_xml_parsed": 0,
            "docx_media_seen": 0,
            "docx_media_used": 0,
            "docx_media_parsed": 0,
            "docx_media_parse_errors": 0,
            "docx_media_skipped_duplicate": 0,
            "docx_media_vision_enabled": bool(self.docx_media_vision_enable),
        }
        ref_idx = start_ref_idx
        if not (self.docx_chart_xml_enable or self.docx_media_probe_enable):
            return figures, table_blocks, stats, ref_idx

        try:
            zf = zipfile.ZipFile(io.BytesIO(file_bytes))
        except Exception:
            return figures, table_blocks, stats, ref_idx

        with zf:
            names = zf.namelist()
            chart_files = sorted(
                [name for name in names if name.startswith("word/charts/") and name.endswith(".xml")]
            )
            stats["docx_chart_xml_seen"] = len(chart_files)

            if self.docx_chart_xml_enable and chart_files:
                ns = {
                    "c": "http://schemas.openxmlformats.org/drawingml/2006/chart",
                    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
                }
                chart_max_series = max(2, int(os.getenv("MODULE2_DOCX_CHART_XML_MAX_SERIES", "10")))
                chart_max_points = max(6, int(os.getenv("MODULE2_DOCX_CHART_XML_MAX_POINTS", "40")))
                chart_max_key_points = max(4, int(os.getenv("MODULE2_DOCX_CHART_XML_MAX_KEYPOINTS", "12")))
                chart_table_max_rows = max(24, int(os.getenv("MODULE2_DOCX_CHART_XML_TABLE_MAX_ROWS", "220")))
                stats["docx_chart_xml_table_count"] = 0
                for chart_idx, chart_path in enumerate(chart_files, start=1):
                    if self.nonpdf_figure_max > 0 and len(figures) >= self.nonpdf_figure_max:
                        break
                    try:
                        root = ET.fromstring(zf.read(chart_path))
                    except Exception:
                        continue

                    title_tokens = [
                        self._normalize_text(str(node.text or ""))
                        for node in root.findall(".//c:title//a:t", ns)
                    ]
                    title = self._normalize_text(" ".join(x for x in title_tokens if x))
                    if not title:
                        title = f"DOCX图表 {chart_idx}"

                    series_payload = self._extract_docx_chart_series_payload(
                        root=root,
                        ns=ns,
                        max_series=chart_max_series,
                        max_points=chart_max_points,
                    )
                    key_points = self._build_docx_chart_key_points(
                        series_payload=series_payload,
                        max_items=chart_max_key_points,
                    )

                    summary = f"{title}。"
                    if key_points:
                        summary += " 关键数据：" + "；".join(key_points[:6])

                    ref_id = f"docx_chart_{chart_idx}"
                    parts.append(f'<ref id="{ref_id}">{escape(summary)}</ref>')
                    bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]

                    figures.append(
                        {
                            "figure_id": f"docx_chart_f{chart_idx}",
                            "source": "docx_chart_xml",
                            "page": 1,
                            "figure_type": "chart",
                            "caption": title,
                            "key_points": key_points,
                            "quality": 0.9,
                            "ref_ids": [ref_id],
                            "bbox_norm": [0.0, 0.0, 1.0, 1.0],
                        }
                    )
                    chart_table = self._build_docx_chart_table_block(
                        chart_idx=chart_idx,
                        title=title,
                        series_payload=series_payload,
                        parts=parts,
                        bbox_map=bbox_map,
                        max_rows=chart_table_max_rows,
                    )
                    if chart_table:
                        table_blocks.append(chart_table)
                        stats["docx_chart_xml_table_count"] = int(stats.get("docx_chart_xml_table_count", 0)) + 1
                    stats["docx_chart_xml_parsed"] += 1

            media_files_all = sorted(
                [
                    name
                    for name in names
                    if name.startswith("word/media/")
                    and os.path.splitext(name.lower())[1] in IMAGE_EXTENSIONS
                ]
            )
            stats["docx_media_seen"] = len(media_files_all)
            if self.docx_media_probe_enable and self.docx_media_max_assets > 0 and media_files_all:
                media_candidates: List[Dict[str, Any]] = []
                for media_path in media_files_all:
                    media_name = os.path.basename(media_path)
                    media_size = 0
                    try:
                        media_size = max(0, int(zf.getinfo(media_path).file_size))
                    except Exception:
                        media_size = 0
                    media_candidates.append(
                        {
                            "path": media_path,
                            "name": media_name,
                            "size": media_size,
                            "is_chart_cue": bool(self._looks_like_figure_cue_text(media_name)),
                        }
                    )

                chart_cue_seen = sum(1 for item in media_candidates if bool(item.get("is_chart_cue")))
                stats["docx_media_chart_cue_seen"] = int(chart_cue_seen)

                # Prefer chart-like names first, then larger images (often key tables/charts),
                # instead of lexical filename order (image1, image10, image100...).
                media_candidates.sort(
                    key=lambda item: (
                        0 if bool(item.get("is_chart_cue")) else 1,
                        -int(item.get("size") or 0),
                        str(item.get("path") or ""),
                    )
                )
                media_files = media_candidates[: self.docx_media_max_assets]
                stats["docx_media_selected"] = len(media_files)
                stats["docx_media_selected_strategy"] = "chart_cue_then_size"

                # If chart-only mode is enabled but filenames have no chart cues (common in Word: image1.png),
                # allow a bounded fallback on selected high-priority assets to avoid zero vision coverage.
                allow_noncue_vision_fallback = bool(
                    self.docx_media_vision_chart_only
                    and chart_cue_seen == 0
                    and self.docx_media_vision_allow_noncue
                )
                stats["docx_media_vision_noncue_fallback"] = bool(allow_noncue_vision_fallback)

                seen_sha256: set[str] = set()
                vision_attempted = 0
                saved_last_figures = self.get_last_figure_blocks()
                for media_idx, media_item in enumerate(media_files, start=1):
                    if self.nonpdf_figure_max > 0 and len(figures) >= self.nonpdf_figure_max:
                        break
                    media_path = str(media_item.get("path") or "")
                    media_name = str(media_item.get("name") or os.path.basename(media_path))
                    media_type = "chart" if bool(media_item.get("is_chart_cue")) else "photo"
                    caption = f"DOCX内嵌图像 {media_name}"
                    try:
                        media_bytes = zf.read(media_path)
                    except Exception:
                        media_bytes = b""
                    media_size = len(media_bytes)
                    artifact_path = self._persist_docx_media_artifact(
                        media_bytes=media_bytes,
                        media_name=media_name,
                        media_idx=media_idx,
                    )
                    if media_bytes:
                        media_sha = hashlib.sha256(media_bytes).hexdigest()
                        if media_sha in seen_sha256:
                            stats["docx_media_skipped_duplicate"] += 1
                            continue
                        seen_sha256.add(media_sha)
                    parsed_from_media = False
                    if (
                        self.docx_media_vision_enable
                        and media_bytes
                        and media_size <= self.docx_media_vision_max_bytes
                        and vision_attempted < self.docx_media_vision_max_assets
                        and (
                            (not self.docx_media_vision_chart_only)
                            or (media_type == "chart")
                            or allow_noncue_vision_fallback
                        )
                    ):
                        vision_attempted += 1
                        try:
                            _vision_md, _vision_bbox, _vision_tables = self._parse_image(
                                file_name=media_name,
                                file_bytes=media_bytes,
                            )
                            vision_figures = self.get_last_figure_blocks()
                            if _vision_tables:
                                for t_idx, table in enumerate(_vision_tables[:2], start=1):
                                    copied = dict(table)
                                    copied["table_id"] = f"docx_media_t{media_idx}_{t_idx}"
                                    copied["source"] = "docx_media_vision"
                                    copied["page"] = 1
                                    copied["artifact_path"] = artifact_path or copied.get("artifact_path")
                                    table_blocks.append(copied)
                            if vision_figures:
                                best = max(
                                    vision_figures,
                                    key=lambda x: float(x.get("quality", 0.0) or 0.0),
                                )
                                best_caption = self._normalize_text(str(best.get("caption", "") or "")) or caption
                                points = self._safe_text_list(best.get("key_points") or best.get("insights"), max_items=6, max_len=160)
                                content_modes = [
                                    self._normalize_text(str(x or "")).lower()
                                    for x in (best.get("content_modes") if isinstance(best.get("content_modes"), list) else [])
                                ]
                                content_modes = [x for x in content_modes if x in {"dataframe", "topology", "text", "visual"}]
                                dataframe_raw = best.get("dataframe") if isinstance(best.get("dataframe"), dict) else {}
                                df_headers = self._normalize_dataframe_headers(dataframe_raw.get("headers"), max_len=120)
                                df_rows = self._normalize_dataframe_matrix(dataframe_raw.get("rows"), max_cell_len=160)
                                topology_raw = best.get("topology") if isinstance(best.get("topology"), dict) else {}
                                topo_nodes_raw = topology_raw.get("nodes") if isinstance(topology_raw.get("nodes"), list) else []
                                topo_edges_raw = topology_raw.get("edges") if isinstance(topology_raw.get("edges"), list) else []
                                topo_nodes: List[Dict[str, str]] = []
                                topo_edges: List[Dict[str, str]] = []
                                for node in topo_nodes_raw[:20]:
                                    if not isinstance(node, dict):
                                        continue
                                    topo_nodes.append(
                                        {
                                            "id": self._normalize_text(str(node.get("id", "") or "")),
                                            "label": self._normalize_text(str(node.get("label", "") or "")),
                                            "type": self._normalize_text(str(node.get("type", "") or "")),
                                        }
                                    )
                                for edge in topo_edges_raw[:30]:
                                    if not isinstance(edge, dict):
                                        continue
                                    topo_edges.append(
                                        {
                                            "source": self._normalize_text(str(edge.get("source", "") or "")),
                                            "target": self._normalize_text(str(edge.get("target", "") or "")),
                                            "label": self._normalize_text(str(edge.get("label", "") or "")),
                                        }
                                    )
                                text_blocks = self._safe_text_list(best.get("text_blocks"), max_items=8, max_len=180)
                                if df_headers and df_rows and "dataframe" not in content_modes:
                                    content_modes.append("dataframe")
                                if (topo_nodes or topo_edges) and "topology" not in content_modes:
                                    content_modes.append("topology")
                                if text_blocks and "text" not in content_modes:
                                    content_modes.append("text")
                                if not content_modes:
                                    content_modes = ["visual"]
                                ref_id = f"docx_media_{media_idx}_vision"
                                summary = best_caption
                                if points:
                                    summary = f"{summary}；" + "；".join(points[:3])
                                parts.append(f'<ref id="{ref_id}">{escape(summary)}</ref>')
                                bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]
                                figures.append(
                                    {
                                        "figure_id": f"docx_media_f{media_idx}",
                                        "source": "docx_media_vision",
                                        "page": 1,
                                        "figure_type": str(best.get("figure_type") or media_type),
                                        "caption": best_caption,
                                        "key_points": points,
                                        "quality": max(0.7, float(best.get("quality", 0.7) or 0.7)),
                                        "ref_ids": [ref_id],
                                        "bbox_norm": [0.0, 0.0, 1.0, 1.0],
                                        "artifact_path": artifact_path,
                                        "content_modes": content_modes[:4],
                                        "dataframe": {
                                            "headers": df_headers,
                                            "rows": df_rows,
                                        },
                                        "topology": {
                                            "nodes": topo_nodes,
                                            "edges": topo_edges,
                                        },
                                        "text_blocks": text_blocks[:8],
                                    }
                                )
                                stats["docx_media_used"] += 1
                                stats["docx_media_parsed"] += 1
                                ref_idx += 1
                                parsed_from_media = True
                        except Exception:
                            stats["docx_media_parse_errors"] += 1
                        finally:
                            self._last_figure_blocks = saved_last_figures
                    if parsed_from_media:
                        continue

                    ref_id = f"docx_media_{media_idx}"
                    probe_text = f"{caption}（大小 {round(media_size / 1024.0, 1)}KB）"
                    parts.append(f'<ref id="{ref_id}">{escape(probe_text)}</ref>')
                    bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]

                    figures.append(
                        {
                            "figure_id": f"docx_media_f{media_idx}",
                            "source": "docx_media",
                            "page": 1,
                            "figure_type": media_type,
                            "caption": caption,
                            "key_points": [probe_text],
                            "quality": 0.6,
                            "ref_ids": [ref_id],
                            "bbox_norm": [0.0, 0.0, 1.0, 1.0],
                            "artifact_path": artifact_path,
                        }
                    )
                    stats["docx_media_used"] += 1
                    ref_idx += 1

        return figures, table_blocks, stats, ref_idx

    def _collect_docx_chart_points(
        self,
        ser: ET.Element,
        ns: Dict[str, str],
        node_paths: List[str],
        max_points: int,
    ) -> List[str]:
        points: List[str] = []
        limit = max(1, int(max_points or 1))
        for node_path in node_paths:
            for node in ser.findall(f".//{node_path}//c:v", ns) + ser.findall(f".//{node_path}//a:t", ns):
                text = self._normalize_text(str(node.text or ""))
                if not text:
                    continue
                if points and points[-1] == text:
                    continue
                points.append(text)
                if len(points) >= limit:
                    return points
        return points

    def _extract_docx_chart_series_payload(
        self,
        *,
        root: ET.Element,
        ns: Dict[str, str],
        max_series: int,
        max_points: int,
    ) -> List[Dict[str, Any]]:
        payload: List[Dict[str, Any]] = []
        series_nodes = root.findall(".//c:ser", ns)
        for series_idx, ser in enumerate(series_nodes[: max(1, max_series)], start=1):
            name_tokens = [
                self._normalize_text(str(node.text or ""))
                for node in (ser.findall(".//c:tx//c:v", ns) + ser.findall(".//c:tx//a:t", ns))
            ]
            series_name = self._normalize_text(" ".join(x for x in name_tokens if x))
            if not series_name:
                series_name = f"序列{series_idx}"

            categories = self._collect_docx_chart_points(ser, ns, ["c:cat", "c:xVal"], max_points=max_points)
            values = self._collect_docx_chart_points(ser, ns, ["c:val", "c:yVal", "c:bubbleSize"], max_points=max_points)

            if not categories and values:
                categories = [f"点{idx + 1}" for idx in range(len(values))]
            if not values and not categories:
                continue
            payload.append(
                {
                    "name": series_name,
                    "categories": categories[:max_points],
                    "values": values[:max_points],
                }
            )
        return payload

    def _build_docx_chart_key_points(self, *, series_payload: List[Dict[str, Any]], max_items: int) -> List[str]:
        key_points: List[str] = []
        for item in series_payload:
            series_name = self._normalize_text(str(item.get("name") or "序列"))
            categories = [self._normalize_text(str(x or "")) for x in (item.get("categories") or [])]
            values = [self._normalize_text(str(x or "")) for x in (item.get("values") or [])]
            categories = [x for x in categories if x]
            values = [x for x in values if x]
            if values and categories:
                paired = ", ".join(f"{categories[i]}={values[i]}" for i in range(min(4, len(categories), len(values))))
                text = f"{series_name}: {paired}"
            elif values:
                text = f"{series_name}: {', '.join(values[:4])}"
            elif categories:
                text = f"{series_name}: {', '.join(categories[:4])}"
            else:
                continue
            text = self._normalize_text(text)
            if text:
                key_points.append(text)
            if len(key_points) >= max(1, int(max_items or 1)):
                break
        return key_points

    def _build_docx_chart_table_block(
        self,
        *,
        chart_idx: int,
        title: str,
        series_payload: List[Dict[str, Any]],
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        max_rows: int,
    ) -> Optional[Dict[str, Any]]:
        if not series_payload:
            return None

        headers = ["序列", "类别", "数值"]
        rows_payload: List[Dict[str, Any]] = []
        row_idx = 1
        limit = max(12, int(max_rows or 12))

        for series_idx, item in enumerate(series_payload, start=1):
            series_name = self._normalize_text(str(item.get("name") or f"序列{series_idx}"))
            categories = [self._normalize_text(str(x or "")) for x in (item.get("categories") or [])]
            values = [self._normalize_text(str(x or "")) for x in (item.get("values") or [])]
            point_count = max(len(categories), len(values))
            if point_count <= 0:
                continue
            for point_idx in range(point_count):
                if len(rows_payload) >= limit:
                    break
                category = categories[point_idx] if point_idx < len(categories) and categories[point_idx] else f"点{point_idx + 1}"
                value = values[point_idx] if point_idx < len(values) else ""
                cells_payload: List[Dict[str, Any]] = []
                for col_idx, cell_text in enumerate([series_name, category, value], start=1):
                    normalized = self._normalize_text(str(cell_text or ""))
                    cell_ref = None
                    bbox = [1.0, 0.0, 0.0, 1.0, 1.0]
                    if normalized:
                        cell_ref = f"docx_chart_t{chart_idx}_r{row_idx}_c{col_idx}"
                        parts.append(f'<ref id="{cell_ref}">{escape(normalized)}</ref>')
                        bbox_map[cell_ref] = bbox
                    cells_payload.append(
                        {
                            "col_index": col_idx,
                            "text": normalized,
                            "ref_id": cell_ref,
                            "bbox": bbox,
                        }
                    )
                if any(str(cell.get("text", "")).strip() for cell in cells_payload):
                    rows_payload.append({"row_index": row_idx, "cells": cells_payload})
                    row_idx += 1
            if len(rows_payload) >= limit:
                break

        if not rows_payload:
            return None

        decorated_rows = self._decorate_rows_with_meta(rows_payload, headers)
        if not decorated_rows:
            return None

        return {
            "table_id": f"docx_chart_t{chart_idx}",
            "source": "docx_chart_xml",
            "page": 1,
            "headers": headers,
            "header_meta": self._build_header_meta(headers),
            "rows": decorated_rows,
            "row_count": len(decorated_rows),
            "col_count": max((len(r.get("cells", [])) for r in decorated_rows), default=0),
            "chart_title": self._normalize_text(title),
        }

    def _persist_docx_media_artifact(
        self,
        *,
        media_bytes: bytes,
        media_name: str,
        media_idx: int,
    ) -> str:
        if not media_bytes:
            return ""
        ext = Path(media_name or "").suffix.lower()
        if ext not in IMAGE_EXTENSIONS:
            ext = ".png"
        safe_stem = re.sub(r"[^a-zA-Z0-9_\-]+", "_", Path(media_name or "").stem or f"media_{media_idx}")
        digest = hashlib.sha256(media_bytes).hexdigest()[:16]
        rel = Path("docx_media") / f"{safe_stem}_{media_idx}_{digest}{ext}"
        target = (self.artifact_root_dir / rel).resolve()
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(media_bytes)
            return str(target)
        except Exception:
            return ""

    def _parse_xlsx(self, file_bytes: bytes) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        from openpyxl import load_workbook

        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        table_blocks: TableBlocks = []
        emitted_cells = 0
        used_zip_fallback = False

        def _xlsx_bbox(
            *,
            sheet_idx: int,
            row_idx: int,
            col_idx: int,
            max_rows: int,
            max_cols: int,
        ) -> List[float]:
            rows = max(1, max_rows)
            cols = max(1, max_cols)
            x = min(1.0, max(0.0, (col_idx - 1) / float(cols)))
            y = min(1.0, max(0.0, (row_idx - 1) / float(rows)))
            w = min(1.0, max(0.001, 1.0 / float(cols)))
            h = min(1.0, max(0.001, 1.0 / float(rows)))
            return [float(sheet_idx), x, y, w, h]

        def _append_rows_as_table(
            *,
            source_tag: str,
            sheet_idx: int,
            sheet_name: str,
            rows_payload: List[Dict[str, Any]],
        ) -> None:
            if not rows_payload:
                return
            headers, data_rows = self._infer_headers_and_data_rows(rows_payload)
            data_rows = self._drop_redundant_header_like_rows(data_rows, headers)
            data_rows = self._decorate_rows_with_meta(data_rows, headers)
            if not data_rows:
                return
            table_blocks.append(
                {
                    "table_id": f"{source_tag}_t{sheet_idx}",
                    "source": source_tag,
                    "page": sheet_idx,
                    "sheet_index": sheet_idx,
                    "sheet_name": sheet_name,
                    "headers": headers,
                    "header_meta": self._build_header_meta(headers),
                    "rows": data_rows,
                    "row_count": len(data_rows),
                    "col_count": max((len(r.get("cells", [])) for r in data_rows), default=0),
                }
            )

        def consume_workbook(wb: Any, source_tag: str) -> None:
            nonlocal emitted_cells
            for sheet_idx, ws in enumerate(wb.worksheets[: self.xlsx_sheet_limit], start=1):
                rows_payload: List[Dict[str, Any]] = []
                max_rows_hint = min(self.table_max_rows, max(int(getattr(ws, "max_row", 0) or 0), 1))
                max_cols_hint = min(self.table_max_cols, max(int(getattr(ws, "max_column", 0) or 0), 1))

                for row_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
                    if row_idx > self.table_max_rows:
                        break
                    cells_payload: List[Dict[str, Any]] = []
                    for col_idx, val in enumerate(list(row)[: self.table_max_cols], start=1):
                        text = self._normalize_text("" if val is None else str(val))
                        cell_ref = None
                        bbox = _xlsx_bbox(
                            sheet_idx=sheet_idx,
                            row_idx=row_idx,
                            col_idx=col_idx,
                            max_rows=max_rows_hint,
                            max_cols=max_cols_hint,
                        )
                        if text:
                            cell_ref = f"{source_tag}_t{sheet_idx}_r{row_idx}_c{col_idx}"
                            parts.append(f'<ref id="{cell_ref}">{escape(text)}</ref>')
                            bbox_map[cell_ref] = bbox
                            emitted_cells += 1
                        cells_payload.append(
                            {
                                "col_index": col_idx,
                                "text": text,
                                "ref_id": cell_ref,
                                "bbox": bbox,
                            }
                        )
                        if emitted_cells >= self.xlsx_cell_cap:
                            break

                    if any(cell.get("text") for cell in cells_payload):
                        rows_payload.append({"row_index": row_idx, "cells": cells_payload})

                    if emitted_cells >= self.xlsx_cell_cap:
                        break

                _append_rows_as_table(
                    source_tag=source_tag,
                    sheet_idx=sheet_idx,
                    sheet_name=str(getattr(ws, "title", "") or f"Sheet{sheet_idx}"),
                    rows_payload=rows_payload,
                )

                if emitted_cells >= self.xlsx_cell_cap:
                    break

        def _xlsx_col_to_index(col_ref: str) -> int:
            idx = 0
            for ch in str(col_ref or "").upper():
                if "A" <= ch <= "Z":
                    idx = idx * 26 + (ord(ch) - 64)
            return idx

        def _xlsx_ref_to_row_col(cell_ref: str) -> Tuple[int, int]:
            match = re.match(r"^([A-Za-z]+)(\d+)$", str(cell_ref or "").strip())
            if not match:
                return 0, 0
            return int(match.group(2)), _xlsx_col_to_index(match.group(1))

        def _xlsx_dimension_hints(ref_value: str) -> Tuple[int, int]:
            raw = str(ref_value or "").strip()
            if not raw:
                return 1, 1
            tail = raw.split(":")[-1]
            row_idx, col_idx = _xlsx_ref_to_row_col(tail)
            return max(1, row_idx), max(1, col_idx)

        def _xlsx_shared_strings_from_zip(zf: zipfile.ZipFile) -> List[str]:
            try:
                root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            except Exception:
                return []
            shared: List[str] = []
            for node in root.findall(".//{*}si"):
                fragments = [str(text_node.text or "") for text_node in node.iterfind(".//{*}t")]
                if fragments:
                    shared.append(self._normalize_text("".join(fragments)))
                else:
                    shared.append("")
            return shared

        def _xlsx_sheet_entries_from_zip(zf: zipfile.ZipFile) -> List[Tuple[int, str, str]]:
            rel_map: Dict[str, str] = {}
            try:
                rel_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
                for rel in rel_root.findall(".//{*}Relationship"):
                    rel_id = str(rel.get("Id") or "").strip()
                    rel_type = str(rel.get("Type") or "").strip().lower()
                    target = str(rel.get("Target") or "").strip().replace("\\", "/")
                    if not rel_id or not target or not rel_type.endswith("/worksheet"):
                        continue
                    if target.startswith("/"):
                        normalized_target = target.lstrip("/")
                    elif target.startswith("xl/"):
                        normalized_target = target
                    else:
                        normalized_target = f"xl/{target.lstrip('./')}"
                    rel_map[rel_id] = normalized_target
            except Exception:
                rel_map = {}

            entries: List[Tuple[int, str, str]] = []
            try:
                root = ET.fromstring(zf.read("xl/workbook.xml"))
                rid_keys = (
                    "{http://purl.oclc.org/ooxml/officeDocument/relationships}id",
                    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id",
                )
                for sheet_idx, sheet in enumerate(root.findall(".//{*}sheet"), start=1):
                    sheet_name = self._normalize_text(str(sheet.get("name") or f"Sheet{sheet_idx}"))
                    rel_id = ""
                    for rid_key in rid_keys:
                        rel_id = str(sheet.get(rid_key) or "").strip()
                        if rel_id:
                            break
                    target = rel_map.get(rel_id)
                    if target:
                        entries.append((sheet_idx, sheet_name or f"Sheet{sheet_idx}", target))
            except Exception:
                entries = []

            if entries:
                return entries[: self.xlsx_sheet_limit]

            sheet_paths = sorted(
                name
                for name in zf.namelist()
                if name.startswith("xl/worksheets/") and name.endswith(".xml")
            )
            return [
                (sheet_idx, f"Sheet{sheet_idx}", sheet_path)
                for sheet_idx, sheet_path in enumerate(sheet_paths[: self.xlsx_sheet_limit], start=1)
            ]

        def _xlsx_cell_text_from_xml(cell_node: ET.Element, shared_strings: List[str]) -> str:
            cell_type = str(cell_node.get("t") or "").strip().lower()
            if cell_type == "inlinestr":
                text_parts = [str(node.text or "") for node in cell_node.findall(".//{*}t")]
                return "".join(text_parts).strip()

            value_node = cell_node.find("./{*}v")
            formula_node = cell_node.find("./{*}f")
            raw_value = "".join(value_node.itertext()).strip() if value_node is not None else ""
            raw_formula = "".join(formula_node.itertext()).strip() if formula_node is not None else ""

            if cell_type == "s":
                try:
                    shared_idx = int(float(raw_value))
                    if 0 <= shared_idx < len(shared_strings):
                        return shared_strings[shared_idx]
                except Exception:
                    return raw_value
                return raw_value
            if cell_type == "b":
                if raw_value.lower() in {"1", "true"}:
                    return "TRUE"
                if raw_value.lower() in {"0", "false"}:
                    return "FALSE"
                return raw_value
            if cell_type in {"str", "d", "e"}:
                return raw_value
            if raw_value:
                return raw_value
            if raw_formula:
                return f"={raw_formula}"
            return ""

        def consume_zip_workbook(source_tag: str) -> None:
            nonlocal emitted_cells, used_zip_fallback
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                shared_strings = _xlsx_shared_strings_from_zip(zf)
                sheet_entries = _xlsx_sheet_entries_from_zip(zf)
                if not sheet_entries:
                    return
                used_zip_fallback = True

                for sheet_idx, sheet_name, sheet_path in sheet_entries:
                    if emitted_cells >= self.xlsx_cell_cap:
                        break
                    try:
                        root = ET.fromstring(zf.read(sheet_path))
                    except Exception:
                        continue

                    dimension_node = root.find(".//{*}dimension")
                    max_rows_hint, max_cols_hint = _xlsx_dimension_hints(
                        str(dimension_node.get("ref") or "") if dimension_node is not None else ""
                    )
                    rows_payload: List[Dict[str, Any]] = []
                    sheet_data = root.find(".//{*}sheetData")
                    if sheet_data is None:
                        continue

                    for row_pos, row_node in enumerate(sheet_data.findall("./{*}row"), start=1):
                        try:
                            row_idx = int(row_node.get("r") or row_pos)
                        except Exception:
                            row_idx = row_pos
                        if row_idx > self.table_max_rows:
                            break

                        cells_payload: List[Dict[str, Any]] = []
                        max_rows_hint = max(max_rows_hint, row_idx)
                        for cell_pos, cell_node in enumerate(row_node.findall("./{*}c"), start=1):
                            cell_ref_raw = str(cell_node.get("r") or "").strip()
                            ref_row_idx, ref_col_idx = _xlsx_ref_to_row_col(cell_ref_raw)
                            col_idx = ref_col_idx or cell_pos
                            if col_idx > self.table_max_cols:
                                continue

                            text = self._normalize_text(_xlsx_cell_text_from_xml(cell_node, shared_strings))
                            bbox = _xlsx_bbox(
                                sheet_idx=sheet_idx,
                                row_idx=ref_row_idx or row_idx,
                                col_idx=col_idx,
                                max_rows=max_rows_hint,
                                max_cols=max(max_cols_hint, col_idx),
                            )
                            cell_ref = None
                            if text:
                                cell_ref = f"{source_tag}_t{sheet_idx}_r{ref_row_idx or row_idx}_c{col_idx}"
                                parts.append(f'<ref id="{cell_ref}">{escape(text)}</ref>')
                                bbox_map[cell_ref] = bbox
                                emitted_cells += 1
                            cells_payload.append(
                                {
                                    "col_index": col_idx,
                                    "text": text,
                                    "ref_id": cell_ref,
                                    "bbox": bbox,
                                }
                            )
                            max_cols_hint = max(max_cols_hint, col_idx)
                            if emitted_cells >= self.xlsx_cell_cap:
                                break

                        if any(cell.get("text") for cell in cells_payload):
                            rows_payload.append({"row_index": row_idx, "cells": cells_payload})

                        if emitted_cells >= self.xlsx_cell_cap:
                            break

                    _append_rows_as_table(
                        source_tag=source_tag,
                        sheet_idx=sheet_idx,
                        sheet_name=sheet_name or f"Sheet{sheet_idx}",
                        rows_payload=rows_payload,
                    )

        try:
            wb_data = load_workbook(io.BytesIO(file_bytes), data_only=True, read_only=True)
            if getattr(wb_data, "worksheets", None):
                consume_workbook(wb_data, "xlsx")
        except Exception:
            pass

        if not parts:
            try:
                consume_zip_workbook("xlsx")
            except Exception:
                used_zip_fallback = False

        if not parts:
            try:
                wb_formula = load_workbook(io.BytesIO(file_bytes), data_only=False, read_only=True)
                if getattr(wb_formula, "worksheets", None):
                    consume_workbook(wb_formula, "xlsx_formula")
            except Exception:
                pass

        if not parts:
            sheet_names: List[str] = []
            try:
                wb_meta = load_workbook(io.BytesIO(file_bytes), data_only=False, read_only=True)
                sheet_names = list(getattr(wb_meta, "sheetnames", []) or [])
            except Exception:
                sheet_names = []
            for idx, sheet_name in enumerate(sheet_names[: self.xlsx_sheet_limit], start=1):
                ref_id = f"xlsx_sheet_{idx}"
                safe_name = self._normalize_text(str(sheet_name or f"Sheet{idx}"))
                desc = f"工作表：{safe_name}（未检测到可提取单元格，可能为图表或公式驱动文件）"
                parts.append(f'<ref id="{ref_id}">{escape(desc)}</ref>')
                bbox_map[ref_id] = [float(idx), 0.0, 0.0, 1.0, 1.0]
            if not parts:
                ref_id = "xlsx_sheet_1"
                desc = "工作簿中未检测到可提取工作表，已按空结构文件处理。"
                parts.append(f'<ref id="{ref_id}">{escape(desc)}</ref>')
                bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]

        if not parts:
            raise ValueError("XLSX contains no extractable rows.")
        self._last_parse_stats = {"xlsx_zip_fallback": used_zip_fallback}
        self._last_figure_blocks = []
        return "\n".join(parts), bbox_map, table_blocks

    def _parse_image(self, file_name: str, file_bytes: bytes) -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        visual_backend_ready, visual_backend_missing = self._visual_backend_available()
        vision_api_ready = bool(self._gemini_api_key()) and self.enable_gemini_vision_enhance
        if not visual_backend_ready and not vision_api_ready:
            raise ValueError(
                "Image OCR backend is unavailable. "
                f"Please install: {visual_backend_missing}"
            )

        try:
            import fitz  # pymupdf
        except Exception as exc:
            raise ValueError(
                "Image OCR backend is unavailable. Install pymupdf and rapidocr-onnxruntime."
            ) from exc
        np = None
        if visual_backend_ready:
            try:
                import numpy as np  # type: ignore
            except Exception as exc:
                raise ValueError(
                    "Image OCR backend is unavailable. Install pymupdf and rapidocr-onnxruntime."
                ) from exc

        ext = os.path.splitext((file_name or "").lower())[1].lstrip(".")
        filetype_candidates = [x for x in [ext, "png", "jpeg"] if x]
        doc = None
        open_error: Exception | None = None
        for filetype in filetype_candidates:
            try:
                doc = fitz.open(stream=file_bytes, filetype=filetype)
                break
            except Exception as exc:  # pragma: no cover - backend-specific decode fallback
                open_error = exc
                continue
        if doc is None:
            raise ValueError(f"Unsupported or corrupted image payload: {file_name}") from open_error

        min_conf = float(os.getenv("MODULE2_OCR_MIN_CONF", "0.45"))
        dpi = max(96, int(os.getenv("MODULE2_IMAGE_OCR_DPI", "180")))
        mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
        engine = self._get_ocr_engine() if visual_backend_ready else None

        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        page_lines: Dict[int, List[str]] = {}
        page_cells: Dict[int, List[Dict[str, Any]]] = {}

        try:
            page_count = min(len(doc), self.max_pages_visual)
            self._runtime_page_count = page_count
            for page_idx in range(page_count):
                page_no = page_idx + 1
                page = doc.load_page(page_idx)
                if not visual_backend_ready:
                    ref_id = f"img_p{page_no}_vision_probe"
                    placeholder = f"[Image page {page_no}] OCR backend unavailable, trying Gemini Vision."
                    parts.append(f'<ref id="{ref_id}">{escape(placeholder)}</ref>')
                    bbox_map[ref_id] = [float(page_no), 0.0, 0.0, 1.0, 1.0]
                    page_lines[page_no] = [placeholder]
                    continue

                pix = page.get_pixmap(matrix=mat, alpha=False)
                raw = np.frombuffer(pix.samples, dtype=np.uint8)
                if pix.n == 1:
                    image = raw.reshape(pix.height, pix.width)
                else:
                    image = raw.reshape(pix.height, pix.width, pix.n)
                    if pix.n > 3:
                        image = image[:, :, :3]

                ocr_result, _ = engine(image)
                if not ocr_result:
                    ref_id = f"img_p{page_no}_ocr1"
                    placeholder = f"[Image page {page_no}] OCR found no text."
                    parts.append(f'<ref id="{ref_id}">{escape(placeholder)}</ref>')
                    bbox_map[ref_id] = [float(page_no), 0.0, 0.0, 1.0, 1.0]
                    continue

                lines: List[str] = []
                item_idx = 1
                for item in ocr_result:
                    if not isinstance(item, (list, tuple)) or len(item) < 3:
                        continue
                    box, text, score = item[0], str(item[1]).strip(), float(item[2] or 0.0)
                    if not text or score < min_conf:
                        continue
                    normalized = self._normalize_text(text)
                    if not normalized:
                        continue

                    ref_id = f"img_p{page_no}_ocr{item_idx}"
                    parts.append(f'<ref id="{ref_id}">{escape(normalized)}</ref>')
                    x, y, w, h = self._normalize_box(box, pix.width, pix.height)
                    bbox_map[ref_id] = [float(page_no), x, y, w, h]
                    lines.append(normalized)
                    page_cells.setdefault(page_no, []).append(
                        {
                            "ref_id": ref_id,
                            "text": normalized,
                            "bbox": [float(page_no), x, y, w, h],
                            "x_center": x + (w / 2.0),
                            "y_center": y + (h / 2.0),
                        }
                    )
                    item_idx += 1
                if lines:
                    page_lines[page_no] = lines
        finally:
            doc.close()

        if visual_backend_ready and not parts:
            raise ValueError(
                "Image OCR completed but no text was extracted."
            )

        table_blocks: TableBlocks = []
        if visual_backend_ready:
            table_blocks = self._infer_tables_from_ocr_cells(page_cells)
        if visual_backend_ready and not table_blocks and page_lines:
            table_blocks = self._infer_tables_from_page_lines(
                page_lines,
                parts,
                bbox_map,
                source="image_ocr_line",
            )

        figure_blocks = self._infer_figures_from_page_lines(
            page_lines=page_lines,
            parts=parts,
            bbox_map=bbox_map,
            source_prefix="image_caption",
        )

        table_blocks, vision_figures = self._enhance_low_quality_pages_with_gemini_vision(
            file_bytes=file_bytes,
            filetype=ext or "png",
            page_lines=page_lines,
            table_blocks=table_blocks,
            parts=parts,
            bbox_map=bbox_map,
            source_prefix="image_gemini_vision",
        )
        if vision_figures:
            figure_blocks = self._merge_figure_blocks(figure_blocks, vision_figures)

        table_blocks = self._prune_fragment_tables(table_blocks)
        self._last_figure_blocks = figure_blocks
        return "\n".join(parts), bbox_map, table_blocks

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
        if not self.enable_gemini_vision_enhance or self.gemini_vision_max_pages <= 0:
            return table_blocks, []

        api_key = self._gemini_api_key()
        if not api_key:
            return table_blocks, []
        if not page_lines:
            return table_blocks, []

        candidate_pages = self._select_low_quality_pages_for_vision(
            page_lines=page_lines,
            table_blocks=table_blocks,
        )
        if not candidate_pages:
            return table_blocks, []

        try:
            import fitz  # pymupdf
        except Exception:
            return table_blocks, []

        try:
            doc = fitz.open(stream=file_bytes, filetype=filetype)
        except Exception:
            return table_blocks, []

        try:
            table_idx = self._next_table_index(table_blocks, f"{source_prefix}_t")
            figure_idx = self._next_figure_index(self._last_figure_blocks, f"{source_prefix}_f")
            vision_tables: TableBlocks = []
            vision_figures: FigureBlocks = []
            consecutive_empty_payload = 0
            for page_no in candidate_pages:
                page_idx = page_no - 1
                if page_idx < 0 or page_idx >= len(doc):
                    continue
                try:
                    page = doc.load_page(page_idx)
                except Exception:
                    continue
                image_png = self._render_page_png_for_vision(page)
                if not image_png:
                    continue

                focus = self._vision_focus_from_page_lines(page_lines.get(page_no, []))
                payload = self._gemini_vision_extract_payload(image_png, focus=focus)
                if not payload:
                    consecutive_empty_payload += 1
                    if consecutive_empty_payload >= self.gemini_vision_consecutive_fail_stop:
                        break
                    continue
                consecutive_empty_payload = 0

                insight_refs = self._extract_vision_insights(payload, page_no, bbox_map)
                for ref_id, text in insight_refs:
                    if ref_id in bbox_map:
                        continue
                    parts.append(f'<ref id="{ref_id}">{escape(text)}</ref>')
                    bbox_map[ref_id] = [float(page_no), 0.0, 0.0, 1.0, 1.0]

                built, table_idx = self._build_tables_from_vision_payload(
                    payload=payload,
                    page_no=page_no,
                    table_idx=table_idx,
                    parts=parts,
                    bbox_map=bbox_map,
                    source_prefix=source_prefix,
                )
                if built:
                    vision_tables.extend(built)
                built_figures, figure_idx = self._build_figures_from_vision_payload(
                    payload=payload,
                    page_no=page_no,
                    figure_idx=figure_idx,
                    parts=parts,
                    bbox_map=bbox_map,
                    source_prefix=source_prefix,
                )
                if built_figures:
                    vision_figures.extend(built_figures)
        finally:
            doc.close()

        if not vision_tables:
            return table_blocks, self._merge_figure_blocks([], vision_figures)
        if table_blocks:
            merged = self._augment_with_line_tables(table_blocks, vision_tables)
            return merged, self._merge_figure_blocks([], vision_figures)
        return vision_tables, self._merge_figure_blocks([], vision_figures)

    def _select_low_quality_pages_for_vision(
        self,
        page_lines: Dict[int, List[str]],
        table_blocks: TableBlocks,
    ) -> List[int]:
        if not page_lines or self.gemini_vision_max_pages <= 0:
            return []

        pages = sorted(page_lines.keys())
        if not pages:
            return []
        vision_cap = self.gemini_vision_max_pages
        probe_like_pages = 0
        for p in pages:
            lines = page_lines.get(p, [])
            joined = " ".join(lines[:3]).lower()
            if ("vision probe" in joined) or ("no extractable native text" in joined) or ("ocr found no text" in joined):
                probe_like_pages += 1
        if pages and (probe_like_pages / float(len(pages))) >= 0.55:
            vision_cap = min(len(pages), max(vision_cap, min(48, len(pages))))
        elif self.gemini_vision_enable_figures and len(pages) <= 60:
            vision_cap = min(len(pages), max(vision_cap, min(36, len(pages))))

        quality_by_page: Dict[int, float] = {}
        for table in table_blocks:
            page_no = int(table.get("page", 0) or 0)
            if page_no <= 0:
                continue
            try:
                quality = float(table.get("quality"))
            except (TypeError, ValueError):
                quality = 0.66
            prev = quality_by_page.get(page_no)
            if prev is None:
                quality_by_page[page_no] = quality
            else:
                quality_by_page[page_no] = min(prev, quality)

        ranked: List[Tuple[int, int, int]] = []
        page_signal: Dict[int, int] = {}
        for page_no in pages:
            lines = page_lines.get(page_no, [])
            if not lines:
                continue
            cue_text = " ".join(lines[:40])
            cue_hit = 1 if self._looks_like_table_cue_text(cue_text) else 0
            figure_hit = 1 if self._looks_like_figure_cue_text(cue_text) else 0
            numeric_lines = 0
            for line in lines[:80]:
                if sum(1 for ch in line if ch.isdigit()) >= 3:
                    numeric_lines += 1
            table_signal = (4 if cue_hit else 0) + min(7, numeric_lines)
            figure_signal = (5 if figure_hit else 0) + min(
                4,
                sum(1 for line in lines[:50] if self._contains_figure_marker(line)),
            )
            combined_signal = table_signal + figure_signal
            page_signal[page_no] = combined_signal
            qv = quality_by_page.get(page_no)

            if qv is not None and qv < self.gemini_vision_min_table_quality:
                # Primary targets: pages with weak existing tables.
                ranked.append((0, -combined_signal, page_no))
                continue

            if qv is None and table_signal >= 3:
                # No table yet but strong tabular signal.
                ranked.append((1, -combined_signal, page_no))
                continue

            if figure_signal >= 4:
                # Figure-heavy pages are also valuable for Vision enrichment.
                ranked.append((2, -combined_signal, page_no))
                continue

            if qv is not None and qv < (self.gemini_vision_min_table_quality + 0.10) and combined_signal >= 2:
                # Borderline quality pages with moderate signal.
                ranked.append((3, -combined_signal, page_no))

        if not ranked and len(table_blocks) < 2:
            for page_no in pages:
                lines = page_lines.get(page_no, [])
                numeric_lines = 0
                for line in lines[:80]:
                    if sum(1 for ch in line if ch.isdigit()) >= 3:
                        numeric_lines += 1
                fig_lines = sum(1 for line in lines[:50] if self._contains_figure_marker(line))
                signal = numeric_lines + (fig_lines * 2)
                if signal >= 3:
                    ranked.append((4, -signal, page_no))

        if not ranked:
            if len(table_blocks) == 0:
                if len(pages) <= vision_cap:
                    return pages
            if vision_cap == 1:
                return [pages[len(pages) // 2]]
            step = (len(pages) - 1) / float(vision_cap - 1)
            sampled = [pages[int(round(i * step))] for i in range(vision_cap)]
            return sorted(set(sampled))
            return []

        ranked.sort()
        selected: List[int] = []
        selected_set = set()

        def _pick(page_no: int) -> None:
            if page_no in selected_set:
                return
            selected.append(page_no)
            selected_set.add(page_no)

        primary_cap = max(1, int(round(vision_cap * 0.55)))
        for _, _, page_no in ranked:
            _pick(page_no)
            if len(selected) >= primary_cap:
                break

        # Keep cross-document coverage to avoid only hitting early pages.
        if len(selected) < vision_cap and len(pages) >= 8:
            seg_count = min(vision_cap, 8)
            for seg in range(seg_count):
                start = int(round((len(pages) * seg) / float(seg_count)))
                end = int(round((len(pages) * (seg + 1)) / float(seg_count)))
                seg_pages = pages[start:end] if end > start else []
                if not seg_pages:
                    continue
                best_page = max(seg_pages, key=lambda p: page_signal.get(p, 0))
                _pick(best_page)
                if len(selected) >= vision_cap:
                    break

        # Tail-biased fallback for long docs (common missed tables/figures in appendices).
        if len(selected) < vision_cap and len(pages) >= 40:
            tail_len = max(10, len(pages) // 5)
            tail_pages = pages[-tail_len:]
            for page_no in sorted(tail_pages, key=lambda p: page_signal.get(p, 0), reverse=True):
                _pick(page_no)
                if len(selected) >= vision_cap:
                    break

        if len(selected) < vision_cap:
            for page_no in list(selected):
                for cand in (page_no - 1, page_no + 1):
                    if cand in page_lines and page_signal.get(cand, 0) >= 2:
                        _pick(cand)
                        if len(selected) >= vision_cap:
                            break
                if len(selected) >= vision_cap:
                    break

        if len(selected) < vision_cap:
            for _, _, page_no in ranked:
                _pick(page_no)
                if len(selected) >= vision_cap:
                    break

        if len(selected) < vision_cap:
            for page_no in pages:
                _pick(page_no)
                if len(selected) >= vision_cap:
                    break

        return selected

    @staticmethod
    def _next_table_index(table_blocks: TableBlocks, prefix: str) -> int:
        max_idx = 0
        for table in table_blocks:
            table_id = str(table.get("table_id", ""))
            if not table_id.startswith(prefix):
                continue
            m = re.search(r"(\d+)$", table_id)
            if not m:
                continue
            try:
                max_idx = max(max_idx, int(m.group(1)))
            except ValueError:
                continue
        return max_idx + 1

    @staticmethod
    def _next_figure_index(figure_blocks: FigureBlocks, prefix: str) -> int:
        max_idx = 0
        for figure in figure_blocks:
            figure_id = str(figure.get("figure_id", ""))
            if not figure_id.startswith(prefix):
                continue
            m = re.search(r"(\d+)$", figure_id)
            if not m:
                continue
            try:
                max_idx = max(max_idx, int(m.group(1)))
            except ValueError:
                continue
        return max_idx + 1

    def _looks_like_figure_cue_text(self, text: str) -> bool:
        t = self._normalize_text(str(text or ""))
        if not t:
            return False
        lower = t.lower()
        if self._contains_figure_marker(t):
            return True
        if any(
            kw in lower
            for kw in [
                "figure ",
                "chart",
                "diagram",
                "plot",
                "curve",
                "spectrum",
                "flowchart",
                "histogram",
            ]
        ):
            return True
        if any(kw in t for kw in ["图表", "示意图", "流程图", "曲线", "趋势图", "柱状图", "折线图", "饼图"]):
            return True
        return False

    def _extract_figure_captions_from_lines(self, lines: List[str]) -> List[str]:
        captions: List[str] = []
        if not lines:
            return captions

        n = len(lines)
        for idx, raw in enumerate(lines):
            line = self._normalize_text(raw)
            if not line:
                continue

            lower = line.lower()
            if re.search(r"^\s*table\b", lower) or re.search(r"^\s*表\s*[0-9A-Za-z一二三四五六七八九十.\-]+", line):
                continue

            marker_match = re.match(
                r"^\s*((?:fig(?:ure)?\.?\s*[A-Za-z0-9.\-]+|图\s*[0-9A-Za-z一二三四五六七八九十百千.\-]+))\s*[:：\-]?\s*(.*)$",
                line,
                flags=re.IGNORECASE,
            )
            if not marker_match:
                continue
            if re.search(r"\.{3,}\s*\d{1,4}\s*$", line):
                # Skip table-of-contents style entries like "Figure 3 .... 27".
                continue

            marker = self._normalize_text(marker_match.group(1))
            suffix = self._normalize_text(marker_match.group(2))
            caption = suffix
            if not caption and idx + 1 < n:
                nxt = self._normalize_text(lines[idx + 1])
                if nxt and not self._contains_figure_marker(nxt):
                    caption = nxt

            full = marker if not caption else f"{marker}: {caption}"
            full = self._normalize_text(full)
            if len(full) < 4:
                continue
            if len(full) > 220:
                full = full[:220]
            captions.append(full)

        deduped: List[str] = []
        seen = set()
        for cap in captions:
            key = self._normalize_token_for_compare(cap)
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(cap)
        return deduped

    def _infer_figure_type_from_text(self, text: str) -> str:
        t = self._normalize_text(text).lower()
        if not t:
            return "other"
        if any(kw in t for kw in ["diagram", "flow", "scheme", "示意", "流程", "框图"]):
            return "diagram"
        if any(
            kw in t
            for kw in [
                "chart",
                "curve",
                "plot",
                "trend",
                "histogram",
                "bar",
                "line",
                "pie",
                "曲线",
                "趋势",
                "柱状",
                "折线",
                "饼图",
                "分布",
            ]
        ):
            return "chart"
        if any(kw in t for kw in ["photo", "image", "照片", "图片"]):
            return "photo"
        return "other"

    @staticmethod
    def _safe_text_list(values: Any, max_items: int = 8, max_len: int = 180) -> List[str]:
        if not isinstance(values, list):
            return []
        out: List[str] = []
        for item in values[:max_items]:
            text = str(item or "").strip()
            if not text:
                continue
            if len(text) > max_len:
                text = text[:max_len]
            out.append(text)
        return out

    def _normalize_figure_key_values(self, values: Any, *, max_items: int = 8) -> List[Dict[str, str]]:
        if not isinstance(values, list):
            return []
        out: List[Dict[str, str]] = []
        for item in values[:max_items]:
            if not isinstance(item, dict):
                continue
            name = self._normalize_text(str(item.get("name", "") or ""))
            value = self._normalize_text(str(item.get("value", "") or ""))
            unit = self._normalize_text(str(item.get("unit", "") or ""))
            if not name and not value:
                continue
            out.append({"name": name, "value": value, "unit": unit})
        return out

    def _coerce_figure_dataframe(
        self,
        *,
        headers: List[str],
        rows: List[List[str]],
        key_values: List[Dict[str, str]],
        fallback_texts: List[str],
        x_axis: str = "",
        y_axis: str = "",
    ) -> Tuple[List[str], List[List[str]], str]:
        normalized_headers = self._normalize_dataframe_headers(headers)
        normalized_rows = self._normalize_dataframe_matrix(rows)

        if normalized_rows:
            if not normalized_headers:
                max_cols = max((len(row) for row in normalized_rows), default=0)
                if max_cols == 2 and (x_axis or y_axis):
                    normalized_headers = [
                        self._normalize_text(x_axis or "维度"),
                        self._normalize_text(y_axis or "数值"),
                    ]
                elif max_cols == 3:
                    normalized_headers = ["指标", "值", "单位"]
                elif max_cols > 0:
                    normalized_headers = [f"列{i + 1}" for i in range(max_cols)]
            return normalized_headers, normalized_rows, "model"

        key_value_rows: List[List[str]] = []
        for item in key_values:
            name = self._normalize_text(item.get("name", ""))
            value = self._normalize_text(item.get("value", ""))
            unit = self._normalize_text(item.get("unit", ""))
            if not name and not value:
                continue
            key_value_rows.append([name or f"指标{len(key_value_rows) + 1}", value, unit])
        if key_value_rows:
            return ["指标", "值", "单位"], key_value_rows, "key_values"

        parsed_rows: List[List[str]] = []
        for raw in fallback_texts:
            text = self._normalize_text(str(raw or ""))
            if not text:
                continue
            m = re.match(
                r"^(.{1,72}?)[：:]\s*([-+]?(?:\d[\d,]*\.?\d*|\d*\.?\d+)(?:[%％‰])?)\s*([A-Za-z\u4e00-\u9fa5/°℃μ\-]{0,18})$",
                text,
            )
            if not m:
                m = re.match(
                    r"^(.{1,56}?)\s+([-+]?(?:\d[\d,]*\.?\d*|\d*\.?\d+)(?:[%％‰])?)\s*([A-Za-z\u4e00-\u9fa5/°℃μ\-]{0,18})$",
                    text,
                )
            if not m:
                continue
            label = self._normalize_text(m.group(1))
            value = self._normalize_text(m.group(2))
            unit = self._normalize_text(m.group(3))
            if not label or not value:
                continue
            parsed_rows.append([label, value, unit])
        if parsed_rows:
            return ["指标", "值", "单位"], parsed_rows, "text_blocks"

        return normalized_headers, [], "none"

    def _infer_figures_from_page_lines(
        self,
        page_lines: Dict[int, List[str]],
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        source_prefix: str,
    ) -> FigureBlocks:
        if not page_lines:
            return []
        figure_idx = self._next_figure_index(self._last_figure_blocks, f"{source_prefix}_f")
        figures: FigureBlocks = []
        for page_no in sorted(page_lines.keys()):
            lines = page_lines.get(page_no, [])
            page_probe = self._normalize_text(" ".join(lines[:24]))
            lower_probe = page_probe.lower()
            if (
                self._contains_catalog_marker(page_probe)
                or "list of figures" in lower_probe
                or "list of tables" in lower_probe
                or "table of contents" in lower_probe
            ):
                continue

            captions = self._extract_figure_captions_from_lines(lines)
            for caption in captions[:4]:
                figure_id = f"{source_prefix}_f{figure_idx}"
                figure_idx += 1
                ref_id = f"{figure_id}_caption"
                bbox = [float(page_no), 0.0, 0.0, 1.0, 1.0]
                if ref_id not in bbox_map:
                    parts.append(f'<ref id="{ref_id}">{escape(caption)}</ref>')
                    bbox_map[ref_id] = bbox
                figures.append(
                    {
                        "figure_id": figure_id,
                        "source": source_prefix,
                        "page": page_no,
                        "figure_type": self._infer_figure_type_from_text(caption),
                        "caption": caption,
                        "insights": [],
                        "quality": 0.58,
                        "ref_ids": [ref_id],
                    }
                )
        return self._merge_figure_blocks([], figures)

    def _build_figures_from_vision_payload(
        self,
        payload: Dict[str, Any],
        page_no: int,
        figure_idx: int,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        source_prefix: str,
    ) -> Tuple[FigureBlocks, int]:
        if not self.gemini_vision_enable_figures or self.gemini_vision_max_figures_per_page <= 0:
            return [], figure_idx
        figures_raw = payload.get("figures", [])
        if not isinstance(figures_raw, list):
            return [], figure_idx

        built: FigureBlocks = []
        for figure_raw in figures_raw[: self.gemini_vision_max_figures_per_page]:
            if not isinstance(figure_raw, dict):
                continue
            title = self._normalize_text(str(figure_raw.get("title", "") or ""))
            caption = self._normalize_text(str(figure_raw.get("caption", "") or ""))
            if not caption:
                caption = title
            kind = self._normalize_text(str(figure_raw.get("type", "") or "")) or self._infer_figure_type_from_text(caption)
            if kind not in {"chart", "diagram", "photo", "other"}:
                kind = self._infer_figure_type_from_text(kind)

            key_points = self._safe_text_list(figure_raw.get("key_points"), max_items=8, max_len=180)
            legend_items = self._safe_text_list(figure_raw.get("legend"), max_items=8, max_len=80)
            text_blocks = self._safe_text_list(figure_raw.get("text_blocks"), max_items=10, max_len=180)
            axes = figure_raw.get("axes")
            if isinstance(axes, dict):
                x_axis = self._normalize_text(str(axes.get("x", "") or ""))
                y_axis = self._normalize_text(str(axes.get("y", "") or ""))
            else:
                x_axis = ""
                y_axis = ""

            insights: List[str] = []
            if x_axis:
                insights.append(f"x-axis: {x_axis}")
            if y_axis:
                insights.append(f"y-axis: {y_axis}")
            for item in legend_items:
                insights.append(f"legend: {self._normalize_text(item)}")
            for item in key_points:
                insights.append(self._normalize_text(item))
            for item in text_blocks[:3]:
                insights.append(f"text: {self._normalize_text(item)}")

            dataframe = figure_raw.get("dataframe") if isinstance(figure_raw.get("dataframe"), dict) else {}
            df_headers = self._normalize_dataframe_headers(dataframe.get("headers"), max_len=120)
            df_rows = self._normalize_dataframe_matrix(dataframe.get("rows"), max_cell_len=160)
            key_values = self._normalize_figure_key_values(figure_raw.get("key_values"), max_items=6)
            for item in key_values:
                name = self._normalize_text(item.get("name", ""))
                value = self._normalize_text(item.get("value", ""))
                unit = self._normalize_text(item.get("unit", ""))
                if unit:
                    insights.append(f"{name}: {value} {unit}".strip())
                else:
                    insights.append(f"{name}: {value}".strip())
            df_headers, df_rows, dataframe_source = self._coerce_figure_dataframe(
                headers=df_headers,
                rows=df_rows,
                key_values=key_values,
                fallback_texts=text_blocks + key_points + insights,
                x_axis=x_axis,
                y_axis=y_axis,
            )
            if df_headers and df_rows:
                insights.append(f"dataframe: {len(df_rows)}x{max(len(r) for r in df_rows)}")

            topology = figure_raw.get("topology") if isinstance(figure_raw.get("topology"), dict) else {}
            topo_nodes_raw = topology.get("nodes") if isinstance(topology.get("nodes"), list) else []
            topo_edges_raw = topology.get("edges") if isinstance(topology.get("edges"), list) else []
            topo_nodes: List[Dict[str, str]] = []
            topo_edges: List[Dict[str, str]] = []
            for node in topo_nodes_raw[:20]:
                if not isinstance(node, dict):
                    continue
                topo_nodes.append(
                    {
                        "id": self._normalize_text(str(node.get("id", "") or "")),
                        "label": self._normalize_text(str(node.get("label", "") or "")),
                        "type": self._normalize_text(str(node.get("type", "") or "")),
                    }
                )
            for edge in topo_edges_raw[:30]:
                if not isinstance(edge, dict):
                    continue
                topo_edges.append(
                    {
                        "source": self._normalize_text(str(edge.get("source", "") or "")),
                        "target": self._normalize_text(str(edge.get("target", "") or "")),
                        "label": self._normalize_text(str(edge.get("label", "") or "")),
                    }
                )
            if topo_nodes or topo_edges:
                insights.append(f"topology: nodes={len(topo_nodes)}, edges={len(topo_edges)}")

            content_modes = [
                self._normalize_text(str(x or "")).lower()
                for x in (figure_raw.get("content_modes") if isinstance(figure_raw.get("content_modes"), list) else [])
            ]
            content_modes = [x for x in content_modes if x in {"dataframe", "topology", "text", "visual"}]
            if (df_headers and df_rows) and "dataframe" not in content_modes:
                content_modes.append("dataframe")
            if (topo_nodes or topo_edges) and "topology" not in content_modes:
                content_modes.append("topology")
            if text_blocks and "text" not in content_modes:
                content_modes.append("text")
            if not content_modes:
                content_modes = ["visual"]

            insights = [x for x in insights if x]

            if not caption and not insights:
                continue

            confidence = self._to_float_or_none(figure_raw.get("confidence"))
            if confidence is None:
                confidence = 0.72
            confidence = max(0.1, min(1.0, float(confidence)))
            if confidence < self.gemini_vision_min_figure_quality and not caption:
                continue

            figure_id = f"{source_prefix}_f{figure_idx}"
            figure_idx += 1
            bbox = [float(page_no), 0.0, 0.0, 1.0, 1.0]
            ref_ids: List[str] = []
            if caption:
                cap_ref = f"{figure_id}_caption"
                if cap_ref not in bbox_map:
                    parts.append(f'<ref id="{cap_ref}">{escape(caption)}</ref>')
                    bbox_map[cap_ref] = bbox
                ref_ids.append(cap_ref)
            for i, insight in enumerate(insights[:6], start=1):
                insight_ref = f"{figure_id}_k{i}"
                if insight_ref not in bbox_map:
                    parts.append(f'<ref id="{insight_ref}">{escape(insight)}</ref>')
                    bbox_map[insight_ref] = bbox
                ref_ids.append(insight_ref)

            built.append(
                {
                    "figure_id": figure_id,
                    "source": source_prefix,
                    "page": page_no,
                    "figure_type": kind or "other",
                    "caption": caption,
                    "insights": insights[:6],
                    "key_points": key_points[:6] if key_points else insights[:6],
                    "quality": round(confidence, 4),
                    "ref_ids": ref_ids,
                    "content_modes": content_modes[:4],
                    "dataframe": {
                        "headers": df_headers,
                        "rows": df_rows,
                    },
                    "dataframe_source": dataframe_source,
                    "topology": {
                        "nodes": topo_nodes,
                        "edges": topo_edges,
                    },
                    "text_blocks": text_blocks[:8],
                }
            )
        return built, figure_idx

    def _figure_deep_score(self, item: Dict[str, Any]) -> int:
        score = 0
        key_points = item.get("key_points") if isinstance(item.get("key_points"), list) else []
        insights = item.get("insights") if isinstance(item.get("insights"), list) else []
        text_blocks = item.get("text_blocks") if isinstance(item.get("text_blocks"), list) else []
        dataframe = item.get("dataframe") if isinstance(item.get("dataframe"), dict) else {}
        df_rows = dataframe.get("rows") if isinstance(dataframe.get("rows"), list) else []
        if key_points:
            score += min(3, len(key_points))
        if insights:
            score += min(2, len(insights))
        if text_blocks:
            score += 1
        if df_rows:
            score += 4
        return score

    def _figure_blocks_need_vision(self, figure_blocks: FigureBlocks) -> bool:
        if not self.gemini_vision_enable_figures or not figure_blocks:
            return False

        rich_count = sum(1 for item in figure_blocks if self._figure_deep_score(item) > 0)
        total = len(figure_blocks)
        if rich_count <= 0:
            return True

        rich_ratio = rich_count / float(total)
        if total <= 2:
            return rich_ratio < 1.0
        return rich_ratio < 0.4

    def _merge_figure_blocks(self, left: FigureBlocks, right: FigureBlocks) -> FigureBlocks:
        if not left and not right:
            return []

        merged: Dict[Tuple[int, str], Dict[str, Any]] = {}
        passthrough: List[Dict[str, Any]] = []
        for figure in list(left) + list(right):
            page_no = int(figure.get("page", 0) or 0)
            caption = self._normalize_text(str(figure.get("caption", "") or ""))
            key_norm = self._normalize_token_for_compare(caption)
            if key_norm:
                key = (page_no, key_norm[:96])
                prev = merged.get(key)
                if prev:
                    try:
                        prev_q = float(prev.get("quality", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        prev_q = 0.0
                else:
                    prev_q = -1.0
                try:
                    cur_q = float(figure.get("quality", 0.0) or 0.0)
                except (TypeError, ValueError):
                    cur_q = 0.0
                if prev is None or cur_q >= prev_q:
                    merged[key] = dict(figure)
                continue
            passthrough.append(dict(figure))

        out = list(merged.values()) + passthrough
        by_page: Dict[int, List[Dict[str, Any]]] = {}
        for item in out:
            page_no = int(item.get("page", 0) or 0)
            by_page.setdefault(page_no, []).append(item)

        pruned: List[Dict[str, Any]] = []
        for page_no in sorted(by_page.keys()):
            items = by_page.get(page_no, [])
            caption_items = [x for x in items if "_caption" in str(x.get("source", ""))]
            rich_items = [x for x in items if self._figure_deep_score(x) > 0]
            if rich_items:
                if caption_items:
                    caption_candidates = [str(x.get("caption") or "").strip() for x in caption_items if str(x.get("caption") or "").strip()]
                    first_caption = caption_candidates[0] if caption_candidates else ""
                    merged_rich: List[Dict[str, Any]] = []
                    for item in rich_items:
                        candidate = dict(item)
                        if (not str(candidate.get("caption") or "").strip()) and first_caption:
                            candidate["caption"] = first_caption
                        merged_rich.append(candidate)
                    pruned.extend(merged_rich)
                else:
                    pruned.extend(rich_items)
                continue
            if caption_items:
                # OCR/native caption items are generally more stable on scanned pages;
                # avoid double-counting with additional vision figures on the same page.
                pruned.extend(caption_items)
                continue
            pruned.extend(items)
        pruned.sort(key=lambda x: (int(x.get("page", 0) or 0), str(x.get("figure_id", ""))))
        return pruned

    def _render_page_png_for_vision(self, page: Any) -> bytes:
        try:
            import fitz  # pymupdf
        except Exception:
            return b""

        scale = self.gemini_vision_dpi / 72.0
        matrix = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        max_side = max(pix.width, pix.height)
        if max_side > self.gemini_vision_max_side_px:
            shrink = self.gemini_vision_max_side_px / float(max_side)
            matrix = fitz.Matrix(scale * shrink, scale * shrink)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
        try:
            return pix.tobytes("png")
        except Exception:
            return b""

    def _vision_focus_from_page_lines(self, lines: List[str]) -> str:
        cue_text = " ".join([str(line or "") for line in lines[:40]])
        figure_hits = sum(1 for line in lines[:32] if self._contains_figure_marker(str(line or "")))
        figure_like = self._looks_like_figure_cue_text(cue_text) or figure_hits >= 2
        table_like = self._looks_like_table_cue_text(cue_text)
        if figure_like and not table_like:
            return "figure"
        if table_like and not figure_like:
            return "table"
        return "mixed"

    def _gemini_vision_extract_payload(self, image_png: bytes, focus: str = "mixed") -> Optional[Dict[str, Any]]:
        text = self._gemini_vision_generate(image_png, focus=focus)
        if not text:
            return None
        return self._extract_json_object(text)

    def _gemini_vision_generate(self, image_png: bytes, focus: str = "mixed") -> str:
        api_key = self._gemini_api_key()
        native_api_key = self._gemini_native_api_key()
        if not api_key and not native_api_key:
            return ""

        focus_key = str(focus or "mixed").strip().lower()
        if focus_key not in {"mixed", "table", "figure"}:
            focus_key = "mixed"

        if focus_key == "figure":
            prompt = (
                "Extract visible figure and chart information from this page image. "
                "Return strict JSON only, with no markdown fences. "
                "Return at most 4 figures. Do not return tables. "
                "Use this exact schema: "
                "{\"tables\":[],"
                "\"figures\":[{"
                "\"title\":\"\","
                "\"type\":\"chart|diagram|photo|other\","
                "\"caption\":\"\","
                "\"content_modes\":[\"dataframe|topology|text|visual\"],"
                "\"key_points\":[\"...\"],"
                "\"key_values\":[{\"name\":\"\",\"value\":\"\",\"unit\":\"\"}],"
                "\"axes\":{\"x\":\"\",\"y\":\"\"},"
                "\"legend\":[\"...\"],"
                "\"text_blocks\":[\"...\"],"
                "\"dataframe\":{\"headers\":[\"...\"],\"rows\":[[\"...\"],...]},"
                "\"topology\":{\"nodes\":[{\"id\":\"\",\"label\":\"\",\"type\":\"\"}],\"edges\":[{\"source\":\"\",\"target\":\"\",\"label\":\"\"}]}," 
                "\"confidence\":0.0"
                "}],"
                "\"insights\":[\"...\"]}. "
                "Keep output compact, but for charts and diagrams you should recover the fullest visible structured data you can. "
                "Preserve row order, series order, and axis order. Do not arbitrarily truncate visible dataframe headers or rows. "
                "If exact numeric values are visible, prefer dataframe and key_values over long prose. "
                "Do not invent values that are not visible."
            )
        elif focus_key == "table":
            prompt = (
                "Extract visible table information from this page image. "
                "Return strict JSON only, with no markdown fences. "
                "Return at most 3 tables. Do not return figures. "
                "Use this exact schema: "
                "{\"tables\":[{"
                "\"title\":\"\","
                "\"caption\":\"\","
                "\"headers\":[\"...\"],"
                "\"rows\":[[\"...\"],...],"
                "\"notes\":[\"...\"],"
                "\"confidence\":0.0"
                "}],"
                "\"figures\":[],"
                "\"insights\":[\"...\"]}. "
                "Keep output compact. For each table, keep at most 8 rows and 8 columns. "
                "Do not invent values that are not visible."
            )
        else:
            prompt = (
                "Extract visible structured information from this page image. "
                "Return strict JSON only, with no markdown fences. "
                "Use this exact schema: "
                "{\"tables\":[{\"title\":\"\",\"caption\":\"\",\"headers\":[\"...\"],\"rows\":[[\"...\"],...],\"notes\":[\"...\"],\"confidence\":0.0}],"
                "\"figures\":[{\"title\":\"\",\"type\":\"chart|diagram|photo|other\",\"caption\":\"\",\"content_modes\":[\"dataframe|topology|text|visual\"],"
                "\"key_points\":[\"...\"],\"key_values\":[{\"name\":\"\",\"value\":\"\",\"unit\":\"\"}],\"axes\":{\"x\":\"\",\"y\":\"\"},"
                "\"legend\":[\"...\"],\"text_blocks\":[\"...\"],\"dataframe\":{\"headers\":[\"...\"],\"rows\":[[\"...\"],...]},"
                "\"topology\":{\"nodes\":[{\"id\":\"\",\"label\":\"\",\"type\":\"\"}],\"edges\":[{\"source\":\"\",\"target\":\"\",\"label\":\"\"}]},\"confidence\":0.0}],"
                "\"insights\":[\"...\"]}. "
                "Keep output compact. Return at most 2 tables and 3 figures. "
                "For charts and diagrams, recover the fullest visible dataframe you can without inventing hidden values. "
                "Do not arbitrarily truncate visible headers, rows, or series labels. "
                "Do not invent values that are not visible."
            )

        model = self.gemini_vision_model.strip() or "gemini-3-pro"
        base_url = resolve_llm_base_url()
        if base_url:
            provider = OpenAICompatibleChatProvider(
                base_url=base_url,
                api_key=api_key,
                model=model,
                temperature=0.0,
                max_tokens=self.gemini_vision_max_output_tokens,
                timeout_sec=self.gemini_vision_timeout_sec,
            )
            if not provider.configured:
                return ""
            data_url = f"data:image/png;base64,{base64.b64encode(image_png).decode('ascii')}"
            try:
                result = provider.complete(
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {"type": "image_url", "image_url": {"url": data_url}},
                            ],
                        }
                    ],
                    temperature=0.0,
                    max_tokens=self.gemini_vision_max_output_tokens,
                    response_format={"type": "json_object"},
                    reasoning_effort=self.gemini_vision_reasoning_effort,
                )
            except Exception:
                if not (self.gemini_native_fallback_enabled and native_api_key):
                    return ""
            else:
                content = str(result.content or "").strip()
                if content:
                    return content
                if not (self.gemini_native_fallback_enabled and native_api_key):
                    return ""
        elif not (self.gemini_native_fallback_enabled and native_api_key):
            return ""

        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{urllib.parse.quote(model, safe='')}:generateContent"
            f"?key={urllib.parse.quote(native_api_key, safe='')}"
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": base64.b64encode(image_png).decode("ascii"),
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": self.gemini_vision_max_output_tokens,
                "responseMimeType": "application/json",
            },
        }

        def _post_json(payload_obj: Dict[str, Any]) -> str:
            req = urllib.request.Request(
                url=url,
                data=json.dumps(payload_obj, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.gemini_vision_timeout_sec) as resp:
                return resp.read().decode("utf-8", errors="ignore")

        try:
            raw = _post_json(payload)
        except urllib.error.HTTPError as http_exc:
            status = int(getattr(http_exc, "code", 0) or 0)
            if status != 400:
                return ""
            # Fallback for endpoints/models that reject responseMimeType.
            cfg = dict(payload.get("generationConfig", {}))
            cfg.pop("responseMimeType", None)
            payload_retry = dict(payload)
            payload_retry["generationConfig"] = cfg
            try:
                raw = _post_json(payload_retry)
            except Exception:
                return ""
        except Exception:
            return ""

        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return ""

        texts: List[str] = []
        for candidate in obj.get("candidates", []):
            content = candidate.get("content", {})
            for part in content.get("parts", []):
                txt = part.get("text")
                if isinstance(txt, str) and txt.strip():
                    texts.append(txt.strip())
        return "\n".join(texts)

    @staticmethod
    def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
        raw = str(text or "").strip()
        if not raw:
            return None

        fence = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", raw, flags=re.IGNORECASE)
        if fence:
            raw = fence.group(1).strip()

        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            pass

        start = raw.find("{")
        if start >= 0:
            depth = 0
            in_string = False
            escape_next = False
            for index, ch in enumerate(raw[start:], start=start):
                if in_string:
                    if escape_next:
                        escape_next = False
                    elif ch == "\\":
                        escape_next = True
                    elif ch == '"':
                        in_string = False
                    continue
                if ch == '"':
                    in_string = True
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        chunk = raw[start : index + 1]
                        try:
                            payload = json.loads(chunk)
                            if isinstance(payload, dict):
                                return payload
                        except json.JSONDecodeError:
                            pass

        starts = [idx for idx, ch in enumerate(raw) if ch == "{"]
        ends = [idx for idx, ch in enumerate(raw) if ch == "}"]
        for s in starts:
            for e in reversed(ends):
                if e <= s:
                    continue
                chunk = raw[s : e + 1]
                try:
                    payload = json.loads(chunk)
                    if isinstance(payload, dict):
                        return payload
                except json.JSONDecodeError:
                    continue
        return None

    def _extract_vision_insights(
        self,
        payload: Dict[str, Any],
        page_no: int,
        bbox_map: Dict[str, List[float]],
    ) -> List[Tuple[str, str]]:
        insights_raw = payload.get("insights", [])
        if not isinstance(insights_raw, list):
            return []

        existing = set(bbox_map.keys())
        out: List[Tuple[str, str]] = []
        max_insights = 4
        for idx, item in enumerate(insights_raw[:max_insights], start=1):
            text = self._normalize_text(str(item or ""))
            if not text:
                continue
            ref_id = f"gv_p{page_no}_s{idx}"
            if ref_id in existing:
                continue
            out.append((ref_id, text))
        return out

    def _build_tables_from_vision_payload(
        self,
        payload: Dict[str, Any],
        page_no: int,
        table_idx: int,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        source_prefix: str,
    ) -> Tuple[TableBlocks, int]:
        tables_raw = payload.get("tables", [])
        if not isinstance(tables_raw, list):
            return [], table_idx

        built: TableBlocks = []
        for table_raw in tables_raw[: self.gemini_vision_max_tables_per_page]:
            matrix = self._vision_table_to_matrix(table_raw)
            if len(matrix) < 2:
                continue

            table_id = f"{source_prefix}_t{table_idx}"
            table_idx += 1
            raw_rows_payload: List[Dict[str, Any]] = []
            for row_idx, row_vals in enumerate(matrix[: self.table_max_rows + 1], start=1):
                cells_payload: List[Dict[str, Any]] = []
                for col_idx, cell in enumerate(row_vals[: self.table_max_cols], start=1):
                    text = self._normalize_text(str(cell or ""))
                    if not text:
                        continue
                    ref_id = f"{table_id}_r{row_idx}_c{col_idx}"
                    if ref_id in bbox_map:
                        continue
                    parts.append(f'<ref id="{ref_id}">{escape(text)}</ref>')
                    bbox = [float(page_no), 0.0, 0.0, 1.0, 1.0]
                    bbox_map[ref_id] = bbox
                    cells_payload.append(
                        {
                            "col_index": col_idx,
                            "text": text,
                            "ref_id": ref_id,
                            "bbox": bbox,
                        }
                    )
                if cells_payload:
                    raw_rows_payload.append({"row_index": row_idx, "cells": cells_payload})
            if len(raw_rows_payload) < 2:
                continue

            headers, data_rows = self._infer_headers_and_data_rows(raw_rows_payload)
            data_rows = self._drop_redundant_header_like_rows(data_rows, headers)
            data_rows = self._decorate_rows_with_meta(data_rows, headers)
            if len(data_rows) < self.ocr_table_min_rows:
                continue
            if self._looks_like_false_table(headers, data_rows):
                continue

            confidence = self._to_float_or_none(table_raw.get("confidence")) if isinstance(table_raw, dict) else None
            if confidence is None:
                confidence = 0.74
            confidence = max(0.1, min(1.0, float(confidence)))
            built.append(
                {
                    "table_id": table_id,
                    "source": source_prefix,
                    "page": page_no,
                    "headers": headers,
                    "header_meta": self._build_header_meta(headers),
                    "rows": data_rows,
                    "row_count": len(data_rows),
                    "col_count": max((len(r.get("cells", [])) for r in data_rows), default=0),
                    "quality": round(confidence, 4),
                }
            )
        return built, table_idx

    def _vision_table_to_matrix(self, table_raw: Any) -> List[List[str]]:
        if not isinstance(table_raw, dict):
            return []

        matrix: List[List[str]] = []
        headers_raw = table_raw.get("headers", [])
        if isinstance(headers_raw, list):
            header_row = [self._normalize_text(str(x or "")) for x in headers_raw[: self.table_max_cols]]
            if any(header_row):
                matrix.append(header_row)

        rows_raw = table_raw.get("rows", [])
        if isinstance(rows_raw, list):
            for row in rows_raw[: self.table_max_rows]:
                vals: List[str] = []
                if isinstance(row, list):
                    vals = [self._normalize_text(str(x or "")) for x in row[: self.table_max_cols]]
                elif isinstance(row, dict):
                    row_cells = row.get("cells")
                    if isinstance(row_cells, list):
                        vals = [self._normalize_text(str(x or "")) for x in row_cells[: self.table_max_cols]]
                    else:
                        keys = sorted(k for k in row.keys() if str(k).lower() not in {"row_index"})
                        for key in keys[: self.table_max_cols]:
                            vals.append(self._normalize_text(str(row.get(key) or "")))
                if any(vals):
                    matrix.append(vals)

        return matrix

    @staticmethod
    def _to_float_or_none(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return None
            cleaned = re.sub(r"[,\s%\uFF05]", "", cleaned)
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

    def _prune_fragment_tables(self, table_blocks: TableBlocks) -> TableBlocks:
        if not table_blocks:
            return table_blocks

        robust_by_page: Dict[int, int] = {}
        robust_total = 0
        for table in table_blocks:
            rows = int(table.get("row_count", 0) or 0)
            cols = int(table.get("col_count", 0) or 0)
            if rows >= 2 and cols >= 2:
                robust_total += 1
                page_no = int(table.get("page", 0) or 0)
                if page_no > 0:
                    robust_by_page[page_no] = robust_by_page.get(page_no, 0) + 1

        if robust_total == 0:
            return table_blocks

        pruned: TableBlocks = []
        for table in table_blocks:
            rows = int(table.get("row_count", 0) or 0)
            cols = int(table.get("col_count", 0) or 0)
            page_no = int(table.get("page", 0) or 0)
            source = str(table.get("source", "") or "")
            cells = [
                cell
                for row in table.get("rows", [])
                for cell in row.get("cells", [])
                if isinstance(cell, dict)
            ]
            cell_count = len(cells)
            numeric_cells = sum(1 for cell in cells if re.search(r"\d", str(cell.get("text", ""))))
            same_page_has_robust = robust_by_page.get(page_no, 0) > 0

            if source == "pdf_ocr_layout":
                numeric_ratio = numeric_cells / float(max(cell_count, 1))
                section_cell_hits = sum(
                    1
                    for cell in cells
                    if self._contains_section_marker(str(cell.get("text", "")))
                )
                section_cell_ratio = section_cell_hits / float(max(cell_count, 1))
                headers = [self._normalize_text(str(h or "")) for h in table.get("headers", [])]
                headers = [h for h in headers if h]
                generic_headers = sum(1 for h in headers if self._header_token_is_generic(h))
                generic_ratio = (generic_headers / float(max(len(headers), 1))) if headers else 0.0
                if rows <= 3 and cols <= 3 and numeric_cells < 6:
                    continue
                if rows >= 10 and cols <= 3 and numeric_ratio < 0.45:
                    continue
                if rows >= 10 and cols >= 6 and numeric_ratio < 0.2 and section_cell_ratio >= 0.03:
                    continue
                if rows >= 8 and section_cell_ratio >= 0.04 and numeric_ratio < 0.35:
                    continue
                if generic_ratio >= 0.6 and numeric_ratio < 0.38:
                    continue

            if rows <= 1:
                keep_sparse_row = cols >= 4 and cell_count >= 4 and numeric_cells >= 3 and robust_total <= 1
                if keep_sparse_row and not same_page_has_robust:
                    pruned.append(table)
                continue
            if cols > 1:
                pruned.append(table)
                continue

            keep_long_single_column = rows >= 6 and cell_count >= 6 and numeric_cells >= 2
            keep_gemini_signal = source.startswith("pdf_gemini_vision") and rows >= 3 and cell_count >= 3
            if keep_long_single_column or keep_gemini_signal:
                pruned.append(table)
                continue

            if same_page_has_robust or robust_total >= 2:
                continue

            # Keep only if this is the sole evidence and has some numeric signal.
            if numeric_cells >= 2 and rows >= 3:
                pruned.append(table)

        out = pruned if pruned else table_blocks
        out = self._prune_ocr_layout_density(out)
        return self._prune_gemini_native_tables_per_page(out)

    def _prune_ocr_layout_density(self, table_blocks: TableBlocks) -> TableBlocks:
        if not table_blocks:
            return table_blocks
        by_page: Dict[int, List[Dict[str, Any]]] = {}
        for table in table_blocks:
            page_no = int(table.get("page", 0) or 0)
            by_page.setdefault(page_no, []).append(table)

        pruned: TableBlocks = []
        for page_no in sorted(by_page.keys()):
            page_tables = by_page.get(page_no, [])
            non_ocr = [t for t in page_tables if str(t.get("source", "")) != "pdf_ocr_layout"]
            ocr = [t for t in page_tables if str(t.get("source", "")) == "pdf_ocr_layout"]
            pruned.extend(non_ocr)
            if not ocr:
                continue

            candidates: List[Dict[str, Any]] = []
            for t in ocr:
                rows = int(t.get("row_count", 0) or 0)
                cols = int(t.get("col_count", 0) or 0)
                cells = [
                    c
                    for r in t.get("rows", [])
                    for c in r.get("cells", [])
                    if isinstance(c, dict)
                ]
                cell_count = len(cells)
                numeric_cells = sum(
                    1
                    for c in cells
                    if c.get("numeric_value") is not None or re.search(r"\d", str(c.get("text", "")))
                )
                numeric_ratio = numeric_cells / float(max(cell_count, 1))
                if cols <= 2 and numeric_ratio < 0.75:
                    continue
                if cols <= 3 and rows >= 8 and numeric_ratio < 0.65:
                    continue
                if cols <= 4 and rows <= 4 and numeric_ratio < 0.65:
                    continue
                candidates.append(t)

            if not candidates:
                continue
            candidates.sort(
                key=lambda x: (
                    float(x.get("quality", 0.0) or 0.0),
                    int(x.get("row_count", 0) or 0) * int(x.get("col_count", 0) or 0),
                ),
                reverse=True,
            )
            pruned.append(candidates[0])

        pruned.sort(key=lambda x: (int(x.get("page", 0) or 0), str(x.get("table_id", ""))))
        return pruned if pruned else table_blocks

    def _prune_gemini_native_tables_per_page(self, table_blocks: TableBlocks) -> TableBlocks:
        if not table_blocks:
            return table_blocks
        by_page: Dict[int, List[Dict[str, Any]]] = {}
        for table in table_blocks:
            page_no = int(table.get("page", 0) or 0)
            by_page.setdefault(page_no, []).append(table)

        out: TableBlocks = []
        for page_no in sorted(by_page.keys()):
            tables = by_page.get(page_no, [])
            native_vision = [t for t in tables if str(t.get("source", "")) == "pdf_gemini_vision_native"]
            others = [t for t in tables if str(t.get("source", "")) != "pdf_gemini_vision_native"]
            out.extend(others)
            if not native_vision:
                continue
            native_vision.sort(
                key=lambda x: (
                    float(x.get("quality", 0.0) or 0.0),
                    int(x.get("row_count", 0) or 0) * int(x.get("col_count", 0) or 0),
                ),
                reverse=True,
            )
            out.append(native_vision[0])

        out.sort(key=lambda x: (int(x.get("page", 0) or 0), str(x.get("table_id", ""))))
        return out if out else table_blocks

    def _parse_plain(self, file_bytes: bytes, ext: str = ".txt") -> Tuple[str, Dict[str, List[float]], TableBlocks]:
        decoded = ""
        for encoding in ("utf-8", "utf-8-sig", "gb18030", "gbk"):
            try:
                decoded = file_bytes.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if not decoded:
            decoded = file_bytes.decode("latin-1", errors="ignore")

        text = self._normalize_text(decoded)
        if not text:
            raise ValueError("Unsupported file type or empty plain text payload.")

        parts: List[str] = []
        bbox_map: Dict[str, List[float]] = {}
        table_blocks: TableBlocks = []
        figure_blocks: FigureBlocks = []

        chunks = self._split_page_text(text)
        for idx, chunk in enumerate(chunks, start=1):
            ref_id = f"text_{idx}"
            parts.append(f'<ref id="{ref_id}">{escape(chunk)}</ref>')
            bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]

        normalized_ext = (ext or ".txt").lower()
        if normalized_ext in {".md", ".markdown"}:
            md_tables = self._extract_markdown_tables(text, parts, bbox_map)
            if md_tables:
                table_blocks.extend(md_tables)
            md_figures = self._extract_markdown_figures(text, parts, bbox_map)
            if md_figures:
                figure_blocks.extend(md_figures[: self.nonpdf_figure_max])
        else:
            txt_tables = self._extract_plain_text_tables(text, parts, bbox_map)
            if txt_tables:
                table_blocks.extend(txt_tables)
            txt_figures = self._extract_text_figure_cues(text, parts, bbox_map)
            if txt_figures:
                figure_blocks.extend(txt_figures[: self.nonpdf_figure_max])

        self._last_parse_stats = {
            "plain_ext": normalized_ext,
            "plain_text_chars": len(text),
            "plain_ref_count": len(bbox_map),
            "plain_table_count": len(table_blocks),
            "plain_figure_count": len(figure_blocks),
        }
        self._last_figure_blocks = self._merge_figure_blocks([], figure_blocks)
        return "\n".join(parts), bbox_map, table_blocks

    def _extract_markdown_tables(
        self,
        text: str,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
    ) -> TableBlocks:
        lines = text.splitlines()
        table_blocks: TableBlocks = []
        table_idx = 1
        line_idx = 0

        while line_idx + 1 < len(lines):
            head_line = lines[line_idx].strip()
            sep_line = lines[line_idx + 1].strip()
            if head_line.count("|") < 2 or not self._is_markdown_table_separator(sep_line):
                line_idx += 1
                continue

            headers = self._split_markdown_row(head_line)
            if len(headers) < 2:
                line_idx += 1
                continue

            data_rows_raw: List[List[str]] = []
            cursor = line_idx + 2
            while cursor < len(lines):
                row_line = lines[cursor].strip()
                if row_line.count("|") < 2:
                    break
                row_cells = self._split_markdown_row(row_line)
                if len(row_cells) < 2:
                    break
                data_rows_raw.append(row_cells)
                cursor += 1

            if not data_rows_raw:
                line_idx += 1
                continue

            table_id = f"md_t{table_idx}"
            table_idx += 1
            rows_payload: List[Dict[str, Any]] = []
            for row_idx, row_cells in enumerate(data_rows_raw[: self.table_max_rows], start=1):
                cells_payload: List[Dict[str, Any]] = []
                for col_idx, cell_text in enumerate(row_cells[: self.table_max_cols], start=1):
                    normalized_cell = self._normalize_text(cell_text)
                    if not normalized_cell:
                        continue
                    ref_id = f"{table_id}_r{row_idx}_c{col_idx}"
                    parts.append(f'<ref id="{ref_id}">{escape(normalized_cell)}</ref>')
                    bbox = [1.0, 0.0, 0.0, 1.0, 1.0]
                    bbox_map[ref_id] = bbox
                    cells_payload.append(
                        {
                            "col_index": col_idx,
                            "text": normalized_cell,
                            "ref_id": ref_id,
                            "bbox": bbox,
                        }
                    )
                if cells_payload:
                    rows_payload.append({"row_index": row_idx, "cells": cells_payload})

            if rows_payload:
                header_vals = [
                    (self._normalize_text(headers[idx]) or f"col_{idx+1}")
                    for idx in range(min(len(headers), self.table_max_cols))
                ]
                decorated_rows = self._decorate_rows_with_meta(rows_payload, header_vals)
                table_blocks.append(
                    {
                        "table_id": table_id,
                        "source": "md",
                        "page": 1,
                        "headers": header_vals,
                        "header_meta": self._build_header_meta(header_vals),
                        "rows": decorated_rows,
                        "row_count": len(decorated_rows),
                        "col_count": max((len(r.get("cells", [])) for r in decorated_rows), default=0),
                        "quality": 0.88,
                    }
                )

            line_idx = cursor

        return table_blocks

    def _extract_markdown_figures(
        self,
        text: str,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
    ) -> FigureBlocks:
        figures: FigureBlocks = []
        links = re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", text)
        for idx, (alt, src) in enumerate(links[: self.nonpdf_figure_max], start=1):
            caption = self._normalize_text(alt) or f"Markdown图像 {idx}"
            src_norm = self._normalize_text(src)
            ref_id = f"md_fig_{idx}"
            snippet = f"{caption} ({src_norm})" if src_norm else caption
            parts.append(f'<ref id="{ref_id}">{escape(snippet)}</ref>')
            bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]
            figure_type = "chart" if self._looks_like_figure_cue_text(f"{caption} {src_norm}") else "photo"
            figures.append(
                {
                    "figure_id": f"md_f{idx}",
                    "source": "md",
                    "page": 1,
                    "figure_type": figure_type,
                    "caption": caption,
                    "key_points": [src_norm] if src_norm else [],
                    "quality": 0.72,
                    "ref_ids": [ref_id],
                    "bbox_norm": [0.0, 0.0, 1.0, 1.0],
                }
            )
        return figures

    def _extract_plain_text_tables(
        self,
        text: str,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
    ) -> TableBlocks:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        groups: List[List[List[str]]] = []
        current: List[List[str]] = []

        def _split_line(raw_line: str) -> List[str]:
            if "\t" in raw_line:
                cells = [self._normalize_text(x) for x in raw_line.split("\t")]
            elif raw_line.count(",") >= 2:
                cells = [self._normalize_text(x) for x in raw_line.split(",")]
            else:
                cells = [self._normalize_text(x) for x in re.split(r"\s{2,}", raw_line)]
            return [c for c in cells if c]

        for line in lines:
            cells = _split_line(line)
            if len(cells) >= 3:
                current.append(cells[: self.table_max_cols])
                continue
            if len(current) >= 3:
                groups.append(current)
            current = []
        if len(current) >= 3:
            groups.append(current)

        table_blocks: TableBlocks = []
        table_idx = 1
        for group in groups[:8]:
            header_vals = [self._normalize_text(x) or f"col_{idx+1}" for idx, x in enumerate(group[0])]
            rows_payload: List[Dict[str, Any]] = []
            for row_idx, row_cells in enumerate(group[1 : self.table_max_rows + 1], start=1):
                cells_payload: List[Dict[str, Any]] = []
                for col_idx, cell_text in enumerate(row_cells[: self.table_max_cols], start=1):
                    normalized_cell = self._normalize_text(cell_text)
                    if not normalized_cell:
                        continue
                    ref_id = f"txt_t{table_idx}_r{row_idx}_c{col_idx}"
                    parts.append(f'<ref id="{ref_id}">{escape(normalized_cell)}</ref>')
                    bbox = [1.0, 0.0, 0.0, 1.0, 1.0]
                    bbox_map[ref_id] = bbox
                    cells_payload.append(
                        {
                            "col_index": col_idx,
                            "text": normalized_cell,
                            "ref_id": ref_id,
                            "bbox": bbox,
                        }
                    )
                if cells_payload:
                    rows_payload.append({"row_index": row_idx, "cells": cells_payload})
            if not rows_payload:
                continue
            decorated_rows = self._decorate_rows_with_meta(rows_payload, header_vals)
            table_blocks.append(
                {
                    "table_id": f"txt_t{table_idx}",
                    "source": "txt",
                    "page": 1,
                    "headers": header_vals,
                    "header_meta": self._build_header_meta(header_vals),
                    "rows": decorated_rows,
                    "row_count": len(decorated_rows),
                    "col_count": max((len(r.get("cells", [])) for r in decorated_rows), default=0),
                    "quality": 0.66,
                }
            )
            table_idx += 1

        return table_blocks

    def _extract_text_figure_cues(
        self,
        text: str,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
    ) -> FigureBlocks:
        lines = [self._normalize_text(line) for line in text.splitlines()]
        lines = [line for line in lines if line]
        figure_lines = [line for line in lines if self._looks_like_figure_cue_text(line)]
        figures: FigureBlocks = []
        for idx, line in enumerate(figure_lines[: self.nonpdf_figure_max], start=1):
            ref_id = f"txt_fig_{idx}"
            parts.append(f'<ref id="{ref_id}">{escape(line)}</ref>')
            bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]
            figures.append(
                {
                    "figure_id": f"txt_f{idx}",
                    "source": "txt",
                    "page": 1,
                    "figure_type": "chart",
                    "caption": line[:120],
                    "key_points": [line[:200]],
                    "quality": 0.58,
                    "ref_ids": [ref_id],
                    "bbox_norm": [0.0, 0.0, 1.0, 1.0],
                }
            )
        return figures

    @staticmethod
    def _is_markdown_table_separator(line: str) -> bool:
        tokens = [token.strip() for token in line.strip().strip("|").split("|")]
        if len(tokens) < 2:
            return False
        for token in tokens:
            core = token.replace(":", "").replace("-", "")
            if core:
                return False
            if token.count("-") < 3:
                return False
        return True

    @staticmethod
    def _split_markdown_row(line: str) -> List[str]:
        raw = line.strip().strip("|")
        return [cell.strip() for cell in raw.split("|")]

    def _infer_pdf_tables(
        self,
        page_texts: List[str],
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        source: str,
    ) -> TableBlocks:
        page_lines: Dict[int, List[str]] = {}
        for idx, text in enumerate(page_texts, start=1):
            lines = [self._normalize_text(line) for line in text.splitlines()]
            lines = [line for line in lines if line]
            if lines:
                page_lines[idx] = lines
        return self._infer_tables_from_page_lines(page_lines, parts, bbox_map, source=source)

    def _extract_pdf_tables_with_fitz(
        self,
        file_bytes: bytes,
        page_count: int,
        parts: List[str],
        bbox_map: Dict[str, List[float]],
    ) -> TableBlocks:
        try:
            import fitz  # pymupdf
        except Exception:
            return []

        table_blocks: TableBlocks = []
        emitted_cells = 0
        table_idx = 1

        try:
            doc = fitz.open(stream=file_bytes, filetype="pdf")
        except Exception:
            return []

        try:
            for page_idx in range(min(page_count, len(doc))):
                page = doc.load_page(page_idx)
                page_no = page_idx + 1
                if not hasattr(page, "find_tables"):
                    continue

                try:
                    finder = page.find_tables()
                except Exception:
                    continue

                tables = getattr(finder, "tables", None) or []
                for table in tables:
                    if emitted_cells >= self.table_cell_cap:
                        break

                    try:
                        matrix = table.extract()
                    except Exception:
                        continue
                    if not matrix or len(matrix) < 2:
                        continue

                    rows_cleaned: List[List[str]] = []
                    for row in matrix[: self.table_max_rows + 1]:
                        vals: List[str] = []
                        for cell in list(row)[: self.table_max_cols]:
                            text = self._normalize_text("" if cell is None else str(cell))
                            vals.append(text)
                        if any(vals):
                            rows_cleaned.append(vals)
                    if len(rows_cleaned) < 2:
                        continue

                    header_width = min(
                        self.table_max_cols,
                        max(len(rows_cleaned[0]), max((len(r) for r in rows_cleaned[1:]), default=0)),
                    )
                    header_seed = rows_cleaned[0] + ([""] * max(0, header_width - len(rows_cleaned[0])))
                    headers = [
                        (self._normalize_text(raw_h) or f"col_{idx}")
                        for idx, raw_h in enumerate(header_seed[:header_width], start=1)
                    ]
                    data_rows = rows_cleaned[1:]
                    table_id = f"pdf_fitz_t{table_idx}"
                    table_bbox = self._normalize_table_bbox(getattr(table, "bbox", None), page.rect.width, page.rect.height)

                    rows_payload: List[Dict[str, Any]] = []
                    for row_idx, vals in enumerate(data_rows, start=1):
                        cells_payload: List[Dict[str, Any]] = []
                        for col_idx, text in enumerate(vals[: self.table_max_cols], start=1):
                            if not text:
                                continue
                            ref_id = f"{table_id}_r{row_idx}_c{col_idx}"
                            if ref_id in bbox_map:
                                continue
                            parts.append(f'<ref id="{ref_id}">{escape(text)}</ref>')
                            bbox = [float(page_no), table_bbox[0], table_bbox[1], table_bbox[2], table_bbox[3]]
                            bbox_map[ref_id] = bbox
                            cells_payload.append(
                                {
                                    "col_index": col_idx,
                                    "text": text,
                                    "ref_id": ref_id,
                                    "bbox": bbox,
                                }
                            )
                            emitted_cells += 1
                            if emitted_cells >= self.table_cell_cap:
                                break
                        if cells_payload:
                            rows_payload.append({"row_index": row_idx, "cells": cells_payload})
                        if emitted_cells >= self.table_cell_cap:
                            break

                    if rows_payload:
                        rows_payload = self._decorate_rows_with_meta(rows_payload, headers)
                        table_blocks.append(
                            {
                                "table_id": table_id,
                                "source": "pdf_fitz",
                                "page": page_no,
                                "headers": headers,
                                "header_meta": self._build_header_meta(headers),
                                "rows": rows_payload,
                                "row_count": len(rows_payload),
                                "col_count": max((len(r.get("cells", [])) for r in rows_payload), default=0),
                            }
                        )
                        table_idx += 1

                if emitted_cells >= self.table_cell_cap:
                    break
        finally:
            doc.close()

        if table_blocks and self.table_merge_enable:
            table_blocks = self._merge_same_page_tables(table_blocks)
            table_blocks = self._merge_cross_page_tables(table_blocks)
        return table_blocks

    @staticmethod
    def _normalize_table_bbox(raw_bbox: Any, width: float, height: float) -> Tuple[float, float, float, float]:
        if not raw_bbox or not isinstance(raw_bbox, (list, tuple)) or len(raw_bbox) < 4:
            return 0.0, 0.0, 1.0, 1.0
        try:
            x0 = max(0.0, float(raw_bbox[0])) / max(float(width), 1.0)
            y0 = max(0.0, float(raw_bbox[1])) / max(float(height), 1.0)
            x1 = max(0.0, float(raw_bbox[2])) / max(float(width), 1.0)
            y1 = max(0.0, float(raw_bbox[3])) / max(float(height), 1.0)
            return x0, y0, max(0.0, x1 - x0), max(0.0, y1 - y0)
        except (TypeError, ValueError):
            return 0.0, 0.0, 1.0, 1.0

    def _infer_headers_and_data_rows(
        self, rows_payload: List[Dict[str, Any]]
    ) -> Tuple[List[str], List[Dict[str, Any]]]:
        if not rows_payload:
            return [], []

        def _row_texts(row: Dict[str, Any]) -> List[str]:
            cells = sorted(row.get("cells", []), key=lambda c: int(c.get("col_index", 0) or 0))
            return [self._normalize_text(str(c.get("text", ""))) for c in cells]

        rows_text = [_row_texts(r) for r in rows_payload]
        row1 = rows_text[0]
        col_count = max(len(row1), max((len(r.get("cells", [])) for r in rows_payload), default=0))

        header_start = 0
        if self._is_caption_like_header_row(row1, col_count) and len(rows_payload) >= 2:
            header_start = 1
            row1 = rows_text[header_start]

        headers = row1[:] if row1 else [f"col_{i+1}" for i in range(col_count)]
        data_rows = rows_payload[header_start + 1 :] if len(rows_payload) > (header_start + 1) else []

        if len(rows_payload) >= (header_start + 2):
            row2 = rows_text[header_start + 1]
            if self._is_unit_row(row2):
                merged = self._merge_header_rows(row1, row2, col_count)
                if any(merged):
                    headers = merged
                    data_rows = (
                        rows_payload[header_start + 2 :]
                        if len(rows_payload) > (header_start + 2)
                        else rows_payload[header_start + 1 :]
                    )
            elif len(rows_payload) >= (header_start + 4) and self._should_merge_hierarchical_header_rows(
                row1, row2, col_count
            ):
                merged = self._merge_header_rows(row1, row2, col_count)
                if any(merged):
                    headers = merged
                    data_rows = (
                        rows_payload[header_start + 2 :]
                        if len(rows_payload) > (header_start + 2)
                        else rows_payload[header_start + 1 :]
                    )

        if not self._looks_like_header_row(headers):
            if len(rows_payload) >= (header_start + 2):
                alt_header = rows_text[header_start + 1]
                if self._looks_like_header_row(alt_header):
                    headers = alt_header[:]
                    data_rows = (
                        rows_payload[header_start + 2 :]
                        if len(rows_payload) > (header_start + 2)
                        else rows_payload[header_start + 1 :]
                    )
                else:
                    headers = [f"col_{i+1}" for i in range(max(col_count, 1))]
                    data_rows = rows_payload[header_start:]
            else:
                headers = [f"col_{i+1}" for i in range(max(col_count, 1))]
                data_rows = rows_payload[header_start:]

        headers = [h if h else f"col_{i+1}" for i, h in enumerate(headers)]
        return headers, data_rows

    def _should_merge_hierarchical_header_rows(self, row1: List[str], row2: List[str], col_count: int) -> bool:
        if col_count < 4:
            return False
        if int(getattr(self, "_runtime_page_count", 0) or 0) > 120:
            return False
        vals1 = [self._normalize_text(v) for v in row1 if self._normalize_text(v)]
        vals2 = [self._normalize_text(v) for v in row2 if self._normalize_text(v)]
        if not vals1 or not vals2:
            return False
        if self._is_unit_row(row2):
            return False
        if self._contains_figure_marker(" ".join(vals1 + vals2)):
            return False
        if not self._looks_like_header_row(row2):
            return False

        fill1 = len(vals1) / float(max(col_count, 1))
        fill2 = len(vals2) / float(max(col_count, 1))
        numeric_like2 = sum(
            1
            for v in vals2
            if re.search(r"\d", v) and not re.search(r"[A-Za-z\u4e00-\u9fa5]", v)
        )
        numeric_ratio2 = numeric_like2 / float(max(len(vals2), 1))

        if numeric_ratio2 > 0.45:
            return False
        if fill1 <= 0.6 and fill2 >= 0.55 and len(vals2) >= 2:
            return True
        if fill1 <= 0.5 and len(vals2) >= 3:
            return True
        return False

    def _is_caption_like_header_row(self, values: List[str], col_count: int) -> bool:
        non_empty = [self._normalize_text(v) for v in values if self._normalize_text(v)]
        if not non_empty:
            return False
        joined = " ".join(non_empty)
        lower = joined.lower()
        if len(non_empty) <= 2:
            if re.search(r"\btable\b\s*[a-z0-9.\-]*", lower):
                return True
            if re.search(r"^\s*表\s*[0-9A-Za-z一二三四五六七八九十.\-]*", joined):
                return True
            if "续表" in joined:
                return True
        if len(non_empty) == 1 and len(non_empty[0]) >= 20:
            if self._contains_catalog_marker(joined):
                return True
            if re.search(r"\btable\b", lower):
                return True
        if len(non_empty) <= max(2, col_count // 3) and self._contains_catalog_marker(joined):
            return True
        return False

    def _is_unit_row(self, values: List[str]) -> bool:
        if not values:
            return False
        non_empty = [v for v in values if v]
        if not non_empty:
            return False
        unit_like = sum(1 for v in non_empty if self._is_unit_like_token(v))
        return unit_like / float(len(non_empty)) >= 0.6

    @staticmethod
    def _is_unit_like_token_legacy(text: str) -> bool:
        return NativeDocumentParser._is_unit_like_token(text)

    @staticmethod
    def _merge_header_rows(row1: List[str], row2: List[str], col_count: int) -> List[str]:
        merged: List[str] = []
        for i in range(col_count):
            h1 = row1[i] if i < len(row1) else ""
            h2 = row2[i] if i < len(row2) else ""
            if h1 and h2:
                merged.append(f"{h1} ({h2})")
            elif h1:
                merged.append(h1)
            elif h2:
                merged.append(h2)
            else:
                merged.append("")
        return merged

    def _looks_like_header_row(self, headers: List[str]) -> bool:
        vals = [h.strip() for h in headers if h and h.strip()]
        if not vals:
            return False
        numeric_only = sum(1 for v in vals if re.fullmatch(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", v))
        if numeric_only / float(len(vals)) > 0.5:
            return False
        return True

    def _drop_redundant_header_like_rows(
        self, rows_payload: List[Dict[str, Any]], headers: List[str]
    ) -> List[Dict[str, Any]]:
        if not rows_payload:
            return rows_payload
        header_norm = [self._normalize_token_for_compare(h) for h in headers]
        filtered: List[Dict[str, Any]] = []
        for row in rows_payload:
            cells = sorted(row.get("cells", []), key=lambda c: int(c.get("col_index", 0) or 0))
            row_vals = [self._normalize_token_for_compare(str(c.get("text", ""))) for c in cells]
            row_vals = row_vals[: len(header_norm)]
            if not row_vals:
                continue

            match = 0
            comparable = 0
            has_number = False
            for i, val in enumerate(row_vals):
                if not val:
                    continue
                if re.search(r"\d", val):
                    has_number = True
                hv = header_norm[i] if i < len(header_norm) else ""
                if hv:
                    comparable += 1
                    if val == hv:
                        match += 1
            ratio = (match / float(comparable)) if comparable else 0.0
            if ratio >= 0.7 and not has_number:
                continue
            filtered.append(row)
        return filtered

    @staticmethod
    def _normalize_token_for_compare_legacy(text: str) -> str:
        t = str(text or "").strip().lower()
        t = re.sub(r"[\s\(\)\[\]（）【】<>/\\,.;:：，、\-_]+", "", t)
        return t

    def _build_header_meta(self, headers: List[str]) -> List[Dict[str, Any]]:
        meta: List[Dict[str, Any]] = []
        for idx, raw in enumerate(headers, start=1):
            name, unit = self._extract_header_name_and_unit(raw)
            meta.append(
                {
                    "col_index": idx,
                    "raw": raw,
                    "name": name,
                    "name_norm": self._normalize_token_for_compare(name),
                    "unit": unit,
                }
            )
        return meta

    def _decorate_rows_with_meta(self, rows_payload: List[Dict[str, Any]], headers: List[str]) -> List[Dict[str, Any]]:
        header_meta = self._build_header_meta(headers)
        header_map = {int(h.get("col_index", 0)): h for h in header_meta}
        decorated: List[Dict[str, Any]] = []
        row_idx = 1
        for row in rows_payload:
            cells = sorted(row.get("cells", []), key=lambda c: int(c.get("col_index", 0) or 0))
            out_cells: List[Dict[str, Any]] = []
            for cell in cells:
                col_idx = int(cell.get("col_index", 0) or 0)
                text = self._normalize_text(str(cell.get("text", "")))
                if not text:
                    continue
                hmeta = header_map.get(col_idx, {"name": f"col_{col_idx}", "name_norm": "", "unit": None})
                num_meta = self._extract_number_meta(text, hmeta.get("unit"))
                out = dict(cell)
                out.update(
                    {
                        "text": text,
                        "header": hmeta.get("name"),
                        "header_norm": hmeta.get("name_norm"),
                        "header_unit": hmeta.get("unit"),
                        "value_type": num_meta.get("value_type"),
                        "numeric_value": num_meta.get("numeric_value"),
                        "ratio_value": num_meta.get("ratio_value"),
                        "detected_unit": num_meta.get("detected_unit"),
                        "normalized_text": num_meta.get("normalized_text"),
                    }
                )
                out_cells.append(out)
            if out_cells:
                source_row_index = int(row.get("row_index", row_idx) or row_idx)
                decorated.append(
                    {
                        "row_index": row_idx,
                        "source_row_index": source_row_index,
                        "cells": out_cells,
                    }
                )
                row_idx += 1
        return decorated

    def _extract_header_name_and_unit_legacy(self, raw_header: str) -> Tuple[str, Optional[str]]:
        text = self._normalize_text(str(raw_header or ""))
        if not text:
            return "", None
        m = re.match(r"^(.*?)[\(\[（](.+?)[\)\]）]\s*$", text)
        if m:
            name = self._normalize_text(m.group(1))
            unit = self._normalize_text(m.group(2))
            return name or text, unit or None
        # Common compact style: 温度/℃ or flow(L/h)
        m2 = re.match(r"^(.*?)[/／]\s*([%°℃a-zA-Z0-9·\-]+)$", text)
        if m2 and len(m2.group(2)) <= 16:
            name = self._normalize_text(m2.group(1))
            unit = self._normalize_text(m2.group(2))
            return name or text, unit or None
        return text, None

    def _extract_number_meta_legacy(self, text: str, unit_hint: Optional[str]) -> Dict[str, Any]:
        return self._extract_number_meta(text, unit_hint)

    def _build_ocr_page_indices(self, page_count: int, cue_pages: List[int] | None = None) -> List[int]:
        if page_count <= 0:
            return []

        def _even_sample(source: List[int], n: int) -> List[int]:
            if n <= 0 or not source:
                return []
            if n >= len(source):
                return source[:]
            if n == 1:
                return [source[len(source) // 2]]
            step = (len(source) - 1) / float(n - 1)
            picked = [source[int(round(i * step))] for i in range(n)]
            seen_local = set()
            out_local: List[int] = []
            for idx_local in picked:
                if idx_local in seen_local:
                    continue
                seen_local.add(idx_local)
                out_local.append(idx_local)
            if len(out_local) < n:
                for idx_local in source:
                    if idx_local in seen_local:
                        continue
                    seen_local.add(idx_local)
                    out_local.append(idx_local)
                    if len(out_local) >= n:
                        break
            return out_local

        def _interleave_edges(source: List[int]) -> List[int]:
            if not source:
                return []
            out_local: List[int] = []
            left = 0
            right = len(source) - 1
            while left <= right:
                out_local.append(source[left])
                left += 1
                if left <= right:
                    out_local.append(source[right])
                    right -= 1
            return out_local

        first_span = min(page_count, self.ocr_max_pages)
        if not cue_pages and self.ocr_front_scan_pages > first_span:
            first_span = min(page_count, self.ocr_front_scan_pages)
        first_indices: List[int] = list(range(first_span))
        base_extra_indices: List[int] = []
        remaining = list(range(first_span, page_count))
        if remaining and self.ocr_extra_sample_pages > 0:
            extra = min(len(remaining), self.ocr_extra_sample_pages)
            base_extra_indices = _even_sample(remaining, extra)
        base_indices: List[int] = first_indices + base_extra_indices

        cue_indices: List[int] = []
        if cue_pages:
            valid_cues = sorted(set(int(p) for p in cue_pages if isinstance(p, int) and 0 <= int(p) < page_count))
            expanded: List[int] = []
            for page_idx in valid_cues:
                for delta in range(-self.ocr_cue_neighbor, self.ocr_cue_neighbor + 1):
                    cur = page_idx + delta
                    if 0 <= cur < page_count:
                        expanded.append(cur)
            cue_indices = sorted(set(expanded))
            if self.ocr_cue_max_pages > 0 and len(cue_indices) > self.ocr_cue_max_pages:
                cue_indices = sorted(_even_sample(cue_indices, self.ocr_cue_max_pages))

        hard_cap_base = min(page_count, self.ocr_max_scan_pages)
        if cue_indices:
            cue_cap = min(page_count, self.ocr_cue_boost_max_pages, max(first_span, len(cue_indices)))
            hard_cap = max(hard_cap_base, cue_cap)
        else:
            hard_cap = hard_cap_base
        target_by_ratio = int(round(page_count * self.ocr_min_coverage_ratio))
        target = max(len(base_indices), self.ocr_min_scan_pages, target_by_ratio)
        target = min(hard_cap, target)

        selected_set = set(i for i in (base_indices + cue_indices) if 0 <= i < page_count)
        if len(selected_set) < target:
            universe = [i for i in range(page_count) if i not in selected_set]
            for idx_local in _even_sample(universe, target - len(selected_set)):
                selected_set.add(idx_local)

        mandatory: List[int] = []
        mandatory_seen = set()
        for idx_local in first_indices + cue_indices + base_extra_indices:
            if idx_local in selected_set and idx_local not in mandatory_seen:
                mandatory.append(idx_local)
                mandatory_seen.add(idx_local)

        if len(selected_set) > hard_cap:
            if len(mandatory) > hard_cap:
                mandatory = _even_sample(mandatory, hard_cap)
                mandatory_seen = set(mandatory)
            rest = sorted(i for i in selected_set if i not in mandatory_seen)
            slots = max(0, hard_cap - len(mandatory))
            trimmed = set(mandatory)
            for idx_local in _even_sample(rest, slots):
                trimmed.add(idx_local)
            selected_set = trimmed

        ordered: List[int] = []
        seen = set()

        def _append(idx_local: int) -> None:
            if idx_local in selected_set and idx_local not in seen:
                ordered.append(idx_local)
                seen.add(idx_local)

        for idx_local in mandatory:
            _append(idx_local)

        remaining_sorted = sorted(i for i in selected_set if i not in seen)
        if remaining_sorted:
            anchor_n = min(len(remaining_sorted), max(6, min(24, target // 2 if target > 0 else 6)))
            anchors = _even_sample(remaining_sorted, anchor_n)
            for idx_local in _interleave_edges(anchors):
                _append(idx_local)
            for idx_local in _interleave_edges(remaining_sorted):
                _append(idx_local)

        return ordered

    def _need_line_table_augmentation(
        self,
        table_blocks: TableBlocks,
        page_lines: Dict[int, List[str]],
    ) -> bool:
        if not page_lines:
            return False
        if not table_blocks:
            return True

        if len(table_blocks) < self.visual_weak_table_min:
            return True

        quality_vals: List[float] = []
        for t in table_blocks:
            try:
                q = float(t.get("quality"))
                quality_vals.append(q)
            except (TypeError, ValueError):
                continue
        if not quality_vals:
            return True

        avg_q = sum(quality_vals) / float(max(len(quality_vals), 1))
        low_q = sum(1 for x in quality_vals if x < max(self.ocr_table_min_quality + 0.08, 0.72))
        low_ratio = low_q / float(max(len(quality_vals), 1))
        if avg_q < 0.8 and low_ratio >= 0.34:
            return True
        return False

    def _select_line_augmentation_pages(
        self,
        page_lines: Dict[int, List[str]],
        base_tables: TableBlocks,
        cue_pages: List[int] | None = None,
    ) -> Dict[int, List[str]]:
        if not page_lines:
            return {}
        if not base_tables:
            return page_lines

        focus_pages = set()
        for t in base_tables:
            p = int(t.get("page", 0) or 0)
            if p <= 0:
                continue
            focus_pages.add(p)
            focus_pages.add(p - 1)
            focus_pages.add(p + 1)

        cue_candidates = sorted(
            {
                int(page_idx) + 1
                for page_idx in (cue_pages or [])
                if isinstance(page_idx, int) and (int(page_idx) + 1) in page_lines
            }
        )
        if cue_candidates and self.ocr_line_aug_max_extra_cue_pages > 0:
            if len(cue_candidates) > self.ocr_line_aug_max_extra_cue_pages:
                step = (len(cue_candidates) - 1) / float(max(self.ocr_line_aug_max_extra_cue_pages - 1, 1))
                cue_candidates = sorted(
                    {
                        cue_candidates[int(round(i * step))]
                        for i in range(self.ocr_line_aug_max_extra_cue_pages)
                    }
                )
            for p in cue_candidates:
                focus_pages.add(p)

        cue_text_pages = [
            p
            for p, lines in page_lines.items()
            if self._looks_like_table_cue_text(" ".join(lines[:18]))
        ]
        if cue_text_pages and self.ocr_line_aug_max_extra_cue_pages > 0:
            if len(cue_text_pages) > self.ocr_line_aug_max_extra_cue_pages:
                step = (len(cue_text_pages) - 1) / float(max(self.ocr_line_aug_max_extra_cue_pages - 1, 1))
                cue_text_pages = sorted(
                    {
                        cue_text_pages[int(round(i * step))]
                        for i in range(self.ocr_line_aug_max_extra_cue_pages)
                    }
                )
            for p in cue_text_pages:
                focus_pages.add(p)

        valid = sorted(p for p in focus_pages if p in page_lines)
        if not valid:
            return page_lines

        hard_limit = max(18, min(64, self.ocr_max_scan_pages // 2))
        if len(valid) <= hard_limit:
            return {p: page_lines[p] for p in valid}

        step = (len(valid) - 1) / float(max(hard_limit - 1, 1))
        sampled = [valid[int(round(i * step))] for i in range(hard_limit)]
        sampled = sorted(set(sampled))
        return {p: page_lines[p] for p in sampled}

    def _select_uncovered_table_like_pages(
        self,
        page_lines: Dict[int, List[str]],
        base_tables: TableBlocks,
        aggressive: bool = False,
    ) -> Dict[int, List[str]]:
        if not page_lines or not base_tables or self.ocr_uncovered_line_aug_pages <= 0:
            return {}
        covered_pages = {
            int(t.get("page", 0) or 0)
            for t in base_tables
            if int(t.get("page", 0) or 0) > 0
        }
        total_page_count = max(len(page_lines), 1)
        coverage_ratio = len(covered_pages) / float(total_page_count)
        min_table_line_hits = 2 if aggressive else 3
        min_numeric_line_hits = 1 if aggressive else 2
        min_score = 6 if aggressive else 9
        if coverage_ratio < 0.22:
            min_score = max(5 if aggressive else 8, min_score - 1)
        max_pages = self.ocr_uncovered_line_aug_pages + (4 if aggressive else 0)
        if coverage_ratio < 0.22:
            max_pages += 2
        if aggressive and total_page_count >= 80:
            max_pages += min(6, total_page_count // 40)
        max_pages = max(
            self.ocr_uncovered_line_aug_pages,
            min(max_pages, max(12, self.ocr_uncovered_line_aug_pages * 3)),
        )
        candidates: List[Tuple[int, int]] = []
        for page_no, lines in page_lines.items():
            if page_no in covered_pages:
                continue
            if not lines:
                continue

            score = 0
            if self._looks_like_table_cue_text(" ".join(lines[:24])):
                score += 2
            if (page_no - 1) in covered_pages or (page_no + 1) in covered_pages:
                score += 2
            if re.search(r"\btable\b|^\s*\u8868\s*[0-9A-Za-z\u4e00-\u9fa5.\-]*", " ".join(lines[:20]), re.IGNORECASE):
                score += 2

            table_line_hits = 0
            numeric_line_hits = 0
            for line in lines[:160]:
                tokens = self._split_table_line(line)
                if not self._is_table_line(line, tokens):
                    continue
                table_line_hits += 1
                score += 1
                numeric_hits = sum(1 for t in tokens if re.search(r"\d", t))
                if numeric_hits >= 2:
                    numeric_line_hits += 1
                    score += 1
                if len(tokens) >= 5:
                    score += 1
            if table_line_hits >= min_table_line_hits and numeric_line_hits >= min_numeric_line_hits and score >= min_score:
                candidates.append((score, page_no))

        if not candidates:
            return {}
        chosen = [page for _, page in sorted(candidates, key=lambda x: (-x[0], x[1]))[: max_pages]]
        return {p: page_lines[p] for p in sorted(chosen)}

    def _table_signature(self, table: Dict[str, Any]) -> str:
        page_no = int(table.get("page", 0) or 0)
        headers = [self._normalize_token_for_compare(str(h or "")) for h in table.get("headers", [])]
        headers = [h for h in headers if h][:6]
        col_count = int(table.get("col_count", 0) or 0)
        row_count = int(table.get("row_count", 0) or 0)
        first_row_tokens: List[str] = []
        rows = table.get("rows", [])
        if isinstance(rows, list) and rows:
            first_cells = rows[0].get("cells", []) if isinstance(rows[0], dict) else []
            if isinstance(first_cells, list):
                for c in first_cells[:6]:
                    first_row_tokens.append(self._normalize_token_for_compare(str(c.get("text", ""))))
        first_row_tokens = [x for x in first_row_tokens if x]
        return "|".join(
            [
                str(page_no),
                str(col_count),
                str(row_count),
                ",".join(headers),
                ",".join(first_row_tokens),
            ]
        )

    def _augment_with_line_tables(self, base_tables: TableBlocks, line_tables: TableBlocks) -> TableBlocks:
        if not base_tables:
            return line_tables
        if not line_tables:
            return base_tables

        out: TableBlocks = list(base_tables)
        seen = {self._table_signature(t) for t in base_tables}
        for t in line_tables:
            sig = self._table_signature(t)
            if not sig or sig in seen:
                continue
            rows = int(t.get("row_count", 0) or 0)
            cols = int(t.get("col_count", 0) or 0)
            if rows <= 1 or cols <= 1:
                continue
            out.append(t)
            seen.add(sig)

        if out and self.table_merge_enable:
            out = self._merge_same_page_tables(out)
            out = self._merge_cross_page_tables(out)
        return out

    def _infer_tables_from_ocr_cells(
        self,
        page_cells: Dict[int, List[Dict[str, Any]]],
        min_quality: float | None = None,
        enable_relaxed_second_pass: bool = True,
    ) -> TableBlocks:
        table_blocks: TableBlocks = []
        table_idx = 1
        quality_threshold = self.ocr_table_min_quality if min_quality is None else float(min_quality)

        for page_no in sorted(page_cells.keys()):
            raw_cells = [c for c in page_cells.get(page_no, []) if c.get("text")]
            cells = self._dedupe_ocr_cells(raw_cells)
            if len(cells) < self.ocr_table_min_cols * self.ocr_table_min_rows:
                continue

            dynamic_row_tol = max(self.ocr_table_row_tol, self._median_cell_height(cells) * 1.25)
            rows = self._cluster_ocr_rows(cells, dynamic_row_tol)
            candidate_rows = [row for row in rows if len(row.get("cells", [])) >= self.ocr_table_min_cols]
            if len(candidate_rows) < self.ocr_table_min_rows:
                continue

            groups = self._group_table_rows(candidate_rows)
            page_tables, table_idx = self._build_tables_from_row_groups(
                page_no=page_no,
                groups=groups,
                quality_threshold=quality_threshold,
                table_idx=table_idx,
                all_rows=rows,
            )

            # Second pass: only when strict grouping misses this page, relax row continuity rules.
            if (
                enable_relaxed_second_pass
                and not page_tables
                and len(candidate_rows) >= (self.ocr_table_min_rows + 1)
                and len(candidate_rows) <= 48
                and len(cells) <= 420
            ):
                relaxed_groups = self._group_table_rows(
                    candidate_rows,
                    row_gap=self.ocr_table_row_gap * self.ocr_table_relaxed_row_gap_scale,
                    align_min=self.ocr_table_relaxed_align_min,
                    overlap_min=self.ocr_table_relaxed_overlap_min,
                    col_diff_max=self.ocr_table_relaxed_col_diff_max,
                )
                page_tables, table_idx = self._build_tables_from_row_groups(
                    page_no=page_no,
                    groups=relaxed_groups,
                    quality_threshold=quality_threshold,
                    table_idx=table_idx,
                    all_rows=rows,
                )
            table_blocks.extend(page_tables)

        if table_blocks and self.table_merge_enable:
            table_blocks = self._merge_same_page_tables(table_blocks)
            table_blocks = self._merge_cross_page_tables(table_blocks)
        return table_blocks

    def _build_tables_from_row_groups(
        self,
        page_no: int,
        groups: List[List[Dict[str, Any]]],
        quality_threshold: float,
        table_idx: int,
        all_rows: List[Dict[str, Any]] | None = None,
    ) -> Tuple[TableBlocks, int]:
        page_tables: TableBlocks = []
        for raw_group in groups:
            for group in self._split_group_by_row_gaps(raw_group):
                if len(group) < self.ocr_table_min_rows:
                    continue

                anchors = self._build_col_anchors(group, self.ocr_table_col_tol)
                if len(anchors) < self.ocr_table_min_cols:
                    continue
                base_quality = self._table_quality_score(group, anchors)
                if base_quality < quality_threshold:
                    continue

                use_group = group
                quality = base_quality
                if base_quality >= max(quality_threshold + 0.06, 0.62):
                    dense_group = self._expand_group_with_sparse_rows(group, anchors, all_rows or group)
                    if len(dense_group) > len(group):
                        dense_quality = self._table_quality_score(dense_group, anchors)
                        added_rows = len(dense_group) - len(group)
                        max_added = max(2, min(6, (len(group) // 2) + 1))
                        if added_rows <= max_added and dense_quality >= quality_threshold and dense_quality + 0.03 >= base_quality:
                            use_group = dense_group
                            quality = dense_quality
                elif base_quality < quality_threshold:
                    continue

                if quality < quality_threshold:
                    continue

                rows_payload: List[Dict[str, Any]] = []
                for row_idx, row in enumerate(use_group[: self.table_max_rows], start=1):
                    row_cells = sorted(row.get("cells", []), key=lambda c: c.get("x_center", 0.0))
                    row_map: Dict[int, Dict[str, Any]] = {}
                    for cell in row_cells:
                        col_index = self._nearest_anchor_index(cell.get("x_center", 0.0), anchors) + 1
                        if col_index in row_map:
                            prev = row_map[col_index]
                            if len(str(cell.get("text", ""))) > len(str(prev.get("text", ""))):
                                row_map[col_index] = cell
                        else:
                            row_map[col_index] = cell

                    cells_payload: List[Dict[str, Any]] = []
                    for col_index in sorted(row_map.keys())[: self.table_max_cols]:
                        cell = row_map[col_index]
                        cells_payload.append(
                            {
                                "col_index": col_index,
                                "text": str(cell.get("text", "")).strip(),
                                "ref_id": cell.get("ref_id"),
                                "bbox": cell.get("bbox", [float(page_no), 0.0, 0.0, 1.0, 1.0]),
                            }
                        )
                    if cells_payload:
                        rows_payload.append({"row_index": row_idx, "cells": cells_payload})

                if len(rows_payload) < self.ocr_table_min_rows:
                    continue

                headers, data_rows = self._infer_headers_and_data_rows(rows_payload)
                data_rows = self._drop_redundant_header_like_rows(data_rows, headers)
                data_rows = self._decorate_rows_with_meta(data_rows, headers)
                if len(data_rows) < self.ocr_table_min_rows:
                    if not (
                        len(data_rows) == 1
                        and int(getattr(self, "_runtime_page_count", 0) or 0) <= 120
                        and len(data_rows[0].get("cells", [])) >= 3
                        and sum(
                            1
                            for c in data_rows[0].get("cells", [])
                            if c.get("numeric_value") is not None or re.search(r"\d", str(c.get("text", "")))
                        )
                        >= 2
                    ):
                        continue
                if self._looks_like_false_table(headers, data_rows):
                    continue
                col_count = max((len(r.get("cells", [])) for r in data_rows), default=0)
                numeric_dense_rows = 0
                section_like_rows = 0
                edge_page_rows = 0
                for row in data_rows[:80]:
                    cells = row.get("cells", [])
                    numeric_hits = sum(
                        1
                        for c in cells
                        if c.get("numeric_value") is not None or re.search(r"\d", str(c.get("text", "")))
                    )
                    if numeric_hits >= 2:
                        numeric_dense_rows += 1
                    row_values = [self._normalize_text(str(c.get("text", ""))) for c in cells if c.get("text")]
                    row_text = " ".join(row_values)
                    if self._contains_section_marker(row_text):
                        section_like_rows += 1
                    if row_values:
                        if self._is_page_number_token(row_values[0]) or self._is_page_number_token(row_values[-1]):
                            edge_page_rows += 1
                section_ratio = section_like_rows / float(max(len(data_rows[:80]), 1))
                edge_page_ratio = edge_page_rows / float(max(len(data_rows[:80]), 1))
                if col_count <= 2 and len(data_rows) <= 3 and numeric_dense_rows < 2:
                    continue
                if col_count <= 3 and len(data_rows) >= 8 and numeric_dense_rows < 2:
                    continue
                if col_count <= 3 and len(data_rows) >= 8 and section_ratio >= 0.18 and edge_page_ratio >= 0.35:
                    continue
                if col_count <= 3 and len(data_rows) >= 12 and edge_page_ratio >= 0.45 and numeric_dense_rows < 4:
                    continue
                if col_count <= 3 and len(data_rows) >= 12 and section_ratio >= 0.2 and numeric_dense_rows < 3:
                    continue

                page_tables.append(
                    {
                        "table_id": f"pdf_ocr_layout_t{table_idx}",
                        "source": "pdf_ocr_layout",
                        "page": page_no,
                        "headers": headers,
                        "header_meta": self._build_header_meta(headers),
                        "rows": data_rows,
                        "row_count": len(data_rows),
                        "col_count": col_count,
                        "quality": round(quality, 4),
                    }
                )
                table_idx += 1
        return page_tables, table_idx

    def _split_group_by_row_gaps(self, group: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        if len(group) < (self.ocr_table_min_rows * 2):
            return [group]
        ordered = sorted(group, key=lambda r: float(r.get("y_center", 0.0)))
        gaps: List[float] = []
        col_counts: List[int] = [len(r.get("cells", [])) for r in ordered]
        for i in range(1, len(ordered)):
            gaps.append(float(ordered[i].get("y_center", 0.0)) - float(ordered[i - 1].get("y_center", 0.0)))
        if not gaps:
            return [ordered]
        sorted_gaps = sorted(gaps)
        mid = len(sorted_gaps) // 2
        median_gap = sorted_gaps[mid] if len(sorted_gaps) % 2 else (sorted_gaps[mid - 1] + sorted_gaps[mid]) / 2.0
        split_threshold = max(self.ocr_table_row_gap * 1.8, median_gap * 2.7)

        parts: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = [ordered[0]]
        for i in range(1, len(ordered)):
            gap = gaps[i - 1]
            prev_cols = col_counts[i - 1]
            curr_cols = col_counts[i]
            col_jump = abs(curr_cols - prev_cols)
            should_split = gap > split_threshold
            if not should_split and gap > (self.ocr_table_row_gap * 1.15) and col_jump >= 3:
                should_split = True
            if should_split and len(current) >= self.ocr_table_min_rows:
                parts.append(current)
                current = [ordered[i]]
            else:
                current.append(ordered[i])
        if current:
            parts.append(current)

        valid = [p for p in parts if len(p) >= self.ocr_table_min_rows]
        if not valid:
            return [ordered]
        if len(valid) == 1:
            return [ordered]
        return valid

    def _expand_group_with_sparse_rows(
        self,
        group: List[Dict[str, Any]],
        anchors: List[float],
        all_rows: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not group or not all_rows or len(all_rows) > 220:
            return group
        group_ids = {id(r) for r in group}
        ys = [float(r.get("y_center", 0.0)) for r in group]
        y_min = min(ys)
        y_max = max(ys)
        y_pad = self.ocr_table_row_gap * 1.0

        group_cells: List[Dict[str, Any]] = []
        for r in group:
            group_cells.extend(r.get("cells", []))
        g_x0, g_x1 = self._cells_x_span(group_cells)

        selected: List[Dict[str, Any]] = list(group)
        for row in all_rows:
            if id(row) in group_ids:
                continue
            cells = row.get("cells", [])
            if not cells:
                continue
            y = float(row.get("y_center", 0.0))
            if y < (y_min - y_pad) or y > (y_max + y_pad):
                continue
            align = self._row_anchor_coverage(cells, anchors, self.ocr_table_col_tol * 1.25)
            overlap = self._cells_span_overlap(cells, g_x0, g_x1)
            has_numeric = any(re.search(r"\d", str(c.get("text", ""))) for c in cells)
            if align >= 0.5 or (len(cells) >= 2 and overlap >= 0.52) or (has_numeric and align >= 0.4 and overlap >= 0.35):
                selected.append(row)

        selected = sorted(selected, key=lambda r: float(r.get("y_center", 0.0)))
        return selected

    @staticmethod
    def _cluster_ocr_rows(cells: List[Dict[str, Any]], row_tol: float) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        ordered = sorted(cells, key=lambda c: (c.get("y_center", 0.0), c.get("x_center", 0.0)))
        for cell in ordered:
            y = float(cell.get("y_center", 0.0))
            placed = False
            for row in rows:
                if abs(y - row["y_center"]) <= row_tol:
                    row["cells"].append(cell)
                    n = len(row["cells"])
                    row["y_center"] = ((row["y_center"] * (n - 1)) + y) / n
                    placed = True
                    break
            if not placed:
                rows.append({"y_center": y, "cells": [cell]})

        rows.sort(key=lambda r: r["y_center"])
        for row in rows:
            row["cells"] = sorted(row["cells"], key=lambda c: c.get("x_center", 0.0))
        return rows

    def _group_table_rows(
        self,
        rows: List[Dict[str, Any]],
        row_gap: float | None = None,
        align_min: float = 0.5,
        overlap_min: float = 0.45,
        col_diff_max: int = 1,
    ) -> List[List[Dict[str, Any]]]:
        groups: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = []
        gap_limit = float(self.ocr_table_row_gap if row_gap is None else row_gap)

        for row in rows:
            if not current:
                current = [row]
                continue

            prev = current[-1]
            y_gap = float(row.get("y_center", 0.0)) - float(prev.get("y_center", 0.0))
            align = self._row_alignment_score(prev.get("cells", []), row.get("cells", []), self.ocr_table_col_tol)
            overlap = self._x_overlap_ratio(prev.get("cells", []), row.get("cells", []))
            col_diff = abs(len(prev.get("cells", [])) - len(row.get("cells", [])))

            if y_gap <= gap_limit and ((align >= align_min and overlap >= overlap_min) or col_diff <= col_diff_max):
                current.append(row)
            else:
                if len(current) >= self.ocr_table_min_rows:
                    groups.append(current)
                current = [row]

        if len(current) >= self.ocr_table_min_rows:
            groups.append(current)
        return groups

    @staticmethod
    def _row_alignment_score(cells_a: List[Dict[str, Any]], cells_b: List[Dict[str, Any]], tol: float) -> float:
        if not cells_a or not cells_b:
            return 0.0
        xs_a = sorted(float(c.get("x_center", 0.0)) for c in cells_a)
        xs_b = sorted(float(c.get("x_center", 0.0)) for c in cells_b)
        short, long = (xs_a, xs_b) if len(xs_a) <= len(xs_b) else (xs_b, xs_a)
        if not short:
            return 0.0

        matched = 0
        for x in short:
            if any(abs(x - y) <= tol for y in long):
                matched += 1
        return matched / float(len(short))

    @staticmethod
    def _x_overlap_ratio(cells_a: List[Dict[str, Any]], cells_b: List[Dict[str, Any]]) -> float:
        if not cells_a or not cells_b:
            return 0.0

        def span(cells: List[Dict[str, Any]]) -> Tuple[float, float]:
            x0 = min(float(c.get("bbox", [0, 0, 0, 0, 0])[1]) for c in cells)
            x1 = max(float(c.get("bbox", [0, 0, 0, 0, 0])[1]) + float(c.get("bbox", [0, 0, 0, 0, 0])[3]) for c in cells)
            return x0, x1

        a0, a1 = span(cells_a)
        b0, b1 = span(cells_b)
        inter = max(0.0, min(a1, b1) - max(a0, b0))
        den = max(a1 - a0, b1 - b0, 1e-6)
        return inter / den

    @staticmethod
    def _cells_x_span(cells: List[Dict[str, Any]]) -> Tuple[float, float]:
        if not cells:
            return 0.0, 1.0
        x0 = min(float(c.get("bbox", [0, 0, 0, 0, 0])[1]) for c in cells)
        x1 = max(float(c.get("bbox", [0, 0, 0, 0, 0])[1]) + float(c.get("bbox", [0, 0, 0, 0, 0])[3]) for c in cells)
        if x1 <= x0:
            return 0.0, 1.0
        return x0, x1

    @staticmethod
    def _cells_span_overlap(cells: List[Dict[str, Any]], x0: float, x1: float) -> float:
        if not cells:
            return 0.0
        c0, c1 = NativeDocumentParser._cells_x_span(cells)
        inter = max(0.0, min(c1, x1) - max(c0, x0))
        den = max(c1 - c0, x1 - x0, 1e-6)
        return inter / den

    @staticmethod
    def _row_anchor_coverage(cells: List[Dict[str, Any]], anchors: List[float], tol: float) -> float:
        if not cells or not anchors:
            return 0.0
        matched = 0
        for c in cells:
            x = float(c.get("x_center", 0.0))
            if any(abs(x - a) <= tol for a in anchors):
                matched += 1
        return matched / float(max(len(cells), 1))

    @staticmethod
    def _median_cell_height(cells: List[Dict[str, Any]]) -> float:
        hs = [float(c.get("bbox", [0, 0, 0, 0, 0])[4]) for c in cells if len(c.get("bbox", [])) >= 5]
        hs = [h for h in hs if h > 0]
        if not hs:
            return 0.015
        hs.sort()
        mid = len(hs) // 2
        if len(hs) % 2:
            return hs[mid]
        return (hs[mid - 1] + hs[mid]) / 2.0

    @staticmethod
    def _is_page_number_token(text: str) -> bool:
        t = str(text or "").strip()
        if not t:
            return False
        if re.fullmatch(r"[\(\[]?\d{1,4}[\)\]]?", t):
            return True
        return bool(re.fullmatch(r"[\(\[]?[ivxlcdm]{1,8}[\)\]]?", t, re.IGNORECASE))

    @staticmethod
    def _contains_section_marker(text: str) -> bool:
        t = str(text or "").strip()
        if not t:
            return False
        if re.search(r"\u7b2c.{0,4}[\u7ae0\u8282\u7bc7]", t):
            return True
        if "\u6838\u71c3\u6599\u540e\u5904\u7406\u5de5\u5b66" in t:
            return True
        lower = t.lower()
        if re.search(r"\bchapter\b|\bsection\b|\bcontents\b|table of contents|references", lower):
            return True
        return False

    @staticmethod
    def _contains_equation_marker(text: str) -> bool:
        t = str(text or "").strip()
        if not t:
            return False
        if re.search(r"\(\d+\-\d+\)", t):
            return True
        if ("=" in t and "+" in t) or ("\u2192" in t) or ("->" in t):
            return True
        return False

    @staticmethod
    def _contains_catalog_marker(text: str) -> bool:
        t = str(text or "").strip().lower()
        if not t:
            return False
        return "list of tables" in t or "table of contents" in t or "contents" == t

    @staticmethod
    def _contains_figure_marker(text: str) -> bool:
        t = str(text or "").strip()
        if not t:
            return False
        lower = t.lower()
        if re.search(r"\bfig(?:ure)?\.?\s*\d+", lower):
            return True
        if re.search(r"^\s*图\s*[0-9A-Za-z一二三四五六七八九十.\-]+", t):
            return True
        if re.search(r"[\s(（]图\s*[0-9A-Za-z一二三四五六七八九十.\-]+", t):
            return True
        return False

    @staticmethod
    def _is_sentence_like_text(text: str) -> bool:
        t = str(text or "").strip()
        if len(t) < 24:
            return False
        if re.search(r"[。；！？]|[A-Za-z]{3,}\s+[A-Za-z]{3,}", t):
            return True
        if t.count(",") + t.count("，") + t.count(";") + t.count("；") >= 2:
            return True
        return False

    def _looks_like_false_table(self, headers: List[str], data_rows: List[Dict[str, Any]]) -> bool:
        if not headers or not data_rows:
            return True

        cleaned_headers = [self._normalize_text(str(h or "")) for h in headers if str(h or "").strip()]
        if not cleaned_headers:
            return True

        chapter_hits = sum(1 for h in cleaned_headers if self._contains_section_marker(h))
        catalog_hits = sum(1 for h in cleaned_headers if self._contains_catalog_marker(h))
        page_hits = sum(1 for h in cleaned_headers if self._is_page_number_token(h))
        equation_hits = sum(1 for h in cleaned_headers if self._contains_equation_marker(h))
        figure_hits = sum(1 for h in cleaned_headers if self._contains_figure_marker(h))

        flat_cells: List[Dict[str, Any]] = []
        for row in data_rows:
            for cell in row.get("cells", []):
                flat_cells.append(cell)
                if len(flat_cells) >= 500:
                    break
            if len(flat_cells) >= 500:
                break

        if not flat_cells:
            return True

        numeric_cells = 0
        long_text_cells = 0
        sentence_like_rows = 0
        inspected_rows = 0
        for row in data_rows[:40]:
            cells = row.get("cells", [])
            if not cells:
                continue
            row_text = " ".join(self._normalize_text(str(c.get("text", ""))) for c in cells if c.get("text"))
            inspected_rows += 1
            if len(cells) <= 2 and self._is_sentence_like_text(row_text):
                sentence_like_rows += 1
        for cell in flat_cells:
            text = self._normalize_text(str(cell.get("text", "")))
            if not text:
                continue
            if cell.get("numeric_value") is not None or re.search(r"\d", text):
                numeric_cells += 1
            if len(text) >= 24:
                long_text_cells += 1

        total = max(len(flat_cells), 1)
        numeric_ratio = numeric_cells / float(total)
        long_ratio = long_text_cells / float(total)
        sentence_like_ratio = (
            sentence_like_rows / float(max(inspected_rows, 1))
            if inspected_rows > 0
            else 0.0
        )
        avg_cols = (
            sum(len(r.get("cells", [])) for r in data_rows) / float(max(len(data_rows), 1))
            if data_rows
            else 0.0
        )
        row_end_page_hits = 0
        section_row_hits = 0
        catalog_row_hits = 0
        inspected_toc_rows = 0
        for row in data_rows[:100]:
            cells = sorted(row.get("cells", []), key=lambda c: int(c.get("col_index", 0) or 0))
            vals = [self._normalize_text(str(c.get("text", ""))) for c in cells if c.get("text")]
            if not vals:
                continue
            inspected_toc_rows += 1
            if self._is_page_number_token(vals[-1]) or self._is_page_number_token(vals[0]):
                row_end_page_hits += 1
            if any(self._contains_section_marker(v) for v in vals[:2]):
                section_row_hits += 1
            if self._contains_catalog_marker(" ".join(vals)):
                catalog_row_hits += 1
        row_end_page_ratio = row_end_page_hits / float(max(inspected_toc_rows, 1))
        section_row_ratio = section_row_hits / float(max(inspected_toc_rows, 1))
        catalog_row_ratio = catalog_row_hits / float(max(inspected_toc_rows, 1))

        # Keep large, consistently tabular blocks to avoid over-filtering text-heavy technical tables.
        if len(data_rows) >= 14 and avg_cols >= 3.2 and sentence_like_ratio <= 0.45:
            return False

        if (
            len(data_rows) >= 8
            and avg_cols <= 3.4
            and row_end_page_ratio >= 0.55
            and section_row_ratio >= 0.18
        ):
            return True
        if catalog_row_ratio >= 0.12 and row_end_page_ratio >= 0.4 and avg_cols <= 4.2:
            return True
        if (
            chapter_hits > 0
            and page_hits > 0
            and len(cleaned_headers) <= 4
            and (numeric_ratio < 0.35 or len(data_rows) <= 6)
        ):
            return True
        if figure_hits > 0 and int(getattr(self, "_runtime_page_count", 0) or 0) <= 120:
            has_year_span = any(re.search(r"20\d{2}\s*[-—~至]\s*20\d{2}", h) for h in cleaned_headers)
            growth_label = any(("增长速度" in h) or ("增速" in h) for h in cleaned_headers)
            if has_year_span and len(data_rows) <= 3 and avg_cols <= 6.2:
                return True
            if growth_label and sentence_like_ratio <= 0.22 and len(data_rows) <= 3 and avg_cols <= 6.2:
                return True
        if catalog_hits > 0 and len(cleaned_headers) <= 5 and len(data_rows) <= 10:
            return True
        if catalog_hits > 0 and avg_cols <= 4.5 and numeric_ratio < 0.55:
            return True
        if chapter_hits > 0 and len(cleaned_headers) <= 2 and numeric_ratio < 0.6 and len(data_rows) <= 8:
            return True
        if equation_hits > 0 and page_hits > 0 and avg_cols <= 3.2 and len(data_rows) <= 8:
            return True
        if equation_hits >= 2 and avg_cols <= 3.2 and len(data_rows) <= 8:
            return True
        if (
            len(cleaned_headers) <= 1
            and len(cleaned_headers[0]) >= 28
            and avg_cols <= 2.2
            and len(data_rows) <= 8
            and numeric_ratio < 0.3
        ):
            return True
        if len(cleaned_headers) <= 2 and avg_cols <= 2.2 and long_ratio >= 0.45 and numeric_ratio < 0.25:
            return True
        if numeric_ratio < 0.08 and avg_cols <= 2.2 and len(data_rows) <= 4:
            return True
        if sentence_like_ratio >= 0.62 and avg_cols <= 3.0 and numeric_ratio < 0.2:
            return True
        if sentence_like_ratio >= 0.5 and avg_cols <= 2.2 and numeric_ratio < 0.28:
            return True
        if len(data_rows) <= 6 and avg_cols >= 5.0 and sentence_like_ratio >= 0.25 and numeric_ratio < 0.45:
            return True
        if len(data_rows) <= 5 and avg_cols >= 4.0 and long_ratio >= 0.35 and numeric_ratio < 0.4:
            return True
        return False

    def _table_quality_score(self, group: List[Dict[str, Any]], anchors: List[float]) -> float:
        if not group or not anchors:
            return 0.0

        row_count = len(group)
        col_count = len(anchors)
        row_lengths = [len(r.get("cells", [])) for r in group]
        avg_cols = (sum(row_lengths) / float(max(row_count, 1))) if row_lengths else 0.0
        col_coverage = min(1.0, avg_cols / float(max(col_count, 1)))
        row_score = min(1.0, row_count / 6.0)
        col_score = min(1.0, col_count / 6.0)

        align_scores: List[float] = []
        numeric_like = 0
        total_cells = 0
        for i, row in enumerate(group):
            cells = row.get("cells", [])
            total_cells += len(cells)
            for c in cells:
                text = str(c.get("text", "")).strip()
                if re.search(r"\d", text):
                    numeric_like += 1
            if i > 0:
                align_scores.append(
                    self._row_alignment_score(group[i - 1].get("cells", []), cells, self.ocr_table_col_tol)
                )
        align_score = (sum(align_scores) / len(align_scores)) if align_scores else 0.0
        numeric_ratio = (numeric_like / float(total_cells)) if total_cells else 0.0
        numeric_score = min(1.0, numeric_ratio * 1.8 + 0.2)

        quality = (
            0.25 * row_score
            + 0.2 * col_score
            + 0.25 * align_score
            + 0.15 * col_coverage
            + 0.15 * numeric_score
        )
        return max(0.0, min(1.0, quality))

    @staticmethod
    def _dedupe_ocr_cells(cells: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not cells:
            return []
        ordered = sorted(
            cells,
            key=lambda c: (
                round(float(c.get("x_center", 0.0)), 4),
                round(float(c.get("y_center", 0.0)), 4),
                str(c.get("text", "")),
            ),
        )
        out: List[Dict[str, Any]] = []
        for cell in ordered:
            x = float(cell.get("x_center", 0.0))
            y = float(cell.get("y_center", 0.0))
            text = str(cell.get("text", "")).strip()
            if not text:
                continue
            duplicated = False
            for prev in out[-12:]:
                if text != str(prev.get("text", "")).strip():
                    continue
                if abs(x - float(prev.get("x_center", 0.0))) <= 0.006 and abs(y - float(prev.get("y_center", 0.0))) <= 0.006:
                    duplicated = True
                    break
            if not duplicated:
                out.append(cell)
        return out

    @staticmethod
    def _build_col_anchors(rows: List[Dict[str, Any]], tol: float) -> List[float]:
        xs: List[float] = []
        for row in rows:
            xs.extend(float(c.get("x_center", 0.0)) for c in row.get("cells", []))
        xs.sort()
        if not xs:
            return []

        anchors: List[float] = []
        counts: List[int] = []
        for x in xs:
            if not anchors:
                anchors.append(x)
                counts.append(1)
                continue
            if abs(x - anchors[-1]) <= tol:
                n = counts[-1] + 1
                anchors[-1] = ((anchors[-1] * counts[-1]) + x) / n
                counts[-1] = n
            else:
                anchors.append(x)
                counts.append(1)
        return anchors

    @staticmethod
    def _nearest_anchor_index(x: float, anchors: List[float]) -> int:
        if not anchors:
            return 0
        best_i = 0
        best_d = abs(x - anchors[0])
        for i in range(1, len(anchors)):
            d = abs(x - anchors[i])
            if d < best_d:
                best_d = d
                best_i = i
        return best_i

    def _infer_tables_from_page_lines(
        self,
        page_lines: Dict[int, List[str]],
        parts: List[str],
        bbox_map: Dict[str, List[float]],
        source: str,
    ) -> TableBlocks:
        table_blocks: TableBlocks = []
        table_idx = 1
        emitted_cells = 0

        for page_no in sorted(page_lines.keys()):
            lines = page_lines.get(page_no, [])
            groups: List[List[List[str]]] = []
            current_group: List[List[str]] = []

            for line in lines:
                tokens = self._split_table_line(line)
                if self._is_table_line(line, tokens):
                    current_group.append(tokens)
                else:
                    if len(current_group) >= 2:
                        groups.append(current_group)
                    current_group = []
            if len(current_group) >= 2:
                groups.append(current_group)

            for group in groups:
                if emitted_cells >= self.table_cell_cap:
                    break
                raw_rows = group[: self.table_max_rows + 1]
                if len(raw_rows) < self.ocr_table_min_rows:
                    continue

                table_id = f"{source}_t{table_idx}"
                raw_rows_payload: List[Dict[str, Any]] = []
                for row_idx, row_tokens in enumerate(raw_rows, start=1):
                    cells_payload: List[Dict[str, Any]] = []
                    for col_idx, text in enumerate(row_tokens[: self.table_max_cols], start=1):
                        normalized = self._normalize_text(text)
                        if not normalized:
                            continue
                        ref_id = f"{table_id}_r{row_idx}_c{col_idx}"
                        parts.append(f'<ref id="{ref_id}">{escape(normalized)}</ref>')
                        bbox = [float(page_no), 0.0, 0.0, 1.0, 1.0]
                        bbox_map[ref_id] = bbox
                        cells_payload.append(
                            {
                                "col_index": col_idx,
                                "text": normalized,
                                "ref_id": ref_id,
                                "bbox": bbox,
                            }
                        )
                        emitted_cells += 1
                        if emitted_cells >= self.table_cell_cap:
                            break
                    if cells_payload:
                        raw_rows_payload.append({"row_index": row_idx, "cells": cells_payload})
                    if emitted_cells >= self.table_cell_cap:
                        break

                if raw_rows_payload:
                    headers, data_rows_payload = self._infer_headers_and_data_rows(raw_rows_payload)
                    data_rows_payload = self._drop_redundant_header_like_rows(data_rows_payload, headers)
                    data_rows_payload = self._decorate_rows_with_meta(data_rows_payload, headers)
                    if len(data_rows_payload) < self.ocr_table_min_rows:
                        if len(data_rows_payload) != 1:
                            continue
                        first_cells = data_rows_payload[0].get("cells", [])
                        numeric_hits = sum(
                            1
                            for c in first_cells
                            if c.get("numeric_value") is not None or re.search(r"\d", str(c.get("text", "")))
                        )
                        if len(first_cells) < 3 or numeric_hits < 2:
                            continue
                    if self._looks_like_false_table(headers, data_rows_payload):
                        continue
                    table_blocks.append(
                        {
                            "table_id": table_id,
                            "source": source,
                            "page": page_no,
                            "headers": headers,
                            "header_meta": self._build_header_meta(headers),
                            "rows": data_rows_payload,
                            "row_count": len(data_rows_payload),
                            "col_count": max((len(r.get("cells", [])) for r in data_rows_payload), default=0),
                        }
                    )
                    table_idx += 1

        if table_blocks and self.table_merge_enable:
            table_blocks = self._merge_same_page_tables(table_blocks)
            table_blocks = self._merge_cross_page_tables(table_blocks)
        return table_blocks

    @staticmethod
    def _split_table_line(line: str) -> List[str]:
        cleaned = line.strip().strip("|")
        if not cleaned:
            return []
        tokens = [t.strip() for t in re.split(r"\s{2,}|\t|\|", cleaned) if t.strip()]
        if len(tokens) < 2:
            alt = [t.strip() for t in re.split(r"\s+", cleaned) if t.strip()]
            if len(alt) >= 2:
                num_like = sum(1 for t in alt if re.search(r"\d", t))
                if (len(alt) >= 3 and num_like >= 2) or (len(alt) == 2 and num_like >= 1):
                    tokens = alt
        return tokens

    @staticmethod
    def _is_table_line(line: str, tokens: List[str]) -> bool:
        if len(tokens) < 2:
            return False

        if len(tokens) >= 3:
            if line.count("|") >= 2:
                return True
            if "\t" in line:
                return True
            if re.search(r"\s{2,}", line):
                return True

        if len(tokens) == 2:
            numeric_like = sum(1 for t in tokens if re.search(r"\d", t))
            alpha_like = sum(1 for t in tokens if re.search(r"[A-Za-z\u4e00-\u9fa5]", t))
            if (line.count("|") >= 1 or "\t" in line or re.search(r"\s{2,}", line)) and numeric_like >= 1 and alpha_like >= 1:
                return True

        numeric_like = sum(1 for t in tokens if re.search(r"\d", t))
        if numeric_like >= 2 and len(tokens) >= 4:
            return True
        return False

    @staticmethod
    def _is_unit_like_token(text: str) -> bool:
        value = str(text or "").strip().lower()
        if not value:
            return False
        value = value.strip("()[]{}<>（）【】")
        if not value:
            return False
        unit_set = {
            "%", "\uff05", "\u2030",
            "\u2103", "\u00b0c", "\u2109", "\u00b0f",
            "k", "pa", "kpa", "mpa", "bar",
            "s", "sec", "min", "h",
            "g", "kg", "mg", "ug", "\u03bcg",
            "l", "ml", "m3", "m3/h", "l/h",
            "mol", "mol/l", "g/l", "mg/l", "kg/m3",
            "wt%", "vol%", "ppm", "ppb", "ph",
        }
        if value in unit_set:
            return True
        if re.fullmatch(r"[a-z%\u00b0\u2103\u2109\u2030\u03bc/\-0-9]{1,16}", value):
            return True
        return False

    @staticmethod
    def _normalize_token_for_compare(text: str) -> str:
        token = str(text or "").strip().lower()
        token = re.sub(r"[\s\(\)\[\]{}<>/\\,.;:：，、\-_]+", "", token)
        return token

    def _extract_header_name_and_unit(self, raw_header: str) -> Tuple[str, str | None]:
        text = self._normalize_text(str(raw_header or ""))
        if not text:
            return "", None
        m = re.match(r"^(.*?)\s*[\(\[（【]\s*([^\)\]）】]{1,24})\s*[\)\]）】]\s*$", text)
        if m:
            name = self._normalize_text(m.group(1))
            unit = self._normalize_text(m.group(2))
            return name or text, unit or None

        m2 = re.match(r"^(.*?)\s*[/／]\s*([%a-zA-Z\u00b0\u2103\u2109\u2030\u03bc0-9\-]{1,16})$", text)
        if m2:
            name = self._normalize_text(m2.group(1))
            unit = self._normalize_text(m2.group(2))
            return name or text, unit or None
        return text, None

    def _extract_number_meta(self, text: str, unit_hint: str | None) -> Dict[str, Any]:
        raw = self._normalize_text(str(text or ""))
        result: Dict[str, Any] = {
            "value_type": "text",
            "numeric_value": None,
            "ratio_value": None,
            "detected_unit": unit_hint,
            "normalized_text": raw,
        }
        if not raw:
            return result

        cleaned = re.sub(r"[,\uFF0C\s]", "", raw)
        numeric_matches = list(re.finditer(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", cleaned))
        if len(numeric_matches) > 1:
            # Composite OCR cells like "1730.4万人，固定资产原价8610.0亿" are too ambiguous
            # to coerce into one stable numeric_value here. Keep them as text so later
            # extraction can treat them as cautious evidence instead of a confident wrong number.
            return result
        sci_text = cleaned.replace("×", "x").replace("X", "x").replace("＊", "x").replace("−", "-")
        sci_match = re.search(r"([-+]?\d*\.?\d+)\s*[x*]\s*10(?:\^)?\s*([-+]?\d+)", sci_text)
        if sci_match:
            try:
                base = float(sci_match.group(1))
                exponent = int(sci_match.group(2))
                if exponent > 308 or exponent < -308:
                    return result
                value = base * (10.0 ** exponent)
            except (ValueError, OverflowError):
                return result
        else:
            m = numeric_matches[0] if numeric_matches else None
            if not m:
                return result
            try:
                value = float(m.group(0))
            except (ValueError, OverflowError):
                return result

        suffix = cleaned[m.end() :] if not sci_match and m else ""
        scale = 1.0
        if suffix.startswith("\u4ebf"):
            scale *= 1e8
        elif suffix.startswith("\u4e07"):
            scale *= 1e4
        elif suffix.startswith("\u5343"):
            scale *= 1e3
        elif suffix.startswith("\u767e"):
            scale *= 1e2

        try:
            numeric_value = value * scale
        except OverflowError:
            return result
        if not math.isfinite(numeric_value):
            return result
        detected_unit = unit_hint
        if "%" in raw or "\uff05" in raw:
            detected_unit = detected_unit or "%"
            ratio = numeric_value / 100.0
        else:
            ratio = None
        if ratio is not None and not math.isfinite(ratio):
            ratio = None

        unit_match = re.search(
            r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?\s*([%a-zA-Z\u00b0\u2103\u2109\u2030\u03bc/\-]+)$",
            raw,
        )
        if unit_match:
            detected_unit = unit_match.group(1)

        result.update(
            {
                "value_type": "number",
                "numeric_value": round(numeric_value, 10),
                "ratio_value": None if ratio is None else round(ratio, 10),
                "detected_unit": detected_unit,
                "normalized_text": str(round(numeric_value, 10)),
            }
        )
        return result

    @staticmethod
    def _split_page_text(text: str, max_len: int = 700) -> List[str]:
        blocks = [b.strip() for b in re.split(r"\n{2,}", text) if b.strip()]
        chunks: List[str] = []
        for block in blocks:
            if len(block) <= max_len:
                chunks.append(block)
                continue
            for i in range(0, len(block), max_len):
                piece = block[i : i + max_len].strip()
                if piece:
                    chunks.append(piece)
        return chunks

    @staticmethod
    def _normalize_text(text: str) -> str:
        text = text.replace("\x00", " ")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def parse_document_in_subprocess(
    file_bytes: bytes,
    file_name: str = "document.pdf",
    track: str = "FastTrack",
    source_file_name: Optional[str] = None,
    source_file_bytes: Optional[bytes] = None,
) -> Tuple[str, Dict[str, List[float]], TableBlocks, FigureBlocks, Dict[str, Any]]:
    """ProcessPool entrypoint (must be top-level and picklable)."""

    parser = NativeDocumentParser()
    markdown, bbox_map, table_blocks = parser.parse_document(
        file_name=file_name,
        file_bytes=file_bytes,
        track=track,
        source_file_name=source_file_name,
        source_file_bytes=source_file_bytes,
    )
    source_suffix = Path(source_file_name or "").suffix.lower()
    if (
        str(file_name or "").lower().endswith(".pdf")
        and source_suffix == ".docx"
        and isinstance(source_file_bytes, (bytes, bytearray))
        and source_file_bytes
    ):
        merge_t0 = time.perf_counter()
        try:
            parser._merge_docx_chart_xml_into_pdf_figures(file_bytes=bytes(source_file_bytes))
            parser._last_parse_stats["docx_source_chart_merge_applied"] = True
        except Exception as exc:
            parser._last_parse_stats["docx_source_chart_merge_applied"] = False
            parser._last_parse_stats["docx_source_chart_merge_error"] = f"{type(exc).__name__}: {exc}"
        finally:
            parser._last_parse_stats["docx_source_chart_merge_ms"] = int((time.perf_counter() - merge_t0) * 1000)
            parser._last_parse_stats["docx_source_file_name"] = str(source_file_name or "")
    figure_blocks = parser.get_last_figure_blocks()
    parse_stats = parser.get_last_parse_stats()
    return markdown, bbox_map, table_blocks, figure_blocks, parse_stats

