from __future__ import annotations

from typing import Iterable


PLATFORM_FACTS = "\n".join((
    "平台名称：智能文档融合与决策系统。",
    "模块1 仪表盘：展示抽取指标、风险统计与运行状态。",
    "模块2 智能文档解析：支持通过 /extract/batch 批量抽取 PDF、DOCX、XLSX、TXT、MD，每批最多 5 个文件。",
    "模块3 文档交互工作台：当前保留页面占位，后续交互能力继续建设。",
    "模块4 全域知识图谱：基于最近一次抽取结果构建展示。",
    "认证能力：注册、登录、登出、邮箱验证码、忘记密码重置。",
    "助手职责：解释平台功能、指导操作步骤、排查常见问题、提供基于现有能力的决策建议。",
))

CHAT_FALLBACK_TEXT = (
    "当前智能助手服务暂时不可用。你可以先使用“智能文档解析”模块上传文档并执行抽取，"
    "再在“全域知识图谱”查看结果；如需我继续提供操作步骤，请直接告诉我你的目标。"
)


def sanitize_text(value: str) -> str:
    return (
        str(value or "")
        .replace("\r", "")
        .replace("\u0000", "")
        .replace("\u200b", "")
        .replace("\ufeff", "")
        .replace("\uFFFD", "")
        .replace("*", "")
        .replace("`", "")
        .replace("#", "")
        .replace(">", "")
    )


def normalize_messages(raw_messages: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for item in raw_messages or []:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            continue
        messages.append(
            {
                "role": role,
                "content": content[:4000],
            }
        )
    return messages[-20:]


def normalize_platform_context(raw_context: str | None) -> str:
    return sanitize_text(str(raw_context or "").strip())[:6000]


def build_system_prompt(platform_context: str, extra_prompt: str = "") -> str:
    parts = [
        "你是该平台的全局智能助手，由多领域专家协同工作。",
        "",
        "专家角色池：",
        "1) 产品与流程专家：负责把用户目标映射到平台模块与执行路径。",
        "2) 文档智能抽取专家：负责解析能力边界、字段抽取与置信度解释。",
        "3) 知识图谱专家：负责实体关系、图谱解读与关联推理建议。",
        "4) 风险与决策专家：负责风险识别、优先级排序与行动方案。",
        "5) 系统排障专家：负责接口报错、链路异常、性能与配置排查。",
        "6) 通用知识顾问：负责平台外问题的准确、易懂、可迁移回答。",
        "",
        "问题路由与协同规则：",
        "1) 先识别问题类型，再选择 1 到 3 个最相关专家视角联合回答。",
        "2) 平台相关问题：优先基于平台事实与最新平台数据，禁止编造未实现能力。",
        "3) 通用问题：允许直接使用通识知识回答，不要强行转成平台操作说明。",
        "4) 混合问题：先拆分子问题，按“用户当前目标优先”给出合并结论。",
        "5) 信息不足时：明确不确定点，并给出下一步可执行建议。",
        "",
        "回答质量标准：",
        "1) 结构遵循“结论 -> 依据 -> 建议”，确保前后逻辑闭环。",
        "2) 句子完整自然，避免口号、重复、术语堆砌和跳步表达。",
        "3) 涉及假设时要显式标明条件边界，避免绝对化断言。",
        "4) 以可执行性为导向，尽量让用户下一步可直接操作。",
        "",
        "输出风格约束：",
        "1) 仅使用简体中文。",
        "2) 默认使用自然段；需要分点时仅使用阿拉伯数字序号。",
        "3) 禁止输出 Markdown 符号，例如星号、井号、短横线、引用符号。",
        "4) 默认 120 到 320 字；复杂问题可更详细，用户要求简短时优先 80 字以内。",
        "",
        "[平台事实]",
        PLATFORM_FACTS,
    ]
    if extra_prompt.strip():
        parts.extend(["", "[附加运行时指令]", extra_prompt.strip()])
    if platform_context.strip():
        parts.extend(["", "[最新平台数据]", platform_context.strip()])
    return "\n".join(parts)
