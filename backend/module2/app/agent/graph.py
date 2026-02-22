from __future__ import annotations

import json
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, Set, Tuple, TypedDict

from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field


SYSTEM_PROMPT = """You are an expert Data Extraction Agent.
You extract structured fields from markdown that uses <ref id="..."> blocks.
Every extracted value must be grounded to an exact ref_id.
If uncertain or not found, return null.
"""

TABLE_SYSTEM_PROMPT = """You are an expert table extraction agent.
You receive structured table JSON and must extract target fields from table cells first.
Return only fields that can be grounded to existing table cell ref_id values.
Do not invent ref_id.
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
    retries: int
    max_retries: int


class ExtractionGraph:
    def __init__(self, llm: Optional[ChatGoogleGenerativeAI] = None) -> None:
        temperature = float(os.getenv("MODULE2_LLM_TEMPERATURE", "0"))
        primary_model = os.getenv("MODULE2_LLM_MODEL", "gemini-2.0-flash")
        fallback_models = [
            m.strip()
            for m in os.getenv(
                "MODULE2_LLM_MODEL_FALLBACKS",
                "gemini-2.5-flash,gemini-2.0-flash-lite,gemini-1.5-flash-latest",
            ).split(",")
            if m.strip()
        ]
        self._model_candidates = [primary_model] + [m for m in fallback_models if m != primary_model]
        self._temperature = temperature

        self.llm = llm or ChatGoogleGenerativeAI(model=primary_model, temperature=temperature)
        self.structured_llm = self.llm.with_structured_output(LLMExtractionPayload)
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

        table_context = self._build_table_context(tables, state.get("field_hints", {}), focus_fields)
        if not table_context:
            return state

        max_table_refs = max(300, int(os.getenv("MODULE2_TABLE_ALLOWED_REFS_MAX", "1200")))
        allowed_table_refs = self._collect_table_ref_ids(tables, max_refs=max_table_refs)
        if not allowed_table_refs:
            return state

        correction_context = "\n".join(state["errors"][-5:]) if state["errors"] else "None"
        correction_fields = sorted(error_fields) if error_fields else []
        user_prompt = (
            "Table profile summary:\n"
            f"{state.get('table_summary', '')}\n\n"
            "Target Schema:\n"
            f"{json.dumps(focus_fields, ensure_ascii=False)}\n\n"
            "Fields requiring correction first:\n"
            f"{json.dumps(correction_fields, ensure_ascii=False)}\n\n"
            "Table context JSON:\n"
            f"{table_context}\n\n"
            "Allowed table ref_id candidates:\n"
            f"{json.dumps(allowed_table_refs, ensure_ascii=False)}\n\n"
            "Previous validation errors to correct:\n"
            f"{correction_context}\n\n"
            "Return strictly as JSON using: {\"fields\": {field_name: {\"value\": ..., \"ref_id\": ...}}}."
        )

        payload = await self._invoke_with_model_fallback(
            [
                {"role": "system", "content": TABLE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
        )

        max_field_chars = max(80, int(os.getenv("MODULE2_MAX_FIELD_CHARS", "300")))
        table_ref_lookup = self._table_ref_lookup(tables)

        for field_name in focus_fields.keys():
            existing = extracted.get(field_name, {})
            if (
                field_name not in error_fields
                and existing.get("value") is not None
                and existing.get("source_ref_id") in state["bbox_map"]
            ):
                continue

            expected_type = focus_fields.get(field_name)
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
        compact_markdown = self._build_context(state["markdown"], pending_fields)
        max_allowed_refs = max(260, int(os.getenv("MODULE2_ALLOWED_REFS_MAX", "1200")))
        allowed_refs = list(state["bbox_map"].keys())[:max_allowed_refs]
        prev_summary = self._results_summary(existing)
        correction_fields = sorted(error_fields) if error_fields else []

        user_prompt = (
            "Document Markdown:\n"
            f"{compact_markdown}\n\n"
            "Target Schema:\n"
            f"{json.dumps(pending_fields, ensure_ascii=False)}\n\n"
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
            "Return strictly as JSON using: {\"fields\": {field_name: {\"value\": ..., \"ref_id\": ...}}}.\n"
            "Do not fabricate values or ref_id. If missing, set value/ref_id to null."
        )

        payload = await self._invoke_with_model_fallback(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
        )

        max_field_chars = max(80, int(os.getenv("MODULE2_MAX_FIELD_CHARS", "300")))
        for field_name in pending_fields.keys():
            if field_name not in error_fields and existing.get(field_name, {}).get("value") is not None:
                continue

            expected_type = pending_fields.get(field_name)
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
        max_chars = max(2000, int(os.getenv("MODULE2_PROMPT_MAX_CHARS", "32000")))
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
        for score, _, ref_id, text in sorted(ranked, key=lambda x: (-x[0], x[1])):
            if score <= 0:
                continue
            segment = f'<ref id="{ref_id}">{text}</ref>'
            add_len = len(segment) + 1
            if size + add_len > max_chars:
                continue
            picked.append(segment)
            size += add_len

        chosen = {re.search(r'<ref id="([^"]+)">', row).group(1) for row in picked} if picked else set()
        if size < max_chars:
            for _, _, ref_id, text in ranked:
                if ref_id in chosen:
                    continue
                segment = f'<ref id="{ref_id}">{text}</ref>'
                add_len = len(segment) + 1
                if size + add_len > max_chars:
                    break
                picked.append(segment)
                size += add_len

        return "\n".join(picked) if picked else markdown[:max_chars]

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

        preferred_ids: List[str] = []
        for field_name in target_fields.keys():
            for table_id in field_hints.get(field_name, []):
                if table_id not in preferred_ids:
                    preferred_ids.append(table_id)

        selected: List[Dict[str, Any]] = []
        for table_id in preferred_ids:
            table = next((t for t in table_blocks if str(t.get("table_id")) == table_id), None)
            if table:
                selected.append(table)
            if len(selected) >= max_tables:
                break

        if len(selected) < max_tables:
            for table in table_blocks:
                if table in selected:
                    continue
                selected.append(table)
                if len(selected) >= max_tables:
                    break

        compact: List[Dict[str, Any]] = []
        for table in selected:
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
                for cell in row.get("cells", [])[:max_cols]:
                    cell_text = str(cell.get("text", "")).strip()
                    if not cell_text:
                        continue
                    payload: Dict[str, Any] = {
                        "col_index": cell.get("col_index"),
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
                    normalized_raw = cell.get("normalized_text")
                    normalized_text = normalized_raw.strip() if isinstance(normalized_raw, str) else ""
                    if normalized_text and normalized_text.lower() not in {"none", "null"} and normalized_text != cell_text:
                        payload["normalized_text"] = normalized_text
                    numeric_value = cell.get("numeric_value")
                    if numeric_value is not None:
                        payload["numeric_value"] = numeric_value
                    ratio_value = cell.get("ratio_value")
                    if ratio_value is not None:
                        payload["ratio_value"] = ratio_value
                    detected_raw = cell.get("detected_unit")
                    detected_unit = detected_raw.strip() if isinstance(detected_raw, str) else ""
                    if detected_unit and detected_unit.lower() not in {"none", "null"}:
                        payload["detected_unit"] = detected_unit
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
                    "headers": table.get("headers", [])[:max_cols],
                    "header_meta": header_meta,
                    "row_count": table.get("row_count"),
                    "col_count": table.get("col_count"),
                    "rows": rows,
                }
            )
        return json.dumps(compact, ensure_ascii=False)

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

    async def _invoke_with_model_fallback(self, messages: List[Dict[str, str]]) -> LLMExtractionPayload:
        try:
            return await self.structured_llm.ainvoke(messages)
        except Exception as exc:
            if not self._is_model_not_found_error(exc):
                raise
            last_exc: Exception = exc

        for model_name in self._model_candidates[1:]:
            self.llm = ChatGoogleGenerativeAI(model=model_name, temperature=self._temperature)
            self.structured_llm = self.llm.with_structured_output(LLMExtractionPayload)
            try:
                return await self.structured_llm.ainvoke(messages)
            except Exception as exc:
                last_exc = exc
                if self._is_model_not_found_error(exc):
                    continue
                raise

        raise last_exc

    @staticmethod
    def _is_model_not_found_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return "not_found" in text or "is not found" in text or "404" in text

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
        chunks: List[str] = []
        for idx, (field_name, value) in enumerate(results.items()):
            if idx >= 30:
                break
            chunks.append(
                f"{field_name}: value={value.get('value')}, ref_id={value.get('source_ref_id')}, "
                f"confidence={value.get('confidence')}"
            )
        return "\n".join(chunks) if chunks else "None"

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
