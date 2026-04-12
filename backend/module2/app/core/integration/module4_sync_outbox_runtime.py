from __future__ import annotations

import asyncio
import hashlib
import json
import urllib.error
import urllib.request
import warnings
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple


HeadersFactory = Callable[[str], Dict[str, str]]
RetryableStatusFn = Callable[[int], bool]
DelayFactory = Callable[[int], float]
UtcNowFactory = Callable[[], datetime]
DefaultTenantFactory = Callable[[], str]
TransportFn = Callable[[str, Dict[str, str], bytes, float], Awaitable[Tuple[int, str]]]
ScheduleOutboxFn = Callable[[str], None]


class Module4SyncHttpError(RuntimeError):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = int(status_code or 0)
        self.detail = str(detail or "")
        super().__init__(f"HTTP {self.status_code}: {self.detail[:300]}")


class Module4SyncOutboxRuntime:
    """Handle module4 sync outbox delivery, retry orchestration, and row serialization."""

    def __init__(
        self,
        *,
        logger: Any,
        outbox_repository: Any | None = None,
        legacy_storage: Any | None = None,
        metrics_runtime: Any,
        base_url_factory: Callable[[], str],
        headers_factory: HeadersFactory,
        timeout_factory: Callable[[], float],
        retries_factory: Callable[[], int],
        retryable_status: RetryableStatusFn,
        delay_factory: DelayFactory,
        utcnow_factory: UtcNowFactory,
        default_tenant_factory: DefaultTenantFactory,
        transport: TransportFn | None = None,
        sleep_fn: Callable[[float], Awaitable[None]] | None = None,
        **legacy_kwargs: Any,
    ) -> None:
        if "storage" in legacy_kwargs:
            if legacy_storage is not None:
                raise TypeError("Pass only one of legacy_storage=... or storage=...")
            legacy_storage = legacy_kwargs.pop("storage")
        if legacy_kwargs:
            unexpected = ", ".join(sorted(legacy_kwargs))
            raise TypeError(f"Unexpected keyword argument(s): {unexpected}")
        if outbox_repository is None and legacy_storage is not None:
            warnings.warn(
                "Module4SyncOutboxRuntime(storage=...) is deprecated; "
                "pass outbox_repository=... instead.",
                DeprecationWarning,
                stacklevel=2,
            )
        resolved_outbox_repository = outbox_repository or legacy_storage
        if resolved_outbox_repository is None:
            raise ValueError("outbox_repository or legacy_storage is required")
        self._logger = logger
        self._outbox_repository = resolved_outbox_repository
        self._metrics_runtime = metrics_runtime
        self._base_url_factory = base_url_factory
        self._headers_factory = headers_factory
        self._timeout_factory = timeout_factory
        self._retries_factory = retries_factory
        self._retryable_status = retryable_status
        self._delay_factory = delay_factory
        self._utcnow_factory = utcnow_factory
        self._default_tenant_factory = default_tenant_factory
        self._transport = transport or self._default_transport
        self._sleep = sleep_fn or asyncio.sleep

    async def _default_transport(
        self,
        url: str,
        headers: Dict[str, str],
        data: bytes,
        timeout_sec: float,
    ) -> Tuple[int, str]:
        def _post() -> Tuple[int, str]:
            req = urllib.request.Request(url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                    return int(getattr(resp, "status", 200) or 200), body
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
                return int(getattr(exc, "code", 0) or 0), body

        return await asyncio.to_thread(_post)

    @staticmethod
    def outbox_payload(row: Dict[str, Any]) -> Dict[str, Any]:
        payload = row.get("payload_json")
        if isinstance(payload, dict):
            return dict(payload)
        if isinstance(payload, str):
            try:
                loaded = json.loads(payload)
                return dict(loaded) if isinstance(loaded, dict) else {}
            except Exception:
                return {}
        return {}

    @staticmethod
    def normalize_documents(documents: List[Any], *, payload_mode: str = "hybrid") -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        for item in documents or []:
            if hasattr(item, "model_dump"):
                raw = item.model_dump(mode="json")
            elif isinstance(item, dict):
                raw = dict(item)
            else:
                continue
            if isinstance(raw, dict):
                normalized.append(
                    Module4SyncOutboxRuntime._normalize_document_payload(
                        raw,
                        payload_mode=payload_mode,
                    )
                )
        return normalized

    @staticmethod
    def _normalize_document_payload(doc: Dict[str, Any], *, payload_mode: str = "hybrid") -> Dict[str, Any]:
        normalized = dict(doc or {})
        normalized["text_corpus"] = Module4SyncOutboxRuntime._build_text_corpus(normalized)
        normalized["source_texts"] = Module4SyncOutboxRuntime._build_source_texts(normalized)
        if not isinstance(normalized.get("settings_overrides"), dict):
            normalized["settings_overrides"] = {}
        mode = str(payload_mode or "hybrid").strip().lower() or "hybrid"
        if mode == "text_corpus_only":
            normalized = Module4SyncOutboxRuntime._to_text_corpus_payload(normalized)
        return normalized

    @staticmethod
    def _to_text_corpus_payload(doc: Dict[str, Any]) -> Dict[str, Any]:
        diagnostics = doc.get("diagnostics") if isinstance(doc.get("diagnostics"), dict) else {}
        metadata = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        return {
            "file_name": str(doc.get("file_name") or metadata.get("file_name") or "").strip() or "document.md",
            "file_hash": str(doc.get("file_hash") or "").strip(),
            "track": str(doc.get("track") or metadata.get("track") or "").strip(),
            "cached": bool(doc.get("cached", False)),
            "text_corpus": str(doc.get("text_corpus") or "").strip(),
            "source_texts": list(doc.get("source_texts") or []),
            "settings_overrides": dict(doc.get("settings_overrides") or {}),
            "metadata": metadata,
            "diagnostics": diagnostics,
        }

    @staticmethod
    def _build_text_corpus(doc: Dict[str, Any]) -> str:
        if isinstance(doc.get("text_corpus"), str) and str(doc.get("text_corpus") or "").strip():
            return str(doc.get("text_corpus") or "").strip()

        fragments: list[str] = []
        seen: set[str] = set()

        def push(value: Any) -> None:
            text = str(value or "").strip()
            if not text:
                return
            key = text.lower()
            if key in seen:
                return
            seen.add(key)
            fragments.append(text)

        file_name = str(doc.get("file_name") or "").strip()
        if file_name:
            push(f"Document {file_name}")

        for key in ("normalized_text", "text", "content", "markdown", "raw_text"):
            push(doc.get(key))

        result = doc.get("result")
        if isinstance(result, dict):
            for field_name, entity in result.items():
                entity_map = entity if isinstance(entity, dict) else {}
                value = str(entity_map.get("value") or "").strip()
                if value:
                    push(f"{field_name}: {value}")

        trace_hits = doc.get("trace_hits")
        if isinstance(trace_hits, list):
            for item in trace_hits[:120]:
                hit = item if isinstance(item, dict) else {}
                push(hit.get("snippet"))
                locator = hit.get("locator")
                if isinstance(locator, dict):
                    for key in ("summary", "caption", "title"):
                        push(locator.get(key))
        return "\n".join(fragments)

    @staticmethod
    def _build_source_texts(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
        source_texts: list[dict[str, Any]] = []
        diagnostics = doc.get("diagnostics") if isinstance(doc.get("diagnostics"), dict) else {}

        assistant1_md = str(
            diagnostics.get("assistant1_source_markdown_artifact_path")
            or diagnostics.get("markdown_artifact_path")
            or ""
        ).strip()
        if assistant1_md:
            source_texts.append(
                {
                    "kind": "assistant1_markdown",
                    "artifact_path": assistant1_md,
                    "quality_weight": 1.0,
                }
            )

        assistant_payload = str(diagnostics.get("assistant_payload_artifact_path") or "").strip()
        if assistant_payload:
            source_texts.append(
                {
                    "kind": "assistant_payload",
                    "artifact_path": assistant_payload,
                    "quality_weight": 0.85,
                }
            )

        text_corpus = str(doc.get("text_corpus") or "").strip()
        if text_corpus:
            source_texts.append(
                {
                    "kind": "text_corpus",
                    "text": text_corpus,
                    "quality_weight": 0.95,
                }
            )

        for key, weight in (
            ("normalized_text", 0.9),
            ("text", 0.88),
            ("markdown", 0.9),
            ("raw_text", 0.8),
            ("content", 0.8),
        ):
            value = str(doc.get(key) or "").strip()
            if value:
                source_texts.append({"kind": key, "text": value, "quality_weight": weight})
        return source_texts

    @classmethod
    def source_batch_key(
        cls,
        *,
        source: str,
        tenant_id: str,
        documents: List[Any],
        seed: str,
        payload_mode: str = "hybrid",
    ) -> str:
        payload = {
            "source": source,
            "tenant_id": tenant_id,
            "seed": seed,
            "payload_mode": str(payload_mode or "hybrid").strip().lower() or "hybrid",
            "documents": cls.normalize_documents(documents, payload_mode=payload_mode),
        }
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        return digest[:32]

    async def enqueue_document_sync(
        self,
        *,
        source: str,
        tenant_id: str,
        documents: List[Any],
        source_batch_key: str,
        payload_mode: str = "hybrid",
        schedule_outbox: ScheduleOutboxFn,
    ) -> Optional[Dict[str, Any]]:
        normalized_docs = self.normalize_documents(documents, payload_mode=payload_mode)
        if not normalized_docs:
            return None

        single_file_hash = ""
        if len(normalized_docs) == 1 and isinstance(normalized_docs[0], dict):
            single_file_hash = str(normalized_docs[0].get("file_hash") or "").strip()

        row = await self._outbox_repository.upsert_graph_sync_outbox(
            tenant_id=tenant_id,
            source=source,
            source_batch_key=source_batch_key,
            endpoint="/module4/ingest",
            payload={
                "tenant_id": tenant_id,
                "source": source,
                "source_batch_key": source_batch_key,
                "documents": normalized_docs,
            },
            sync_kind="document_batch",
            file_hash=single_file_hash or None,
            max_attempts=self._retries_factory() + 1,
        )
        if row:
            schedule_outbox(str(row.get("outbox_id") or ""))
        return dict(row) if isinstance(row, dict) else row

    async def recover_pending_outbox(
        self,
        *,
        schedule_outbox: ScheduleOutboxFn,
        limit: int = 200,
    ) -> int:
        rows = await self._outbox_repository.recover_pending_graph_sync_outbox(limit=limit)
        scheduled = 0
        for row in rows:
            outbox_id = str(row.get("outbox_id") or "").strip()
            if not outbox_id:
                continue
            schedule_outbox(outbox_id)
            scheduled += 1
        return scheduled

    async def post_sync_once(self, *, endpoint: str, tenant_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self._base_url_factory()}{endpoint}"
        headers = self._headers_factory(tenant_id)
        timeout_sec = self._timeout_factory()
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        status, body = await self._transport(url, headers, data, timeout_sec)
        if status >= 400:
            raise Module4SyncHttpError(status, body)
        try:
            loaded = json.loads(body)
            return dict(loaded) if isinstance(loaded, dict) else {}
        except Exception:
            return {}

    async def deliver_outbox(self, outbox_id: str) -> None:
        key = str(outbox_id or "").strip()
        if not key:
            return

        while True:
            row = await self._outbox_repository.get_graph_sync_outbox(key)
            if not row:
                return
            if str(row.get("status") or "") == "delivered":
                return

            next_attempt_at = row.get("next_attempt_at")
            if isinstance(next_attempt_at, datetime):
                delay_sec = (next_attempt_at - self._utcnow_factory()).total_seconds()
                if delay_sec > 0:
                    await self._sleep(min(delay_sec, 30.0))
                    continue

            claimed = await self._outbox_repository.claim_graph_sync_outbox(key)
            if not claimed:
                return

            endpoint = str(claimed.get("endpoint") or "").strip()
            tenant_id = str(
                claimed.get("tenant_id") or self._default_tenant_factory()
            ).strip() or self._default_tenant_factory()
            source_value = str(claimed.get("source") or "module2").strip() or "module2"
            source_batch_key = str(claimed.get("source_batch_key") or "").strip()
            file_hash = str(claimed.get("file_hash") or "").strip()
            payload = self.outbox_payload(claimed)
            attempt_count = max(1, int(claimed.get("attempt_count") or 1))
            max_attempts = max(1, int(claimed.get("max_attempts") or (self._retries_factory() + 1)))

            self._metrics_runtime.mark_attempt()

            try:
                response_payload = await self.post_sync_once(
                    endpoint=endpoint,
                    tenant_id=tenant_id,
                    payload=payload,
                )
                await self._outbox_repository.mark_graph_sync_outbox_delivered(
                    outbox_id=key,
                    response_payload=response_payload,
                )
                self._metrics_runtime.mark_success(
                    response_payload=response_payload,
                    endpoint=endpoint,
                    source_batch_key=source_batch_key,
                )
                self._logger.info(
                    "module2 delivered module4 sync outbox=%s source=%s file=%s batch=%s attempt=%s/%s endpoint=%s",
                    key,
                    source_value,
                    file_hash or "n/a",
                    source_batch_key,
                    attempt_count,
                    max_attempts,
                    endpoint,
                )
                return
            except Module4SyncHttpError as exc:
                retryable = self._retryable_status(exc.status_code)
                message = f"HTTPError {exc.status_code}: {exc.detail[:400]}"
            except Exception as exc:
                retryable = True
                message = f"{type(exc).__name__}: {exc}"

            if attempt_count < max_attempts and retryable:
                delay = self._delay_factory(attempt_count)
                await self._outbox_repository.requeue_graph_sync_outbox(
                    outbox_id=key,
                    error_message=message,
                    next_attempt_at=self._utcnow_factory() + timedelta(seconds=delay),
                )
                self._logger.warning(
                    "module2 -> module4 outbox retry scheduled in %.1fs outbox=%s file=%s batch=%s attempt=%s/%s: %s",
                    delay,
                    key,
                    file_hash or "n/a",
                    source_batch_key,
                    attempt_count,
                    max_attempts,
                    message,
                )
                await self._sleep(delay)
                continue

            await self._outbox_repository.mark_graph_sync_outbox_failed(outbox_id=key, error_message=message)
            self._metrics_runtime.mark_failure(
                message=message,
                endpoint=endpoint,
                source_batch_key=source_batch_key,
            )
            self._logger.warning(
                "module2 -> module4 outbox permanently failed outbox=%s file=%s batch=%s attempt=%s/%s: %s",
                key,
                file_hash or "n/a",
                source_batch_key,
                attempt_count,
                max_attempts,
                message,
            )
            return

    @staticmethod
    def sync_payload_summary(payload: Dict[str, Any], *, doc_limit: int = 12) -> Dict[str, Any]:
        data = dict(payload or {})
        documents = data.get("documents") if isinstance(data.get("documents"), list) else []
        doc_summaries: List[Dict[str, Any]] = []
        for item in documents[:doc_limit]:
            doc = dict(item) if isinstance(item, dict) else {}
            result = doc.get("result") if isinstance(doc.get("result"), dict) else {}
            trace_hits = doc.get("trace_hits") if isinstance(doc.get("trace_hits"), list) else []
            errors = doc.get("errors") if isinstance(doc.get("errors"), list) else []
            soft_warnings = doc.get("soft_warnings") if isinstance(doc.get("soft_warnings"), list) else []
            diagnostics = doc.get("diagnostics") if isinstance(doc.get("diagnostics"), dict) else {}
            doc_summaries.append(
                {
                    "file_name": str(doc.get("file_name") or "").strip(),
                    "file_hash": str(doc.get("file_hash") or "").strip(),
                    "track": str(doc.get("track") or "").strip(),
                    "field_count": len(result),
                    "trace_hit_count": len(trace_hits),
                    "error_count": len(errors),
                    "soft_warning_count": len(soft_warnings),
                    "quality_status": str(diagnostics.get("quality_status") or "").strip(),
                    "cached": bool(doc.get("cached", False)),
                }
            )
        return {
            "tenant_id": str(data.get("tenant_id") or "").strip(),
            "source": str(data.get("source") or "").strip(),
            "source_batch_key": str(data.get("source_batch_key") or "").strip(),
            "document_count": len(documents),
            "documents": doc_summaries,
            "documents_truncated": len(documents) > doc_limit,
        }

    @staticmethod
    def sync_response_summary(payload: Any) -> Dict[str, Any]:
        data = dict(payload) if isinstance(payload, dict) else {}
        return {
            "job_id": str(data.get("job_id") or "").strip(),
            "batch_id": str(data.get("batch_id") or "").strip(),
            "status": str(data.get("status") or "").strip(),
        }

    @staticmethod
    def metrics_summary(metrics_snapshot: Dict[str, Any]) -> Dict[str, Any]:
        metrics = dict(metrics_snapshot or {})
        return {
            "attempted_batches": int(metrics.get("attempted_batches", 0) or 0),
            "succeeded_batches": int(metrics.get("succeeded_batches", 0) or 0),
            "failed_batches": int(metrics.get("failed_batches", 0) or 0),
            "last_error": str(metrics.get("last_error", "") or ""),
            "last_job_id": str(metrics.get("last_job_id", "") or ""),
            "last_batch_id": str(metrics.get("last_batch_id", "") or ""),
            "last_endpoint": str(metrics.get("last_endpoint", "") or ""),
            "last_source_batch_key": str(metrics.get("last_source_batch_key", "") or ""),
        }

    @classmethod
    def list_response(
        cls,
        *,
        rows: List[Dict[str, Any]],
        tenant_id: str,
        source: str,
        source_batch_key: str,
        endpoint: str,
        statuses: List[str],
        limit: int,
        include_payload: bool,
        include_future: bool,
        metrics_snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "items": [cls.serialize_outbox_row(row, include_payload=include_payload) for row in rows],
            "count": len(rows),
            "filters": {
                "tenant_id": tenant_id.strip(),
                "source": source.strip(),
                "source_batch_key": source_batch_key.strip(),
                "endpoint": endpoint.strip(),
                "status": list(statuses),
                "limit": int(limit),
                "include_payload": bool(include_payload),
                "include_future": bool(include_future),
            },
            "metrics": cls.metrics_summary(metrics_snapshot),
        }

    @classmethod
    def serialize_outbox_row(cls, row: Dict[str, Any], *, include_payload: bool = False) -> Dict[str, Any]:
        payload = row.get("payload_json")
        payload_data = dict(payload) if isinstance(payload, dict) else {}
        response_payload = row.get("last_response_json")
        response_data = dict(response_payload) if isinstance(response_payload, dict) else {}

        def _ts(value: Any) -> Optional[str]:
            if isinstance(value, datetime):
                return value.isoformat()
            text = str(value or "").strip()
            return text or None

        view = {
            "outbox_id": str(row.get("outbox_id") or "").strip(),
            "tenant_id": str(row.get("tenant_id") or "").strip(),
            "source": str(row.get("source") or "").strip(),
            "source_batch_key": str(row.get("source_batch_key") or "").strip(),
            "endpoint": str(row.get("endpoint") or "").strip(),
            "sync_kind": str(row.get("sync_kind") or "").strip(),
            "file_hash": str(row.get("file_hash") or "").strip(),
            "status": str(row.get("status") or "").strip(),
            "attempt_count": int(row.get("attempt_count") or 0),
            "max_attempts": int(row.get("max_attempts") or 0),
            "last_error": str(row.get("last_error") or "").strip(),
            "next_attempt_at": _ts(row.get("next_attempt_at")),
            "last_attempt_at": _ts(row.get("last_attempt_at")),
            "delivered_at": _ts(row.get("delivered_at")),
            "created_at": _ts(row.get("created_at")),
            "updated_at": _ts(row.get("updated_at")),
            "payload_summary": cls.sync_payload_summary(payload_data),
            "response_summary": cls.sync_response_summary(response_data),
        }
        if include_payload:
            view["payload_json"] = payload_data
            view["last_response_json"] = response_data
        return view
