from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict


GetEnv = Callable[[str, str], str]
LimitEnvValue = Callable[..., int]


class ParserConfigRuntime:
    """Resolve parser config from environment without owning parser behavior."""

    def __init__(
        self,
        *,
        getenv: GetEnv,
        limit_env_value: LimitEnvValue,
        module2_root: Path,
        repo_root: Path,
    ) -> None:
        self._getenv = getenv
        self._limit_env_value = limit_env_value
        self._module2_root = Path(module2_root).resolve()
        self._repo_root = Path(repo_root).resolve()

    def resolve_cache_dir(self, raw_value: str, default_path: Path) -> str:
        raw = str(raw_value or "").strip()
        if not raw:
            return str(Path(default_path).resolve())
        p = Path(raw)
        if p.is_absolute():
            return str(p.resolve())
        candidate_module2 = (self._module2_root / p).resolve()
        candidate_repo = (self._repo_root / p).resolve()
        normalized = raw.replace("\\", "/").lower()
        if normalized.startswith("backend/app/modules/module2/"):
            return str(candidate_repo)
        if candidate_repo.exists() and not candidate_module2.exists():
            return str(candidate_repo)
        return str(candidate_module2)

    def build_core_parse_config(
        self,
        *,
        module2_cache_root: Path,
        max_pages_override: int | None,
    ) -> Dict[str, Any]:
        max_pages = max_pages_override or max(1, int(self._getenv("MODULE2_MAX_PARSE_PAGES", "120")))
        return {
            "artifact_root_dir": Path(
                self.resolve_cache_dir(
                    self._getenv("MODULE2_ARTIFACT_ROOT_DIR", ""),
                    module2_cache_root,
                )
            ).resolve(),
            "office_convert_enabled": self._bool_env("MODULE2_DOC_TO_PDF_ENABLE", "true"),
            "word_parse_via_pdf": (
                self._getenv(
                    "MODULE2_WORD_PARSE_VIA_PDF",
                    self._getenv("MODULE2_WORD_REQUIRE_PDF_PARSE", "true"),
                ).lower()
                in {"1", "true", "yes"}
            ),
            "word_convert_allow_native_fallback": self._bool_env(
                "MODULE2_WORD_CONVERT_ALLOW_NATIVE_FALLBACK",
                "false",
            ),
            "word_pdf_timeout_sec": max(20.0, float(self._getenv("MODULE2_DOC_TO_PDF_TIMEOUT_SEC", "60"))),
            "max_pages": max_pages,
            "max_pages_visual": max(
                max_pages,
                int(self._getenv("MODULE2_MAX_PARSE_PAGES_VISUAL", "480")),
            ),
            "visual_probe_pages": max(1, int(self._getenv("MODULE2_VISUAL_PROBE_PAGES", "12"))),
            "native_text_threshold": max(120, int(self._getenv("MODULE2_NATIVE_TEXT_THRESHOLD", "200"))),
        }

    def build_ocr_table_limits(
        self,
        *,
        max_pages_visual: int,
        visual_probe_pages: int,
    ) -> Dict[str, Any]:
        ocr_time_budget_sec = max(10.0, float(self._getenv("MODULE2_OCR_TIME_BUDGET_SEC", "90")))
        ocr_table_min_quality = max(0.1, float(self._getenv("MODULE2_OCR_TABLE_MIN_QUALITY", "0.52")))
        ocr_max_attempt_pages_dense_cue = max(
            16,
            int(self._getenv("MODULE2_OCR_MAX_ATTEMPT_PAGES_DENSE_CUE", "72")),
        )
        return {
            "ocr_max_pages": max(1, int(self._getenv("MODULE2_OCR_MAX_PAGES", "4"))),
            "ocr_extra_sample_pages": max(0, int(self._getenv("MODULE2_OCR_EXTRA_SAMPLE_PAGES", "10"))),
            "ocr_time_budget_sec": ocr_time_budget_sec,
            "ocr_time_budget_per_page": max(0.2, float(self._getenv("MODULE2_OCR_TIME_BUDGET_PER_PAGE", "2.8"))),
            "ocr_time_budget_max_sec": max(
                ocr_time_budget_sec,
                float(self._getenv("MODULE2_OCR_TIME_BUDGET_MAX_SEC", "300")),
            ),
            "ocr_budget_guard_ratio": max(
                0.5,
                min(0.98, float(self._getenv("MODULE2_OCR_BUDGET_GUARD_RATIO", "0.90"))),
            ),
            "ocr_min_pages_before_budget": max(3, int(self._getenv("MODULE2_OCR_MIN_PAGES_BEFORE_BUDGET", "22"))),
            "ocr_cue_scan_pages": max(
                visual_probe_pages,
                int(self._getenv("MODULE2_OCR_CUE_SCAN_PAGES", str(max_pages_visual))),
            ),
            "ocr_cue_max_pages": max(0, int(self._getenv("MODULE2_OCR_CUE_MAX_PAGES", "220"))),
            "ocr_cue_boost_max_pages": max(1, int(self._getenv("MODULE2_OCR_CUE_BOOST_MAX_PAGES", "110"))),
            "ocr_cue_neighbor": max(0, int(self._getenv("MODULE2_OCR_CUE_NEIGHBOR", "1"))),
            "visual_weak_table_min": max(1, int(self._getenv("MODULE2_VISUAL_WEAK_TABLE_MIN", "4"))),
            "visual_weak_table_quality": max(
                0.0,
                min(1.0, float(self._getenv("MODULE2_VISUAL_WEAK_TABLE_QUALITY", "0.35"))),
            ),
            "visual_force_ocr_on_weak_native": self._bool_env("MODULE2_VISUAL_FORCE_OCR_ON_WEAK_NATIVE", "true"),
            "ocr_min_coverage_ratio": min(
                1.0,
                max(0.02, float(self._getenv("MODULE2_OCR_MIN_COVERAGE_RATIO", "0.14"))),
            ),
            "ocr_max_scan_pages": max(1, int(self._getenv("MODULE2_OCR_MAX_SCAN_PAGES", "96"))),
            "ocr_min_scan_pages": max(1, int(self._getenv("MODULE2_OCR_MIN_SCAN_PAGES", "28"))),
            "ocr_front_scan_pages": max(0, int(self._getenv("MODULE2_OCR_FRONT_SCAN_PAGES", "72"))),
            "ocr_large_doc_page_threshold": max(
                50,
                int(self._getenv("MODULE2_OCR_LARGE_DOC_PAGE_THRESHOLD", "220")),
            ),
            "ocr_large_doc_dpi": max(72, int(self._getenv("MODULE2_OCR_LARGE_DOC_DPI", "96"))),
            "ocr_low_priority_dpi": max(72, int(self._getenv("MODULE2_OCR_LOW_PRIORITY_DPI", "84"))),
            "ocr_high_priority_pages": max(1, int(self._getenv("MODULE2_OCR_HIGH_PRIORITY_PAGES", "14"))),
            "ocr_dense_cue_threshold": max(20, int(self._getenv("MODULE2_OCR_DENSE_CUE_THRESHOLD", "160"))),
            "ocr_max_attempt_pages_dense_cue": ocr_max_attempt_pages_dense_cue,
            "ocr_max_attempt_pages_mid_cue": max(
                ocr_max_attempt_pages_dense_cue,
                int(self._getenv("MODULE2_OCR_MAX_ATTEMPT_PAGES_MID_CUE", "84")),
            ),
            "ocr_dynamic_neighbor_pages": max(0, int(self._getenv("MODULE2_OCR_DYNAMIC_NEIGHBOR_PAGES", "0"))),
            "ocr_dynamic_neighbor_auto_enable": self._bool_env("MODULE2_OCR_DYNAMIC_NEIGHBOR_AUTO_ENABLE", "true"),
            "ocr_dynamic_neighbor_auto_max": max(0, int(self._getenv("MODULE2_OCR_DYNAMIC_NEIGHBOR_AUTO_MAX", "8"))),
            "ocr_dynamic_early_stop_enable": self._bool_env("MODULE2_OCR_DYNAMIC_EARLY_STOP_ENABLE", "true"),
            "ocr_dynamic_early_stop_min_pages": max(
                12,
                int(self._getenv("MODULE2_OCR_DYNAMIC_EARLY_STOP_MIN_PAGES", "34")),
            ),
            "ocr_dynamic_early_stop_streak": max(
                4,
                int(self._getenv("MODULE2_OCR_DYNAMIC_EARLY_STOP_STREAK", "14")),
            ),
            "ocr_dynamic_early_stop_min_signal_pages": max(
                2,
                int(self._getenv("MODULE2_OCR_DYNAMIC_EARLY_STOP_MIN_SIGNAL_PAGES", "8")),
            ),
            "ocr_low_cue_boost_enable": self._bool_env("MODULE2_OCR_LOW_CUE_BOOST_ENABLE", "false"),
            "ocr_low_cue_min_pages_cap": max(
                24,
                int(self._getenv("MODULE2_OCR_LOW_CUE_MIN_PAGES_CAP", "44")),
            ),
            "enable_fitz_table": self._bool_env("MODULE2_ENABLE_FITZ_TABLE", "true"),
            "ocr_table_min_cols": max(2, int(self._getenv("MODULE2_OCR_TABLE_MIN_COLS", "2"))),
            "ocr_table_min_rows": max(2, int(self._getenv("MODULE2_OCR_TABLE_MIN_ROWS", "2"))),
            "ocr_table_row_tol": max(0.006, float(self._getenv("MODULE2_OCR_TABLE_ROW_TOL", "0.018"))),
            "ocr_table_col_tol": max(0.01, float(self._getenv("MODULE2_OCR_TABLE_COL_TOL", "0.04"))),
            "ocr_table_row_gap": max(0.02, float(self._getenv("MODULE2_OCR_TABLE_ROW_GAP", "0.08"))),
            "ocr_table_relaxed_row_gap_scale": max(
                1.0,
                float(self._getenv("MODULE2_OCR_TABLE_RELAXED_ROW_GAP_SCALE", "1.5")),
            ),
            "ocr_table_relaxed_align_min": max(
                0.1,
                min(0.9, float(self._getenv("MODULE2_OCR_TABLE_RELAXED_ALIGN_MIN", "0.36"))),
            ),
            "ocr_table_relaxed_overlap_min": max(
                0.1,
                min(0.9, float(self._getenv("MODULE2_OCR_TABLE_RELAXED_OVERLAP_MIN", "0.3"))),
            ),
            "ocr_table_relaxed_col_diff_max": max(
                1,
                int(self._getenv("MODULE2_OCR_TABLE_RELAXED_COL_DIFF_MAX", "2")),
            ),
            "ocr_table_min_quality": ocr_table_min_quality,
            "ocr_table_relaxed_min_quality": max(
                0.1,
                min(
                    ocr_table_min_quality,
                    float(self._getenv("MODULE2_OCR_TABLE_RELAXED_MIN_QUALITY", "0.42")),
                ),
            ),
            "ocr_relaxed_trigger_table_count": max(
                1,
                int(self._getenv("MODULE2_OCR_RELAXED_TRIGGER_TABLE_COUNT", "6")),
            ),
            "ocr_line_aug_max_extra_cue_pages": max(
                0,
                int(self._getenv("MODULE2_OCR_LINE_AUG_MAX_EXTRA_CUE_PAGES", "24")),
            ),
            "ocr_uncovered_line_aug_pages": max(
                0,
                int(self._getenv("MODULE2_OCR_UNCOVERED_LINE_AUG_PAGES", "8")),
            ),
            "table_max_rows": max(1, int(self._getenv("MODULE2_TABLE_MAX_ROWS", "120"))),
            "table_max_cols": max(1, int(self._getenv("MODULE2_TABLE_MAX_COLS", "20"))),
            "table_cell_cap": max(200, int(self._getenv("MODULE2_TABLE_CELL_CAP", "3000"))),
            "xlsx_sheet_limit": max(1, int(self._getenv("MODULE2_XLSX_SHEET_LIMIT", "8"))),
            "xlsx_cell_cap": max(200, int(self._getenv("MODULE2_XLSX_CELL_CAP", "1600"))),
        }

    def build_docx_media_config(self) -> Dict[str, Any]:
        unbounded_visual_cap = 1_000_000
        raw_docx_media_max_assets = str(self._getenv("MODULE2_DOCX_MEDIA_MAX_ASSETS", "24") or "24").strip()
        try:
            docx_media_max_assets_value = int(raw_docx_media_max_assets)
        except Exception:
            docx_media_max_assets_value = 24

        raw_docx_media_vision_max_assets = str(
            self._getenv("MODULE2_DOCX_MEDIA_VISION_MAX_ASSETS", "6") or "6"
        ).strip()
        try:
            docx_media_vision_max_assets_value = int(raw_docx_media_vision_max_assets)
        except Exception:
            docx_media_vision_max_assets_value = 6

        docx_media_max_assets = self._limit_env_value(
            "MODULE2_DOCX_MEDIA_MAX_ASSETS",
            24,
            minimum=0,
            unlimited_value=unbounded_visual_cap,
        )
        return {
            "docx_chart_xml_enable": self._bool_env("MODULE2_DOCX_CHART_XML_ENABLE", "true"),
            "word_pdf_parse_use_source_signals": self._bool_env("MODULE2_WORD_PDF_PARSE_USE_SOURCE_SIGNALS", "false"),
            "word_pdf_docx_chart_xml_merge_enable": self._bool_env(
                "MODULE2_WORD_PDF_DOCX_CHART_XML_MERGE_ENABLE",
                "true",
            ),
            "docx_media_probe_enable": self._bool_env("MODULE2_DOCX_MEDIA_PROBE_ENABLE", "true"),
            "docx_media_max_assets_unbounded": docx_media_max_assets_value <= 0,
            "docx_media_max_assets": docx_media_max_assets,
            "docx_media_vision_enable": self._bool_env("MODULE2_DOCX_MEDIA_VISION_ENABLE", "true"),
            "docx_media_nested_gemini_enhance_enable": (
                self._getenv(
                    "MODULE2_DOCX_MEDIA_NESTED_GEMINI_ENHANCE_ENABLE",
                    self._getenv("MODULE2_ENABLE_GEMINI_VISION_ENHANCE", "true"),
                ).lower()
                in {"1", "true", "yes"}
            ),
            "docx_media_vision_max_assets_unbounded": docx_media_vision_max_assets_value <= 0,
            "docx_media_vision_max_assets": min(
                docx_media_max_assets,
                self._limit_env_value(
                    "MODULE2_DOCX_MEDIA_VISION_MAX_ASSETS",
                    6,
                    minimum=0,
                    unlimited_value=docx_media_max_assets,
                ),
            ),
            "docx_media_vision_max_bytes": max(
                200 * 1024,
                int(self._getenv("MODULE2_DOCX_MEDIA_VISION_MAX_BYTES", str(6 * 1024 * 1024))),
            ),
            "docx_media_vision_chart_only": self._bool_env("MODULE2_DOCX_MEDIA_VISION_CHART_ONLY", "true"),
            "docx_media_vision_allow_noncue": self._bool_env("MODULE2_DOCX_MEDIA_VISION_ALLOW_NONCUE", "true"),
            "nonpdf_figure_max": max(0, int(self._getenv("MODULE2_NONPDF_FIGURE_MAX", "24"))),
        }

    def build_table_merge_and_vision_config(
        self,
        *,
        max_pages_visual: int,
        native_text_threshold: int,
    ) -> Dict[str, Any]:
        gemini_vision_reasoning_effort = str(
            self._getenv("MODULE2_GEMINI_VISION_REASONING_EFFORT", "minimal") or "minimal"
        ).strip().lower() or "minimal"
        if gemini_vision_reasoning_effort not in {"minimal", "low", "medium", "high"}:
            gemini_vision_reasoning_effort = "minimal"

        default_vision_endpoint_style = "openai_chat_completions"
        gemini_vision_endpoint_style = str(
            self._getenv("MODULE2_GEMINI_VISION_ENDPOINT_STYLE", default_vision_endpoint_style)
            or default_vision_endpoint_style
        ).strip().lower()
        if gemini_vision_endpoint_style in {"openai", "openai_chat", "chat_completions"}:
            gemini_vision_endpoint_style = "openai_chat_completions"
        if gemini_vision_endpoint_style in {"native", "google_native", "gemini_native"}:
            raise RuntimeError(
                "MODULE2_GEMINI_VISION_ENDPOINT_STYLE no longer supports native Gemini/Google branches; "
                "set it to openai_chat_completions."
            )
        if gemini_vision_endpoint_style != "openai_chat_completions":
            gemini_vision_endpoint_style = default_vision_endpoint_style

        pipeline_mode = (self._getenv("MODULE2_PIPELINE_MODE", "visual_first") or "visual_first").strip().lower()
        if pipeline_mode not in {"legacy", "hybrid", "visual_first"}:
            pipeline_mode = "hybrid"

        visual_figure_chart_score_min = max(
            1,
            int(self._getenv("MODULE2_VISUAL_FIGURE_CHART_SCORE_MIN", "3")),
        )
        visual_runtime_large_doc_page_threshold = max(
            8,
            int(self._getenv("MODULE2_VISUAL_LARGE_DOC_PAGE_THRESHOLD", "16")),
        )
        visual_runtime_large_doc_chart_score_min = max(
            visual_figure_chart_score_min,
            int(self._getenv("MODULE2_VISUAL_LARGE_DOC_CHART_SCORE_MIN", "4")),
        )
        visual_runtime_extreme_doc_layout_page_cap = max(
            12,
            int(self._getenv("MODULE2_VISUAL_EXTREME_DOC_LAYOUT_PAGE_CAP", "40")),
        )
        visual_first_max_pages = min(
            max_pages_visual,
            max(1, int(self._getenv("MODULE2_VISUAL_FIRST_MAX_PAGES", "120"))),
        )
        pdf_text_heavy_max_visual_cues = max(
            0,
            int(self._getenv("MODULE2_PDF_TEXT_HEAVY_MAX_VISUAL_CUES", "1")),
        )
        return {
            "table_merge_enable": self._bool_env("MODULE2_TABLE_MERGE_ENABLE", "true"),
            "table_merge_max_page_gap": max(1, int(self._getenv("MODULE2_TABLE_MERGE_MAX_PAGE_GAP", "1"))),
            "table_merge_header_sim": max(
                0.0,
                min(1.0, float(self._getenv("MODULE2_TABLE_MERGE_HEADER_SIM_THRESHOLD", "0.58"))),
            ),
            "table_merge_col_overlap": max(
                0.3,
                min(1.0, float(self._getenv("MODULE2_TABLE_MERGE_COL_OVERLAP_THRESHOLD", "0.55"))),
            ),
            "enable_gemini_vision_enhance": self._bool_env("MODULE2_ENABLE_GEMINI_VISION_ENHANCE", "true"),
            "gemini_vision_model": self._getenv(
                "MODULE2_GEMINI_VISION_MODEL",
                self._getenv("MODULE2_GEMINI_MODEL", "qwen3-vl-plus"),
            ),
            "gemini_vision_base_url": self._getenv(
                "MODULE2_GEMINI_VISION_BASE_URL",
                self._getenv("MODULE2_LLM_BASE_URL", self._getenv("MODULE2_LLM_API_BASE_URL", "")),
            ),
            "gemini_vision_endpoint_style": gemini_vision_endpoint_style,
            "gemini_vision_timeout_sec": max(5.0, float(self._getenv("MODULE2_GEMINI_VISION_TIMEOUT_SEC", "25"))),
            "gemini_vision_dpi": max(96, int(self._getenv("MODULE2_GEMINI_VISION_DPI", "150"))),
            "gemini_vision_max_side_px": max(768, int(self._getenv("MODULE2_GEMINI_VISION_MAX_SIDE_PX", "1800"))),
            "gemini_vision_max_pages": self._limit_env_value(
                "MODULE2_GEMINI_VISION_MAX_PAGES",
                24,
                minimum=0,
                unlimited_value=max_pages_visual,
            ),
            "gemini_vision_max_tables_per_page": self._limit_env_value(
                "MODULE2_GEMINI_VISION_MAX_TABLES_PER_PAGE",
                5,
                minimum=1,
                unlimited_value=512,
            ),
            "gemini_vision_max_figures_per_page": self._limit_env_value(
                "MODULE2_GEMINI_VISION_MAX_FIGURES_PER_PAGE",
                8,
                minimum=0,
                unlimited_value=512,
            ),
            "gemini_vision_enable_figures": self._bool_env("MODULE2_GEMINI_VISION_ENABLE_FIGURES", "true"),
            "gemini_vision_min_table_quality": max(
                0.1,
                min(1.0, float(self._getenv("MODULE2_GEMINI_VISION_MIN_TABLE_QUALITY", "0.72"))),
            ),
            "gemini_vision_min_figure_quality": max(
                0.1,
                min(1.0, float(self._getenv("MODULE2_GEMINI_VISION_MIN_FIGURE_QUALITY", "0.56"))),
            ),
            "gemini_vision_max_output_tokens": max(
                512,
                int(self._getenv("MODULE2_GEMINI_VISION_MAX_OUTPUT_TOKENS", "4096")),
            ),
            "gemini_vision_reasoning_effort": gemini_vision_reasoning_effort,
            "gemini_native_fallback_enabled": self._bool_env("MODULE2_GEMINI_NATIVE_FALLBACK", "false"),
            "gemini_vision_consecutive_fail_stop": max(
                1,
                int(self._getenv("MODULE2_GEMINI_VISION_CONSECUTIVE_FAIL_STOP", "2")),
            ),
            "visual_vision_concurrency": max(
                1,
                min(4, int(self._getenv("MODULE2_VISION_CONCURRENCY", "2"))),
            ),
            "pipeline_mode": pipeline_mode,
            "enable_mineru_layout": self._bool_env("MODULE2_ENABLE_MINERU_LAYOUT", "true"),
            "visual_first_allow_legacy_fallback": self._bool_env(
                "MODULE2_VISUAL_FIRST_ALLOW_LEGACY_FALLBACK",
                "false",
            ),
            "visual_first_max_pages": visual_first_max_pages,
            "visual_first_max_pages_scanned": min(
                visual_first_max_pages,
                max(1, int(self._getenv("MODULE2_VISUAL_FIRST_MAX_PAGES_SCANNED", "72"))),
            ),
            "visual_text_only_min_chars": max(
                20,
                int(self._getenv("MODULE2_VISUAL_TEXT_ONLY_MIN_CHARS", "80")),
            ),
            "visual_max_objects": max(8, int(self._getenv("MODULE2_VISUAL_MAX_OBJECTS", "220"))),
            "visual_table_max_per_page": max(
                1,
                int(self._getenv("MODULE2_VISUAL_TABLE_MAX_PER_PAGE", "6")),
            ),
            "visual_figure_max_per_page": max(
                0,
                int(self._getenv("MODULE2_VISUAL_FIGURE_MAX_PER_PAGE", "8")),
            ),
            "visual_table_min_confidence": max(
                0.0,
                min(1.0, float(self._getenv("MODULE2_VISUAL_TABLE_MIN_CONFIDENCE", "0.45"))),
            ),
            "visual_figure_min_confidence": max(
                0.0,
                min(1.0, float(self._getenv("MODULE2_VISUAL_FIGURE_MIN_CONFIDENCE", "0.35"))),
            ),
            "visual_figure_chart_only": self._bool_env("MODULE2_VISUAL_FIGURE_CHART_ONLY", "true"),
            "visual_figure_allow_cueless_fallback": self._bool_env(
                "MODULE2_VISUAL_FIGURE_ALLOW_CUELESS_FALLBACK",
                "true",
            ),
            "visual_figure_cueless_fallback_max": max(
                0,
                int(self._getenv("MODULE2_VISUAL_FIGURE_CUELESS_FALLBACK_MAX", "2")),
            ),
            "visual_figure_chart_score_min": visual_figure_chart_score_min,
            "visual_figure_refine_budget": max(
                0,
                int(self._getenv("MODULE2_VISUAL_FIGURE_REFINE_BUDGET", "8")),
            ),
            "visual_figure_refine_min_score": max(
                1,
                int(self._getenv("MODULE2_VISUAL_FIGURE_REFINE_MIN_SCORE", "6")),
            ),
            "visual_runtime_large_doc_page_threshold": visual_runtime_large_doc_page_threshold,
            "visual_runtime_large_doc_image_threshold": max(
                4,
                int(self._getenv("MODULE2_VISUAL_LARGE_DOC_IMAGE_THRESHOLD", "10")),
            ),
            "visual_runtime_large_doc_max_objects": max(
                8,
                int(self._getenv("MODULE2_VISUAL_LARGE_DOC_MAX_OBJECTS", "96")),
            ),
            "visual_runtime_large_doc_figure_max_per_page": max(
                1,
                int(self._getenv("MODULE2_VISUAL_LARGE_DOC_FIGURE_MAX_PER_PAGE", "4")),
            ),
            "visual_runtime_large_doc_cueless_fallback_max": max(
                0,
                int(self._getenv("MODULE2_VISUAL_LARGE_DOC_CUELESS_FALLBACK_MAX", "0")),
            ),
            "visual_runtime_large_doc_chart_score_min": visual_runtime_large_doc_chart_score_min,
            "visual_runtime_large_doc_refine_budget": max(
                0,
                int(self._getenv("MODULE2_VISUAL_LARGE_DOC_REFINE_BUDGET", "4")),
            ),
            "visual_runtime_extreme_doc_page_threshold": max(
                visual_runtime_large_doc_page_threshold + 4,
                int(self._getenv("MODULE2_VISUAL_EXTREME_DOC_PAGE_THRESHOLD", "32")),
            ),
            "visual_runtime_extreme_doc_max_objects": max(
                8,
                int(self._getenv("MODULE2_VISUAL_EXTREME_DOC_MAX_OBJECTS", "56")),
            ),
            "visual_runtime_extreme_doc_figure_max_per_page": max(
                1,
                int(self._getenv("MODULE2_VISUAL_EXTREME_DOC_FIGURE_MAX_PER_PAGE", "2")),
            ),
            "visual_runtime_extreme_doc_cueless_fallback_max": max(
                0,
                int(self._getenv("MODULE2_VISUAL_EXTREME_DOC_CUELESS_FALLBACK_MAX", "0")),
            ),
            "visual_runtime_extreme_doc_chart_score_min": max(
                visual_runtime_large_doc_chart_score_min,
                int(self._getenv("MODULE2_VISUAL_EXTREME_DOC_CHART_SCORE_MIN", "5")),
            ),
            "visual_runtime_extreme_doc_refine_budget": max(
                0,
                int(self._getenv("MODULE2_VISUAL_EXTREME_DOC_REFINE_BUDGET", "2")),
            ),
            "visual_runtime_extreme_doc_layout_page_cap": visual_runtime_extreme_doc_layout_page_cap,
            "visual_runtime_office_text_layout_page_cap": max(
                12,
                int(
                    self._getenv(
                        "MODULE2_VISUAL_OFFICE_TEXT_LAYOUT_PAGE_CAP",
                        str(visual_runtime_extreme_doc_layout_page_cap),
                    )
                ),
            ),
            "visual_runtime_mixed_text_layout_page_cap": max(
                16,
                int(self._getenv("MODULE2_VISUAL_MIXED_TEXT_LAYOUT_PAGE_CAP", "48")),
            ),
            "mineru_text_first_office_pdf_enable": self._bool_env(
                "MODULE2_MINERU_TEXT_FIRST_OFFICE_PDF_ENABLE",
                "true",
            ),
            "mineru_text_first_office_pdf_min_pages": max(
                4,
                int(
                    self._getenv(
                        "MODULE2_MINERU_TEXT_FIRST_OFFICE_PDF_MIN_PAGES",
                        str(visual_runtime_large_doc_page_threshold),
                    )
                ),
            ),
            "mineru_text_first_office_pdf_min_probe_chars": max(
                native_text_threshold,
                int(self._getenv("MODULE2_MINERU_TEXT_FIRST_OFFICE_PDF_MIN_PROBE_CHARS", "900")),
            ),
            "pdf_text_first_enable": self._bool_env("MODULE2_PDF_TEXT_FIRST_ENABLE", "true"),
            "pdf_text_heavy_min_probe_chars": max(
                native_text_threshold * 2,
                int(self._getenv("MODULE2_PDF_TEXT_HEAVY_MIN_PROBE_CHARS", "1800")),
            ),
            "pdf_text_heavy_min_chars_per_page": max(
                native_text_threshold,
                int(self._getenv("MODULE2_PDF_TEXT_HEAVY_MIN_CHARS_PER_PAGE", "850")),
            ),
            "pdf_text_heavy_max_visual_cues": pdf_text_heavy_max_visual_cues,
            "pdf_mixed_text_pref_min_chars_per_page": max(
                native_text_threshold,
                int(self._getenv("MODULE2_PDF_MIXED_TEXT_PREF_MIN_CHARS_PER_PAGE", "520")),
            ),
            "pdf_mixed_text_pref_max_visual_cues": max(
                pdf_text_heavy_max_visual_cues,
                int(self._getenv("MODULE2_PDF_MIXED_TEXT_PREF_MAX_VISUAL_CUES", "4")),
            ),
            "pdf_text_only_short_circuit_enable": self._bool_env(
                "MODULE2_PDF_TEXT_ONLY_SHORT_CIRCUIT_ENABLE",
                "true",
            ),
            "visual_context_max_chars": max(
                600,
                int(self._getenv("MODULE2_VISUAL_CONTEXT_MAX_CHARS", "2400")),
            ),
            "visual_use_table_html_fallback": self._bool_env(
                "MODULE2_VISUAL_USE_TABLE_HTML_FALLBACK",
                "true",
            ),
        }

    def build_visual_mineru_config(self, *, module2_cache_root: Path) -> Dict[str, Any]:
        return {
            "mineru_backend": self._getenv("MODULE2_MINERU_BACKEND", "pipeline"),
            "mineru_method": self._getenv("MODULE2_MINERU_METHOD", "auto"),
            "mineru_scanned_method": self._getenv("MODULE2_MINERU_SCANNED_METHOD", "auto"),
            "mineru_timeout_sec": max(120, int(self._getenv("MODULE2_MINERU_TIMEOUT_SEC", "3600"))),
            "mineru_cache_dir": self.resolve_cache_dir(
                self._getenv("MODULE2_MINERU_CACHE_DIR", ""),
                module2_cache_root / "mineru",
            ),
            "mineru_device": self._getenv("MODULE2_MINERU_DEVICE", "cpu"),
            "mineru_method_fallbacks": self._getenv("MODULE2_MINERU_METHOD_FALLBACKS", "auto,ocr,txt"),
            "mineru_enable_cache": self._bool_env("MODULE2_MINERU_ENABLE_CACHE", "true"),
            "mineru_enable_formula": self._bool_env("MODULE2_MINERU_ENABLE_FORMULA", "false"),
            "mineru_enable_table": self._bool_env("MODULE2_MINERU_ENABLE_TABLE", "false"),
            "visual_crop_table_dpi": max(120, int(self._getenv("MODULE2_VISUAL_TABLE_CROP_DPI", "260"))),
            "visual_crop_figure_dpi": max(120, int(self._getenv("MODULE2_VISUAL_FIGURE_CROP_DPI", "220"))),
            "visual_crop_expand_ratio": max(
                0.0,
                min(0.2, float(self._getenv("MODULE2_VISUAL_CROP_EXPAND_RATIO", "0.03"))),
            ),
            "visual_crop_max_side_px": max(
                1200,
                int(self._getenv("MODULE2_VISUAL_CROP_MAX_SIDE_PX", "2800")),
            ),
            "visual_vision_retry_count": max(
                0,
                int(self._getenv("MODULE2_VISUAL_VISION_RETRY_COUNT", "1")),
            ),
            "gemini_cache_dir": self.resolve_cache_dir(
                self._getenv("MODULE2_GEMINI_CACHE_DIR", ""),
                module2_cache_root / "gemini",
            ),
            "gemini_cache_enable": self._bool_env("MODULE2_GEMINI_CACHE_ENABLE", "true"),
        }

    def _bool_env(self, name: str, default: str) -> bool:
        return (self._getenv(name, default) or default).lower() in {"1", "true", "yes"}
