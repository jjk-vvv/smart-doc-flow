from __future__ import annotations

import asyncio
from importlib import import_module
from pathlib import Path


extraction_jobs_module = import_module("app.modules.module2.services.extraction.job")
ExtractionJobRuntime = extraction_jobs_module.ExtractionJobRuntime


class _FakeLogger:
    def warning(self, *args) -> None:
        pass

    def info(self, *args) -> None:
        pass


def _build_runtime() -> ExtractionJobRuntime:
    return ExtractionJobRuntime(
        state_root_factory=lambda: Path("."),
        safe_artifact_path=lambda path: Path(path),
        job_state_factory=lambda **kwargs: kwargs,
        job_file_state_factory=lambda **kwargs: kwargs,
        document_validate=lambda item: item,
        run_extraction_job=lambda **kwargs: asyncio.sleep(0),
        logger=_FakeLogger(),
    )


def test_extraction_job_runtime_shutdown_persists_and_cancels_running_tasks() -> None:
    runtime = _build_runtime()
    runtime.jobs["job-1"] = {"job_id": "job-1"}
    runtime.jobs["job-2"] = {"job_id": "job-2"}
    persisted: list[tuple[str, bool]] = []
    state = {"cancelled": 0}

    async def _run() -> None:
        async def _pending() -> None:
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                state["cancelled"] += 1
                raise

        task1 = asyncio.create_task(_pending())
        task2 = asyncio.create_task(_pending())
        runtime.tasks["job-1"] = task1
        runtime.tasks["job-2"] = task2
        await asyncio.sleep(0)

        async def _persist_snapshot(job_id: str, force: bool) -> None:
            persisted.append((job_id, force))

        await runtime.shutdown_runtime(persist_snapshot=_persist_snapshot)

        assert persisted == [("job-1", True), ("job-2", True)]
        assert state["cancelled"] == 2
        assert runtime.tasks == {}

    asyncio.run(_run())
