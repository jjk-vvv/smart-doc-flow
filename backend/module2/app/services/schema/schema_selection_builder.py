from __future__ import annotations

"""Schema selection bundle builder for module2 service layer."""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple


SanitizeFieldNameFn = Callable[[Any], str]
IsLowValueFieldNameFn = Callable[[Any], bool]
SemanticClosureFragmentAliasKeysFn = Callable[[Dict[str, Any]], set[str]]
SchemaSemanticLabelStrengthFn = Callable[[str, Any, Dict[str, Any]], int]
IsSemanticallyWeakFieldLabelFn = Callable[[str], bool]
NormalizeFieldNameFn = Callable[..., Dict[str, Any]]
CoerceFieldTypeFn = Callable[[Any], str]


@dataclass(frozen=True)
class Module2MainSchemaSelectionBundle:
    pick_semantic_closure_candidate: Callable[..., Optional[Dict[str, Any]]]
    apply_conservative_semantic_closure: Callable[..., Tuple[Dict[str, str], Dict[str, Dict[str, Any]], Dict[str, str], Dict[str, str], Dict[str, Any]]]
    schema_field_selection_score: Callable[..., int]
    select_best_canonical_schema_fields: Callable[..., Tuple[Dict[str, str], Dict[str, Dict[str, Any]]]]


def build_module2_main_schema_selection_bundle(
    *,
    sanitize_field_name: SanitizeFieldNameFn,
    is_low_value_auto_schema_field_name: IsLowValueFieldNameFn,
    semantic_closure_fragment_alias_keys: SemanticClosureFragmentAliasKeysFn,
    schema_semantic_label_strength: SchemaSemanticLabelStrengthFn,
    is_semantically_weak_field_label: IsSemanticallyWeakFieldLabelFn,
    normalize_field_name_fn: NormalizeFieldNameFn,
    coerce_field_type: CoerceFieldTypeFn,
    schema_semantic_rules: Dict[str, Any],
    schema_coverage_profiles: Dict[str, Any] | None = None,
) -> Module2MainSchemaSelectionBundle:
    def _coverage_profile_for_template(template_hint: str) -> Dict[str, Any]:
        templates = (
            dict(schema_coverage_profiles.get("templates") or {})
            if isinstance(schema_coverage_profiles, dict)
            else {}
        )
        return dict(templates.get(str(template_hint or "").strip()) or {})

    def _field_matches_profile(field_name: str, profile_fields: Any) -> bool:
        normalized_field_name = str(field_name or "").strip()
        if not normalized_field_name:
            return False
        normalized_field_key = sanitize_field_name(normalized_field_name)
        for item in profile_fields if isinstance(profile_fields, (list, tuple, set, frozenset)) else ():
            profile_field_name = str(item or "").strip()
            if not profile_field_name:
                continue
            if normalized_field_name == profile_field_name:
                return True
            if normalized_field_key and sanitize_field_name(profile_field_name) == normalized_field_key:
                return True
        return False

    def _match_profile_fields_in_order(profile_fields: Any, available_field_names: Any) -> List[str]:
        available_by_name: Dict[str, str] = {}
        available_by_key: Dict[str, str] = {}
        for item in available_field_names if isinstance(available_field_names, (list, tuple, set, frozenset, dict)) else ():
            field_name = str(item or "").strip()
            if not field_name:
                continue
            available_by_name.setdefault(field_name, field_name)
            sanitized = sanitize_field_name(field_name)
            if sanitized:
                available_by_key.setdefault(sanitized, field_name)

        matched: List[str] = []
        seen: set[str] = set()
        for item in profile_fields if isinstance(profile_fields, (list, tuple, set, frozenset)) else ():
            profile_field_name = str(item or "").strip()
            if not profile_field_name:
                continue
            candidate = available_by_name.get(profile_field_name)
            if candidate is None:
                candidate = available_by_key.get(sanitize_field_name(profile_field_name))
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            matched.append(candidate)
        return matched

    def _pick_semantic_closure_candidate(
        field_name: str,
        field_type: Any,
        field_meta: Dict[str, Any],
        *,
        template_hint: str,
    ) -> Optional[Dict[str, Any]]:
        current_strength = schema_semantic_label_strength(field_name, field_type, field_meta)
        rules = schema_semantic_rules
        raw_names = [str(item).strip() for item in field_meta.get("raw_names", []) if str(item).strip()]
        aliases = [str(item).strip() for item in field_meta.get("aliases", []) if str(item).strip()]
        blocked_alias_keys = semantic_closure_fragment_alias_keys(field_meta)
        best_by_label: Dict[str, Dict[str, Any]] = {}

        for source_kind, source_text in [("raw", item) for item in raw_names] + [("alias", item) for item in aliases]:
            if not source_text:
                continue
            source_key = sanitize_field_name(source_text)
            if source_kind == "alias" and source_key and source_key in blocked_alias_keys:
                continue
            normalized = normalize_field_name_fn(
                source_text,
                type_hint=field_type,
                template_hint=template_hint,
            )
            candidate_label = sanitize_field_name(
                normalized.get("canonical_label")
                or normalized.get("canonical_base_label")
                or source_text
            )
            if not candidate_label or candidate_label == field_name:
                continue
            if is_low_value_auto_schema_field_name(candidate_label):
                continue

            candidate_meta = dict(field_meta)
            candidate_meta.update(
                {
                    "canonical_label": candidate_label,
                    "canonical_base_label": str(
                        normalized.get("canonical_base_label")
                        or field_meta.get("canonical_base_label")
                        or candidate_label
                    ).strip(),
                    "unit_norm": str(normalized.get("unit_norm") or field_meta.get("unit_norm") or "").strip(),
                    "unit_raw": str(normalized.get("unit_raw") or field_meta.get("unit_raw") or "").strip(),
                    "dimensions": normalized.get("dimensions") or field_meta.get("dimensions") or {},
                    "normalization_rule_id": str(
                        normalized.get("normalization_rule_id")
                        or field_meta.get("normalization_rule_id")
                        or ""
                    ).strip(),
                    "normalization_confidence": max(
                        float(field_meta.get("normalization_confidence", 0.0) or 0.0),
                        float(normalized.get("normalization_confidence", 0.0) or 0.0),
                    ),
                }
            )
            candidate_strength = schema_semantic_label_strength(candidate_label, field_type, candidate_meta)
            if source_kind == "raw":
                candidate_strength += 4
            if len(candidate_label) > len(field_name):
                candidate_strength += 2

            existing = best_by_label.get(candidate_label)
            if existing is None or candidate_strength > int(existing.get("strength", -999)):
                best_by_label[candidate_label] = {
                    "label": candidate_label,
                    "meta": candidate_meta,
                    "strength": candidate_strength,
                    "source_kind": source_kind,
                    "source_text": source_text,
                    "gain": candidate_strength - current_strength,
                }

        if not best_by_label:
            return None

        ranked = sorted(
            best_by_label.values(),
            key=lambda item: (
                -int(item.get("strength", -999)),
                -len(str(item.get("label") or "")),
                str(item.get("label") or ""),
            ),
        )
        best = ranked[0]
        second_strength = int(ranked[1].get("strength", -999)) if len(ranked) > 1 else -999
        best_strength = int(best.get("strength", -999))
        best_gain = int(best.get("gain", -999))

        if best_strength < int(rules.get("closure_min_score", 8) or 8):
            return None
        if best_gain < int(rules.get("closure_min_gain", 8) or 8):
            return None
        if len(ranked) > 1 and best_strength - second_strength < int(rules.get("closure_min_unique_gap", 3) or 3):
            return None
        if not is_semantically_weak_field_label(field_name) and best_gain < int(rules.get("closure_min_gain", 8) or 8) + 4:
            return None

        return best

    def _apply_conservative_semantic_closure(
        canonical_fields: Dict[str, str],
        field_meta: Dict[str, Dict[str, Any]],
        raw_to_canonical: Dict[str, str],
        canonical_to_raw: Dict[str, str],
        *,
        template_hint: str,
    ) -> Tuple[Dict[str, str], Dict[str, Dict[str, Any]], Dict[str, str], Dict[str, str], Dict[str, Any]]:
        if not canonical_fields:
            return dict(canonical_fields), dict(field_meta), dict(raw_to_canonical), dict(canonical_to_raw), {
                "semantic_closure_renamed_count": 0,
                "semantic_closure_fields": {},
            }

        renamed_fields: Dict[str, str] = {}
        next_fields: Dict[str, str] = {}
        next_meta: Dict[str, Dict[str, Any]] = {}
        label_remap: Dict[str, str] = {}
        original_labels = set(canonical_fields.keys())

        for field_name, field_type in canonical_fields.items():
            meta = dict(field_meta.get(field_name, {}))
            target_label = field_name
            target_meta = dict(meta)
            candidate = _pick_semantic_closure_candidate(
                field_name,
                field_type,
                meta,
                template_hint=template_hint,
            )
            if candidate:
                candidate_label = str(candidate.get("label") or "").strip()
                if candidate_label and candidate_label not in original_labels and candidate_label not in next_fields:
                    target_label = candidate_label
                    target_meta.update(dict(candidate.get("meta") or {}))
                    target_meta["canonical_label"] = candidate_label
                    target_meta["semantic_closure_source"] = str(candidate.get("source_kind") or "").strip()
                    target_meta["semantic_closure_gain"] = int(candidate.get("gain", 0) or 0)
                    renamed_fields[field_name] = candidate_label

            label_remap[field_name] = target_label
            next_fields[target_label] = field_type
            next_meta[target_label] = target_meta

        next_raw_to_canonical = {
            raw_name: label_remap.get(canonical_name, canonical_name)
            for raw_name, canonical_name in raw_to_canonical.items()
        }
        next_canonical_to_raw: Dict[str, str] = {}
        for raw_name, canonical_name in next_raw_to_canonical.items():
            next_canonical_to_raw.setdefault(canonical_name, raw_name)
        for canonical_name, raw_name in canonical_to_raw.items():
            next_canonical_to_raw.setdefault(label_remap.get(canonical_name, canonical_name), raw_name)

        return next_fields, next_meta, next_raw_to_canonical, next_canonical_to_raw, {
            "semantic_closure_renamed_count": len(renamed_fields),
            "semantic_closure_fields": renamed_fields,
        }

    def _schema_field_selection_score(
        field_name: str,
        field_type: Any,
        field_meta: Dict[str, Any],
        *,
        template_hint: str,
    ) -> int:
        label = str(field_name or "").strip()
        score = 0
        coverage_profile = _coverage_profile_for_template(template_hint)
        semantic_strength = schema_semantic_label_strength(label, field_type, field_meta)
        if is_low_value_auto_schema_field_name(label):
            score -= 200
        score += semantic_strength * 10
        if _field_matches_profile(label, coverage_profile.get("critical_fields", ())):
            score += 1200
        elif _field_matches_profile(label, coverage_profile.get("preferred_fields", ())):
            score += 220
        if field_meta.get("normalization_rule_id"):
            score += 400
        score += int(round(float(field_meta.get("normalization_confidence", 0.0) or 0.0) * 100))
        if field_meta.get("dimensions"):
            score += 40
        if field_meta.get("unit_norm"):
            score += 20
        if coerce_field_type(field_type) != "string":
            score += 12

        lowered = label.lower()
        if template_hint == "government_statistical_bulletin":
            if any(token in label for token in ("\u7edf\u8ba1", "\u4fdd\u969c", "\u5e8a\u4f4d", "\u4eba\u53e3", "\u9500\u552e\u989d", "\u793e\u4f1a\u7ec4\u7ec7", "\u767b\u8bb0", "\u706b\u5316", "\u673a\u6784", "\u57fa\u91d1\u4f1a")):
                score += 18
        elif template_hint == "chemical_process_experiment":
            if any(token in lowered for token in ("tbp", "dfru", "runo")):
                score += 30
            if any(token in label for token in ("\u76f8\u5bf9\u6d41\u91cf", "\u6d17\u6da4\u6bb5", "\u8fdb\u6599\u6bb5", "\u53cd\u8433\u6bb5", "\u603b\u4f53")):
                score += 24
        elif template_hint == "scientific_appendix_exercise":
            if any(token in label for token in ("\u4e60\u9898", "\u7b54\u6848", "\u540c\u4f4d\u7d20", "\u7c92\u5b50", "\u7269\u7406\u6027\u8d28")):
                score += 20
        elif template_hint == "xlsx_business_ledger":
            if any(token in label for token in ("\u8ba2\u5355", "\u9500\u552e", "\u5546\u54c1", "\u5e97\u94fa", "SKU", "\u7528\u6237")):
                score += 18
            if label in ("\u8ba2\u5355\u72b6\u6001", "\u652f\u4ed8\u65b9\u5f0f", "\u914d\u9001\u65b9\u5f0f", "\u9000\u6362\u653f\u7b56", "\u552e\u540e\u653f\u7b56"):
                score += 40
            if label in ("\u5ba2\u6237\u8bc4\u4ef7", "\u4fc3\u9500\u6d3b\u52a8", "\u7279\u6b8a\u9700\u6c42", "\u8ba2\u5355\u5904\u7406\u4eba"):
                score -= 24
        elif template_hint == "recruitment_hr_table":
            if any(token in label for token in ("\u62db\u8003", "\u804c\u4f4d", "\u9762\u8bd5", "\u90e8\u95e8", "\u4e13\u4e1a", "\u5b66\u5386", "\u5b66\u4f4d")):
                score += 18
            if any(token in label for token in ("\u62db\u8003\u4eba\u6570", "\u62db\u8003\u804c\u4f4d", "\u804c\u4f4d\u4ee3\u7801", "\u90e8\u95e8\u4ee3\u7801", "\u9762\u8bd5\u4eba\u5458\u6bd4\u4f8b")):
                score += 12
        elif template_hint == "clinical_patient_dataset":
            if any(token in label for token in ("\u60a3\u8005", "\u5c31\u8bca", "\u4f4f\u9662", "\u8bca\u65ad", "\u8840\u6e05\u8461\u8404\u7cd6", "\u7cd6\u5316\u8840\u7ea2\u86cb\u767d")):
                score += 18
            if any(token in label for token in ("\u5c31\u8bcaID", "\u60a3\u8005\u7f16\u53f7", "\u4f4f\u9662\u5929\u6570", "\u8bca\u65ad\u6570\u91cf", "\u8840\u6e05\u8461\u8404\u7cd6\u6700\u5927\u503c", "\u7cd6\u5316\u8840\u7ea2\u86cb\u767d\u7ed3\u679c")):
                score += 12
        elif template_hint == "epidemic_surveillance_dataset":
            if any(token in label for token in ("\u56fd\u5bb6", "\u5730\u533a", "\u5927\u6d32", "\u68c0\u6d4b", "\u75c5\u4f8b", "\u6b7b\u4ea1", "\u533b\u9662\u5e8a\u4f4d", "\u533b\u751f", "\u65e5\u671f")):
                score += 18
            if any(token in label for token in ("\u6bcf\u65e5\u68c0\u6d4b\u6570", "\u75c5\u4f8b\u6570", "\u6b7b\u4ea1\u6570", "\u6bcf\u5343\u4eba\u533b\u9662\u5e8a\u4f4d\u6570", "\u6bcf\u5343\u4eba\u533b\u751f\u6570", "65\u5c81\u53ca\u4ee5\u4e0a\u4eba\u53e3\u5360\u6bd4")):
                score += 12
            if label in ("\u56fd\u5bb6/\u5730\u533a", "\u65e5\u671f", "\u6bcf\u65e5\u68c0\u6d4b\u6570", "\u75c5\u4f8b\u6570", "\u6b7b\u4ea1\u6570"):
                score += 80
            if "\u4eba\u53e3\u5360\u6bd4" in label and "65\u5c81\u53ca\u4ee5\u4e0a" in label:
                score -= 320
            if label == "\u5927\u6d32":
                score -= 60
        elif template_hint == "environment_monitoring_report":
            if any(token in label for token in ("\u76d1\u6d4b", "\u7ad9\u70b9", "\u7a7a\u6c14\u8d28\u91cf", "PM", "AQI", "\u81ed\u6c27", "\u4e8c\u6c27\u5316", "\u4e00\u6c27\u5316\u78b3")):
                score += 18
            if label in ("\u57ce\u5e02", "\u533a\u53bf"):
                score += 320
            if label in ("\u76d1\u6d4b\u65f6\u95f4", "\u7ad9\u70b9\u7f16\u7801", "\u7ad9\u70b9\u540d\u79f0", "\u7a7a\u6c14\u8d28\u91cf\u6307\u6570"):
                score += 90
            if label in ("\u9996\u8981\u6c61\u67d3\u7269", "\u6c61\u67d3\u7c7b\u578b"):
                score -= 80
        return score

    def _select_best_canonical_schema_fields(
        canonical_fields: Dict[str, str],
        field_meta: Dict[str, Dict[str, Any]],
        *,
        max_fields: int,
        template_hint: str,
    ) -> Tuple[Dict[str, str], Dict[str, Dict[str, Any]]]:
        coverage_profile = _coverage_profile_for_template(template_hint)
        ranked: List[Tuple[int, str]] = []
        for field_name, field_type in canonical_fields.items():
            meta = field_meta.get(field_name, {})
            score = _schema_field_selection_score(
                field_name,
                field_type,
                meta,
                template_hint=template_hint,
            )
            ranked.append((score, field_name))

        ranked.sort(key=lambda item: (-item[0], item[1]))
        min_selection_score = int(schema_semantic_rules.get("selection_min_score", 0) or 0)
        ranked_names = [field_name for score, field_name in ranked if score >= min_selection_score]
        if not ranked_names:
            ranked_names = [field_name for _, field_name in ranked]

        selected_names: List[str] = []
        selected_name_set: set[str] = set()
        for field_name in _match_profile_fields_in_order(
            coverage_profile.get("critical_fields", ()),
            canonical_fields.keys(),
        ):
            if len(selected_names) >= max_fields:
                break
            selected_names.append(field_name)
            selected_name_set.add(field_name)

        for field_name in ranked_names:
            if len(selected_names) >= max_fields:
                break
            if field_name in selected_name_set:
                continue
            selected_names.append(field_name)
            selected_name_set.add(field_name)

        selected_name_set = set(selected_names)
        selected_fields = {
            field_name: canonical_fields[field_name]
            for field_name in selected_names
            if field_name in canonical_fields
        }
        selected_meta = {field_name: dict(field_meta.get(field_name, {})) for field_name in selected_name_set}
        return selected_fields, selected_meta

    return Module2MainSchemaSelectionBundle(
        pick_semantic_closure_candidate=_pick_semantic_closure_candidate,
        apply_conservative_semantic_closure=_apply_conservative_semantic_closure,
        schema_field_selection_score=_schema_field_selection_score,
        select_best_canonical_schema_fields=_select_best_canonical_schema_fields,
    )
