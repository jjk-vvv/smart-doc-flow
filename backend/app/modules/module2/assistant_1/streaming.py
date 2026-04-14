from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


ASSISTANT1_STREAM_PROTOCOL = "assistant1.sse.v1"


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def sse_event(event: str, data: Any) -> bytes:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {str(event or 'message').strip()}\ndata: {payload}\n\n".encode("utf-8")


def join_non_empty(parts: Iterable[str], sep: str = "\n") -> str:
    return sep.join([str(part).strip() for part in parts if str(part or "").strip()]).strip()


@dataclass
class Assistant1TextBuffer:
    flush_chars: int = 36
    flush_timeout_ms: int = 120
    text: str = ""
    last_append_monotonic: float = 0.0

    def append(self, value: str, now_monotonic: float) -> None:
        text = str(value or "")
        if not text:
            return
        self.text += text
        self.last_append_monotonic = float(now_monotonic)

    def should_flush(self, now_monotonic: float, *, force: bool = False) -> bool:
        if force:
            return bool(self.text)
        stripped = self.text.strip()
        if not stripped:
            return False
        if len(stripped) >= max(8, int(self.flush_chars or 36)):
            return True
        if stripped.endswith(("。", "！", "？", "；", "：", "\n", ".", "!", "?", ";", ":")):
            return True
        timeout_ms = max(40, int(self.flush_timeout_ms or 120))
        return (float(now_monotonic) - float(self.last_append_monotonic or 0.0)) * 1000 >= timeout_ms

    def pop(self) -> str:
        text = self.text
        self.text = ""
        return text


class Assistant1SSEEmitter:
    def __init__(
        self,
        *,
        session_id: str = "",
        run_id: str = "",
        turn_id: str = "",
        assistant_message_id: str = "",
        initial_seq: int = 0,
        debug: bool = False,
    ) -> None:
        self.session_id = str(session_id or "").strip() or _new_id("sess")
        self.run_id = str(run_id or "").strip() or _new_id("run")
        self.turn_id = str(turn_id or "").strip() or _new_id("turn")
        self.assistant_message_id = str(assistant_message_id or "").strip() or _new_id("msg")
        self.debug = bool(debug)
        self._seq = max(0, int(initial_seq or 0))

    def event(
        self,
        event_type: str,
        payload: Dict[str, Any],
        *,
        phase: str = "",
        visibility: str = "user",
    ) -> Optional[bytes]:
        normalized_visibility = str(visibility or "user").strip().lower() or "user"
        if normalized_visibility == "debug" and not self.debug:
            return None
        self._seq += 1
        envelope = {
            "version": ASSISTANT1_STREAM_PROTOCOL,
            "type": str(event_type or "message").strip() or "message",
            "seq": self._seq,
            "run_id": self.run_id,
            "turn_id": self.turn_id,
            "ts": _now_iso(),
            "visibility": normalized_visibility,
            "phase": str(phase or "").strip(),
            "payload": payload if isinstance(payload, dict) else {"value": payload},
        }
        return sse_event(envelope["type"], envelope)

    def stream_open(self) -> Optional[bytes]:
        return self.event(
            "stream.open",
            {
                "protocol": ASSISTANT1_STREAM_PROTOCOL,
                "session_id": self.session_id,
                "assistant_message_id": self.assistant_message_id,
            },
            phase="init",
        )

    def assistant_start(self) -> Optional[bytes]:
        return self.event(
            "assistant.start",
            {
                "session_id": self.session_id,
                "assistant_message_id": self.assistant_message_id,
            },
            phase="init",
        )

    def status(
        self,
        code: str,
        label: str,
        detail: str = "",
        *,
        phase: str = "",
        blocking: bool = False,
        ui_state: str = "thinking",
        thinking_label: str = "Thinking",
        accent: str = "blue",
    ) -> Optional[bytes]:
        return self.event(
            "status",
            {
                "code": str(code or "").strip(),
                "label": str(label or "").strip(),
                "detail": str(detail or "").strip(),
                "blocking": bool(blocking),
                "ui_state": str(ui_state or "thinking").strip(),
                "thinking_label": str(thinking_label or "Thinking").strip(),
                "accent": str(accent or "blue").strip(),
            },
            phase=phase or code,
        )

    def delta(self, text: str, *, phase: str = "answering") -> Optional[bytes]:
        return self.event(
            "assistant.delta",
            {"text": str(text or "")},
            phase=phase,
        )

    def replace(self, text: str, *, reason: str = "stream_repair", phase: str = "finalizing") -> Optional[bytes]:
        return self.event(
            "assistant.replace",
            {
                "text": str(text or ""),
                "reason": str(reason or "stream_repair").strip(),
            },
            phase=phase,
        )

    def evidence_bundle(self, items: List[Dict[str, Any]], *, phase: str = "retrieving") -> Optional[bytes]:
        return self.event(
            "evidence.bundle",
            {
                "render_hint": "side_panel_only",
                "items": items if isinstance(items, list) else [],
            },
            phase=phase,
        )

    def action_preview(self, payload: Dict[str, Any], *, phase: str = "awaiting_confirmation") -> Optional[bytes]:
        return self.event("action.preview", payload, phase=phase)

    def warning(self, code: str, message: str, *, recoverable: bool = True, phase: str = "warning") -> Optional[bytes]:
        return self.event(
            "warning",
            {
                "code": str(code or "").strip(),
                "message": str(message or "").strip(),
                "recoverable": bool(recoverable),
            },
            phase=phase,
        )

    def tool_status(
        self,
        tool_name: str,
        status: str,
        *,
        summary: str = "",
        latency_ms: int = 0,
        phase: str = "tool",
    ) -> Optional[bytes]:
        return self.event(
            "tool.status",
            {
                "tool_name": str(tool_name or "").strip(),
                "status": str(status or "").strip(),
                "summary": str(summary or "").strip(),
                "latency_ms": max(0, int(latency_ms or 0)),
            },
            phase=phase,
            visibility="debug",
        )

    def heartbeat(self, idle_ms: int, *, phase: str = "heartbeat") -> Optional[bytes]:
        return self.event(
            "heartbeat",
            {"idle_ms": max(0, int(idle_ms or 0))},
            phase=phase,
            visibility="debug",
        )

    def done(
        self,
        *,
        final_text: str,
        finish_reason: str = "completed",
        requires_followup: bool = False,
        action_preview: Optional[Dict[str, Any]] = None,
        current_object_lock: Optional[Dict[str, Any]] = None,
        warnings: Optional[List[str]] = None,
        user_visible_warnings: Optional[List[str]] = None,
        phase: str = "done",
    ) -> Optional[bytes]:
        payload: Dict[str, Any] = {
            "final_text": str(final_text or ""),
            "finish_reason": str(finish_reason or "completed").strip() or "completed",
            "requires_followup": bool(requires_followup),
        }
        if isinstance(action_preview, dict) and action_preview:
            payload["action_preview"] = action_preview
        if isinstance(current_object_lock, dict) and current_object_lock:
            payload["current_object_lock"] = current_object_lock
        if isinstance(warnings, list) and warnings:
            payload["warnings"] = [str(item).strip() for item in warnings if str(item or "").strip()]
        if isinstance(user_visible_warnings, list) and user_visible_warnings:
            payload["user_visible_warnings"] = [
                str(item).strip() for item in user_visible_warnings if str(item or "").strip()
            ]
        return self.event("assistant.done", payload, phase=phase)

    def error(
        self,
        code: str,
        message: str,
        *,
        recoverable: bool = True,
        can_retry: bool = True,
        phase: str = "error",
    ) -> Optional[bytes]:
        return self.event(
            "error",
            {
                "code": str(code or "").strip(),
                "message": str(message or "").strip(),
                "recoverable": bool(recoverable),
                "can_retry": bool(can_retry),
            },
            phase=phase,
        )
