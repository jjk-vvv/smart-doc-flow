from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from html import escape
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from fastapi import HTTPException

from ..table.table_metadata import build_header_meta, decorate_rows_with_meta, normalize_text


@dataclass(frozen=True)
class DirectSemanticExtractOutcome:
    marked_markdown: str
    bbox_map: Dict[str, Any]
    table_blocks: List[Dict[str, Any]]
    naming_template: str
    schema_context_preview: str
    allow_schema_llm: bool
    effective_schema: Dict[str, Any]
    schema_meta: Dict[str, Any]
    effective_schema_fields: Dict[str, Any]
    dynamic_extract_timeout_meta: Dict[str, Any]
    file_size_mb: float
    final_state: Dict[str, Any]
    extract_ms: int
    used_quick_fallback: bool


class DirectSemanticExtractRuntime:
    """Run a lightweight LLM-first extraction path for txt/md/xlsx inputs."""

    _TEXT_EXTS = {".txt", ".md", ".markdown"}
    _SPREADSHEET_EXTS = {".xlsx"}
    _SUPPORTED_EXTS = _TEXT_EXTS | _SPREADSHEET_EXTS

    def __init__(
        self,
        *,
        graph: Any,
        extraction_llm_semaphore: Any,
        schema_target_fields: Callable[[Dict[str, Any]], Dict[str, Any]],
        normalize_schema_fields: Callable[[Dict[str, Any], int], Dict[str, str]],
        schema_auto_infer_requested: Callable[[Dict[str, Any]], bool],
        sanitize_field_name: Callable[[Any], str],
        coerce_field_type: Callable[[Any], str],
        upsert_schema_field_candidate: Callable[[Dict[str, str], Any, Any, bool], None],
        filter_auto_schema_fields: Callable[[Dict[str, Any], int], Dict[str, str]],
        detect_domain_template: Callable[..., str],
        extract_text_for_schema: Callable[[str, List[Dict[str, Any]], Optional[List[Dict[str, Any]]], int], str],
        getenv: Callable[[str, str], Any] = os.getenv,
        perf_counter: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._graph = graph
        self._extraction_llm_semaphore = extraction_llm_semaphore
        self._schema_target_fields = schema_target_fields
        self._normalize_schema_fields = normalize_schema_fields
        self._schema_auto_infer_requested = schema_auto_infer_requested
        self._sanitize_field_name = sanitize_field_name
        self._coerce_field_type = coerce_field_type
        self._upsert_schema_field_candidate = upsert_schema_field_candidate
        self._filter_auto_schema_fields = filter_auto_schema_fields
        self._detect_domain_template = detect_domain_template
        self._extract_text_for_schema = extract_text_for_schema
        self._getenv = getenv
        self._perf_counter = perf_counter

    @classmethod
    def supports(cls, file_name: str) -> bool:
        normalized = str(file_name or "").strip().lower()
        return any(normalized.endswith(ext) for ext in cls._SUPPORTED_EXTS)

    async def execute(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        marked_markdown: str,
        bbox_map: Dict[str, Any],
        table_blocks: List[Dict[str, Any]],
        figure_blocks: List[Dict[str, Any]],
        requested_schema: Dict[str, Any],
        extract_timeout_sec: float,
        emit_progress,
        logger,
    ) -> DirectSemanticExtractOutcome:
        normalized_name = str(file_name or "").strip()
        lowered_name = normalized_name.lower()
        is_spreadsheet = lowered_name.endswith(tuple(self._SPREADSHEET_EXTS))
        route_kind = "direct_spreadsheet_semantic" if is_spreadsheet else "direct_text_semantic"

        requested_fields_raw = self._schema_target_fields(requested_schema)
        auto_infer = self._schema_auto_infer_requested(requested_schema)
        manual_field_cap = self._manual_field_cap()
        normalized_requested_fields = self._normalize_schema_fields(
            requested_fields_raw,
            max_fields=max(manual_field_cap, len(requested_fields_raw) or manual_field_cap),
        )
        manual_lookup = {
            self._sanitize_field_name(field_name): field_name
            for field_name in normalized_requested_fields.keys()
            if self._sanitize_field_name(field_name)
        }
        manual_mode = bool(normalized_requested_fields) and not auto_infer

        naming_template = self._detect_domain_template(
            file_name=normalized_name,
            markdown=marked_markdown,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
        )
        file_size_mb = len(file_bytes) / (1024.0 * 1024.0)
        schema_context_preview = self._extract_text_for_schema(
            marked_markdown,
            table_blocks,
            figure_blocks,
            max_chars=self._schema_context_chars_cap(is_spreadsheet=is_spreadsheet),
        )
        route_context = self._build_route_context(
            file_name=normalized_name,
            marked_markdown=marked_markdown,
            table_blocks=table_blocks,
            is_spreadsheet=is_spreadsheet,
        )
        allowed_refs = self._collect_allowed_refs(
            bbox_map=bbox_map,
            table_blocks=table_blocks,
            is_spreadsheet=is_spreadsheet,
        )
        auto_field_cap = self._auto_field_cap(requested_schema=requested_schema, is_spreadsheet=is_spreadsheet)
        supplemental_table_cap = self._supplemental_table_cap()

        await emit_progress(
            "extracting",
            0.80,
            "正在执行轻量语义抽取，直接分析文本/表格并生成关键字段",
        )

        prompt_messages = self._build_prompt_messages(
            file_name=normalized_name,
            route_kind=route_kind,
            route_context=route_context,
            table_blocks=table_blocks,
            allowed_refs=allowed_refs,
            requested_fields=normalized_requested_fields,
            manual_mode=manual_mode,
            auto_field_cap=auto_field_cap,
            supplemental_table_cap=supplemental_table_cap,
        )

        extract_started_at = self._perf_counter()
        async with self._extraction_llm_semaphore:
            try:
                payload = await asyncio.wait_for(
                    self._graph.invoke_json_object(
                        prompt_messages,
                        max_tokens=self._max_output_tokens(),
                        purpose="direct_semantic_extract",
                    ),
                    timeout=max(12.0, float(extract_timeout_sec or 0.0)),
                )
            except asyncio.TimeoutError as exc:
                raise HTTPException(
                    status_code=504,
                    detail=f"Direct semantic extraction timed out for {normalized_name}",
                ) from exc
            except Exception as exc:
                raise HTTPException(
                    status_code=500,
                    detail=f"Direct semantic extraction failed for {normalized_name}: {exc}",
                ) from exc

        payload_fields = self._normalize_field_items(payload.get("fields"))
        if manual_mode:
            results, effective_schema_fields = self._build_manual_results(
                payload_fields=payload_fields,
                requested_fields=normalized_requested_fields,
                manual_lookup=manual_lookup,
                bbox_map=bbox_map,
            )
        else:
            results, effective_schema_fields = self._build_auto_results(
                payload_fields=payload_fields,
                bbox_map=bbox_map,
                auto_field_cap=auto_field_cap,
            )

        supplemental_tables_added = 0
        updated_markdown = marked_markdown
        updated_bbox_map = dict(bbox_map or {})
        updated_table_blocks = list(table_blocks or [])
        if (not is_spreadsheet) and not updated_table_blocks:
            supplemental_tables = self._normalize_table_items(payload.get("tables"))
            if supplemental_tables:
                updated_markdown, updated_bbox_map, updated_table_blocks, supplemental_tables_added = (
                    self._append_supplemental_tables(
                        marked_markdown=updated_markdown,
                        bbox_map=updated_bbox_map,
                        existing_table_blocks=updated_table_blocks,
                        tables=supplemental_tables[:supplemental_table_cap],
                    )
                )

        final_state = {
            "results": results,
            "errors": [],
            "soft_warnings": self._build_soft_warnings(
                route_kind=route_kind,
                manual_mode=manual_mode,
                results=results,
                supplemental_tables_added=supplemental_tables_added,
            ),
            "retries": 0,
            "max_retries": 0,
        }

        effective_schema = {
            "fields": effective_schema_fields,
            "field_meta": {},
        }
        schema_meta = {
            "mode": "manual" if manual_mode else "auto",
            "source": route_kind,
            "route_kind": route_kind,
            "field_count": len(effective_schema_fields),
            "fields": list(effective_schema_fields.keys()),
            "raw_fields": list(effective_schema_fields.keys()),
            "naming_template": naming_template,
            "direct_semantic": True,
            "manual_mode": manual_mode,
            "auto_field_cap": auto_field_cap,
            "supplemental_tables_added": supplemental_tables_added,
        }
        dynamic_extract_timeout_meta = {
            "applied": False,
            "reason": "direct_semantic_route",
            "route_kind": route_kind,
            "context_chars": len(route_context),
            "allowed_ref_count": len(allowed_refs),
            "manual_mode": manual_mode,
            "auto_field_cap": auto_field_cap,
        }

        extract_ms = int((self._perf_counter() - extract_started_at) * 1000)
        logger.info(
            "module2 direct semantic finished file=%s route=%s manual=%s fields=%s tables=%s extract_ms=%s",
            normalized_name,
            route_kind,
            manual_mode,
            len(results),
            len(updated_table_blocks),
            extract_ms,
        )

        return DirectSemanticExtractOutcome(
            marked_markdown=updated_markdown,
            bbox_map=updated_bbox_map,
            table_blocks=updated_table_blocks,
            naming_template=naming_template,
            schema_context_preview=schema_context_preview,
            allow_schema_llm=False,
            effective_schema=effective_schema,
            schema_meta=schema_meta,
            effective_schema_fields=effective_schema_fields,
            dynamic_extract_timeout_meta=dynamic_extract_timeout_meta,
            file_size_mb=file_size_mb,
            final_state=final_state,
            extract_ms=extract_ms,
            used_quick_fallback=False,
        )

    def _build_prompt_messages(
        self,
        *,
        file_name: str,
        route_kind: str,
        route_context: str,
        table_blocks: List[Dict[str, Any]],
        allowed_refs: List[str],
        requested_fields: Dict[str, str],
        manual_mode: bool,
        auto_field_cap: int,
        supplemental_table_cap: int,
    ) -> List[Dict[str, str]]:
        table_presence = "present" if table_blocks else "absent"
        system_prompt = (
            "You are a grounded semantic extraction engine for plain text, markdown, and spreadsheet documents. "
            "Read the provided context directly and extract only fields that are supported by the document. "
            "Never pad to a target count. Never invent missing values. "
            "Use the original document language for field_name whenever possible. "
            "If a ref_id is not grounded in the provided context, return null for ref_id. "
            "For spreadsheet content, prioritize primary dimensions, key metrics, totals, ratios, and time periods. "
            "Ignore helper columns, filler labels, and low-value notes unless they are actual business fields."
        )
        if manual_mode:
            instruction_block = (
                "Extraction mode: manual\n"
                "Extract exactly the requested fields below. Keep field_name exactly the same as the requested name. "
                "If a field is missing, return value=null and ref_id=null."
            )
        else:
            instruction_block = (
                "Extraction mode: auto\n"
                "Return every grounded, non-trivial key field you can support, but do not aim for any default field count. "
                f"Technical output cap: at most {auto_field_cap} fields."
            )

        tables_instruction = ""
        if not table_blocks and route_kind == "direct_text_semantic":
            tables_instruction = (
                "If the content clearly contains an embedded table that is not already structured, "
                f"you may return up to {supplemental_table_cap} supplemental tables in the tables array."
            )

        user_prompt = (
            f"File name: {file_name}\n"
            f"Route kind: {route_kind}\n"
            f"Structured table blocks already detected: {table_presence}\n"
            f"{instruction_block}\n"
            f"{tables_instruction}\n\n"
            "Requested fields JSON:\n"
            f"{json.dumps(requested_fields, ensure_ascii=False)}\n\n"
            "Allowed ref_id candidates:\n"
            f"{json.dumps(allowed_refs, ensure_ascii=False)}\n\n"
            "Document context:\n"
            f"{route_context}\n\n"
            "Return JSON only in the following shape:\n"
            "{\n"
            '  "fields": [\n'
            '    {"field_name": "...", "field_type": "string|number|integer|date|boolean", "value": ..., "ref_id": "...", "confidence": 0.0},\n'
            "    ...\n"
            "  ],\n"
            '  "tables": [\n'
            '    {"title": "...", "headers": ["..."], "rows": [["...", "..."]]},\n'
            "    ...\n"
            "  ]\n"
            "}\n"
        )
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    def _build_route_context(
        self,
        *,
        file_name: str,
        marked_markdown: str,
        table_blocks: List[Dict[str, Any]],
        is_spreadsheet: bool,
    ) -> str:
        max_chars = self._route_context_chars_cap(is_spreadsheet=is_spreadsheet)
        if is_spreadsheet:
            return self._serialize_table_context(table_blocks=table_blocks, max_chars=max_chars)

        base_text = str(marked_markdown or "").strip()
        if len(base_text) <= max_chars:
            return base_text
        head_chars = max(1200, int(max_chars * 0.65))
        tail_chars = max(600, max_chars - head_chars - 16)
        return f"{base_text[:head_chars]}\n...\n{base_text[-tail_chars:]}"

    def _serialize_table_context(self, *, table_blocks: List[Dict[str, Any]], max_chars: int) -> str:
        tables_payload: List[Dict[str, Any]] = []
        max_tables = max(1, int(self._getenv("MODULE2_DIRECT_SEMANTIC_TABLE_MAX_TABLES", "6") or "6"))
        max_rows = max(1, int(self._getenv("MODULE2_DIRECT_SEMANTIC_TABLE_MAX_ROWS", "10") or "10"))
        max_cols = max(1, int(self._getenv("MODULE2_DIRECT_SEMANTIC_TABLE_MAX_COLS", "8") or "8"))
        for table in (table_blocks or [])[:max_tables]:
            rows_out: List[List[Dict[str, Any]]] = []
            for row in list(table.get("rows") or [])[:max_rows]:
                cells_out: List[Dict[str, Any]] = []
                for cell in list(row.get("cells") or [])[:max_cols]:
                    cell_text = normalize_text(str(cell.get("text") or ""))
                    if not cell_text:
                        continue
                    cells_out.append(
                        {
                            "header": str(cell.get("header") or "").strip(),
                            "text": cell_text,
                            "ref_id": str(cell.get("ref_id") or "").strip(),
                        }
                    )
                if cells_out:
                    rows_out.append(cells_out)
            if not rows_out:
                continue
            tables_payload.append(
                {
                    "table_id": str(table.get("table_id") or "").strip(),
                    "source": str(table.get("source") or "").strip(),
                    "headers": list(table.get("headers") or [])[:max_cols],
                    "rows": rows_out,
                }
            )
        serialized = json.dumps(tables_payload, ensure_ascii=False)
        if len(serialized) <= max_chars:
            return serialized
        return serialized[:max_chars]

    def _collect_allowed_refs(
        self,
        *,
        bbox_map: Dict[str, Any],
        table_blocks: List[Dict[str, Any]],
        is_spreadsheet: bool,
    ) -> List[str]:
        max_refs = max(24, int(self._getenv("MODULE2_DIRECT_SEMANTIC_MAX_REFS", "240") or "240"))
        refs: List[str] = []
        seen: set[str] = set()
        if is_spreadsheet:
            for table in table_blocks or []:
                for row in table.get("rows") or []:
                    for cell in row.get("cells") or []:
                        ref_id = str(cell.get("ref_id") or "").strip()
                        if not ref_id or ref_id in seen:
                            continue
                        seen.add(ref_id)
                        refs.append(ref_id)
                        if len(refs) >= max_refs:
                            return refs
        for ref_id in (bbox_map or {}).keys():
            key = str(ref_id or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            refs.append(key)
            if len(refs) >= max_refs:
                break
        return refs

    @staticmethod
    def _normalize_field_items(raw_fields: Any) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        if isinstance(raw_fields, dict):
            for name, value in raw_fields.items():
                if isinstance(value, dict):
                    item = dict(value)
                    item.setdefault("field_name", name)
                    items.append(item)
                else:
                    items.append({"field_name": name, "value": value})
            return items
        if isinstance(raw_fields, list):
            for item in raw_fields:
                if isinstance(item, dict):
                    items.append(dict(item))
            return items
        return items

    @staticmethod
    def _normalize_table_items(raw_tables: Any) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        if not isinstance(raw_tables, list):
            return out
        for item in raw_tables:
            if not isinstance(item, dict):
                continue
            headers = item.get("headers") if isinstance(item.get("headers"), list) else []
            rows = item.get("rows") if isinstance(item.get("rows"), list) else []
            if len(headers) < 2 or not rows:
                continue
            out.append(
                {
                    "title": str(item.get("title") or "").strip(),
                    "headers": [normalize_text(str(cell or "")) for cell in headers if normalize_text(str(cell or ""))],
                    "rows": [
                        [normalize_text(str(cell or "")) for cell in row if normalize_text(str(cell or ""))]
                        for row in rows
                        if isinstance(row, list)
                    ],
                }
            )
        return out

    def _build_manual_results(
        self,
        *,
        payload_fields: List[Dict[str, Any]],
        requested_fields: Dict[str, str],
        manual_lookup: Dict[str, str],
        bbox_map: Dict[str, Any],
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
        results: Dict[str, Dict[str, Any]] = {}
        for item in payload_fields:
            raw_name = str(item.get("field_name") or item.get("name") or "").strip()
            lookup_key = self._sanitize_field_name(raw_name)
            if not lookup_key or lookup_key not in manual_lookup:
                continue
            field_name = manual_lookup[lookup_key]
            expected_type = requested_fields.get(field_name, "string")
            entity = self._build_entity_from_payload(
                item=item,
                expected_type=expected_type,
                bbox_map=bbox_map,
            )
            results[field_name] = entity
        for field_name, field_type in requested_fields.items():
            results.setdefault(
                field_name,
                {
                    "value": None,
                    "confidence": 0.0,
                    "source_ref_id": None,
                    "bbox": [],
                },
            )
        return results, dict(requested_fields)

    def _build_auto_results(
        self,
        *,
        payload_fields: List[Dict[str, Any]],
        bbox_map: Dict[str, Any],
        auto_field_cap: int,
    ) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
        results: Dict[str, Dict[str, Any]] = {}
        schema_fields: Dict[str, str] = {}
        for item in payload_fields:
            raw_name = item.get("field_name") or item.get("name")
            normalized_name = self._sanitize_field_name(raw_name)
            if not normalized_name:
                continue
            raw_type = item.get("field_type") or item.get("type") or self._infer_field_type(item.get("value"))
            self._upsert_schema_field_candidate(
                schema_fields,
                normalized_name,
                raw_type,
                True,
            )
            field_name = self._resolve_canonical_field_name(schema_fields, normalized_name)
            entity = self._build_entity_from_payload(
                item=item,
                expected_type=schema_fields.get(field_name, self._coerce_field_type(raw_type)),
                bbox_map=bbox_map,
            )
            if not self._has_meaningful_value(entity.get("value")):
                continue
            results[field_name] = entity
            if len(results) >= auto_field_cap:
                break
        filtered_fields = self._filter_auto_schema_fields(schema_fields, max_fields=auto_field_cap)
        filtered_results = {
            field_name: results[field_name]
            for field_name in filtered_fields.keys()
            if field_name in results
        }
        filtered_fields = {
            field_name: filtered_fields[field_name]
            for field_name in filtered_results.keys()
        }
        return filtered_results, filtered_fields

    def _build_entity_from_payload(
        self,
        *,
        item: Dict[str, Any],
        expected_type: Any,
        bbox_map: Dict[str, Any],
    ) -> Dict[str, Any]:
        raw_value = item.get("value")
        coerced_value, coerced = self._graph._coerce_value(raw_value, expected_type)
        ref_id = str(item.get("ref_id") or "").strip() or None
        ref_valid = bool(ref_id and ref_id in bbox_map)
        if not ref_valid:
            ref_id = None
        raw_confidence = item.get("confidence")
        confidence = self._safe_confidence(raw_confidence)
        if confidence <= 0.0:
            confidence = self._graph._estimate_confidence(coerced_value, expected_type, ref_valid, coerced)
        bbox = list(bbox_map.get(ref_id, [])) if ref_id else []
        return {
            "value": coerced_value,
            "confidence": confidence,
            "source_ref_id": ref_id,
            "bbox": bbox,
        }

    def _append_supplemental_tables(
        self,
        *,
        marked_markdown: str,
        bbox_map: Dict[str, Any],
        existing_table_blocks: List[Dict[str, Any]],
        tables: Sequence[Dict[str, Any]],
    ) -> Tuple[str, Dict[str, Any], List[Dict[str, Any]], int]:
        updated_markdown = str(marked_markdown or "")
        updated_bbox_map = dict(bbox_map or {})
        updated_table_blocks = list(existing_table_blocks or [])
        table_index = 1
        for item in updated_table_blocks:
            table_id = str(item.get("table_id") or "").strip().lower()
            if table_id.startswith("semantic_t"):
                try:
                    table_index = max(table_index, int(table_id.replace("semantic_t", "")) + 1)
                except ValueError:
                    continue

        added = 0
        for table in tables:
            headers = [normalize_text(str(cell or "")) for cell in list(table.get("headers") or []) if normalize_text(str(cell or ""))]
            rows_raw = [
                [normalize_text(str(cell or "")) for cell in row if normalize_text(str(cell or ""))]
                for row in list(table.get("rows") or [])
                if isinstance(row, list)
            ]
            rows_raw = [row for row in rows_raw if row]
            if len(headers) < 2 or not rows_raw:
                continue
            table_id = f"semantic_t{table_index}"
            table_index += 1
            rows_payload: List[Dict[str, Any]] = []
            for row_idx, row_cells in enumerate(rows_raw, start=1):
                cells_payload: List[Dict[str, Any]] = []
                for col_idx, cell_text in enumerate(row_cells[: len(headers)], start=1):
                    if not cell_text:
                        continue
                    ref_id = f"{table_id}_r{row_idx}_c{col_idx}"
                    updated_markdown = f"{updated_markdown}\n<ref id=\"{ref_id}\">{escape(cell_text)}</ref>"
                    updated_bbox_map[ref_id] = [1.0, 0.0, 0.0, 1.0, 1.0]
                    cells_payload.append(
                        {
                            "col_index": col_idx,
                            "text": cell_text,
                            "ref_id": ref_id,
                            "bbox": [1.0, 0.0, 0.0, 1.0, 1.0],
                        }
                    )
                if cells_payload:
                    rows_payload.append({"row_index": row_idx, "cells": cells_payload})
            if not rows_payload:
                continue
            decorated_rows = decorate_rows_with_meta(rows_payload, headers)
            updated_table_blocks.append(
                {
                    "table_id": table_id,
                    "source": "semantic",
                    "page": 1,
                    "headers": headers,
                    "header_meta": build_header_meta(headers),
                    "rows": decorated_rows,
                    "row_count": len(decorated_rows),
                    "col_count": max((len(row.get("cells", [])) for row in decorated_rows), default=0),
                    "quality": 0.74,
                    "caption": str(table.get("title") or "").strip(),
                }
            )
            added += 1
        return updated_markdown, updated_bbox_map, updated_table_blocks, added

    @staticmethod
    def _safe_confidence(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    def _resolve_canonical_field_name(self, schema_fields: Dict[str, str], normalized_name: str) -> str:
        key = self._sanitize_field_name(normalized_name)
        if not key:
            return normalized_name
        for current_name in schema_fields.keys():
            if self._sanitize_field_name(current_name) == key:
                return current_name
        return normalized_name

    @staticmethod
    def _infer_field_type(value: Any) -> str:
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int) and not isinstance(value, bool):
            return "integer"
        if isinstance(value, float):
            return "number"
        return "string"

    @staticmethod
    def _has_meaningful_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            normalized = value.strip().lower()
            if not normalized:
                return False
            if normalized in {"null", "none", "n/a", "na", "-", "--"}:
                return False
        return True

    def _build_soft_warnings(
        self,
        *,
        route_kind: str,
        manual_mode: bool,
        results: Dict[str, Dict[str, Any]],
        supplemental_tables_added: int,
    ) -> List[str]:
        warnings = [f"{route_kind}_used"]
        warnings.append("direct_semantic_manual_mode" if manual_mode else "direct_semantic_auto_mode")
        if not results:
            warnings.append("direct_semantic_no_fields")
        if supplemental_tables_added > 0:
            warnings.append(f"direct_semantic_tables_supplemented:{supplemental_tables_added}")
        return warnings

    def _route_context_chars_cap(self, *, is_spreadsheet: bool) -> int:
        env_name = (
            "MODULE2_DIRECT_SEMANTIC_XLSX_CONTEXT_CHARS"
            if is_spreadsheet
            else "MODULE2_DIRECT_SEMANTIC_TEXT_CONTEXT_CHARS"
        )
        default = "14000" if is_spreadsheet else "16000"
        return max(2400, int(self._getenv(env_name, default) or default))

    def _schema_context_chars_cap(self, *, is_spreadsheet: bool) -> int:
        env_name = (
            "MODULE2_DIRECT_SEMANTIC_XLSX_SCHEMA_CONTEXT_CHARS"
            if is_spreadsheet
            else "MODULE2_DIRECT_SEMANTIC_TEXT_SCHEMA_CONTEXT_CHARS"
        )
        default = "7200" if is_spreadsheet else "10000"
        return max(2400, int(self._getenv(env_name, default) or default))

    def _manual_field_cap(self) -> int:
        return max(8, int(self._getenv("MODULE2_DIRECT_SEMANTIC_MANUAL_FIELD_CAP", "64") or "64"))

    def _supplemental_table_cap(self) -> int:
        return max(1, int(self._getenv("MODULE2_DIRECT_SEMANTIC_SUPPLEMENTAL_TABLE_CAP", "3") or "3"))

    def _auto_field_cap(self, *, requested_schema: Dict[str, Any], is_spreadsheet: bool) -> int:
        requested_cap = requested_schema.get("max_auto_fields") if isinstance(requested_schema, dict) else None
        default_cap = "64" if is_spreadsheet else "48"
        try:
            resolved = int(requested_cap) if requested_cap is not None else int(self._getenv("MODULE2_DIRECT_SEMANTIC_MAX_FIELDS", default_cap) or default_cap)
        except (TypeError, ValueError):
            resolved = int(default_cap)
        return max(8, min(resolved, 96))

    def _max_output_tokens(self) -> int:
        return max(1024, int(self._getenv("MODULE2_DIRECT_SEMANTIC_MAX_OUTPUT_TOKENS", "4096") or "4096"))
