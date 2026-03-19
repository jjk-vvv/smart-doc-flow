from __future__ import annotations

import json
from typing import Any, Dict, List


PROMPT_VERSION = "document-intelligence-assistant-v1.31"


SYSTEM_PROMPT = """You are the Information Extraction Task Assistant.

You help users:
- understand uploaded documents, tables, and images
- extract requested facts from provided context
- discuss general document-processing methods and tradeoffs
- design database schemas and draft SQL when asked

Behavior rules:
- Answer the user's real question directly and naturally.
- Use the provided context, but do not let internal route hints override the user's actual intent.
- If the context is ambiguous or insufficient, say what is missing instead of guessing.
- Do not mention hidden tools, routes, JSON keys, traces, locators, or internal processing details.
- Distinguish clearly between confirmed facts, drafts, previews, and unverified assumptions.
- Do not use fixed openings, fixed closings, or repeated response templates.
- Write like a capable human teammate, not like a workflow engine.
"""


def _history_text(history: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for item in history[-6:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower() or "user"
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        role_label = "User" if role == "user" else "Assistant"
        lines.append(f"{role_label}: {content}")
    return "\n".join(lines) or "(no recent history)"


def build_answer_messages(
    *,
    route: str,
    user_message: str,
    summary_text: str,
    history: List[Dict[str, Any]],
    answer_context: Dict[str, Any],
) -> List[Dict[str, Any]]:
    route_key = str(route or "").strip().lower() or "general"
    context_json = json.dumps(answer_context or {}, ensure_ascii=False, separators=(",", ":"))
    user_prompt = (
        f"User question:\n{str(user_message or '').strip()}\n\n"
        f"Intent hint:\n{route_key} (internal hint only, may be imperfect; prioritize the real question)\n\n"
        f"Document summary:\n{str(summary_text or '').strip() or '(none)'}\n\n"
        f"Recent conversation:\n{_history_text(history)}\n\n"
        f"Available context JSON:\n{context_json}\n\n"
        "Write one user-facing answer only.\n"
        "Use the same language as the user unless there is a strong reason not to.\n"
        "If the question can already be answered, answer it directly.\n"
        "If a small clarification is truly necessary, ask only the minimum clarifying question.\n"
        "Do not expose internal metadata or system behavior.\n"
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
