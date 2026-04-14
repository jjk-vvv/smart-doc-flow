from __future__ import annotations

"""Progress heartbeat helpers for module2 extraction service layer."""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional


GetEnvFn = Callable[[str, str | None], str | None]
EmitProgressFn = Callable[[str, float, str, Optional[Dict[str, Any]]], Awaitable[None]]


_EXTRACTION_PROGRESS_STAGE_META: Dict[str, Dict[str, float]] = {
    "queued": {"ceiling": 0.06, "ramp_sec": 8.0, "max_headroom": 0.02},
    "preflight": {"ceiling": 0.12, "ramp_sec": 4.0, "max_headroom": 0.02},
    "converting": {"ceiling": 0.28, "ramp_sec": 16.0, "max_headroom": 0.05},
    "parsing": {"ceiling": 0.74, "ramp_sec": 24.0, "max_headroom": 0.04},
    "parsed": {"ceiling": 0.78, "ramp_sec": 5.0, "max_headroom": 0.01},
    "extracting": {"ceiling": 0.93, "ramp_sec": 28.0, "max_headroom": 0.05},
    "finalizing": {"ceiling": 0.98, "ramp_sec": 12.0, "max_headroom": 0.015},
}


@dataclass(frozen=True)
class Module2MainProgressBundle:
    resolve_parse_progress_ramp_sec: Callable[..., float]
    resolve_extract_progress_ramp_sec: Callable[..., float]
    run_with_progress_heartbeat: Callable[..., Awaitable[Any]]


def build_module2_main_progress_bundle(
    *,
    getenv: GetEnvFn,
    perf_counter: Callable[[], float] | None = None,
) -> Module2MainProgressBundle:
    resolved_perf_counter = perf_counter or time.perf_counter

    def _normalize_extraction_stage_name(stage: Any) -> str:
        return str(stage or "").strip().lower() or "queued"

    def _ease_out_cubic(value: float) -> float:
        t = max(0.0, min(1.0, float(value or 0.0)))
        return 1.0 - pow(1.0 - t, 3)

    def _heartbeat_progress_ratio(
        *,
        base_ratio: float,
        stage: Any,
        elapsed_sec: float,
        ceiling_ratio: Optional[float] = None,
        ramp_sec: Optional[float] = None,
    ) -> float:
        stage_name = _normalize_extraction_stage_name(stage)
        meta = _EXTRACTION_PROGRESS_STAGE_META.get(stage_name, {})
        base = max(0.0, min(1.0, float(base_ratio or 0.0)))
        resolved_ceiling = max(
            base,
            min(
                1.0,
                float(
                    ceiling_ratio
                    if ceiling_ratio is not None
                    else meta.get("ceiling", min(0.96, base + 0.12))
                ),
            ),
        )
        if resolved_ceiling <= base:
            return base
        resolved_ramp = max(2.0, float(ramp_sec if ramp_sec is not None else meta.get("ramp_sec", 10.0)))
        eased = base + (resolved_ceiling - base) * _ease_out_cubic(elapsed_sec / resolved_ramp)
        max_headroom = max(0.0, min(0.12, float(meta.get("max_headroom", 0.0) or 0.0)))
        if max_headroom <= 0.0 or elapsed_sec <= resolved_ramp:
            return eased
        overrun_elapsed = elapsed_sec - resolved_ramp
        overrun_ramp = max(8.0, resolved_ramp * 2.2)
        extended_ceiling = min(0.995, resolved_ceiling + max_headroom)
        return eased + (extended_ceiling - eased) * _ease_out_cubic(overrun_elapsed / overrun_ramp)

    def _resolve_parse_progress_ramp_sec(
        *,
        parse_input_bytes_len: int,
        timeout_sec: float,
        parse_input_name: str = "",
        parse_track: str = "",
    ) -> float:
        size_mb = max(0.0, float(parse_input_bytes_len) / (1024.0 * 1024.0))
        size_driven = 24.0 + min(36.0, size_mb * 9.0)
        timeout_driven = max(30.0, max(0.0, float(timeout_sec)) * 0.55)
        default_ramp = min(110.0, max(size_driven, timeout_driven))
        is_visual_pdf = (
            str(parse_track or "").strip().lower() == "visualtrack"
            and str(parse_input_name or "").strip().lower().endswith(".pdf")
        )
        if not is_visual_pdf:
            return default_ramp

        # Visual PDF parsing can legitimately spend minutes inside MinerU on CPU.
        # Stretch the ramp so the frontend keeps moving instead of appearing frozen at ~78%.
        visual_size_driven = 80.0 + min(260.0, size_mb * 120.0)
        visual_timeout_driven = 90.0 + min(150.0, max(0.0, float(timeout_sec)) * 0.04)
        return min(360.0, max(default_ramp, visual_size_driven, visual_timeout_driven))

    def _resolve_extract_progress_ramp_sec(
        *,
        timeout_sec: float,
        schema_field_count: int,
        table_count: int,
        figure_count: int,
    ) -> float:
        complexity = (
            max(0.0, min(float(schema_field_count), 24.0)) * 0.7
            + max(0.0, min(float(table_count), 24.0)) * 0.4
            + max(0.0, min(float(figure_count), 120.0)) * 0.08
        )
        complexity_driven = 22.0 + min(28.0, complexity * 1.15)
        timeout_driven = max(24.0, max(0.0, float(timeout_sec)) * 0.42)
        return min(96.0, max(complexity_driven, timeout_driven))

    async def _run_with_progress_heartbeat(
        awaitable: Awaitable[Any],
        *,
        emit_progress: EmitProgressFn,
        stage: str,
        base_ratio: float,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        ceiling_ratio: Optional[float] = None,
        ramp_sec: Optional[float] = None,
        interval_sec: Optional[float] = None,
    ) -> Any:
        stage_name = _normalize_extraction_stage_name(stage)
        tick_interval_sec = max(
            0.35,
            float(interval_sec or (getenv("MODULE2_PROGRESS_HEARTBEAT_INTERVAL_SEC", "0.8") or "0.8")),
        )
        started_at = resolved_perf_counter()
        stop_event = asyncio.Event()

        async def _heartbeat() -> None:
            try:
                while True:
                    try:
                        await asyncio.wait_for(stop_event.wait(), timeout=tick_interval_sec)
                        return
                    except TimeoutError:
                        pass
                    ratio = _heartbeat_progress_ratio(
                        base_ratio=base_ratio,
                        stage=stage_name,
                        elapsed_sec=max(0.0, resolved_perf_counter() - started_at),
                        ceiling_ratio=ceiling_ratio,
                        ramp_sec=ramp_sec,
                    )
                    if ratio > base_ratio:
                        await emit_progress(stage_name, ratio, message, extra)
            except asyncio.CancelledError:
                raise
            except Exception:
                return

        heartbeat_task = asyncio.create_task(_heartbeat())
        try:
            return await awaitable
        finally:
            stop_event.set()
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

    return Module2MainProgressBundle(
        resolve_parse_progress_ramp_sec=_resolve_parse_progress_ramp_sec,
        resolve_extract_progress_ramp_sec=_resolve_extract_progress_ramp_sec,
        run_with_progress_heartbeat=_run_with_progress_heartbeat,
    )
