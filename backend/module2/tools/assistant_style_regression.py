from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv


MODULE2_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MODULE2_ROOT.parents[1]
DEFAULT_OUTPUT = REPO_ROOT / ".runlogs" / "module2-targeted-regression" / "assistant-style-regression-latest.json"

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
    expected_feel: str


STYLE_SCENARIOS: List[Scenario] = [
    Scenario(
        name="warmup_precise_pm10",
        question="先帮我确认一下，滕州新二中这条记录的 PM10 现在是多少？",
        expected_feel="一句话先给值，别加固定收尾，不要像系统提示语。",
    ),
    Scenario(
        name="plain_risk_one_point",
        question="你别讲太官方，就直接告诉我这份表现在最值得先盯的一个点是什么。",
        expected_feel="像同事提醒风险，先给一个最关键判断点，不要自动展开成长篇大纲。",
    ),
    Scenario(
        name="trustworthiness_walkthrough",
        question="如果我是第一次看这种监测表，你会先带我怎么判断它靠不靠谱？",
        expected_feel="有带着人看的感觉，顺着真实判断顺序讲，不要像教材章节。",
    ),
    Scenario(
        name="non_tech_recheck_reason",
        question="假设我不是技术人员，你会怎么解释为什么这份表后面还得复核？",
        expected_feel="解释清楚复核的必要性，口语化一点，不要写成培训材料。",
    ),
    Scenario(
        name="extract_or_organize_first",
        question="现在不谈实现，你觉得这份材料更适合先抽取还是先整理？为什么？",
        expected_feel="先给倾向判断，再说原因，别一上来就列流水线总表。",
    ),
    Scenario(
        name="db_first_confirmation",
        question="如果我后面要接数据库，你第一步会先让我确认什么？别一下子讲太多概念。",
        expected_feel="先给最前置的确认点，别自动膨胀成完整数据库方案书。",
    ),
    Scenario(
        name="ocr_one_shot_limit",
        question="为什么这类东西不能只靠 OCR 一把梭？你按真实项目里会出的问题说。",
        expected_feel="聚焦真实出错点，不要用“定义对定义”的方式解释。",
    ),
    Scenario(
        name="messy_table_screenshot_start",
        question="如果用户只给你一张质量一般、还有点歪的表格截图，你通常第一步怎么下手？",
        expected_feel="先说第一步和判断门槛，像实际做事的口吻，不要五段制模板化开讲。",
    ),
    Scenario(
        name="pipeline_drift_casual",
        question="我现在脑子有点乱，你帮我理一下，这份材料从抽取到入库，最容易先在哪一步跑偏？",
        expected_feel="先帮用户理顺一个最容易跑偏的环节，再补原因，不要全流程平均用力。",
    ),
    Scenario(
        name="latest_boundary_casual",
        question="如果我还想知道这类数据处理最近有没有什么值得注意的规范变化，你现在最多能回答到哪一步？",
        expected_feel="自然说明边界，区分现有材料、通用经验和需要联网核实的部分，不要假装已经联网。",
    ),
]


DISCOURSE_MARKERS = (
    "先把",
    "先看",
    "先说",
    "先给",
    "再看",
    "再说",
    "最后",
    "换句话说",
    "本质上",
    "从工程视角看",
    "如果你问的是",
    "简单说",
    "更稳一点",
    "比较稳的做法",
    "真正麻烦的是",
)

FIXED_PHRASES = (
    "要继续看这条记录，直接点指标名就行",
    "沿着刚才那条记录继续看",
    "先看当前文档里已经能确认的部分",
    "先说我现在能比较稳地确认的部分",
)


def _normalize_stem(text: str, limit: int = 16) -> str:
    compact = re.sub(r"[^\u4e00-\u9fffa-zA-Z0-9]", "", str(text or ""))
    return compact[:limit]


def _split_sentences(text: str) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    parts = re.split(r"[。！？!?]\s*|\n+", raw)
    return [part.strip(" \t\r\n-*:：") for part in parts if part and part.strip()]


def _opening_sentence(text: str) -> str:
    sentences = _split_sentences(text)
    return sentences[0] if sentences else ""


def _closing_sentence(text: str) -> str:
    sentences = _split_sentences(text)
    return sentences[-1] if sentences else ""


def _style_checks(answer: str) -> Dict[str, Any]:
    text = str(answer or "").strip()
    paragraphs = [part for part in re.split(r"\n\s*\n", text) if part.strip()]
    sentences = _split_sentences(text)
    opening = _opening_sentence(text)
    closing = _closing_sentence(text)
    discourse_hits = [marker for marker in DISCOURSE_MARKERS if marker in text]
    fixed_phrase_hits = [phrase for phrase in FIXED_PHRASES if phrase in text]
    numbered_items = len(re.findall(r"(?m)^\d+\.\s+", text))
    bullet_items = len(re.findall(r"(?m)^[-*]\s+", text))
    heading_count = len(re.findall(r"(?m)^#{1,6}\s+", text))
    return {
        "answer_chars": len(text),
        "paragraph_count": len(paragraphs),
        "sentence_count": len(sentences),
        "numbered_items": numbered_items,
        "bullet_items": bullet_items,
        "heading_count": heading_count,
        "opening_sentence": opening[:120],
        "closing_sentence": closing[:120],
        "opening_stem": _normalize_stem(opening),
        "closing_stem": _normalize_stem(closing),
        "discourse_markers": discourse_hits,
        "fixed_phrase_hits": fixed_phrase_hits,
        "sounds_heavy_structured": numbered_items >= 3 or bullet_items >= 4 or heading_count >= 2,
    }


def _repeated_phrase_summary(results: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    bucket: Dict[str, List[str]] = defaultdict(list)
    for item in results:
        checks = item.get("style_checks") if isinstance(item.get("style_checks"), dict) else {}
        stem = str(checks.get(key) or "").strip()
        if not stem:
            continue
        bucket[stem].append(str(item.get("name") or ""))
    out: List[Dict[str, Any]] = []
    for stem, scenario_names in bucket.items():
        if len(scenario_names) < 2:
            continue
        out.append(
            {
                "stem": stem,
                "count": len(scenario_names),
                "scenarios": scenario_names,
            }
        )
    out.sort(key=lambda item: (-int(item.get("count") or 0), str(item.get("stem") or "")))
    return out


def _repeated_sentence_summary(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    sentence_hits: Dict[str, List[str]] = defaultdict(list)
    for item in results:
        answer = str(item.get("answer") or "")
        scenario_name = str(item.get("name") or "")
        for sentence in _split_sentences(answer):
            if len(_normalize_stem(sentence, limit=24)) < 10:
                continue
            sentence_hits[sentence].append(scenario_name)
    out: List[Dict[str, Any]] = []
    for sentence, scenario_names in sentence_hits.items():
        unique_names = list(dict.fromkeys(scenario_names))
        if len(unique_names) < 2:
            continue
        out.append(
            {
                "sentence": sentence,
                "count": len(unique_names),
                "scenarios": unique_names,
            }
        )
    out.sort(key=lambda item: (-int(item.get("count") or 0), str(item.get("sentence") or "")))
    return out


def _marker_summary(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counter: Counter[str] = Counter()
    scenario_map: Dict[str, List[str]] = defaultdict(list)
    for item in results:
        checks = item.get("style_checks") if isinstance(item.get("style_checks"), dict) else {}
        for marker in checks.get("discourse_markers") or []:
            marker_text = str(marker or "").strip()
            if not marker_text:
                continue
            counter[marker_text] += 1
            scenario_map[marker_text].append(str(item.get("name") or ""))
    out: List[Dict[str, Any]] = []
    for marker, count in counter.most_common():
        out.append(
            {
                "marker": marker,
                "count": count,
                "scenarios": scenario_map.get(marker, []),
            }
        )
    return out


def _fixed_phrase_summary(results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bucket: Dict[str, List[str]] = defaultdict(list)
    for item in results:
        checks = item.get("style_checks") if isinstance(item.get("style_checks"), dict) else {}
        for phrase in checks.get("fixed_phrase_hits") or []:
            phrase_text = str(phrase or "").strip()
            if not phrase_text:
                continue
            bucket[phrase_text].append(str(item.get("name") or ""))
    out: List[Dict[str, Any]] = []
    for phrase, scenario_names in bucket.items():
        out.append(
            {
                "phrase": phrase,
                "count": len(scenario_names),
                "scenarios": scenario_names,
            }
        )
    out.sort(key=lambda item: (-int(item.get("count") or 0), str(item.get("phrase") or "")))
    return out


def _annotate_adjacent_reuse(results: List[Dict[str, Any]]) -> None:
    previous_opening: str = ""
    previous_closing: str = ""
    for item in results:
        checks = item.get("style_checks") if isinstance(item.get("style_checks"), dict) else {}
        opening_stem = str(checks.get("opening_stem") or "").strip()
        closing_stem = str(checks.get("closing_stem") or "").strip()
        checks["same_opening_as_previous"] = bool(opening_stem and previous_opening and opening_stem == previous_opening)
        checks["same_closing_as_previous"] = bool(closing_stem and previous_closing and closing_stem == previous_closing)
        previous_opening = opening_stem or previous_opening
        previous_closing = closing_stem or previous_closing


def _build_global_summary(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    repeated_openings = _repeated_phrase_summary(results, "opening_stem")
    repeated_closings = _repeated_phrase_summary(results, "closing_stem")
    repeated_sentences = _repeated_sentence_summary(results)
    marker_summary = _marker_summary(results)
    fixed_phrase_summary = _fixed_phrase_summary(results)
    adjacent_opening_reuse = sum(
        1
        for item in results
        if bool((item.get("style_checks") or {}).get("same_opening_as_previous"))
    )
    adjacent_closing_reuse = sum(
        1
        for item in results
        if bool((item.get("style_checks") or {}).get("same_closing_as_previous"))
    )
    heavy_structured_count = sum(
        1
        for item in results
        if bool((item.get("style_checks") or {}).get("sounds_heavy_structured"))
    )
    return {
        "repeated_opening_stems": repeated_openings,
        "repeated_closing_stems": repeated_closings,
        "repeated_sentences": repeated_sentences,
        "marker_summary": marker_summary,
        "fixed_phrase_summary": fixed_phrase_summary,
        "adjacent_opening_reuse_count": adjacent_opening_reuse,
        "adjacent_closing_reuse_count": adjacent_closing_reuse,
        "heavy_structured_answer_count": heavy_structured_count,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run anti-template style regression for the Module 2 assistant.")
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
) -> Tuple[str, Dict[str, Any]]:
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
    for scenario in STYLE_SCENARIOS:
        answer, meta = await _ask(
            service,
            document=document,
            extraction_payload=extraction_payload,
            question=scenario.question,
            session_id=session_id,
        )
        session_id = str(meta.get("session_id") or session_id or "")
        results.append(
            {
                "name": scenario.name,
                "question": scenario.question,
                "expected_feel": scenario.expected_feel,
                "answer": answer,
                "style_checks": _style_checks(answer),
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

    _annotate_adjacent_reuse(results)
    global_summary = _build_global_summary(results)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "excel_path": str(EXCEL_PATH),
        "parse_brief": parse_brief,
        "result_count": len(results),
        "results": results,
        "global_style_summary": global_summary,
    }
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "output_path": str(output_path),
                "result_count": len(results),
                "repeated_opening_stems": len(global_summary.get("repeated_opening_stems") or []),
                "repeated_closing_stems": len(global_summary.get("repeated_closing_stems") or []),
                "repeated_sentences": len(global_summary.get("repeated_sentences") or []),
            },
            ensure_ascii=False,
        )
    )

    await storage.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
