from __future__ import annotations

from typing import Dict, Optional

from .streaming import Assistant1SSEEmitter


_STATUS_LIBRARY: Dict[str, Dict[str, str]] = {
    "preparing": {
        "label": "正在准备上下文",
        "detail": "我先把这轮问题和当前上下文整理一下。",
        "ui_state": "thinking",
        "thinking_label": "Thinking",
        "accent": "blue",
    },
    "planning": {
        "label": "正在理解你的问题",
        "detail": "我先判断这轮更适合直接回答、检索文档、联网补充，还是走数据库工具。",
        "ui_state": "thinking",
        "thinking_label": "Thinking",
        "accent": "violet",
    },
    "retrieving": {
        "label": "正在检索相关内容",
        "detail": "我在当前文档里找和你问题最相关的内容。",
        "ui_state": "thinking",
        "thinking_label": "Thinking",
        "accent": "cyan",
    },
    "web_searching": {
        "label": "正在补充外部资料",
        "detail": "我在补当前文档之外但对回答有帮助的信息。",
        "ui_state": "thinking",
        "thinking_label": "Thinking",
        "accent": "emerald",
    },
    "inspecting_schema": {
        "label": "正在检查数据库结构",
        "detail": "我先确认现有表结构，再继续往下做。",
        "ui_state": "thinking",
        "thinking_label": "Thinking",
        "accent": "amber",
    },
    "drafting_schema": {
        "label": "正在整理表结构草案",
        "detail": "我在把建表思路和字段设计收束成可执行草案。",
        "ui_state": "thinking",
        "thinking_label": "Thinking",
        "accent": "orange",
    },
    "drafting_sql": {
        "label": "正在生成 SQL 草案",
        "detail": "我先把自然语言需求收成一条可读可审的 SQL。",
        "ui_state": "thinking",
        "thinking_label": "Thinking",
        "accent": "fuchsia",
    },
    "executing_sql": {
        "label": "正在校验 SQL",
        "detail": "我会先过审计和安全校验，再决定是否真正执行。",
        "ui_state": "thinking",
        "thinking_label": "Thinking",
        "accent": "rose",
    },
    "answering": {
        "label": "正在组织回答",
        "detail": "我会把已经确认的内容直接流式输出给你。",
        "ui_state": "answering",
        "thinking_label": "Answering",
        "accent": "blue",
    },
    "finalizing": {
        "label": "正在收尾",
        "detail": "我再把这轮结果对齐一下，确保主回答更顺畅。",
        "ui_state": "finalizing",
        "thinking_label": "Finishing",
        "accent": "slate",
    },
}


_TOOL_PHASES: Dict[str, str] = {
    "search_knowledge_base": "retrieving",
    "search_knowledge_base_grouped": "retrieving",
    "ingest_document": "preparing",
    "web_search_tavily": "web_searching",
    "inspect_database_schema": "inspecting_schema",
    "design_schema_draft": "drafting_schema",
    "draft_sql_from_nl": "drafting_sql",
    "execute_sql_with_audit": "executing_sql",
}


def status_metadata(code: str) -> Dict[str, str]:
    normalized = str(code or "").strip() or "planning"
    item = _STATUS_LIBRARY.get(normalized, _STATUS_LIBRARY["planning"])
    return {"code": normalized, **item}


def emit_status(
    emitter: Assistant1SSEEmitter,
    code: str,
    *,
    phase: str = "",
    blocking: bool = False,
) -> Optional[bytes]:
    item = status_metadata(code)
    return emitter.status(
        item["code"],
        item["label"],
        item["detail"],
        phase=phase or item["code"],
        blocking=blocking,
        ui_state=item.get("ui_state", "thinking"),
        thinking_label=item.get("thinking_label", "Thinking"),
        accent=item.get("accent", "blue"),
    )


def emit_tool_status(emitter: Assistant1SSEEmitter, tool_name: str) -> Optional[bytes]:
    mapped_code = _TOOL_PHASES.get(str(tool_name or "").strip())
    if not mapped_code:
        return None
    return emit_status(emitter, mapped_code)
