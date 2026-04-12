from __future__ import annotations

from typing import Any, Dict, Optional

from .answer_contracts import build_answer_contract_block
from .frontend_grounding import frontend_context_block, frontend_evidence_dossier_block
from .response_planner import Assistant1ResponsePlan


def core_instruction_block() -> str:
    lines = [
        "【角色】你是面向非结构化文档处理场景的信息提取任务助手，支持文档问答、字段抽取、表结构设计、数据库建议、NL2SQL 和必要的联网补充。",
        "【工作方式】先理解用户真正想解决的问题，再给出自然、可信、直接的中文回答。",
        "【表达风格】像熟悉业务的真人同事一样说话，优先把答案和判断讲明白，不要套固定开头、固定结尾，也不要写成系统日志。",
        "【收尾方式】除非确实需要确认下一步或补齐关键信息，否则不要在结尾机械地追问“要不要我继续”“要不要我帮你生成”。",
        "【证据边界】文档问题优先依据当前文档和已拿到的证据；数据库问题优先依据真实库结构；最新外部信息再补联网资料。",
        "【歧义处理】如果同一对象可能对应多条记录、多个时间点、多个版本或多个统计口径，就指出真正缺失的限定条件，不要替用户拍板。",
        "【输出边界】主回答里不要暴露工具名、检索链路、内部 ID、ref_id、unit_id、页码锚点或系统过程。",
        "【不足时】如果依据还不够，就明确说明还缺什么，不要猜，也不要为了完整而编造。",
    ]
    return "\n".join(lines)


def session_context_block(*, default_file_hash: str) -> str:
    if default_file_hash:
        return "【当前上下文】当前会话已经绑定默认文档。除非用户另外说明，可以把它视为默认目标。"
    return (
        "【当前上下文】当前会话还没有绑定默认文档。"
        "如果用户追问具体文件内容但没有给出文件线索，不要猜文档内容，先请他指定文件、粘贴文本或提供定位信息。"
    )


def turn_hint_block(
    *,
    user_message: str,
    default_file_hash: str,
    response_plan: Assistant1ResponsePlan,
) -> str:
    del default_file_hash
    hints: list[str] = []

    if response_plan.must_clarify and response_plan.clarification_reason:
        hints.append(
            "【本轮重点】这次提问还存在记录锁定歧义。"
            f"{response_plan.clarification_reason}"
            "先自然指出歧义点，再请用户补一个最关键的限定条件，不要直接挑一个值作答。"
        )

    if "json" in str(user_message or "").lower():
        hints.append("【格式】如果用户明确指定了 JSON，就严格按 JSON 输出。")

    return "\n".join(hints).strip()


def build_assistant_instructions(
    *,
    user_message: str,
    default_file_hash: str,
    response_plan: Assistant1ResponsePlan,
    extra_context: Optional[Dict[str, Any]] = None,
) -> str:
    blocks = [
        core_instruction_block(),
        session_context_block(default_file_hash=default_file_hash),
    ]

    answer_contract = build_answer_contract_block(response_plan.intent)
    if answer_contract:
        blocks.append(answer_contract)

    frontend_block = frontend_context_block(extra_context)
    if frontend_block:
        blocks.append(frontend_block)

    dossier_block = frontend_evidence_dossier_block(
        user_message=user_message,
        extra_context=extra_context,
    )
    if dossier_block:
        blocks.append(dossier_block)

    hint_block = turn_hint_block(
        user_message=user_message,
        default_file_hash=default_file_hash,
        response_plan=response_plan,
    )
    if hint_block:
        blocks.append(hint_block)

    return "\n\n".join(block.strip() for block in blocks if block and block.strip()).strip()
