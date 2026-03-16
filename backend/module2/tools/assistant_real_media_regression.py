from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import sys
import types
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import MethodType
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
from app import schemas as app_schemas
from app.schemas import DocumentExtractionResponse, ExtractionResult


@dataclass
class AssistantChatStreamRequestCompat:
    document: DocumentExtractionResponse
    summary: str = ""
    user_message: str = ""
    session_id: Optional[str] = None
    persist: bool = False
    top_k: int = 12
    enable_web_search: Optional[bool] = None
    current_object_lock: Optional[Dict[str, Any]] = None
    extraction_payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AssistantSessionMessageCompat:
    role: str
    content: str
    created_at: str = ""


if not hasattr(app_schemas, "AssistantChatStreamRequest"):
    setattr(app_schemas, "AssistantChatStreamRequest", AssistantChatStreamRequestCompat)
if not hasattr(app_schemas, "AssistantSessionMessage"):
    setattr(app_schemas, "AssistantSessionMessage", AssistantSessionMessageCompat)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_storage_compat(storage: ExtractionStorage) -> None:
    if not hasattr(storage, "_compat_sessions"):
        storage._compat_sessions = {}
    if not hasattr(storage, "_compat_assistant_messages"):
        storage._compat_assistant_messages = []
    if not hasattr(storage, "_compat_tool_invocations"):
        storage._compat_tool_invocations = []
    if not hasattr(storage, "_compat_saved_facts"):
        storage._compat_saved_facts = []
    if not hasattr(storage, "_compat_extraction_payloads"):
        storage._compat_extraction_payloads = {}

    async def fetch_assistant_session(self: ExtractionStorage, session_id: str) -> Optional[Dict[str, Any]]:
        return dict(self._compat_sessions.get(str(session_id or "").strip(), {})) or None

    async def upsert_assistant_session(
        self: ExtractionStorage,
        *,
        session_id: str,
        file_hash: str,
        file_name: str,
        summary_text: str,
        current_object_lock: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> None:
        self._compat_sessions[str(session_id)] = {
            "session_id": str(session_id),
            "file_hash": str(file_hash),
            "file_name": str(file_name),
            "summary_text": str(summary_text or ""),
            "current_object_lock_json": dict(current_object_lock or {}),
            "metadata": dict(metadata or {}),
            "updated_at": _utc_now(),
        }

    async def list_assistant_messages(self: ExtractionStorage, session_id: str, limit: int = 24) -> List[Dict[str, Any]]:
        items = [item for item in self._compat_assistant_messages if str(item.get("session_id") or "") == str(session_id or "")]
        return [dict(item) for item in items[-max(1, int(limit or 24)) :]]

    async def save_assistant_message(
        self: ExtractionStorage,
        *,
        session_id: str,
        message_id: str,
        role: str,
        message_type: str,
        content: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> None:
        self._compat_assistant_messages.append(
            {
                "session_id": str(session_id),
                "message_id": str(message_id),
                "role": str(role),
                "message_type": str(message_type or "assistant_text"),
                "content": str(content or ""),
                "payload": dict(payload or {}),
                "created_at": _utc_now(),
            }
        )

    async def query_saved_facts(self: ExtractionStorage, **_: Any) -> List[Dict[str, Any]]:
        return [dict(item) for item in self._compat_saved_facts]

    async def load_extraction_payload(self: ExtractionStorage, file_hash: str) -> Optional[Dict[str, Any]]:
        payload = self._compat_extraction_payloads.get(str(file_hash or "").strip())
        return dict(payload) if isinstance(payload, dict) else None

    async def save_tool_invocation(self: ExtractionStorage, *args: Any, **kwargs: Any) -> None:
        self._compat_tool_invocations.append(
            {
                "args": list(args),
                "kwargs": dict(kwargs),
                "created_at": _utc_now(),
            }
        )

    storage.fetch_assistant_session = MethodType(fetch_assistant_session, storage)
    storage.upsert_assistant_session = MethodType(upsert_assistant_session, storage)
    storage.list_assistant_messages = MethodType(list_assistant_messages, storage)
    storage.save_assistant_message = MethodType(save_assistant_message, storage)
    storage.query_saved_facts = MethodType(query_saved_facts, storage)
    storage.load_extraction_payload = MethodType(load_extraction_payload, storage)
    storage.save_tool_invocation = MethodType(save_tool_invocation, storage)


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


def _pick_first_existing(paths: List[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    raise FileNotFoundError("No existing candidate path found.")


def _resolve_excel_path() -> Path:
    candidates = sorted((REPO_ROOT / "datasets" / "Excel").glob("*空气质量*.xlsx"))
    if candidates:
        return _pick_first_existing(candidates)
    raise FileNotFoundError("Cannot locate excel regression sample.")


def _resolve_pdf_path() -> Path:
    candidates = sorted((MODULE2_ROOT / "artifacts" / "pdf_parse" / "mineru").glob("*/input.pdf"))
    if candidates:
        return _pick_first_existing(candidates)
    if REPORT_PATH.exists():
        try:
            report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
            hinted = Path(str(report.get("pdf_path") or ""))
            if hinted.exists():
                return hinted
        except Exception:
            pass
    raise FileNotFoundError("Cannot locate pdf regression sample.")


EXCEL_PATH = _resolve_excel_path()
PDF_PATH = _resolve_pdf_path()

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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run real media assistant regression for Module 2.")
    parser.add_argument(
        "--kind",
        choices=["all", "excel", "pdf", "image"],
        default="all",
        help="Which real-media scenario set to run.",
    )
    return parser.parse_args()


def _decode_stream_frames(frames: List[bytes]) -> Tuple[str, Dict[str, Any]]:
    text = b"".join(frames).decode("utf-8", errors="ignore")
    normalized = text.replace("\r\n", "\n")
    answer_parts: List[str] = []
    meta: Dict[str, Any] = {}
    tool_names: List[str] = []

    for block in normalized.split("\n\n"):
        chunk = block.strip()
        if not chunk:
            continue
        event_name = "message"
        data_lines: List[str] = []
        for line in chunk.split("\n"):
          stripped = line.strip()
          if not stripped:
              continue
          if stripped.startswith("event:"):
              event_name = stripped[6:].strip() or "message"
              continue
          if stripped.startswith("data:"):
              data_lines.append(stripped[5:].strip())
        if not data_lines:
            continue
        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue

        if event_name == "assistant_start":
            meta["session_id"] = payload.get("session_id")
            meta["assistant_message_id"] = payload.get("assistant_message_id")
        elif event_name == "tool_status":
            tool_name = str(payload.get("tool_name") or "").strip()
            if tool_name and tool_name not in tool_names:
                tool_names.append(tool_name)
        elif event_name == "assistant_delta":
            delta_text = str(payload.get("text") or "")
            if delta_text:
                answer_parts.append(delta_text)
        elif event_name == "assistant_done":
            meta.update(payload)

    if tool_names:
        meta["tools_used"] = tool_names
    answer = str(meta.get("answer") or "").strip() or "".join(answer_parts).strip()
    return answer, meta


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


async def main(kind: str = "all") -> int:
    storage = ExtractionStorage("postgresql://postgres:postgres@localhost:5433/Data_Extraction")
    await storage.connect()
    _ensure_storage_compat(storage)
    service = AssistantService(storage)

    report: Dict[str, Any] = {
        "prompt_version_expected": "document-intelligence-assistant-v1.6",
        "excel_path": str(EXCEL_PATH),
        "pdf_path": str(PDF_PATH),
        "results": [],
    }

    if kind in {"all", "excel"}:
        excel_doc, excel_payload, excel_parse = _build_document_and_payload(EXCEL_PATH, track="FastTrack")
        storage._compat_extraction_payloads[excel_doc.file_hash] = dict(excel_payload)
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

    if kind in {"all", "pdf"}:
        pdf_doc, pdf_payload, pdf_parse = _build_document_and_payload(PDF_PATH, track="VisualTrack")
        storage._compat_extraction_payloads[pdf_doc.file_hash] = dict(pdf_payload)
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

    if kind in {"all", "image"}:
        image_path = _render_pdf_page_image(PDF_PATH, page_no=4, dpi=180)
        image_doc, image_payload, image_parse = _build_document_and_payload(image_path, track="FastTrack")
        storage._compat_extraction_payloads[image_doc.file_hash] = dict(image_payload)
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
    args = _parse_args()
    raise SystemExit(asyncio.run(main(kind=args.kind)))
