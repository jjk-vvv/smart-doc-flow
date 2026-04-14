from __future__ import annotations


def build_answer_contract_block(intent: str) -> str:
    normalized = str(intent or "").strip()
    blocks = {
        "capability": (
            "[Answer rule] State capability boundary and what can be delivered now. "
            "If context is insufficient, provide the shortest executable next step."
        ),
        "web_search": (
            "[Answer rule] Lead with conclusion and sources. "
            "If evidence conflicts, clearly flag disagreement and suggest a safe decision path. "
            "优先给结论，不展开冗长过程。"
        ),
        "schema_design": (
            "[Answer rule] Prefer concrete table/field/index/DDL output. "
            "Keep implementation-oriented wording and avoid template-heavy filler. "
            "补充必要的设计说明。"
        ),
        "sql_request": (
            "[Answer rule] Return reviewable SQL draft first and explain what it solves. "
            "For write/DDL operations, include one concise safety confirmation note. "
            "涉及落库变更时给一次确认提示。"
        ),
        "document_lookup": (
            "[Answer rule] For conditional lookup questions (e.g. 'where A=B, what is C'), "
            "verify exact row-level evidence before answering. "
            "If unique match or provenance is missing, explicitly reply "
            "'not found in current evidence' and list missing constraints/provenance fields "
            "(page/row/ref_id). Do not guess from loosely related fields. "
            "结果不唯一时明确写出“不唯一”。"
        ),
        "entity_extraction": (
            "[Answer rule] When user asks to extract entities/fields (especially JSON output), "
            "return structured results in requested format. "
            "For unmatched fields, mark them as missing instead of fabricating values. "
            "禁止编造。"
        ),
        "document_summary": (
            "[Answer rule] Cover topic, object, and time scope first, then key fields. "
            "If evidence is insufficient, explicitly name the missing evidence."
        ),
        "document_risk_review": (
            "[Answer rule] Point out concrete high-priority verification risks, not generic warnings. "
            "If evidence chain is weak, explicitly mark the review as preliminary. "
            "强调具体问题，避免泛泛而谈。"
        ),
        "general_method": (
            "[Answer rule] Prefer actionable plan in goal-step-checkpoint format. "
            "Keep operational detail; avoid abstract-only descriptions."
        ),
        "missing_document": (
            "[Answer rule] Clearly state what is missing: file, snippet, or locating condition. "
            "Never imply document content was seen when it was not. "
            "缺什么就直接说什么。"
        ),
    }
    return blocks.get(normalized, "")
