from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_module(path_parts: list[str], module_name: str):
    module_path = Path(__file__).resolve().parents[1]
    for part in path_parts:
        module_path = module_path / part
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


parser_config_runtime_module = _load_module(
    ["app", "modules", "module2", "core", "parsers", "parser_config_runtime.py"],
    "_smart_doc_flow_module2_parser_config_runtime",
)

ParserConfigRuntime = parser_config_runtime_module.ParserConfigRuntime


def _limit_env_value(
    name: str,
    default: int,
    *,
    minimum: int = 0,
    unlimited_value: int | None = None,
    env_map=None,
) -> int:
    env = dict(env_map or {})
    raw = str(env.get(name, str(default)) or str(default)).strip()
    try:
        value = int(raw)
    except Exception:
        value = int(default)
    if value <= 0 and unlimited_value is not None:
        return max(minimum, int(unlimited_value))
    return max(minimum, value)


def _build_runtime(tmp_path: Path, env: dict[str, str] | None = None) -> ParserConfigRuntime:
    env_map = dict(env or {})
    repo_root = tmp_path / "repo"
    module2_root = repo_root / "backend" / "app" / "modules" / "module2"
    module2_root.mkdir(parents=True, exist_ok=True)
    return ParserConfigRuntime(
        getenv=lambda name, default="": env_map.get(name, default),
        limit_env_value=lambda name, default, minimum=0, unlimited_value=None: _limit_env_value(
            name,
            default,
            minimum=minimum,
            unlimited_value=unlimited_value,
            env_map=env_map,
        ),
        module2_root=module2_root,
        repo_root=repo_root,
    )


def test_parser_config_runtime_resolves_cache_dir_and_builds_core_parse_config(tmp_path: Path) -> None:
    runtime = _build_runtime(
        tmp_path,
        env={
            "MODULE2_DOC_TO_PDF_ENABLE": "false",
            "MODULE2_WORD_PARSE_VIA_PDF": "false",
            "MODULE2_WORD_CONVERT_ALLOW_NATIVE_FALLBACK": "true",
            "MODULE2_DOC_TO_PDF_TIMEOUT_SEC": "75",
            "MODULE2_MAX_PARSE_PAGES_VISUAL": "160",
            "MODULE2_VISUAL_PROBE_PAGES": "9",
            "MODULE2_NATIVE_TEXT_THRESHOLD": "180",
        },
    )
    repo_cache = tmp_path / "repo" / "shared-cache"
    repo_cache.mkdir(parents=True, exist_ok=True)

    resolved = runtime.resolve_cache_dir(
        "shared-cache",
        tmp_path / "repo" / "backend" / "app" / "modules" / "module2" / ".cache",
    )
    backend_prefixed = runtime.resolve_cache_dir(
        "backend/app/modules/module2/custom-cache",
        tmp_path / "repo" / "backend" / "app" / "modules" / "module2" / ".cache",
    )
    core = runtime.build_core_parse_config(
        module2_cache_root=tmp_path / "repo" / "backend" / "app" / "modules" / "module2" / ".cache",
        max_pages_override=200,
    )

    assert resolved == str(repo_cache.resolve())
    assert backend_prefixed == str(
        (tmp_path / "repo" / "backend" / "app" / "modules" / "module2" / "custom-cache").resolve()
    )
    assert core["artifact_root_dir"] == (
        tmp_path / "repo" / "backend" / "app" / "modules" / "module2" / ".cache"
    ).resolve()
    assert core["office_convert_enabled"] is False
    assert core["word_parse_via_pdf"] is False
    assert core["word_convert_allow_native_fallback"] is True
    assert core["word_pdf_timeout_sec"] == 75.0
    assert core["max_pages"] == 200
    assert core["max_pages_visual"] == 200
    assert core["visual_probe_pages"] == 9
    assert core["native_text_threshold"] == 180


def test_parser_config_runtime_builds_ocr_limits_with_existing_bounds(tmp_path: Path) -> None:
    runtime = _build_runtime(
        tmp_path,
        env={
            "MODULE2_OCR_TIME_BUDGET_SEC": "90",
            "MODULE2_OCR_TIME_BUDGET_MAX_SEC": "80",
            "MODULE2_OCR_CUE_SCAN_PAGES": "4",
            "MODULE2_OCR_TABLE_MIN_QUALITY": "0.52",
            "MODULE2_OCR_TABLE_RELAXED_MIN_QUALITY": "0.9",
            "MODULE2_TABLE_CELL_CAP": "50",
            "MODULE2_XLSX_CELL_CAP": "150",
        },
    )

    config = runtime.build_ocr_table_limits(max_pages_visual=480, visual_probe_pages=12)

    assert config["ocr_time_budget_sec"] == 90.0
    assert config["ocr_time_budget_max_sec"] == 90.0
    assert config["ocr_cue_scan_pages"] == 12
    assert config["ocr_table_min_quality"] == 0.52
    assert config["ocr_table_relaxed_min_quality"] == 0.52
    assert config["table_cell_cap"] == 200
    assert config["xlsx_cell_cap"] == 200


def test_parser_config_runtime_builds_docx_and_table_merge_vision_config(tmp_path: Path) -> None:
    runtime = _build_runtime(
        tmp_path,
        env={
            "MODULE2_DOCX_MEDIA_MAX_ASSETS": "0",
            "MODULE2_DOCX_MEDIA_VISION_MAX_ASSETS": "0",
            "MODULE2_DOCX_MEDIA_NESTED_GEMINI_ENHANCE_ENABLE": "false",
            "MODULE2_PIPELINE_MODE": "unknown",
            "MODULE2_GEMINI_VISION_REASONING_EFFORT": "invalid",
            "MODULE2_GEMINI_VISION_MAX_PAGES": "0",
            "MODULE2_VISUAL_FIRST_MAX_PAGES": "999",
            "MODULE2_VISUAL_FIRST_MAX_PAGES_SCANNED": "999",
            "MODULE2_VISUAL_FIGURE_CHART_SCORE_MIN": "3",
            "MODULE2_VISUAL_LARGE_DOC_CHART_SCORE_MIN": "2",
            "MODULE2_VISUAL_EXTREME_DOC_CHART_SCORE_MIN": "1",
            "MODULE2_PDF_TEXT_HEAVY_MIN_PROBE_CHARS": "180",
        },
    )

    docx_config = runtime.build_docx_media_config()
    vision_config = runtime.build_table_merge_and_vision_config(
        max_pages_visual=480,
        native_text_threshold=200,
    )

    assert docx_config["docx_media_max_assets_unbounded"] is True
    assert docx_config["docx_media_max_assets"] == 1_000_000
    assert docx_config["docx_media_vision_max_assets_unbounded"] is True
    assert docx_config["docx_media_vision_max_assets"] == 1_000_000
    assert docx_config["docx_media_nested_gemini_enhance_enable"] is False
    assert vision_config["pipeline_mode"] == "hybrid"
    assert vision_config["gemini_vision_reasoning_effort"] == "minimal"
    assert vision_config["gemini_vision_max_pages"] == 480
    assert vision_config["visual_first_max_pages"] == 480
    assert vision_config["visual_first_max_pages_scanned"] == 480
    assert vision_config["visual_runtime_large_doc_chart_score_min"] == 3
    assert vision_config["visual_runtime_extreme_doc_chart_score_min"] == 3
    assert vision_config["mineru_text_first_office_pdf_min_pages"] == 16
    assert vision_config["pdf_text_heavy_min_probe_chars"] == 400


def test_parser_config_runtime_builds_visual_mineru_config_with_resolved_paths(tmp_path: Path) -> None:
    runtime = _build_runtime(
        tmp_path,
        env={
            "MODULE2_MINERU_TIMEOUT_SEC": "30",
            "MODULE2_MINERU_CACHE_DIR": "backend/app/modules/module2/cache/mineru-alt",
            "MODULE2_MINERU_DEVICE": "cuda",
            "MODULE2_MINERU_ENABLE_TABLE": "true",
            "MODULE2_VISUAL_TABLE_CROP_DPI": "100",
            "MODULE2_VISUAL_FIGURE_CROP_DPI": "100",
            "MODULE2_VISUAL_CROP_EXPAND_RATIO": "0.5",
            "MODULE2_VISUAL_CROP_MAX_SIDE_PX": "800",
            "MODULE2_VISUAL_VISION_RETRY_COUNT": "-1",
            "MODULE2_GEMINI_CACHE_DIR": "cache/gemini",
            "MODULE2_GEMINI_CACHE_ENABLE": "false",
        },
    )
    repo_gemini_cache = tmp_path / "repo" / "cache" / "gemini"
    repo_gemini_cache.mkdir(parents=True, exist_ok=True)

    config = runtime.build_visual_mineru_config(
        module2_cache_root=tmp_path / "repo" / "backend" / "app" / "modules" / "module2" / ".cache",
    )

    assert config["mineru_timeout_sec"] == 120
    assert config["mineru_cache_dir"] == str(
        (tmp_path / "repo" / "backend" / "app" / "modules" / "module2" / "cache" / "mineru-alt").resolve()
    )
    assert config["mineru_device"] == "cuda"
    assert config["mineru_enable_table"] is True
    assert config["visual_crop_table_dpi"] == 120
    assert config["visual_crop_figure_dpi"] == 120
    assert config["visual_crop_expand_ratio"] == 0.2
    assert config["visual_crop_max_side_px"] == 1200
    assert config["visual_vision_retry_count"] == 0
    assert config["gemini_cache_dir"] == str(repo_gemini_cache.resolve())
    assert config["gemini_cache_enable"] is False
