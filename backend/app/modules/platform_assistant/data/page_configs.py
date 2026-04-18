from __future__ import annotations

from copy import deepcopy
from typing import Any


def _action(label: str, target_tab: str, variant: str = "primary") -> dict[str, str]:
    return {
        "label": label,
        "targetTab": target_tab,
        "variant": variant,
    }


_PAGE_CONFIGS: dict[str, dict[str, Any]] = {
    "dashboard": {
        "tab": "dashboard",
        "label": "控制台",
        "cue": "你当前在控制台页，适合先了解模块入口和推荐使用顺序。",
        "starter": {
            "title": "建议先从 AI 文档处理 开始",
            "summary": "先进入模块一处理文档交互，可以最快形成完整闭环，再进入提取和融合。",
            "steps": [
                "进入「AI文档处理」上传一份文档。",
                "先做一次问答和预览确认。",
                "再根据需要切换到「AI信息提取」做结构化处理。",
            ],
            "primaryAction": _action("打开 AI文档处理", "doc-processing"),
            "secondaryAction": _action("查看平台指南", "guide", "secondary"),
        },
        "prompts": [
            {
                "id": "dashboard-start",
                "question": "我该从哪里开始？",
                "keywords": ["从哪里开始", "怎么开始", "第一步", "新手"],
                "answer": {
                    "title": "从 AI 文档处理开始最稳妥",
                    "summary": "模块一最适合新手先上手，先交互理解文档，再决定是否进入提取。",
                    "steps": [
                        "打开 AI文档处理。",
                        "上传文档并提一个总览问题。",
                        "按回答再进入提取或融合。",
                    ],
                    "primaryAction": _action("进入 AI文档处理", "doc-processing"),
                    "secondaryAction": _action("查看指南", "guide", "secondary"),
                },
            },
            {
                "id": "dashboard-diff",
                "question": "文档处理和信息提取有什么区别？",
                "keywords": ["区别", "文档处理", "信息提取", "模块区别"],
                "answer": {
                    "title": "文档处理偏交互，信息提取偏结构化",
                    "summary": "文档处理用于边看边问；信息提取用于字段抽取和结果整理。",
                    "steps": [
                        "先在 AI文档处理里确认内容与目标。",
                        "再在 AI信息提取里拿结构化结果。",
                        "最后按需做融合与图谱。",
                    ],
                    "primaryAction": _action("打开 AI文档处理", "doc-processing"),
                    "secondaryAction": _action("打开 AI信息提取", "deepread_extraction", "secondary"),
                },
            },
        ],
        "primaryPromptCount": 2,
    },
    "deepread": {
        "tab": "deepread",
        "label": "智能文档解析",
        "cue": "你当前在文档解析域，可先选文档处理或信息提取子链路。",
        "starter": {
            "title": "建议先用 AI 文档处理",
            "summary": "先交互理解文档，再做结构化提取，流程更稳定。",
            "steps": [
                "进入 AI文档处理上传文档。",
                "完成一次问答确认核心内容。",
                "需要字段化时再进入 AI信息提取。",
            ],
            "primaryAction": _action("打开 AI文档处理", "doc-processing"),
            "secondaryAction": _action("打开 AI信息提取", "deepread_extraction", "secondary"),
        },
        "prompts": [],
        "primaryPromptCount": 0,
    },
    "doc-processing": {
        "tab": "doc-processing",
        "label": "AI文档处理",
        "cue": "你当前在模块一，适合上传文档并进行问答、预览、报告处理。",
        "starter": {
            "title": "模块一标准流程",
            "summary": "上传文档 -> 问答理解 -> 预览核对 -> 报告处理。",
            "steps": [
                "上传一份文档并确认预览。",
                "提出总览问题与关键问题。",
                "根据结果进入报告处理或提取模块。",
            ],
            "primaryAction": _action("继续当前页面操作", "doc-processing"),
            "secondaryAction": _action("打开 AI信息提取", "deepread_extraction", "secondary"),
        },
        "prompts": [
            {
                "id": "doc-processing-upload",
                "question": "上传后下一步怎么做？",
                "keywords": ["上传后", "下一步", "怎么操作"],
                "answer": {
                    "title": "先问总览，再问细节",
                    "summary": "先确认文档主旨和结构，再深挖你关心的点。",
                    "steps": [
                        "先问“这份文档主要讲什么”。",
                        "再问“有哪些关键风险/重点”。",
                        "最后按结果选择提取或继续追问。",
                    ],
                    "primaryAction": _action("继续文档问答", "doc-processing"),
                },
            },
            {
                "id": "doc-processing-preview",
                "question": "怎么查看预览和报告？",
                "keywords": ["预览", "报告", "怎么看"],
                "answer": {
                    "title": "从当前文件卡片进入预览与报告",
                    "summary": "先看预览确认原文，再看报告总结提炼结果。",
                    "steps": [
                        "点击当前文件的预览入口。",
                        "核对原文定位与内容一致性。",
                        "再打开报告页查看结构化总结。",
                    ],
                    "primaryAction": _action("打开文档预览", "doc-processing"),
                },
            },
        ],
        "primaryPromptCount": 2,
    },
    "deepread_extraction": {
        "tab": "deepread_extraction",
        "label": "AI信息提取",
        "cue": "你当前在信息提取模块，适合做字段化抽取和结果校对。",
        "starter": {
            "title": "先抽取，再校对，再下游使用",
            "summary": "提取完成后，先校对关键字段，再进入后续流程。",
            "steps": [
                "上传并执行提取。",
                "核对关键字段与来源定位。",
                "按需进入融合或图谱。",
            ],
            "primaryAction": _action("继续信息提取", "deepread_extraction"),
            "secondaryAction": _action("回到 AI文档处理", "doc-processing", "secondary"),
        },
        "prompts": [],
        "primaryPromptCount": 0,
    },
    "fusion": {
        "tab": "fusion",
        "label": "融合",
        "cue": "你当前在融合模块，适合处理多源结果填充和整合。",
        "starter": {
            "title": "确认输入完整后再融合",
            "summary": "先保证上游文档或提取结果齐全，再做融合最稳妥。",
            "steps": [
                "确认输入文档与模板完整。",
                "执行融合并检查输出。",
                "异常时回到上游补充信息。",
            ],
            "primaryAction": _action("继续融合", "fusion"),
            "secondaryAction": _action("回到 AI文档处理", "doc-processing", "secondary"),
        },
        "prompts": [],
        "primaryPromptCount": 0,
    },
    "nexus": {
        "tab": "nexus",
        "label": "知识图谱",
        "cue": "你当前在图谱模块，适合查看关系网络和全局结构。",
        "starter": {
            "title": "先有上游结果，再看图谱",
            "summary": "图谱是后链路能力，需先完成文档处理/提取。",
            "steps": [
                "确认上游数据已生成。",
                "进入图谱查看关系结构。",
                "需要核对时回到原文或提取结果。",
            ],
            "primaryAction": _action("继续图谱查看", "nexus"),
            "secondaryAction": _action("回到 AI文档处理", "doc-processing", "secondary"),
        },
        "prompts": [],
        "primaryPromptCount": 0,
    },
    "guide": {
        "tab": "guide",
        "label": "指南",
        "cue": "你当前在指南页，适合先理清模块边界和推荐路径。",
        "starter": {
            "title": "按“处理 -> 提取 -> 融合/图谱”路径使用",
            "summary": "先模块一，再模块二，再下游模块，是最稳定的使用顺序。",
            "steps": [
                "从 AI文档处理开始。",
                "再进入 AI信息提取。",
                "最后按需使用融合和图谱。",
            ],
            "primaryAction": _action("打开 AI文档处理", "doc-processing"),
            "secondaryAction": _action("打开 AI信息提取", "deepread_extraction", "secondary"),
        },
        "prompts": [],
        "primaryPromptCount": 0,
    },
    "mine": {
        "tab": "mine",
        "label": "我的",
        "cue": "当前位于个人中心，适合处理账号、安全、会话和返回工作区相关的问题。",
        "starter": {
            "title": "账号页常用操作",
            "summary": "先确认当前账号状态，再处理安全设置或回到具体业务模块继续工作。",
            "steps": [
                "查看当前登录账号与安全信息。",
                "如需继续业务操作，可直接跳回首页或提取页面。",
                "如果登录状态异常，优先处理账号与会话问题。",
            ],
            "primaryAction": _action("返回首页", "dashboard"),
            "secondaryAction": _action("打开 AI信息提取", "deepread_extraction", "secondary"),
        },
        "prompts": [
            {
                "id": "mine-account",
                "question": "我想回到工作页面继续处理文档",
                "keywords": ["回到工作页面", "继续处理文档", "返回工作区"],
                "answer": {
                    "title": "从个人中心返回工作区",
                    "summary": "你可以先回到首页，再进入提取、处理或融合模块继续当前任务。",
                    "steps": [
                        "先回到首页确认要继续的模块。",
                        "如果要继续提取，进入 AI信息提取。",
                        "如果要继续问答或处理，进入 AI文档处理。",
                    ],
                    "primaryAction": _action("返回首页", "dashboard"),
                    "secondaryAction": _action("打开 AI信息提取", "deepread_extraction", "secondary"),
                },
            },
        ],
        "primaryPromptCount": 1,
    },
}


def normalize_platform_tab(tab: str | None) -> str:
    candidate = str(tab or "").strip()
    if candidate in _PAGE_CONFIGS:
        return candidate
    return "dashboard"


def get_page_config(tab: str | None) -> dict[str, Any]:
    normalized = normalize_platform_tab(tab)
    return deepcopy(_PAGE_CONFIGS[normalized])


def get_all_page_configs() -> list[dict[str, Any]]:
    return [deepcopy(config) for config in _PAGE_CONFIGS.values()]


__all__ = ["get_all_page_configs", "get_page_config", "normalize_platform_tab"]
