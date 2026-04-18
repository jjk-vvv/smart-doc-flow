from __future__ import annotations

import json
import logging
import queue
import threading
import time
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any, Iterator

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse

from app.core.assistant_config import AssistantSettings
from app.services.assistant_prompting import (
    CHAT_FALLBACK_TEXT,
    build_system_prompt,
    normalize_messages,
    normalize_platform_context,
    sanitize_text,
)
from app.integrations.assistant_provider import AssistantResponsesProvider

logger = logging.getLogger(__name__)


SMOKE_EXPECTED_TEXT = "\u94fe\u8def\u6b63\u5e38"
SMOKE_USER_TEXT = "\u8bf7\u53ea\u56de\u590d\u56db\u4e2a\u5b57\uff1a\u94fe\u8def\u6b63\u5e38"
ASSISTANT_NO_KEY_TEXT = (
    "\u5f53\u524d\u672a\u914d\u7f6e\u6a21\u578b\u5bc6\u94a5\uff0c\u5df2\u5207\u6362\u4e3a\u5e73\u53f0"
    "\u52a9\u624b\u5140\u5e95\u6a21\u5f0f\u3002\u8bf7\u8054\u7cfb\u7ba1\u7406\u5458\u914d\u7f6e "
    "ASSISTANT1_CHAT_API_KEY\u3002"
)
ASSISTANT_STREAM_ERROR_TEXT = "\u6a21\u578b\u6d41\u5f0f\u8f93\u51fa\u5f02\u5e38\uff0c\u5df2\u5207\u6362\u4e3a\u5140\u5e95\u56de\u590d\u3002"
ASSISTANT_EMPTY_RESPONSE_TEXT = "\u6a21\u578b\u672a\u8fd4\u56de\u6709\u6548\u6587\u672c\uff0c\u5df2\u5207\u6362\u4e3a\u5140\u5e95\u56de\u590d\u3002"
SMOKE_INSTRUCTIONS = (
    "You are a healthcheck assistant. "
    "Reply in Simplified Chinese only. "
    f"Reply with exactly four Chinese characters: {SMOKE_EXPECTED_TEXT}. "
    "Do not add punctuation, markdown, or extra words."
)


class AssistantService:
    def __init__(
        self,
        settings: AssistantSettings | None = None,
        provider: AssistantResponsesProvider | None = None,
    ) -> None:
        self.settings = settings or AssistantSettings.from_env()
        self.provider = provider or AssistantResponsesProvider(self.settings)
        self._smoke_lock = threading.RLock()
        self._smoke_snapshot: dict[str, Any] | None = None
        self._smoke_checked_at_monotonic = 0.0

    def health_payload(self, *, force_smoke: bool = False) -> dict[str, Any]:
        smoke = self._get_smoke_snapshot(force=force_smoke)
        return {
            "ok": True,
            "model": self.settings.chat_model,
            "keyConfigured": self.provider.configured,
            "endpointStyle": self.settings.chat_endpoint_style,
            "provider": self.provider.provider_info(),
            "unicodeSmoke": smoke,
            "now": datetime.now(UTC).isoformat(),
        }

    def stream_chat(self, payload: dict[str, Any]) -> StreamingResponse:
        messages = normalize_messages(payload.get("messages") or [])
        platform_context = normalize_platform_context(payload.get("platformContext"))
        if not messages:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="messages is required.")

        if not self.provider.configured:
            return self._stream_text_response(ASSISTANT_NO_KEY_TEXT, source="fallback_no_key")

        system_prompt = build_system_prompt(platform_context, self.settings.extra_prompt)
        return self._build_streaming_response(
            self._model_event_stream(messages=messages, system_prompt=system_prompt),
            source="model",
        )

    def _get_smoke_snapshot(self, *, force: bool = False) -> dict[str, Any]:
        if not self.settings.smoke_test_enabled:
            return {
                "enabled": False,
                "ok": None,
                "checkedAt": None,
                "expected": SMOKE_EXPECTED_TEXT,
            }

        now_monotonic = time.monotonic()
        with self._smoke_lock:
            cache_is_fresh = (
                not force
                and self._smoke_snapshot is not None
                and (now_monotonic - self._smoke_checked_at_monotonic) < self.settings.smoke_test_ttl_sec
            )
            if cache_is_fresh:
                return dict(self._smoke_snapshot)

            checked_at = datetime.now(UTC).isoformat()
            if not self.provider.configured:
                snapshot = {
                    "enabled": True,
                    "ok": False,
                    "checkedAt": checked_at,
                    "expected": SMOKE_EXPECTED_TEXT,
                    "reply": "",
                    "error": "provider_not_configured",
                }
            else:
                try:
                    reply = self.provider.complete_text(
                        messages=[{"role": "user", "content": SMOKE_USER_TEXT}],
                        instructions=SMOKE_INSTRUCTIONS,
                        max_output_tokens=64,
                        reasoning_effort="minimal",
                        text_verbosity="low",
                    )
                    snapshot = {
                        "enabled": True,
                        "ok": self._is_smoke_success(reply),
                        "checkedAt": checked_at,
                        "expected": SMOKE_EXPECTED_TEXT,
                        "reply": sanitize_text(reply)[:120],
                        "error": "",
                    }
                except Exception as exc:
                    snapshot = {
                        "enabled": True,
                        "ok": False,
                        "checkedAt": checked_at,
                        "expected": SMOKE_EXPECTED_TEXT,
                        "reply": "",
                        "error": str(exc).strip()[:240],
                    }

            self._smoke_snapshot = snapshot
            self._smoke_checked_at_monotonic = now_monotonic
            return dict(snapshot)

    @staticmethod
    def _is_smoke_success(reply: str) -> bool:
        normalized = (
            sanitize_text(reply)
            .replace(" ", "")
            .replace("\n", "")
            .replace("\t", "")
            .replace("\u3000", "")
            .replace("。", "")
            .replace("，", "")
            .replace(",", "")
            .replace("！", "")
            .replace("!", "")
            .replace("：", "")
            .replace(":", "")
        )
        return normalized == SMOKE_EXPECTED_TEXT

    def _stream_text_response(self, text: str, *, source: str) -> StreamingResponse:
        return self._build_streaming_response(self._text_event_stream(text), source=source)

    def _build_streaming_response(self, stream: Iterator[str], *, source: str) -> StreamingResponse:
        return StreamingResponse(
            stream,
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "X-Vercel-AI-Data-Stream": "v1",
                "X-AI-Reply-Source": source,
            },
        )

    def _text_event_stream(self, text: str) -> Iterator[str]:
        yield ":ka\n\n"
        for frame in self._text_frames(text):
            yield frame
        yield '0:"[DONE]"\n'

    def _model_event_stream(self, *, messages: list[dict[str, str]], system_prompt: str) -> Iterator[str]:
        yield ":ka\n\n"
        emitted_any = False
        pending_whitespace_chunks: list[str] = []
        result_queue: queue.Queue[tuple[str, str]] = queue.Queue()

        def worker() -> None:
            try:
                for chunk in self.provider.stream_text(messages=messages, instructions=system_prompt):
                    result_queue.put(("chunk", chunk))
            except Exception as exc:
                logger.exception("Assistant stream failed: %s", exc)
                result_queue.put(("error", str(exc)))
            finally:
                result_queue.put(("done", ""))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        while True:
            try:
                event, value = result_queue.get(timeout=8.0)
            except queue.Empty:
                if not thread.is_alive():
                    break
                yield ":ka\n\n"
                continue

            if event == "chunk":
                safe_chunk = sanitize_text(value)
                if safe_chunk:
                    if not safe_chunk.strip():
                        if emitted_any:
                            yield self._data_line(safe_chunk)
                        else:
                            pending_whitespace_chunks.append(safe_chunk)
                        continue
                    if pending_whitespace_chunks:
                        for whitespace_chunk in pending_whitespace_chunks:
                            yield self._data_line(whitespace_chunk)
                        pending_whitespace_chunks.clear()
                    emitted_any = True
                    yield self._data_line(safe_chunk)
                continue

            if event == "error":
                emitted_any = True
                yield self._data_line(ASSISTANT_STREAM_ERROR_TEXT)
                for frame in self._text_frames(CHAT_FALLBACK_TEXT):
                    yield frame
                continue

            if event == "done":
                break

        if not emitted_any:
            for frame in self._text_frames(ASSISTANT_EMPTY_RESPONSE_TEXT):
                yield frame
            for frame in self._text_frames(CHAT_FALLBACK_TEXT):
                yield frame

        yield '0:"[DONE]"\n'

    @staticmethod
    def _data_line(text: str) -> str:
        return f"0:{json.dumps(text, ensure_ascii=False)}\n"

    def _text_frames(self, text: str) -> Iterator[str]:
        safe_text = sanitize_text(text)
        if not safe_text:
            return
        for char in safe_text:
            yield self._data_line(char)


@lru_cache(maxsize=1)
def get_assistant_service() -> AssistantService:
    return AssistantService()
