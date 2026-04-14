from __future__ import annotations

import re
from dataclasses import dataclass


def normalize_question(question: str) -> str:
    return str(question or "").strip()


def lower_question(question: str) -> str:
    return normalize_question(question).lower()


def contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers if marker)


def is_strict_minimal_request(question: str) -> bool:
    text = normalize_question(question)
    lowered = text.lower()
    return contains_any(
        text,
        (
            "只回答",
            "只回",
            "仅回答",
            "仅回",
            "只给",
            "仅输出",
            "不要解释",
            "不要带其他内容",
        ),
    ) or contains_any(
        lowered,
        (
            "just answer",
            "only answer",
            "only give me",
            "answer only",
            "no explanation",
        ),
    )


def wants_brief_answer(question: str) -> bool:
    text = normalize_question(question)
    lowered = text.lower()
    return is_strict_minimal_request(text) or contains_any(
        text,
        ("简要", "简单说", "简短", "一句话", "先说结论", "直接说"),
    ) or contains_any(
        lowered,
        ("briefly", "short answer", "one sentence", "concisely"),
    )


def wants_detailed_answer(question: str) -> bool:
    text = normalize_question(question)
    lowered = text.lower()
    return contains_any(
        text,
        ("详细", "系统", "全面", "展开", "具体分析", "分阶段", "分步骤", "逐步", "完整"),
    ) or contains_any(
        lowered,
        ("detailed", "systematic", "comprehensive", "step by step", "in detail", "fully"),
    )


def is_capability_question(question: str) -> bool:
    text = normalize_question(question)
    lowered = text.lower()
    chinese_markers = (
        "能做什么",
        "可以做什么",
        "可以帮我做什么",
        "你能帮我做哪些事",
        "怎么开始",
        "先做什么",
        "建议怎么推进",
    )
    english_markers = (
        "what can you do",
        "how can you help",
        "what can you help me with",
        "what are your capabilities",
        "where should i start",
    )
    if contains_any(text, chinese_markers) or contains_any(lowered, english_markers):
        return True
    return bool(
        re.search(r"\bwhat\s+can\s+you\s+help\s+(?:me\s+)?with\b", lowered)
        or re.search(r"\btell\s+me\s+what\s+you\s+can\s+help\s+(?:me\s+)?with\b", lowered)
        or re.search(r"\bhow\s+you\s+can\s+help\b", lowered)
    )


def is_web_search_request(question: str) -> bool:
    lowered = lower_question(question)
    explicit_markers = (
        "联网",
        "联网搜索",
        "联网查",
        "上网查",
        "搜一下官网",
        "查一下官网",
        "查一下网",
        "搜索网页",
        "搜索官网",
        "web search",
        "search the web",
        "search online",
        "look up online",
        "browse the web",
    )
    soft_markers = (
        "官方",
        "官网",
        "官方资料",
        "official",
        "official site",
        "official homepage",
        "official materials",
        "latest",
        "最近",
        "最新",
        "新闻",
        "实时",
        "news",
        "real-time",
    )
    database_markers = (
        "database",
        "postgres",
        "postgresql",
        "sql",
        "schema",
        "table design",
        "table draft",
        "current database",
        "数据库",
        "表结构",
        "建表",
        "sql草案",
        "sql 语句",
        "查数据库",
        "查询数据库",
    )
    explicit = contains_any(lowered, explicit_markers)
    if explicit:
        return True
    if contains_any(lowered, database_markers):
        return False
    if is_document_specific_question(question):
        return False
    return contains_any(lowered, soft_markers)


def is_schema_design_request(question: str) -> bool:
    lowered = lower_question(question)
    if contains_any(
        lowered,
        (
            "表结构",
            "建表",
            "建库",
            "数据库设计",
            "表设计",
            "字段设计",
            "字段规划",
            "创建表",
            "新建表",
            "设计一张表",
            "设计数据库表",
            "ddl",
            "schema",
            "schema design",
            "table design",
            "schema draft",
            "table draft",
            "table structure",
            "create table",
            "design a table",
            "design a postgresql table",
            "postgresql table draft",
            "database table draft",
            "ddl draft",
            "建表草案",
            "表结构草案",
        ),
    ):
        return True
    schema_markers = ("主键", "索引", "唯一键", "字段", "字段类型", "约束")
    table_markers = ("表", "数据表", "postgresql", "postgres", "table")
    if contains_any(lowered, schema_markers) and contains_any(lowered, table_markers):
        return True
    if "设计一张" in lowered and contains_any(lowered, table_markers):
        return True
    if contains_any(lowered, ("design", "draft", "model", "structure")) and contains_any(
        lowered,
        ("postgresql table", "database table", "document fields", "field extraction", "schema"),
    ):
        return True
    return False


def is_sql_request(question: str) -> bool:
    lowered = lower_question(question)
    if contains_any(
        lowered,
        (
            "nl2sql",
            "转sql",
            "sql草案",
            "sql 草案",
            "sql语句",
            "写sql",
            "写一条sql",
            "查数据库",
            "查询数据库",
            "执行sql",
            "运行sql",
            "删改查",
            "入库",
            "写入数据库",
            "读数据库",
            "run sql",
            "draft sql",
            "query the database",
            "read-only sql",
            "insert ",
            "update ",
            "delete ",
            "alter table",
            "drop table",
            "select ",
        ),
    ):
        return True
    if re.search(r"\bsql\b", lowered):
        return True
    if re.search(r"^\s*(select|insert|update|delete|alter|drop|create)\b", lowered):
        return True
    return bool(re.search(r"^\s*with\s+[a-z0-9_\"`]+\s+as\s*\(", lowered))


def is_general_method_question(question: str) -> bool:
    text = normalize_question(question)
    lowered = text.lower()
    method_markers = (
        "怎么做",
        "如何做",
        "通常会怎么处理",
        "一般怎么处理",
        "思路",
        "流程",
        "分阶段",
        "为什么",
        "原理",
        "最佳实践",
        "what is the best way",
        "how do you usually",
        "how would you handle",
        "workflow",
        "best practice",
    )
    domain_markers = (
        "文档处理",
        "ocr",
        "表格恢复",
        "信息抽取",
        "非结构化文档",
        "扫描件",
        "扫描文档",
        "版式",
        "版面分析",
        "向量数据库",
        "向量检索",
        "知识库",
        "重排",
        "图片理解",
        "图表理解",
        "document processing",
        "layout analysis",
        "table recovery",
        "information extraction",
        "vector database",
        "retrieval",
        "knowledge base",
    )
    return contains_any(text, method_markers) and contains_any(lowered, domain_markers)


def is_document_specific_question(question: str) -> bool:
    text = normalize_question(question)
    lowered = text.lower()
    return contains_any(
        text,
        (
            "这份文档",
            "这个文档",
            "该文档",
            "当前文档",
            "这份文件",
            "这个文件",
            "该文件",
            "当前文件",
            "这张表",
            "这个表",
            "表格里",
            "表里",
            "表中",
            "图里",
            "图片里",
            "这一页",
            "这页",
            "文档里",
            "文件里",
            "上传的文件",
            "当前对象",
            "这条记录",
            "这一行",
            "工作表",
            "sheet",
        ),
    ) or contains_any(
        lowered,
        (
            "this document",
            "this file",
            "bound document",
            "bound file",
            "current document",
            "current file",
            "selected document",
            "selected file",
            "this table",
            "in this table",
            "this row",
            "this record",
            "uploaded file",
            "worksheet",
            "sheet",
            "this image",
            "this figure",
        ),
    )


def is_document_risk_review_question(question: str) -> bool:
    lowered = lower_question(question)
    return contains_any(
        lowered,
        (
            "第一次核对",
            "首次核对",
            "风险点",
            "优先核对",
            "优先检查",
            "最应该先核对",
            "最值得先核对",
            "最该先看",
            "最该先查",
            "先核对哪",
            "先检查哪",
            "最容易出错",
            "先盯哪几项",
            "先看哪3类信息",
            "先看哪 3 类信息",
            "重点核对",
            "risk point",
            "risk review",
            "biggest risk point",
            "biggest verification risk",
            "highest priority risk",
            "what should i check first",
            "what should i verify first",
            "most important checks",
        ),
    )


def is_broad_document_question(question: str) -> bool:
    text = normalize_question(question)
    lowered = text.lower()
    if contains_any(
        text,
        (
            "主要讲了什么",
            "主要在讲什么",
            "主要在说什么",
            "重点是什么",
            "整体情况",
            "核心内容",
            "主要内容是什么",
            "大意是什么",
            "怎么理解这份文档",
            "这份文档讲的是什么",
            "这份文档主要描述什么",
            "这个文档主要描述什么",
            "文档摘要",
            "总结一下",
            "概括一下",
            "按年份怎么区分",
            "差异是什么",
            "全貌",
        ),
    ):
        return True
    if contains_any(
        lowered,
        (
            "main points",
            "overall summary",
            "summary of this document",
            "summarize this document",
            "summarize the bound document",
            "summarize the selected document",
            "summarize the current document",
            "what is this document about",
            "what does this document mainly describe",
            "what is this document mainly about",
            "what is the document mainly about",
            "what is this file mainly about",
            "how should i understand this document",
            "big picture",
        ),
    ):
        return True
    if re.search(r"\b(?:summari[sz]e|summary|sum up)\b", lowered) and re.search(
        r"\b(?:document|file|report|bulletin)\b",
        lowered,
    ):
        return True
    if re.search(r"(总结|概括|摘要)", text) and re.search(r"(文档|文件|报告|公报|当前文档|这份文档|这个文档)", text):
        return True
    if re.search(
        r"\b(?:document|file|report|bulletin)\b.*\bmain(?:ly)?\s+about\b",
        lowered,
    ):
        return True
    return is_document_risk_review_question(question)


def is_field_lookup_question(question: str) -> bool:
    text = normalize_question(question)
    lowered = text.lower()
    return contains_any(
        text,
        (
            "字段",
            "提取值",
            "值是什么",
            "年份是什么",
            "标题是什么",
            "文件名",
            "页码",
            "第几页",
            "出处",
            "金额",
            "数量",
            "总数",
            "是多少",
            "数值",
            "病例数",
            "死亡数",
            "检测数",
            "监测值",
            "浓度",
        ),
    ) or contains_any(
        lowered,
        (
            "what is",
            "how many",
            "which year",
            "page",
            "value",
            "total",
            "count",
            "extract",
            "pm10",
            "pm2.5",
            "aqi",
            "so2",
            "no2",
            "o3",
            "co",
        ),
    )


def is_entity_extraction_request(question: str) -> bool:
    text = normalize_question(question)
    lowered = text.lower()
    if is_schema_design_request(text) or is_sql_request(text):
        return False
    if contains_any(
        lowered,
        (
            "postgres",
            "postgresql",
            "schema",
            "ddl",
            "create table",
            "table design",
            "database table",
        ),
    ):
        return False

    extraction_markers_cn = ("抽取", "提取", "抽出", "提炼")
    extraction_markers_en = ("extract", "pull out", "list out")
    entity_markers_cn = ("实体", "字段", "关键信息", "关键字段", "指标", "要素", "属性")
    entity_markers_en = ("entity", "entities", "field", "fields", "attribute", "attributes")
    format_markers = ("json", "结构化", "列表", "清单", "schema", "array", "object")
    action_markers = (
        "请",
        "帮我",
        "给我",
        "把",
        "将",
        "输出",
        "返回",
        "列出",
        "extract",
        "return",
        "list",
    )
    method_markers = (
        "如何",
        "怎么",
        "优化",
        "提升",
        "策略",
        "方案",
        "评估",
        "workflow",
        "best practice",
        "how to",
        "improve",
    )
    doc_markers = (
        "文档",
        "文件",
        "表格",
        "工作表",
        "当前文档",
        "this document",
        "this file",
        "current document",
        "selected document",
        "bound document",
        "worksheet",
        "sheet",
    )

    has_extract = contains_any(text, extraction_markers_cn) or contains_any(lowered, extraction_markers_en)
    has_entity = contains_any(text, entity_markers_cn) or contains_any(lowered, entity_markers_en)
    has_structured = contains_any(text, format_markers) or contains_any(lowered, format_markers)
    has_action = contains_any(text, action_markers) or contains_any(lowered, action_markers)
    has_doc_hint = is_document_specific_question(text) or contains_any(text, doc_markers) or contains_any(lowered, doc_markers)
    asks_method = contains_any(text, method_markers) or contains_any(lowered, method_markers)
    has_list_hint = bool(re.search(r"[、,，;；/]|(?:以及|和|与| and )", text))

    if asks_method and not has_doc_hint:
        return False
    if re.search(r"\bextract(?:ing)?\b.{0,32}\b(fields?|entities?)\b", lowered):
        return True
    if re.search(r"\b(fields?|entities?)\b.{0,24}\bjson\b", lowered) and has_doc_hint:
        return True
    if has_extract and (has_entity or has_structured) and (has_doc_hint or has_action):
        return True
    if has_extract and has_doc_hint and (has_list_hint or has_structured):
        return True
    if has_entity and has_structured and has_doc_hint:
        return True
    return False


def looks_like_fact_lookup(question: str) -> bool:
    lowered = lower_question(question)
    return contains_any(
        lowered,
        (
            "?",
            "？",
            "多少",
            "是否",
            "是不是",
            "列出",
            "提取",
            "找出",
            "统计",
            "compare",
            "list",
            "extract",
            "find",
            "tell me",
            "show me",
        ),
    )


def has_explicit_time_scope(question: str) -> bool:
    text = normalize_question(question)
    lowered = text.lower()
    if re.search(r"20\d{2}[年/-]\d{1,2}([月/-]\d{1,2})?", text):
        return True
    if re.search(r"\d{1,2}:\d{2}(:\d{2})?", text):
        return True
    return contains_any(
        lowered,
        (
            "时间",
            "日期",
            "监测时间",
            "小时",
            "当天",
            "昨天",
            "今天",
            "季度",
            "月份",
            "年份",
            "截至",
            "时点",
            "date",
            "time",
            "day",
            "month",
            "year",
            "as of",
        ),
    )


def prefers_active_document_grounding(question: str, has_default_file: bool) -> bool:
    if not has_default_file:
        return False
    return (
        is_document_specific_question(question)
        or is_broad_document_question(question)
        or is_field_lookup_question(question)
        or looks_like_fact_lookup(question)
    )


def should_prefer_frontend_grounding(user_message: str) -> bool:
    lowered = lower_question(user_message)
    return contains_any(
        lowered,
        (
            "字段",
            "当前选中文档",
            "当前选中的文档",
            "选中文档",
            "选中的文档",
            "核心内容",
            "主要讲了什么",
            "重点是什么",
            "摘要",
            "概括",
            "总结",
            "current document",
            "selected document",
            "summary",
            "key points",
            "extract fields",
            "extract entities",
            "entity extraction",
            "json output",
        ),
    )


def looks_like_generic_deictic_lookup(question: str) -> bool:
    text = normalize_question(question)
    lowered = text.lower()
    chinese_patterns = (
        r"^(?:当前|现在|这里|这份文档里|文档里)?(?:这个|这个数值|这个值|这个数据|这个指标|这项|这一项)(?:的)?(?:数值|值|数据|指标)?(?:是)?多少[?？]?$",
        r"^(?:这个|这项|这一项)(?:具体)?(?:指什么|代表什么)[?？]?$",
        r"^(?:它)(?:的)?(?:数值|值|数据)?(?:是)?多少[?？]?$",
    )
    english_patterns = (
        r"^(?:what is|how much is)\s+(?:this|that)\s+(?:value|number|metric)\??$",
        r"^(?:what does)\s+(?:this|that)\s+(?:value|metric)\s+(?:mean|refer to)\??$",
    )
    return any(re.search(pattern, text) for pattern in chinese_patterns) or any(
        re.search(pattern, lowered) for pattern in english_patterns
    )


def is_ambiguous_record_lookup(question: str, has_default_file: bool) -> bool:
    if not has_default_file:
        return False
    text = normalize_question(question)
    lowered = text.lower()
    if not prefers_active_document_grounding(text, has_default_file):
        return False
    if has_explicit_time_scope(text):
        return False
    # If the question contains a quoted or bracketed specific term, it is already
    # sufficiently precise — no clarification needed.
    if re.search(r'[""「」《》【】\'"]', text):
        return False
    row_markers = (
        "这条记录",
        "这一条",
        "当前这行",
        "当前记录",
        "这个站点",
        "该站点",
        "当前对象",
        "现在",
        "this row",
        "this record",
        "current record",
        "current row",
        "now",
    )
    metric_markers = (
        "是多少",
        "多少",
        "数值",
        "值",
        "浓度",
        "pm10",
        "pm2.5",
        "aqi",
        "so2",
        "no2",
        "o3",
        "co",
        "value",
        "count",
        "cases",
        "deaths",
        "tests",
    )
    return (
        (contains_any(text, row_markers) and contains_any(lowered, metric_markers))
        or looks_like_generic_deictic_lookup(text)
    )


@dataclass(frozen=True)
class Assistant1IntentSignals:
    question: str
    lowered: str
    has_default_file: bool
    strict_minimal: bool
    brief: bool
    detailed: bool
    capability: bool
    web_search: bool
    schema_design: bool
    sql_request: bool
    general_method: bool
    document_specific: bool
    broad_document: bool
    document_risk_review: bool
    field_lookup: bool
    entity_extraction: bool
    ambiguous_record_lookup: bool


def collect_intent_signals(question: str, *, has_default_file: bool) -> Assistant1IntentSignals:
    text = normalize_question(question)
    return Assistant1IntentSignals(
        question=text,
        lowered=text.lower(),
        has_default_file=bool(has_default_file),
        strict_minimal=is_strict_minimal_request(text),
        brief=wants_brief_answer(text),
        detailed=wants_detailed_answer(text),
        capability=is_capability_question(text),
        web_search=is_web_search_request(text),
        schema_design=is_schema_design_request(text),
        sql_request=is_sql_request(text),
        general_method=is_general_method_question(text),
        document_specific=is_document_specific_question(text),
        broad_document=is_broad_document_question(text),
        document_risk_review=is_document_risk_review_question(text),
        field_lookup=is_field_lookup_question(text),
        entity_extraction=is_entity_extraction_request(text),
        ambiguous_record_lookup=is_ambiguous_record_lookup(text, has_default_file),
    )
