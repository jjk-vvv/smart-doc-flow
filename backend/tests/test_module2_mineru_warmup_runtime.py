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


mineru_warmup_runtime_module = _load_module(
    ["module2", "app", "core", "integration", "mineru_warmup_runtime.py"],
    "_smart_doc_flow_module2_mineru_warmup_runtime",
)

MineruWarmupRuntime = mineru_warmup_runtime_module.MineruWarmupRuntime


class _FakeLogger:
    def __init__(self) -> None:
        self.infos: list[tuple[object, ...]] = []
        self.warnings: list[tuple[object, ...]] = []

    def info(self, *args) -> None:
        self.infos.append(args)

    def warning(self, *args) -> None:
        self.warnings.append(args)


def test_mineru_warmup_runtime_marks_disabled_state() -> None:
    logger = _FakeLogger()
    runtime = MineruWarmupRuntime(logger=logger)

    async def _run() -> None:
        await runtime.startup_warmup_task(
            enabled=False,
            worker_count=0,
            delay_sec=0.0,
            timeout_sec=30.0,
            build_warmup_pdf_bytes=lambda: b"unused",
            run_parse_in_process_pool=lambda **kwargs: None,
        )

    asyncio.run(_run())
    snapshot = runtime.snapshot()
    assert snapshot["enabled"] is False
    assert snapshot["worker_count"] == 0
    assert snapshot["status"] == "disabled"
    assert snapshot["detail"] == "warmup_disabled_by_env"
    assert snapshot["error"] == ""


def test_mineru_warmup_runtime_completes_and_records_status() -> None:
    logger = _FakeLogger()
    runtime = MineruWarmupRuntime(logger=logger)
    captured_calls: list[dict[str, object]] = []

    async def _run_parse_in_process_pool(**kwargs) -> None:
        captured_calls.append(dict(kwargs))

    async def _run() -> None:
        await runtime.startup_warmup_task(
            enabled=True,
            worker_count=2,
            delay_sec=0.0,
            timeout_sec=45.0,
            build_warmup_pdf_bytes=lambda: b"%PDF-warmup",
            run_parse_in_process_pool=_run_parse_in_process_pool,
        )

    asyncio.run(_run())
    snapshot = runtime.snapshot()
    assert snapshot["enabled"] is True
    assert snapshot["worker_count"] == 2
    assert snapshot["status"] == "completed"
    assert snapshot["ok"] is True
    assert snapshot["error"] == ""
    assert snapshot["detail"].startswith("warmed_workers=2;")
    assert len(captured_calls) == 2
    assert captured_calls[0]["file_name"] == "module2_mineru_warmup_1.pdf"
    assert captured_calls[0]["track"] == "VisualTrack"
    assert captured_calls[0]["timeout_sec"] == 45.0
    assert captured_calls[0]["context_label"] == "startup_mineru_warmup_1"
    assert captured_calls[1]["file_name"] == "module2_mineru_warmup_2.pdf"
    assert logger.infos[-1][0] == "module2 MinerU warmup completed workers=%s elapsed=%.3fs"


def test_mineru_warmup_runtime_marks_failed_state() -> None:
    logger = _FakeLogger()
    runtime = MineruWarmupRuntime(logger=logger)

    async def _run_parse_in_process_pool(**kwargs) -> None:
        raise RuntimeError("warmup boom")

    async def _run() -> None:
        await runtime.startup_warmup_task(
            enabled=True,
            worker_count=1,
            delay_sec=0.0,
            timeout_sec=45.0,
            build_warmup_pdf_bytes=lambda: b"%PDF-warmup",
            run_parse_in_process_pool=_run_parse_in_process_pool,
        )

    asyncio.run(_run())
    snapshot = runtime.snapshot()
    assert snapshot["status"] == "failed"
    assert snapshot["ok"] is False
    assert snapshot["detail"] == "warmup_failed"
    assert snapshot["error"] == "RuntimeError: warmup boom"
    assert logger.warnings[-1] == ("module2 MinerU warmup failed: %s", "RuntimeError: warmup boom")
