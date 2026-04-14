from __future__ import annotations

import math
from string import Formatter
from typing import Any, Dict, Optional

SUPPORTED_RULE_KINDS = {"deterministic"}
SEVERITY_DEFAULT_RISK = {"yellow": 40.0, "orange": 70.0, "red": 90.0}
SUPPORTED_RULE_OPS = {
    "eq",
    "neq",
    "lt",
    "lte",
    "gt",
    "gte",
    "contains",
    "in",
    "exists",
    "not_exists",
    "non_empty",
    "is_empty",
}


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else default
    except Exception:
        return default


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set, dict, str)):
        return len(value) > 0
    return True


def _get_by_path(data: Any, path: str) -> Any:
    if not path:
        return data
    cur: Any = data
    for token in str(path).split("."):
        key = token.strip()
        if not key:
            continue
        if isinstance(cur, dict):
            cur = cur.get(key)
            continue
        if isinstance(cur, list) and key.isdigit():
            idx = int(key)
            cur = cur[idx] if 0 <= idx < len(cur) else None
            continue
        return None
    return cur


def _flatten_for_template(data: Any, prefix: str = "") -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if isinstance(data, dict):
        for key, value in data.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.update(_flatten_for_template(value, next_prefix))
        return out
    if isinstance(data, (list, tuple)):
        out[prefix] = ",".join(str(x) for x in data)
        return out
    out[prefix] = data
    return out


def _render_template(template: str, context: Dict[str, Any]) -> str:
    if not template:
        return ""
    flat = _flatten_for_template(context)
    fields = {name for _, name, _, _ in Formatter().parse(template) if name}
    values = {name: flat.get(name, context.get(name, "")) for name in fields}
    try:
        return template.format(**values).strip()
    except Exception:
        return template.strip()


def _normalize_op(expr: Dict[str, Any]) -> str:
    op = str(expr.get("op") or expr.get("condition") or "").strip().lower()
    if not op and "equals" in expr:
        op = "eq"
    if not op and "threshold" in expr:
        op = "lt"
    if not op:
        op = "exists"
    if op not in SUPPORTED_RULE_OPS:
        return "exists"
    return op


def _compare_values(op: str, actual: Any, expected: Any) -> bool:
    if op == "exists":
        return actual is not None
    if op == "not_exists":
        return actual is None
    if op == "non_empty":
        return _is_non_empty(actual)
    if op == "is_empty":
        return not _is_non_empty(actual)

    if op in {"lt", "lte", "gt", "gte"}:
        actual_num = _to_float(actual, float("nan"))
        expected_num = _to_float(expected, float("nan"))
        if str(actual_num) == "nan" or str(expected_num) == "nan":
            return False
        if op == "lt":
            return actual_num < expected_num
        if op == "lte":
            return actual_num <= expected_num
        if op == "gt":
            return actual_num > expected_num
        return actual_num >= expected_num

    if op == "contains":
        if isinstance(actual, (list, tuple, set)):
            return expected in actual
        return str(expected) in str(actual or "")

    if op == "in":
        if not isinstance(expected, (list, tuple, set)):
            return False
        return actual in expected

    if op == "neq":
        return actual != expected
    return actual == expected


def _evaluate_rule_expr(expr: Dict[str, Any], context: Dict[str, Any]) -> bool:
    if not isinstance(expr, dict):
        return False
    if "all" in expr:
        children = expr.get("all")
        if not isinstance(children, list) or not children:
            return False
        return all(_evaluate_rule_expr(item, context) for item in children if isinstance(item, dict))
    if "any" in expr:
        children = expr.get("any")
        if not isinstance(children, list) or not children:
            return False
        return any(_evaluate_rule_expr(item, context) for item in children if isinstance(item, dict))
    if "not" in expr and isinstance(expr.get("not"), dict):
        return not _evaluate_rule_expr(expr["not"], context)

    path = str(expr.get("path") or expr.get("field") or "").strip()
    op = _normalize_op(expr)
    actual = _get_by_path(context, path) if path else context
    expected = expr.get("value")
    if expected is None and "equals" in expr:
        expected = expr.get("equals")
    if expected is None and "threshold" in expr:
        expected = expr.get("threshold")
    return _compare_values(op, actual, expected)


def _rule_scope(rule: Dict[str, Any]) -> str:
    expr = rule.get("expr") if isinstance(rule.get("expr"), dict) else {}
    scope = str(expr.get("scope") or "").strip().lower()
    if scope in {"field", "document"}:
        return scope
    path = str(expr.get("path") or expr.get("field") or "").strip().lower()
    if "confidence" in path or "value" in path:
        return "field"
    return "document"


def _compact_payload_context(context: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        "file_name": context.get("file_name"),
        "file_hash": context.get("file_hash"),
        "track": context.get("track"),
        "field_name": context.get("field_name"),
        "value": context.get("value"),
        "confidence": context.get("confidence"),
        "errors_count": context.get("errors_count"),
        "soft_warning_count": context.get("soft_warning_count"),
        "quality_status": _get_by_path(context, "diagnostics.quality_status"),
    }
    return {k: v for k, v in payload.items() if v is not None and v != ""}


def _rule_risk_score(rule: Dict[str, Any], context: Dict[str, Any]) -> float:
    severity = str(rule.get("severity") or "yellow").lower()
    expr = rule.get("expr") if isinstance(rule.get("expr"), dict) else {}
    explicit = expr.get("risk_score")
    if isinstance(explicit, (int, float, str)):
        return round(_clamp(_to_float(explicit, 0.0), 0.0, 100.0), 3)
    formula = str(expr.get("risk_formula") or "").strip().lower()
    if formula == "1_minus_confidence":
        confidence = _to_float(_get_by_path(context, "confidence"), 1.0)
        return round(_clamp((1.0 - confidence) * 100.0, 0.0, 100.0), 3)
    return round(SEVERITY_DEFAULT_RISK.get(severity, 40.0), 3)


def _evaluate_rule_hit(rule: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not bool(rule.get("enabled", True)):
        return None
    if str(rule.get("rule_kind") or "").strip().lower() not in SUPPORTED_RULE_KINDS:
        return None

    expr = rule.get("expr") if isinstance(rule.get("expr"), dict) else {}
    if not _evaluate_rule_expr(expr, context):
        return None

    merged_context = dict(context)
    merged_context.update(
        {
            "rule_id": rule.get("rule_id"),
            "rule_name": rule.get("name"),
            "severity": rule.get("severity"),
        }
    )
    title_template = str(expr.get("title") or f"Rule hit: {rule.get('name') or rule.get('rule_id')}")
    summary_template = str(expr.get("summary") or "Rule {rule_id} matched for {file_name}")
    title = _render_template(title_template, merged_context) or str(rule.get("name") or rule.get("rule_id"))
    summary = _render_template(summary_template, merged_context) or f"Rule {rule.get('rule_id')} matched"
    return {
        "rule_id": str(rule.get("rule_id")),
        "severity": str(rule.get("severity") or "yellow"),
        "title": title,
        "summary": summary,
        "risk_score": _rule_risk_score(rule, context),
        "payload": {
            "rule_expr": expr,
            "context": _compact_payload_context(context),
        },
    }
