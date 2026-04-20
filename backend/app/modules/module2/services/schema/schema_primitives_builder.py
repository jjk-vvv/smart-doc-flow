from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Callable, Dict, List, Set, Tuple

from fastapi import HTTPException


@dataclass(frozen=True)
class Module2MainSchemaPrimitivesBundle:
    schema_hash: Callable[[Dict[str, Any]], str]
    schema_target_fields: Callable[[Dict[str, Any]], Dict[str, Any]]
    schema_field_type_hint: Callable[[Any], Any]
    coerce_field_type: Callable[[Any], str]
    sanitize_field_name: Callable[[Any], str]
    schema_field_type_priority: Callable[[str], int]


def build_module2_main_schema_primitives_bundle() -> Module2MainSchemaPrimitivesBundle:
    def _schema_hash(schema: Dict[str, Any]) -> str:
        normalized = json.dumps(schema, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _schema_target_fields(schema: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(schema, dict):
            return {}
        fields = schema.get("fields")
        if isinstance(fields, dict):
            return dict(fields)
        excluded = {"dependencies", "validations", "required", "auto_infer", "max_auto_fields", "prefer_llm"}
        return {str(k): v for k, v in schema.items() if str(k) not in excluded}

    def _schema_field_type_hint(type_hint: Any) -> Any:
        if isinstance(type_hint, dict):
            nested = type_hint.get("type")
            if nested is not None:
                return nested
        return type_hint

    def _coerce_field_type(type_hint: Any) -> str:
        text = str(_schema_field_type_hint(type_hint) or "").strip().lower()
        if text in {"int", "integer"}:
            return "integer"
        if text in {"number", "float", "double", "numeric", "decimal", "ratio", "percent"}:
            return "number"
        if text in {"date", "datetime", "time", "timestamp"}:
            return "date"
        if text in {"bool", "boolean"}:
            return "boolean"
        return "string"

    def _sanitize_field_name(raw_name: Any) -> str:
        text = re.sub(r"\s+", " ", str(raw_name or "").strip())
        if not text:
            return ""
        text = re.sub(r"[^\w\u4e00-\u9fff ]+", "", text)
        text = text.strip()
        if len(text) < 2:
            return ""
        return text[:48]

    def _schema_field_type_priority(field_type: str) -> int:
        normalized = _coerce_field_type(field_type)
        return {
            "string": 0,
            "number": 1,
            "integer": 2,
            "date": 2,
            "boolean": 2,
        }.get(normalized, 0)

    return Module2MainSchemaPrimitivesBundle(
        schema_hash=_schema_hash,
        schema_target_fields=_schema_target_fields,
        schema_field_type_hint=_schema_field_type_hint,
        coerce_field_type=_coerce_field_type,
        sanitize_field_name=_sanitize_field_name,
        schema_field_type_priority=_schema_field_type_priority,
    )


SchemaTargetFieldsFn = Callable[[Dict[str, Any]], Dict[str, Any]]
NormalizeSchemaFieldsFn = Callable[[Dict[str, Any], int], Dict[str, str]]
GetEnvFn = Callable[[str, str], Any]
IsWordFileFn = Callable[[str], bool]
SchemaContextCleanTextFn = Callable[[Any], str]
CountTableCellsFn = Callable[[List[Dict[str, Any]]], int]
CountFigureDataframeCellsFn = Callable[[List[Dict[str, Any]]], int]


@dataclass(frozen=True)
class Module2MainSchemaRequestBundle:
    repair_latin1_utf8_mojibake: Callable[[str], str]
    schema_payload_score: Callable[[Any], Tuple[int, int, int]]
    parse_schema_form_json: Callable[[str], Dict[str, Any]]


def build_module2_main_schema_request_bundle(
    *,
    schema_target_fields: SchemaTargetFieldsFn,
    normalize_schema_fields: NormalizeSchemaFieldsFn,
) -> Module2MainSchemaRequestBundle:
    def _repair_latin1_utf8_mojibake(text: str) -> str:
        raw = str(text or "")
        if not raw:
            return raw
        try:
            repaired = raw.encode("latin-1").decode("utf-8")
        except Exception:
            return raw
        return repaired if repaired else raw

    def _schema_payload_score(schema_obj: Any) -> Tuple[int, int, int]:
        if not isinstance(schema_obj, dict):
            return (-1, -1, -1)
        raw_fields = schema_target_fields(schema_obj)
        normalized = normalize_schema_fields(raw_fields, max(8, min(64, len(raw_fields) or 8)))
        cjk_hits = sum(
            sum(1 for ch in str(name) if "\u4e00" <= ch <= "\u9fff")
            for name in normalized.keys()
        )
        return (len(normalized), cjk_hits, len(raw_fields))

    def _parse_schema_form_json(raw_schema: str) -> Dict[str, Any]:
        candidates: list[str] = []
        seen: Set[str] = set()

        def _add_candidate(text: str) -> None:
            candidate = str(text or "")
            if candidate in seen:
                return
            seen.add(candidate)
            candidates.append(candidate)

        _add_candidate(raw_schema)
        _add_candidate(_repair_latin1_utf8_mojibake(raw_schema))

        best_obj: Dict[str, Any] | None = None
        best_score: Tuple[int, int, int] = (-1, -1, -1)
        first_json_error: json.JSONDecodeError | None = None
        non_dict_payload: Any = None

        for candidate in candidates:
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError as exc:
                if first_json_error is None:
                    first_json_error = exc
                continue
            if not isinstance(payload, dict):
                if non_dict_payload is None:
                    non_dict_payload = payload
                continue
            score = _schema_payload_score(payload)
            if score > best_score:
                best_obj = payload
                best_score = score

        if best_obj is not None:
            return best_obj
        if non_dict_payload is not None:
            raise HTTPException(status_code=400, detail="Schema must be a JSON object")
        if first_json_error is not None:
            raise HTTPException(status_code=400, detail=f"Invalid schema JSON: {first_json_error}") from first_json_error
        raise HTTPException(status_code=400, detail="Invalid schema JSON")

    return Module2MainSchemaRequestBundle(
        repair_latin1_utf8_mojibake=_repair_latin1_utf8_mojibake,
        schema_payload_score=_schema_payload_score,
        parse_schema_form_json=_parse_schema_form_json,
    )


@dataclass(frozen=True)
class Module2MainSchemaTimeoutBundle:
    resolve_dynamic_extract_timeout_sec: Callable[..., Tuple[float, Dict[str, Any]]]


def build_module2_main_schema_timeout_bundle(
    *,
    getenv: GetEnvFn,
    is_word_file: IsWordFileFn,
    schema_context_clean_text: SchemaContextCleanTextFn,
    count_table_cells: CountTableCellsFn,
    count_figure_dataframe_cells: CountFigureDataframeCellsFn,
) -> Module2MainSchemaTimeoutBundle:
    def _resolve_dynamic_extract_timeout_sec(
        *,
        file_name: str,
        extract_timeout_sec: float,
        markdown: str,
        schema_fields: Dict[str, Any],
        table_blocks: List[Dict[str, Any]],
        figure_blocks: List[Dict[str, Any]],
    ) -> Tuple[float, Dict[str, Any]]:
        base_timeout = max(8.0, float(extract_timeout_sec or 0.0))
        if not is_word_file(file_name):
            return base_timeout, {
                "applied": False,
                "reason": "not_word_file",
                "resolved_timeout_sec": round(base_timeout, 3),
            }

        text_len = len(schema_context_clean_text(markdown))
        table_cells = count_table_cells(table_blocks)
        figure_dataframe_cells = count_figure_dataframe_cells(figure_blocks)
        field_count = len(schema_fields)
        complexity_score = (
            min(text_len / 3600.0, 18.0)
            + min(float(field_count) * 1.35, 18.0)
            + min(float(len(table_blocks)) * 1.15, 14.0)
            + min(float(len(figure_blocks)) * 1.05, 14.0)
            + min(table_cells / 85.0, 16.0)
            + min(figure_dataframe_cells / 48.0, 16.0)
        )
        trigger_score = max(8.0, float(getenv("MODULE2_WORD_DYNAMIC_EXTRACT_TRIGGER_SCORE", "10.0")))
        configured_max_timeout_sec = max(
            base_timeout,
            float(getenv("MODULE2_WORD_DYNAMIC_EXTRACT_TIMEOUT_MAX_SEC", "420")),
        )
        hard_cap_raw = float(getenv("MODULE2_WORD_DYNAMIC_EXTRACT_TIMEOUT_HARD_CAP_SEC", "300"))
        hard_cap_enabled = hard_cap_raw > 0.0
        hard_cap_timeout_sec = max(base_timeout, hard_cap_raw) if hard_cap_enabled else 0.0
        max_timeout_sec = (
            max(base_timeout, min(configured_max_timeout_sec, hard_cap_timeout_sec))
            if hard_cap_enabled
            else configured_max_timeout_sec
        )
        hard_cap_applied = bool(hard_cap_enabled and max_timeout_sec + 1e-6 < configured_max_timeout_sec)
        bonus_per_score = max(2.0, float(getenv("MODULE2_WORD_DYNAMIC_EXTRACT_BONUS_PER_SCORE", "6.0")))

        if complexity_score < trigger_score:
            return base_timeout, {
                "applied": False,
                "reason": "below_trigger",
                "complexity_score": round(complexity_score, 3),
                "resolved_timeout_sec": round(base_timeout, 3),
                "text_len": text_len,
                "field_count": field_count,
                "table_count": len(table_blocks),
                "figure_count": len(figure_blocks),
                "table_cells": table_cells,
                "figure_dataframe_cells": figure_dataframe_cells,
            }

        recommended_timeout = base_timeout + max(0.0, complexity_score - trigger_score) * bonus_per_score
        resolved_timeout = min(max_timeout_sec, max(base_timeout, recommended_timeout))
        return resolved_timeout, {
            "applied": resolved_timeout > base_timeout + 0.5,
            "reason": "word_complexity_scale",
            "complexity_score": round(complexity_score, 3),
            "resolved_timeout_sec": round(resolved_timeout, 3),
            "base_timeout_sec": round(base_timeout, 3),
            "configured_max_timeout_sec": round(configured_max_timeout_sec, 3),
            "effective_max_timeout_sec": round(max_timeout_sec, 3),
            "hard_cap_timeout_sec": (round(hard_cap_timeout_sec, 3) if hard_cap_enabled else None),
            "hard_cap_applied": hard_cap_applied,
            "text_len": text_len,
            "field_count": field_count,
            "table_count": len(table_blocks),
            "figure_count": len(figure_blocks),
            "table_cells": table_cells,
            "figure_dataframe_cells": figure_dataframe_cells,
        }

    return Module2MainSchemaTimeoutBundle(
        resolve_dynamic_extract_timeout_sec=_resolve_dynamic_extract_timeout_sec,
    )
