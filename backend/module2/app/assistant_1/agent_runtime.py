from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .config import Assistant1Settings
from .ingest_pipeline import Assistant1IngestPipeline
from .responses_provider import Assistant1ResponsesProvider, ResponsesFunctionCall
from .retrieval_pipeline import Assistant1RetrievalPipeline


@dataclass
class Assistant1ToolContext:
    default_file_hash: str = ""
    top_k: int = 5
    max_snippet_chars: int = 700


@dataclass(frozen=True)
class Assistant1ResponsePlan:
    use_tools: bool = True
    text_verbosity: str = "medium"
    max_output_tokens: int = 900
    reasoning_effort: str = "minimal"
    tool_names: tuple[str, ...] = ()


class Assistant1AgentRuntime:
    def __init__(self, settings: Assistant1Settings | None = None) -> None:
        self.settings = settings or Assistant1Settings.from_env()
        self.provider = Assistant1ResponsesProvider(self.settings)
        self.retrieval = Assistant1RetrievalPipeline(self.settings)
        self.ingest = Assistant1IngestPipeline(self.settings)

    def chat(
        self,
        user_message: str,
        *,
        file_hash: str = "",
        history: Optional[List[Dict[str, Any]]] = None,
        max_steps: int = 6,
        top_k: int = 5,
    ) -> Dict[str, Any]:
        question = str(user_message or "").strip()
        if not question:
            raise ValueError("user_message is required")
        if not self.provider.configured:
            raise RuntimeError("assistant_1 chat provider is not configured")

        context = Assistant1ToolContext(
            default_file_hash=str(file_hash or "").strip(),
            top_k=max(1, min(8, int(top_k or 5))),
        )
        response_plan = self._plan_response(
            user_message=question,
            default_file_hash=context.default_file_hash,
        )
        instructions = self._build_instructions(
            user_message=question,
            default_file_hash=context.default_file_hash,
            response_plan=response_plan,
        )
        input_messages = list(history or []) + [{"role": "user", "content": question}]
        tools = self._tool_definitions(response_plan.tool_names) if response_plan.use_tools else None

        response = self.provider.complete(
            messages=input_messages,
            instructions=instructions,
            tools=tools,
            tool_choice="auto",
            max_output_tokens=response_plan.max_output_tokens,
            reasoning_effort=response_plan.reasoning_effort,
            text_verbosity=response_plan.text_verbosity,
            metadata={
                "assistant_runtime": "assistant_1",
                "phase": "initial",
                "text_verbosity": response_plan.text_verbosity,
                "use_tools": str(response_plan.use_tools).lower(),
            },
        )

        tool_steps: List[Dict[str, Any]] = []
        final_response = response
        for step_index in range(max(1, int(max_steps or 1))):
            if not final_response.function_calls:
                break
            tool_outputs: List[Dict[str, Any]] = []
            executed_tools: List[Dict[str, Any]] = []
            for call in final_response.function_calls:
                result = self._execute_tool(call, context)
                executed_tools.append(
                    {
                        "tool_name": call.name,
                        "arguments": call.arguments,
                        "result_preview": self._tool_result_preview(result),
                    }
                )
                tool_outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )
            tool_steps.append(
                {
                    "step": step_index + 1,
                    "response_id": final_response.response_id,
                    "executed_tools": executed_tools,
                }
            )
            final_response = self.provider.complete(
                input_items=tool_outputs,
                previous_response_id=final_response.response_id,
                instructions=instructions,
                tools=tools,
                tool_choice="auto",
                max_output_tokens=response_plan.max_output_tokens,
                reasoning_effort=response_plan.reasoning_effort,
                text_verbosity=response_plan.text_verbosity,
                metadata={
                    "assistant_runtime": "assistant_1",
                    "phase": f"tool_step_{step_index + 1}",
                    "text_verbosity": response_plan.text_verbosity,
                    "use_tools": str(response_plan.use_tools).lower(),
                },
            )

        answer = str(final_response.output_text or "").strip()
        if not answer:
            if final_response.function_calls:
                answer = (
                    "我已经拿到工具结果了，但这一轮模型还没有把最终答复组织出来。"
                    "你可以让我继续追问，或者我也可以把现有结果整理成更直接的自然语言回答。"
                )
            else:
                answer = "这次没有拿到稳定的最终回答，你可以换个问法再试一次。"
        answer = self._cleanup_answer_text(answer)

        return {
            "answer": answer,
            "response_id": final_response.response_id,
            "status": final_response.status,
            "file_hash": context.default_file_hash,
            "tool_steps": tool_steps,
            "final_output_types": [
                str(item.get("type") or "")
                for item in final_response.raw.get("output", [])
                if isinstance(item, dict)
            ],
        }

    def _build_instructions(
        self,
        *,
        user_message: str,
        default_file_hash: str,
        response_plan: Assistant1ResponsePlan,
    ) -> str:
        blocks = [
            self._core_instruction_block(),
            self._session_context_block(default_file_hash=default_file_hash),
        ]
        turn_hint = self._turn_hint_block(
            user_message=user_message,
            default_file_hash=default_file_hash,
            response_plan=response_plan,
        )
        if turn_hint:
            blocks.append(turn_hint)
        return "\n\n".join(block.strip() for block in blocks if block and block.strip()).strip()

    @staticmethod
    def _core_instruction_block() -> str:
        lines = [
            "【角色】你是一个面向非结构化文档处理场景的信息提取任务助手，支持文档问答、字段抽取、表结构设计、数据入库建议和 NL2SQL 草案生成。",
            "【目标】先理解用户真正想解决的问题，再给出可信、自然、直接的中文回答。",
            "【文档问题】处理文档具体内容时，优先基于当前文档或已取得的证据回答；处理通用方法、方案设计或知识解释时，可以直接回答。",
            "【歧义处理】如果同一对象可能对应多条记录、多个时间点、多个版本或多个统计口径，不要猜测，也不要混成一个值。先点明差异，再分别说明，或请用户补充最关键的限定条件。",
            "【内部信息】不要暴露内部实现、工具调用、检索过程、系统字段或中间技术细节。",
            "【表达方式】默认用自然中文。先回答用户真正想知道的内容；简单问题短答，复杂问题再展开。只有当内容天然适合步骤、对比或清单时才使用列表，否则优先自然段。",
            "【格式服从】如果用户明确指定输出形式，比如一句话、JSON、SQL、表格或极简答复，就严格遵守。",
            "【信息不足】当依据不足时，明确说明不确定点，并给出最小必要的下一步。",
        ]
        return "\n".join(lines)

    @staticmethod
    def _session_context_block(*, default_file_hash: str) -> str:
        if default_file_hash:
            return "【当前上下文】当前会话已绑定一个默认文档。除非用户另有说明，可以把它视为默认目标。"
        return (
            "【当前上下文】当前会话未绑定默认文档。"
            "如果用户追问具体文档内容但没有给出文件线索，不要猜内容，先请他指定文件、粘贴文本或提供定位信息。"
        )

    def _turn_hint_block(
        self,
        *,
        user_message: str,
        default_file_hash: str,
        response_plan: Assistant1ResponsePlan,
    ) -> str:
        question = str(user_message or "").strip()
        has_default_file = bool(str(default_file_hash or "").strip())
        if self._is_strict_minimal_request(question):
            return "【本轮提示】用户明确限制了输出形式或长度，严格按要求作答即可。"
        if self._is_broad_document_question(question):
            return "【本轮提示】这是文档宽问题。如果涉及多个年份、版本或口径，请分别说明，不要合并成一个区间或单一结论。"
        if self._is_document_specific_question(question) and has_default_file:
            return "【本轮提示】这是文档具体问答。如果候选记录不唯一，或时间条件、对象条件不足，请先点明歧义再回答。"
        if self._is_document_specific_question(question) and not has_default_file:
            return "【本轮提示】这是文档具体问答，但当前没有默认文档。先让用户给出文件或定位信息。"
        if self._is_capability_question(question):
            return "【本轮提示】这是能力咨询。优先用自然段概括，不要主动展开成完整功能清单；先说现在能帮什么，再说还需要什么信息。"
        if self._is_general_method_question(question) and self._wants_detailed_answer(question):
            return "【本轮提示】这是方法咨询。可以适度展开，但保持自然、具体、可执行。"
        if response_plan.text_verbosity == "low":
            return "【本轮提示】用户更适合收到简洁回答。"
        return ""

    def _plan_response(
        self,
        *,
        user_message: str,
        default_file_hash: str,
    ) -> Assistant1ResponsePlan:
        question = str(user_message or "").strip()
        has_default_file = bool(str(default_file_hash or "").strip())
        wants_brief = self._wants_brief_answer(question)
        wants_detailed = self._wants_detailed_answer(question)
        strict_minimal = self._is_strict_minimal_request(question)
        capability_question = self._is_capability_question(question)
        general_method_question = self._is_general_method_question(question)
        document_question = self._is_document_specific_question(question)
        broad_document_question = self._is_broad_document_question(question)

        if strict_minimal:
            return Assistant1ResponsePlan(
                use_tools=False,
                text_verbosity="low",
                max_output_tokens=80,
                reasoning_effort="minimal",
                tool_names=(),
            )

        if document_question and not has_default_file:
            return Assistant1ResponsePlan(
                use_tools=False,
                text_verbosity="low",
                max_output_tokens=220,
                reasoning_effort="minimal",
                tool_names=(),
            )

        if capability_question and not has_default_file:
            return Assistant1ResponsePlan(
                use_tools=False,
                text_verbosity="medium" if wants_detailed else "low",
                max_output_tokens=320 if not wants_detailed else 560,
                reasoning_effort="minimal",
                tool_names=(),
            )

        if general_method_question and not document_question:
            return Assistant1ResponsePlan(
                use_tools=False,
                text_verbosity="medium" if wants_detailed else "medium",
                max_output_tokens=1000 if wants_detailed else 850,
                reasoning_effort="minimal",
                tool_names=(),
            )

        if document_question and has_default_file:
            if broad_document_question:
                return Assistant1ResponsePlan(
                    use_tools=True,
                    text_verbosity="low" if not wants_detailed else "medium",
                    max_output_tokens=750 if not wants_detailed else 1100,
                    reasoning_effort="minimal",
                    tool_names=("search_knowledge_base_grouped", "ingest_document"),
                )
            return Assistant1ResponsePlan(
                use_tools=True,
                text_verbosity="low" if wants_brief else "medium",
                max_output_tokens=700 if wants_brief else 1000,
                reasoning_effort="minimal",
                tool_names=("search_knowledge_base", "ingest_document"),
            )

        return Assistant1ResponsePlan(
            use_tools=False,
            text_verbosity="high" if wants_detailed else "low" if wants_brief else "medium",
            max_output_tokens=1400 if wants_detailed else 650 if wants_brief else 900,
            reasoning_effort="minimal",
            tool_names=(),
        )

    def _tool_definitions(self, tool_names: tuple[str, ...] = ()) -> List[Dict[str, Any]]:
        definitions = [
            {
                "type": "function",
                "name": "search_knowledge_base_grouped",
                "description": (
                    "Search the assistant_1 knowledge base and return evidence grouped by year/version when possible. "
                    "Prefer this for broad document questions like key points, risks, summaries, comparisons, trend explanations, or when multiple years or versions may be mixed together."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The exact user question or a focused retrieval query.",
                        },
                        "file_hash": {
                            "type": "string",
                            "description": "Optional target file hash. Omit it to use the current default file if available.",
                        },
                        "unit_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of unit types such as narrative_chunk, table_row, figure_overview.",
                        },
                        "top_k": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 8,
                            "description": "How many matches to retrieve.",
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "search_knowledge_base",
                "description": (
                    "Search the assistant_1 knowledge base for evidence from the current document or a specified file. "
                    "Use this before answering document-specific questions about text, fields, values, time points, tables, charts, figures, or page-level content."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The exact user question or a focused retrieval query.",
                        },
                        "file_hash": {
                            "type": "string",
                            "description": "Optional target file hash. Omit it to use the current default file if available.",
                        },
                        "unit_types": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional list of unit types such as narrative_chunk, table_row, figure_overview.",
                        },
                        "top_k": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 8,
                            "description": "How many matches to retrieve.",
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "ingest_document",
                "description": (
                    "Build and persist assistant_1 knowledge artifacts for a document file hash. "
                    "Use this when the user asks to index a file into the knowledge base, or when you need to prepare the current file before retrieval."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_hash": {
                            "type": "string",
                            "description": "Optional target file hash. Omit it to use the current default file if available.",
                        },
                        "persist": {
                            "type": "boolean",
                            "description": "Whether to generate embeddings and write them to PostgreSQL/pgvector.",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
        ]
        if not tool_names:
            return definitions
        allowed = {name for name in tool_names if name}
        return [item for item in definitions if str(item.get("name") or "") in allowed]

    def _execute_tool(self, call: ResponsesFunctionCall, context: Assistant1ToolContext) -> Dict[str, Any]:
        name = str(call.name or "").strip()
        arguments = call.arguments if isinstance(call.arguments, dict) else {}
        if name == "search_knowledge_base":
            return self._tool_search_knowledge_base(arguments, context, grouped=False)
        if name == "search_knowledge_base_grouped":
            return self._tool_search_knowledge_base(arguments, context, grouped=True)
        if name == "ingest_document":
            return self._tool_ingest_document(arguments, context)
        return {
            "ok": False,
            "error": f"unknown tool: {name}",
        }

    def _tool_search_knowledge_base(
        self,
        arguments: Dict[str, Any],
        context: Assistant1ToolContext,
        *,
        grouped: bool,
    ) -> Dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        target_file_hash = str(arguments.get("file_hash") or context.default_file_hash or "").strip()
        unit_types = (
            [str(item).strip() for item in arguments.get("unit_types", []) if str(item).strip()]
            if isinstance(arguments.get("unit_types"), list)
            else []
        )
        top_k_raw = arguments.get("top_k")
        top_k = context.top_k
        if isinstance(top_k_raw, int):
            top_k = max(1, min(8, top_k_raw))
        if not query:
            return {"ok": False, "error": "query is required"}
        if not target_file_hash:
            return {
                "ok": False,
                "error": "file_hash is required because there is no default document in the current session",
            }
        try:
            result = self.retrieval.query(
                query,
                file_hash=target_file_hash,
                unit_types=unit_types,
                top_k=top_k,
            )
        except Exception as exc:
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "file_hash": target_file_hash,
            }

        compact_matches: List[Dict[str, Any]] = []
        aggregated_years: set[str] = set()
        for index, item in enumerate(result.get("matches", []), start=1):
            if not isinstance(item, dict):
                continue
            content_preview = self._trim_text(item.get("content"), context.max_snippet_chars)
            year_hints = self._extract_year_tokens(" ".join([str(item.get("title") or ""), content_preview]))
            aggregated_years.update(year_hints)
            compact_matches.append(
                {
                    "rank": index,
                    "unit_id": str(item.get("id") or ""),
                    "unit_type": str(item.get("unit_type") or ""),
                    "title": str(item.get("title") or ""),
                    "page_start": item.get("page_start"),
                    "page_end": item.get("page_end"),
                    "distance": round(float(item.get("distance") or 0.0), 6),
                    "content_preview": content_preview,
                    "year_hints": year_hints,
                    "source_block_ids": item.get("source_block_ids") if isinstance(item.get("source_block_ids"), list) else [],
                    "unit_meta": item.get("unit_meta_json") if isinstance(item.get("unit_meta_json"), dict) else {},
                }
            )

        warnings: List[str] = []
        if len(aggregated_years) > 1:
            warnings.append(
                "retrieved matches appear to span multiple years or versions: " + ", ".join(sorted(aggregated_years))
            )

        payload: Dict[str, Any] = {
            "ok": True,
            "file_hash": target_file_hash,
            "query": query,
            "match_count": len(compact_matches),
            "matches": compact_matches,
            "warnings": warnings,
            "year_groups": self._group_matches_by_year(compact_matches),
        }
        if grouped:
            payload["grouped_mode"] = True
        if len(payload["year_groups"]) > 1:
            payload["suggested_answer_mode"] = "separate_by_year"
        return payload

    def _tool_ingest_document(self, arguments: Dict[str, Any], context: Assistant1ToolContext) -> Dict[str, Any]:
        target_file_hash = str(arguments.get("file_hash") or context.default_file_hash or "").strip()
        persist = bool(arguments.get("persist", True))
        if not target_file_hash:
            return {
                "ok": False,
                "error": "file_hash is required because there is no default document in the current session",
            }
        try:
            result = self.ingest.ingest(target_file_hash, persist=persist)
        except Exception as exc:
            return {
                "ok": False,
                "file_hash": target_file_hash,
                "error": f"{type(exc).__name__}: {exc}",
            }
        return {
            "ok": True,
            "file_hash": target_file_hash,
            "persisted": bool(result.get("persisted")),
            "knowledge_unit_count": int(result.get("knowledge_unit_count") or 0),
            "warning_count": int(result.get("warning_count") or 0),
            "warnings": result.get("warnings") if isinstance(result.get("warnings"), list) else [],
            "artifact_dir": str(result.get("artifact_dir") or ""),
        }

    @staticmethod
    def _tool_result_preview(result: Dict[str, Any]) -> Dict[str, Any]:
        preview: Dict[str, Any] = {
            "ok": bool(result.get("ok")),
        }
        if "error" in result:
            preview["error"] = str(result.get("error") or "")
            return preview
        if "match_count" in result:
            preview["match_count"] = int(result.get("match_count") or 0)
            matches = result.get("matches") if isinstance(result.get("matches"), list) else []
            preview["top_titles"] = [
                str(item.get("title") or "")
                for item in matches[:3]
                if isinstance(item, dict) and str(item.get("title") or "").strip()
            ]
            year_groups = result.get("year_groups") if isinstance(result.get("year_groups"), list) else []
            if year_groups:
                preview["year_groups"] = [
                    str(item.get("year_label") or "")
                    for item in year_groups[:4]
                    if isinstance(item, dict) and str(item.get("year_label") or "").strip()
                ]
        if "knowledge_unit_count" in result:
            preview["knowledge_unit_count"] = int(result.get("knowledge_unit_count") or 0)
            preview["warning_count"] = int(result.get("warning_count") or 0)
        return preview

    @classmethod
    def _group_matches_by_year(cls, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        groups: Dict[str, Dict[str, Any]] = {}
        for item in matches:
            if not isinstance(item, dict):
                continue
            year_hints = [str(value).strip() for value in item.get("year_hints", []) if str(value).strip()]
            if len(year_hints) == 1:
                year_label = year_hints[0]
            elif len(year_hints) > 1:
                year_label = "multi_year"
            else:
                year_label = "unknown"
            bucket = groups.setdefault(
                year_label,
                {
                    "year_label": year_label,
                    "match_count": 0,
                    "titles": [],
                    "pages": [],
                    "snippets": [],
                },
            )
            bucket["match_count"] += 1
            title = str(item.get("title") or "").strip()
            if title and title not in bucket["titles"]:
                bucket["titles"].append(title)
            page_start = item.get("page_start")
            page_end = item.get("page_end")
            if isinstance(page_start, int):
                page_label = (
                    f"{page_start}"
                    if page_end == page_start or not isinstance(page_end, int)
                    else f"{page_start}-{page_end}"
                )
                if page_label not in bucket["pages"]:
                    bucket["pages"].append(page_label)
            snippet = str(item.get("content_preview") or "").strip()
            if snippet and len(bucket["snippets"]) < 2:
                bucket["snippets"].append(snippet)
        ordered: List[Dict[str, Any]] = []
        for key in sorted(groups.keys(), key=lambda value: (value in {"unknown", "multi_year"}, value)):
            bucket = groups[key]
            ordered.append(
                {
                    "year_label": bucket["year_label"],
                    "match_count": bucket["match_count"],
                    "titles": bucket["titles"][:4],
                    "pages": bucket["pages"][:6],
                    "snippets": bucket["snippets"][:2],
                }
            )
        return ordered

    @staticmethod
    def _cleanup_answer_text(answer: str) -> str:
        text = str(answer or "").replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @staticmethod
    def _is_strict_minimal_request(question: str) -> bool:
        text = str(question or "").strip()
        markers = ("只回复", "只回答", "仅回复", "仅回答", "不要带其他内容", "不要解释", "只给", "仅输出")
        return any(marker in text for marker in markers)

    @staticmethod
    def _wants_brief_answer(question: str) -> bool:
        text = str(question or "").strip()
        markers = ("简要", "简单说", "简短", "一句话", "先说结论", "直接说")
        return any(marker in text for marker in markers) or Assistant1AgentRuntime._is_strict_minimal_request(text)

    @staticmethod
    def _wants_detailed_answer(question: str) -> bool:
        text = str(question or "").strip()
        markers = ("详细", "系统", "全面", "展开", "具体分析", "分阶段", "分步骤", "逐步", "完整")
        return any(marker in text for marker in markers)

    @staticmethod
    def _is_capability_question(question: str) -> bool:
        text = str(question or "").strip()
        markers = ("能做什么", "可以帮我做什么", "可以做什么", "怎么开始", "先做什么", "建议怎么推进")
        return any(marker in text for marker in markers)

    @staticmethod
    def _is_general_method_question(question: str) -> bool:
        text = str(question or "").strip()
        markers = (
            "文档处理",
            "OCR",
            "表格恢复",
            "信息抽取",
            "知识库",
            "向量数据库",
            "向量检索",
            "入库",
            "建表",
            "自然语言转SQL",
            "NL2SQL",
            "扫描文档",
            "扫描件",
            "版式",
        )
        return any(marker.lower() in text.lower() for marker in markers)

    @staticmethod
    def _is_document_specific_question(question: str) -> bool:
        text = str(question or "").strip()
        markers = (
            "这份文档",
            "这个文档",
            "该文档",
            "当前文档",
            "这份文件",
            "这个文件",
            "该文件",
            "当前文件",
            "这张表",
            "这个表",
            "表格里",
            "图里",
            "图片里",
            "这页",
            "这一页",
            "文档里",
            "文件里",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _is_broad_document_question(question: str) -> bool:
        text = str(question or "").strip()
        markers = (
            "主要讲了什么",
            "重点是什么",
            "风险点是什么",
            "最值得优先核对",
            "按年份怎么区别",
            "差异是什么",
            "总体情况",
            "核心内容",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _trim_text(value: Any, limit: int) -> str:
        text = str(value or "").strip()
        if len(text) <= limit:
            return text
        if limit <= 3:
            return text[:limit]
        return text[: limit - 3].rstrip() + "..."

    @staticmethod
    def _extract_year_tokens(text: str) -> List[str]:
        hits = sorted(set(re.findall(r"\b(20\d{2})\b", str(text or ""))))
        return hits[:6]
