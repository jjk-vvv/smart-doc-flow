from __future__ import annotations

import time
from threading import Lock
from typing import Any, Dict


class Module4SyncMetricsRuntime:
    """Track module4 sync attempt/success/failure diagnostics."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._state: Dict[str, Any] = {
            "attempted_batches": 0,
            "succeeded_batches": 0,
            "failed_batches": 0,
            "last_error": "",
            "last_success_at": 0.0,
            "last_job_id": "",
            "last_batch_id": "",
            "last_endpoint": "",
            "last_source_batch_key": "",
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def mark_attempt(self) -> None:
        with self._lock:
            self._state["attempted_batches"] = int(self._state.get("attempted_batches", 0) or 0) + 1

    def mark_success(self, *, response_payload: Dict[str, Any], endpoint: str, source_batch_key: str) -> None:
        with self._lock:
            self._state["succeeded_batches"] = int(self._state.get("succeeded_batches", 0) or 0) + 1
            self._state["last_error"] = ""
            self._state["last_success_at"] = time.time()
            self._state["last_job_id"] = str(response_payload.get("job_id") or "")
            self._state["last_batch_id"] = str(response_payload.get("batch_id") or "")
            self._state["last_endpoint"] = str(endpoint or "")
            self._state["last_source_batch_key"] = str(source_batch_key or "")

    def mark_failure(self, *, message: str, endpoint: str, source_batch_key: str) -> None:
        with self._lock:
            self._state["failed_batches"] = int(self._state.get("failed_batches", 0) or 0) + 1
            self._state["last_error"] = str(message or "")[:400]
            self._state["last_endpoint"] = str(endpoint or "")
            self._state["last_source_batch_key"] = str(source_batch_key or "")
