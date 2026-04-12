from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest


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


document_process_pool_runtime_module = _load_module(
    ["module2", "app", "core", "pipeline", "document_process_pool_runtime.py"],
    "_smart_doc_flow_module2_document_process_pool_runtime",
)

DocumentProcessPoolRuntime = document_process_pool_runtime_module.DocumentProcessPoolRuntime
BrokenProcessPool = document_process_pool_runtime_module.BrokenProcessPool


class _FakeProc:
    def __init__(self, alive: bool = True) -> None:
        self._alive = alive
        self.terminated = False

    def is_alive(self) -> bool:
        return self._alive

    def terminate(self) -> None:
        self.terminated = True


class _FakePool:
    def __init__(self) -> None:
        self._processes = {"p1": _FakeProc(True), "p2": _FakeProc(False)}
        self.shutdown_calls: list[tuple[bool, bool]] = []

    def shutdown(self, *, wait: bool, cancel_futures: bool) -> None:
        self.shutdown_calls.append((wait, cancel_futures))


class _FakeLogger:
    def __init__(self) -> None:
        self.warnings: list[tuple[object, ...]] = []

    def warning(self, *args) -> None:
        self.warnings.append(args)


class _FakeLoop:
    def __init__(self, running_loop: asyncio.AbstractEventLoop, *, result=..., exc: Exception | None = None, pending: bool = False) -> None:
        self._running_loop = running_loop
        self._result = result
        self._exc = exc
        self._pending = pending
        self.calls: list[tuple[object, object, tuple[object, ...]]] = []

    def run_in_executor(self, executor, fn, *args):
        self.calls.append((executor, fn, args))
        future = self._running_loop.create_future()
        if self._pending:
            return future
        if self._exc is not None:
            future.set_exception(self._exc)
        else:
            future.set_result(self._result)
        return future


def test_document_process_pool_runtime_reset_pool_rebuilds_and_shuts_down_old_pool() -> None:
    logger = _FakeLogger()
    pools = [_FakePool(), _FakePool()]
    runtime = DocumentProcessPoolRuntime(
        build_pool=lambda: pools.pop(0),
        parse_document_in_subprocess=lambda *args: None,
        logger=logger,
    )

    old_pool = runtime.current_pool()
    generation = runtime.reset_pool("manual_reset")

    assert generation == 1
    assert old_pool.shutdown_calls == [(False, True)]
    assert old_pool._processes["p1"].terminated is True
    assert old_pool._processes["p2"].terminated is False
    assert runtime.current_pool() is not old_pool
    assert logger.warnings[-1] == ("module2 process pool reset to generation=%s due to %s", 1, "manual_reset")


def test_document_process_pool_runtime_runs_parse_in_pool() -> None:
    logger = _FakeLogger()
    pool = _FakePool()
    runtime = DocumentProcessPoolRuntime(
        build_pool=lambda: pool,
        parse_document_in_subprocess=lambda *args: ("ok",),
        logger=logger,
    )

    async def _run():
        running_loop = asyncio.get_running_loop()
        fake_loop = _FakeLoop(running_loop, result=("markdown", {}, [], [], {}))
        result = await runtime.run_parse_in_pool(
            loop=fake_loop,
            file_bytes=b"payload",
            file_name="demo.pdf",
            track="VisualTrack",
            timeout_sec=0.2,
            context_label="unit",
            source_file_name="source.docx",
            source_file_bytes=b"source-bytes",
        )
        assert fake_loop.calls == [
            (
                pool,
                runtime._parse_document_in_subprocess,
                (b"payload", "demo.pdf", "VisualTrack", "source.docx", b"source-bytes"),
            )
        ]
        return result

    assert asyncio.run(_run()) == ("markdown", {}, [], [], {})


def test_document_process_pool_runtime_resets_on_timeout() -> None:
    logger = _FakeLogger()
    pools = [_FakePool(), _FakePool()]
    runtime = DocumentProcessPoolRuntime(
        build_pool=lambda: pools.pop(0),
        parse_document_in_subprocess=lambda *args: None,
        logger=logger,
    )

    async def _run():
        running_loop = asyncio.get_running_loop()
        fake_loop = _FakeLoop(running_loop, pending=True)
        with pytest.raises(TimeoutError):
            await runtime.run_parse_in_pool(
                loop=fake_loop,
                file_bytes=b"payload",
                file_name="demo.pdf",
                track="VisualTrack",
                timeout_sec=0.01,
                context_label="timeout_case",
            )

    asyncio.run(_run())
    assert logger.warnings[-1] == (
        "module2 process pool reset to generation=%s due to %s",
        1,
        "parse_timeout:timeout_case",
    )


def test_document_process_pool_runtime_resets_on_broken_pool() -> None:
    logger = _FakeLogger()
    pools = [_FakePool(), _FakePool()]
    runtime = DocumentProcessPoolRuntime(
        build_pool=lambda: pools.pop(0),
        parse_document_in_subprocess=lambda *args: None,
        logger=logger,
    )

    async def _run():
        running_loop = asyncio.get_running_loop()
        fake_loop = _FakeLoop(running_loop, exc=BrokenProcessPool("broken"))
        with pytest.raises(BrokenProcessPool):
            await runtime.run_parse_in_pool(
                loop=fake_loop,
                file_bytes=b"payload",
                file_name="demo.pdf",
                track="VisualTrack",
                timeout_sec=0.2,
                context_label="broken_case",
            )

    asyncio.run(_run())
    assert logger.warnings[-1] == (
        "module2 process pool reset to generation=%s due to %s",
        1,
        "broken_process_pool:broken_case",
    )
