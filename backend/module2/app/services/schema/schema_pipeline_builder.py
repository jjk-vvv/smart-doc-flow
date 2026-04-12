from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .result_filter_builder import (
    Module2MainResultFilterBundle,
    build_module2_main_result_filter_bundle,
)
from .schema_context_builder import (
    Module2MainSchemaContextBundle,
    build_module2_main_schema_context_bundle,
)
from .schema_fields_builder import (
    Module2MainSchemaFieldsBundle,
    build_module2_main_schema_fields_bundle,
)
from .schema_inference_builder import (
    Module2MainSchemaInferenceBundle,
    build_module2_main_schema_inference_bundle,
)
from .schema_llm_builder import Module2MainSchemaLlmBundle, build_module2_main_schema_llm_bundle
from .schema_primitives_builder import (
    Module2MainSchemaRequestBundle,
    Module2MainSchemaTimeoutBundle,
    build_module2_main_schema_request_bundle,
    build_module2_main_schema_timeout_bundle,
)
from .schema_resolution_builder import (
    Module2MainSchemaResolutionBundle,
    build_module2_main_schema_resolution_bundle,
)
from .schema_selection_builder import (
    Module2MainSchemaSelectionBundle,
    build_module2_main_schema_selection_bundle,
)
from .schema_semantics_builder import (
    Module2MainSchemaSemanticsBundle,
    build_module2_main_schema_semantics_bundle,
)


_DEFAULT_AUTO_SCHEMA_GENERIC_EN = {
    "appendix",
    "chapter",
    "content",
    "contents",
    "data",
    "equation",
    "eqn",
    "exercise",
    "figure",
    "fig",
    "index",
    "item",
    "items",
    "label",
    "labels",
    "legend",
    "number",
    "page",
    "part",
    "ratio",
    "rate",
    "score",
    "section",
    "series",
    "sheet",
    "system",
    "table",
    "text",
    "value",
    "xaxis",
    "yaxis",
}

_DEFAULT_AUTO_SCHEMA_GENERIC_ZH = {
    "字段",
    "内容",
    "序号",
    "备注",
    "说明",
    "项目",
    "数据",
    "文本",
    "页码",
    "图",
    "图片",
    "表",
    "表格",
    "图例",
    "横轴",
    "纵轴",
    "坐标轴",
    "其中",
}

_DEFAULT_AUTO_SCHEMA_GENERIC_ZH_EXACT = {
    "合计",
    "分类",
    "注释",
    "实验",
    "左轴",
    "单位",
    "床位",
    "名称",
    "图例",
    "机构",
    "农村",
    "右轴",
    "坐标轴",
    "总计",
    "指标",
    "数据",
    "数量",
    "文本",
    "横轴",
    "类型",
    "纵轴",
    "统计",
    "结果",
    "说明",
    "项目",
}

_DEFAULT_AUTO_SCHEMA_GENERIC_ZH_UNIT_TOKENS = {
    "人",
    "个",
    "万元",
    "万张",
    "家",
    "张",
    "年",
    "对",
    "次",
    "项",
}

_DEFAULT_AUTO_SCHEMA_GENERIC_JA_EXACT = {
    "施設名",
    "設備名",
    "装置名",
    "抜出装置",
    "工程名",
    "指標名",
    "評価対象",
    "対象工程",
    "対象核種",
    "核種",
    "製品種別",
    "実績値",
    "設計値",
}

_DEFAULT_LOW_VALUE_RESULT_GENERIC_EN = _DEFAULT_AUTO_SCHEMA_GENERIC_EN | {
    "extract",
    "extracted",
    "generic",
    "metric",
    "output",
    "result",
    "results",
    "summary",
    "unknown",
}

_DEFAULT_LOW_VALUE_RESULT_GENERIC_ZH = _DEFAULT_AUTO_SCHEMA_GENERIC_ZH | _DEFAULT_AUTO_SCHEMA_GENERIC_ZH_EXACT | {
    "其他",
    "分类",
    "标签",
    "名称",
    "类型",
    "结果",
    "统计",
    "指标",
    "摘要",
}

_DEFAULT_SCHEMA_FIGURE_TITLE_TOKENS = (
    "示意图",
    "分布图",
    "趋势图",
    "柱状图",
    "折线图",
    "饼图",
    "散点图",
    "流程图",
    "结构图",
    "对比图",
    "雷达图",
    "热力图",
)

_DEFAULT_SCHEMA_SENTENCE_CUE_TOKENS_ZH = (
    "均为",
    "分别",
    "表现",
    "高于",
    "低于",
    "达到",
    "显著",
    "其中",
    "均在",
    "位于",
    "最多",
    "最少",
    "最高",
    "最低",
    "相对较",
    "说明",
    "显示",
)

_DEFAULT_SCHEMA_SENTENCE_CUE_TOKENS_EN = (
    "shows",
    "showing",
    "indicates",
    "indicating",
    "higher",
    "lower",
    "reaches",
)

_DEFAULT_DATE_FIELD_TOKENS = (
    "日期",
    "时间",
    "年份",
    "年月",
    "季度",
    "时点",
    "date",
    "time",
    "datetime",
    "timestamp",
    "year",
    "month",
)

_DEFAULT_INTEGER_FIELD_TOKENS = (
    "数量",
    "总数",
    "个数",
    "条数",
    "件数",
    "人数",
    "家数",
    "座数",
    "项数",
    "单位数",
    "count",
    "quantity",
    "qty",
    "total_count",
    "item_count",
)

_DEFAULT_NUMBER_FIELD_TOKENS = (
    "金额",
    "总量",
    "总计",
    "合计",
    "均值",
    "平均",
    "比例",
    "占比",
    "比率",
    "税率",
    "增速",
    "增长",
    "成本",
    "费用",
    "单价",
    "总价",
    "值",
    "分数",
    "指数",
    "监测值",
    "amount",
    "total",
    "ratio",
    "rate",
    "percent",
    "price",
    "cost",
    "value",
    "score",
    "index",
    "avg",
    "average",
)


def _coerce_string_set(value: Any, *, fallback: set[str]) -> set[str]:
    if not isinstance(value, (set, frozenset, list, tuple)):
        return set(fallback)
    normalized = {str(item).strip() for item in value if str(item).strip()}
    return normalized or set(fallback)


def _coerce_string_tuple(value: Any, *, fallback: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(value, (set, frozenset, list, tuple)):
        return tuple(fallback)
    normalized = tuple(str(item).strip() for item in value if str(item).strip())
    return normalized or tuple(fallback)


@dataclass(frozen=True)
class Module2MainSchemaPipelineBundle:
    result_filter_bundle: Module2MainResultFilterBundle
    schema_context_bundle: Module2MainSchemaContextBundle
    schema_fields_bundle: Module2MainSchemaFieldsBundle
    schema_request_bundle: Module2MainSchemaRequestBundle
    schema_inference_bundle: Module2MainSchemaInferenceBundle
    schema_llm_bundle: Module2MainSchemaLlmBundle
    schema_semantics_bundle: Module2MainSchemaSemanticsBundle
    schema_selection_bundle: Module2MainSchemaSelectionBundle
    schema_resolution_bundle: Module2MainSchemaResolutionBundle
    schema_timeout_bundle: Module2MainSchemaTimeoutBundle


def build_module2_main_schema_pipeline_bundle(
    *,
    graph: Any,
    getenv: Any,
    main_schema_primitives_bundle: Any,
    main_quality_bundle: Any,
    main_quick_extract_bundle: Any,
    normalize_field_name_fn: Any,
    canonicalize_schema_fields_fn: Any,
    normalize_schema_contracts_fn: Any,
    infer_rule_backed_schema_fields: Any,
    is_word_file: Any,
    schema_noise_rules: dict[str, Any],
    schema_semantic_rules: dict[str, Any],
    schema_selection_rules: dict[str, Any],
    schema_coverage_profiles: dict[str, Any] | None = None,
    auto_schema_stopwords_en: set[str],
    auto_schema_generic_en: set[str],
    auto_schema_generic_zh: set[str],
    auto_schema_generic_zh_exact: set[str],
    auto_schema_generic_zh_unit_tokens: set[str],
    auto_schema_generic_ja_exact: set[str],
    low_value_result_generic_en: set[str],
    low_value_result_generic_zh: set[str],
    schema_figure_title_tokens: tuple[str, ...],
    schema_sentence_cue_tokens_zh: tuple[str, ...],
    schema_sentence_cue_tokens_en: tuple[str, ...],
    date_field_tokens: tuple[str, ...],
    integer_field_tokens: tuple[str, ...],
    number_field_tokens: tuple[str, ...],
) -> Module2MainSchemaPipelineBundle:
    schema_context_bundle = build_module2_main_schema_context_bundle(
        sanitize_field_name=main_schema_primitives_bundle.sanitize_field_name,
        schema_figure_title_tokens=schema_figure_title_tokens,
        schema_sentence_cue_tokens_zh=schema_sentence_cue_tokens_zh,
        schema_sentence_cue_tokens_en=schema_sentence_cue_tokens_en,
    )
    schema_fields_bundle = build_module2_main_schema_fields_bundle(
        sanitize_field_name=main_schema_primitives_bundle.sanitize_field_name,
        coerce_field_type=main_schema_primitives_bundle.coerce_field_type,
        schema_field_type_priority=main_schema_primitives_bundle.schema_field_type_priority,
        schema_field_type_hint=main_schema_primitives_bundle.schema_field_type_hint,
        auto_schema_stopwords_en=set(auto_schema_stopwords_en),
        auto_schema_generic_en=set(auto_schema_generic_en),
        auto_schema_generic_zh=set(auto_schema_generic_zh),
        auto_schema_generic_zh_exact=set(auto_schema_generic_zh_exact),
        auto_schema_generic_zh_unit_tokens=set(auto_schema_generic_zh_unit_tokens),
        auto_schema_generic_ja_exact=set(auto_schema_generic_ja_exact),
    )
    result_filter_bundle = build_module2_main_result_filter_bundle(
        sanitize_field_name=main_schema_primitives_bundle.sanitize_field_name,
        is_low_value_auto_schema_field_name=lambda field_name: schema_fields_bundle.is_low_value_auto_schema_field_name(
            field_name
        ),
        should_prune_shadowed_auto_field_name=lambda short_name, long_name: schema_fields_bundle.should_prune_shadowed_auto_field_name(
            short_name,
            long_name,
        ),
        to_number_or_none=main_quick_extract_bundle.to_number_or_none,
        auto_schema_stopwords_en=set(auto_schema_stopwords_en),
        low_value_result_generic_en=set(low_value_result_generic_en),
        low_value_result_generic_zh=set(low_value_result_generic_zh),
    )
    schema_request_bundle = build_module2_main_schema_request_bundle(
        schema_target_fields=main_schema_primitives_bundle.schema_target_fields,
        normalize_schema_fields=lambda fields, max_fields: schema_fields_bundle.normalize_schema_fields(
            fields,
            max_fields,
        ),
    )
    schema_inference_bundle = build_module2_main_schema_inference_bundle(
        sanitize_field_name=main_schema_primitives_bundle.sanitize_field_name,
        is_low_value_auto_schema_field_name=schema_fields_bundle.is_low_value_auto_schema_field_name,
        filter_auto_schema_fields=schema_fields_bundle.filter_auto_schema_fields,
        schema_field_type_priority=main_schema_primitives_bundle.schema_field_type_priority,
        schema_context_clean_text=schema_context_bundle.schema_context_clean_text,
        looks_like_schema_figure_title=schema_context_bundle.looks_like_schema_figure_title,
        looks_like_schema_sentence_fragment=schema_context_bundle.looks_like_schema_sentence_fragment,
        date_field_tokens=date_field_tokens,
        integer_field_tokens=integer_field_tokens,
        number_field_tokens=number_field_tokens,
        schema_heuristic_stop_tokens=set(schema_noise_rules["schema_heuristic_stop_tokens"]),
    )
    schema_llm_bundle = build_module2_main_schema_llm_bundle(
        graph=graph,
        getenv=getenv,
        extract_text_for_schema=schema_context_bundle.extract_text_for_schema,
        upsert_schema_field_candidate=schema_fields_bundle.upsert_schema_field_candidate,
        filter_auto_schema_fields=schema_fields_bundle.filter_auto_schema_fields,
    )
    schema_semantics_bundle = build_module2_main_schema_semantics_bundle(
        sanitize_field_name=main_schema_primitives_bundle.sanitize_field_name,
        field_name_word_tokens=schema_fields_bundle.field_name_word_tokens,
        coerce_field_type=main_schema_primitives_bundle.coerce_field_type,
        schema_semantic_rules=schema_semantic_rules,
        looks_like_schema_figure_title=schema_context_bundle.looks_like_schema_figure_title,
        looks_like_schema_sentence_fragment=schema_context_bundle.looks_like_schema_sentence_fragment,
    )
    schema_selection_bundle = build_module2_main_schema_selection_bundle(
        sanitize_field_name=main_schema_primitives_bundle.sanitize_field_name,
        is_low_value_auto_schema_field_name=schema_fields_bundle.is_low_value_auto_schema_field_name,
        semantic_closure_fragment_alias_keys=schema_semantics_bundle.semantic_closure_fragment_alias_keys,
        schema_semantic_label_strength=schema_semantics_bundle.schema_semantic_label_strength,
        is_semantically_weak_field_label=schema_semantics_bundle.is_semantically_weak_field_label,
        normalize_field_name_fn=normalize_field_name_fn,
        coerce_field_type=main_schema_primitives_bundle.coerce_field_type,
        schema_semantic_rules=schema_semantic_rules,
        schema_coverage_profiles=schema_coverage_profiles,
    )
    schema_resolution_bundle = build_module2_main_schema_resolution_bundle(
        schema_target_fields=main_schema_primitives_bundle.schema_target_fields,
        normalize_schema_fields=schema_fields_bundle.normalize_schema_fields,
        select_best_canonical_schema_fields=schema_selection_bundle.select_best_canonical_schema_fields,
        apply_conservative_semantic_closure=schema_selection_bundle.apply_conservative_semantic_closure,
        upsert_schema_field_candidate=schema_fields_bundle.upsert_schema_field_candidate,
        filter_auto_schema_fields=schema_fields_bundle.filter_auto_schema_fields,
        infer_schema_fields_llm=schema_llm_bundle.infer_schema_fields_llm,
        infer_rule_backed_schema_fields=infer_rule_backed_schema_fields,
        infer_schema_fields_heuristic=schema_inference_bundle.infer_schema_fields_heuristic,
        canonicalize_schema_fields_fn=canonicalize_schema_fields_fn,
        normalize_schema_contracts_fn=normalize_schema_contracts_fn,
        schema_selection_rules=schema_selection_rules,
        schema_coverage_profiles=schema_coverage_profiles,
        getenv=getenv,
    )
    schema_timeout_bundle = build_module2_main_schema_timeout_bundle(
        getenv=getenv,
        is_word_file=is_word_file,
        schema_context_clean_text=schema_context_bundle.schema_context_clean_text,
        count_table_cells=main_quality_bundle.count_table_cells,
        count_figure_dataframe_cells=main_quality_bundle.count_figure_dataframe_cells,
    )
    return Module2MainSchemaPipelineBundle(
        result_filter_bundle=result_filter_bundle,
        schema_context_bundle=schema_context_bundle,
        schema_fields_bundle=schema_fields_bundle,
        schema_request_bundle=schema_request_bundle,
        schema_inference_bundle=schema_inference_bundle,
        schema_llm_bundle=schema_llm_bundle,
        schema_semantics_bundle=schema_semantics_bundle,
        schema_selection_bundle=schema_selection_bundle,
        schema_resolution_bundle=schema_resolution_bundle,
        schema_timeout_bundle=schema_timeout_bundle,
    )


def build_module2_main_schema_pipeline_bundle_from_rules(
    *,
    graph: Any,
    getenv: Any,
    main_schema_primitives_bundle: Any,
    main_quality_bundle: Any,
    main_quick_extract_bundle: Any,
    normalize_field_name_fn: Any,
    canonicalize_schema_fields_fn: Any,
    normalize_schema_contracts_fn: Any,
    infer_rule_backed_schema_fields: Any,
    is_word_file: Any,
    schema_noise_rules: dict[str, Any],
    schema_semantic_rules: dict[str, Any],
    schema_selection_rules: dict[str, Any],
    field_type_rules: dict[str, Any],
    schema_coverage_profiles: dict[str, Any] | None = None,
) -> Module2MainSchemaPipelineBundle:
    return build_module2_main_schema_pipeline_bundle(
        graph=graph,
        getenv=getenv,
        main_schema_primitives_bundle=main_schema_primitives_bundle,
        main_quality_bundle=main_quality_bundle,
        main_quick_extract_bundle=main_quick_extract_bundle,
        normalize_field_name_fn=normalize_field_name_fn,
        canonicalize_schema_fields_fn=canonicalize_schema_fields_fn,
        normalize_schema_contracts_fn=normalize_schema_contracts_fn,
        infer_rule_backed_schema_fields=infer_rule_backed_schema_fields,
        is_word_file=is_word_file,
        schema_noise_rules=schema_noise_rules,
        schema_semantic_rules=schema_semantic_rules,
        schema_selection_rules=schema_selection_rules,
        schema_coverage_profiles=schema_coverage_profiles,
        auto_schema_stopwords_en=_coerce_string_set(
            schema_noise_rules.get("auto_schema_stopwords_en"),
            fallback=set(),
        ),
        auto_schema_generic_en=_coerce_string_set(
            schema_noise_rules.get("auto_schema_generic_en"),
            fallback=_DEFAULT_AUTO_SCHEMA_GENERIC_EN,
        ),
        auto_schema_generic_zh=_coerce_string_set(
            schema_noise_rules.get("auto_schema_generic_zh"),
            fallback=_DEFAULT_AUTO_SCHEMA_GENERIC_ZH,
        ),
        auto_schema_generic_zh_exact=_coerce_string_set(
            schema_noise_rules.get("auto_schema_generic_zh_exact"),
            fallback=_DEFAULT_AUTO_SCHEMA_GENERIC_ZH_EXACT,
        ),
        auto_schema_generic_zh_unit_tokens=_coerce_string_set(
            schema_noise_rules.get("auto_schema_generic_zh_unit_tokens"),
            fallback=_DEFAULT_AUTO_SCHEMA_GENERIC_ZH_UNIT_TOKENS,
        ),
        auto_schema_generic_ja_exact=_coerce_string_set(
            schema_noise_rules.get("auto_schema_generic_ja_exact"),
            fallback=_DEFAULT_AUTO_SCHEMA_GENERIC_JA_EXACT,
        ),
        low_value_result_generic_en=_coerce_string_set(
            schema_noise_rules.get("low_value_result_generic_en"),
            fallback=_DEFAULT_LOW_VALUE_RESULT_GENERIC_EN,
        ),
        low_value_result_generic_zh=_coerce_string_set(
            schema_noise_rules.get("low_value_result_generic_zh"),
            fallback=_DEFAULT_LOW_VALUE_RESULT_GENERIC_ZH,
        ),
        schema_figure_title_tokens=_DEFAULT_SCHEMA_FIGURE_TITLE_TOKENS,
        schema_sentence_cue_tokens_zh=_DEFAULT_SCHEMA_SENTENCE_CUE_TOKENS_ZH,
        schema_sentence_cue_tokens_en=_DEFAULT_SCHEMA_SENTENCE_CUE_TOKENS_EN,
        date_field_tokens=_coerce_string_tuple(
            field_type_rules.get("date_tokens"),
            fallback=_DEFAULT_DATE_FIELD_TOKENS,
        ),
        integer_field_tokens=_coerce_string_tuple(
            field_type_rules.get("integer_tokens"),
            fallback=_DEFAULT_INTEGER_FIELD_TOKENS,
        ),
        number_field_tokens=_coerce_string_tuple(
            field_type_rules.get("number_tokens"),
            fallback=_DEFAULT_NUMBER_FIELD_TOKENS,
        ),
    )
