from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List

from .responses_provider import ResponsesFunctionCall
from .retrieval_reranker import rerank_matches
from .web_search_strategy import (
    build_retry_request,
    finalize_web_search_result,
    prepare_web_search_request,
    should_retry_web_search,
)


@dataclass
class Assistant1ToolContext:
    default_file_hash: str = ""
    top_k: int = 5
    max_snippet_chars: int = 700
    current_user_message: str = ""


class Assistant1ToolRouter:
    def __init__(self, *, retrieval: Any, ingest: Any, schema_tools: Any, sql_tools: Any, tavily: Any) -> None:
        self.retrieval = retrieval
        self.ingest = ingest
        self.schema_tools = schema_tools
        self.sql_tools = sql_tools
        self.tavily = tavily

    def tool_definitions(self, tool_names: tuple[str, ...] = ()) -> List[Dict[str, Any]]:
        definitions = [
            {
                "type": "function",
                "name": "search_knowledge_base_grouped",
                "description": (
                    "Search the assistant_1 knowledge base and return evidence grouped by year or version when possible. "
                    "Use this for broad document questions such as key points, risks, summaries, comparisons, trend explanations, "
                    "or when different years and versions may be mixed together."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The exact user question or a focused retrieval query."},
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
                    "Use this before answering document-specific questions about text, fields, values, tables, charts, figures, or page-level content."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The exact user question or a focused retrieval query."},
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
            {
                "type": "function",
                "name": "web_search_tavily",
                "description": (
                    "Search the public web using Tavily for latest information, official pages, background knowledge, or document-external facts. "
                    "When the user explicitly asks for official or latest information, prefer stronger grounding: keep multiple results, use deeper search, "
                    "and include domain filters when the official source is clear."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "The web search query."},
                        "topic": {"type": "string", "description": "general or news."},
                        "search_depth": {"type": "string", "description": "basic or advanced."},
                        "max_results": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 10,
                            "description": "Maximum result count.",
                        },
                        "include_domains": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional domain whitelist.",
                        },
                        "time_range": {
                            "type": "string",
                            "description": "Optional recency range for current information, such as day, week, month, or year.",
                        },
                        "days": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 365,
                            "description": "Legacy recency window in days. Prefer time_range for current Tavily requests.",
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "inspect_database_schema",
                "description": "Inspect the live PostgreSQL schema so the assistant can ground table design and SQL generation in actual database structure.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "schemas": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional schema names to inspect.",
                        },
                        "table_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional table name filter.",
                        },
                        "include_columns": {
                            "type": "boolean",
                            "description": "Whether to include column details.",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "design_schema_draft",
                "description": "Design a PostgreSQL schema draft for extracted data, document facts, or business records, and return normalized DDL suggestions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "objective": {"type": "string", "description": "What the table design needs to support."},
                        "table_name": {"type": "string", "description": "Optional preferred base table name."},
                        "fields": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Optional candidate fields with names, descriptions, or sample values.",
                        },
                        "expected_queries": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional expected query patterns.",
                        },
                        "file_context": {
                            "type": "string",
                            "description": "Optional document-derived context or requirements summary.",
                        },
                    },
                    "required": ["objective"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "draft_sql_from_nl",
                "description": "Translate a natural-language database request into a PostgreSQL SQL draft grounded in the live schema.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "request": {"type": "string", "description": "The natural-language database request."},
                        "allowed_tables": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional table allowlist.",
                        },
                        "mode": {"type": "string", "description": "read_only or read_write_draft."},
                    },
                    "required": ["request"],
                    "additionalProperties": False,
                },
            },
            {
                "type": "function",
                "name": "execute_sql_with_audit",
                "description": "Execute a PostgreSQL SQL statement with audit logging. Write operations and DDL require explicit confirmation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "sql": {"type": "string", "description": "The SQL statement to execute."},
                        "params": {"type": "array", "items": {}, "description": "Optional positional parameters."},
                        "confirmed": {"type": "boolean", "description": "Must be true for write or DDL statements."},
                        "reason": {"type": "string", "description": "Why this statement should be executed."},
                    },
                    "required": ["sql"],
                    "additionalProperties": False,
                },
            },
        ]
        if not tool_names:
            return definitions
        allowed = {name for name in tool_names if name}
        return [item for item in definitions if str(item.get("name") or "") in allowed]

    def execute_tool(self, call: ResponsesFunctionCall, context: Assistant1ToolContext) -> Dict[str, Any]:
        name = str(call.name or "").strip()
        arguments = call.arguments if isinstance(call.arguments, dict) else {}
        if name == "search_knowledge_base":
            return self._tool_search_knowledge_base(arguments, context, grouped=False)
        if name == "search_knowledge_base_grouped":
            return self._tool_search_knowledge_base(arguments, context, grouped=True)
        if name == "ingest_document":
            return self._tool_ingest_document(arguments, context)
        if name == "web_search_tavily":
            return self._tool_web_search(arguments, context)
        if name == "inspect_database_schema":
            return self._tool_inspect_database_schema(arguments)
        if name == "design_schema_draft":
            return self._tool_design_schema_draft(arguments)
        if name == "draft_sql_from_nl":
            return self._tool_draft_sql_from_nl(arguments)
        if name == "execute_sql_with_audit":
            return self._tool_execute_sql_with_audit(arguments)
        return {"ok": False, "error": f"unknown tool: {name}"}

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

        warnings: List[str] = []
        retrieval_stats: Dict[str, Any] = {}
        auto_ingest_result: Dict[str, Any] | None = None
        try:
            retrieval_stats = self.retrieval.stats(target_file_hash)
        except Exception as exc:
            warnings.append(f"retrieval_stats_unavailable:{type(exc).__name__}")
        if int(retrieval_stats.get("unit_count") or 0) <= 0:
            auto_ingest_result = self._tool_ingest_document(
                {"file_hash": target_file_hash, "persist": True},
                context,
            )
            if auto_ingest_result.get("ok"):
                retrieval_stats = {
                    "document_count": 1,
                    "unit_count": int(auto_ingest_result.get("knowledge_unit_count") or 0),
                }
                if int(retrieval_stats.get("unit_count") or 0) <= 0:
                    warnings.append("auto_ingest_completed_but_no_units_built")
            else:
                warnings.append(str(auto_ingest_result.get("error") or "auto_ingest_failed"))
        try:
            candidate_top_k = min(24, max(top_k, top_k * 4))
            result = self.retrieval.query(
                query,
                file_hash=target_file_hash,
                unit_types=unit_types,
                top_k=candidate_top_k,
            )
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "file_hash": target_file_hash}

        reranked_matches = rerank_matches(query, result.get("matches", []), limit=top_k)
        if not reranked_matches and unit_types:
            warnings.append("initial_unit_type_filter_returned_no_matches; broadened_to_all_unit_types")
            try:
                result = self.retrieval.query(
                    query,
                    file_hash=target_file_hash,
                    unit_types=[],
                    top_k=candidate_top_k,
                )
                reranked_matches = rerank_matches(query, result.get("matches", []), limit=top_k)
            except Exception as exc:
                warnings.append(f"broadened_retry_failed:{type(exc).__name__}")
        compact_matches: List[Dict[str, Any]] = []
        aggregated_years: set[str] = set()
        for index, item in enumerate(reranked_matches, start=1):
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
                    "original_rank": int(item.get("original_rank") or index),
                    "rerank_score": round(float(item.get("rerank_score") or 0.0), 4),
                    "matched_signals": item.get("matched_signals") if isinstance(item.get("matched_signals"), list) else [],
                    "content_preview": content_preview,
                    "year_hints": year_hints,
                    "source_block_ids": item.get("source_block_ids") if isinstance(item.get("source_block_ids"), list) else [],
                    "unit_meta": item.get("unit_meta_json") if isinstance(item.get("unit_meta_json"), dict) else {},
                    "ref_table_preview": item.get("ref_table_preview") if isinstance(item.get("ref_table_preview"), dict) else {},
                }
            )

        if len(aggregated_years) > 1:
            warnings.append(
                "retrieved matches appear to span multiple years or versions: " + ", ".join(sorted(aggregated_years))
            )

        payload: Dict[str, Any] = {
            "ok": True,
            "file_hash": target_file_hash,
            "query": query,
            "retrieved_candidate_count": len(result.get("matches", [])) if isinstance(result.get("matches"), list) else 0,
            "match_count": len(compact_matches),
            "matches": compact_matches,
            "warnings": warnings,
            "year_groups": self.group_matches_by_year(compact_matches),
            "retrieval_stats": retrieval_stats,
        }
        if auto_ingest_result is not None:
            payload["auto_ingest"] = auto_ingest_result
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

    def _tool_web_search(self, arguments: Dict[str, Any], context: Assistant1ToolContext) -> Dict[str, Any]:
        try:
            prepared = prepare_web_search_request(
                arguments,
                origin_question=str(context.current_user_message or ""),
            )
            primary_result = self.tavily.search(
                prepared.query,
                topic=prepared.topic,
                search_depth=prepared.search_depth,
                max_results=prepared.max_results,
                include_domains=prepared.include_domains,
                time_range=prepared.time_range,
                days=prepared.days,
            )
            retry_result: Dict[str, Any] | None = None
            if should_retry_web_search(primary_result, prepared):
                retry_request = build_retry_request(prepared)
                retry_result = self.tavily.search(
                    retry_request.query,
                    topic=retry_request.topic,
                    search_depth=retry_request.search_depth,
                    max_results=retry_request.max_results,
                    include_domains=retry_request.include_domains,
                    time_range=retry_request.time_range,
                    days=retry_request.days,
                )
            return finalize_web_search_result(
                primary_result,
                prepared=prepared,
                retry_result=retry_result,
            )
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _tool_inspect_database_schema(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self.sql_tools.inspect_database_schema(
                schemas=arguments.get("schemas") if isinstance(arguments.get("schemas"), list) else [],
                table_names=arguments.get("table_names") if isinstance(arguments.get("table_names"), list) else [],
                include_columns=bool(arguments.get("include_columns", True)),
            )
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _tool_design_schema_draft(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self.schema_tools.design_schema_draft(
                objective=str(arguments.get("objective") or ""),
                table_name=str(arguments.get("table_name") or ""),
                fields=arguments.get("fields") if isinstance(arguments.get("fields"), list) else [],
                expected_queries=arguments.get("expected_queries") if isinstance(arguments.get("expected_queries"), list) else [],
                file_context=str(arguments.get("file_context") or ""),
            )
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _tool_draft_sql_from_nl(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self.sql_tools.draft_sql_from_nl(
                request=str(arguments.get("request") or ""),
                allowed_tables=arguments.get("allowed_tables") if isinstance(arguments.get("allowed_tables"), list) else [],
                mode=str(arguments.get("mode") or "read_only"),
            )
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def _tool_execute_sql_with_audit(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self.sql_tools.execute_sql_with_audit(
                sql=str(arguments.get("sql") or ""),
                params=arguments.get("params") if isinstance(arguments.get("params"), list) else [],
                confirmed=bool(arguments.get("confirmed", False)),
                reason=str(arguments.get("reason") or ""),
            )
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    @staticmethod
    def tool_result_preview(result: Dict[str, Any]) -> Dict[str, Any]:
        preview: Dict[str, Any] = {"ok": bool(result.get("ok"))}
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
        if "table_count" in result:
            preview["table_count"] = int(result.get("table_count") or 0)
            preview["tables"] = [
                str(item.get("table_name") or "")
                for item in result.get("tables", [])[:5]
                if isinstance(item, dict) and str(item.get("table_name") or "").strip()
            ]
        if "ddl_statements" in result:
            preview["ddl_count"] = len(result.get("ddl_statements") or [])
            preview["table_names"] = [
                str(item.get("name") or "")
                for item in result.get("tables", [])[:5]
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            ]
        if "sql" in result:
            preview["statement_type"] = str(result.get("statement_type") or "")
            preview["sql_preview"] = Assistant1ToolRouter._trim_text(result.get("sql"), 120)
        if "row_count" in result:
            preview["statement_type"] = str(result.get("statement_type") or "")
            preview["row_count"] = int(result.get("row_count") or 0)
        if "results" in result and isinstance(result.get("results"), list):
            preview["result_count"] = len(result.get("results") or [])
            preview["top_titles"] = [
                str(item.get("title") or "")
                for item in result.get("results", [])[:3]
                if isinstance(item, dict) and str(item.get("title") or "").strip()
            ]
            preferred_title = str(result.get("preferred_title") or "").strip()
            preferred_url = str(result.get("preferred_url") or "").strip()
            preferred_result = result.get("preferred_result") if isinstance(result.get("preferred_result"), dict) else {}
            if preferred_title:
                preview["preferred_title"] = preferred_title
            elif preferred_result:
                preview["preferred_title"] = str(preferred_result.get("title") or "")
            if preferred_url:
                preview["preferred_url"] = Assistant1ToolRouter._trim_text(preferred_url, 80)
            elif preferred_result:
                preview["preferred_url"] = Assistant1ToolRouter._trim_text(preferred_result.get("url"), 80)
        return preview

    @classmethod
    def group_matches_by_year(cls, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
                {"year_label": year_label, "match_count": 0, "titles": [], "pages": [], "snippets": []},
            )
            bucket["match_count"] += 1
            title = str(item.get("title") or "").strip()
            if title and title not in bucket["titles"]:
                bucket["titles"].append(title)
            page_start = item.get("page_start")
            page_end = item.get("page_end")
            if isinstance(page_start, int):
                page_label = f"{page_start}" if page_end == page_start or not isinstance(page_end, int) else f"{page_start}-{page_end}"
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
