from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional
from urllib.parse import unquote

from app.assistant.prompting import PROMPT_VERSION, build_answer_messages
from app.assistant.provider import (
    ChatStreamEvent,
    OpenAICompatibleChatProvider,
    resolve_assistant_api_key,
    resolve_assistant_base_url,
    resolve_assistant_model,
)
from app.assistant.streaming import chunk_text, sse_event
from app.assistant.tools import (
    assess_table_lookup,
    build_action_preview,
    build_action_preview_citations,
    build_document_overview,
    build_field_citations,
    build_field_facts_from_table_overviews,
    build_figure_citations,
    build_ocr_fact_group_lock,
    build_table_overview_citations,
    build_table_overview_context,
    classify_route,
    collect_trace_hits,
    dump_context_for_model,
    enrich_matched_fields_with_trace_hits,
    fallback_answer,
    match_fields,
    merge_structural_payload,
    payload_has_structural_context,
    reconstruct_payload_from_trace_hits,
    select_tables,
    select_figures,
)
from app.db.storage import ExtractionStorage
from app.schemas import (
    AssistantActionPreview,
    AssistantChatStreamRequest,
    AssistantObjectLock,
    AssistantQueryRequest,
    AssistantQueryResponse,
    AssistantSessionMessage,
    AssistantSessionRequest,
    AssistantSessionResponse,
    DocumentExtractionResponse,
)


@dataclass
class TurnArtifacts:
    route: str
    warnings: List[str] = field(default_factory=list)
    matched_fields: List[Dict[str, Any]] = field(default_factory=list)
    matched_trace_hits: List[Dict[str, Any]] = field(default_factory=list)
    citations: List[Dict[str, Any]] = field(default_factory=list)
    current_object_lock: Optional[Dict[str, Any]] = None
    action_preview: Optional[Dict[str, Any]] = None
    answer_context: Dict[str, Any] = field(default_factory=dict)
    fallback_answer: str = ""
    tool_events: List[Dict[str, Any]] = field(default_factory=list)
    prefer_fallback_only: bool = False


class AssistantProviderStreamError(RuntimeError):
    def __init__(self, message: str, *, classification: str, diagnostics: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.classification = str(classification or "provider_error").strip() or "provider_error"
        self.diagnostics = dict(diagnostics or {})


class AssistantService:
    def __init__(self, storage: ExtractionStorage) -> None:
        self._storage = storage
        self._temperature = max(0.0, min(1.0, float(os.getenv("MODULE2_ASSISTANT_TEMPERATURE", "1.0"))))
        self._max_tokens = max(600, int(os.getenv("MODULE2_ASSISTANT_MAX_TOKENS", "3200")))
        self._prompt_version = PROMPT_VERSION
        self._model = resolve_assistant_model(default="gemini-2.5-flash")
        self._base_url = resolve_assistant_base_url()
        self._api_key = resolve_assistant_api_key()
        legacy_first_token_timeout = max(2.0, float(os.getenv("MODULE2_ASSISTANT_FIRST_TOKEN_TIMEOUT_SEC", "12")))
        self._connect_timeout_sec = max(
            2.0,
            float(os.getenv("MODULE2_ASSISTANT_CONNECT_TIMEOUT_SEC", str(legacy_first_token_timeout))),
        )
        self._first_frame_timeout_sec = max(
            2.0,
            float(os.getenv("MODULE2_ASSISTANT_FIRST_FRAME_TIMEOUT_SEC", str(legacy_first_token_timeout))),
        )
        self._first_visible_timeout_sec = max(
            self._first_frame_timeout_sec,
            float(os.getenv("MODULE2_ASSISTANT_FIRST_VISIBLE_TIMEOUT_SEC", str(legacy_first_token_timeout))),
        )
        self._stream_idle_timeout_sec = max(
            self._first_visible_timeout_sec,
            float(os.getenv("MODULE2_ASSISTANT_STREAM_IDLE_TIMEOUT_SEC", "20")),
        )
        self._broad_primary_mode = str(
            os.getenv("MODULE2_ASSISTANT_BROAD_PRIMARY_MODE", "stream") or "stream"
        ).strip().lower()
        self._complete_chunk_size = max(24, int(os.getenv("MODULE2_ASSISTANT_COMPLETE_CHUNK_SIZE", "72")))
        debug_dir_raw = str(os.getenv("MODULE2_ASSISTANT_DEBUG_DIR", ".runlogs/module2-llm-debug") or "").strip()
        self._debug_dir = Path(debug_dir_raw).resolve() if debug_dir_raw else None
        self._stream_debug_always = str(os.getenv("MODULE2_ASSISTANT_STREAM_DEBUG_ALWAYS", "false")).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._provider: Optional[OpenAICompatibleChatProvider] = None
        if self._base_url and self._api_key:
            self._provider = OpenAICompatibleChatProvider(
                base_url=self._base_url,
                api_key=self._api_key,
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                timeout_sec=max(10.0, float(os.getenv("MODULE2_ASSISTANT_TIMEOUT_SEC", "120"))),
            )

    @staticmethod
    def _artifact_root_dirs() -> List[Path]:
        configured = str(os.getenv("MODULE2_ARTIFACT_ROOT_DIR", "backend/module2/artifacts")).strip() or "backend/module2/artifacts"
        module_root = Path(__file__).resolve().parents[2]
        candidates = [
            Path(configured),
            module_root / "artifacts",
            module_root / "backend" / "module2" / "artifacts",
            module_root / ".cache",
            module_root / "backend" / "module2" / ".cache",
        ]
        seen: set[str] = set()
        roots: List[Path] = []
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except Exception:
                continue
            key = str(resolved).lower()
            if key in seen:
                continue
            seen.add(key)
            roots.append(resolved)
        return roots

    @staticmethod
    def _filter_user_visible_warnings(warnings: List[str]) -> List[str]:
        hidden_prefixes = (
            "assistant_provider_fallback:",
            "assistant_context_fallback:",
        )
        visible: List[str] = []
        for item in warnings or []:
            text = str(item or "").strip()
            if not text:
                continue
            if any(text.startswith(prefix) for prefix in hidden_prefixes):
                continue
            visible.append(text)
        return visible

    @staticmethod
    def _looks_like_incomplete_provider_answer(text: str) -> bool:
        answer = str(text or "").strip()
        if not answer:
            return True
        broken_prefixes = (
            "）",
            ")",
            "，",
            "。",
            "；",
            "*",
            "-",
            "•",
        )
        normalized_prefix = answer.lstrip()
        if normalized_prefix.startswith(broken_prefixes):
            return True
        leading_window = normalized_prefix[:120].lower()
        if len(normalized_prefix) >= 48 and not normalized_prefix.endswith(("。", "！", "？", ".", "!", "?")):
            return True
        if "summary/next steps" in leading_window:
            return True
        if normalized_prefix.count("```") == 1:
            return True
        mojibake_markers = ("锛", "銆", "鈥", "璇", "闂", "鏄", "鍦", "鐨", "缁", "鑷")
        mojibake_hits = sum(normalized_prefix.count(marker) for marker in mojibake_markers)
        if mojibake_hits >= 3:
            return True
        return False

    @staticmethod
    def _message_debug_summary(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        summary: List[Dict[str, Any]] = []
        for item in messages or []:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "")
            summary.append(
                {
                    "role": str(item.get("role") or ""),
                    "content_chars": len(content),
                    "content_preview": content[:240],
                }
            )
        return summary

    @staticmethod
    def _provider_error_classification(text: str, *, stream_opened: bool) -> str:
        raw = str(text or "").strip().lower()
        if "http error" in raw or "connection error" in raw or "timed out" in raw or "timeout" in raw:
            return "transport_failure" if stream_opened else "connect_failure"
        if "stream error" in raw:
            return "provider_stream_error"
        return "provider_error" if stream_opened else "connect_failure"

    def _prefer_local_knowledge_answer(self, user_message: str) -> bool:
        text = str(user_message or "").strip()
        lowered = text.lower()
        if "ocr" in lowered and any(token in text for token in ("版面", "布局", "版面分析", "布局分析", "区别")):
            return True
        if any(token in text for token in ("表格恢复", "表格抽取", "表格识别", "单元格", "跨行", "跨列")):
            return True
        if any(token in lowered for token in ("sql", "nl2sql")):
            return True
        if any(token in text for token in ("数据库", "增删改查", "入库", "落库", "审计", "回滚")) and any(
            token in text for token in ("流程", "约束", "风险", "容易出错", "设计思路")
        ):
            return True
        if any(
            token in text
            for token in (
                "扫描文档",
                "扫描件",
                "版式不规整",
                "版式也不规整",
                "质量一般",
                "分阶段处理",
                "怎么分阶段处理",
            )
        ):
            return True
        if any(token in text for token in ("绑定", "结构恢复")) and any(token in text for token in ("为什么", "更难", "更麻烦", "麻烦")):
            return True
        if any(token in text for token in ("风险点", "优先核对", "复核", "判断点")) and any(
            token in text for token in ("表格", "这份表", "当前这张表")
        ):
            return True

        model_name = str(self._model or "").strip().lower()
        if "gemini-3-pro" not in model_name:
            return False
        if any(token in text for token in ("数据库", "增删改查", "入库", "落库", "审计", "权限", "回滚")):
            return True
        if any(
            token in text
            for token in (
                "扫描文档",
                "扫描件",
                "版式不规整",
                "质量一般",
                "分阶段处理",
                "怎么分阶段处理",
                "问答和落库都更稳",
            )
        ):
            return True
        return False

    @staticmethod
    def _prefer_local_document_summary_answer(user_message: str) -> bool:
        text = str(user_message or "").strip()
        if not text:
            return False
        wants_focus = any(token in text for token in ("当前锁定对象", "锁定对象", "当前对象", "刚才那条", "那一行", "这张表"))
        wants_global = any(token in text for token in ("全局概览", "整体", "全局", "大致讲了什么", "主要讲了什么"))
        wants_stable_split = any(token in text for token in ("比较稳定", "谨慎校对", "还需要校对", "还要再核", "稳定"))
        wants_explicit_order = any(token in text for token in ("先", "再", "单独说明", "区分"))
        return wants_focus and wants_global and wants_stable_split and wants_explicit_order

    def _answer_max_tokens(self, route: str) -> int:
        route_key = str(route or "").strip().lower()
        preferred = {
            "field_lookup": 900,
            "table_lookup": 1000,
            "clarification_needed": 1000,
            "figure_value_read": 1100,
            "document_summary": 1600,
            "figure_overview": 1500,
            "database_action": 1500,
            "web_research": 1700,
            "knowledge_explain": 2100,
        }.get(route_key, self._max_tokens)
        return max(600, min(self._max_tokens, int(preferred)))

    def _reasoning_effort(self, route: str) -> Optional[str]:
        route_key = str(route or "").strip().lower()
        if route_key in {"field_lookup", "table_lookup", "clarification_needed", "figure_value_read"}:
            return "minimal"
        if route_key in {"document_summary", "web_research", "knowledge_explain"}:
            model_name = str(self._model or "").strip().lower()
            if "gemini-3-pro" in model_name:
                return None
            return "minimal"
        if route_key in {"figure_overview", "database_action"}:
            return "low"
        return None

    def _stream_recovery_max_tokens(self, route: str, base_budget: int) -> int:
        route_key = str(route or "").strip().lower()
        if route_key in {"knowledge_explain", "web_research", "document_summary"}:
            return max(base_budget, min(self._max_tokens, base_budget + 240))
        return max(base_budget, min(self._max_tokens, base_budget + 120))

    def _use_complete_then_chunk_primary(self, route: str) -> bool:
        route_key = str(route or "").strip().lower()
        if route_key not in {"knowledge_explain", "document_summary", "web_research"}:
            return False
        if self._broad_primary_mode in {"complete_then_chunk", "complete_then_chunk_primary"}:
            return True
        if self._broad_primary_mode == "auto":
            model_name = str(self._model or "").strip().lower()
            return "gemini-3-pro" in model_name
        return False

    @staticmethod
    def _prompt_history_limit(route: str) -> int:
        route_key = str(route or "").strip().lower()
        if route_key == "knowledge_explain":
            return 2
        if route_key in {"document_summary", "web_research"}:
            return 3
        return 6

    @staticmethod
    def _truncate_prompt_text(value: Any, max_chars: int) -> str:
        text = str(value or "").strip()
        if len(text) <= max_chars:
            return text
        if max_chars <= 3:
            return text[:max_chars]
        return text[: max_chars - 3].rstrip() + "..."

    @staticmethod
    def _truncate_prompt_tail_text(value: Any, max_chars: int) -> str:
        text = str(value or "").strip()
        if len(text) <= max_chars:
            return text
        if max_chars <= 3:
            return text[-max_chars:]
        return "..." + text[-(max_chars - 3) :].lstrip()

    def _trim_history_for_prompt(self, route: str, history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        limit = self._prompt_history_limit(route)
        trimmed: List[Dict[str, Any]] = []
        for item in (history or [])[-max(0, limit) :]:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            trimmed.append(
                {
                    "role": str(item.get("role") or "").strip().lower() or "user",
                    "content": self._truncate_prompt_text(content, 320),
                }
            )
        return trimmed

    def _compact_row_preview_for_prompt(self, row_preview: Any, *, max_cells: int = 6) -> List[Dict[str, str]]:
        compacted: List[Dict[str, str]] = []
        for item in row_preview[:max_cells] if isinstance(row_preview, list) else []:
            if not isinstance(item, dict):
                continue
            header = str(item.get("header") or "").strip()
            text = str(item.get("text") or "").strip()
            if not header and not text:
                continue
            compact_item: Dict[str, str] = {}
            if header:
                compact_item["header"] = self._truncate_prompt_text(header, 40)
            if text:
                compact_item["text"] = self._truncate_prompt_text(text, 80)
            compacted.append(compact_item)
        return compacted

    def _compact_focus_for_prompt(self, current_focus: Any) -> Dict[str, Any]:
        if not isinstance(current_focus, dict) or not current_focus:
            return {}
        compact: Dict[str, Any] = {}
        for key in ("lock_type", "lock_quality", "label", "row_label", "header", "recognition_tier"):
            value = str(current_focus.get(key) or "").strip()
            if value:
                compact[key] = self._truncate_prompt_text(value, 120)
        snippet = str(current_focus.get("snippet") or "").strip()
        if snippet:
            compact["snippet"] = self._truncate_prompt_text(snippet, 180)
        row_preview = self._compact_row_preview_for_prompt(current_focus.get("row_preview"), max_cells=6)
        if row_preview:
            compact["row_preview"] = row_preview
        fact_preview = self._compact_row_preview_for_prompt(current_focus.get("fact_preview"), max_cells=4)
        if fact_preview:
            compact["fact_preview"] = fact_preview
        return compact

    def _compact_document_overview_for_prompt(self, overview: Any) -> Dict[str, Any]:
        if not isinstance(overview, dict) or not overview:
            return {}
        compact: Dict[str, Any] = {}
        for key in (
            "field_count",
            "stable_field_count",
            "unstable_field_count",
            "table_count",
            "figure_count",
        ):
            value = overview.get(key)
            if value is not None:
                compact[key] = value
        evidence_scope = str(overview.get("evidence_scope") or "").strip()
        if evidence_scope:
            compact["evidence_scope"] = self._truncate_prompt_text(evidence_scope, 160)
        current_focus = self._compact_focus_for_prompt(overview.get("current_focus"))
        if current_focus:
            compact["current_focus"] = current_focus
        top_fields = [
            self._truncate_prompt_text(item, 40)
            for item in overview.get("top_fields", [])[:4]
            if str(item or "").strip()
        ] if isinstance(overview.get("top_fields"), list) else []
        if top_fields:
            compact["top_fields"] = top_fields
        top_tables = [
            self._truncate_prompt_text(item, 40)
            for item in overview.get("top_tables", [])[:3]
            if str(item or "").strip()
        ] if isinstance(overview.get("top_tables"), list) else []
        if top_tables:
            compact["top_tables"] = top_tables
        if isinstance(overview.get("top_figures"), list):
            figures: List[Dict[str, Any]] = []
            for item in overview.get("top_figures", [])[:2]:
                if not isinstance(item, dict):
                    continue
                caption = str(item.get("caption") or "").strip()
                page = item.get("page")
                figure: Dict[str, Any] = {}
                if caption:
                    figure["caption"] = self._truncate_prompt_text(caption, 80)
                if page is not None:
                    figure["page"] = page
                if figure:
                    figures.append(figure)
            if figures:
                compact["top_figures"] = figures
        soft_warnings = [
            self._truncate_prompt_text(item, 100)
            for item in overview.get("soft_warnings", [])[:3]
            if str(item or "").strip()
        ] if isinstance(overview.get("soft_warnings"), list) else []
        if soft_warnings:
            compact["soft_warnings"] = soft_warnings
        errors = [
            self._truncate_prompt_text(item, 100)
            for item in overview.get("errors", [])[:2]
            if str(item or "").strip()
        ] if isinstance(overview.get("errors"), list) else []
        if errors:
            compact["errors"] = errors
        return compact

    def _prepare_answer_context_for_prompt(self, route: str, answer_context: Dict[str, Any]) -> Dict[str, Any]:
        route_key = str(route or "").strip().lower()
        if route_key == "knowledge_explain":
            prepared: Dict[str, Any] = {
                "document_overview": self._compact_document_overview_for_prompt(answer_context.get("document_overview")),
            }
            return dump_context_for_model(prepared)
        if route_key == "document_summary":
            return dump_context_for_model(self._compact_document_overview_for_prompt(answer_context))
        if route_key == "web_research":
            prepared = {
                "document_overview": self._compact_document_overview_for_prompt(answer_context.get("document_overview")),
                "live_web_result_available": bool(answer_context.get("live_web_result_available")),
            }
            if isinstance(answer_context.get("web_results"), list):
                prepared["web_results"] = [
                    {
                        "title": self._truncate_prompt_text(str(item.get("title") or "").strip(), 80),
                        "url": self._truncate_prompt_text(str(item.get("url") or "").strip(), 120),
                        "published_at": self._truncate_prompt_text(str(item.get("published_at") or "").strip(), 40),
                    }
                    for item in answer_context.get("web_results", [])[:3]
                    if isinstance(item, dict)
                ]
            return dump_context_for_model(prepared)
        return dump_context_for_model(answer_context)

    def _prepare_summary_for_prompt(self, route: str, summary_text: str) -> str:
        route_key = str(route or "").strip().lower()
        limit = 240 if route_key in {"knowledge_explain", "document_summary", "web_research"} else 800
        return self._truncate_prompt_text(summary_text, limit)

    @staticmethod
    def _normalize_user_visible_spacing(text: str) -> str:
        answer = str(text or "")
        if not answer:
            return ""
        answer = (
            answer.replace("\r\n", "\n")
            .replace("\r", "\n")
            .replace("\u200b", "")
            .replace("\u0000", "")
            .replace("\ufeff", "")
            .replace("\u00a0", " ")
            .replace("\u3000", " ")
            .replace("\u2002", " ")
            .replace("\u2003", " ")
            .replace("\u2009", " ")
            .replace("\u202f", " ")
            .replace("\u205f", " ")
        )
        answer = re.sub(r"[ \t]+\n", "\n", answer)
        answer = re.sub(r"\n[ \t]+", "\n", answer)
        answer = re.sub(r"[ \t]{2,}", " ", answer)
        answer = "\n".join([line.strip() if line.strip() else "" for line in answer.split("\n")])
        answer = re.sub(r"\n{3,}", "\n\n", answer)
        answer = re.sub(r"\n\n(?=[-*•]\s)", "\n", answer)
        answer = AssistantService._merge_short_bridge_paragraphs(answer)
        return answer.strip()

    @staticmethod
    def _contains_any_keyword(text: str, keywords: tuple[str, ...]) -> bool:
        raw = str(text or "").strip()
        if not raw:
            return False
        lowered = raw.lower()
        return any(keyword in raw or keyword.lower() in lowered for keyword in keywords)

    @staticmethod
    def _merge_short_bridge_paragraphs(text: str) -> str:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n", str(text or "")) if part.strip()]
        if len(paragraphs) < 2:
            return "\n\n".join(paragraphs)
        bridge_patterns = (
            r"^(?:先看|再看|最后再看|先说|再说|先把|再把|整体看|单看|换句话说|更具体一点)[：:，,]?$",
            r"^(?:先看当前对象|再看整份文档|先看文档里能确认的部分|再看通用做法|最后说还需要联网核实的部分|比较稳的部分|还要再核的部分)[：:，,]?$",
        )
        merged: List[str] = []
        index = 0
        while index < len(paragraphs):
            current = paragraphs[index]
            if index + 1 < len(paragraphs):
                normalized_current = re.sub(r"\s+", "", current)
                if len(normalized_current) <= 20 and any(re.match(pattern, normalized_current) for pattern in bridge_patterns):
                    current_prefix = current
                    if current_prefix:
                        if current_prefix[-1] in "：:":
                            pass
                        elif current_prefix[-1] in "。！？":
                            current_prefix = f"{current_prefix[:-1]}，"
                        elif current_prefix[-1] not in "，,":
                            current_prefix = f"{current_prefix}，"
                    merged.append(f"{current_prefix}{paragraphs[index + 1]}")
                    index += 2
                    continue
            merged.append(current)
            index += 1
        return "\n\n".join(merged)

    @staticmethod
    def _normalize_internal_status_terms(text: str) -> str:
        normalized = str(text or "")
        replacements = (
            (r"\bblocked\b", "当前还不能安全执行"),
            (r"\bweak_lock\b", "目标对象还没稳定锁定"),
            (r"\bno_lock\b", "还没有锁定到明确对象"),
            (r"\bfallback\b", "保守回答"),
            (r"\btimeout\b", "响应超时"),
        )
        for pattern, replacement in replacements:
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        return normalized

    @staticmethod
    def _strip_internal_metadata_lines(text: str) -> str:
        patterns = (
            r"(?i)^\s*[-*]?\s*(?:route|tool|function|payload|json|trace|citation|message_id|assistant_message_id|diagnostics?)\s*[:：=]",
            r"(?i)^\s*[-*]?\s*(?:ref_id|source_ref_id|figure_id|table_id|object_id|row_id|row_index|page|line|column|bbox|locator)\s*[:：=]",
            r"^\s*[-*]?\s*(?:原文定位|定位信息|内部定位|引用定位)\s*[:：=]",
        )
        kept_lines: List[str] = []
        for line in str(text or "").split("\n"):
            stripped = line.strip()
            if stripped and any(re.search(pattern, stripped) for pattern in patterns):
                continue
            kept_lines.append(line)
        cleaned = "\n".join(kept_lines)
        cleaned = re.sub(r"(?i)\b(?:ref_id|source_ref_id|figure_id|table_id|object_id|locator)\s*[:=]\s*[\w./-]+", "", cleaned)
        cleaned = re.sub(r"(?i)\b(?:route|payload|tool|function)\s*[:=]\s*[\w./-]+", "", cleaned)
        cleaned = re.sub(r"(?:原文定位|定位信息|内部定位|引用定位)\s*[:：]\s*[^\n]+", "", cleaned)
        cleaned = re.sub(r"\(\s*,\s*\)", "", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned

    def _alignment_requirements(self, route: str, user_message: str) -> List[str]:
        route_key = str(route or "").strip().lower()
        question = str(user_message or "").strip()
        requirements: List[str] = []
        if self._contains_any_keyword(question, ("先", "再", "分别", "分开", "单独说明", "依次", "然后")):
            requirements.append("如果用户点了回答顺序，就按那个顺序说。")
        if route_key == "document_summary" or self._contains_any_keyword(
            question,
            ("大致讲了什么", "主要讲了什么", "概览", "整体", "全局"),
        ):
            requirements.append("如果用户要概览，就先给概览结论，不要改写成排查建议。")
        if self._contains_any_keyword(
            question,
            ("当前锁定对象", "锁定对象", "当前对象", "刚才那条", "那一行", "这张图", "这个表"),
        ):
            requirements.append("如果用户点了当前对象，就先把当前对象说清楚。")
        if self._contains_any_keyword(question, ("稳定", "比较稳", "谨慎", "核对", "校对", "不确定")):
            requirements.append("如果用户要区分稳妥部分和待核对部分，就明确分开说。")
        if self._contains_any_keyword(question, ("流程", "链路", "步骤", "怎么做", "怎么处理")):
            requirements.append("如果用户问流程或做法，就把流程讲出来，不要只讲原则。")
        if self._contains_any_keyword(question, ("分阶段", "分段处理", "阶段处理")):
            requirements.append("如果用户问分阶段处理，就按阶段展开，至少覆盖质量门槛、图像清洗、结构恢复、抽取校验和问答/入库衔接。")
        if self._contains_any_keyword(question, ("为什么", "更难", "更麻烦", "难点")):
            requirements.append("如果用户问原因或难点，就先回答原因，不要改写成泛泛的方法论介绍。")
        if self._contains_any_keyword(question, ("约束", "限制", "边界", "确认", "审计")):
            requirements.append("如果用户问约束、确认或审计边界，就把不能越过的条件说清楚。")
        if self._contains_any_keyword(question, ("容易出错", "坑", "风险点", "误差", "翻车")):
            requirements.append("如果用户问容易出错的地方，就给具体风险点。")
        if self._contains_any_keyword(question, ("不要泛泛而谈", "具体判断点", "别太泛", "不要只给定义")):
            requirements.append("不要只讲定义或架构口号，至少给出当前题目需要的具体判断点。")
        if self._contains_any_keyword(question, ("自然一点", "口语一点", "别太书面", "像人话", "像聊天")):
            requirements.append("表达再自然一点，不要写成讲稿。")
        if route_key in {"knowledge_explain", "document_summary", "web_research"} or self._contains_any_keyword(
            question,
            ("区别", "怎么理解", "为什么", "思路", "概览", "整体", "全局"),
        ):
            requirements.append("默认用自然段，不要写成讲义或汇报稿。")
        return requirements

    def _answer_needs_alignment_repair(self, route: str, user_message: str, answer_text: str) -> bool:
        route_key = str(route or "").strip().lower()
        question = str(user_message or "").strip()
        normalized_answer = self._normalize_user_visible_spacing(answer_text)
        answer = normalized_answer.lower()
        if not question or not normalized_answer:
            return False
        if re.search(r"\b(ref_id|figure_id|table_id|payload|tool_call|assistant_message_id)\b", answer):
            return True

        wants_summary = route_key == "document_summary" or self._contains_any_keyword(
            question,
            ("大致讲了什么", "主要讲了什么", "概览", "整体", "全局"),
        )
        wants_focus = self._contains_any_keyword(
            question,
            ("当前锁定对象", "锁定对象", "当前对象", "刚才那条", "那一行", "这张图", "这个表"),
        )
        wants_global = self._contains_any_keyword(question, ("整体", "全局", "概览", "大致讲了什么", "主要讲了什么"))
        wants_focus_then_global = wants_focus and wants_global
        wants_stable_split = self._contains_any_keyword(
            question,
            ("稳定", "比较稳", "谨慎", "核对", "校对", "不确定"),
        )
        wants_flow = self._contains_any_keyword(question, ("流程", "链路", "步骤", "怎么做", "怎么处理"))
        wants_stagewise = self._contains_any_keyword(question, ("分阶段", "分段处理", "阶段处理"))
        wants_causal_explain = self._contains_any_keyword(question, ("为什么", "更难", "更麻烦", "难点"))
        wants_constraints = self._contains_any_keyword(question, ("约束", "限制", "边界", "确认", "审计"))
        wants_risks = self._contains_any_keyword(question, ("容易出错", "坑", "风险点", "误差", "翻车"))
        wants_stepwise = self._contains_any_keyword(question, ("步骤", "分步骤", "一步一步", "逐条", "按步骤", "列出来"))

        if wants_summary:
            summary_hits = ("主要", "大致", "整体", "概览", "这份文档", "这份材料", "内容", "重点")
            drift_hits = ("优先核对", "准备入库", "风险点", "排查", "审计")
            if any(hit in normalized_answer for hit in drift_hits) and not any(hit in normalized_answer for hit in summary_hits):
                return True

        if wants_focus_then_global:
            focus_hits = ("刚才那条", "当前这条", "这条记录", "当前对象", "这张表", "这张图")
            global_hits = ("整份文档", "整体", "全局", "概览", "这份文档", "这份材料")
            if not any(hit in normalized_answer for hit in focus_hits):
                return True
            if not any(hit in normalized_answer for hit in global_hits):
                return True

        if wants_stable_split:
            stable_hits = ("比较稳", "较稳", "能确认", "可以先确认", "目前能确定", "已经能确认")
            caution_hits = ("还要再核", "还要核对", "谨慎", "不确定", "仍需核对", "还不能完全确认")
            if not any(hit in normalized_answer for hit in stable_hits):
                return True
            if not any(hit in normalized_answer for hit in caution_hits):
                return True

        if wants_flow:
            flow_hits = ("流程", "链路", "步骤", "先", "再", "最后")
            if not any(hit in normalized_answer for hit in flow_hits):
                return True

        if wants_stagewise:
            stage_hits = ("门槛", "清洗", "纠偏", "去噪", "结构恢复", "表格", "抽取", "校验", "问答", "入库")
            if sum(1 for hit in stage_hits if hit in normalized_answer) < 4:
                return True

        if wants_causal_explain:
            cause_hits = ("因为", "难在", "麻烦在", "绑定", "行列", "表头", "字段映射", "上下文", "错位", "挂错")
            if sum(1 for hit in cause_hits if hit in normalized_answer) < 3:
                return True

        if wants_constraints:
            constraint_hits = ("约束", "限制", "边界", "确认", "预览", "审计", "白名单", "where", "影响范围")
            if not any(hit.lower() in answer for hit in constraint_hits):
                return True

        if wants_risks:
            risk_hits = ("容易出错", "风险", "坑", "翻车", "误差", "错绑", "错位", "越界", "误删")
            if not any(hit in normalized_answer for hit in risk_hits):
                return True

        if route_key == "web_research" and self._contains_any_keyword(
            question,
            ("文档内证据", "通用经验", "联网", "联网查证", "联网核实"),
        ):
            document_hits = ("文档", "材料", "当前这份", "单看")
            general_hits = ("通用经验", "通用做法", "一般会")
            web_hits = ("联网", "最新", "再核", "查证", "核实", "外部来源")
            if not any(hit in normalized_answer for hit in document_hits):
                return True
            if not any(hit in normalized_answer for hit in general_hits):
                return True
            if not any(hit in normalized_answer for hit in web_hits):
                return True

        if route_key in {"knowledge_explain", "document_summary", "web_research"}:
            paragraph_count = len([part for part in re.split(r"\n\s*\n", normalized_answer) if part.strip()])
            numbered_items = len(re.findall(r"(?m)^\d+\.\s+", normalized_answer))
            heading_count = len(re.findall(r"(?m)^#{1,6}\s+", normalized_answer))
            bookish_markers = (
                "关于这个问题，我们先",
                "从工程视角看",
                "本质上",
                "换句话说",
                "可以参考以下思路",
                "下面分几个方面说",
                "这里最容易出错的主要有三个",
                "可以，我先把边界拆开说",
                "按你当前这份材料的上下文看",
                "这几项先过了",
                "别把这种扫描件直接往抽取链路里塞",
            )
            if paragraph_count >= 8 and not wants_stepwise:
                return True
            if numbered_items >= 4 and not wants_stepwise:
                return True
            if heading_count >= 3 and not wants_stepwise:
                return True
            if sum(1 for marker in bookish_markers if marker in normalized_answer) >= 2:
                return True

        return False

    def _alignment_repair_instruction(self, route: str, user_message: str) -> str:
        requirements = self._alignment_requirements(route, user_message)
        if not requirements:
            return ""
        bullet_text = "\n".join([f"- {item}" for item in requirements])
        return (
            "上一版回答还没有完全对齐用户这一轮的问题。请在不改变已确认事实的前提下，补齐缺失点，并把表达收顺一些：\n"
            f"{bullet_text}\n"
            "保留自然口吻，像真人当面解释，不要套固定开场和固定收尾，不要写成汇报稿，也不要暴露工具、route、payload 或原始定位串。"
        )

    def _polish_user_visible_answer(self, text: str, route: str) -> str:
        answer = self._normalize_user_visible_spacing(text)
        if not answer:
            return ""
        route_key = str(route or "").strip().lower()
        answer = re.sub(r"\*\*(.*?)\*\*", r"\1", answer)
        answer = self._normalize_internal_status_terms(answer)
        answer = self._strip_internal_metadata_lines(answer)
        answer = re.sub(r"(?:原文定位|定位信息|内部定位|引用定位)\s*[:：]\s*[^\n]+", "", answer)
        answer = re.sub(r"[ \t]+([，。；：！？])", r"\1", answer)
        answer = re.sub(r"([（(])\s+", r"\1", answer)
        answer = re.sub(r"\s+([）)])", r"\1", answer)
        answer = re.sub(r"\n{3,}", "\n\n", answer)

        if route_key in {"table_lookup", "field_lookup"} and len(answer) <= 180:
            answer = re.sub(r"\n{2,}", " ", answer)
            answer = re.sub(r"\s{2,}", " ", answer)

        answer = self._normalize_user_visible_spacing(answer)
        return answer.strip()

    def _build_prompt_messages(
        self,
        *,
        route: str,
        user_message: str,
        summary_text: str,
        history: List[Dict[str, Any]],
        answer_context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        return build_answer_messages(
            route=route,
            user_message=user_message,
            summary_text=self._prepare_summary_for_prompt(route, summary_text),
            history=self._trim_history_for_prompt(route, history),
            answer_context=self._prepare_answer_context_for_prompt(route, answer_context),
        )

    @staticmethod
    def _completed_answer_retry_threshold(route: str) -> int:
        route_key = str(route or "").strip().lower()
        if route_key == "knowledge_explain":
            return 280
        if route_key == "document_summary":
            return 180
        if route_key == "web_research":
            return 220
        return 0

    def _should_retry_completed_answer(
        self,
        *,
        route: str,
        answer_text: str,
        finish_reason: str,
    ) -> bool:
        normalized = str(answer_text or "").strip()
        if not normalized:
            return True
        if self._looks_like_incomplete_provider_answer(normalized):
            return True
        if str(finish_reason or "").strip().lower() not in {"length", "max_tokens"}:
            return False
        threshold = self._completed_answer_retry_threshold(route)
        return threshold > 0 and len(normalized) < threshold

    @staticmethod
    def _build_completion_repair_messages(route: str, prepared_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        route_key = str(route or "").strip().lower()
        route_hint = {
            "knowledge_explain": "优先把概念讲成人话，再补流程、边界和常见坑。",
            "document_summary": "优先说清当前对象或文档到底在讲什么，再区分已确认和仍需核对的部分。",
            "web_research": "先把现在能确定的边界说清，再分开文档依据、通用知识和仍待联网核实的部分。",
        }.get(route_key, "先补齐缺失点，再把表达收顺。")
        repair_instruction = (
            "请在保留已确认事实不变的前提下，把上一版中文回答补齐并润色成一条更自然的最终答复。"
            "先补用户真正问到但还没答到的点，再把表达收顺。"
            "不要提工具、route、payload、JSON、原始定位串，也不要重复问题。"
            "尽量放在一个连续回答里，优先自然段；除非确有必要，不要写成 1. 2. 3. 的讲义。"
            + route_hint
        )
        return list(prepared_messages) + [{"role": "user", "content": repair_instruction}]

    def _should_repair_streamed_answer(
        self,
        *,
        route: str,
        answer_text: str,
        diagnostics: Dict[str, Any],
    ) -> bool:
        normalized = str(answer_text or "").strip()
        if not normalized:
            return True
        finish_reason = str(diagnostics.get("finish_reason") or "").strip().lower()
        if finish_reason in {"length", "max_tokens"}:
            return True
        if self._looks_like_incomplete_provider_answer(normalized):
            return True
        if re.search(r"\b(ref_id|figure_id|table_id|payload|tool_call|assistant_message_id)\b", normalized.lower()):
            return True
        route_key = str(route or "").strip().lower()
        if route_key in {"knowledge_explain", "document_summary", "web_research"} and len(normalized) < 120:
            return True
        return False

    def _stream_timeout_profile(self, route: str) -> Dict[str, float]:
        route_key = str(route or "").strip().lower()
        profile = {
            "connect_timeout_sec": self._connect_timeout_sec,
            "first_frame_timeout_sec": self._first_frame_timeout_sec,
            "first_visible_timeout_sec": self._first_visible_timeout_sec,
            "stream_idle_timeout_sec": self._stream_idle_timeout_sec,
        }
        if route_key in {"knowledge_explain", "web_research"}:
            profile["connect_timeout_sec"] = max(profile["connect_timeout_sec"], 30.0)
            profile["first_frame_timeout_sec"] = max(profile["first_frame_timeout_sec"], 70.0)
            profile["first_visible_timeout_sec"] = max(profile["first_visible_timeout_sec"], 80.0)
            profile["stream_idle_timeout_sec"] = max(profile["stream_idle_timeout_sec"], 45.0)
        elif route_key == "document_summary":
            profile["connect_timeout_sec"] = max(profile["connect_timeout_sec"], 26.0)
            profile["first_frame_timeout_sec"] = max(profile["first_frame_timeout_sec"], 55.0)
            profile["first_visible_timeout_sec"] = max(profile["first_visible_timeout_sec"], 65.0)
            profile["stream_idle_timeout_sec"] = max(profile["stream_idle_timeout_sec"], 36.0)
        elif route_key in {"figure_overview", "database_action"}:
            profile["connect_timeout_sec"] = max(profile["connect_timeout_sec"], 18.0)
            profile["first_frame_timeout_sec"] = max(profile["first_frame_timeout_sec"], 18.0)
            profile["first_visible_timeout_sec"] = max(profile["first_visible_timeout_sec"], 22.0)
            profile["stream_idle_timeout_sec"] = max(profile["stream_idle_timeout_sec"], 26.0)
        return profile

    @staticmethod
    def _build_stream_repair_messages(
        route: str,
        prepared_messages: List[Dict[str, Any]],
        partial_answer: str,
    ) -> List[Dict[str, Any]]:
        route_key = str(route or "").strip().lower()
        route_hint = {
            "knowledge_explain": "Keep the practical, engineer-to-engineer tone and continue with concrete guidance.",
            "document_summary": "Keep the answer concise, specific, and focused on the most important checks.",
            "web_research": "Keep boundaries explicit and continue separating document evidence from general knowledge.",
        }.get(route_key, "Keep the same tone and continue naturally.")
        continuation_instruction = (
            "Continue the assistant's previous Chinese answer from exactly where it stopped. "
            "Do not restart, do not paraphrase the earlier content, and do not add a new preamble. "
            "Return only the missing continuation text. "
            "If the answer is already complete, reply with <NO_CONTINUATION>. "
            + route_hint
        )
        return list(prepared_messages) + [
            {"role": "assistant", "content": partial_answer},
            {"role": "user", "content": continuation_instruction},
        ]

    @staticmethod
    def _dedupe_stream_repair_text(partial_answer: str, repair_text: str) -> str:
        candidate = str(repair_text or "").strip()
        if not candidate or candidate == "<NO_CONTINUATION>":
            return ""
        partial = str(partial_answer or "")
        partial_clean = partial.rstrip()
        candidate_clean = candidate.lstrip()
        if not partial_clean:
            return candidate_clean
        if candidate_clean in partial_clean:
            return ""
        max_overlap = min(len(partial_clean), len(candidate_clean), 160)
        for overlap in range(max_overlap, 0, -1):
            if partial_clean[-overlap:] == candidate_clean[:overlap]:
                return candidate_clean[overlap:].lstrip()
        return candidate_clean

    def _write_stream_debug_artifact(
        self,
        *,
        assistant_message_id: str,
        route: str,
        diagnostics: Dict[str, Any],
        messages: List[Dict[str, Any]],
    ) -> None:
        if self._debug_dir is None:
            return
        try:
            day_dir = self._debug_dir / time.strftime("%Y%m%d")
            day_dir.mkdir(parents=True, exist_ok=True)
            safe_route = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(route or "route")).strip("_") or "route"
            target = day_dir / f"{time.strftime('%H%M%S')}_{str(assistant_message_id or uuid.uuid4().hex)}_{safe_route}_stream.json"
            target.write_text(
                json.dumps(
                    {
                        "assistant_message_id": assistant_message_id,
                        "route": route,
                        "diagnostics": diagnostics,
                        "messages": self._message_debug_summary(messages),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            return

    def _load_payload_from_document_diagnostics(self, document: DocumentExtractionResponse) -> Dict[str, Any]:
        diagnostics = document.diagnostics if isinstance(document.diagnostics, dict) else {}
        artifact_path = str(diagnostics.get("assistant_payload_artifact_path") or "").strip()
        if not artifact_path:
            artifact_url = str(diagnostics.get("assistant_payload_artifact_url") or "").strip()
            prefix = "/extract/artifact/"
            if artifact_url.startswith(prefix):
                encoded = artifact_url[len(prefix):]
                artifact_path = "/".join(unquote(part) for part in encoded.split("/") if part)
        if not artifact_path:
            return {}

        fragment = artifact_path.lstrip("/\\")
        direct_candidate = Path(artifact_path)
        path_candidates: List[Path] = []
        if direct_candidate.is_absolute():
            path_candidates.append(direct_candidate)
        else:
            for root in self._artifact_root_dirs():
                path_candidates.append(root / fragment)

        seen_targets: set[str] = set()
        for candidate in path_candidates:
            try:
                target = candidate.resolve()
            except Exception:
                continue
            target_key = str(target).lower()
            if target_key in seen_targets:
                continue
            seen_targets.add(target_key)
            if not target.exists() or not target.is_file():
                continue
            try:
                raw = json.loads(target.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            if isinstance(raw.get("payload"), dict):
                raw = raw.get("payload") or {}
            if isinstance(raw, dict):
                return raw
        return {}

    async def _resolve_extraction_payload(
        self,
        *,
        document: DocumentExtractionResponse,
        request_payload: Optional[Dict[str, Any]] = None,
    ) -> tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        resolved = dict(request_payload or {})
        if payload_has_structural_context(resolved):
            return resolved, None

        storage_payload = await self._storage.load_extraction_payload(document.file_hash) or {}
        resolved = merge_structural_payload(resolved, storage_payload)
        if payload_has_structural_context(resolved):
            return resolved, None

        artifact_payload = self._load_payload_from_document_diagnostics(document)
        resolved = merge_structural_payload(resolved, artifact_payload)
        if payload_has_structural_context(resolved):
            return resolved, {
                "tool_name": "restore_assistant_context",
                "status": "done",
                "message": "已从文档附带的结构化 artifact 恢复助手上下文",
                "detail": f"tables={len(resolved.get('tables', []) or [])}, figures={len(resolved.get('figures', []) or [])}",
                "output": {
                    "source": "diagnostic_artifact",
                    "table_count": len(resolved.get("tables", []) or []),
                    "figure_count": len(resolved.get("figures", []) or []),
                },
            }

        trace_payload = reconstruct_payload_from_trace_hits(document)
        resolved = merge_structural_payload(resolved, trace_payload)
        if payload_has_structural_context(resolved):
            return resolved, {
                "tool_name": "restore_assistant_context",
                "status": "done",
                "message": "已根据 trace_hits 重建轻量助手上下文",
                "detail": f"tables={len(resolved.get('tables', []) or [])}, figures={len(resolved.get('figures', []) or [])}",
                "output": {
                    "source": "trace_hits",
                    "table_count": len(resolved.get("tables", []) or []),
                    "figure_count": len(resolved.get("figures", []) or []),
                },
            }

        return resolved, None

    async def ensure_session(self, payload: AssistantSessionRequest) -> AssistantSessionResponse:
        requested_id = str(payload.session_id or "").strip()
        summary_text = str(payload.summary or "").strip()
        existing = await self._storage.fetch_assistant_session(requested_id) if requested_id else None
        if existing and str(existing.get("file_hash") or "").strip() == payload.document.file_hash:
            session_id = str(existing.get("session_id") or requested_id)
            current_lock_raw = existing.get("current_object_lock_json") if isinstance(existing.get("current_object_lock_json"), dict) else {}
            messages = await self._storage.list_assistant_messages(session_id, limit=40)
            await self._storage.upsert_assistant_session(
                session_id=session_id,
                file_hash=payload.document.file_hash,
                file_name=payload.document.file_name,
                summary_text=summary_text or str(existing.get("summary_text") or ""),
                current_object_lock=current_lock_raw,
                metadata={"track": payload.document.track},
            )
            return AssistantSessionResponse(
                session_id=session_id,
                summary_used=summary_text or str(existing.get("summary_text") or ""),
                current_object_lock=AssistantObjectLock(**current_lock_raw) if current_lock_raw else None,
                messages=[self._to_session_message(item) for item in messages],
            )

        session_id = f"asst-{uuid.uuid4().hex}"
        await self._storage.upsert_assistant_session(
            session_id=session_id,
            file_hash=payload.document.file_hash,
            file_name=payload.document.file_name,
            summary_text=summary_text,
            current_object_lock={},
            metadata={"track": payload.document.track},
        )
        return AssistantSessionResponse(
            session_id=session_id,
            summary_used=summary_text,
            current_object_lock=None,
            messages=[],
        )

    async def query_once(self, payload: AssistantQueryRequest) -> AssistantQueryResponse:
        extraction_payload, _restore_event = await self._resolve_extraction_payload(
            document=payload.document,
            request_payload=None,
        )
        artifacts = await self._build_turn_artifacts_safe(
            document=payload.document,
            summary_text=str(payload.summary or "").strip(),
            user_message=str(payload.user_instruction or "").strip(),
            top_k=int(payload.top_k or 12),
            current_object_lock=None,
            extraction_payload=extraction_payload,
        )
        if artifacts.prefer_fallback_only:
            answer = artifacts.fallback_answer
        else:
            answer = await self._complete_answer_text(
                route=artifacts.route,
                user_message=str(payload.user_instruction or "").strip(),
                summary_text=str(payload.summary or "").strip(),
                history=[],
                answer_context=artifacts.answer_context,
                fallback=artifacts.fallback_answer,
            )
        answer = self._polish_user_visible_answer(answer, artifacts.route)
        return AssistantQueryResponse(
            ok=True,
            answer=answer,
            summary_used=str(payload.summary or "").strip(),
            matched_fields=artifacts.matched_fields,
            matched_trace_hits=artifacts.matched_trace_hits,
            persisted=False,
            persisted_rows=0,
            warnings=artifacts.warnings,
        )

    async def stream_chat(self, payload: AssistantChatStreamRequest) -> AsyncIterator[bytes]:
        session_req = AssistantSessionRequest(
            document=payload.document,
            summary=payload.summary,
            session_id=payload.session_id,
        )
        session = await self.ensure_session(session_req)
        session_id = session.session_id
        session_lock = session.current_object_lock.model_dump(mode="json") if session.current_object_lock else {}
        request_lock = payload.current_object_lock.model_dump(mode="json") if payload.current_object_lock else {}
        current_lock = request_lock or session_lock or {}
        history = [item.model_dump(mode="json") for item in session.messages]
        user_message = str(payload.user_message or "").strip()
        summary_text = str(payload.summary or "").strip() or session.summary_used

        user_message_id = f"msg-{uuid.uuid4().hex}"
        assistant_message_id = f"msg-{uuid.uuid4().hex}"
        await self._storage.save_assistant_message(
            session_id=session_id,
            message_id=user_message_id,
            role="user",
            message_type="user_message",
            content=user_message,
            payload={},
        )
        yield sse_event(
            "assistant_start",
            {
                "session_id": session_id,
                "assistant_message_id": assistant_message_id,
            },
        )

        extraction_payload, restore_event = await self._resolve_extraction_payload(
            document=payload.document,
            request_payload=dict(payload.extraction_payload or {}),
        )
        if restore_event:
            await self._storage.save_tool_invocation(
                session_id=session_id,
                message_id=assistant_message_id,
                tool_name=str(restore_event.get("tool_name") or "restore_assistant_context"),
                status=str(restore_event.get("status") or "done"),
                input_summary={},
                output_summary=restore_event.get("output") if isinstance(restore_event.get("output"), dict) else {},
                latency_ms=0,
            )
            yield sse_event(
                "tool_status",
                {
                    "tool_name": str(restore_event.get("tool_name") or "restore_assistant_context"),
                    "status": str(restore_event.get("status") or "done"),
                    "message": str(restore_event.get("message") or ""),
                    "detail": str(restore_event.get("detail") or ""),
                },
            )
        artifacts = await self._build_turn_artifacts_safe(
            document=payload.document,
            summary_text=summary_text,
            user_message=user_message,
            top_k=int(payload.top_k or 12),
            current_object_lock=current_lock or None,
            extraction_payload=extraction_payload,
        )

        for event in artifacts.tool_events:
            tool_name = str(event.get("tool_name") or "").strip()
            await self._storage.save_tool_invocation(
                session_id=session_id,
                message_id=assistant_message_id,
                tool_name=tool_name,
                status=str(event.get("status") or "done"),
                input_summary=event.get("input") if isinstance(event.get("input"), dict) else {},
                output_summary=event.get("output") if isinstance(event.get("output"), dict) else {},
                latency_ms=int(event.get("latency_ms", 0) or 0),
            )
            yield sse_event(
                "tool_status",
                {
                    "tool_name": tool_name,
                    "status": str(event.get("status") or "done"),
                    "message": str(event.get("message") or ""),
                    "detail": str(event.get("detail") or ""),
                },
            )

        if artifacts.citations or artifacts.current_object_lock:
            yield sse_event(
                "citation_bundle",
                {
                    "citations": artifacts.citations,
                    "current_object_lock": artifacts.current_object_lock or {},
                },
            )

        if artifacts.action_preview:
            yield sse_event("action_preview", artifacts.action_preview)

        answer_text_parts: List[str] = []
        final_answer_override = ""
        provider_error = ""
        provider_diagnostics: Dict[str, Any] = {}
        messages: List[Dict[str, Any]] = []
        provider_model = str(getattr(self._provider, "model", "") or self._model)
        route_max_tokens = self._answer_max_tokens(artifacts.route)
        if artifacts.prefer_fallback_only:
            fallback_text = self._polish_user_visible_answer(artifacts.fallback_answer, artifacts.route)
            provider_diagnostics = {
                "classification": "fallback_only_local",
                "fallback_used": True,
                "fallback_mode": "conservative_local_answer",
                "provider_model": provider_model,
                "route": artifacts.route,
                "prompt_version": self._prompt_version,
                "max_tokens_budget": route_max_tokens,
            }
            for chunk in chunk_text(fallback_text, chunk_size=72):
                answer_text_parts.append(chunk)
                yield sse_event("assistant_delta", {"text": chunk})
        else:
            try:
                messages = self._build_prompt_messages(
                    route=artifacts.route,
                    user_message=user_message,
                    summary_text=summary_text,
                    history=history,
                    answer_context=artifacts.answer_context,
                )
                if self._use_complete_then_chunk_primary(artifacts.route):
                    completed_answer, completion_diagnostics = await self._complete_answer_with_diagnostics(
                        route=artifacts.route,
                        user_message=user_message,
                        summary_text=summary_text,
                        history=history,
                        answer_context=artifacts.answer_context,
                        fallback=artifacts.fallback_answer,
                        max_tokens=route_max_tokens,
                        messages=messages,
                        delivery_mode="complete_then_chunk_primary",
                    )
                    provider_diagnostics = completion_diagnostics
                    completed_clean = completed_answer.strip()
                    final_answer_override = self._polish_user_visible_answer(
                        completed_clean or artifacts.fallback_answer,
                        artifacts.route,
                    )
                    for chunk in chunk_text(final_answer_override, chunk_size=self._complete_chunk_size):
                        answer_text_parts.append(chunk)
                        yield sse_event("assistant_delta", {"text": chunk})
                else:
                    stream_diagnostics: Dict[str, Any] = {}
                    async for chunk in self._stream_provider_text(
                        messages,
                        diagnostics=stream_diagnostics,
                        max_tokens=route_max_tokens,
                        route=artifacts.route,
                    ):
                        answer_text_parts.append(chunk)
                        yield sse_event("assistant_delta", {"text": chunk})
                    provider_diagnostics = stream_diagnostics
                    streamed_answer = "".join(answer_text_parts).strip()
                    needs_alignment_repair = self._answer_needs_alignment_repair(
                        artifacts.route,
                        user_message,
                        streamed_answer,
                    )
                    if self._should_repair_streamed_answer(
                        route=artifacts.route,
                        answer_text=streamed_answer,
                        diagnostics=provider_diagnostics,
                    ) or needs_alignment_repair:
                        recovery_budget = self._stream_recovery_max_tokens(artifacts.route, route_max_tokens)
                        repair_suffix = ""
                        repair_suffix_diagnostics: Dict[str, Any] = {}
                        if streamed_answer:
                            repair_suffix, repair_suffix_diagnostics = await self._continue_streamed_answer_with_diagnostics(
                                route=artifacts.route,
                                prepared_messages=messages,
                                partial_answer=streamed_answer,
                                max_tokens=recovery_budget,
                            )
                            if repair_suffix:
                                answer_text_parts.append(repair_suffix)
                                yield sse_event("assistant_delta", {"text": repair_suffix})
                                provider_diagnostics["post_stream_repair_used"] = True
                                provider_diagnostics["repair_strategy"] = "continuation_delta"
                                provider_diagnostics["repair_added_chars"] = len(repair_suffix)
                                provider_diagnostics["repair_classification"] = str(
                                    repair_suffix_diagnostics.get("classification") or ""
                                )
                                provider_diagnostics["repair_finish_reason"] = str(
                                    repair_suffix_diagnostics.get("finish_reason") or ""
                                )
                                provider_diagnostics["visible_chars"] = len("".join(answer_text_parts).strip())

                        repaired_streamed_answer = "".join(answer_text_parts).strip()
                        if repair_suffix:
                            still_needs_full_recovery = self._looks_like_incomplete_provider_answer(
                                repaired_streamed_answer
                            )
                        else:
                            still_needs_full_recovery = self._should_repair_streamed_answer(
                                route=artifacts.route,
                                answer_text=repaired_streamed_answer,
                                diagnostics=provider_diagnostics,
                            )
                        if not still_needs_full_recovery:
                            still_needs_full_recovery = self._answer_needs_alignment_repair(
                                artifacts.route,
                                user_message,
                                repaired_streamed_answer,
                            )
                        if still_needs_full_recovery:
                            recovered_answer = await self._complete_answer_text(
                                route=artifacts.route,
                                user_message=user_message,
                                summary_text=summary_text,
                                history=history,
                                answer_context=artifacts.answer_context,
                                fallback=artifacts.fallback_answer,
                                max_tokens=recovery_budget,
                            )
                            recovered_clean = recovered_answer.strip()
                            if recovered_clean:
                                if repaired_streamed_answer and recovered_clean.startswith(repaired_streamed_answer):
                                    repair_tail = recovered_clean[len(repaired_streamed_answer) :].lstrip()
                                    if repair_tail:
                                        answer_text_parts.append(repair_tail)
                                        yield sse_event("assistant_delta", {"text": repair_tail})
                                        provider_diagnostics["post_stream_repair_used"] = True
                                        provider_diagnostics["repair_strategy"] = "full_recovery_tail_append"
                                        provider_diagnostics["repair_added_chars"] = provider_diagnostics.get(
                                            "repair_added_chars", 0
                                        ) + len(repair_tail)
                                        provider_diagnostics["visible_chars"] = len("".join(answer_text_parts).strip())
                                else:
                                    final_answer_override = self._polish_user_visible_answer(
                                        recovered_clean, artifacts.route
                                    )
                                provider_diagnostics["fallback_used"] = True
                                provider_diagnostics["fallback_mode"] = (
                                    "same_provider_non_stream_recovery"
                                    if recovered_clean != artifacts.fallback_answer.strip()
                                    else "conservative_local_answer"
                                )
                                provider_diagnostics["post_stream_repair_used"] = True
                                provider_diagnostics["partial_visible_content_before_fallback"] = bool(streamed_answer)
                                provider_diagnostics["repair_reason"] = (
                                    "alignment_drift"
                                    if needs_alignment_repair
                                    else "stream_incomplete_or_length_capped"
                                )
            except Exception as exc:
                if isinstance(exc, AssistantProviderStreamError):
                    provider_diagnostics = dict(exc.diagnostics or {})
                    provider_diagnostics.setdefault("classification", exc.classification)
                    provider_error = f"{exc.classification}: {exc}"
                else:
                    provider_error = f"{type(exc).__name__}: {exc}"
                    provider_diagnostics = {
                        "classification": "unexpected_stream_error",
                        "error": provider_error,
                        "provider_model": provider_model,
                        "route": artifacts.route,
                    }
                yield sse_event(
                    "tool_status",
                    {
                        "tool_name": "assistant_model_stream",
                        "status": "fallback",
                        "message": "正在基于已确认的文档证据继续整理回答。",
                        "detail": provider_error,
                    },
                )
                recovered_answer = ""
                if not answer_text_parts:
                    recovered_answer = await self._complete_answer_text(
                        route=artifacts.route,
                        user_message=user_message,
                        summary_text=summary_text,
                        history=history,
                        answer_context=artifacts.answer_context,
                        fallback=artifacts.fallback_answer,
                        max_tokens=route_max_tokens,
                    )
                fallback_mode = "conservative_local_answer"
                if recovered_answer.strip() and recovered_answer.strip() != artifacts.fallback_answer.strip():
                    fallback_mode = "same_provider_non_stream_recovery"
                fallback = self._polish_user_visible_answer(
                    recovered_answer.strip()
                    or self._provider_fallback_text(
                        artifacts.fallback_answer,
                        partial_answer_exists=bool(answer_text_parts),
                    ),
                    artifacts.route,
                )
                provider_diagnostics["fallback_used"] = True
                provider_diagnostics["fallback_mode"] = fallback_mode
                provider_diagnostics["partial_visible_content_before_fallback"] = bool(answer_text_parts)
                for chunk in chunk_text(fallback, chunk_size=72):
                    answer_text_parts.append(chunk)
                    yield sse_event("assistant_delta", {"text": chunk})

        provider_diagnostics.setdefault("prompt_version", self._prompt_version)
        provider_diagnostics.setdefault("max_tokens_budget", route_max_tokens)

        if messages and (
            self._stream_debug_always
            or str(provider_diagnostics.get("classification") or "").strip().lower() != "success"
            or bool(provider_diagnostics.get("post_stream_repair_used"))
        ):
            self._write_stream_debug_artifact(
                assistant_message_id=assistant_message_id,
                route=artifacts.route,
                diagnostics=provider_diagnostics,
                messages=messages,
            )

        if provider_error:
            error_label = str(provider_diagnostics.get("classification") or "provider_error")
            artifacts.warnings.append(f"assistant_provider_fallback:{error_label}:{provider_error}")

        user_visible_warnings = self._filter_user_visible_warnings(artifacts.warnings)

        final_answer = self._polish_user_visible_answer(
            final_answer_override or "".join(answer_text_parts).strip() or artifacts.fallback_answer,
            artifacts.route,
        )
        await self._storage.save_assistant_message(
            session_id=session_id,
            message_id=assistant_message_id,
            role="assistant",
            message_type="assistant_text",
            content=final_answer,
            payload={
                "route": artifacts.route,
                "citations": artifacts.citations,
                "current_object_lock": artifacts.current_object_lock or {},
                "action_preview": artifacts.action_preview or {},
                "warnings": artifacts.warnings,
                "user_visible_warnings": user_visible_warnings,
                "provider_diagnostics": provider_diagnostics,
                "prompt_version": self._prompt_version,
            },
        )
        await self._storage.upsert_assistant_session(
            session_id=session_id,
            file_hash=payload.document.file_hash,
            file_name=payload.document.file_name,
            summary_text=summary_text,
            current_object_lock=artifacts.current_object_lock or current_lock or {},
            metadata={"track": payload.document.track, "route": artifacts.route},
        )
        yield sse_event(
            "assistant_done",
            {
                "session_id": session_id,
                "assistant_message_id": assistant_message_id,
                "route": artifacts.route,
                "answer": final_answer,
                "warnings": user_visible_warnings,
                "current_object_lock": artifacts.current_object_lock or {},
                "citations": artifacts.citations,
                "action_preview": artifacts.action_preview or {},
                "provider_diagnostics": provider_diagnostics,
                "prompt_version": self._prompt_version,
            },
        )

    async def _build_turn_artifacts_safe(
        self,
        *,
        document: DocumentExtractionResponse,
        summary_text: str,
        user_message: str,
        top_k: int,
        current_object_lock: Optional[Dict[str, Any]],
        extraction_payload: Dict[str, Any],
    ) -> TurnArtifacts:
        try:
            return await self._build_turn_artifacts(
                document=document,
                summary_text=summary_text,
                user_message=user_message,
                top_k=top_k,
                current_object_lock=current_object_lock,
                extraction_payload=extraction_payload,
            )
        except Exception as exc:
            warning = f"assistant_context_fallback:{type(exc).__name__}: {exc}"
            artifacts = TurnArtifacts(
                route="clarification_needed",
                warnings=[warning],
                current_object_lock=dict(current_object_lock or {}) or None,
                tool_events=[
                    {
                        "tool_name": "build_turn_artifacts",
                        "status": "fallback",
                        "message": "本轮上下文构建异常，已切换到保守回答模式。",
                        "detail": warning,
                        "output": {
                            "route": "clarification_needed",
                        },
                    }
                ],
            )
            try:
                overview = build_document_overview(
                    document=document,
                    payload=extraction_payload,
                    summary_text=summary_text,
                    current_object_lock=current_object_lock,
                )
                artifacts.route = "document_summary"
                artifacts.answer_context = overview
                artifacts.fallback_answer = fallback_answer("document_summary", overview)
            except Exception:
                artifacts.answer_context = {
                    "summary_text": summary_text,
                    "matched_fields": [],
                    "matched_trace_hits_count": 0,
                }
                artifacts.fallback_answer = (
                    "当前这轮回答在组织上下文时发生异常。"
                    "我已经切换到保守模式，避免流式中断。"
                    "你可以直接重试刚才的问题，或指定字段名、表格、行号、图片对象继续提问。"
                )
            return artifacts

    @staticmethod
    def _provider_fallback_text(base_fallback: str, *, partial_answer_exists: bool) -> str:
        fallback = str(base_fallback or "").strip() or "当前无法生成更详细的模型回答，我先返回基于结构化事实整理出的结果。"
        if not partial_answer_exists:
            return fallback
        return (
            "\n\n补充说明：下面这部分我会更保守一些，只基于已经确认的文档证据继续回答。\n"
            f"{fallback}"
        )

    async def _build_turn_artifacts(
        self,
        *,
        document: DocumentExtractionResponse,
        summary_text: str,
        user_message: str,
        top_k: int,
        current_object_lock: Optional[Dict[str, Any]],
        extraction_payload: Dict[str, Any],
    ) -> TurnArtifacts:
        route = classify_route(
            user_message=user_message,
            payload=extraction_payload,
            current_object_lock=current_object_lock,
        )
        artifacts = TurnArtifacts(route=route)
        if extraction_payload:
            artifacts.tool_events.append(
                {
                    "tool_name": "load_extraction_payload",
                    "status": "done",
                    "message": "已加载当前文档的结构化上下文",
                    "detail": f"tables={len(extraction_payload.get('tables', []) or [])}, figures={len(extraction_payload.get('figures', []) or [])}",
                    "output": {
                        "table_count": len(extraction_payload.get("tables", []) or []),
                        "figure_count": len(extraction_payload.get("figures", []) or []),
                    },
                }
            )

        if route == "table_lookup":
            started = time.perf_counter()
            assessment = assess_table_lookup(
                document=document,
                payload=extraction_payload,
                user_message=user_message,
                current_object_lock=current_object_lock,
            )
            result = assessment if bool(assessment.get("resolved")) else None
            artifacts.tool_events.append(
                {
                    "tool_name": "locate_table_cells",
                    "status": "done" if result else ("clarify" if assessment.get("candidate_rows") else "empty"),
                    "message": "已完成表格行列定位" if result else "当前没有稳定定位到目标表格行",
                    "detail": str((result or {}).get("table_id") or ""),
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "output": {
                        "found": bool(result),
                        "table_id": str((result or {}).get("table_id") or ""),
                        "lock_quality": str(assessment.get("lock_quality") or ""),
                        "candidate_count": len(assessment.get("candidate_rows") or []),
                    },
                }
            )
            if result:
                artifacts.citations = [result["citation"]]
                artifacts.current_object_lock = result["current_object_lock"]
                artifacts.answer_context = dict(result)
                # Stable row-grounded answers are already complete and auditable from structured facts.
                # Returning them immediately avoids letting model latency block a straightforward lookup.
                artifacts.prefer_fallback_only = True
                artifacts.fallback_answer = fallback_answer(route, artifacts.answer_context)
                return artifacts
            artifacts.warnings.append("当前未稳定定位到目标表格行。")
            artifacts.route = "clarification_needed"
            artifacts.answer_context = {
                "clarification_reason": str(assessment.get("clarification_reason") or "weak_row_grounding"),
                "candidate_rows": list(assessment.get("candidate_rows") or [])[:3],
                "missing_anchor_terms": list(assessment.get("missing_anchor_terms") or [])[:4],
                "lock_quality": str(assessment.get("lock_quality") or ""),
                "document_overview": build_document_overview(
                    document=document,
                    payload=extraction_payload,
                    summary_text=summary_text,
                    current_object_lock=current_object_lock,
                ),
                "query": user_message,
            }
            artifacts.prefer_fallback_only = True
            artifacts.fallback_answer = fallback_answer(artifacts.route, artifacts.answer_context)
            return artifacts

        if route in {"figure_overview", "figure_value_read"}:
            started = time.perf_counter()
            user_message_lower = user_message.lower()
            figures = select_figures(
                document=document,
                payload=extraction_payload,
                user_message=user_message,
                top_k=max(1, min(top_k, 8)),
            )
            citations = build_figure_citations(document, figures)
            artifacts.tool_events.append(
                {
                    "tool_name": "read_figures" if route == "figure_overview" else "inspect_figure",
                    "status": "done" if citations else "empty",
                    "message": "已整理图表对象信息" if citations else "当前没有拿到稳定的图表对象信息",
                    "detail": f"count={len(citations)}",
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                    "output": {"figure_count": len(citations)},
                }
            )
            figures_for_model: List[Dict[str, Any]] = []
            for citation in citations:
                payload_json = citation.get("payload") if isinstance(citation.get("payload"), dict) else {}
                figures_for_model.append(
                    {
                        "figure_id": str(payload_json.get("figure_id") or citation.get("object_id") or ""),
                        "page": payload_json.get("page") or citation.get("page"),
                        "caption": str(payload_json.get("caption") or citation.get("title") or ""),
                        "figure_type": str(payload_json.get("figure_type") or ""),
                        "key_points": list(payload_json.get("key_points") or [])[:4],
                        "dataframe_rows": list(payload_json.get("dataframe_rows") or [])[:4],
                        "content_modes": list(payload_json.get("content_modes") or [])[:4],
                    }
                )
            fallback_fields: List[Dict[str, Any]] = []
            fallback_trace_hits: List[Dict[str, Any]] = []
            fallback_tables: List[Dict[str, Any]] = []
            current_ocr_lock = (
                current_object_lock
                if current_object_lock and str(current_object_lock.get("lock_type") or "").strip().lower() == "ocr_fact_group"
                else None
            )
            current_ocr_metadata = current_ocr_lock.get("metadata") if current_ocr_lock and isinstance(current_ocr_lock.get("metadata"), dict) else {}
            if not figures_for_model:
                if isinstance(current_ocr_metadata.get("fact_tables"), list):
                    fallback_tables = list(current_ocr_metadata.get("fact_tables") or [])[:2]
                if isinstance(current_ocr_metadata.get("fact_fields"), list):
                    fallback_fields = list(current_ocr_metadata.get("fact_fields") or [])[:4]
                if not fallback_tables:
                    fallback_tables = build_table_overview_context(
                        select_tables(extraction_payload, user_message, top_k=2),
                        max_rows=3,
                        max_cells=5,
                    )
                if not fallback_fields:
                    fallback_fields = match_fields(document, user_message, top_k=4)
                    fallback_trace_hits = collect_trace_hits(document, fallback_fields, user_message, top_k=8)
                    fallback_fields = enrich_matched_fields_with_trace_hits(fallback_fields, fallback_trace_hits)
                if not fallback_fields and fallback_tables:
                    fallback_fields = build_field_facts_from_table_overviews(fallback_tables, max_items=6)
                artifacts.matched_fields = fallback_fields
                artifacts.matched_trace_hits = fallback_trace_hits
            recognition_tier = (
                "figure"
                if figures_for_model
                else ("ocr_table_only" if fallback_tables else ("ocr_field_only" if fallback_fields else "none"))
            )
            artifacts.citations = (
                citations
                or build_table_overview_citations(document, fallback_tables)
                or build_field_citations(fallback_fields, fallback_trace_hits)
            )
            artifacts.answer_context = {
                "figures": figures_for_model,
                "figure_count": len(figures_for_model),
                "summary_text": summary_text,
                "fallback_tables": fallback_tables[:2],
                "fallback_fields": fallback_fields[:4],
                "recognition_tier": recognition_tier,
            }
            if figures_for_model:
                first = figures_for_model[0]
                artifacts.current_object_lock = {
                    "lock_type": "figure",
                    "lock_quality": "stable_lock",
                    "object_id": str(first.get("figure_id") or ""),
                    "label": str(first.get("caption") or first.get("figure_id") or "图表"),
                    "page": first.get("page"),
                    "ref_id": str((citations[0] or {}).get("ref_id") or "") if citations else None,
                    "metadata": {"figure_type": str(first.get("figure_type") or "")},
                }
            else:
                artifacts.current_object_lock = build_ocr_fact_group_lock(
                    fallback_tables=fallback_tables[:2],
                    fallback_fields=fallback_fields[:4],
                    recognition_tier=recognition_tier,
                    current_object_lock=current_object_lock,
                )
                artifacts.warnings.append("当前只拿到了较弱的图表线索，尚未形成稳定的 figure 级结果。")
            if (
                not figures_for_model
                and fallback_fields
                and any(token in user_message_lower for token in ("字段级", "字段事实", "ref_id", "页码", "page", "写明", "列出"))
            ):
                artifacts.answer_context["prefer_field_facts"] = True
                artifacts.prefer_fallback_only = True
            artifacts.fallback_answer = fallback_answer(route, artifacts.answer_context)
            return artifacts

        if route == "document_summary":
            overview = build_document_overview(
                document=document,
                payload=extraction_payload,
                summary_text=summary_text,
                current_object_lock=current_object_lock,
            )
            artifacts.tool_events.append(
                {
                    "tool_name": "summarize_document_context",
                    "status": "done",
                    "message": "已整理文档概览上下文",
                    "detail": f"fields={overview.get('field_count', 0)}, tables={overview.get('table_count', 0)}, figures={overview.get('figure_count', 0)}",
                }
            )
            artifacts.answer_context = {**overview, "user_question": user_message}
            artifacts.prefer_fallback_only = self._prefer_local_document_summary_answer(user_message)
            artifacts.fallback_answer = fallback_answer(route, artifacts.answer_context)
            return artifacts

        if route == "knowledge_explain":
            overview = build_document_overview(
                document=document,
                payload=extraction_payload,
                summary_text=summary_text,
                current_object_lock=current_object_lock,
            )
            artifacts.tool_events.append(
                {
                    "tool_name": "prepare_knowledge_context",
                    "status": "done",
                    "message": "已整理知识解释所需的文档上下文",
                    "detail": f"fields={overview.get('field_count', 0)}, tables={overview.get('table_count', 0)}, figures={overview.get('figure_count', 0)}",
                    "output": {
                        "field_count": int(overview.get("field_count", 0) or 0),
                        "table_count": int(overview.get("table_count", 0) or 0),
                        "figure_count": int(overview.get("figure_count", 0) or 0),
                    },
                }
            )
            artifacts.answer_context = {
                "user_question": user_message,
                "summary_text": summary_text,
                "document_overview": overview,
            }
            artifacts.prefer_fallback_only = self._prefer_local_knowledge_answer(user_message)
            artifacts.fallback_answer = fallback_answer(route, artifacts.answer_context)
            return artifacts

        if route == "web_research":
            overview = build_document_overview(
                document=document,
                payload=extraction_payload,
                summary_text=summary_text,
                current_object_lock=current_object_lock,
            )
            artifacts.tool_events.append(
                {
                    "tool_name": "prepare_web_research_context",
                    "status": "fallback",
                    "message": "当前会话没有实时联网结果，已切换为保守回答模式",
                    "detail": "no_live_web_results",
                    "output": {
                        "live_web_result_available": False,
                    },
                }
            )
            artifacts.answer_context = {
                "user_question": user_message,
                "summary_text": summary_text,
                "document_overview": overview,
                "live_web_result_available": False,
                "web_results": [],
            }
            artifacts.prefer_fallback_only = True
            artifacts.fallback_answer = fallback_answer(route, artifacts.answer_context)
            return artifacts

        matched_fields = match_fields(document, user_message, top_k=max(1, min(top_k, 8)))
        matched_trace_hits = collect_trace_hits(document, matched_fields, user_message, top_k=max(6, top_k))
        matched_fields = enrich_matched_fields_with_trace_hits(matched_fields, matched_trace_hits)
        artifacts.tool_events.append(
            {
                "tool_name": "match_fields",
                "status": "done" if matched_fields else "empty",
                "message": "已完成字段与溯源片段匹配" if matched_fields else "当前没有稳定命中的目标字段",
                "detail": f"field_count={len(matched_fields)}, trace_count={len(matched_trace_hits)}",
                "output": {"field_count": len(matched_fields), "trace_count": len(matched_trace_hits)},
            }
        )
        artifacts.matched_fields = matched_fields
        artifacts.matched_trace_hits = matched_trace_hits
        artifacts.citations = build_field_citations(matched_fields, matched_trace_hits)
        if route == "database_action":
            artifacts.action_preview = build_action_preview(
                user_message,
                document,
                matched_fields,
                payload=extraction_payload,
                current_object_lock=current_object_lock,
            )
            preview_payload = (
                artifacts.action_preview.get("payload")
                if isinstance(artifacts.action_preview, dict) and isinstance(artifacts.action_preview.get("payload"), dict)
                else {}
            )
            preview_status = str(preview_payload.get("preview_status") or "ready")
            preview_lock_quality = str(preview_payload.get("lock_quality") or "").strip().lower()
            preview_citations = build_action_preview_citations(artifacts.action_preview)
            if (
                preview_status == "ready"
                and preview_lock_quality == "stable_lock"
                and preview_payload.get("focus_scope") == "table_row"
            ):
                artifacts.current_object_lock = {
                    "lock_type": "table_row",
                    "lock_quality": "stable_lock",
                    "object_id": str(preview_payload.get("table_id") or ""),
                    "label": f"{str(preview_payload.get('table_id') or '表格')} 第{preview_payload.get('row_index') or '?'}行",
                    "page": preview_payload.get("page"),
                    "ref_id": str((preview_citations[0] or {}).get("ref_id") or "") if preview_citations else None,
                    "table_id": str(preview_payload.get("table_id") or ""),
                    "row_index": preview_payload.get("row_index"),
                    "source_row_index": preview_payload.get("source_row_index"),
                    "metadata": {
                        "header": str(((preview_citations[0] or {}).get("title") or "")) if preview_citations else "",
                    },
                }
            elif (
                preview_status == "ready"
                and preview_lock_quality == "stable_lock"
                and preview_payload.get("focus_scope") == "ocr_fact_group"
                and isinstance(preview_payload.get("focus_lock"), dict)
            ):
                artifacts.current_object_lock = dict(preview_payload.get("focus_lock") or {})
            if preview_status == "blocked":
                artifacts.prefer_fallback_only = True
            artifacts.citations = preview_citations or artifacts.citations
            artifacts.answer_context = {
                "action_preview": artifacts.action_preview,
                "matched_fields": matched_fields[:6],
                "summary_text": summary_text,
            }
            artifacts.fallback_answer = fallback_answer(route, artifacts.answer_context)
            return artifacts

        if matched_fields:
            first = matched_fields[0]
            artifacts.current_object_lock = {
                "lock_type": "field",
                "lock_quality": "stable_lock",
                "object_id": str(first.get("field_name") or ""),
                "label": str(first.get("label") or first.get("field_name") or "字段"),
                "page": first.get("page"),
                "ref_id": first.get("source_ref_id"),
                "metadata": {},
            }
        else:
            overview = build_document_overview(document=document, payload=extraction_payload, summary_text=summary_text)
            artifacts.warnings.append("当前没有稳定匹配到字段，我改为基于整体文档上下文来组织回答。")
            artifacts.route = "clarification_needed"
            artifacts.answer_context = {
                "matched_fields": [],
                "matched_trace_hits_count": len(matched_trace_hits),
                "document_overview": overview,
            }
            artifacts.fallback_answer = fallback_answer(artifacts.route, artifacts.answer_context)
            return artifacts

        artifacts.answer_context = {
            "matched_fields": matched_fields[:6],
            "matched_trace_hits_count": len(matched_trace_hits),
            "summary_text": summary_text,
        }
        artifacts.fallback_answer = fallback_answer(route, artifacts.answer_context)
        return artifacts

    async def _complete_answer_text(
        self,
        *,
        route: str,
        user_message: str,
        summary_text: str,
        history: List[Dict[str, Any]],
        answer_context: Dict[str, Any],
        fallback: str,
        max_tokens: Optional[int] = None,
    ) -> str:
        answer, _diagnostics = await self._complete_answer_with_diagnostics(
            route=route,
            user_message=user_message,
            summary_text=summary_text,
            history=history,
            answer_context=answer_context,
            fallback=fallback,
            max_tokens=max_tokens,
        )
        return answer

    async def _complete_answer_with_diagnostics(
        self,
        *,
        route: str,
        user_message: str,
        summary_text: str,
        history: List[Dict[str, Any]],
        answer_context: Dict[str, Any],
        fallback: str,
        max_tokens: Optional[int] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        delivery_mode: str = "complete",
    ) -> tuple[str, Dict[str, Any]]:
        max_tokens_budget = max(600, int(max_tokens or self._max_tokens))
        reasoning_effort = self._reasoning_effort(route)
        provider_model = str(getattr(self._provider, "model", "") or self._model)
        prepared_messages = messages or self._build_prompt_messages(
            route=route,
            user_message=user_message,
            summary_text=summary_text,
            history=history,
            answer_context=answer_context,
        )
        diagnostics: Dict[str, Any] = {
            "provider_model": provider_model,
            "prompt_version": self._prompt_version,
            "classification": "",
            "delivery_mode": delivery_mode,
            "message_count": len(prepared_messages),
            "input_chars": sum(len(str(item.get("content") or "")) for item in prepared_messages if isinstance(item, dict)),
            "max_tokens_budget": max_tokens_budget,
            "reasoning_effort": reasoning_effort or "",
            "finish_reason": "",
            "visible_chars": 0,
            "fallback_used": False,
        }
        started_at = time.perf_counter()

        def _finalize(classification: str, *, error: str = "") -> Dict[str, Any]:
            diagnostics["classification"] = str(classification or "").strip() or "unknown"
            diagnostics["error"] = str(error or "")
            diagnostics["total_duration_ms"] = int((time.perf_counter() - started_at) * 1000)
            return dict(diagnostics)

        if not self._provider or not self._provider.configured:
            diagnostics["fallback_used"] = True
            diagnostics["fallback_mode"] = "conservative_local_answer"
            return fallback, _finalize("provider_not_configured")

        try:
            result = await asyncio.to_thread(
                self._provider.complete,
                messages=prepared_messages,
                temperature=self._temperature,
                max_tokens=max_tokens_budget,
                reasoning_effort=reasoning_effort,
            )
            content = str(getattr(result, "content", "") or "").strip()
            finish_reason = str(getattr(result, "finish_reason", "") or "").strip()
            diagnostics["finish_reason"] = finish_reason
            if not content:
                diagnostics["fallback_used"] = True
                diagnostics["fallback_mode"] = "conservative_local_answer"
                diagnostics["visible_chars"] = len(fallback)
                return fallback, _finalize("complete_empty_fallback")
            needs_alignment_repair = self._answer_needs_alignment_repair(route, user_message, content)
            if self._should_retry_completed_answer(
                route=route,
                answer_text=content,
                finish_reason=finish_reason,
            ) or needs_alignment_repair:
                diagnostics["repair_attempted"] = True
                diagnostics["repair_trigger"] = (
                    "alignment_drift" if needs_alignment_repair else "length_capped_or_incomplete"
                )
                repair_messages = self._build_completion_repair_messages(route, prepared_messages)
                alignment_instruction = self._alignment_repair_instruction(route, user_message)
                if alignment_instruction:
                    repair_messages = list(repair_messages) + [{"role": "user", "content": alignment_instruction}]
                repair_max_tokens = self._stream_recovery_max_tokens(route, max_tokens_budget)
                diagnostics["repair_max_tokens_budget"] = repair_max_tokens
                try:
                    repair_result = await asyncio.to_thread(
                        self._provider.complete,
                        messages=repair_messages,
                        temperature=self._temperature,
                        max_tokens=repair_max_tokens,
                        reasoning_effort="minimal",
                    )
                    repair_content = str(getattr(repair_result, "content", "") or "").strip()
                    repair_finish_reason = str(getattr(repair_result, "finish_reason", "") or "").strip()
                    diagnostics["repair_finish_reason"] = repair_finish_reason
                    if repair_content and not self._should_retry_completed_answer(
                        route=route,
                        answer_text=repair_content,
                        finish_reason=repair_finish_reason,
                    ) and not self._answer_needs_alignment_repair(route, user_message, repair_content):
                        diagnostics["finish_reason"] = repair_finish_reason or finish_reason
                        diagnostics["visible_chars"] = len(repair_content)
                        diagnostics["repair_used"] = True
                        return repair_content, _finalize("success_after_compact_retry")
                    diagnostics["repair_used"] = False
                except Exception as repair_exc:
                    diagnostics["repair_used"] = False
                    diagnostics["repair_error"] = f"{type(repair_exc).__name__}: {repair_exc}"
                diagnostics["fallback_used"] = True
                diagnostics["fallback_mode"] = "conservative_local_answer"
                diagnostics["visible_chars"] = len(fallback)
                return fallback, _finalize("complete_incomplete_fallback")
            final_answer = content or fallback
            diagnostics["visible_chars"] = len(final_answer)
            return final_answer, _finalize("success")
        except Exception as exc:
            diagnostics["fallback_used"] = True
            diagnostics["fallback_mode"] = "conservative_local_answer"
            diagnostics["visible_chars"] = len(fallback)
            error_text = f"{type(exc).__name__}: {exc}"
            return fallback, _finalize("complete_error", error=error_text)

    async def _continue_streamed_answer_with_diagnostics(
        self,
        *,
        route: str,
        prepared_messages: List[Dict[str, Any]],
        partial_answer: str,
        max_tokens: Optional[int] = None,
    ) -> tuple[str, Dict[str, Any]]:
        max_tokens_budget = max(400, int(max_tokens or self._max_tokens))
        provider_model = str(getattr(self._provider, "model", "") or self._model)
        partial_tail = self._truncate_prompt_tail_text(partial_answer, 1400)
        continuation_messages = self._build_stream_repair_messages(route, prepared_messages, partial_tail)
        diagnostics: Dict[str, Any] = {
            "provider_model": provider_model,
            "prompt_version": self._prompt_version,
            "classification": "",
            "delivery_mode": "stream_repair_continuation",
            "message_count": len(continuation_messages),
            "input_chars": sum(
                len(str(item.get("content") or "")) for item in continuation_messages if isinstance(item, dict)
            ),
            "max_tokens_budget": max_tokens_budget,
            "partial_answer_chars": len(str(partial_answer or "").strip()),
            "finish_reason": "",
            "visible_chars": 0,
            "fallback_used": False,
        }
        started_at = time.perf_counter()

        def _finalize(classification: str, *, error: str = "") -> Dict[str, Any]:
            diagnostics["classification"] = str(classification or "").strip() or "unknown"
            diagnostics["error"] = str(error or "")
            diagnostics["total_duration_ms"] = int((time.perf_counter() - started_at) * 1000)
            return dict(diagnostics)

        if not self._provider or not self._provider.configured:
            return "", _finalize("provider_not_configured")

        try:
            result = await asyncio.to_thread(
                self._provider.complete,
                messages=continuation_messages,
                temperature=self._temperature,
                max_tokens=max_tokens_budget,
                reasoning_effort="minimal",
            )
            content = str(getattr(result, "content", "") or "").strip()
            finish_reason = str(getattr(result, "finish_reason", "") or "").strip()
            diagnostics["finish_reason"] = finish_reason
            deduped = self._dedupe_stream_repair_text(partial_answer, content)
            diagnostics["visible_chars"] = len(deduped)
            if not deduped:
                return "", _finalize("empty_or_duplicate")
            return deduped, _finalize("success")
        except Exception as exc:
            error_text = f"{type(exc).__name__}: {exc}"
            return "", _finalize("repair_error", error=error_text)

    async def _stream_provider_text(
        self,
        messages: List[Dict[str, Any]],
        *,
        diagnostics: Optional[Dict[str, Any]] = None,
        max_tokens: Optional[int] = None,
        route: str = "",
    ) -> AsyncIterator[str]:
        if not self._provider or not self._provider.configured:
            raise RuntimeError("assistant provider is not configured")

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        started_at = time.perf_counter()
        max_tokens_budget = max(600, int(max_tokens or self._max_tokens))
        timeout_profile = self._stream_timeout_profile(route)
        reasoning_effort = self._reasoning_effort(route)

        diag: Dict[str, Any] = {
            "provider_model": str(getattr(self._provider, "model", "") or self._model),
            "prompt_version": self._prompt_version,
            "classification": "",
            "message_count": len(messages),
            "input_chars": sum(len(str(item.get("content") or "")) for item in messages if isinstance(item, dict)),
            "max_tokens_budget": max_tokens_budget,
            "connect_timeout_sec": timeout_profile["connect_timeout_sec"],
            "first_frame_timeout_sec": timeout_profile["first_frame_timeout_sec"],
            "first_visible_timeout_sec": timeout_profile["first_visible_timeout_sec"],
            "stream_idle_timeout_sec": timeout_profile["stream_idle_timeout_sec"],
            "reasoning_effort": reasoning_effort or "",
            "frame_count": 0,
            "semantic_event_count": 0,
            "content_event_count": 0,
            "reasoning_chars": 0,
            "visible_chars": 0,
            "finish_reason": "",
            "fallback_used": False,
        }

        def _finalize(classification: str, *, error: str = "") -> Dict[str, Any]:
            diag["classification"] = str(classification or "").strip() or "unknown"
            diag["error"] = str(error or "")
            diag["total_duration_ms"] = int((time.perf_counter() - started_at) * 1000)
            return dict(diag)

        def _worker() -> None:
            try:
                for event in self._provider.stream_events(
                    messages=messages,
                    temperature=self._temperature,
                    max_tokens=max_tokens_budget,
                    reasoning_effort=reasoning_effort,
                ):
                    asyncio.run_coroutine_threadsafe(queue.put(("event", event)), loop)
            except Exception as exc:
                asyncio.run_coroutine_threadsafe(queue.put(("error", f"{type(exc).__name__}: {exc}")), loop)
            finally:
                asyncio.run_coroutine_threadsafe(queue.put(("done", "")), loop)

        threading.Thread(target=_worker, daemon=True).start()

        stream_opened = False
        first_frame_received = False
        visible_content_received = False
        first_frame_at: Optional[float] = None
        first_visible_deadline_at: Optional[float] = None
        while True:
            now = time.perf_counter()
            if not stream_opened:
                timeout_sec = timeout_profile["connect_timeout_sec"]
                timeout_label = "connect_timeout"
            elif not first_frame_received:
                timeout_sec = timeout_profile["first_frame_timeout_sec"]
                timeout_label = "first_frame_timeout"
            elif not visible_content_received:
                if first_visible_deadline_at is None and first_frame_at is not None:
                    first_visible_deadline_at = first_frame_at + timeout_profile["first_visible_timeout_sec"]
                remaining_visible = (
                    max(0.05, first_visible_deadline_at - now)
                    if first_visible_deadline_at is not None
                    else timeout_profile["first_visible_timeout_sec"]
                )
                timeout_sec = remaining_visible
                timeout_label = "first_visible_content_timeout"
            else:
                timeout_sec = timeout_profile["stream_idle_timeout_sec"]
                timeout_label = "stream_idle_timeout"
            try:
                kind, payload = await asyncio.wait_for(queue.get(), timeout=timeout_sec)
            except asyncio.TimeoutError as exc:
                diagnostics_payload = _finalize(timeout_label, error=f"{timeout_label} after {timeout_sec:.1f}s")
                if diagnostics is not None:
                    diagnostics.clear()
                    diagnostics.update(diagnostics_payload)
                raise AssistantProviderStreamError(
                    f"assistant provider {timeout_label} after {timeout_sec:.1f}s",
                    classification=timeout_label,
                    diagnostics=diagnostics_payload,
                ) from exc
            if kind == "event":
                event = payload if isinstance(payload, ChatStreamEvent) else None
                if event is None:
                    continue
                if event.event == "stream_opened":
                    if not stream_opened:
                        stream_opened = True
                        diag["time_to_connect_ms"] = int((time.perf_counter() - started_at) * 1000)
                    continue
                if event.event == "frame_received":
                    diag["frame_count"] = int(diag.get("frame_count", 0) or 0) + 1
                    if not first_frame_received:
                        first_frame_received = True
                        first_frame_at = time.perf_counter()
                        diag["time_to_first_frame_ms"] = int((first_frame_at - started_at) * 1000)
                    continue
                if event.event == "reasoning_delta":
                    diag["semantic_event_count"] = int(diag.get("semantic_event_count", 0) or 0) + 1
                    diag["reasoning_chars"] = int(diag.get("reasoning_chars", 0) or 0) + len(event.reasoning_text or "")
                    if "time_to_first_semantic_ms" not in diag:
                        diag["time_to_first_semantic_ms"] = int((time.perf_counter() - started_at) * 1000)
                    continue
                if event.event == "content_delta":
                    diag["content_event_count"] = int(diag.get("content_event_count", 0) or 0) + 1
                    diag["visible_chars"] = int(diag.get("visible_chars", 0) or 0) + len(event.text or "")
                    if "time_to_first_semantic_ms" not in diag:
                        diag["time_to_first_semantic_ms"] = int((time.perf_counter() - started_at) * 1000)
                    if not visible_content_received:
                        visible_content_received = True
                        diag["time_to_first_visible_content_ms"] = int((time.perf_counter() - started_at) * 1000)
                    if event.text:
                        yield event.text
                    continue
                if event.event == "finish":
                    finish_reason = str(event.finish_reason or "").strip()
                    if finish_reason and (not str(diag.get("finish_reason") or "").strip() or finish_reason.lower() != "done"):
                        diag["finish_reason"] = finish_reason
                continue
            if kind == "error":
                error_text = str(payload or "").strip()
                classification = self._provider_error_classification(error_text, stream_opened=stream_opened)
                diagnostics_payload = _finalize(classification, error=error_text)
                if diagnostics is not None:
                    diagnostics.clear()
                    diagnostics.update(diagnostics_payload)
                raise AssistantProviderStreamError(
                    error_text,
                    classification=classification,
                    diagnostics=diagnostics_payload,
                )
            break

        if not visible_content_received:
            finish_reason = str(diag.get("finish_reason") or "").strip().lower()
            classification = "filtered_completion" if finish_reason == "content_filter" else "empty_completion"
            message = (
                "assistant provider finished without visible content"
                if classification == "empty_completion"
                else "assistant provider finished with content filtering before visible content"
            )
            diagnostics_payload = _finalize(classification, error=message)
            if diagnostics is not None:
                diagnostics.clear()
                diagnostics.update(diagnostics_payload)
            raise AssistantProviderStreamError(
                message,
                classification=classification,
                diagnostics=diagnostics_payload,
            )

        diagnostics_payload = _finalize("success")
        if diagnostics is not None:
            diagnostics.clear()
            diagnostics.update(diagnostics_payload)

    @staticmethod
    def _to_session_message(item: Dict[str, Any]) -> AssistantSessionMessage:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        return AssistantSessionMessage(
            message_id=str(item.get("message_id") or ""),
            role=str(item.get("role") or ""),
            message_type=str(item.get("message_type") or "assistant_text"),
            content=str(item.get("content") or ""),
            payload=payload,
            created_at=str(item.get("created_at") or ""),
        )
