from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


logger = logging.getLogger(__name__)

COLOR_NAME_MAP = {
    "red": "#FF0000",
    "blue": "#0000FF",
    "green": "#00FF00",
    "yellow": "#FFFF00",
    "purple": "#800080",
    "orange": "#FFA500",
    "black": "#000000",
    "white": "#FFFFFF",
    "cyan": "#00FFFF",
    "magenta": "#FF00FF",
    "gray": "#808080",
}


@dataclass(frozen=True)
class ShadowNode:
    paragraph_index: int
    text: str
    style: str = "Normal"
    run_count: int = 0


def normalize_color(color: Any) -> Optional[str]:
    if not isinstance(color, str):
        return None

    normalized = color.strip()
    if not normalized:
        return None

    mapped = COLOR_NAME_MAP.get(normalized.lower(), normalized)
    if not mapped.startswith("#"):
        mapped = f"#{mapped}"

    if re.fullmatch(r"#[0-9A-Fa-f]{6}", mapped):
        return mapped.upper()
    return None


def build_shadow_dom_snapshot(doc_info: Dict[str, Any]) -> List[ShadowNode]:
    paragraphs = doc_info.get("paragraphs", [])
    nodes: List[ShadowNode] = []

    for paragraph in paragraphs:
        if not isinstance(paragraph, dict):
            continue
        nodes.append(
            ShadowNode(
                paragraph_index=int(paragraph.get("index", len(nodes))),
                text=str(paragraph.get("text", "")),
                style=str(paragraph.get("style", "Normal") or "Normal"),
                run_count=len(paragraph.get("runs", []) or []),
            )
        )

    return nodes


def parse_ai_modifications(ai_response: str) -> List[Dict[str, Any]]:
    modifications: List[Dict[str, Any]] = []
    try:
        patterns = [
            r"```json\s*(.*?)\s*```",
            r"```\s*(.*?)\s*```",
            r"(\[.*?\])",
            r"({.*?})",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, ai_response, re.DOTALL)
            for match in matches:
                try:
                    parsed = json.loads(match.strip())
                except json.JSONDecodeError:
                    continue

                raw_modifications: List[Dict[str, Any]] = []
                if isinstance(parsed, list):
                    if len(parsed) == 1 and isinstance(parsed[0], dict) and isinstance(parsed[0].get("modifications"), list):
                        raw_modifications = parsed[0]["modifications"]
                    else:
                        raw_modifications = [item for item in parsed if isinstance(item, dict)]
                elif isinstance(parsed, dict):
                    if isinstance(parsed.get("modifications"), list):
                        raw_modifications = [item for item in parsed["modifications"] if isinstance(item, dict)]
                    else:
                        raw_modifications = [parsed]

                for raw in raw_modifications:
                    modification: Dict[str, Any] = {"type": "text_run_format"}

                    paragraph_index = raw.get("paragraph_index", raw.get("paragraphIndex"))
                    if paragraph_index is None:
                        continue

                    try:
                        modification["paragraph_index"] = int(paragraph_index)
                    except (TypeError, ValueError):
                        continue

                    run_indices = raw.get("run_indices", raw.get("runIndices"))
                    if isinstance(run_indices, list):
                        safe_indices: List[int] = []
                        for run_index in run_indices:
                            try:
                                safe_indices.append(int(run_index))
                            except (TypeError, ValueError):
                                continue
                        if safe_indices:
                            modification["run_indices"] = safe_indices

                    bold = raw.get("bold")
                    color = raw.get("color")
                    for key in ("changes", "format_changes", "properties"):
                        payload = raw.get(key)
                        if not isinstance(payload, dict):
                            continue
                        if bold is None and "bold" in payload:
                            bold = payload["bold"]
                        if color is None and "color" in payload:
                            color = payload["color"]

                    if bold is not None:
                        modification["bold"] = bool(bold)

                    normalized_color = normalize_color(color)
                    if normalized_color:
                        modification["color"] = normalized_color

                    modifications.append(modification)

                if modifications:
                    logger.info("标准化后的修改方案: %s", modifications)
                    return modifications

        if not modifications:
            response_lower = ai_response.lower()
            if "加粗" in ai_response or "bold" in response_lower:
                modifications.append({"type": "text_run_format", "paragraph_index": 0, "bold": True})
            if "红色" in ai_response or "red" in response_lower:
                modifications.append({"type": "text_run_format", "paragraph_index": 0, "color": "#FF0000"})
    except Exception as exc:  # pragma: no cover - defensive parsing
        logger.error("解析操作失败: %s", exc)

    logger.info("最终修改方案: %s", modifications)
    return modifications


def extract_text_explanation(ai_response: str) -> str:
    text = re.sub(r"```json\s*.*?\s*```", "", ai_response, flags=re.DOTALL)
    text = re.sub(r"```\s*.*?\s*```", "", text, flags=re.DOTALL)
    return text.strip()
