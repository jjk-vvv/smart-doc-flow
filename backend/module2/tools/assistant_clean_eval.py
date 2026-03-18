from __future__ import annotations

import json
import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import fitz
import requests
from requests import Response
from requests.exceptions import ChunkedEncodingError, RequestException


BASE_URL = str(os.getenv("MODULE2_EVAL_BASE_URL", "http://127.0.0.1:8000")).strip() or "http://127.0.0.1:8000"
ROOT = Path(__file__).resolve().parents[3]
OUT_DIR = ROOT / ".runlogs" / "module2-assistant-eval"
OUT_DIR.mkdir(parents=True, exist_ok=True)

REQUEST_TIMEOUT_SEC = 1800


SCENARIOS: Dict[str, Dict[str, Any]] = {
    "excel": {
        "discover": "excel",
        "questions": [
            {
                "question": "请直接查看 xlsx_t1 表格，站点名称为滁州新二中的 PM10 监测值是多少？请写明表格、页码、表内行号、原始行号和 ref_id。",
                "expected": {
                    "goal": "当目标站点不存在或未稳定命中时，应明确进入澄清模式，不用别的行替答。",
                    "route": "clarification_needed",
                    "required_events": ["assistant_start", "assistant_done"],
                    "must_contain": ["不会自动替代"],
                    "should_contain": ["目标行", "补充", "候选记录"],
                    "prohibited_contain": ["当前定位到的值为"],
                },
            },
            {
                "question": "继续，那一行的污染类型是什么？也请保持同样的引用格式。",
                "expected": {
                    "goal": "如果上一轮没有稳定锁定行，本轮也应继续澄清，而不是猜测“那一行”。",
                    "route": "clarification_needed",
                    "required_events": ["assistant_start", "assistant_done"],
                    "must_contain": ["不会自动替代"],
                    "should_contain": ["目标行", "补充", "候选记录"],
                    "prohibited_contain": ["当前定位到的值为"],
                },
            },
            {
                "question": "把刚才那一行里已经识别到的关键字段准备入库，先给我看动作预览，不要直接执行。",
                "expected": {
                    "goal": "识别数据库意图，但只返回动作预览，不直接执行。",
                    "route": "database_action",
                    "required_events": ["assistant_start", "action_preview", "assistant_done"],
                    "must_contain": ["预览", "阻塞"],
                    "should_contain": ["入库", "当前", "确认"],
                    "prohibited_contain": ["已执行", "已经写入数据库"],
                    "expect_action_preview": True,
                    "action_preview": {
                        "present": True,
                        "preview_status": "blocked",
                        "lock_quality_in": ["weak_lock", "no_lock"],
                        "focus_scope_in": ["unresolved_table_row", "context"],
                    },
                },
            },
            {
                "question": "重新判断一下：这份文档现在大致讲了什么？请先单独说明当前锁定对象，再说明全局概览，并区分哪些信息比较稳定、哪些还需要谨慎核对。",
                "expected": {
                    "goal": "验证 current_focus 是否先于全局概览输出。",
                    "route": "document_summary",
                    "required_events": ["assistant_start", "assistant_done"],
                    "must_contain": ["当前", "稳定", "谨慎"],
                    "should_contain": ["概览", "表格"],
                },
            },
            {
                "question": "如果我只说“帮我看看这份表里最值得注意的点”，你会怎么回答？如果证据不够请直接说明。",
                "expected": {
                    "goal": "验证偏泛化问题时是否会收敛回答范围，不胡乱扩写。",
                    "route": "document_summary",
                    "required_events": ["assistant_start", "assistant_done"],
                    "must_contain": ["结论"],
                    "should_contain": ["证据", "不够", "稳定"],
                },
            },
        ],
    },
    "pdf": {
        "discover": "pdf",
        "questions": [
            {
                "question": "请先概述文档中的图表，并列出 figure_id、页码和关键要点。如果关键要点还不稳定也请直接写出来。",
                "expected": {
                    "goal": "确认 PDF 图表场景下能否区分 figure 级与非 figure 级。",
                    "route": "figure_overview",
                    "required_events": ["assistant_start", "assistant_done"],
                    "must_contain": ["figure", "页"],
                    "should_contain": ["关键要点", "识别"],
                },
            },
            {
                "question": "这份文档里的图表能稳定看出什么趋势？如果不能稳定判断，也请直接说明你现在只到了标题级、关键要点级还是 dataframe 级。",
                "expected": {
                    "goal": "验证图表趋势回答是否诚实暴露识别层级。",
                    "route": "figure_value_read",
                    "required_events": ["assistant_start", "assistant_done"],
                    "must_contain": ["级"],
                    "should_contain": ["趋势", "稳定", "dataframe"],
                },
            },
        ],
    },
    "image": {
        "discover": "image",
        "questions": [
            {
                "question": "请概述这张图片中的图表，并列出 figure_id、页码、关键要点，以及是否识别出了 dataframe 或可引用的数值。",
                "expected": {
                    "goal": "确认图片问答里能否稳定说明当前识别层级。",
                    "route": "figure_overview",
                    "required_events": ["assistant_start", "assistant_done"],
                    "must_contain": ["识别", "页"],
                    "should_contain": ["figure", "dataframe", "数值"],
                },
            },
            {
                "question": "这张图最可能在讲什么？如果你现在只能确认 OCR / 表格级或 OCR / 字段级，请直接说明，不要冒充 figure 级结论。",
                "expected": {
                    "goal": "验证图片场景是否会把 OCR 结果误说成 figure 结论。",
                    "route": ["figure_value_read", "figure_overview"],
                    "required_events": ["assistant_start", "assistant_done"],
                    "must_contain": ["OCR"],
                    "should_contain": ["figure", "字段", "表格"],
                },
            },
            {
                "question": "如果现在还没有稳定的图表对象，请直接列出你能稳定确认的字段级事实，写明字段名、值、ref_id 和页码。",
                "expected": {
                    "goal": "确认图片 fallback 到字段级时能给出稳定的溯源格式。",
                    "route": ["figure_value_read", "figure_overview"],
                    "required_events": ["assistant_start", "assistant_done"],
                    "lock_type": ["ocr_fact_group", ""],
                    "must_contain": ["ref_id"],
                    "should_contain": ["页", "字段", "值"],
                },
            },
        ],
    },
}


def _discover_excel() -> Path:
    matches = sorted((ROOT / "datasets" / "Excel").glob("*.xlsx"))
    if not matches:
        raise FileNotFoundError("no xlsx file found under datasets/Excel")
    return matches[0]


def _discover_pdf() -> Path:
    matches = sorted((ROOT / ".runlogs" / "mineru-smoke").rglob("*origin.pdf"))
    if not matches:
        raise FileNotFoundError("no origin.pdf file found under .runlogs/mineru-smoke")
    return matches[0]


def _ensure_image(pdf_path: Path) -> Path:
    image_path = OUT_DIR / "page4_from_pdf.png"
    if image_path.exists():
        return image_path
    doc = fitz.open(pdf_path)
    try:
        page_index = min(3, max(0, doc.page_count - 1))
        page = doc.load_page(page_index)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image_path.write_bytes(pix.tobytes("png"))
    finally:
        doc.close()
    return image_path


def _extract_doc(path: Path) -> Dict[str, Any]:
    schema = {"auto_infer": True, "prefer_llm": True, "max_auto_fields": 8}
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    with path.open("rb") as f:
        files = {"files": (path.name, f, mime)}
        data = {"schema": json.dumps(schema, ensure_ascii=False)}
        response = requests.post(
            f"{BASE_URL}/extract/batch",
            files=files,
            data=data,
            timeout=REQUEST_TIMEOUT_SEC,
        )
    response.raise_for_status()
    payload = response.json()
    return payload["documents"][0]


def _parse_sse(response: Response) -> Iterator[Tuple[str, str]]:
    event_name = "message"
    data_lines: List[str] = []
    try:
        for raw in response.iter_lines(decode_unicode=True):
            if raw is None:
                continue
            line = raw.rstrip("\n")
            if not line:
                yield event_name, "\n".join(data_lines)
                event_name = "message"
                data_lines = []
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip()
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
    except ChunkedEncodingError as exc:
        yield "stream_error", json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
    except RequestException as exc:
        yield "stream_error", json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
    except Exception as exc:
        yield "stream_error", json.dumps({"error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False)
    if data_lines:
        yield event_name, "\n".join(data_lines)


def _parse_event_payload(data_text: str) -> Dict[str, Any]:
    text = str(data_text or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}
    return payload if isinstance(payload, dict) else {"value": payload}


def _compact_citations(citations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in citations[:6]:
        if not isinstance(item, dict):
            continue
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        out.append(
            {
                "citation_type": str(item.get("citation_type") or ""),
                "title": str(item.get("title") or ""),
                "page": item.get("page"),
                "ref_id": item.get("ref_id"),
                "object_id": str(item.get("object_id") or ""),
                "snippet": str(item.get("snippet") or "")[:220],
                "payload": payload,
            }
        )
    return out


def _compact_tool_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in events:
        data = item.get("data") if isinstance(item.get("data"), dict) else {}
        out.append(
            {
                "tool_name": str(data.get("tool_name") or ""),
                "status": str(data.get("status") or ""),
                "message": str(data.get("message") or ""),
                "detail": str(data.get("detail") or ""),
            }
        )
    return out


def _value_matches(actual: Any, expected: Any) -> bool:
    if expected in (None, "", []):
        return True
    actual_text = str(actual or "").strip()
    if isinstance(expected, list):
        return actual_text in {str(item).strip() for item in expected}
    return actual_text == str(expected).strip()


def _run_checks(
    *,
    answer: str,
    expected: Dict[str, Any],
    assistant_done_received: bool,
    stream_error: str,
    route: str,
    current_lock: Optional[Dict[str, Any]],
    action_preview: Optional[Dict[str, Any]],
    event_sequence: List[str],
) -> Dict[str, Any]:
    must_contain = [str(item) for item in expected.get("must_contain", [])]
    should_contain = [str(item) for item in expected.get("should_contain", [])]
    prohibited_contain = [str(item) for item in expected.get("prohibited_contain", [])]
    missing_must = [token for token in must_contain if token not in answer]
    hit_should = [token for token in should_contain if token in answer]
    hit_prohibited = [token for token in prohibited_contain if token in answer]
    expect_action_preview = bool(expected.get("expect_action_preview"))
    action_preview_present = isinstance(action_preview, dict) and bool(action_preview)
    current_lock = current_lock if isinstance(current_lock, dict) else {}
    expected_route = expected.get("route")
    route_match = _value_matches(route, expected_route)
    expected_lock_type = expected.get("lock_type")
    expected_lock_quality = expected.get("lock_quality")
    lock_type_match = _value_matches(current_lock.get("lock_type"), expected_lock_type)
    lock_quality_match = _value_matches(current_lock.get("lock_quality"), expected_lock_quality)
    required_events = [str(item) for item in expected.get("required_events", [])]
    missing_events = [item for item in required_events if item not in event_sequence]
    preview_expect = expected.get("action_preview") if isinstance(expected.get("action_preview"), dict) else {}
    action_preview_payload = action_preview.get("payload") if isinstance(action_preview, dict) and isinstance(action_preview.get("payload"), dict) else {}
    preview_match = True
    if preview_expect:
        preview_match = (
            _value_matches(action_preview_present, preview_expect.get("present"))
            and _value_matches(action_preview_payload.get("preview_status"), preview_expect.get("preview_status") or preview_expect.get("preview_status_in"))
            and _value_matches(action_preview_payload.get("lock_quality"), preview_expect.get("lock_quality") or preview_expect.get("lock_quality_in"))
            and _value_matches(action_preview_payload.get("focus_scope"), preview_expect.get("focus_scope") or preview_expect.get("focus_scope_in"))
        )
    return {
        "assistant_done_received": assistant_done_received,
        "stream_error": stream_error,
        "route": route,
        "expected_route": expected_route if isinstance(expected_route, list) else str(expected_route or ""),
        "route_match": route_match,
        "current_lock_type": str(current_lock.get("lock_type") or ""),
        "current_lock_quality": str(current_lock.get("lock_quality") or ""),
        "lock_type_match": lock_type_match,
        "lock_quality_match": lock_quality_match,
        "missing_must_contain": missing_must,
        "hit_should_contain": hit_should,
        "hit_prohibited_contain": hit_prohibited,
        "expect_action_preview": expect_action_preview,
        "action_preview_present": action_preview_present,
        "preview_match": preview_match,
        "missing_events": missing_events,
        "passed": (
            assistant_done_received
            and not stream_error
            and not missing_must
            and not hit_prohibited
            and route_match
            and lock_type_match
            and lock_quality_match
            and not missing_events
            and preview_match
            and (not expect_action_preview or action_preview_present)
        ),
    }


def _chat(
    document: Dict[str, Any],
    question: str,
    expected: Dict[str, Any],
    *,
    session_id: Optional[str] = None,
    current_lock: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "document": document,
        "summary": "",
        "user_message": question,
        "session_id": session_id,
        "top_k": 16,
    }
    if current_lock:
        payload["current_object_lock"] = current_lock

    started = time.perf_counter()
    response = requests.post(
        f"{BASE_URL}/extract/assistant/chat/stream",
        json=payload,
        stream=True,
        timeout=REQUEST_TIMEOUT_SEC,
    )
    response.raise_for_status()

    raw_events: List[Dict[str, Any]] = []
    tool_events: List[Dict[str, Any]] = []
    answer = ""
    next_session = session_id
    next_lock = current_lock
    citations: List[Dict[str, Any]] = []
    action_preview: Optional[Dict[str, Any]] = None
    warnings: List[str] = []
    route = ""
    assistant_done_received = False
    stream_error = ""
    provider_diagnostics: Dict[str, Any] = {}

    with response:
        for event_name, data_text in _parse_sse(response):
            data = _parse_event_payload(data_text)
            raw_events.append({"event": event_name, "data": data})
            if event_name == "assistant_start":
                next_session = str(data.get("session_id") or next_session or "") or None
            elif event_name == "assistant_delta":
                answer += str(data.get("text") or data.get("delta") or "")
            elif event_name == "citation_bundle":
                next_lock = data.get("current_object_lock") if isinstance(data.get("current_object_lock"), dict) else next_lock
                citations = data.get("citations") if isinstance(data.get("citations"), list) else citations
            elif event_name == "action_preview":
                action_preview = data if isinstance(data, dict) else None
            elif event_name == "tool_status":
                tool_events.append({"event": event_name, "data": data})
            elif event_name == "assistant_done":
                assistant_done_received = True
                answer = str(data.get("answer") or answer)
                route = str(data.get("route") or route)
                warnings = data.get("warnings") if isinstance(data.get("warnings"), list) else warnings
                next_lock = data.get("current_object_lock") if isinstance(data.get("current_object_lock"), dict) else next_lock
                citations = data.get("citations") if isinstance(data.get("citations"), list) else citations
                if isinstance(data.get("action_preview"), dict):
                    action_preview = data["action_preview"]
                provider_diagnostics = (
                    data.get("provider_diagnostics")
                    if isinstance(data.get("provider_diagnostics"), dict)
                    else provider_diagnostics
                )
            elif event_name == "stream_error":
                stream_error = str(data.get("error") or data.get("raw") or "unknown_stream_error")

    duration_ms = int((time.perf_counter() - started) * 1000)
    checks = _run_checks(
        answer=answer,
        expected=expected,
        assistant_done_received=assistant_done_received,
        stream_error=stream_error,
        route=route,
        current_lock=next_lock,
        action_preview=action_preview,
        event_sequence=[item["event"] for item in raw_events],
    )

    return {
        "question": question,
        "expected": expected,
        "duration_ms": duration_ms,
        "session_id": next_session,
        "current_lock": next_lock,
        "route": route,
        "answer": answer,
        "warnings": warnings,
        "assistant_done_received": assistant_done_received,
        "stream_error": stream_error,
        "event_sequence": [item["event"] for item in raw_events],
        "tool_events": _compact_tool_events(tool_events),
        "citations": _compact_citations(citations),
        "action_preview": action_preview,
        "provider_diagnostics": provider_diagnostics,
        "checks": checks,
    }


def _run_rounds(document: Dict[str, Any], questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rounds: List[Dict[str, Any]] = []
    session_id: Optional[str] = None
    current_lock: Optional[Dict[str, Any]] = None
    for item in questions:
        result = _chat(
            document,
            str(item.get("question") or ""),
            item.get("expected") if isinstance(item.get("expected"), dict) else {},
            session_id=session_id,
            current_lock=current_lock,
        )
        session_id = str(result.get("session_id") or "") or None
        current_lock = result.get("current_lock") if isinstance(result.get("current_lock"), dict) else None
        rounds.append(result)
    return rounds


def _scenario_path(kind: str, pdf_path: Optional[Path] = None) -> Path:
    if kind == "excel":
        return _discover_excel()
    if kind == "pdf":
        return _discover_pdf()
    if kind == "image":
        if pdf_path is None:
            pdf_path = _discover_pdf()
        return _ensure_image(pdf_path)
    raise ValueError(f"unknown scenario kind: {kind}")


def main() -> int:
    pdf_path = _discover_pdf()
    scenario_inputs = {
        name: _scenario_path(config["discover"], pdf_path=pdf_path)
        for name, config in SCENARIOS.items()
    }
    extracted_docs = {
        name: _extract_doc(path)
        for name, path in scenario_inputs.items()
    }

    report: Dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "base_url": BASE_URL,
        "scenarios": {},
    }

    for name, config in SCENARIOS.items():
        document = extracted_docs[name]
        diagnostics = document.get("diagnostics", {}) if isinstance(document.get("diagnostics"), dict) else {}
        report["scenarios"][name] = {
            "file": str(scenario_inputs[name].relative_to(ROOT)),
            "diagnostics": {
                "assistant_payload_artifact_path": diagnostics.get("assistant_payload_artifact_path"),
                "assistant_payload_version": diagnostics.get("assistant_payload_version"),
                "table_count": diagnostics.get("table_count"),
                "figure_count": diagnostics.get("figure_count"),
            },
            "rounds": _run_rounds(document, list(config.get("questions") or [])),
        }

    out_path = OUT_DIR / "assistant_clean_eval_latest.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
