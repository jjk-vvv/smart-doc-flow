from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional


ParseAttempt = Callable[..., Any]
UnpackParseOutput = Callable[[Any], tuple[str, Dict[str, List[float]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]]


class DocxNativeRecoveryRuntime:
    """Coordinate DOCX native recovery attempts without owning parse execution details."""

    def __init__(self, *, getenv=os.getenv) -> None:
        self._getenv = getenv

    async def try_recover(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        reason: str,
        enabled: bool,
        parse_attempt: ParseAttempt,
        unpack_parse_output: UnpackParseOutput,
        timeout_hint_sec: Optional[float] = None,
        nonpdf_total_budget_sec: Optional[float] = None,
        elapsed_sec: float = 0.0,
        nonpdf_guard_sec: float = 0.0,
    ) -> Optional[tuple[str, Dict[str, List[float]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]]:
        if not str(file_name or "").lower().endswith(".docx"):
            return None
        if not bool(enabled):
            return None

        recovery_timeout_sec = max(
            12.0,
            float(self._getenv("MODULE2_DOCX_NATIVE_RECOVERY_TIMEOUT_SEC", "180")),
        )
        if timeout_hint_sec is not None:
            recovery_timeout_sec = min(recovery_timeout_sec, max(12.0, float(timeout_hint_sec)))
        if nonpdf_total_budget_sec is not None:
            remaining_budget = float(nonpdf_total_budget_sec) - max(0.0, float(elapsed_sec)) - max(6.0, float(nonpdf_guard_sec))
            if remaining_budget <= 8.0:
                return None
            recovery_timeout_sec = min(recovery_timeout_sec, max(8.0, remaining_budget))

        parsed_output = await parse_attempt(
            attempt_file_bytes=file_bytes,
            attempt_file_name=file_name,
            attempt_track="NativeDocx",
            attempt_timeout_sec=recovery_timeout_sec,
            context_label=f"{file_name}:NativeDocx",
        )
        markdown, refs, tables, figures, stats = unpack_parse_output(parsed_output)
        recovery_stats = dict(stats) if isinstance(stats, dict) else {}
        recovery_stats["docx_native_recovery"] = True
        recovery_stats["docx_native_recovery_reason"] = reason
        recovery_stats["docx_native_recovery_timeout_sec"] = round(recovery_timeout_sec, 3)
        return markdown, refs, tables, figures, recovery_stats
