from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Literal, Optional, Set, Tuple, TypedDict

from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

from app.assistant.provider import (
    OpenAICompatibleChatProvider,
    extract_json_object,
    resolve_llm_api_key,
    resolve_llm_base_url,
    resolve_llm_model,
)

if TYPE_CHECKING:
    from langchain_google_genai import ChatGoogleGenerativeAI


SYSTEM_PROMPT = """You are an expert document data extraction agent.
You extract structured fields from markdown that uses <ref id="..."> blocks.
Every extracted value must be grounded to an exact ref_id that already exists in the provided document context.

Core rules:
1. Prefer exact evidence, but also recognize aliases, synonymous labels, abbreviations, bilingual labels, nearby label-value pairs, and repeated header variants.
2. For table-heavy or spreadsheet-like documents, use row headers, column headers, merged headers, units, neighboring cells, and same-row context to resolve the best value.
3. Join multi-line fragments when they clearly form one entity. Keep the meaning faithful to the source text.
4. For dates, amounts, tax rates, IDs, invoice numbers, organization names, people, regions, and contract fields, prefer the most specific explicit value supported by the source.
5. If multiple candidates exist, choose the candidate whose wording is closest to the target field and whose ref_id most directly grounds the value.
6. Never fabricate values or ref_id. If evidence is weak or missing, return null.
Return JSON only.
"""

TABLE_SYSTEM_PROMPT = """You are an expert table extraction agent.
You receive structured table JSON and must extract target fields from table cells first.
Every returned field must be grounded to an existing table cell ref_id.

Core rules:
1. Match target fields using table headers, header aliases, units, merged headers, row labels, summary rows, and nearby cells.
2. Prefer values directly supported by the same row/column context rather than guessing from distant content.
3. When a value spans multiple cells or lines but clearly belongs together, combine it faithfully.
4. Normalize only trivial formatting differences when the source is explicit, but do not invent missing parts.
5. In repetitive tables without an explicit row filter, if the first visible cell under a matched column is a placeholder such as "-", "—", blank, "N/A", or "null", continue scanning downward and prefer the earliest explicit grounded value in that same matched column.
6. If a field cannot be reliably grounded to one of the allowed ref_id candidates, return null for that field.
Return JSON only.
"""

JSON_REPAIR_SYSTEM_PROMPT = """You repair assistant output into one valid JSON object.
Return JSON only.
Do not add markdown fences, explanations, or any extra text outside the JSON object.
"""


class LLMField(BaseModel):
    value: Any = None
    ref_id: Optional[str] = None


class LLMExtractionPayload(BaseModel):
    fields: Dict[str, LLMField] = Field(default_factory=dict)


class AgentState(TypedDict):
    markdown: str
    bbox_map: Dict[str, List[float]]
    table_blocks: List[Dict[str, Any]]
    table_summary: str
    field_hints: Dict[str, List[str]]
    schema: Dict[str, Any]
    results: Dict[str, Dict[str, Any]]
    errors: List[str]
    soft_warnings: List[str]
    retries: int
    max_retries: int


class ExtractionGraph:
    def __init__(self, llm: Optional["ChatGoogleGenerativeAI"] = None) -> None:
        temperature = float(os.getenv("MODULE2_LLM_TEMPERATURE", "0"))
        primary_model = resolve_llm_model(default="gemini-3.1-pro")
        fallback_models = [
            m.strip()
            for m in os.getenv(
                "MODULE2_LLM_MODEL_FALLBACKS",
                "",
            ).split(",")
            if m.strip()
        ]
        self._model_candidates = [primary_model] + [m for m in fallback_models if m != primary_model]
        self._temperature = temperature
        self._base_url = resolve_llm_base_url()
        self._api_key = resolve_llm_api_key()
        self._max_tokens = max(512, int(os.getenv("MODULE2_ASSISTANT_MAX_TOKENS", "1600")))
        self._json_retry_count = max(1, int(os.getenv("MODULE2_ASSISTANT_JSON_RETRY_COUNT", "3")))
        self._json_max_tokens = max(self._max_tokens, int(os.getenv("MODULE2_ASSISTANT_JSON_MAX_TOKENS", "4096")))
        raw_reasoning_effort = str(os.getenv("MODULE2_LLM_REASONING_EFFORT", "minimal") or "minimal").strip().lower()
        self._reasoning_effort = raw_reasoning_effort if raw_reasoning_effort in {"minimal", "low", "medium", "high"} else "minimal"
        self._timeout_sec = max(
            10.0,
            float(
                os.getenv(
                    "MODULE2_ASSISTANT_TIMEOUT_SEC",
                    os.getenv("MODULE2_FIELD_EXTRACT_TIMEOUT_SEC", "90"),
                )
            ),
        )
        debug_dir_raw = str(os.getenv("MODULE2_ASSISTANT_DEBUG_DIR", ".runlogs/module2-llm-debug") or "").strip()
        self._debug_dir = Path(debug_dir_raw).resolve() if debug_dir_raw else None
        self._llm_disabled_reason: Optional[str] = None
        self._provider: Optional[OpenAICompatibleChatProvider] = None
        if llm is not None:
            self.llm = llm
            self.structured_llm = self.llm.with_structured_output(LLMExtractionPayload)
        else:
            has_key = bool(self._api_key)
            if self._base_url and has_key:
                self.llm = None
                self.structured_llm = None
                self._provider = OpenAICompatibleChatProvider(
                    base_url=self._base_url,
                    api_key=self._api_key,
                    model=primary_model,
                    temperature=temperature,
                    max_tokens=self._max_tokens,
                    timeout_sec=self._timeout_sec,
                )
            elif has_key:
                from langchain_google_genai import ChatGoogleGenerativeAI

                self.llm = ChatGoogleGenerativeAI(
                    model=primary_model,
                    temperature=temperature,
                    google_api_key=self._api_key,
                )
                self.structured_llm = self.llm.with_structured_output(LLMExtractionPayload)
            else:
                self.llm = None
                self.structured_llm = None
                self._llm_disabled_reason = "missing_gemini_api_key"
        self.graph = self._build_graph()

    async def run(self, state: AgentState) -> AgentState:
        return await self.graph.ainvoke(state)

    def _build_graph(self):
        builder = StateGraph(AgentState)

        builder.add_node("table_profile", self.table_profile_node)
        builder.add_node("table_extract", self.table_extract_node)
        builder.add_node("extract", self.extraction_node)
        builder.add_node("validate", self.validation_node)
        builder.add_node("resolve_dependencies", self.resolve_dependencies_node)

        builder.set_entry_point("table_profile")
        builder.add_edge("table_profile", "table_extract")
        builder.add_edge("table_extract", "extract")
        builder.add_edge("extract", "validate")

        builder.add_conditional_edges(
            "validate",
            self._route_after_validation,
            {
                "extract": "extract",
                "resolve_dependencies": "resolve_dependencies",
            },
        )

        builder.add_conditional_edges(
            "resolve_dependencies",
            self._route_after_dependency,
            {
                "extract": "extract",
                "end": END,
            },
        )

        return builder.compile()

    async def table_profile_node(self, state: AgentState) -> AgentState:
        target_fields = self._target_fields(state["schema"])
        tables = state.get("table_blocks", [])
        if not tables:
            state["table_summary"] = "No table blocks detected."
            state["field_hints"] = {}
            return state

        hints: Dict[str, List[Tuple[int, str]]] = {field: [] for field in target_fields.keys()}
        table_notes: List[Tuple[int, str]] = []

        for table in tables:
            table_id = str(table.get("table_id", ""))
            page = table.get("page")
            quality = float(table.get("quality", 0.5) or 0.5)
            headers = [str(h).strip() for h in table.get("headers", []) if str(h).strip()]
            header_meta = table.get("header_meta", [])
            header_terms: List[str] = []
            for item in header_meta[:8]:
                name = str(item.get("name", "")).strip()
                unit = str(item.get("unit", "")).strip()
                if name:
                    header_terms.append(name)
                if unit:
                    header_terms.append(unit)
            row_samples: List[str] = []
            for row in table.get("rows", [])[:6]:
                texts: List[str] = []
                for c in row.get("cells", []):
                    cell_text = str(c.get("normalized_text") or c.get("text", "")).strip()
                    if not cell_text:
                        continue
                    header = str(c.get("header", "")).strip()
                    unit = str(c.get("detected_unit") or c.get("header_unit") or "").strip()
                    if header and unit:
                        texts.append(f"{header}({unit})={cell_text}")
                    elif header:
                        texts.append(f"{header}={cell_text}")
                    else:
                        texts.append(cell_text)
                if texts:
                    row_samples.append(" | ".join(texts))
            table_text = " ".join(headers + header_terms + row_samples).lower()

            score = 0
            for field_name, field_type in target_fields.items():
                field_score = self._keyword_overlap_score(str(field_name), table_text)
                if field_score > 0:
                    boosted = field_score + int(round(quality * 2))
                    hints[field_name].append((boosted, table_id))
                    score += boosted

            note = (
                f"{table_id} (page={page}, quality={quality:.2f}, headers={headers[:6]}, "
                f"rows={len(table.get('rows', []))}, score={score})"
            )
            table_notes.append((score, note))

        max_notes = max(2, int(os.getenv("MODULE2_TABLE_PROFILE_MAX_TABLES", "8")))
        table_notes = sorted(table_notes, key=lambda x: -x[0])[:max_notes]
        state["table_summary"] = "\n".join(note for _, note in table_notes) if table_notes else "No table profile generated."

        normalized_hints: Dict[str, List[str]] = {}
        for field_name, entries in hints.items():
            sorted_entries = sorted(entries, key=lambda x: -x[0])
            seen: Set[str] = set()
            picked: List[str] = []
            for _, table_id in sorted_entries:
                if not table_id or table_id in seen:
                    continue
                seen.add(table_id)
                picked.append(table_id)
                if len(picked) >= 3:
                    break
            if picked:
                normalized_hints[field_name] = picked
        state["field_hints"] = normalized_hints
        return state

    async def table_extract_node(self, state: AgentState) -> AgentState:
        target_fields = self._target_fields(state["schema"])
        tables = state.get("table_blocks", [])
        if not tables or not target_fields:
            return state

        extracted = dict(state.get("results", {}))
        error_fields = self._fields_from_errors(state.get("errors", []), target_fields)
        if state.get("errors") and not error_fields:
            error_fields = set(target_fields.keys())

        focus_fields: Dict[str, Any] = {}
        for field_name, field_type in target_fields.items():
            existing = extracted.get(field_name, {})
            if existing.get("value") is None or field_name in error_fields:
                focus_fields[field_name] = field_type
        if not focus_fields:
            return state

        max_table_refs = max(120, int(os.getenv("MODULE2_TABLE_ALLOWED_REFS_MAX", "360")))
        correction_context = "\n".join(state["errors"][-5:]) if state["errors"] else "None"
        table_timeout_sec = max(5.0, float(os.getenv("MODULE2_TABLE_EXTRACT_TIMEOUT_SEC", "60")))
        max_field_chars = max(80, int(os.getenv("MODULE2_MAX_FIELD_CHARS", "300")))
        table_ref_lookup = self._table_ref_lookup(tables)
        field_batches = self._chunk_target_fields(
            focus_fields,
            env_name="MODULE2_TABLE_EXTRACT_BATCH_SIZE",
            default_size=4,
        )

        for batch_fields in field_batches:
            table_context = self._build_table_context(tables, state.get("field_hints", {}), batch_fields)
            if not table_context:
                continue
            allowed_table_refs = self._extract_ref_ids_from_text(table_context, max_refs=max_table_refs)
            if not allowed_table_refs:
                allowed_table_refs = self._collect_table_ref_ids(tables, max_refs=max_table_refs)
            if not allowed_table_refs:
                continue
            correction_fields = [name for name in sorted(error_fields) if name in batch_fields]
            user_prompt = (
                "Table profile summary:\n"
                f"{state.get('table_summary', '')}\n\n"
                "Target Schema:\n"
                f"{json.dumps(batch_fields, ensure_ascii=False)}\n\n"
                "Fields requiring correction first:\n"
                f"{json.dumps(correction_fields, ensure_ascii=False)}\n\n"
                "Table context JSON:\n"
                f"{table_context}\n\n"
                "Allowed table ref_id candidates:\n"
                f"{json.dumps(allowed_table_refs, ensure_ascii=False)}\n\n"
                "Previous validation errors to correct:\n"
                f"{correction_context}\n\n"
                "Extraction rules:\n"
                "- Match field aliases, synonymous headers, abbreviations, and unit-bearing labels.\n"
                "- Use row labels, column labels, merged headers, same-row context, and nearby cells together.\n"
                "- For repetitive tables without a user-specified row filter, do not stop at placeholder cells like —, -, blank, or N/A; continue downward and prefer the earliest explicit grounded value in the matched column.\n"
                "- Prefer the most explicit grounded value and correct previous validation errors first.\n"
                "- If evidence is insufficient, return null instead of guessing.\n\n"
                "Return strictly as JSON using: {\"fields\": {field_name: {\"value\": ..., \"ref_id\": ...}}}."
            )

            try:
                payload = await asyncio.wait_for(
                    self._invoke_with_model_fallback(
                        [
                            {"role": "system", "content": TABLE_SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        purpose="table_extract",
                    ),
                    timeout=table_timeout_sec,
                )
            except asyncio.TimeoutError:
                self._push_soft_warning(state, f"table_extract_timeout: exceeded {table_timeout_sec:.1f}s")
                continue
            except Exception as exc:
                self._push_soft_warning(state, f"table_extract_error: {type(exc).__name__}: {exc}")
                continue

            for field_name in batch_fields.keys():
                existing = extracted.get(field_name, {})
                if (
                    field_name not in error_fields
                    and existing.get("value") is not None
                    and existing.get("source_ref_id") in state["bbox_map"]
                ):
                    continue

                expected_type = batch_fields.get(field_name)
                item = payload.fields.get(field_name, LLMField())
                coerced_value, coerced = self._coerce_value(item.value, expected_type)
                ref_id = item.ref_id
                ref_valid = bool(ref_id and ref_id in state["bbox_map"] and ref_id in allowed_table_refs)
                expected_str = str(expected_type).lower()
                if ref_valid:
                    cell = table_ref_lookup.get(str(ref_id), {})
                    numeric_value = cell.get("numeric_value")
                    if expected_str in {"number", "float", "double"} and isinstance(numeric_value, (int, float)) and not isinstance(numeric_value, bool):
                        coerced_value = float(numeric_value)
                        coerced = True
                    elif expected_str in {"integer", "int"} and isinstance(numeric_value, (int, float)) and not isinstance(numeric_value, bool):
                        coerced_value = int(round(float(numeric_value)))
                        coerced = True
                    elif expected_str in {"string", "str", "text", "date", "datetime", "timestamp"}:
                        cell_text = str(cell.get("text", "")).strip()
                        if cell_text:
                            coerced_value = cell_text
                            coerced = True
                if not ref_valid or coerced_value is None:
                    continue

                if isinstance(coerced_value, str) and len(coerced_value) > max_field_chars:
                    coerced_value = coerced_value[:max_field_chars].rstrip()
                    coerced = True

                bbox = state["bbox_map"].get(ref_id, [0.0, 0.0, 0.0, 0.0, 0.0])
                confidence = min(0.99, self._estimate_confidence(coerced_value, expected_type, True, coerced) + 0.08)
                extracted[field_name] = {
                    "value": coerced_value,
                    "confidence": confidence,
                    "source_ref_id": ref_id,
                    "bbox": bbox,
                }

        extracted = self._backfill_missing_table_fields(
            table_blocks=tables,
            target_fields=focus_fields,
            extracted=extracted,
            bbox_map=state["bbox_map"],
        )
        state["results"] = extracted
        return state

    async def extraction_node(self, state: AgentState) -> AgentState:
        target_fields = self._target_fields(state["schema"])
        existing = dict(state.get("results", {}))
        table_ref_lookup = self._table_ref_lookup(state.get("table_blocks", []))
        error_fields = self._fields_from_errors(state.get("errors", []), target_fields)
        if state.get("errors") and not error_fields:
            error_fields = set(target_fields.keys())

        pending_fields = {
            field_name: field_type
            for field_name, field_type in target_fields.items()
            if existing.get(field_name, {}).get("value") is None or field_name in error_fields
        }
        if not pending_fields:
            state["errors"] = []
            return state

        correction_context = "\n".join(state["errors"][-5:]) if state["errors"] else "None"
        max_allowed_refs = max(120, int(os.getenv("MODULE2_ALLOWED_REFS_MAX", "320")))
        prev_summary = self._results_summary(existing)

        field_timeout_sec = max(8.0, float(os.getenv("MODULE2_FIELD_EXTRACT_TIMEOUT_SEC", "90")))
        max_field_chars = max(80, int(os.getenv("MODULE2_MAX_FIELD_CHARS", "300")))
        field_batches = self._chunk_target_fields(
            pending_fields,
            env_name="MODULE2_FIELD_EXTRACT_BATCH_SIZE",
            default_size=4,
        )

        for batch_fields in field_batches:
            compact_markdown = self._build_context(state["markdown"], batch_fields)
            allowed_refs = self._extract_ref_ids_from_text(compact_markdown, max_refs=max_allowed_refs)
            if len(allowed_refs) < max(12, min(48, max_allowed_refs // 4)):
                for ref_id in self._selected_result_refs(existing, max_refs=max_allowed_refs):
                    if ref_id not in allowed_refs:
                        allowed_refs.append(ref_id)
                    if len(allowed_refs) >= max_allowed_refs:
                        break
            if not allowed_refs:
                allowed_refs = list(state["bbox_map"].keys())[:max_allowed_refs]
            correction_fields = [name for name in sorted(error_fields) if name in batch_fields]
            user_prompt = (
                "Document Markdown:\n"
                f"{compact_markdown}\n\n"
                "Target Schema:\n"
                f"{json.dumps(batch_fields, ensure_ascii=False)}\n\n"
                "Fields requiring correction first:\n"
                f"{json.dumps(correction_fields, ensure_ascii=False)}\n\n"
                "Table profile summary:\n"
                f"{state.get('table_summary', '')}\n\n"
                "Field-to-table hints:\n"
                f"{json.dumps(state.get('field_hints', {}), ensure_ascii=False)}\n\n"
                "Already extracted fields:\n"
                f"{prev_summary}\n\n"
                "Allowed ref_id candidates:\n"
                f"{json.dumps(allowed_refs, ensure_ascii=False)}\n\n"
                "Previous validation errors to correct:\n"
                f"{correction_context}\n\n"
                "Extraction rules:\n"
                "- Recognize field aliases, synonymous labels, abbreviations, nearby label-value pairs, and multi-line entities.\n"
                "- For table-heavy evidence, trust header/row context and field-to-table hints before broad prose guesses.\n"
                "- Preserve the source meaning for amounts, dates, IDs, organization names, people, and locations.\n"
                "- Prefer the most direct grounded candidate from the allowed ref_id list.\n"
                "- If evidence is insufficient, return null instead of guessing.\n\n"
                "Return strictly as JSON using: {\"fields\": {field_name: {\"value\": ..., \"ref_id\": ...}}}.\n"
                "Do not fabricate values or ref_id. If missing, set value/ref_id to null."
            )

            try:
                payload = await asyncio.wait_for(
                    self._invoke_with_model_fallback(
                        [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        purpose="field_extract",
                    ),
                    timeout=field_timeout_sec,
                )
            except asyncio.TimeoutError:
                self._push_soft_warning(state, f"field_extract_timeout: exceeded {field_timeout_sec:.1f}s")
                continue
            except Exception as exc:
                self._push_soft_warning(state, f"field_extract_error: {type(exc).__name__}: {exc}")
                continue

            for field_name in batch_fields.keys():
                if field_name not in error_fields and existing.get(field_name, {}).get("value") is not None:
                    continue

                expected_type = batch_fields.get(field_name)
                item = payload.fields.get(field_name, LLMField())
                coerced_value, coerced = self._coerce_value(item.value, expected_type)
                ref_id = item.ref_id
                ref_valid = bool(ref_id and ref_id in state["bbox_map"])
                expected_str = str(expected_type).lower()
                if ref_valid:
                    cell = table_ref_lookup.get(str(ref_id), {})
                    numeric_value = cell.get("numeric_value")
                    if expected_str in {"number", "float", "double"} and isinstance(numeric_value, (int, float)) and not isinstance(numeric_value, bool):
                        coerced_value = float(numeric_value)
                        coerced = True
                    elif expected_str in {"integer", "int"} and isinstance(numeric_value, (int, float)) and not isinstance(numeric_value, bool):
                        coerced_value = int(round(float(numeric_value)))
                        coerced = True
                    elif expected_str in {"string", "str", "text", "date", "datetime", "timestamp"}:
                        cell_text = str(cell.get("text", "")).strip()
                        if cell_text:
                            coerced_value = cell_text
                            coerced = True
                if not ref_valid:
                    coerced_value = None
                elif isinstance(coerced_value, str) and len(coerced_value) > max_field_chars:
                    coerced_value = coerced_value[:max_field_chars].rstrip()
                    coerced = True

                bbox = state["bbox_map"].get(ref_id, [0.0, 0.0, 0.0, 0.0, 0.0]) if ref_valid else [0.0, 0.0, 0.0, 0.0, 0.0]
                confidence = self._estimate_confidence(coerced_value, expected_type, ref_valid, coerced)
                existing[field_name] = {
                    "value": coerced_value,
                    "confidence": confidence,
                    "source_ref_id": ref_id,
                    "bbox": bbox,
                }

        state["results"] = existing
        state["errors"] = []
        return state

    async def validation_node(self, state: AgentState) -> AgentState:
        errors: List[str] = []
        target_fields = self._target_fields(state["schema"])
        required_fields = self._required_fields(state["schema"], target_fields)

        for field_name, field_type in target_fields.items():
            result = state["results"].get(field_name)
            value = result.get("value") if result else None
            source_ref_id = result.get("source_ref_id") if result else None
            bbox = result.get("bbox") if result else []

            if value is None:
                if field_name in required_fields:
                    errors.append(f"{field_name} is required but missing")
                continue

            if not source_ref_id or source_ref_id not in state["bbox_map"]:
                errors.append(f"{field_name} missing or invalid source_ref_id")

            if not isinstance(bbox, list) or len(bbox) != 5:
                errors.append(f"{field_name} missing valid bbox [page, x, y, w, h]")

            if not self._validate_type(value, field_type):
                errors.append(f"{field_name} type mismatch, expected {field_type}, got {type(value).__name__}")

        date_error = self._validate_date_order(state["results"])
        if date_error:
            errors.append(date_error)
        errors.extend(self._validate_schema_rules(state["results"], state["schema"]))

        if errors:
            state["errors"] = errors
            state["retries"] += 1
        else:
            state["errors"] = []
        return state

    async def resolve_dependencies_node(self, state: AgentState) -> AgentState:
        dependency_errors: List[str] = []
        dependencies = self._dependencies(state["schema"])

        for field_b, deps in dependencies.items():
            field_b_value = state["results"].get(field_b, {}).get("value")
            if field_b_value is None:
                continue

            for field_a in deps:
                field_a_value = state["results"].get(field_a, {}).get("value")
                if field_a_value is None:
                    dependency_errors.append(f"Dependency missing: {field_b} requires {field_a}")

        if dependency_errors:
            state["errors"] = dependency_errors
            state["retries"] += 1

        return state

    @staticmethod
    def _route_after_validation(state: AgentState) -> Literal["extract", "resolve_dependencies"]:
        if state["errors"] and state["retries"] <= state["max_retries"]:
            return "extract"
        return "resolve_dependencies"

    @staticmethod
    def _route_after_dependency(state: AgentState) -> Literal["extract", "end"]:
        if state["errors"] and state["retries"] <= state["max_retries"]:
            return "extract"
        return "end"

    @staticmethod
    def _target_fields(schema: Dict[str, Any]) -> Dict[str, Any]:
        if "fields" in schema and isinstance(schema["fields"], dict):
            return schema["fields"]
        excluded = {"dependencies", "validations"}
        return {k: v for k, v in schema.items() if k not in excluded}

    @staticmethod
    def _required_fields(schema: Dict[str, Any], target_fields: Dict[str, Any]) -> Set[str]:
        required: Set[str] = set()

        raw_required = schema.get("required", [])
        if isinstance(raw_required, list):
            for item in raw_required:
                name = str(item or "").strip()
                if name:
                    required.add(name)

        fields_raw = schema.get("fields")
        if isinstance(fields_raw, dict):
            for field_name, field_spec in fields_raw.items():
                if isinstance(field_spec, dict) and bool(field_spec.get("required")):
                    required.add(str(field_name))

        return {name for name in required if name in target_fields}

    @staticmethod
    def _dependencies(schema: Dict[str, Any]) -> Dict[str, List[str]]:
        raw = schema.get("dependencies", {})
        normalized: Dict[str, List[str]] = {}
        if isinstance(raw, dict):
            for k, v in raw.items():
                if isinstance(v, list):
                    normalized[k] = [str(item) for item in v]
                elif isinstance(v, str):
                    normalized[k] = [v]
        return normalized

    @staticmethod
    def _validation_rules(schema: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw = schema.get("validations", [])
        if not isinstance(raw, list):
            return []
        rules: List[Dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                rules.append(item)
        return rules

    @staticmethod
    def _fields_from_errors(errors: List[str], target_fields: Dict[str, Any]) -> Set[str]:
        if not errors or not target_fields:
            return set()
        lower_map = {str(name).lower(): str(name) for name in target_fields.keys()}
        hits: Set[str] = set()
        for err in errors:
            text = str(err or "")
            lower_text = text.lower()
            for lname, original in lower_map.items():
                if not lname:
                    continue
                if re.fullmatch(r"[a-z0-9_]+", lname):
                    pattern = rf"(?<![a-z0-9_]){re.escape(lname)}(?![a-z0-9_])"
                    if re.search(pattern, lower_text):
                        hits.add(original)
                else:
                    if lname in lower_text:
                        hits.add(original)
        return hits

    @staticmethod
    def _to_float_or_none(value: Any) -> Optional[float]:
        if value is None:
            return None
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            cleaned = re.sub(r"[,\s$\u00a5\uffe5\uff0c]", "", value).strip()
            cleaned = cleaned[:-1] if cleaned.endswith(("%", "\uff05")) else cleaned
            if not cleaned:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

    @classmethod
    def _validate_schema_rules(cls, results: Dict[str, Dict[str, Any]], schema: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        rules = cls._validation_rules(schema)
        for idx, rule in enumerate(rules, start=1):
            rule_type = str(rule.get("type", "")).strip().lower()
            if not rule_type:
                continue

            if rule_type == "sum":
                target = str(rule.get("target", "")).strip()
                operands_raw = rule.get("operands", [])
                operands = [str(x).strip() for x in operands_raw] if isinstance(operands_raw, list) else []
                if not target or not operands:
                    continue
                tolerance = cls._to_float_or_none(rule.get("tolerance"))
                tolerance = tolerance if tolerance is not None and tolerance >= 0 else 0.01

                target_value = cls._to_float_or_none(results.get(target, {}).get("value"))
                op_values = [cls._to_float_or_none(results.get(name, {}).get("value")) for name in operands]
                if target_value is None or any(v is None for v in op_values):
                    continue

                expected = sum(v for v in op_values if v is not None)
                base = max(1.0, abs(expected))
                if abs(target_value - expected) > (tolerance * base):
                    errors.append(
                        f"Validation rule #{idx} failed: {target}={target_value} does not match sum({', '.join(operands)})={expected}"
                    )
                continue

            if rule_type == "range":
                field = str(rule.get("field", "")).strip()
                if not field:
                    continue
                value = cls._to_float_or_none(results.get(field, {}).get("value"))
                if value is None:
                    continue
                min_v = cls._to_float_or_none(rule.get("min"))
                max_v = cls._to_float_or_none(rule.get("max"))
                if min_v is not None and value < min_v:
                    errors.append(f"Validation rule #{idx} failed: {field}={value} < min({min_v})")
                if max_v is not None and value > max_v:
                    errors.append(f"Validation rule #{idx} failed: {field}={value} > max({max_v})")
                continue
        return errors

    @staticmethod
    def _build_context(markdown: str, target_fields: Dict[str, Any]) -> str:
        max_chars = max(1600, int(os.getenv("MODULE2_PROMPT_MAX_CHARS", "12000")))
        max_refs = max(40, int(os.getenv("MODULE2_PROMPT_MAX_REFS", "220")))
        fallback_ref_limit = max(8, int(os.getenv("MODULE2_PROMPT_FALLBACK_REF_LIMIT", "24")))
        if len(markdown) <= max_chars:
            return markdown

        refs = re.findall(r'<ref id="([^"]+)">(.*?)</ref>', markdown, flags=re.DOTALL)
        if not refs:
            head = markdown[: max_chars // 2]
            tail = markdown[-(max_chars // 2) :]
            return f"{head}\n...\n{tail}"

        keywords = ExtractionGraph._schema_keywords(target_fields)
        ranked: List[Tuple[int, int, str, str]] = []
        for idx, (ref_id, text) in enumerate(refs):
            normalized = text.lower()
            score = sum(1 for kw in keywords if kw and kw in normalized)
            ranked.append((score, idx, ref_id, text))

        picked: List[str] = []
        size = 0
        picked_ref_count = 0
        for score, _, ref_id, text in sorted(ranked, key=lambda x: (-x[0], x[1])):
            if score <= 0:
                continue
            segment = f'<ref id="{ref_id}">{text}</ref>'
            add_len = len(segment) + 1
            if size + add_len > max_chars or picked_ref_count >= max_refs:
                continue
            picked.append(segment)
            size += add_len
            picked_ref_count += 1

        chosen = {re.search(r'<ref id="([^"]+)">', row).group(1) for row in picked} if picked else set()
        if size < max_chars and picked:
            fallback_added = 0
            for _, _, ref_id, text in ranked:
                if ref_id in chosen:
                    continue
                if fallback_added >= fallback_ref_limit or picked_ref_count >= max_refs:
                    break
                segment = f'<ref id="{ref_id}">{text}</ref>'
                add_len = len(segment) + 1
                if size + add_len > max_chars:
                    break
                picked.append(segment)
                size += add_len
                picked_ref_count += 1
                fallback_added += 1
        elif not picked:
            for _, _, ref_id, text in ranked:
                if picked_ref_count >= max_refs:
                    break
                segment = f'<ref id="{ref_id}">{text}</ref>'
                add_len = len(segment) + 1
                if size + add_len > max_chars:
                    break
                picked.append(segment)
                size += add_len
                picked_ref_count += 1

        compact = "\n".join(picked) if picked else markdown[:max_chars]
        if len(compact) <= max_chars:
            return compact
        return compact[:max_chars]

    def _build_table_context(
        self,
        table_blocks: List[Dict[str, Any]],
        field_hints: Dict[str, List[str]],
        target_fields: Dict[str, Any],
    ) -> str:
        max_tables = max(1, int(os.getenv("MODULE2_TABLE_CONTEXT_MAX_TABLES", "8")))
        max_rows = max(1, int(os.getenv("MODULE2_TABLE_CONTEXT_MAX_ROWS", "24")))
        max_cols = max(1, int(os.getenv("MODULE2_TABLE_CONTEXT_MAX_COLS", "12")))
        max_header_meta = max(1, int(os.getenv("MODULE2_TABLE_CONTEXT_MAX_HEADER_META", "12")))
        max_chars = max(1800, int(os.getenv("MODULE2_TABLE_CONTEXT_MAX_CHARS", "12000")))

        selected = self._select_tables_for_fields(table_blocks, field_hints, target_fields, max_tables=max_tables)
        if not selected:
            return "[]"

        table_limit = len(selected)
        row_limit = max_rows
        col_limit = max_cols
        header_limit = max_header_meta
        while True:
            compact = self._serialize_table_context(
                selected[:table_limit],
                target_fields=target_fields,
                max_rows=row_limit,
                max_cols=col_limit,
                max_header_meta=header_limit,
            )
            serialized = json.dumps(compact, ensure_ascii=False)
            if len(serialized) <= max_chars:
                return serialized
            if row_limit > 8:
                row_limit = max(8, int(round(row_limit * 0.7)))
                continue
            if col_limit > 8:
                col_limit = max(8, int(round(col_limit * 0.7)))
                continue
            if table_limit > 2:
                table_limit -= 1
                continue
            if header_limit > 6:
                header_limit = max(6, int(round(header_limit * 0.7)))
                continue
            return serialized

    @staticmethod
    def _row_context_score(row: Dict[str, Any]) -> float:
        cells = row.get("cells", [])
        if not cells:
            return -1.0
        non_empty = 0
        numeric_like = 0
        header_hit = 0
        for cell in cells:
            text = str(cell.get("text", "")).strip()
            if text:
                non_empty += 1
            if cell.get("numeric_value") is not None or str(cell.get("value_type", "")).lower() == "number":
                numeric_like += 1
            if str(cell.get("header", "")).strip():
                header_hit += 1
        return float(non_empty) + (2.0 * float(numeric_like)) + (0.5 * float(header_hit))

    @staticmethod
    def _collect_table_ref_ids(table_blocks: List[Dict[str, Any]], max_refs: int = 500) -> List[str]:
        refs: List[str] = []
        seen: Set[str] = set()
        for table in table_blocks:
            for row in table.get("rows", []):
                for cell in row.get("cells", []):
                    ref_id = cell.get("ref_id")
                    if not ref_id or ref_id in seen:
                        continue
                    seen.add(ref_id)
                    refs.append(ref_id)
                    if len(refs) >= max_refs:
                        return refs
        return refs

    @staticmethod
    def _extract_ref_ids_from_text(text: str, *, max_refs: int) -> List[str]:
        if not text:
            return []
        refs: List[str] = []
        seen: Set[str] = set()
        candidates = list(re.findall(r'<ref id="([^"]+)">', text))
        candidates.extend(re.findall(r'\b[A-Za-z0-9_.-]+_r\d+_c\d+\b', text))
        for ref_id in candidates:
            token = str(ref_id or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            refs.append(token)
            if len(refs) >= max_refs:
                break
        return refs

    @staticmethod
    def _selected_result_refs(results: Dict[str, Dict[str, Any]], *, max_refs: int) -> List[str]:
        refs: List[str] = []
        seen: Set[str] = set()
        for _, payload in results.items():
            if not isinstance(payload, dict):
                continue
            ref_id = str(payload.get("source_ref_id") or "").strip()
            if not ref_id or ref_id in seen:
                continue
            seen.add(ref_id)
            refs.append(ref_id)
            if len(refs) >= max_refs:
                break
        return refs

    def _select_tables_for_fields(
        self,
        table_blocks: List[Dict[str, Any]],
        field_hints: Dict[str, List[str]],
        target_fields: Dict[str, Any],
        *,
        max_tables: int,
    ) -> List[Dict[str, Any]]:
        preferred_ids: List[str] = []
        for field_name in target_fields.keys():
            for table_id in field_hints.get(field_name, []):
                if table_id not in preferred_ids:
                    preferred_ids.append(table_id)

        selected: List[Dict[str, Any]] = []
        for table_id in preferred_ids:
            table = next((t for t in table_blocks if str(t.get("table_id")) == table_id), None)
            if table and table not in selected:
                selected.append(table)
            if len(selected) >= max_tables:
                break

        if len(selected) < max_tables:
            ranked_tables = sorted(table_blocks, key=lambda item: float(item.get("quality", 0.0) or 0.0), reverse=True)
            for table in ranked_tables:
                if table in selected:
                    continue
                selected.append(table)
                if len(selected) >= max_tables:
                    break
        return selected

    def _serialize_table_context(
        self,
        tables: List[Dict[str, Any]],
        *,
        target_fields: Dict[str, Any],
        max_rows: int,
        max_cols: int,
        max_header_meta: int,
    ) -> List[Dict[str, Any]]:
        compact: List[Dict[str, Any]] = []
        for table in tables:
            selected_columns = self._select_table_column_indices(table, target_fields=target_fields, max_cols=max_cols)
            rows = []
            all_rows = table.get("rows", [])
            ranked_rows = sorted(all_rows, key=self._row_context_score, reverse=True)
            head_keep = min(max_rows, max(2, min(4, max_rows)))
            row_candidates = list(all_rows[:head_keep]) + ranked_rows
            seen_rows: Set[str] = set()
            for row in row_candidates:
                if len(rows) >= max_rows:
                    break
                row_idx = int(row.get("row_index", 0) or 0)
                row_key = str(row_idx) if row_idx > 0 else json.dumps(row, ensure_ascii=False, sort_keys=True)[:200]
                if row_key in seen_rows:
                    continue
                seen_rows.add(row_key)
                cells = []
                for cell in row.get("cells", []):
                    col_index = cell.get("col_index")
                    if selected_columns and col_index not in selected_columns:
                        continue
                    cell_text = str(cell.get("text", "")).strip()
                    if not cell_text:
                        continue
                    payload: Dict[str, Any] = {
                        "col_index": col_index,
                        "text": cell_text,
                        "ref_id": cell.get("ref_id"),
                    }
                    header = str(cell.get("header", "")).strip()
                    if header:
                        payload["header"] = header
                    header_unit_raw = cell.get("header_unit")
                    header_unit = header_unit_raw.strip() if isinstance(header_unit_raw, str) else ""
                    if header_unit and header_unit.lower() not in {"none", "null"}:
                        payload["header_unit"] = header_unit
                    value_type = str(cell.get("value_type", "")).strip()
                    if value_type:
                        payload["value_type"] = value_type
                    numeric_value = cell.get("numeric_value")
                    if numeric_value is not None:
                        payload["numeric_value"] = numeric_value
                    cells.append(payload)
                if cells:
                    rows.append({"row_index": row.get("row_index"), "cells": cells})

            if not rows:
                continue
            header_meta: List[Dict[str, Any]] = []
            for item in table.get("header_meta", [])[:max_header_meta]:
                header_meta.append(
                    {
                        "col_index": item.get("col_index"),
                        "name": item.get("name"),
                        "unit": item.get("unit"),
                    }
                )
            compact.append(
                {
                    "table_id": table.get("table_id"),
                    "source": table.get("source"),
                    "page": table.get("page"),
                    "quality": table.get("quality"),
                    "headers": [
                        header
                        for idx, header in enumerate(table.get("headers", []), start=1)
                        if not selected_columns or idx in selected_columns
                    ][:max_cols],
                    "header_meta": header_meta,
                    "row_count": table.get("row_count"),
                    "col_count": table.get("col_count"),
                    "rows": rows,
                }
            )
        return compact

    def _select_table_column_indices(
        self,
        table: Dict[str, Any],
        *,
        target_fields: Dict[str, Any],
        max_cols: int,
    ) -> Set[int]:
        if max_cols <= 0:
            return set()

        selected: List[int] = []
        all_candidates: List[Tuple[int, int]] = []
        headers = table.get("headers", []) if isinstance(table.get("headers"), list) else []
        header_meta = table.get("header_meta", []) if isinstance(table.get("header_meta"), list) else []

        # Always preserve the leading identifier columns so row anchors remain interpretable.
        for idx in range(1, min(len(headers), max_cols) + 1):
            if idx <= min(4, max_cols) and idx not in selected:
                selected.append(idx)

        for idx, header in enumerate(headers, start=1):
            header_text = str(header or "").strip()
            if not header_text:
                continue
            score = 0
            for field_name in target_fields.keys():
                score += self._keyword_overlap_score(str(field_name), header_text.lower())
            if score > 0:
                all_candidates.append((score, idx))

        for item in header_meta:
            if not isinstance(item, dict):
                continue
            try:
                col_index = int(item.get("col_index") or 0)
            except (TypeError, ValueError):
                continue
            if col_index <= 0:
                continue
            header_text = f"{str(item.get('name') or '').strip()} {str(item.get('unit') or '').strip()}".strip().lower()
            if not header_text:
                continue
            score = 0
            for field_name in target_fields.keys():
                score += self._keyword_overlap_score(str(field_name), header_text)
            if score > 0:
                all_candidates.append((score + 1, col_index))

        for _, col_index in sorted(all_candidates, key=lambda item: (-item[0], item[1])):
            if col_index not in selected:
                selected.append(col_index)
            if len(selected) >= max_cols:
                break

        # If target-related columns are sparse, backfill from the far-right value region as well.
        if len(selected) < max_cols and headers:
            for idx in range(len(headers), 0, -1):
                if idx not in selected:
                    selected.append(idx)
                if len(selected) >= max_cols:
                    break

        return set(sorted(selected[:max_cols]))

    @staticmethod
    def _table_ref_lookup(table_blocks: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        lookup: Dict[str, Dict[str, Any]] = {}
        for table in table_blocks:
            for row in table.get("rows", []):
                for cell in row.get("cells", []):
                    ref_id = str(cell.get("ref_id") or "").strip()
                    if not ref_id or ref_id in lookup:
                        continue
                    lookup[ref_id] = cell
        return lookup

    def _backfill_missing_table_fields(
        self,
        *,
        table_blocks: List[Dict[str, Any]],
        target_fields: Dict[str, Any],
        extracted: Dict[str, Dict[str, Any]],
        bbox_map: Dict[str, List[float]],
    ) -> Dict[str, Dict[str, Any]]:
        if not table_blocks or not target_fields:
            return extracted

        normalized_results = dict(extracted or {})
        for field_name, expected_type in target_fields.items():
            existing = normalized_results.get(field_name, {})
            if self._has_meaningful_result_value(existing):
                continue

            candidate = self._find_table_column_backfill_candidate(
                table_blocks=table_blocks,
                field_name=str(field_name),
                expected_type=expected_type,
            )
            if candidate is None:
                continue

            ref_id = str(candidate.get("ref_id") or "").strip()
            if not ref_id or ref_id not in bbox_map:
                continue
            value = candidate.get("value")
            if value is None or self._is_placeholder_like_value(value):
                continue

            normalized_results[str(field_name)] = {
                "value": value,
                "confidence": candidate.get("confidence", 0.84),
                "source_ref_id": ref_id,
                "bbox": bbox_map.get(ref_id, [0.0, 0.0, 0.0, 0.0, 0.0]),
            }
        return normalized_results

    def _find_table_column_backfill_candidate(
        self,
        *,
        table_blocks: List[Dict[str, Any]],
        field_name: str,
        expected_type: Any,
    ) -> Optional[Dict[str, Any]]:
        wants_number = str(expected_type).lower() in {"number", "float", "double", "integer", "int"}
        best_score = 0
        best_candidate: Optional[Dict[str, Any]] = None

        for table_idx, table in enumerate(table_blocks[:12]):
            candidate_columns = self._rank_table_columns_for_field(table, field_name)
            if not candidate_columns:
                continue
            for score, col_index in candidate_columns:
                if score < best_score:
                    break
                for row in table.get("rows", [])[:160]:
                    if not isinstance(row, dict):
                        continue
                    cell = next(
                        (
                            item
                            for item in row.get("cells", [])
                            if int(item.get("col_index") or 0) == col_index
                        ),
                        None,
                    )
                    if not isinstance(cell, dict):
                        continue
                    cell_text = str(cell.get("text") or "").strip()
                    if self._is_placeholder_like_value(cell_text):
                        continue

                    coerced_value: Any = None
                    if wants_number:
                        numeric_value = cell.get("numeric_value")
                        if isinstance(numeric_value, (int, float)) and not isinstance(numeric_value, bool):
                            if str(expected_type).lower() in {"integer", "int"}:
                                coerced_value = int(round(float(numeric_value)))
                            else:
                                coerced_value = float(numeric_value)
                        else:
                            parsed_value, _ = self._coerce_value(cell_text, expected_type)
                            if isinstance(parsed_value, (int, float)) and not isinstance(parsed_value, bool):
                                coerced_value = parsed_value
                    else:
                        parsed_value, _ = self._coerce_value(cell_text, expected_type)
                        if parsed_value is not None and not self._is_placeholder_like_value(parsed_value):
                            coerced_value = parsed_value

                    if coerced_value is None or self._is_placeholder_like_value(coerced_value):
                        continue

                    confidence = min(0.94, 0.74 + 0.03 * float(score))
                    row_index = int(row.get("row_index", 0) or 0)
                    candidate = {
                        "value": coerced_value,
                        "ref_id": str(cell.get("ref_id") or "").strip(),
                        "confidence": confidence,
                        "score": score,
                        "table_order": table_idx,
                        "row_index": row_index,
                    }
                    if best_candidate is None:
                        best_candidate = candidate
                        best_score = score
                        continue
                    if score > int(best_candidate.get("score", 0) or 0):
                        best_candidate = candidate
                        best_score = score
                        continue
                    if score == int(best_candidate.get("score", 0) or 0):
                        prev_row_raw = best_candidate.get("row_index", 10**9)
                        prev_table_raw = best_candidate.get("table_order", 10**9)
                        prev_row = int(10**9 if prev_row_raw is None else prev_row_raw)
                        prev_table = int(10**9 if prev_table_raw is None else prev_table_raw)
                        if table_idx < prev_table or (table_idx == prev_table and row_index < prev_row):
                            best_candidate = candidate
                            best_score = score
                if best_candidate is not None and best_score >= score:
                    break
        return best_candidate

    def _rank_table_columns_for_field(self, table: Dict[str, Any], field_name: str) -> List[Tuple[int, int]]:
        ranked: List[Tuple[int, int]] = []
        headers = table.get("headers", []) if isinstance(table.get("headers"), list) else []
        header_meta = table.get("header_meta", []) if isinstance(table.get("header_meta"), list) else []
        seen: Set[int] = set()

        for idx, header in enumerate(headers, start=1):
            score = self._table_field_header_score(field_name, str(header or ""))
            if score <= 0 or idx in seen:
                continue
            ranked.append((score, idx))
            seen.add(idx)

        for item in header_meta:
            if not isinstance(item, dict):
                continue
            try:
                col_index = int(item.get("col_index") or 0)
            except (TypeError, ValueError):
                continue
            if col_index <= 0:
                continue
            header_text = f"{str(item.get('name') or '').strip()} {str(item.get('unit') or '').strip()}".strip()
            score = self._table_field_header_score(field_name, header_text)
            if score <= 0:
                continue
            ranked.append((score + 1, col_index))

        return sorted(ranked, key=lambda item: (-item[0], item[1]))

    def _table_field_header_score(self, field_name: str, header_text: str) -> int:
        lowered_header = str(header_text or "").strip().lower()
        if not lowered_header:
            return 0

        score = self._keyword_overlap_score(field_name, lowered_header)
        normalized_header = re.sub(r"[\s_\-/:,().]+", "", lowered_header)
        for alias in self._field_aliases(str(field_name)):
            alias_text = str(alias or "").strip().lower()
            if not alias_text:
                continue
            normalized_alias = re.sub(r"[\s_\-/:,().]+", "", alias_text)
            if normalized_alias and normalized_alias == normalized_header:
                score += 6
            elif alias_text in lowered_header:
                score += 3
        return score

    @staticmethod
    def _has_meaningful_result_value(entity: Any) -> bool:
        if not isinstance(entity, dict):
            return False
        value = entity.get("value")
        if value is None:
            return False
        return not ExtractionGraph._is_placeholder_like_value(value)

    @staticmethod
    def _is_placeholder_like_value(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return False

        text = str(value).strip()
        if not text:
            return True
        normalized = re.sub(r"\s+", "", text).strip().lower()
        if not normalized:
            return True
        if normalized in {
            "-",
            "--",
            "---",
            "—",
            "——",
            "/",
            "\\",
            "null",
            "none",
            "nan",
            "n/a",
            "na",
            "nil",
            "unknown",
            "未提供",
            "暂无",
            "无",
            "空",
        }:
            return True
        if all(ch in "-—_/.\\" for ch in normalized):
            return True
        return False

    @staticmethod
    def _chunk_target_fields(
        target_fields: Dict[str, Any],
        *,
        env_name: str,
        default_size: int = 4,
    ) -> List[Dict[str, Any]]:
        if not target_fields:
            return []
        batch_size = max(1, int(os.getenv(env_name, str(default_size)) or default_size))
        items = list(target_fields.items())
        return [dict(items[index : index + batch_size]) for index in range(0, len(items), batch_size)]

    async def invoke_json_object(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: Optional[int] = None,
        purpose: str = "json_object",
    ) -> Dict[str, Any]:
        if self._provider is not None:
            return await self._invoke_provider_json_object(messages, max_tokens=max_tokens, purpose=purpose)

        if self.llm is None:
            reason = self._llm_disabled_reason or "llm_unavailable"
            raise RuntimeError(f"llm_disabled:{reason}")

        last_exc: Exception | None = None
        for model_index, model_name in enumerate(self._model_candidates):
            if model_index == 0:
                llm = self.llm
            else:
                llm = ChatGoogleGenerativeAI(
                    model=model_name,
                    temperature=self._temperature,
                    google_api_key=self._api_key,
                )
            try:
                raw_resp = await llm.ainvoke(messages)
                payload_dict = extract_json_object(getattr(raw_resp, "content", raw_resp))
                if isinstance(payload_dict, dict):
                    return payload_dict
                raise RuntimeError("llm returned non-json content")
            except Exception as exc:
                last_exc = exc
                if self._is_model_not_found_error(exc):
                    continue
                raise
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("llm provider unavailable")

    async def _invoke_with_model_fallback(
        self,
        messages: List[Dict[str, str]],
        *,
        purpose: str = "field_extract",
    ) -> LLMExtractionPayload:
        if self._provider is not None:
            payload_dict = await self.invoke_json_object(messages, max_tokens=self._max_tokens, purpose=purpose)
            return self._payload_from_dict(payload_dict)

        if self.structured_llm is None:
            reason = self._llm_disabled_reason or "llm_unavailable"
            raise RuntimeError(f"llm_disabled:{reason}")
        try:
            return await self.structured_llm.ainvoke(messages)
        except Exception as exc:
            if not self._is_model_not_found_error(exc):
                raise
            last_exc: Exception = exc

        for model_name in self._model_candidates[1:]:
            self.llm = ChatGoogleGenerativeAI(
                model=model_name,
                temperature=self._temperature,
                google_api_key=self._api_key,
            )
            self.structured_llm = self.llm.with_structured_output(LLMExtractionPayload)
            try:
                return await self.structured_llm.ainvoke(messages)
            except Exception as exc:
                last_exc = exc
                if self._is_model_not_found_error(exc):
                    continue
                raise

        raise last_exc

    async def _invoke_provider_json_object(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: Optional[int] = None,
        purpose: str,
    ) -> Dict[str, Any]:
        last_exc: Exception | None = None
        for model_name in self._model_candidates:
            provider = OpenAICompatibleChatProvider(
                base_url=self._base_url,
                api_key=self._api_key,
                model=model_name,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                timeout_sec=self._timeout_sec,
            )
            try:
                return await self._invoke_provider_json_with_retry(
                    provider,
                    messages,
                    max_tokens=max_tokens,
                    purpose=purpose,
                )
            except Exception as exc:
                last_exc = exc
                if self._is_model_not_found_error(exc):
                    continue
                raise
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("llm provider unavailable")

    async def _invoke_provider_json_with_retry(
        self,
        provider: OpenAICompatibleChatProvider,
        messages: List[Dict[str, str]],
        *,
        max_tokens: Optional[int],
        purpose: str,
    ) -> Dict[str, Any]:
        last_result: Optional[Any] = None
        last_exc: Exception | None = None
        best_partial_payload: Optional[Dict[str, Any]] = None
        best_partial_score = 0
        token_candidates = self._json_token_candidates(max_tokens)
        for token_budget in token_candidates:
            try:
                result = await self._complete_provider_json_attempt(
                    provider,
                    messages,
                    max_tokens=token_budget,
                )
            except Exception as exc:
                last_exc = exc
                if self._is_model_not_found_error(exc):
                    raise
                continue

            last_result = result
            payload_dict = extract_json_object(result.content)
            if isinstance(payload_dict, dict):
                return payload_dict

            partial_payload = self._recover_truncated_json_output(result.content, purpose=purpose)
            partial_score = self._partial_payload_score(partial_payload, purpose=purpose)
            if partial_score > best_partial_score:
                best_partial_payload = partial_payload
                best_partial_score = partial_score

            if self._finish_reason_is_length(result.finish_reason):
                self._write_json_debug_artifact(
                    purpose=purpose,
                    provider=provider,
                    token_budget=token_budget,
                    result=result,
                    note="finish_reason=length",
                    messages=messages,
                )
                continue

            repaired = await self._repair_provider_json_output(
                provider,
                raw_content=result.content,
                token_budget=token_budget,
                purpose=purpose,
            )
            if isinstance(repaired, dict):
                return repaired

            self._write_json_debug_artifact(
                purpose=purpose,
                provider=provider,
                token_budget=token_budget,
                result=result,
                note="non_json_content",
                messages=messages,
            )

        if isinstance(best_partial_payload, dict) and best_partial_score > 0:
            return best_partial_payload
        if last_result is not None:
            raise RuntimeError("llm returned non-json content")
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("llm provider returned empty response")

    async def _complete_provider_json_attempt(
        self,
        provider: OpenAICompatibleChatProvider,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int,
    ):
        try:
            return await asyncio.to_thread(
                provider.complete,
                messages=messages,
                temperature=self._temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                reasoning_effort=self._reasoning_effort,
            )
        except Exception as exc:
            if not self._is_response_format_unsupported_error(exc):
                raise
        return await asyncio.to_thread(
            provider.complete,
            messages=messages,
            temperature=self._temperature,
            max_tokens=max_tokens,
            reasoning_effort=self._reasoning_effort,
        )

    async def _repair_provider_json_output(
        self,
        provider: OpenAICompatibleChatProvider,
        *,
        raw_content: str,
        token_budget: int,
        purpose: str,
    ) -> Optional[Dict[str, Any]]:
        raw = str(raw_content or "").strip()
        if not raw:
            return None
        payload = extract_json_object(raw)
        if isinstance(payload, dict):
            return payload

        fallback_shape = json.dumps(self._empty_json_shape(purpose), ensure_ascii=False)
        repair_messages = [
            {"role": "system", "content": JSON_REPAIR_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Convert the following assistant output into one valid JSON object.\n"
                    "Preserve recovered keys and values when they are unambiguous.\n"
                    f"If the content is incomplete or cannot be repaired safely, return exactly {fallback_shape}.\n\n"
                    f"Assistant output:\n{raw}"
                ),
            },
        ]
        repair_budget = min(self._json_max_tokens, max(512, min(token_budget, 2048)))
        try:
            repair_result = await self._complete_provider_json_attempt(
                provider,
                repair_messages,
                max_tokens=repair_budget,
            )
        except Exception:
            return None
        repaired = extract_json_object(repair_result.content)
        if isinstance(repaired, dict):
            return repaired
        self._write_json_debug_artifact(
            purpose=f"{purpose}_repair",
            provider=provider,
            token_budget=repair_budget,
            result=repair_result,
            note="repair_non_json",
            messages=repair_messages,
        )
        return None

    def _json_token_candidates(self, requested_max_tokens: Optional[int]) -> List[int]:
        start_tokens = max(512, int(requested_max_tokens or self._max_tokens))
        hard_cap = max(start_tokens, self._json_max_tokens)
        candidates: List[int] = []
        current = start_tokens
        for _ in range(self._json_retry_count):
            if current not in candidates:
                candidates.append(current)
            if current >= hard_cap:
                break
            current = min(hard_cap, max(current + 512, int(current * 1.7)))
        if hard_cap not in candidates:
            candidates.append(hard_cap)
        return candidates

    @staticmethod
    def _finish_reason_is_length(reason: Any) -> bool:
        return str(reason or "").strip().lower() == "length"

    @staticmethod
    def _empty_json_shape(purpose: str) -> Dict[str, Any]:
        label = str(purpose or "").strip().lower()
        if "schema" in label:
            return {"fields": []}
        if "field" in label or "table" in label:
            return {"fields": {}}
        return {}

    @classmethod
    def _recover_truncated_json_output(cls, raw_content: str, *, purpose: str) -> Optional[Dict[str, Any]]:
        raw = str(raw_content or "").strip()
        if not raw:
            return None
        label = str(purpose or "").strip().lower()
        if "schema" in label:
            recovered_fields = cls._recover_truncated_schema_fields(raw)
            return {"fields": recovered_fields} if recovered_fields else None
        if "field" in label or "table" in label:
            recovered_field_map = cls._recover_truncated_field_map(raw)
            return {"fields": recovered_field_map} if recovered_field_map else None
        return None

    @staticmethod
    def _partial_payload_score(payload: Optional[Dict[str, Any]], *, purpose: str) -> int:
        if not isinstance(payload, dict):
            return 0
        label = str(purpose or "").strip().lower()
        fields = payload.get("fields")
        if "schema" in label and isinstance(fields, list):
            return len([item for item in fields if isinstance(item, dict)])
        if ("field" in label or "table" in label) and isinstance(fields, dict):
            return len(fields)
        return 0

    @staticmethod
    def _skip_json_whitespace(raw: str, pos: int) -> int:
        limit = len(raw)
        while pos < limit and raw[pos] in {" ", "\t", "\r", "\n"}:
            pos += 1
        return pos

    @staticmethod
    def _parse_json_string_at(raw: str, pos: int) -> Tuple[Optional[str], int]:
        if pos < 0 or pos >= len(raw) or raw[pos] != '"':
            return None, pos
        idx = pos + 1
        escape = False
        while idx < len(raw):
            ch = raw[idx]
            if escape:
                escape = False
                idx += 1
                continue
            if ch == "\\":
                escape = True
                idx += 1
                continue
            if ch == '"':
                token = raw[pos : idx + 1]
                try:
                    return json.loads(token), idx + 1
                except Exception:
                    return None, idx + 1
            idx += 1
        return None, len(raw)

    @staticmethod
    def _find_balanced_json_end(raw: str, start: int) -> Optional[int]:
        if start < 0 or start >= len(raw):
            return None
        opener = raw[start]
        closer = "}" if opener == "{" else "]" if opener == "[" else ""
        if not closer:
            return None
        depth = 0
        in_string = False
        escape = False
        for idx in range(start, len(raw)):
            ch = raw[idx]
            if in_string:
                if escape:
                    escape = False
                    continue
                if ch == "\\":
                    escape = True
                    continue
                if ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
                continue
            if ch == opener:
                depth += 1
                continue
            if ch == closer:
                depth -= 1
                if depth == 0:
                    return idx + 1
        return None

    @classmethod
    def _recover_truncated_schema_fields(cls, raw: str) -> List[Dict[str, Any]]:
        anchor = raw.find('"fields"')
        if anchor < 0:
            return []
        array_start = raw.find("[", anchor)
        if array_start < 0:
            return []

        recovered: List[Dict[str, Any]] = []
        pos = array_start + 1
        while pos < len(raw):
            pos = cls._skip_json_whitespace(raw, pos)
            if pos >= len(raw) or raw[pos] == "]":
                break
            if raw[pos] == ",":
                pos += 1
                continue
            if raw[pos] != "{":
                pos += 1
                continue
            item_end = cls._find_balanced_json_end(raw, pos)
            if item_end is None:
                break
            try:
                item = json.loads(raw[pos:item_end])
            except Exception:
                pos = item_end
                continue
            if isinstance(item, dict):
                field_name = str(item.get("field_name") or "").strip()
                if field_name:
                    recovered.append(
                        {
                            "field_name": field_name,
                            "field_type": str(item.get("field_type") or "string").strip() or "string",
                        }
                    )
            pos = item_end
        return recovered

    @classmethod
    def _recover_truncated_field_map(cls, raw: str) -> Dict[str, Dict[str, Any]]:
        anchor = raw.find('"fields"')
        if anchor < 0:
            return {}
        object_start = raw.find("{", anchor)
        if object_start < 0:
            return {}

        recovered: Dict[str, Dict[str, Any]] = {}
        pos = object_start + 1
        while pos < len(raw):
            pos = cls._skip_json_whitespace(raw, pos)
            if pos >= len(raw) or raw[pos] == "}":
                break
            if raw[pos] == ",":
                pos += 1
                continue
            field_name, next_pos = cls._parse_json_string_at(raw, pos)
            if not field_name:
                pos += 1
                continue
            pos = cls._skip_json_whitespace(raw, next_pos)
            if pos >= len(raw) or raw[pos] != ":":
                break
            pos = cls._skip_json_whitespace(raw, pos + 1)
            if pos >= len(raw) or raw[pos] != "{":
                break
            value_end = cls._find_balanced_json_end(raw, pos)
            if value_end is None:
                break
            try:
                parsed_item = json.loads(raw[pos:value_end])
            except Exception:
                pos = value_end
                continue
            if isinstance(parsed_item, dict):
                recovered[str(field_name)] = parsed_item
            pos = value_end
        return recovered

    @staticmethod
    def _is_response_format_unsupported_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return "response_format" in text and (
            "unsupported" in text
            or "not support" in text
            or "unknown" in text
            or "invalid" in text
        )

    def _write_json_debug_artifact(
        self,
        *,
        purpose: str,
        provider: OpenAICompatibleChatProvider,
        token_budget: int,
        result: Any,
        note: str,
        messages: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        if self._debug_dir is None:
            return
        try:
            day_dir = self._debug_dir / datetime.now().strftime("%Y%m%d")
            day_dir.mkdir(parents=True, exist_ok=True)
            safe_purpose = re.sub(r"[^a-z0-9_.-]+", "_", str(purpose or "json").lower()).strip("_") or "json"
            safe_model = re.sub(r"[^a-z0-9_.-]+", "_", str(provider.model or "model").lower()).strip("_") or "model"
            stamp = datetime.now().strftime("%H%M%S_%f")
            target = day_dir / f"{stamp}_{safe_purpose}_{safe_model}.json"
            message_summary = []
            if messages:
                for item in messages:
                    if not isinstance(item, dict):
                        continue
                    content = str(item.get("content") or "")
                    message_summary.append(
                        {
                            "role": str(item.get("role") or ""),
                            "content_chars": len(content),
                            "content_preview": content[:320],
                        }
                    )
            target.write_text(
                json.dumps(
                    {
                        "purpose": purpose,
                        "note": note,
                        "model": provider.model,
                        "token_budget": token_budget,
                        "reasoning_effort": self._reasoning_effort,
                        "finish_reason": getattr(result, "finish_reason", ""),
                        "content": getattr(result, "content", ""),
                        "message_count": len(messages or []),
                        "prompt_chars": sum(len(str(item.get("content") or "")) for item in (messages or []) if isinstance(item, dict)),
                        "messages": message_summary,
                        "raw": getattr(result, "raw", {}),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except Exception:
            return

    @staticmethod
    def _payload_from_dict(payload: Dict[str, Any]) -> LLMExtractionPayload:
        normalized_payload = dict(payload or {})
        fields_raw = normalized_payload.get("fields")
        if isinstance(fields_raw, dict):
            normalized_fields: Dict[str, Dict[str, Any]] = {}
            for field_name, field_value in fields_raw.items():
                key = str(field_name or "").strip()
                if not key:
                    continue
                if isinstance(field_value, dict):
                    normalized_fields[key] = field_value
                else:
                    normalized_fields[key] = {
                        "value": field_value,
                        "ref_id": None,
                    }
            normalized_payload["fields"] = normalized_fields
        if hasattr(LLMExtractionPayload, "model_validate"):
            return LLMExtractionPayload.model_validate(normalized_payload)
        return LLMExtractionPayload.parse_obj(normalized_payload)

    @staticmethod
    def _is_model_not_found_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return "not_found" in text or "is not found" in text or "404" in text

    @staticmethod
    def _push_soft_warning(state: AgentState, message: str) -> None:
        msg = str(message or "").strip()
        if not msg:
            return
        warnings = list(state.get("soft_warnings", []))
        if msg not in warnings:
            warnings.append(msg)
        state["soft_warnings"] = warnings

    @staticmethod
    def _schema_keywords(target_fields: Dict[str, Any]) -> List[str]:
        keywords: List[str] = []
        for field_name in target_fields.keys():
            key = str(field_name).strip().lower()
            for alias in ExtractionGraph._field_aliases(key):
                keywords.append(alias)
            for token in re.split(r"[\s_\-/:,().]+", key):
                token = token.strip()
                if len(token) >= 2:
                    keywords.append(token)
        seen = set()
        unique: List[str] = []
        for kw in keywords:
            if kw in seen:
                continue
            seen.add(kw)
            unique.append(kw)
            if len(unique) >= 80:
                break
        return unique

    @staticmethod
    def _keyword_overlap_score(field_name: str, haystack: str) -> int:
        key = str(field_name).strip().lower()
        if not key:
            return 0
        score = 0
        aliases = ExtractionGraph._field_aliases(key)
        for alias in aliases:
            if alias and alias in haystack:
                score += 2
        for token in re.split(r"[\s_\-/:,().]+", key):
            token = token.strip()
            if len(token) >= 2 and token in haystack:
                score += 1
        return score

    @staticmethod
    def _field_aliases_legacy(field_name: str) -> List[str]:
        key = str(field_name or "").strip().lower()
        if not key:
            return []

        aliases = [key]
        alias_map = {
            "温度": ["temperature", "temp", "t"],
            "压力": ["pressure", "press", "p"],
            "浓度": ["concentration", "conc"],
            "流量": ["flow", "flowrate", "flow rate"],
            "时间": ["time", "duration"],
            "日期": ["date"],
            "物料": ["material", "component", "substance"],
            "材料": ["material", "component", "substance"],
            "组分": ["component", "composition"],
            "含量": ["content", "fraction"],
            "体积": ["volume", "vol"],
            "质量": ["mass", "weight", "wt"],
            "密度": ["density", "rho"],
            "速率": ["rate", "velocity"],
            "产率": ["yield"],
            "ph": ["ph", "acidity"],
            "作者": ["author"],
            "书名": ["title", "name"],
        }

        for zh, mapped in alias_map.items():
            if zh in key:
                aliases.extend(mapped)
        if "temperature" in key:
            aliases.extend(["温度", "temp", "t"])
        if "pressure" in key:
            aliases.extend(["压力", "press", "p"])
        if "concentration" in key:
            aliases.extend(["浓度", "conc"])
        if "flow" in key:
            aliases.extend(["流量", "flow rate"])
        if "material" in key or "substance" in key or "component" in key:
            aliases.extend(["物料", "材料", "组分"])

        seen: Set[str] = set()
        unique: List[str] = []
        for alias in aliases:
            text = alias.strip().lower()
            if not text or text in seen:
                continue
            seen.add(text)
            unique.append(text)
            if len(unique) >= 20:
                break
        return unique

    @staticmethod
    def _field_aliases(field_name: str) -> List[str]:
        key = str(field_name or "").strip().lower()
        if not key:
            return []

        aliases = [key]
        alias_map = {
            "\u6e29\u5ea6": ["temperature", "temp", "t"],
            "\u538b\u529b": ["pressure", "press", "p"],
            "\u6d53\u5ea6": ["concentration", "conc"],
            "\u6d41\u91cf": ["flow", "flowrate", "flow rate"],
            "\u65f6\u95f4": ["time", "duration"],
            "\u65e5\u671f": ["date"],
            "\u7269\u6599": ["material", "component", "substance"],
            "\u6750\u6599": ["material", "component", "substance"],
            "\u7ec4\u5206": ["component", "composition"],
            "\u542b\u91cf": ["content", "fraction"],
            "\u4f53\u79ef": ["volume", "vol"],
            "\u8d28\u91cf": ["mass", "weight", "wt"],
            "\u5bc6\u5ea6": ["density", "rho"],
            "\u901f\u7387": ["rate", "velocity"],
            "\u4ea7\u7387": ["yield"],
            "ph": ["ph", "acidity"],
            "\u4f5c\u8005": ["author"],
            "\u4e66\u540d": ["title", "name"],
        }

        for zh, mapped in alias_map.items():
            if zh in key:
                aliases.extend(mapped)
        if "temperature" in key:
            aliases.extend(["\u6e29\u5ea6", "temp", "t"])
        if "pressure" in key:
            aliases.extend(["\u538b\u529b", "press", "p"])
        if "concentration" in key:
            aliases.extend(["\u6d53\u5ea6", "conc"])
        if "flow" in key:
            aliases.extend(["\u6d41\u91cf", "flow rate"])
        if "material" in key or "substance" in key or "component" in key:
            aliases.extend(["\u7269\u6599", "\u6750\u6599", "\u7ec4\u5206"])

        seen: Set[str] = set()
        unique: List[str] = []
        for alias in aliases:
            text = alias.strip().lower()
            if not text or text in seen:
                continue
            seen.add(text)
            unique.append(text)
            if len(unique) >= 20:
                break
        return unique

    @staticmethod
    def _results_summary(results: Dict[str, Dict[str, Any]]) -> str:
        max_items = max(6, int(os.getenv("MODULE2_RESULTS_SUMMARY_MAX_ITEMS", "12")))
        max_chars = max(400, int(os.getenv("MODULE2_RESULTS_SUMMARY_MAX_CHARS", "2400")))
        chunks: List[str] = []
        for idx, (field_name, value) in enumerate(results.items()):
            if idx >= max_items:
                break
            chunks.append(
                f"{field_name}: value={value.get('value')}, ref_id={value.get('source_ref_id')}, "
                f"confidence={value.get('confidence')}"
            )
        joined = "\n".join(chunks) if chunks else "None"
        if len(joined) <= max_chars:
            return joined
        return joined[:max_chars]

    @staticmethod
    def _validate_type(value: Any, expected: Any) -> bool:
        expected_str = str(expected).lower()
        if expected_str in {"string", "str", "text"}:
            return isinstance(value, str)
        if expected_str in {"number", "float", "double"}:
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if expected_str in {"integer", "int"}:
            return isinstance(value, int) and not isinstance(value, bool)
        if expected_str in {"boolean", "bool"}:
            return isinstance(value, bool)
        if expected_str in {"array", "list"}:
            return isinstance(value, list)
        if expected_str in {"object", "dict", "json"}:
            return isinstance(value, dict)
        return True

    @staticmethod
    def _validate_date_order(results: Dict[str, Dict[str, Any]]) -> Optional[str]:
        lower_map = {k.lower(): v for k, v in results.items()}
        start_key = next((k for k in lower_map if "start" in k and "date" in k), None)
        end_key = next((k for k in lower_map if "end" in k and "date" in k), None)
        if not start_key or not end_key:
            return None

        start_val = lower_map[start_key].get("value")
        end_val = lower_map[end_key].get("value")
        if start_val is None or end_val is None:
            return None

        start_dt = ExtractionGraph._parse_datetime(start_val)
        end_dt = ExtractionGraph._parse_datetime(end_val)
        if not start_dt or not end_dt:
            return None
        if start_dt >= end_dt:
            return "Business rule violation: Start Date must be earlier than End Date"
        return None

    @staticmethod
    def _coerce_value(value: Any, expected: Any) -> Tuple[Any, bool]:
        if value is None:
            return None, False

        expected_str = str(expected).lower()
        if expected_str in {"string", "str", "text"}:
            if isinstance(value, str):
                return value, False
            return str(value), True

        if expected_str in {"number", "float", "double"}:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value), False
            if isinstance(value, str):
                cleaned = re.sub(r"[,\s$\u00a5\uffe5\uff0c]", "", value).strip()
                cleaned = cleaned[:-1] if cleaned.endswith(("%", "\uff05")) else cleaned
                try:
                    return float(cleaned), True
                except ValueError:
                    return value, False
            return value, False

        if expected_str in {"integer", "int"}:
            if isinstance(value, int) and not isinstance(value, bool):
                return value, False
            if isinstance(value, float):
                return int(value), True
            if isinstance(value, str):
                cleaned = re.sub(r"[,\s$\u00a5\uffe5\uff0c]", "", value).strip()
                cleaned = cleaned[:-1] if cleaned.endswith(("%", "\uff05")) else cleaned
                try:
                    return int(float(cleaned)), True
                except ValueError:
                    return value, False
            return value, False

        if expected_str in {"boolean", "bool"}:
            if isinstance(value, bool):
                return value, False
            if isinstance(value, str):
                v = value.strip().lower()
                if v in {"true", "yes", "y", "1", "\u662f", "\u6709", "\u5df2"}:
                    return True, True
                if v in {"false", "no", "n", "0", "\u5426", "\u65e0", "\u672a"}:
                    return False, True
            return value, False

        if expected_str in {"array", "list"} and isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed, True
            except json.JSONDecodeError:
                return value, False

        if expected_str in {"object", "dict", "json"} and isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, dict):
                    return parsed, True
            except json.JSONDecodeError:
                return value, False

        return value, False

    @staticmethod
    def _estimate_confidence(value: Any, expected: Any, ref_valid: bool, coerced: bool) -> float:
        if value is None:
            return 0.0
        score = 0.45
        if ref_valid:
            score += 0.35
        if ExtractionGraph._validate_type(value, expected):
            score += 0.15
        if not coerced:
            score += 0.05
        return min(score, 0.98)

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        text = str(value).strip()
        if not text:
            return None

        normalized = text.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            pass

        formats = (
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y.%m.%d",
            "%Y\u5e74%m\u6708%d\u65e5",
            "%Y-%m-%d %H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y.%m.%d %H:%M:%S",
            "%Y\u5e74%m\u6708%d\u65e5 %H:%M:%S",
        )
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None
