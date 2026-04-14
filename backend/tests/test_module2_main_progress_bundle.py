from __future__ import annotations

import asyncio
import sys
from importlib import import_module
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


main_progress_bundle_module = import_module("app.modules.module2.bootstrap.progress")


async def _run_heartbeat(bundle) -> str:
    async def _emit_progress(stage: str, ratio: float, message: str, extra):
        return None

    return await bundle.run_with_progress_heartbeat(
        asyncio.sleep(0, result="ok"),
        emit_progress=_emit_progress,
        stage="parsing",
        base_ratio=0.1,
        message="running",
        interval_sec=0.01,
        ramp_sec=0.01,
    )


def test_build_module2_main_progress_bundle_exposes_expected_progress_helpers() -> None:
    bundle = main_progress_bundle_module.build_module2_main_progress_bundle(
        getenv=lambda name, default=None: default,
    )

    assert bundle.resolve_parse_progress_ramp_sec(parse_input_bytes_len=1024, timeout_sec=60.0) > 0
    visual_pdf_ramp = bundle.resolve_parse_progress_ramp_sec(
        parse_input_bytes_len=2 * 1024 * 1024,
        timeout_sec=3600.0,
        parse_input_name="report.pdf",
        parse_track="VisualTrack",
    )
    native_text_ramp = bundle.resolve_parse_progress_ramp_sec(
        parse_input_bytes_len=2 * 1024 * 1024,
        timeout_sec=3600.0,
        parse_input_name="report.txt",
        parse_track="FastTrack",
    )
    assert visual_pdf_ramp > native_text_ramp
    assert bundle.resolve_extract_progress_ramp_sec(
        timeout_sec=60.0,
        schema_field_count=8,
        table_count=2,
        figure_count=4,
    ) > 0
    assert asyncio.run(_run_heartbeat(bundle)) == "ok"
