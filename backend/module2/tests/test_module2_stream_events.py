from __future__ import annotations

import json
import sys
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.streaming import (  # noqa: E402
    ASSISTANT1_STREAM_PROTOCOL,
    Assistant1SSEEmitter,
    join_non_empty,
    sse_event,
)


def test_sse_event_format_ends_with_double_newline() -> None:
    raw = sse_event("status", {"label": "preparing"})
    text = raw.decode("utf-8")
    assert text.endswith("\n\n")


def test_sse_event_format_has_event_and_data_lines() -> None:
    raw = sse_event("status", {"label": "preparing"})
    text = raw.decode("utf-8")
    lines = text.split("\n")
    assert lines[0].startswith("event: status")
    assert lines[1].startswith("data: ")


def test_sse_event_data_is_valid_json() -> None:
    raw = sse_event("assistant.delta", {"text": "hello"})
    text = raw.decode("utf-8")
    data_line = next(line for line in text.split("\n") if line.startswith("data: "))
    payload = json.loads(data_line[len("data: "):])
    assert isinstance(payload, dict)


def test_sse_event_non_ascii_not_escaped() -> None:
    raw = sse_event("status", {"label": "处理中"})
    text = raw.decode("utf-8")
    assert "处理中" in text
    assert "\\u" not in text


def test_sse_event_returns_bytes() -> None:
    assert isinstance(sse_event("heartbeat", {}), bytes)


def test_status_event_has_required_fields() -> None:
    payload = {"label": "retrieving", "detail": "vector search", "code": "retrieving"}
    raw = sse_event("status", payload)
    text = raw.decode("utf-8")
    data_line = next(line for line in text.split("\n") if line.startswith("data: "))
    parsed = json.loads(data_line[len("data: "):])
    assert parsed["label"] == "retrieving"
    assert parsed["detail"] == "vector search"
    assert parsed["code"] == "retrieving"


def test_assistant_done_payload_has_finish_reason() -> None:
    payload = {"finish_reason": "completed", "final_text": "ok"}
    raw = sse_event("assistant.done", payload)
    text = raw.decode("utf-8")
    data_line = next(line for line in text.split("\n") if line.startswith("data: "))
    parsed = json.loads(data_line[len("data: "):])
    assert parsed["finish_reason"] == "completed"


def test_tool_status_payload_fields() -> None:
    payload = {"tool_name": "search_knowledge_base", "status": "done", "latency_ms": 230}
    raw = sse_event("tool.status", payload)
    text = raw.decode("utf-8")
    data_line = next(line for line in text.split("\n") if line.startswith("data: "))
    parsed = json.loads(data_line[len("data: "):])
    assert parsed["tool_name"] == "search_knowledge_base"
    assert parsed["status"] == "done"
    assert parsed["latency_ms"] == 230


def test_evidence_bundle_has_items_array() -> None:
    payload = {"items": [{"title": "p1", "snippet": "text", "page": 1}]}
    raw = sse_event("evidence.bundle", payload)
    text = raw.decode("utf-8")
    data_line = next(line for line in text.split("\n") if line.startswith("data: "))
    parsed = json.loads(data_line[len("data: "):])
    assert isinstance(parsed["items"], list)
    assert len(parsed["items"]) == 1


def test_action_preview_has_required_fields() -> None:
    payload = {
        "action_kind": "sql_write_draft",
        "title": "prepare write",
        "requires_confirmation": True,
        "sql_preview": "INSERT INTO t VALUES (1)",
    }
    raw = sse_event("action.preview", payload)
    text = raw.decode("utf-8")
    data_line = next(line for line in text.split("\n") if line.startswith("data: "))
    parsed = json.loads(data_line[len("data: "):])
    assert parsed["action_kind"] == "sql_write_draft"
    assert parsed["requires_confirmation"] is True
    assert "sql_preview" in parsed


def test_heartbeat_event_type() -> None:
    raw = sse_event("heartbeat", {"ts": 1234567890})
    text = raw.decode("utf-8")
    assert "event: heartbeat" in text


def test_error_event_has_message() -> None:
    payload = {"message": "provider timeout", "error": "TimeoutError"}
    raw = sse_event("error", payload)
    text = raw.decode("utf-8")
    data_line = next(line for line in text.split("\n") if line.startswith("data: "))
    parsed = json.loads(data_line[len("data: "):])
    assert parsed["message"] == "provider timeout"


def test_sse_emitter_done_includes_warnings_and_current_lock() -> None:
    emitter = Assistant1SSEEmitter(session_id="sess_1", run_id="run_1", initial_seq=5)
    raw = emitter.done(
        final_text="ok",
        current_object_lock={
            "lock_type": "table_row",
            "table_id": "xlsx_t1",
            "row_index": 17,
            "source_row_index": 17,
        },
        warnings=["auto_ingest_completed_but_no_units_built"],
        user_visible_warnings=["warning-visible"],
    )
    assert raw is not None
    text = raw.decode("utf-8")
    data_line = next(line for line in text.split("\n") if line.startswith("data: "))
    parsed = json.loads(data_line[len("data: "):])
    assert parsed["seq"] == 6
    assert parsed["payload"]["warnings"] == ["auto_ingest_completed_but_no_units_built"]
    assert parsed["payload"]["user_visible_warnings"] == ["warning-visible"]
    assert parsed["payload"]["current_object_lock"]["lock_type"] == "table_row"
    assert parsed["payload"]["current_object_lock"]["row_index"] == 17


def test_protocol_constant_is_string() -> None:
    assert isinstance(ASSISTANT1_STREAM_PROTOCOL, str)
    assert "assistant1" in ASSISTANT1_STREAM_PROTOCOL


def test_join_non_empty_filters_empty_parts() -> None:
    assert join_non_empty(["first", "", "  ", "third"]) == "first\nthird"


def test_join_non_empty_custom_sep() -> None:
    assert join_non_empty(["a", "b", "c"], sep=" | ") == "a | b | c"


def test_join_non_empty_all_empty_returns_empty() -> None:
    result = join_non_empty(["", "  ", None])  # type: ignore[list-item]
    assert result == ""
