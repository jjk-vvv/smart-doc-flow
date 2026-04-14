from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from fastapi import HTTPException

from ...schemas import ExplainRequest, ExplainResponse, SimulateRequest, SimulateResponse


LoadEvidenceForNodeCallback = Callable[[str, Dict[str, Any], int], Awaitable[List[Dict[str, Any]]]]
LoadArtifactNeighborhoodCallback = Callable[[str, str, int, int], Awaitable[Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]]]


@dataclass(frozen=True)
class Module4InsightRuntimeHelpers:
    to_float: Callable[[Any, float], float]
    to_int: Callable[[Any, int], int]
    as_list: Callable[[Any], List[Any]]
    rule_scope: Callable[[Dict[str, Any]], str]
    evaluate_rule_hit: Callable[[Dict[str, Any], Dict[str, Any]], Optional[Dict[str, Any]]]
    normalize_graph_node_row: Callable[[Dict[str, Any]], Dict[str, Any]]
    load_evidence_for_node: LoadEvidenceForNodeCallback
    load_artifact_neighborhood: LoadArtifactNeighborhoodCallback
    supported_rule_kinds: set[str]


def _scope_values(raw: Any) -> List[str]:
    if isinstance(raw, list):
        values = raw
    elif isinstance(raw, tuple):
        values = list(raw)
    elif raw is None:
        values = []
    else:
        text = str(raw).strip()
        if not text:
            values = []
        else:
            values = [item.strip() for item in text.replace("|", ",").split(",") if item.strip()]
    return [str(item).strip() for item in values if str(item).strip()]


def _simulation_context_label(scope_name: str, context: Dict[str, Any], index: int) -> str:
    if scope_name == "field":
        field_name = str(context.get("field_name") or "").strip()
        file_name = str(context.get("file_name") or "").strip()
        if field_name and file_name:
            return f"{file_name}:{field_name}"
        if field_name:
            return f"field:{field_name}"
    if scope_name == "document":
        file_name = str(context.get("file_name") or "").strip()
        file_hash = str(context.get("file_hash") or "").strip()
        if file_name:
            return f"document:{file_name}"
        if file_hash:
            return f"document:{file_hash}"
    return f"{scope_name}:{index}"


def _inflate_simulation_context(
    *,
    helpers: Module4InsightRuntimeHelpers,
    raw_context: Dict[str, Any],
) -> Dict[str, Any]:
    context = dict(raw_context or {})
    quality_status = str(context.get("quality_status") or "").strip()
    diagnostics = context.get("diagnostics") if isinstance(context.get("diagnostics"), dict) else {}
    if quality_status and "quality_status" not in diagnostics:
        diagnostics = {**diagnostics, "quality_status": quality_status}
        context["diagnostics"] = diagnostics

    errors_count = helpers.to_int(context.get("errors_count"), 0)
    if errors_count > 0 and not isinstance(context.get("errors"), list):
        context["errors"] = ["simulated_error"] * errors_count

    soft_warning_count = helpers.to_int(context.get("soft_warning_count"), 0)
    if soft_warning_count > 0 and not isinstance(context.get("soft_warnings"), list):
        context["soft_warnings"] = ["simulated_warning"] * soft_warning_count

    return context


async def simulation_contexts_from_request(
    *,
    storage: Any,
    helpers: Module4InsightRuntimeHelpers,
    tenant_id: str,
    body: SimulateRequest,
) -> List[Dict[str, Any]]:
    contexts: List[Dict[str, Any]] = []
    params = body.params if isinstance(body.params, dict) else {}
    scope = body.scope if isinstance(body.scope, dict) else {}
    context_overrides = params.get("context_overrides") if isinstance(params.get("context_overrides"), dict) else {}

    def append_context(
        scope_name: str,
        raw_context: Dict[str, Any],
        index: int,
        *,
        source_alert_id: str | None = None,
    ) -> None:
        context = _inflate_simulation_context(helpers=helpers, raw_context=raw_context)
        if context_overrides:
            context.update(context_overrides)
        context["__scope"] = scope_name
        context["__label"] = str(context.get("__label") or _simulation_context_label(scope_name, context, index))
        if source_alert_id:
            context["__source_alert_id"] = source_alert_id
        contexts.append(context)

    if isinstance(params.get("document_context"), dict):
        append_context("document", params["document_context"], len(contexts) + 1)
    if isinstance(params.get("field_context"), dict):
        append_context("field", params["field_context"], len(contexts) + 1)

    for item in helpers.as_list(params.get("document_contexts")):
        if isinstance(item, dict):
            append_context("document", item, len(contexts) + 1)
    for item in helpers.as_list(params.get("field_contexts")):
        if isinstance(item, dict):
            append_context("field", item, len(contexts) + 1)

    alert_ids = _scope_values(scope.get("alert_ids"))
    single_alert_id = str(scope.get("alert_id") or "").strip()
    if single_alert_id:
        alert_ids.append(single_alert_id)

    seen_alert_ids: set[str] = set()
    for alert_id in alert_ids:
        if alert_id in seen_alert_ids:
            continue
        seen_alert_ids.add(alert_id)
        alert = await storage.get_alert(alert_id, tenant_id=tenant_id)
        if not alert:
            continue
        payload = alert.get("payload") if isinstance(alert.get("payload"), dict) else {}
        context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
        rule_expr = payload.get("rule_expr") if isinstance(payload.get("rule_expr"), dict) else {}
        scope_name = helpers.rule_scope({"expr": rule_expr}) if rule_expr else "document"
        if context:
            append_context(scope_name, context, len(contexts) + 1, source_alert_id=alert_id)

    return contexts


async def explain_response(
    *,
    storage: Any,
    helpers: Module4InsightRuntimeHelpers,
    tenant_id: str,
    body: ExplainRequest,
) -> ExplainResponse:
    if body.alert_id:
        alert = await storage.get_alert(body.alert_id, tenant_id=tenant_id)
        if not alert:
            raise HTTPException(status_code=404, detail="\u544a\u8b66\u4e0d\u5b58\u5728")

        payload = alert.get("payload") if isinstance(alert.get("payload"), dict) else {}
        evidence_rows: List[Dict[str, Any]] = []
        steps = [
            f"\u547d\u4e2d\u89c4\u5219\uff1a{alert.get('rule_id')}",
            f"\u98ce\u9669\u7b49\u7ea7\uff1a{alert.get('severity')}",
            f"\u98ce\u9669\u5206\u6570\uff1a{helpers.to_float(alert.get('risk_score'), 0.0):.2f}",
        ]
        subject_node_id = str(alert.get("subject_node_id") or "").strip()
        if subject_node_id:
            node_row = await storage.get_node(tenant_id=tenant_id, node_id=subject_node_id)
            if node_row:
                normalized_node = helpers.normalize_graph_node_row(node_row)
                evidence_rows = await helpers.load_evidence_for_node(tenant_id, node_row, limit=8)
                steps.append(
                    f"\u5173\u8054\u8282\u70b9\uff1a{normalized_node['display_name']}\uff08{normalized_node['node_type']}\uff09"
                )
                if evidence_rows:
                    steps.append(f"\u5df2\u4e3a\u8be5\u8282\u70b9\u89e3\u6790\u51fa {len(evidence_rows)} \u6761\u76f4\u63a5\u8bc1\u636e\u3002")
        if payload and not evidence_rows:
            steps.append("\u672a\u89e3\u6790\u5230\u76f4\u63a5\u8bc1\u636e\uff0c\u5f53\u524d\u8fd4\u56de\u544a\u8b66\u8f7d\u8377\u4e2d\u7684\u4e0a\u4e0b\u6587\u4fe1\u606f\u4f9b\u4eba\u5de5\u590d\u6838\u3002")
        return ExplainResponse(
            conclusion=str(alert.get("summary") or "\u8be5\u544a\u8b66\u9700\u8981\u8fdb\u4e00\u6b65\u6838\u67e5\u3002"),
            reasoning_steps=steps,
            evidence=evidence_rows or ([payload] if payload else []),
        )

    if body.node_id:
        nodes_raw, edges_raw = await helpers.load_artifact_neighborhood(tenant_id, body.node_id, 1, 40)
        if not nodes_raw:
            raise HTTPException(status_code=404, detail="\u8282\u70b9\u4e0d\u5b58\u5728")
        node_row = next((row for row in nodes_raw if str(row.get("node_id") or "") == str(body.node_id)), nodes_raw[0])
        normalized_node = helpers.normalize_graph_node_row(node_row)
        evidence_rows = await helpers.load_evidence_for_node(tenant_id, node_row, limit=10)
        return ExplainResponse(
            conclusion=(
                f"\u8282\u70b9\u201c{normalized_node['display_name']}\u201d\uff08{normalized_node['node_type']}\uff09"
                f"\u5f53\u524d\u5173\u8054 {len(evidence_rows)} \u6761\u8bc1\u636e\u3001{len(edges_raw)} \u6761\u90bb\u63a5\u5173\u7cfb\u3002"
            ),
            reasoning_steps=[
                f"\u5df2\u52a0\u8f7d\u8282\u70b9\u201c{normalized_node['display_name']}\u201d\uff08{normalized_node['node_type']}\uff09\u3002",
                f"\u5728 1 \u8df3\u90bb\u57df\u5185\u5171\u68c0\u7d22\u5230 {max(0, len(nodes_raw) - 1)} \u4e2a\u76f8\u90bb\u8282\u70b9\u3001{len(edges_raw)} \u6761\u5173\u7cfb\u3002",
                f"\u57fa\u4e8e\u8282\u70b9\u7c7b\u578b\u4e0e\u56fe\u8c31\u8840\u7f18\u4fe1\u606f\uff0c\u5171\u56de\u6eaf\u5230 {len(evidence_rows)} \u6761\u8bc1\u636e\u3002",
            ],
            evidence=evidence_rows or [normalized_node],
        )

    raise HTTPException(status_code=400, detail="\u5fc5\u987b\u63d0\u4f9b alert_id \u6216 node_id")


async def simulate_response(
    *,
    storage: Any,
    helpers: Module4InsightRuntimeHelpers,
    tenant_id: str,
    body: SimulateRequest,
) -> SimulateResponse:
    params = body.params if isinstance(body.params, dict) else {}
    scope = body.scope if isinstance(body.scope, dict) else {}
    contexts = await simulation_contexts_from_request(storage=storage, helpers=helpers, tenant_id=tenant_id, body=body)
    rules = await storage.list_rules(tenant_id=tenant_id, enabled_only=True)
    deterministic_rules = [
        rule for rule in rules if str(rule.get("rule_kind") or "").lower() in helpers.supported_rule_kinds
    ]

    explicit_rule_ids = set(_scope_values(scope.get("rule_ids")))
    single_rule_id = str(scope.get("rule_id") or "").strip()
    if single_rule_id:
        explicit_rule_ids.add(single_rule_id)
    if explicit_rule_ids:
        deterministic_rules = [rule for rule in deterministic_rules if str(rule.get("rule_id") or "") in explicit_rule_ids]

    if contexts:
        changed_alerts: List[Dict[str, Any]] = []
        impacts: List[Dict[str, Any]] = []
        hits_by_rule: Counter[str] = Counter()
        hits_by_severity: Counter[str] = Counter()

        for context in contexts:
            scope_name = str(context.get("__scope") or "document")
            applicable_rules = [rule for rule in deterministic_rules if helpers.rule_scope(rule) == scope_name]
            context_label = str(context.get("__label") or scope_name)
            for rule in applicable_rules:
                hit = helpers.evaluate_rule_hit(rule, context)
                if not hit:
                    continue
                hits_by_rule[str(hit["rule_id"])] += 1
                hits_by_severity[str(hit["severity"])] += 1
                changed_alerts.append(
                    {
                        "scenario_name": body.scenario_name,
                        "context_label": context_label,
                        "scope": scope_name,
                        "rule_id": hit["rule_id"],
                        "severity": hit["severity"],
                        "title": hit["title"],
                        "summary": hit["summary"],
                        "simulated_risk_score": round(helpers.to_float(hit["risk_score"], 0.0), 3),
                        "source_alert_id": str(context.get("__source_alert_id") or "") or None,
                    }
                )

        impacts.append({"metric": "simulated_contexts", "value": len(contexts)})
        impacts.append({"metric": "evaluated_rules", "value": len(deterministic_rules)})
        impacts.append({"metric": "simulated_hits", "value": len(changed_alerts)})
        if hits_by_rule:
            impacts.append({"metric": "hits_by_rule", "value": dict(hits_by_rule)})
        if hits_by_severity:
            impacts.append({"metric": "hits_by_severity", "value": dict(hits_by_severity)})

        summary = (
            f"\u573a\u666f\u201c{body.scenario_name}\u201d\u5df2\u5b8c\u6210\u6a21\u62df\uff0c"
            f"\u5171\u8bc4\u4f30 {len(contexts)} \u4e2a\u4e0a\u4e0b\u6587\u3001{len(deterministic_rules)} \u6761\u786e\u5b9a\u6027\u89c4\u5219\uff0c"
            f"\u547d\u4e2d {len(changed_alerts)} \u6761\u7ed3\u679c\u3002"
        )
        return SimulateResponse(impacts=impacts, changed_alerts=changed_alerts, summary=summary)

    multiplier = helpers.to_float(params.get("risk_multiplier", 1.0), 1.0)
    rule_id_filter = next(iter(explicit_rule_ids), None) if explicit_rule_ids else None
    total, alerts = await storage.list_alerts(
        tenant_id=tenant_id,
        status="open",
        severity=None,
        rule_id=rule_id_filter,
        page=1,
        page_size=100,
    )
    changed_alerts: List[Dict[str, Any]] = []
    impacts: List[Dict[str, Any]] = []
    avg_delta = 0.0
    for alert in alerts:
        original = helpers.to_float(alert.get("risk_score"), 0.0)
        simulated = max(0.0, min(100.0, original * multiplier))
        changed_alerts.append(
            {
                "alert_id": alert.get("alert_id"),
                "rule_id": alert.get("rule_id"),
                "original_risk_score": round(original, 3),
                "simulated_risk_score": round(simulated, 3),
                "delta": round(simulated - original, 3),
            }
        )
    if changed_alerts:
        avg_delta = sum(item["delta"] for item in changed_alerts) / len(changed_alerts)
    impacts.append({"metric": "avg_risk_delta", "value": round(avg_delta, 3)})
    impacts.append({"metric": "mode", "value": "legacy_multiplier"})
    impacts.append({"metric": "supported_rule_kinds", "value": sorted(helpers.supported_rule_kinds)})
    summary = (
        f"\u573a\u666f\u201c{body.scenario_name}\u201d\u5df2\u6309\u65e7\u7248\u98ce\u9669\u500d\u7387\u6a21\u5f0f\u5b8c\u6210\u6a21\u62df\uff0c"
        f"\u6d89\u53ca {min(total, len(changed_alerts))} \u6761\u5f00\u653e\u544a\u8b66\u3002"
    )
    return SimulateResponse(impacts=impacts, changed_alerts=changed_alerts, summary=summary)
