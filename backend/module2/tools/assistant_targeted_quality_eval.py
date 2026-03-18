from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import re

from dotenv import load_dotenv


MODULE2_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MODULE2_ROOT.parents[1]
DEFAULT_OUTPUT = REPO_ROOT / ".runlogs" / "module2-targeted-regression" / "assistant-targeted-quality-latest.json"

if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

load_dotenv(MODULE2_ROOT / ".env", override=False)

from tools.assistant_real_media_regression import (  # noqa: E402
    AssistantChatStreamRequestCompat,
    AssistantService,
    EXCEL_PATH,
    ExtractionStorage,
    _build_document_and_payload,
    _decode_stream_frames,
    _ensure_storage_compat,
)


@dataclass(frozen=True)
class Scenario:
    name: str
    question: str
    expected: str


EXCEL_MULTITURN_SCENARIOS: List[Scenario] = [
    Scenario(
        name="precise_pm10",
        question="请直接查看 xlsx_t1 表格，站点名称为滕州新二中的 PM10 监测值是多少？",
        expected="应返回 54，并在正文里避免直接输出页码、行号、ref_id 等原始定位串。",
    ),
    Scenario(
        name="followup_pollution_type",
        question="继续，刚才那一行的污染类型是什么？",
        expected="应沿用上一轮锁定行，回答污染类型为“良”，并保持正文自然，不直接堆原始定位串。",
    ),
    Scenario(
        name="broad_risk_review",
        question="这份表格现在最值得优先核对的风险点是什么？不要泛泛而谈，请给我具体判断点。",
        expected="应给出具体核对点，例如站点行定位、字段列对齐、异常值标注、同名站点歧义、抽取字段与表格行是否一致，而不是只讲通用理论。",
    ),
    Scenario(
        name="focus_then_global_summary",
        question="重新判断一下：这份文档现在大致讲了什么？请先单独说明当前锁定对象，再说明全局概览，并区分哪些信息比较稳定、哪些还需要谨慎校对。",
        expected="应先说明当前锁定对象，再说明整体文档概览，并明确分开“比较稳定”和“仍需谨慎核对”的内容；不能改写成风险排查或入库建议。",
    ),
    Scenario(
        name="ocr_layout_explain",
        question="OCR 和版面分析到底有什么区别？不要只给定义，请按工程落地讲清楚判断边界、常见误差来源，以及它们在当前这类表格文档里分别起什么作用。",
        expected="应分层解释 OCR 与版面分析的职责边界，并结合当前表格场景讲清楚误差来源和落地判断。",
    ),
    Scenario(
        name="nl2sql_design",
        question="如果我想把当前文档抽取结果落到数据库，并且支持自然语言转 SQL 做增删改查，最稳妥的设计思路是什么？请直接讲流程、关键约束和容易出错的地方。",
        expected="应讲清楚入库建模、确认与审计、预览执行、回滚与权限边界，不能只泛谈“可以做”。",
    ),
    Scenario(
        name="web_boundary",
        question="如果我还想进一步了解这类空气质量监测数据处理的最新规范或最佳实践，你现在能怎么回答我？请把文档内证据、通用经验和是否需要联网查证分开说。",
        expected="应明确区分文档内证据、通用经验和需要联网核实的部分，并对“最新”保持谨慎。",
    ),
    Scenario(
        name="generic_processing_strategy",
        question="如果用户上传的是一份质量一般、版式也不规整的扫描文档，你通常会怎么分阶段处理，才能让后面的抽取、问答和落库都更稳？",
        expected="应给出分阶段处理思路、质量门槛和常见失真来源，不能只停留在泛泛定义。",
    ),
    Scenario(
        name="general_binding_why_harder",
        question="这类文档处理里，为什么很多时候不是 OCR 本身最难，而是后面的绑定和结构恢复更麻烦？别写成教材，直接按真实处理经验说。",
        expected="应直接说明难点往往在对象绑定、行列归属、字段映射和上下文收紧，而不是泛泛解释 OCR 定义，也不要写成教材式大纲。",
    ),
]


RAW_LOCATOR_PATTERNS = (
    r"ref_id",
    r"figure_id",
    r"第\s*\d+\s*页",
    r"表内第\s*\d+\s*行",
    r"原始第\s*\d+\s*行",
)

MACHINE_STYLE_PATTERNS = (
    r"\btool\b",
    r"function calling",
    r"\broute\b",
    r"\bjson\b",
    r"fallback",
    r"timeout",
    r"blocked",
    r"weak_lock",
    r"no_lock",
)

FORMULAIC_STYLE_PATTERNS = (
    r"如果你还想继续看这条记录里的其他指标",
    r"如果你愿意，我可以继续",
    r"我先给你一个收敛后的判断",
    r"结合你当前这份文档来看",
)

WRITTEN_STYLE_PATTERNS = (
    r"从工程视角看",
    r"真正的难点(?:通常)?不在",
    r"真正决定体验的，往往不是",
    r"如果把非结构化文档处理拆开来看",
    r"更稳妥的(?:链路|流程)通常是",
    r"一个更稳妥的流程通常是",
    r"工程上之所以要把两者分开，是因为",
)

HEAVY_MARKDOWN_PATTERNS = (
    r"###\s*\d",
    r"\*\*\d\.",
)


def _quality_checks(answer: str) -> Dict[str, Any]:
    text = str(answer or "").strip()
    lowered = text.lower()
    paragraphs = [part for part in re.split(r"\n\s*\n", text) if part.strip()]
    return {
        "answer_chars": len(text),
        "paragraph_count": len(paragraphs),
        "contains_raw_locator": any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in RAW_LOCATOR_PATTERNS),
        "contains_machine_style_terms": any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in MACHINE_STYLE_PATTERNS),
        "contains_formulaic_style": any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in FORMULAIC_STYLE_PATTERNS),
        "contains_written_style": any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in WRITTEN_STYLE_PATTERNS),
        "contains_heavy_markdown": any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in HEAVY_MARKDOWN_PATTERNS),
        "contains_ideographic_space": any(ch in text for ch in ("\u3000", "\u2002", "\u2003", "\u2009", "\u202f", "\u205f")),
        "contains_short_bridge_paragraph": any(
            len(re.sub(r"\s+", "", part)) <= 26
            and re.match(
                r"^(先看|再看|最后|比较稳的|还要再核的|通用经验|文档里能确认的部分|当前聚焦对象能确认什么|整份文档大致讲了什么|哪些信息比较稳定，哪些还需要谨慎校对|关于文档内证据|关于通用经验|关于是否需要联网查证)",
                part.strip(),
            )
            for part in paragraphs
        ),
        "contains_question_echo": False,
        "ends_with_terminal_punctuation": bool(text) and text[-1] in "。！？.!?",
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run targeted assistant quality evaluation for Module 2.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Where to save the JSON report.",
    )
    parser.add_argument(
        "--dsn",
        default="postgresql://postgres@127.0.0.1:5433/Data_Extraction",
        help="Storage DSN for the compatibility harness.",
    )
    return parser.parse_args()


async def _ask(
    service: AssistantService,
    *,
    document: Any,
    extraction_payload: Dict[str, Any],
    question: str,
    session_id: Optional[str] = None,
) -> tuple[str, Dict[str, Any]]:
    request = AssistantChatStreamRequestCompat(
        document=document,
        summary="",
        user_message=question,
        session_id=session_id,
        persist=False,
        top_k=12,
        enable_web_search=False,
        extraction_payload=extraction_payload,
    )
    frames: List[bytes] = []
    async for chunk in service.stream_chat(request):
        frames.append(chunk)
    return _decode_stream_frames(frames)


async def main() -> int:
    args = _parse_args()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    storage = ExtractionStorage(str(args.dsn))
    await storage.connect()
    _ensure_storage_compat(storage)
    service = AssistantService(storage)

    document, extraction_payload, parse_brief = _build_document_and_payload(EXCEL_PATH, track="FastTrack")
    storage._compat_extraction_payloads[document.file_hash] = dict(extraction_payload)

    session_id: Optional[str] = None
    results: List[Dict[str, Any]] = []
    for scenario in EXCEL_MULTITURN_SCENARIOS:
        answer, meta = await _ask(
            service,
            document=document,
            extraction_payload=extraction_payload,
            question=scenario.question,
            session_id=session_id,
        )
        session_id = str(meta.get("session_id") or session_id or "")
        quality_checks = _quality_checks(answer)
        quality_checks["contains_question_echo"] = str(scenario.question or "").strip()[:18] in str(answer or "")
        results.append(
            {
                "name": scenario.name,
                "question": scenario.question,
                "expected": scenario.expected,
                "answer": answer,
                "quality_checks": quality_checks,
                "meta": {
                    "prompt_version": meta.get("prompt_version"),
                    "session_id": meta.get("session_id"),
                    "tools_used": meta.get("tools_used"),
                    "provider_diagnostics": meta.get("provider_diagnostics"),
                    "route": meta.get("route"),
                    "warnings": meta.get("warnings"),
                },
            }
        )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "excel_path": str(EXCEL_PATH),
        "parse_brief": parse_brief,
        "result_count": len(results),
        "results": results,
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output_path": str(output_path), "result_count": len(results)}, ensure_ascii=False))

    await storage.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
