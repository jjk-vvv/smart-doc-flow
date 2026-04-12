from __future__ import annotations

import threading
import time
from typing import Dict, Set

from .config import Assistant1Settings
from .ingest_pipeline import Assistant1IngestPipeline
from .retrieval_pipeline import Assistant1RetrievalPipeline


class Assistant1WarmupRuntime:
    def __init__(
        self,
        settings: Assistant1Settings | None = None,
        *,
        retrieval: Assistant1RetrievalPipeline | None = None,
        ingest: Assistant1IngestPipeline | None = None,
        ready_ttl_sec: float = 600.0,
    ) -> None:
        self.settings = settings or Assistant1Settings.from_env()
        self.retrieval = retrieval or Assistant1RetrievalPipeline(self.settings)
        self.ingest = ingest or Assistant1IngestPipeline(self.settings)
        self.ready_ttl_sec = max(60.0, float(ready_ttl_sec or 600.0))
        self._lock = threading.Lock()
        self._inflight: Set[str] = set()
        self._ready_at: Dict[str, float] = {}
        self._last_error: Dict[str, str] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.settings.database_dsn and self.ingest.embedder.ready)

    def schedule(self, file_hash: str, *, reason: str = "") -> bool:
        normalized_file_hash = str(file_hash or "").strip()
        if not normalized_file_hash or not self.enabled:
            return False
        now_ts = time.time()
        with self._lock:
            ready_at = float(self._ready_at.get(normalized_file_hash) or 0.0)
            if ready_at > 0 and (now_ts - ready_at) < self.ready_ttl_sec:
                return False
            if normalized_file_hash in self._inflight:
                return False
            self._inflight.add(normalized_file_hash)
        worker = threading.Thread(
            target=self._run_warmup,
            args=(normalized_file_hash, str(reason or "").strip()),
            daemon=True,
            name=f"assistant1-warmup-{normalized_file_hash[:8] or 'doc'}",
        )
        worker.start()
        return True

    def last_error(self, file_hash: str) -> str:
        normalized_file_hash = str(file_hash or "").strip()
        with self._lock:
            return str(self._last_error.get(normalized_file_hash) or "")

    def _mark_ready(self, file_hash: str) -> None:
        with self._lock:
            self._ready_at[file_hash] = time.time()
            self._last_error.pop(file_hash, None)

    def _mark_error(self, file_hash: str, error_text: str) -> None:
        with self._lock:
            self._last_error[file_hash] = str(error_text or "").strip()

    def _finish(self, file_hash: str) -> None:
        with self._lock:
            self._inflight.discard(file_hash)

    def _run_warmup(self, file_hash: str, reason: str = "") -> None:
        del reason  # reserved for future diagnostics hooks
        try:
            stats = {}
            try:
                stats = self.retrieval.stats(file_hash)
            except Exception:
                stats = {}
            if int(stats.get("unit_count") or 0) > 0:
                self._mark_ready(file_hash)
                return

            result = self.ingest.ingest(file_hash, persist=True)
            if int(result.get("knowledge_unit_count") or 0) > 0:
                self._mark_ready(file_hash)
                return

            self._mark_error(file_hash, "warmup_completed_without_units")
        except Exception as exc:
            self._mark_error(file_hash, f"{type(exc).__name__}: {exc}")
        finally:
            self._finish(file_hash)
