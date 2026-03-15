from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv


MODULE2_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MODULE2_ROOT.parents[1]
REPORT_PATH = MODULE2_ROOT / "tools" / "assistant_real_media_eval_latest.json"
ARTIFACT_DIR = MODULE2_ROOT / "artifacts" / "assistant_real_media"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

load_dotenv(MODULE2_ROOT / ".env", override=False)

from app.core.parser import parse_document_in_subprocess
from app.db.storage import ExtractionStorage
from app.schemas import DocumentExtractionResponse, ExtractionResult


def _load_module_from_pyc(module_name: str, pyc_path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, pyc_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load sourceless module: {module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _resolve_assistant_service_class() -> type:
    assistant_dir = MODULE2_ROOT / "app" / "assistant"
    service_py = assistant_dir / "service.py"
    if service_py.exists():
        from app.assistant.service import AssistantService as SourceAssistantService

        return SourceAssistantService

    package_name = "app.assistant"
    package = types.ModuleType(package_name)
    package.__path__ = [str(assistant_dir)]
    sys.modules[package_name] = package

    pyc_dir = assistant_dir / "__pycache__"
    module_names = ["provider", "prompting", "streaming", "tools", "service"]
    for module_name in module_names:
        matches = sorted(pyc_dir.glob(f"{module_name}.cpython-*.pyc"))
        if not matches:
            raise FileNotFoundError(f"Missing cached assistant module: {module_name}")
        module = _load_module_from_pyc(f"{package_name}.{module_name}", matches[0])
        setattr(package, module_name, module)

    service_module = sys.modules[f"{package_name}.service"]
    assistant_service = getattr(service_module, "AssistantService")
    setattr(package, "AssistantService", assistant_service)
    return assistant_service


AssistantService = _resolve_assistant_service_class()


@dataclass
class AssistantChatStreamRequestCompat:
    document: DocumentExtractionResponse
    summary: str = ""
    user_message: str = ""
    session_id: Optional[str] = None
    persist: bool = False
    top_k: int = 12
    enable_web_search: Optional[bool] = None
    extraction_payload: Dict[str, Any] = field(default_factory=dict)


EXCEL_PATH = next((REPO_ROOT / "datasets" / "Excel").glob("*空气质量*.xlsx"))
PDF_PATH = next((MODULE2_ROOT / "artifacts" / "pdf_parse" / "mineru").glob("*/input.pdf"))

EXCEL_QUESTIONS = [
    {
        "name": "excel_pm10",
        "question": "请直接查看 xlsx_t1 表格，站点名称为滕州新二中的 PM10监测值是多少？请写明表格、页码、表内行号、原始行号和 ref_id。",
        "expected": "应回答 PM10监测值为 54，并引用 xlsx_t1、第1页、表内第3行、原始第4行、ref_id 类似 xlsx_t1_r4_c10。",
    },
    {
        "name": "excel_pollution_followup",
        "question": "继续，那一行的污染类型是什么？也请保持同样的引用格式。",
        "expected": "应回答污染类型为 良，并沿用上一轮锁定的同一行上下文，引用 xlsx_t1、第1页、表内第3行、原始第4行、ref_id 类似 xlsx_t1_r4_c15。",
    },
]

PDF_QUESTION = {
    "name": "pdf_figure_overview",
    "question": "请先概述文档中的图表，并列出 figure_id、页码和关键要点。",
    "expected": "应至少列出已识别图表的 figure_id 和页码；如果视觉解析成功，还应给出关键要点，否则应明确说明关键要点不足。",
}

IMAGE_QUESTION = {
    "name": "image_figure_overview",
    "question": "请概述这张图片中的图表，并列出 figure_id、页码、关键要点，以及是否识别出了 dataframe 或可引用的数值。",
    "expected": "应至少识别出图片中的图表对象，并说明是否提取到了关键要点、dataframe 或可引用数值；如果识别不足，也应明确说明不足点。",
}


def _decode_stream_frames(frames: List[bytes]) -> Tuple[str, Dict[str, Any]]:
    answer_parts: List[str] = []
    meta: Dict[str, Any] = {}
    for frame in frames:
        text = frame.decode("utf-8", errors="ignore").strip()
        if not text:
            continue
        if text.startswith("0:"):
            payload = json.loads(text[2:])
            if isinstance(payload, str) and payload != "[DONE]":
                answer_parts.append(payload)
        elif text.startswith("8:"):
            meta = json.loads(text[2:])
    return "".join(answer_parts).strip(), meta


def _normalize_parse_output(
    parsed: Any,
) -> Tuple[str, Dict[str, List[float]], List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    if isinstance(parsed, tuple):
        if len(parsed) == 5:
            markdown, bbox_map, tables, figures, parse_stats = parsed
            return (
                str(markdown or ""),
                bbox_map if isinstance(bbox_map, dict) else {},
                tables if isinstance(tables, list) else [],
                figures if isinstance(figures, list) else [],
                parse_stats if isinstance(parse_stats, dict) else {},
            )
        if len(parsed) == 4:
            markdown, bbox_map, tables, figures = parsed
            return (
                str(markdown or ""),
                bbox_map if isinstance(bbox_map, dict) else {},
                tables if isinstance(tables, list) else [],
                figures if isinstance(figures, list) else [],
                {},
            )
        if len(parsed) == 3:
            markdown, bbox_map, tables = parsed
            return (
                str(markdown or ""),
                bbox_map if isinstance(bbox_map, dict) else {},
                tables if isinstance(tables, list) else [],
                [],
                {},
            )
    raise ValueError("Unexpected parse output shape")


def _build_document_and_payload(file_path: Path, *, track: str) -> Tuple[DocumentExtractionResponse, Dict[str, Any], Dict[str, Any]]:
    file_bytes = file_path.read_bytes()
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    parsed = parse_document_in_subprocess(file_bytes, file_path.name, track)
    markdown, bbox_map, tables, figures, parse_stats = _normalize_parse_output(parsed)
    diagnostics = {
        "table_count": len(tables),
        "figure_count": len(figures),
        "parse_stats": parse_stats,
        "ref_count": len(bbox_map),
        "track": track,
    }
    document = DocumentExtractionResponse(
        file_name=file_path.name,
        file_hash=file_hash,
        track=track,
        cached=False,
        result=ExtractionResult({}),
        errors=[],
        soft_warnings=[],
        trace_hits=[],
        trace_stats={},
        diagnostics=diagnostics,
    )
    payload = {
        "file_name": file_path.name,
        "file_hash": file_hash,
        "markdown": markdown,
        "tables": tables,
        "figures": figures,
    }
    parse_brief = {
        "path": str(file_path),
        "track": track,
        "table_count": len(tables),
        "figure_count": len(figures),
        "first_table_id": str(tables[0].get("table_id") or "") if tables else "",
        "first_figure_id": str(figures[0].get("figure_id") or "") if figures else "",
        "first_figure_caption": str(figures[0].get("caption") or "") if figures else "",
        "first_figure_key_points": (
            list(figures[0].get("key_points") or figures[0].get("insights") or [])[:3] if figures else []
        ),
        "first_figure_dataframe_rows": (
            len(((figures[0].get("dataframe") or {}).get("rows") or [])) if figures else 0
        ),
    }
    return document, payload, parse_brief


def _render_pdf_page_image(pdf_path: Path, *, page_no: int = 4, dpi: int = 180) -> Path:
    import fitz

    target = ARTIFACT_DIR / f"{pdf_path.stem}_page_{page_no}.png"
    doc = fitz.open(pdf_path)
    try:
        page_index = max(0, min(len(doc) - 1, page_no - 1))
        page = doc.load_page(page_index)
        pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0), alpha=False)
        pix.save(str(target))
    finally:
        doc.close()
    return target


async def _ask(
    service: AssistantService,
    *,
    document: DocumentExtractionResponse,
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
    storage = ExtractionStorage("postgresql://postgres:postgres@localhost:5433/Data_Extraction")
    await storage.connect()
    service = AssistantService(storage)

    report: Dict[str, Any] = {
        "prompt_version_expected": "document-intelligence-assistant-v1.6",
        "excel_path": str(EXCEL_PATH),
        "pdf_path": str(PDF_PATH),
        "results": [],
    }

    excel_doc, excel_payload, excel_parse = _build_document_and_payload(EXCEL_PATH, track="FastTrack")
    report["excel_parse"] = excel_parse
    session_id: Optional[str] = None
    for scenario in EXCEL_QUESTIONS:
        answer, meta = await _ask(
            service,
            document=excel_doc,
            extraction_payload=excel_payload,
            question=scenario["question"],
            session_id=session_id,
        )
        session_id = str(meta.get("session_id") or session_id or "")
        report["results"].append(
            {
                "name": scenario["name"],
                "kind": "excel",
                "question": scenario["question"],
                "expected": scenario["expected"],
                "answer": answer,
                "meta": {
                    "prompt_version": meta.get("prompt_version"),
                    "tools_used": meta.get("tools_used"),
                    "session_id": meta.get("session_id"),
                },
            }
        )

    pdf_doc, pdf_payload, pdf_parse = _build_document_and_payload(PDF_PATH, track="VisualTrack")
    report["pdf_parse"] = pdf_parse
    pdf_answer, pdf_meta = await _ask(
        service,
        document=pdf_doc,
        extraction_payload=pdf_payload,
        question=PDF_QUESTION["question"],
    )
    report["results"].append(
        {
            "name": PDF_QUESTION["name"],
            "kind": "pdf",
            "question": PDF_QUESTION["question"],
            "expected": PDF_QUESTION["expected"],
            "answer": pdf_answer,
            "meta": {
                "prompt_version": pdf_meta.get("prompt_version"),
                "tools_used": pdf_meta.get("tools_used"),
                "session_id": pdf_meta.get("session_id"),
            },
        }
    )

    image_path = _render_pdf_page_image(PDF_PATH, page_no=4, dpi=180)
    image_doc, image_payload, image_parse = _build_document_and_payload(image_path, track="FastTrack")
    report["image_path"] = str(image_path)
    report["image_parse"] = image_parse
    image_answer, image_meta = await _ask(
        service,
        document=image_doc,
        extraction_payload=image_payload,
        question=IMAGE_QUESTION["question"],
    )
    report["results"].append(
        {
            "name": IMAGE_QUESTION["name"],
            "kind": "image",
            "question": IMAGE_QUESTION["question"],
            "expected": IMAGE_QUESTION["expected"],
            "answer": image_answer,
            "meta": {
                "prompt_version": image_meta.get("prompt_version"),
                "tools_used": image_meta.get("tools_used"),
                "session_id": image_meta.get("session_id"),
            },
        }
    )

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report_path": str(REPORT_PATH), "result_count": len(report["results"])}, ensure_ascii=False))

    await storage.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
