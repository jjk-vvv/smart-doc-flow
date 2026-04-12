from __future__ import annotations

import argparse
import http.cookiejar
import json
import time
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_OUTPUT_PATH = REPO_ROOT / "backend" / "module2" / "tools" / "assistant_question_bank_eval_latest.json"


DEFAULT_EXTRA_CONTEXT: dict[str, Any] = {
    "current_document": {
        "file_name": "2021年民政事业发展统计公报.docx",
        "file_hash": "abc123",
        "summary": "该文档概述了 2021 年民政事业发展总体情况，并给出机构设施、老年人口、基金会等统计数据。",
        "top_fields": [
            {"label": "统计年份", "value": "2021", "confidence": 98, "page": 1},
            {"label": "基金会总数", "value": "8877", "confidence": 98, "page": 12},
            {"label": "民政服务床位总数", "value": "530.5", "confidence": 99, "page": 4},
        ],
        "table_column_headers": ["指标", "数量", "同比增长"],
        "figure_key_points": ["基金会数量保持增长", "床位资源持续扩充"],
    }
}


QUESTION_BANK: list[dict[str, Any]] = [
    {
        "id": "H1",
        "priority": "high",
        "question": "当前文档的统计年份是什么？只回答数字。",
        "intent": "快速拿字段值",
        "expected_shape": "仅返回 2021",
    },
    {
        "id": "H2",
        "priority": "high",
        "question": "请用中文概括当前选中文档的核心内容，并列出你当前最确定的 3 个字段。",
        "intent": "先建全局理解，再抓关键字段",
        "expected_shape": "先总结文档主题，再列出统计年份、基金会总数、民政服务床位总数",
    },
    {
        "id": "H3",
        "priority": "high",
        "question": "这个数值是多少？",
        "intent": "模糊提问，期待助手引导澄清",
        "expected_shape": "不能乱猜，应该进入 clarification_required / requires_followup",
    },
    {
        "id": "H4",
        "priority": "high",
        "question": "如果我是第一次核对这份文档，最应该先核对哪 3 类信息？",
        "intent": "文档质检建议",
        "expected_shape": "建议先看统计年份、核心总量字段、同比或变化口径",
    },
    {
        "id": "E1",
        "priority": "extended",
        "question": "如果我只能保留两个最稳妥的字段做首页卡片，你建议保留哪两个？",
        "intent": "为首页卡片挑最稳的字段",
        "expected_shape": "优先建议统计年份 + 基金会总数，或统计年份 + 民政服务床位总数",
    },
    {
        "id": "E2",
        "priority": "extended",
        "question": "这份文档能直接告诉我 2022 年的基金会总数吗？",
        "intent": "测试边界意识与拒绝幻觉",
        "expected_shape": "应明确说当前文档无法直接给出 2022 年数据",
    },
    {
        "id": "T1",
        "priority": "extended",
        "question": "基金会总数这个数字来自文档里的哪一类信息？",
        "intent": "要求说明证据来源",
        "expected_shape": "回答应指向当前文档已抽取字段/统计指标项，而不是空泛说法",
    },
    {
        "id": "M1",
        "priority": "extended",
        "question": "请告诉我这份文档里的第三季度基金会新增数量。",
        "intent": "测试缺失项处理",
        "expected_shape": "如果当前没有证据，应该明确说没有直接依据，不能编数字",
    },
]


def load_extra_context(path: str) -> dict[str, Any]:
    if not path:
        return dict(DEFAULT_EXTRA_CONTEXT)
    raw = Path(path).read_text(encoding="utf-8")
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise TypeError("extra context file must contain a JSON object")
    return parsed


def build_http_opener() -> urllib.request.OpenerDirector:
    cookie_jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))


def login_if_requested(
    *,
    opener: urllib.request.OpenerDirector,
    base_url: str,
    account: str,
    password: str,
    timeout_sec: float,
) -> dict[str, Any] | None:
    normalized_account = str(account or "").strip()
    normalized_password = str(password or "").strip()
    if not normalized_account or not normalized_password:
        return None

    login_url = f"{base_url.rstrip('/')}/api/login"
    payload = {
        "account": normalized_account,
        "password": normalized_password,
    }
    request = urllib.request.Request(
        login_url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    with opener.open(request, timeout=timeout_sec) as response:
        raw = response.read().decode("utf-8", errors="ignore")
    parsed = json.loads(raw or "{}")
    if not isinstance(parsed, dict):
        raise TypeError("login response must be a JSON object")
    return parsed


def stream_question(
    *,
    opener: urllib.request.OpenerDirector,
    base_url: str,
    session_id: str,
    question: str,
    extra_context: dict[str, Any],
    timeout_sec: float,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}/extract/assistant1/chat/stream"
    payload = {
        "message": question,
        "session_id": session_id,
        "file_hash": str(
            (
                extra_context.get("current_document", {})
                if isinstance(extra_context.get("current_document"), dict)
                else {}
            ).get("file_hash")
            or ""
        ),
        "extra_context": extra_context,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        },
        method="POST",
    )

    started_at = time.perf_counter()
    first_delta_at: float | None = None
    first_delta_text = ""
    warnings: list[str] = []
    statuses: list[dict[str, Any]] = []
    done_payload: dict[str, Any] | None = None
    event_types: list[str] = []
    error_payload: dict[str, Any] | None = None

    try:
        with opener.open(request, timeout=timeout_sec) as response:
            for raw in response:
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])
                event_type = str(event.get("type") or "").strip()
                payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
                event_types.append(event_type)

                if event_type == "status":
                    statuses.append(
                        {
                            "t": round(time.perf_counter() - started_at, 2),
                            "code": payload.get("code"),
                            "label": payload.get("label"),
                            "detail": payload.get("detail"),
                        }
                    )
                elif event_type == "warning":
                    warnings.append(str(payload.get("message") or "").strip())
                elif event_type == "assistant.delta" and first_delta_at is None:
                    first_delta_at = time.perf_counter() - started_at
                    first_delta_text = str(payload.get("text") or "")
                elif event_type == "assistant.done":
                    done_payload = dict(payload)
                    break
    except Exception as exc:
        error_payload = {
            "type": type(exc).__name__,
            "message": str(exc),
        }

    return {
        "first_delta_sec": round(first_delta_at, 2) if first_delta_at is not None else None,
        "first_delta_text": first_delta_text,
        "warnings": warnings,
        "statuses": statuses,
        "done": done_payload or {},
        "event_types": event_types,
        "error": error_payload,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Module2 assistant with the user-oriented question bank.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Assistant API base URL. Default: {DEFAULT_BASE_URL}")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH), help="Path to save JSON results.")
    parser.add_argument(
        "--session-prefix",
        default="",
        help="Session id prefix for this run. Defaults to a timestamped prefix to avoid cross-run history coupling.",
    )
    parser.add_argument("--context-file", default="", help="Optional JSON file path for extra_context.")
    parser.add_argument("--timeout-sec", type=float, default=90.0, help="Per-question timeout in seconds.")
    parser.add_argument("--login-account", default="", help="Optional auth account for protected gateway testing.")
    parser.add_argument("--login-password", default="", help="Optional auth password for protected gateway testing.")
    parser.add_argument(
        "--high-priority-only",
        action="store_true",
        help="Only run the high-priority question set.",
    )
    args = parser.parse_args()

    extra_context = load_extra_context(args.context_file)
    opener = build_http_opener()
    normalized_login_account = str(args.login_account or "").strip()
    normalized_login_password = str(args.login_password or "").strip()
    normalized_session_prefix = str(args.session_prefix or "").strip() or f"assistant-question-bank-{int(time.time())}"
    login_result: dict[str, Any] | None = None
    if normalized_login_account and normalized_login_password:
        login_result = login_if_requested(
            opener=opener,
            base_url=args.base_url,
            account=normalized_login_account,
            password=normalized_login_password,
            timeout_sec=max(5.0, float(args.timeout_sec)),
        )
        print(
            json.dumps(
                {
                    "auth": "login_ok",
                    "account": normalized_login_account,
                    "user": (login_result or {}).get("user"),
                },
                ensure_ascii=False,
            )
        )
    selected_questions = [
        item for item in QUESTION_BANK if (item["priority"] == "high" or not args.high_priority_only)
    ]

    results: list[dict[str, Any]] = []
    had_errors = False
    for index, item in enumerate(selected_questions, start=1):
        session_id = f"{normalized_session_prefix}-{item['id'].lower()}-{index}"
        result = stream_question(
            opener=opener,
            base_url=args.base_url,
            session_id=session_id,
            question=str(item["question"]),
            extra_context=extra_context,
            timeout_sec=max(5.0, float(args.timeout_sec)),
        )
        if isinstance(result.get("error"), dict):
            had_errors = True
        results.append(
            {
                "id": item["id"],
                "priority": item["priority"],
                "question": item["question"],
                "intent": item["intent"],
                "expected_shape": item["expected_shape"],
                "result": result,
            }
        )
        print(
            json.dumps(
                {
                    "id": item["id"],
                    "question": item["question"],
                    "first_delta_sec": result["first_delta_sec"],
                    "finish_reason": result["done"].get("finish_reason"),
                    "requires_followup": result["done"].get("requires_followup"),
                    "error": result.get("error"),
                },
                ensure_ascii=False,
            )
        )

    output_payload = {
        "base_url": args.base_url,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "session_prefix": normalized_session_prefix,
        "authenticated": bool(login_result),
        "login_account": normalized_login_account,
        "question_count": len(results),
        "results": results,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved results to {output_path}")
    return 1 if had_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
