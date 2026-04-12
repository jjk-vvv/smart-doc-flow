from __future__ import annotations

"""Schema resolution bundle builder for module2 service layer."""

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Set, Tuple


SchemaTargetFieldsFn = Callable[[Dict[str, Any]], Dict[str, Any]]
NormalizeSchemaFieldsFn = Callable[[Dict[str, Any], int], Dict[str, Any]]
SelectBestCanonicalSchemaFieldsFn = Callable[[Dict[str, Any], Dict[str, Any], int, str], Tuple[Dict[str, Any], Dict[str, Any]]]
ApplyConservativeSemanticClosureFn = Callable[
    [Dict[str, Any], Dict[str, Any], Dict[str, str], Dict[str, str], str],
    Tuple[Dict[str, Any], Dict[str, Any], Dict[str, str], Dict[str, str], Dict[str, Any]],
]
UpsertSchemaFieldCandidateFn = Callable[[Dict[str, Any], Any, Any, bool], None]
FilterAutoSchemaFieldsFn = Callable[[Dict[str, Any], int], Dict[str, Any]]
InferSchemaFieldsLlmFn = Callable[[str, str, List[Dict[str, Any]], Optional[List[Dict[str, Any]]], int], Awaitable[Dict[str, str]]]
InferRuleBackedSchemaFieldsFn = Callable[..., Dict[str, str]]
InferSchemaFieldsHeuristicFn = Callable[[str, List[Dict[str, Any]], Optional[List[Dict[str, Any]]], int], Dict[str, str]]
CanonicalizeSchemaFieldsFn = Callable[
    [Dict[str, Any], str],
    Tuple[Dict[str, Any], Dict[str, Any], Dict[str, str], Dict[str, str], Dict[str, Any]],
]
NormalizeSchemaContractsFn = Callable[[Dict[str, Any], Dict[str, str], str], Dict[str, Any]]
GetEnvFn = Callable[[str, str], Any]


@dataclass(frozen=True)
class Module2MainSchemaResolutionBundle:
    schema_auto_infer_requested: Callable[[Dict[str, Any]], bool]
    schema_required_from_field_specs: Callable[[Dict[str, Any]], List[str]]
    merge_required_field_names: Callable[[Any, List[str]], List[str]]
    resolve_effective_schema: Callable[..., Awaitable[Tuple[Dict[str, Any], Dict[str, Any]]]]


def build_module2_main_schema_resolution_bundle(
    *,
    schema_target_fields: SchemaTargetFieldsFn,
    normalize_schema_fields: NormalizeSchemaFieldsFn,
    select_best_canonical_schema_fields: SelectBestCanonicalSchemaFieldsFn,
    apply_conservative_semantic_closure: ApplyConservativeSemanticClosureFn,
    upsert_schema_field_candidate: UpsertSchemaFieldCandidateFn,
    filter_auto_schema_fields: FilterAutoSchemaFieldsFn,
    infer_schema_fields_llm: InferSchemaFieldsLlmFn,
    infer_rule_backed_schema_fields: InferRuleBackedSchemaFieldsFn,
    infer_schema_fields_heuristic: InferSchemaFieldsHeuristicFn,
    canonicalize_schema_fields_fn: CanonicalizeSchemaFieldsFn,
    normalize_schema_contracts_fn: NormalizeSchemaContractsFn,
    schema_selection_rules: Dict[str, Any],
    schema_coverage_profiles: Dict[str, Any] | None = None,
    getenv: GetEnvFn,
) -> Module2MainSchemaResolutionBundle:
    def _coverage_profile_for_template(template_hint: str) -> Dict[str, Any]:
        templates = (
            dict(schema_coverage_profiles.get("templates") or {})
            if isinstance(schema_coverage_profiles, dict)
            else {}
        )
        return dict(templates.get(str(template_hint or "").strip()) or {})

    def _profile_target_fields(
        *,
        file_name: str,
        template_hint: str,
        is_table_heavy: bool,
    ) -> int:
        profile = _coverage_profile_for_template(template_hint)
        target_key = "table_target_fields" if is_table_heavy else "text_target_fields"
        target_fields = int(profile.get(target_key, 0) or 0)
        if target_fields > 0:
            return min(target_fields, 20)

        if is_table_heavy:
            fallback_table_target = int(profile.get("text_target_fields", 0) or 0)
            if fallback_table_target > 0:
                return min(fallback_table_target, 20)

        if str(file_name or "").strip().lower().endswith((".txt", ".md", ".markdown")):
            fallback_text_target = int(profile.get("text_target_fields", 0) or 0)
            if fallback_text_target > 0:
                return min(fallback_text_target, 20)

        return 0

    def _profile_freeze_rule_field_count(template_hint: str) -> int:
        profile = _coverage_profile_for_template(template_hint)
        freeze_count = int(profile.get("freeze_rule_field_count", 0) or 0)
        return min(max(freeze_count, 0), 20)

    def _schema_auto_infer_requested(schema: Dict[str, Any]) -> bool:
        if not isinstance(schema, dict):
            return True
        if bool(schema.get("auto_infer")):
            return True
        return len(schema_target_fields(schema)) == 0

    def _schema_required_from_field_specs(schema: Dict[str, Any]) -> List[str]:
        required: List[str] = []
        fields = schema.get("fields")
        if not isinstance(fields, dict):
            return required
        for field_name, field_spec in fields.items():
            if isinstance(field_spec, dict) and bool(field_spec.get("required")):
                name = str(field_name or "").strip()
                if name:
                    required.append(name)
        return required

    def _merge_required_field_names(existing: Any, extra: List[str]) -> List[str]:
        merged: List[str] = []
        seen: Set[str] = set()
        iterable = existing if isinstance(existing, list) else []
        for item in list(iterable) + list(extra):
            name = str(item or "").strip()
            key = name.lower()
            if not name or key in seen:
                continue
            seen.add(key)
            merged.append(name)
        return merged

    def _merge_candidate_sources(
        sources: Sequence[Dict[str, str]],
        *,
        candidate_limit: int,
        preserve_generic_labels: bool = False,
    ) -> Dict[str, str]:
        merged: Dict[str, str] = {}
        for source_index, source in enumerate(sources):
            skip_low_value = not (preserve_generic_labels and source_index == 0)
            for name, type_hint in source.items():
                upsert_schema_field_candidate(
                    merged,
                    name,
                    type_hint,
                    skip_low_value,
                )
                if len(merged) >= candidate_limit:
                    break
            if len(merged) >= candidate_limit:
                break
        if preserve_generic_labels:
            return dict(list(merged.items())[:candidate_limit])
        return filter_auto_schema_fields(merged, max_fields=candidate_limit)

    def _deterministic_schema_target(
        *,
        file_name: str,
        template_hint: str,
        max_fields: int,
        profile_target_fields: int = 0,
    ) -> int:
        if profile_target_fields > 0:
            return min(max_fields, max(4, profile_target_fields))
        normalized_file_name = str(file_name or "").strip().lower()
        normalized_template = str(template_hint or "").strip().lower()
        if normalized_file_name.endswith((".txt", ".md", ".markdown")):
            if normalized_template and normalized_template != "common_document":
                return min(max_fields, max(4, int(schema_selection_rules.get("plain_text_template_target_fields", 6) or 6)))
            return min(max_fields, max(4, int(schema_selection_rules.get("plain_text_target_fields", 5) or 5)))
        if normalized_template and normalized_template != "common_document":
            return min(max_fields, max(4, int(schema_selection_rules.get("template_target_fields", 5) or 5)))
        return min(max_fields, max(4, int(schema_selection_rules.get("default_target_fields", 4) or 4)))

    def _should_invoke_schema_llm(
        *,
        file_name: str,
        template_hint: str,
        max_fields: int,
        profile_target_fields: int,
        rule_fields: Dict[str, str],
        heuristic_fields: Dict[str, str],
        llm_enabled: bool,
        table_blocks: List[Dict[str, Any]],
        figure_blocks: Optional[List[Dict[str, Any]]],
    ) -> bool:
        if not llm_enabled:
            return False

        deterministic_merged = _merge_candidate_sources(
            (rule_fields, heuristic_fields),
            candidate_limit=max_fields,
            preserve_generic_labels=bool(rule_fields),
        )
        deterministic_count = len(deterministic_merged)
        deterministic_target = _deterministic_schema_target(
            file_name=file_name,
            template_hint=template_hint,
            max_fields=max_fields,
            profile_target_fields=profile_target_fields,
        )
        if deterministic_count >= deterministic_target:
            return False

        normalized_template = str(template_hint or "").strip().lower()
        if normalized_template and normalized_template != "common_document" and len(rule_fields) >= max(3, min(max_fields, 4)):
            return False

        if table_blocks or figure_blocks:
            return deterministic_count < max(3, deterministic_target)

        normalized_file_name = str(file_name or "").strip().lower()
        if normalized_file_name.endswith((".txt", ".md", ".markdown")):
            return deterministic_count < max(2, deterministic_target)

        return True

    async def _resolve_effective_schema(
        *,
        requested_schema: Dict[str, Any],
        file_name: str,
        markdown: str,
        table_blocks: List[Dict[str, Any]],
        figure_blocks: Optional[List[Dict[str, Any]]] = None,
        profile_hint: str = "",
        naming_template: str = "",
        allow_llm: bool = True,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        req_fields = schema_target_fields(requested_schema)
        schema_for_contracts = dict(requested_schema)
        required_from_specs = _schema_required_from_field_specs(requested_schema)
        if required_from_specs:
            schema_for_contracts["required"] = _merge_required_field_names(
                schema_for_contracts.get("required"),
                required_from_specs,
            )

        requested_max_fields = max(4, min(int(requested_schema.get("max_auto_fields", 12) or 12), 20))
        template_hint = str(naming_template or "common_document").strip() or "common_document"
        selection_rules = schema_selection_rules
        is_table_heavy = file_name.lower().endswith(".xlsx") or str(profile_hint).lower() == "table_heavy"
        coverage_target_fields = _profile_target_fields(
            file_name=file_name,
            template_hint=template_hint,
            is_table_heavy=is_table_heavy,
        )
        max_fields = max(requested_max_fields, coverage_target_fields or 0)
        base_table_heavy_max_fields = max(4, int(selection_rules.get("xlsx_or_table_heavy_max_fields", 6) or 6))
        if is_table_heavy:
            table_heavy_cap = max(base_table_heavy_max_fields, coverage_target_fields or 0)
            max_fields = min(max_fields, table_heavy_cap, 20)
        elif figure_blocks:
            max_fields = min(
                max_fields,
                max(4, int(selection_rules.get("figure_rich_max_fields", 8) or 8), coverage_target_fields or 0),
                20,
            )
        elif file_name.lower().endswith(".pdf"):
            pdf_max_fields_env = str(selection_rules.get("pdf_max_fields_env") or "MODULE2_AUTO_SCHEMA_PDF_MAX_FIELDS")
            pdf_max_fields_default = max(4, int(selection_rules.get("pdf_max_fields_default", 8) or 8))
            max_fields = min(
                max_fields,
                max(4, int(getenv(pdf_max_fields_env, str(pdf_max_fields_default))), coverage_target_fields or 0),
                20,
            )
        else:
            max_fields = min(max_fields, 20)

        candidate_multiplier = max(2, int(selection_rules.get("candidate_pool_multiplier", 3) or 3))
        candidate_extra_cap = max(4, int(selection_rules.get("candidate_pool_extra_cap", 10) or 10))
        candidate_pool_max = max(max_fields, int(selection_rules.get("candidate_pool_max", 36) or 36))
        
        def _candidate_limit_for_max_fields(max_fields_value: int) -> int:
            return max(
                max_fields_value * candidate_multiplier,
                min(candidate_pool_max, max_fields_value + candidate_extra_cap),
            )

        candidate_limit = _candidate_limit_for_max_fields(max_fields)

        auto_infer = _schema_auto_infer_requested(requested_schema)
        if not auto_infer:
            normalized = normalize_schema_fields(req_fields, max_fields=max_fields)
            canonical_fields, field_meta, raw_to_canonical, canonical_to_raw, naming_stats = canonicalize_schema_fields_fn(
                normalized,
                template_hint=template_hint,
            )
            canonical_fields, field_meta = select_best_canonical_schema_fields(
                canonical_fields,
                field_meta,
                max_fields=max_fields,
                template_hint=template_hint,
            )
            selected_labels = set(canonical_fields.keys())
            raw_to_canonical = {
                raw_name: canonical_name
                for raw_name, canonical_name in raw_to_canonical.items()
                if canonical_name in selected_labels
            }
            canonical_to_raw = {
                canonical_name: raw_name
                for canonical_name, raw_name in canonical_to_raw.items()
                if canonical_name in selected_labels
            }
            effective = normalize_schema_contracts_fn(
                schema_for_contracts,
                raw_to_canonical,
                template_hint=template_hint,
            )
            effective["fields"] = canonical_fields
            effective["field_meta"] = field_meta
            return effective, {
                "mode": "manual",
                "source": "request",
                "field_count": len(canonical_fields),
                "fields": list(canonical_fields.keys()),
                "raw_fields": list(normalized.keys()),
                "field_name_mappings": raw_to_canonical,
                "canonical_to_raw": canonical_to_raw,
                "naming_template": template_hint,
                "coverage_target_fields": coverage_target_fields,
                "naming_stats": naming_stats,
                "field_meta": field_meta,
            }

        enable_rule_candidates = template_hint in set(selection_rules.get("rule_candidate_templates", ()))
        rule_fields = (
            infer_rule_backed_schema_fields(
                file_name=file_name,
                markdown=markdown,
                table_blocks=table_blocks,
                figure_blocks=figure_blocks,
                template_hint=template_hint,
                max_fields=candidate_limit,
            )
            if enable_rule_candidates
            else {}
        )
        if is_table_heavy and template_hint != "common_document":
            rich_trigger_count = max(
                base_table_heavy_max_fields,
                int(selection_rules.get("xlsx_rule_rich_trigger_count", 8) or 8),
            )
            rich_max_fields = max(
                base_table_heavy_max_fields,
                coverage_target_fields or 0,
                int(selection_rules.get("xlsx_rule_rich_max_fields", 12) or 12),
            )
            if len(rule_fields) >= rich_trigger_count:
                max_fields = min(max(requested_max_fields, coverage_target_fields or 0), rich_max_fields, 20)
                candidate_pool_max = max(candidate_pool_max, max_fields)
                candidate_limit = max(candidate_limit, _candidate_limit_for_max_fields(max_fields))
        heuristic_fields = infer_schema_fields_heuristic(
            markdown=markdown,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
            max_fields=max_fields,
        )
        if (
            rule_fields
            and template_hint != "common_document"
            and file_name.lower().endswith((".txt", ".md", ".markdown"))
        ):
            freeze_rule_field_count = _profile_freeze_rule_field_count(template_hint)
            deterministic_target = _deterministic_schema_target(
                file_name=file_name,
                template_hint=template_hint,
                max_fields=max_fields,
                profile_target_fields=coverage_target_fields,
            )
            freeze_threshold = freeze_rule_field_count or deterministic_target
            if len(rule_fields) >= freeze_threshold:
                heuristic_fields = {}
        llm_enabled = bool(requested_schema.get("prefer_llm", True)) and bool(allow_llm)
        llm_attempted = False
        llm_fields: Dict[str, str] = {}
        if _should_invoke_schema_llm(
            file_name=file_name,
            template_hint=template_hint,
            max_fields=max_fields,
            profile_target_fields=coverage_target_fields,
            rule_fields=rule_fields,
            heuristic_fields=heuristic_fields,
            llm_enabled=llm_enabled,
            table_blocks=table_blocks,
            figure_blocks=figure_blocks,
        ):
            llm_attempted = True
            llm_fields = await infer_schema_fields_llm(
                file_name=file_name,
                markdown=markdown,
                table_blocks=table_blocks,
                figure_blocks=figure_blocks,
                max_fields=max_fields,
            )

        merged = _merge_candidate_sources(
            (rule_fields, heuristic_fields, llm_fields),
            candidate_limit=candidate_limit,
            preserve_generic_labels=bool(rule_fields),
        )

        if not merged and req_fields:
            merged = normalize_schema_fields(req_fields, max_fields=max_fields)

        canonical_fields, field_meta, raw_to_canonical, canonical_to_raw, naming_stats = canonicalize_schema_fields_fn(
            merged,
            template_hint=template_hint,
        )
        (
            canonical_fields,
            field_meta,
            raw_to_canonical,
            canonical_to_raw,
            closure_stats,
        ) = apply_conservative_semantic_closure(
            canonical_fields,
            field_meta,
            raw_to_canonical,
            canonical_to_raw,
            template_hint=template_hint,
        )
        naming_stats = {
            **dict(naming_stats),
            **dict(closure_stats),
        }
        canonical_fields, field_meta = select_best_canonical_schema_fields(
            canonical_fields,
            field_meta,
            max_fields=max_fields,
            template_hint=template_hint,
        )
        selected_labels = set(canonical_fields.keys())
        raw_to_canonical = {
            raw_name: canonical_name
            for raw_name, canonical_name in raw_to_canonical.items()
            if canonical_name in selected_labels
        }
        canonical_to_raw = {
            canonical_name: raw_name
            for canonical_name, raw_name in canonical_to_raw.items()
            if canonical_name in selected_labels
        }
        effective = normalize_schema_contracts_fn(
            {"fields": canonical_fields, **schema_for_contracts},
            raw_to_canonical,
            template_hint=template_hint,
        )
        effective["fields"] = canonical_fields
        effective["field_meta"] = field_meta

        source = "llm+heuristic" if llm_fields else ("heuristic" if heuristic_fields else "empty")
        return effective, {
            "mode": "auto",
            "source": "rules+llm+heuristic" if rule_fields and llm_fields else (
                "rules+heuristic" if rule_fields else source
            ),
            "llm_attempted": llm_attempted,
            "llm_used": bool(llm_fields),
            "rule_field_count": len(rule_fields),
            "heuristic_field_count": len(heuristic_fields),
            "deterministic_field_count": len(
                _merge_candidate_sources(
                    (rule_fields, heuristic_fields),
                    candidate_limit=max_fields,
                    preserve_generic_labels=bool(rule_fields),
                )
            ),
            "field_count": len(canonical_fields),
            "fields": list(canonical_fields.keys()),
            "raw_fields": list(merged.keys()),
            "field_name_mappings": raw_to_canonical,
            "canonical_to_raw": canonical_to_raw,
            "naming_template": template_hint,
            "coverage_target_fields": coverage_target_fields,
            "naming_stats": naming_stats,
            "field_meta": field_meta,
        }

    return Module2MainSchemaResolutionBundle(
        schema_auto_infer_requested=_schema_auto_infer_requested,
        schema_required_from_field_specs=_schema_required_from_field_specs,
        merge_required_field_names=_merge_required_field_names,
        resolve_effective_schema=_resolve_effective_schema,
    )
