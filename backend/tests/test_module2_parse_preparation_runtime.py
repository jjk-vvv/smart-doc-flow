from __future__ import annotations

import asyncio
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


parse_preparation_runtime_module = _load_module(
    ["module2", "app", "core", "pipeline", "document_pipeline_stages_runtime.py"],
    "_smart_doc_flow_module2_parse_preparation_runtime",
)

ParsePreparationRuntime = parse_preparation_runtime_module.ParsePreparationRuntime


class _BudgetTightenDecision:
    def __init__(self, *, parse_timeout_sec: float, extract_timeout_sec: float, warning: str = "") -> None:
        self.parse_timeout_sec = parse_timeout_sec
        self.extract_timeout_sec = extract_timeout_sec
        self.warning = warning

    @property
    def tightened(self) -> bool:
        return bool(self.warning)


def test_parse_preparation_runtime_preserves_warning_and_binds_runner() -> None:
    runtime = ParsePreparationRuntime(perf_counter=lambda: 20.0)
    captured: dict[str, object] = {}

    def _tighten_parse_budgets_before_parse(**kwargs):
        captured["tighten_kwargs"] = dict(kwargs)
        return _BudgetTightenDecision(parse_timeout_sec=60.0, extract_timeout_sec=90.0)

    def _build_session(**kwargs):
        captured["session_kwargs"] = dict(kwargs)
        return {
            "parse_timeout_sec": 75.0,
            "parse_source_file_name": "source.docx",
            "parse_source_file_bytes": b"docx",
            "progress_message": "parsing visual pdf",
            "progress_extra": {"parse_track": "VisualTrack"},
        }

    async def _emit_progress(stage, ratio, message, extra):
        captured["progress"] = {
            "stage": stage,
            "ratio": ratio,
            "message": message,
            "extra": extra,
        }

    def _build_runner(**kwargs):
        captured["runner_kwargs"] = dict(kwargs)
        return "runner-token"

    async def _run():
        return await runtime.prepare(
            file_name="demo.docx",
            file_bytes=b"docx",
            parse_input_name="demo.pdf",
            parse_track="VisualTrack",
            parse_timeout_sec=50.0,
            extract_timeout_sec=80.0,
            parse_warning="seed",
            nonpdf_total_budget_sec=120.0,
            started_at_sec=5.0,
            nonpdf_guard_sec=2.0,
            original_file_is_word=True,
            tighten_parse_budgets_before_parse=_tighten_parse_budgets_before_parse,
            build_session=_build_session,
            emit_progress=_emit_progress,
            build_runner=_build_runner,
            loop="loop-token",
            acquire_parse_execution_slots="slot-token",
            run_parse_in_process_pool="pool-token",
            run_with_progress_heartbeat="heartbeat-token",
        )

    outcome = asyncio.run(_run())
    assert outcome.parse_timeout_sec == 75.0
    assert outcome.extract_timeout_sec == 90.0
    assert outcome.parse_warning == "seed"
    assert outcome.parse_source_file_name == "source.docx"
    assert outcome.parse_source_file_bytes == b"docx"
    assert outcome.progress_message == "parsing visual pdf"
    assert outcome.progress_extra == {"parse_track": "VisualTrack"}
    assert outcome.parse_attempt_runner == "runner-token"
    assert captured["tighten_kwargs"]["elapsed_before_parse_sec"] == 15.0
    assert captured["session_kwargs"]["parse_timeout_sec"] == 60.0
    assert captured["progress"] == {
        "stage": "parsing",
        "ratio": 0.32,
        "message": "parsing visual pdf",
        "extra": {"parse_track": "VisualTrack"},
    }
    assert captured["runner_kwargs"]["loop"] == "loop-token"
    assert captured["runner_kwargs"]["emit_progress"] is _emit_progress


def test_parse_preparation_runtime_appends_budget_warning_when_tightened() -> None:
    runtime = ParsePreparationRuntime(perf_counter=lambda: 12.0)

    def _tighten_parse_budgets_before_parse(**kwargs):
        return _BudgetTightenDecision(
            parse_timeout_sec=22.0,
            extract_timeout_sec=44.0,
            warning="nonpdf_budget_tight",
        )

    def _build_session(**kwargs):
        return {
            "parse_timeout_sec": 22.0,
            "parse_source_file_name": None,
            "parse_source_file_bytes": None,
            "progress_message": "parsing",
            "progress_extra": {},
        }

    async def _emit_progress(stage, ratio, message, extra):
        return None

    def _build_runner(**kwargs):
        return object()

    async def _run():
        return await runtime.prepare(
            file_name="demo.txt",
            file_bytes=b"text",
            parse_input_name="demo.txt",
            parse_track="FastTrack",
            parse_timeout_sec=30.0,
            extract_timeout_sec=50.0,
            parse_warning="seed",
            nonpdf_total_budget_sec=40.0,
            started_at_sec=2.0,
            nonpdf_guard_sec=2.0,
            original_file_is_word=False,
            tighten_parse_budgets_before_parse=_tighten_parse_budgets_before_parse,
            build_session=_build_session,
            emit_progress=_emit_progress,
            build_runner=_build_runner,
            loop=None,
            acquire_parse_execution_slots=None,
            run_parse_in_process_pool=None,
            run_with_progress_heartbeat=None,
        )

    outcome = asyncio.run(_run())
    assert outcome.parse_timeout_sec == 22.0
    assert outcome.extract_timeout_sec == 44.0
    assert outcome.parse_warning == "seed|nonpdf_budget_tight"
