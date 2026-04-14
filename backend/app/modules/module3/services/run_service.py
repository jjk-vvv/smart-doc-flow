from __future__ import annotations

import argparse
import json
import threading
from pathlib import Path
from typing import Any, Callable

from app.modules.file_assets.service import resolve_file_for_owner

from ..core.config import ALLOWED_TEMPLATE_SUFFIXES, DEFAULT_HEADER_ROW, DEFAULT_PROMPT, read_runtime_settings
from ..schemas.run_schemas import WebRunRequest
from .source_dispatcher import extract_rows_from_source, extract_rows_from_word_source, log_event, prefixed_logger
from .storage_service import (
    append_run_log,
    load_docset_record,
    load_template_record,
    register_run_output_file_asset,
    run_directory,
    run_rows_path,
    set_run_status,
    utcnow_iso,
    write_json_atomic,
)
from .template_service import build_default_output_path, read_template_headers, write_filled_template
from .user_rule_service import apply_user_rule_bundle, resolve_scope_user_prompts, resolve_user_rule_bundle


class RunCancelledError(Exception):
    pass


_RUN_CANCEL_LOCK = threading.Lock()
_RUN_CANCEL_EVENTS: dict[str, threading.Event] = {}


def register_run_control(run_id: str) -> None:
    with _RUN_CANCEL_LOCK:
        _RUN_CANCEL_EVENTS[run_id] = threading.Event()


def unregister_run_control(run_id: str) -> None:
    with _RUN_CANCEL_LOCK:
        _RUN_CANCEL_EVENTS.pop(run_id, None)


def cancel_run(run_id: str) -> bool:
    with _RUN_CANCEL_LOCK:
        event = _RUN_CANCEL_EVENTS.get(run_id)
    if event is None:
        return False
    event.set()
    return True


def cancel_runs(run_ids: list[str]) -> int:
    cancelled = 0
    for run_id in run_ids:
        if cancel_run(run_id):
            cancelled += 1
    return cancelled


def _ensure_run_active(run_id: str, logger: Callable[[str], None] | None = None) -> None:
    with _RUN_CANCEL_LOCK:
        event = _RUN_CANCEL_EVENTS.get(run_id)
    if event is not None and event.is_set():
        log_event(logger, "[cancelled] task stopped by user")
        raise RunCancelledError("任务已停止")


def _row_has_value(row: dict[str, str], headers: list[str]) -> bool:
    return any(str(row.get(header, "")).strip() for header in headers)


def _collect_available_headers(rows: list[dict[str, str]]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for key in row.keys():
            header = str(key or "").strip()
            if not header or header in seen:
                continue
            seen.add(header)
            ordered.append(header)
    return ordered


def _project_rows(rows: list[dict[str, str]], headers: list[str]) -> list[dict[str, str]]:
    return [{header: str(row.get(header, "")) for header in headers} for row in rows]


def _is_skippable_single_table_source_error(exc: Exception) -> bool:
    message = str(exc)
    return any(
        pattern in message
        for pattern in (
            "模型输出中没有有效的对象行数据",
            "No writable row data extracted from Excel source",
        )
    )


def _docset_item_name(item: dict[str, Any]) -> str:
    filename = str(item.get("filename") or "").strip()
    if filename:
        return filename
    file_id = str(item.get("file_id") or "").strip()
    if file_id:
        return file_id
    return "unknown_source"


def _resolve_docset_source_path(item: dict[str, Any], owner_id: str) -> Path:
    file_id = str(item.get("file_id") or "").strip()
    if not file_id:
        raise ValueError(f"Docset source file_id is missing: {_docset_item_name(item)}")
    try:
        _, resolved_path = resolve_file_for_owner(file_id, owner_id)
    except PermissionError as exc:
        raise PermissionError(f"No access to source file {file_id}: {exc}")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Source file asset not found {file_id}: {exc}")
    return resolved_path


def _resolve_template_path(template_record: dict[str, Any], owner_id: str) -> Path:
    template_file_id = str(template_record.get("template_file_id") or "").strip()
    if not template_file_id:
        raise ValueError("Template file_id is missing")
    try:
        _, resolved_path = resolve_file_for_owner(template_file_id, owner_id)
    except PermissionError as exc:
        raise PermissionError(f"No access to template file {template_file_id}: {exc}")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Template file asset not found {template_file_id}: {exc}")
    return resolved_path


def _table_headers(table_block: dict[str, Any]) -> list[str]:
    headers: list[str] = []
    for item in table_block.get("header_columns", []):
        if isinstance(item, dict):
            header = str(item.get("header", "")).strip()
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            header = str(item[1]).strip()
        else:
            header = ""
        if header:
            headers.append(header)
    return headers


def _filter_table_rows(table_block: dict[str, Any], rows: list[dict[str, str]]) -> list[dict[str, str]]:
    headers = _table_headers(table_block)
    meaningful_rows = [row for row in rows if _row_has_value(row, headers)]
    if str(table_block.get("fill_mode") or "detail_rows") != "key_value":
        return meaningful_rows

    if not meaningful_rows:
        return []

    merged = {header: "" for header in headers}
    for row in meaningful_rows:
        for header in headers:
            value = str(row.get(header, "")).strip()
            if value and not merged[header]:
                merged[header] = value
    return [merged] if _row_has_value(merged, headers) else []


def _build_docx_block_prompt(base_prompt: str, table_block: dict[str, Any], template_filename: str = "") -> str:
    headers = ", ".join(_table_headers(table_block))
    parts: list[str] = []

    if base_prompt.strip():
        parts.append(base_prompt.strip())

    parts.extend(
        [
            "Supplemental template instructions for the current DOCX table block:",
            f"- Only extract data for DOCX template table {int(table_block['table_index']) + 1}.",
            f"- Fill mode: {table_block.get('fill_mode') or 'detail_rows'}.",
            f"- Target fields for this block only: {headers}.",
            "- Do not merge data that belongs to other DOCX template tables.",
        ]
    )

    if template_filename.strip():
        parts.append(f"- DOCX template filename: {template_filename.strip()}")

    context_text = str(table_block.get("context_text", "")).strip()
    if context_text:
        parts.append(f"- Template context: {context_text}")

    available_row_slots = int(table_block.get("available_row_slots") or 0)
    if available_row_slots > 0:
        parts.append(f"- Existing writable rows available in this DOCX table: {available_row_slots}.")

    if str(table_block.get("fill_mode") or "detail_rows") == "key_value":
        parts.append("- Return one object row for this block. Fill only values that belong to the listed keys.")
    else:
        parts.append("- If the source contains multiple record groups, only keep rows that match this table block.")
        parts.append("- If the mapped Excel rows contain more candidates than the table needs, keep only the rows that truly belong to this DOCX table.")

    return "\n".join(parts)


def _build_docx_rows_payload(
    table_blocks: list[dict[str, Any]],
    rows_by_block: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    flat_rows: list[dict[str, str]] = []
    tables_payload: list[dict[str, Any]] = []

    for table_block in table_blocks:
        block_id = str(table_block.get("block_id"))
        headers = _table_headers(table_block)
        rows = rows_by_block.get(block_id, [])
        flat_rows.extend(rows)
        tables_payload.append(
            {
                "block_id": block_id,
                "table_index": int(table_block["table_index"]),
                "fill_mode": table_block.get("fill_mode") or "detail_rows",
                "context_text": table_block.get("context_text") or "",
                "headers": headers,
                "rows": rows,
            }
        )

    return {
        "template_type": "docx",
        "rows": flat_rows,
        "tables": tables_payload,
    }


def _build_docx_rule_scopes(table_blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scopes: list[dict[str, Any]] = []
    for table_block in table_blocks:
        scopes.append(
            {
                "scope_id": str(table_block.get("block_id", "")),
                "table_index": int(table_block.get("table_index", 0)) + 1,
                "headers": _table_headers(table_block),
                "context_text": str(table_block.get("context_text", "") or "").strip(),
                "fill_mode": str(table_block.get("fill_mode") or "detail_rows"),
            }
        )
    return scopes


def _run_docx_template_with_word_source(
    *,
    template_info: dict[str, Any],
    template_path: Path,
    word_path: Path,
    prompt: str,
    settings: dict[str, Any],
    output_path: Path,
    logger: Callable[[str], None] | None,
    template_filename: str = "",
) -> dict[str, Any]:
    table_blocks = template_info.get("tables") or []
    if not table_blocks:
        raise ValueError("No DOCX template tables were detected")

    rows_by_block: dict[str, list[dict[str, str]]] = {}
    scope_prompts = resolve_scope_user_prompts(
        user_prompt=prompt,
        scopes=_build_docx_rule_scopes(table_blocks),
        settings=settings,
        logger=logger,
        template_filename=template_filename,
    )

    for table_block in table_blocks:
        headers = _table_headers(table_block)
        if not headers:
            continue
        block_label = f"[table {int(table_block['table_index']) + 1}] "
        block_logger = prefixed_logger(logger, block_label)
        block_prompt = _build_docx_block_prompt(prompt.strip() or DEFAULT_PROMPT, table_block, template_filename)
        rows = extract_rows_from_word_source(
            word_path=word_path,
            headers=headers,
            prompt=block_prompt,
            base_url=settings["base_url"],
            api_key=settings["api_key"],
            model=settings["model"],
            api_mode=settings["api_mode"],
            max_images=settings["max_images"],
            max_image_bytes=settings["max_image_bytes"],
            logger=block_logger,
        )
        scoped_user_prompt = scope_prompts.get(str(table_block["block_id"]), prompt)
        rule_bundle = resolve_user_rule_bundle(
            user_prompt=scoped_user_prompt,
            headers=headers,
            available_headers=_collect_available_headers(rows),
            settings=settings,
            logger=block_logger,
            context_text=str(table_block.get("context_text") or ""),
            template_filename=template_filename,
            source_context_text=f"source_file={word_path.name}",
            sample_rows=rows,
        )
        rows = apply_user_rule_bundle(rows, rule_bundle, logger=block_logger)
        rows_by_block[str(table_block["block_id"])] = _filter_table_rows(table_block, _project_rows(rows, headers))

    payload = _build_docx_rows_payload(table_blocks, rows_by_block)
    if not payload["rows"]:
        raise ValueError("No writable data extracted for DOCX template")

    write_filled_template(
        template_path=template_path,
        output_path=output_path,
        template_type="docx",
        sheet_name=None,
        table_index=None,
        header_columns=[],
        rows_values=[],
        write_row=0,
        docx_tables=table_blocks,
        docx_rows_by_block=rows_by_block,
    )
    log_event(logger, "[step4] DOCX template blocks written")

    return {
        "row_count": len(payload["rows"]),
        "payload": payload,
        "table_count": len(table_blocks),
    }


def run(args: argparse.Namespace, logger: Callable[[str], None] | None = None) -> dict[str, Any]:
    settings = read_runtime_settings(args.api_mode)
    raw_user_prompt = (args.prompt or "").strip()

    word_path = Path(args.word).resolve()
    template_path = Path(args.template).resolve()
    if not word_path.exists():
        raise FileNotFoundError(f"Word file not found: {word_path}")
    if not template_path.exists():
        raise FileNotFoundError(f"Template file not found: {template_path}")

    template_info = read_template_headers(template_path, args.sheet, args.header_row)
    output_path = Path(args.output).resolve() if args.output else build_default_output_path(template_path)

    if template_info["template_type"] == "docx":
        docx_result = _run_docx_template_with_word_source(
            template_info=template_info,
            template_path=template_path,
            word_path=word_path,
            prompt=raw_user_prompt,
            settings=settings,
            output_path=output_path,
            logger=logger,
            template_filename=template_path.name,
        )
        if args.json_output:
            json_output_path = Path(args.json_output).resolve()
            json_output_path.parent.mkdir(parents=True, exist_ok=True)
            json_output_path.write_text(json.dumps(docx_result["payload"], ensure_ascii=False, indent=2), encoding="utf-8")
        result = {
            "sheet_name": template_info["sheet_name"],
            "header_count": sum(len(_table_headers(block)) for block in template_info.get("tables", [])),
            "row_count": docx_result["row_count"],
            "output_path": str(output_path),
            "json_output_path": str(Path(args.json_output).resolve()) if args.json_output else "",
        }
        return result

    header_columns = template_info["header_columns"]
    headers = [name for _, name in header_columns]
    rows_values = extract_rows_from_word_source(
        word_path=word_path,
        headers=headers,
        prompt=raw_user_prompt or DEFAULT_PROMPT,
        base_url=settings["base_url"],
        api_key=settings["api_key"],
        model=settings["model"],
        api_mode=settings["api_mode"],
        max_images=settings["max_images"],
        max_image_bytes=settings["max_image_bytes"],
        logger=logger,
    )
    rule_bundle = resolve_user_rule_bundle(
        user_prompt=raw_user_prompt,
        headers=headers,
        available_headers=_collect_available_headers(rows_values),
        settings=settings,
        logger=logger,
        template_filename=template_path.name,
        source_context_text=f"source_file={word_path.name}",
        sample_rows=rows_values,
    )
    rows_values = apply_user_rule_bundle(rows_values, rule_bundle, logger=logger)
    rows_values = _project_rows(rows_values, headers)

    output_path = Path(args.output).resolve() if args.output else build_default_output_path(template_path)
    write_filled_template(
        template_path=template_path,
        output_path=output_path,
        template_type=template_info["template_type"],
        sheet_name=template_info["sheet_name"],
        table_index=template_info["table_index"],
        header_columns=header_columns,
        rows_values=rows_values,
        write_row=args.write_row if template_info["template_type"] == "xlsx" else template_info["write_row"],
    )
    log_event(logger, f"[step4] {template_info['template_type'].upper()} template written")

    if args.json_output:
        json_output_path = Path(args.json_output).resolve()
        json_output_path.parent.mkdir(parents=True, exist_ok=True)
        json_output_path.write_text(json.dumps({"rows": rows_values}, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "sheet_name": template_info["sheet_name"],
        "header_count": len(headers),
        "row_count": len(rows_values),
        "output_path": str(output_path),
        "json_output_path": str(Path(args.json_output).resolve()) if args.json_output else "",
    }


def execute_web_run(run_id: str, request: WebRunRequest) -> None:
    run_dir = run_directory(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    owner_id = str(request.owner_id or "").strip() or "default"

    def run_logger(message: str) -> None:
        append_run_log(run_id, message)

    try:
        template_record = load_template_record(request.template_id, owner_id=owner_id)
        docset_record = load_docset_record(request.doc_set_id, owner_id=owner_id)
        settings = read_runtime_settings(request.api_mode)

        template_path = _resolve_template_path(template_record, owner_id)
        if template_path.suffix.lower() not in ALLOWED_TEMPLATE_SUFFIXES:
            raise ValueError("Current templates only support .xlsx and .docx")
        if not template_path.exists():
            raise FileNotFoundError(f"Template file not found: {template_path}")

        template_info = read_template_headers(
            template_path,
            template_record.get("sheet_name"),
            int(template_record.get("header_row", DEFAULT_HEADER_ROW)),
        )
        template_type = str(template_record.get("template_type") or template_info["template_type"])
        raw_user_prompt = (request.prompt or "").strip()

        files = docset_record.get("files") or []
        if not files:
            raise ValueError("No source files found in docset")

        total = len(files)
        processed = 0

        set_run_status(
            run_id,
            status="running",
            filled=0,
            total=total,
            fill_rate=0,
            error=None,
            output_file_id=None,
        )
        run_logger(f"[start] template={template_record['filename']} files={total}")

        if template_type == "docx":
            table_blocks = template_info.get("tables") or []
            if not table_blocks:
                raise ValueError("No DOCX template tables were detected")

            rows_by_block: dict[str, list[dict[str, str]]] = {str(block["block_id"]): [] for block in table_blocks}
            scope_prompts = resolve_scope_user_prompts(
                user_prompt=raw_user_prompt,
                scopes=_build_docx_rule_scopes(table_blocks),
                settings=settings,
                logger=run_logger,
                template_filename=str(template_record.get("filename") or template_path.name),
            )

            for item in files:
                _ensure_run_active(run_id, run_logger)
                source_path = _resolve_docset_source_path(item, owner_id)
                if not source_path.exists():
                    raise FileNotFoundError(f"Source file not found: {source_path}")

                file_logger = prefixed_logger(run_logger, f"[{source_path.name}] ")
                for table_block in table_blocks:
                    _ensure_run_active(run_id, file_logger)
                    headers = _table_headers(table_block)
                    if not headers:
                        continue
                    block_label = f"[table {int(table_block['table_index']) + 1}] "
                    block_logger = prefixed_logger(file_logger, block_label)
                    block_prompt = _build_docx_block_prompt(
                        raw_user_prompt or DEFAULT_PROMPT,
                        table_block,
                        str(template_record.get("filename") or template_path.name),
                    )
                    rows = extract_rows_from_source(
                        source_path,
                        headers,
                        block_prompt,
                        settings=settings,
                        logger=block_logger,
                        table_context={
                            "template_type": "docx",
                            "template_filename": str(template_record.get("filename") or template_path.name),
                            "table_block": table_block,
                        },
                    )
                    rows_by_block[str(table_block["block_id"])].extend(rows)
                    run_logger(
                        f"[progress] {source_path.name} -> table {int(table_block['table_index']) + 1} "
                        f"added {len(rows)} candidate rows"
                    )

                processed += 1
                set_run_status(
                    run_id,
                    status="running",
                    filled=processed,
                    total=total,
                    fill_rate=(processed / total) if total else 0,
                )

            for table_block in table_blocks:
                _ensure_run_active(run_id, run_logger)
                block_id = str(table_block["block_id"])
                block_label = f"[table {int(table_block['table_index']) + 1}] "
                block_logger = prefixed_logger(run_logger, block_label)
                headers = _table_headers(table_block)
                candidate_rows = rows_by_block.get(block_id, [])
                scoped_user_prompt = scope_prompts.get(block_id, raw_user_prompt)
                rule_bundle = resolve_user_rule_bundle(
                    user_prompt=scoped_user_prompt,
                    headers=headers,
                    available_headers=_collect_available_headers(candidate_rows),
                    settings=settings,
                    logger=block_logger,
                    context_text=str(table_block.get("context_text") or ""),
                    template_filename=str(template_record.get("filename") or template_path.name),
                    source_context_text="; ".join(
                        f"source_file={_docset_item_name(item)}" for item in files
                    ),
                    sample_rows=candidate_rows,
                )
                block_rows = apply_user_rule_bundle(candidate_rows, rule_bundle, logger=block_logger)
                rows_by_block[block_id] = _filter_table_rows(table_block, _project_rows(block_rows, headers))

            payload = _build_docx_rows_payload(table_blocks, rows_by_block)
            if not payload["rows"]:
                raise ValueError("No writable data extracted for DOCX template")

            output_name = f"{template_path.stem}_filled{template_path.suffix}"
            output_path = run_dir / output_name
            write_filled_template(
                template_path=template_path,
                output_path=output_path,
                template_type="docx",
                sheet_name=None,
                table_index=None,
                header_columns=[],
                rows_values=[],
                write_row=0,
                docx_tables=table_blocks,
                docx_rows_by_block=rows_by_block,
                cancel_callback=lambda: _ensure_run_active(run_id, run_logger),
            )
            _ensure_run_active(run_id, run_logger)
            write_json_atomic(run_rows_path(run_id), payload)
            output_file_id = register_run_output_file_asset(
                output_path,
                request.owner_id,
                filename=output_path.name,
            )
            set_run_status(
                run_id,
                status="done",
                filled=processed,
                total=total,
                fill_rate=1.0 if total else 0,
                output_file_id=output_file_id,
                output_name=output_path.name,
                error=None,
                finished_at=utcnow_iso(),
            )
            run_logger(f"[done] output={output_path}")
            return

        table_index = template_record.get("table_index", template_info["table_index"])
        sheet_name = template_record.get("sheet_name") or template_info["sheet_name"]
        if template_type == "xlsx":
            write_row = int(template_info["write_row"])
        else:
            write_row = int(template_record.get("write_row", template_info["write_row"]))
        header_columns = template_info["header_columns"]
        headers = [name for _, name in header_columns]
        all_rows: list[dict[str, str]] = []

        for item in files:
            _ensure_run_active(run_id, run_logger)
            source_path = _resolve_docset_source_path(item, owner_id)
            if not source_path.exists():
                raise FileNotFoundError(f"Source file not found: {source_path}")

            file_logger = prefixed_logger(run_logger, f"[{source_path.name}] ")
            try:
                rows = extract_rows_from_source(
                    source_path,
                    headers,
                    raw_user_prompt or DEFAULT_PROMPT,
                    settings=settings,
                    logger=file_logger,
                )
            except Exception as exc:
                if not _is_skippable_single_table_source_error(exc):
                    raise
                rows = []
                file_logger(f"[skipped] 当前源文件未抽取到可写行，已跳过。原因: {exc}")
            all_rows.extend(rows)
            processed += 1
            set_run_status(
                run_id,
                status="running",
                filled=processed,
                total=total,
                fill_rate=(processed / total) if total else 0,
            )
            run_logger(f"[progress] processed {processed}/{total} files, accumulated {len(all_rows)} rows")

        rule_bundle = resolve_user_rule_bundle(
            user_prompt=raw_user_prompt,
            headers=headers,
            available_headers=_collect_available_headers(all_rows),
            settings=settings,
            logger=run_logger,
            template_filename=str(template_record.get("filename") or template_path.name),
            source_context_text="; ".join(f"source_file={_docset_item_name(item)}" for item in files),
            sample_rows=all_rows,
        )
        all_rows = apply_user_rule_bundle(all_rows, rule_bundle, logger=run_logger)
        if not all_rows:
            raise ValueError("No writable rows extracted from docset")
        all_rows = _project_rows(all_rows, headers)

        output_name = f"{template_path.stem}_filled{template_path.suffix}"
        output_path = run_dir / output_name
        write_filled_template(
            template_path=template_path,
            output_path=output_path,
            template_type=template_type,
            sheet_name=sheet_name,
            table_index=int(table_index) if table_index is not None else None,
            header_columns=header_columns,
            rows_values=all_rows,
            write_row=write_row,
            cancel_callback=lambda: _ensure_run_active(run_id, run_logger),
        )
        _ensure_run_active(run_id, run_logger)
        write_json_atomic(run_rows_path(run_id), {"rows": all_rows})
        output_file_id = register_run_output_file_asset(
            output_path,
            request.owner_id,
            filename=output_path.name,
        )
        set_run_status(
            run_id,
            status="done",
            filled=processed,
            total=total,
            fill_rate=1.0 if total else 0,
            output_file_id=output_file_id,
            output_name=output_path.name,
            error=None,
            finished_at=utcnow_iso(),
        )
        run_logger(f"[done] output={output_path}")
    except RunCancelledError as exc:
        set_run_status(
            run_id,
            status="cancelled",
            error=str(exc),
            finished_at=utcnow_iso(),
        )
    except Exception as exc:
        append_run_log(run_id, f"[failed] {exc}")
        set_run_status(
            run_id,
            status="failed",
            error=str(exc),
            finished_at=utcnow_iso(),
        )
    finally:
        unregister_run_control(run_id)


__all__ = [
    "cancel_run",
    "cancel_runs",
    "execute_web_run",
    "register_run_control",
    "run",
]
