from __future__ import annotations

"""Schema LLM bundle builder for module2 service layer."""

import asyncio
from dataclasses import dataclass
import json
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional


GetEnvFn = Callable[[str, str], Any]
ExtractTextForSchemaFn = Callable[[str, List[Dict[str, Any]], Optional[List[Dict[str, Any]]], int], str]
UpsertSchemaFieldCandidateFn = Callable[[Dict[str, str], Any, Any, bool], None]
FilterAutoSchemaFieldsFn = Callable[[Dict[str, str], int], Dict[str, str]]


@dataclass(frozen=True)
class Module2MainSchemaLlmBundle:
    extract_json_payload: Callable[[str], Dict[str, Any]]
    infer_schema_fields_llm: Callable[
        [str, str, List[Dict[str, Any]], Optional[List[Dict[str, Any]]], int],
        Awaitable[Dict[str, str]],
    ]


def build_module2_main_schema_llm_bundle(
    *,
    graph: Any,
    getenv: GetEnvFn,
    extract_text_for_schema: ExtractTextForSchemaFn,
    upsert_schema_field_candidate: UpsertSchemaFieldCandidateFn,
    filter_auto_schema_fields: FilterAutoSchemaFieldsFn,
) -> Module2MainSchemaLlmBundle:
    def _extract_json_payload(raw_text: str) -> Dict[str, Any]:
        text = str(raw_text or "").strip()
        if not text:
            return {}
        fenced = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
        if fenced.startswith("{") and fenced.endswith("}"):
            try:
                payload = json.loads(fenced)
                if isinstance(payload, dict):
                    return payload
            except Exception:
                pass
        match = re.search(r"\{[\s\S]*\}", fenced)
        if not match:
            return {}
        try:
            payload = json.loads(match.group(0))
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    async def _infer_schema_fields_llm(
        file_name: str,
        markdown: str,
        table_blocks: List[Dict[str, Any]],
        figure_blocks: Optional[List[Dict[str, Any]]],
        max_fields: int,
    ) -> Dict[str, str]:
        provider = getattr(graph, "_provider", None)
        llm = getattr(graph, "llm", None)
        if provider is None and llm is None:
            return {}

        is_xlsx = file_name.lower().endswith(".xlsx")
        context = extract_text_for_schema(
            markdown,
            table_blocks,
            figure_blocks,
            4200 if is_xlsx else 10000,
        )
        if not context:
            return {}

        system_prompt = (
            "You are a document schema planner. Select only the most valuable, stable, and extractable fields from the file. "
            "Prefer identifiers, dates, organizations, people, regions, totals, counts, rates, units, and core business metrics. "
            "For spreadsheets or table-heavy documents, prioritize main dimensions and key metrics instead of generic helper columns. "
            "If charts or figures expose dataframe-like metrics, headers, or category labels, treat them as valid schema evidence too. "
            "Avoid low-value generic fields such as ref, page, text, name, sheet, notes, or remarks unless they are true business fields. "
            f"Return 4 to {max(4, min(max_fields, 12))} fields, JSON only, with no explanation."
        )
        user_prompt = (
            f"File name: {file_name}\n"
            f"Document context:\n{context}\n\n"
            "Output JSON exactly as:\n"
            "{\n"
            '  "fields": [\n'
            '    {"field_name": "field_name_in_original_language", "field_type": "string|number|integer|date"},\n'
            "    ...\n"
            "  ]\n"
            "}\n\n"
            "Keep field names in the original document language whenever possible."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        timeout_sec = max(6.0, float(getenv("MODULE2_AUTO_SCHEMA_LLM_TIMEOUT_SEC", "90")))
        max_output_tokens = max(512, int(getenv("MODULE2_AUTO_SCHEMA_LLM_MAX_TOKENS", "1400")))
        try:
            if provider is not None:
                payload = await asyncio.wait_for(
                    graph.invoke_json_object(
                        messages,
                        max_tokens=max_output_tokens,
                        purpose="schema_planner",
                    ),
                    timeout=timeout_sec,
                )
            else:
                raw_resp = await asyncio.wait_for(llm.ainvoke(messages), timeout=timeout_sec)
                content_raw: Any = getattr(raw_resp, "content", raw_resp)
                if isinstance(content_raw, list):
                    chunks: List[str] = []
                    for item in content_raw:
                        if isinstance(item, dict):
                            text = str(item.get("text") or "").strip()
                            if text:
                                chunks.append(text)
                        else:
                            text = str(item or "").strip()
                            if text:
                                chunks.append(text)
                    content_text = "\n".join(chunks).strip()
                else:
                    content_text = str(content_raw or "").strip()
                payload = _extract_json_payload(content_text)
        except Exception:
            return {}

        raw_fields = payload.get("fields")
        if not isinstance(raw_fields, list):
            return {}

        parsed: Dict[str, str] = {}
        for item in raw_fields:
            if not isinstance(item, dict):
                continue
            upsert_schema_field_candidate(
                parsed,
                item.get("field_name"),
                item.get("field_type"),
                True,
            )
            if len(parsed) >= max_fields:
                break
        return filter_auto_schema_fields(parsed, max_fields=max_fields)

    return Module2MainSchemaLlmBundle(
        extract_json_payload=_extract_json_payload,
        infer_schema_fields_llm=_infer_schema_fields_llm,
    )
