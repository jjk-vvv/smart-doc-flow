from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, List, Tuple


ProcessSingleDocBytesFn = Callable[..., Awaitable[Any]]


class ExtractionJobExecutionService:
    """Application service for asynchronous extraction job execution."""

    def __init__(
        self,
        *,
        extraction_job_runtime: Any,
        module4_sync_callback_bundle: Any,
        file_semaphore: asyncio.Semaphore,
        process_single_doc_bytes: ProcessSingleDocBytesFn,
        logger: Any,
    ) -> None:
        self._extraction_job_runtime = extraction_job_runtime
        self._module4_sync_callback_bundle = module4_sync_callback_bundle
        self._file_semaphore = file_semaphore
        self._process_single_doc_bytes = process_single_doc_bytes
        self._logger = logger

    async def _persist_snapshot(self, job_id: str, force: bool) -> None:
        await self._extraction_job_runtime.persist_snapshot(job_id, force)

    async def run_file_task(
        self,
        *,
        job_id: str,
        file_index: int,
        file_name: str,
        file_bytes: bytes,
        file_hash: str,
        schema_obj: Dict[str, Any],
        schema_digest: str,
        max_retries: int,
        tenant_id: str,
    ) -> None:
        async with self._file_semaphore:
            if await self._extraction_job_runtime.should_skip_file(job_id=job_id, file_index=file_index):
                return

            async def _update_progress(stage: str, ratio: float, message: str, extra: Dict[str, Any]) -> None:
                del extra
                updated = await self._extraction_job_runtime.update_file_progress(
                    job_id=job_id,
                    file_index=file_index,
                    file_name=file_name,
                    stage=stage,
                    ratio=ratio,
                    message=message,
                )
                if updated:
                    await self._persist_snapshot(job_id, False)

            try:
                doc = await self._process_single_doc_bytes(
                    file_name=file_name,
                    file_bytes=file_bytes,
                    schema=schema_obj,
                    schema_hash=schema_digest,
                    max_retries=max_retries,
                    tenant_id=tenant_id,
                    progress_hook=_update_progress,
                )
                completion_state = await self._extraction_job_runtime.complete_file(
                    job_id=job_id,
                    file_index=file_index,
                    file_name=file_name,
                    doc=doc,
                )
                if completion_state is None:
                    return
                await self._persist_snapshot(job_id, True)
                if not completion_state:
                    return
            except Exception as exc:
                updated = await self._extraction_job_runtime.fail_file(
                    job_id=job_id,
                    file_index=file_index,
                    file_name=file_name,
                    error_message=f"{type(exc).__name__}: {exc}",
                )
                if updated:
                    await self._persist_snapshot(job_id, True)

    async def run_job(
        self,
        *,
        job_id: str,
        loaded_files: List[Tuple[str, bytes, str, str, str, str]],
        schema_obj: Dict[str, Any],
        schema_digest: str,
        max_retries: int,
        tenant_id: str,
    ) -> None:
        started = await self._extraction_job_runtime.begin_job(job_id)
        if not started:
            return
        await self._persist_snapshot(job_id, True)

        file_tasks = [
            asyncio.create_task(
                self.run_file_task(
                    job_id=job_id,
                    file_index=file_index,
                    file_name=file_name,
                    file_bytes=file_bytes,
                    file_hash=file_hash,
                    schema_obj=schema_obj,
                    schema_digest=schema_digest,
                    max_retries=max_retries,
                    tenant_id=tenant_id,
                )
            )
            for file_index, (file_name, file_bytes, file_hash, _artifact_path, _artifact_url, _mime_type) in enumerate(
                loaded_files,
                start=1,
            )
        ]
        task_results = await asyncio.gather(*file_tasks, return_exceptions=True)

        for file_index, task_result in enumerate(task_results, start=1):
            if not isinstance(task_result, Exception):
                continue
            self._logger.exception(
                "module2 extraction job task crashed job=%s file_index=%s: %s",
                job_id,
                file_index,
                task_result,
            )
            file_name = loaded_files[file_index - 1][0]
            updated = await self._extraction_job_runtime.fail_file(
                job_id=job_id,
                file_index=file_index,
                file_name=file_name,
                error_message=f"{type(task_result).__name__}: {task_result}",
            )
            if updated:
                await self._persist_snapshot(job_id, True)

        _final_documents = await self._extraction_job_runtime.finalize_job(job_id)
        await self._persist_snapshot(job_id, True)

__all__ = ["ExtractionJobExecutionService"]
