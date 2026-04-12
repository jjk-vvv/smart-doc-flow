from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List

from fastapi import HTTPException


@dataclass(frozen=True)
class ExtractionGraphOutcome:
    final_state: Dict[str, Any]
    extract_ms: int
    used_quick_fallback: bool


class ExtractionGraphRuntime:
    """Run the extraction graph and preserve the existing timeout/fallback semantics."""

    def __init__(self, *, getenv=os.getenv, perf_counter: Callable[[], float] = time.perf_counter) -> None:
        self._getenv = getenv
        self._perf_counter = perf_counter

    async def execute(
        self,
        *,
        file_name: str,
        markdown: str,
        bbox_map: Dict[str, Any],
        table_blocks: List[Dict[str, Any]],
        effective_schema: Dict[str, Any],
        effective_schema_fields: Dict[str, Any],
        figure_blocks: List[Dict[str, Any]],
        max_retries: int,
        extract_timeout_sec: float,
        schema_meta: Dict[str, Any],
        run_graph: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]],
        extraction_llm_semaphore: Any,
        emit_progress,
        run_with_progress_heartbeat,
        resolve_extract_progress_ramp_sec,
        quick_extract_from_tables,
        disable_quick_table_fallback,
    ) -> ExtractionGraphOutcome:
        init_state: Dict[str, Any] = {
            "markdown": markdown,
            "bbox_map": bbox_map,
            "table_blocks": table_blocks,
            "table_summary": "",
            "field_hints": {},
            "schema": effective_schema,
            "results": {},
            "errors": [],
            "soft_warnings": [],
            "retries": 0,
            "max_retries": max_retries,
        }

        extract_t0 = self._perf_counter()
        used_quick_fallback = False
        extracting_message = "正在抽取字段、表格、图片与来源信息"
        await emit_progress("extracting", 0.80, extracting_message)
        try:
            async with extraction_llm_semaphore:
                final_state = await run_with_progress_heartbeat(
                    asyncio.wait_for(run_graph(init_state), timeout=extract_timeout_sec),
                    emit_progress=emit_progress,
                    stage="extracting",
                    base_ratio=0.80,
                    ceiling_ratio=0.93,
                    ramp_sec=resolve_extract_progress_ramp_sec(
                        timeout_sec=extract_timeout_sec,
                        schema_field_count=len(effective_schema_fields),
                        table_count=len(table_blocks),
                        figure_count=len(figure_blocks),
                    ),
                    message=extracting_message,
                )
        except TimeoutError as exc:
            fallback_results = quick_extract_from_tables(
                table_blocks=table_blocks,
                schema_fields=effective_schema_fields,
            )
            if str(schema_meta.get("mode", "")) == "auto" and not disable_quick_table_fallback():
                used_quick_fallback = True
                warning = (
                    f"quick_table_fallback:Extraction timed out for {file_name}"
                    if fallback_results
                    else f"auto_timeout_no_fields:{file_name}"
                )
                final_state = {
                    "results": fallback_results,
                    "errors": [],
                    "soft_warnings": [warning],
                }
            else:
                detail = f"Extraction timed out for {file_name}"
                if str(schema_meta.get("mode", "")) == "auto" and disable_quick_table_fallback():
                    detail = (
                        f"Extraction timed out for {file_name}; quick table fallback is disabled by "
                        "MODULE2_DISABLE_QUICK_TABLE_FALLBACK."
                    )
                raise HTTPException(status_code=504, detail=detail) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Extraction graph failed for {file_name}: {exc}") from exc

        extract_ms = int((self._perf_counter() - extract_t0) * 1000)
        return ExtractionGraphOutcome(
            final_state=final_state,
            extract_ms=extract_ms,
            used_quick_fallback=used_quick_fallback,
        )
