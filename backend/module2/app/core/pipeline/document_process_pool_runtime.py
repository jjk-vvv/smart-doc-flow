from __future__ import annotations

import asyncio
from concurrent.futures.process import BrokenProcessPool
from threading import Lock
from typing import Any, Callable, Dict, List, Optional, Tuple


BuildPool = Callable[[], Any]
ParseDocumentEntrypoint = Callable[..., Any]
TableBlocks = List[Dict[str, Any]]
FigureBlocks = List[Dict[str, Any]]
ParserFactory = Callable[[], Any]


def parse_document_in_subprocess_runtime(
    *,
    parser_factory: ParserFactory,
    file_bytes: bytes,
    file_name: str = "document.pdf",
    track: str = "FastTrack",
    source_file_name: Optional[str] = None,
    source_file_bytes: Optional[bytes] = None,
) -> Tuple[str, Dict[str, List[float]], TableBlocks, FigureBlocks, Dict[str, Any]]:
    """Execute the picklable subprocess document parse flow using an injected parser factory."""

    from ..format.word_input_preparation_runtime import WordPdfContextRuntime

    parser = parser_factory()
    word_pdf_context = WordPdfContextRuntime.build_parse_context(
        file_name=file_name,
        source_file_name=source_file_name,
        source_file_bytes=source_file_bytes,
        use_source_signals=parser.word_pdf_parse_use_source_signals,
    )
    parse_source_file_name = word_pdf_context.get("parse_source_file_name")
    parse_source_file_bytes = word_pdf_context.get("parse_source_file_bytes")
    parse_source_cache_identity = str(word_pdf_context.get("parse_source_cache_identity") or "")
    is_word_pdf_context = bool(word_pdf_context.get("is_word_pdf_context"))

    markdown, bbox_map, table_blocks = parser.parse_document(
        file_name=file_name,
        file_bytes=file_bytes,
        track=track,
        source_file_name=parse_source_file_name,
        source_file_bytes=parse_source_file_bytes,
        source_cache_identity=parse_source_cache_identity,
    )
    parser._overlay_last_parse_stats(
        WordPdfContextRuntime.build_source_stats_patch(
            source_file_name=source_file_name,
            parse_source_file_name=parse_source_file_name,
            parse_source_cache_identity=parse_source_cache_identity,
            use_source_signals=parser.word_pdf_parse_use_source_signals,
            chart_xml_merge_enabled=parser.word_pdf_docx_chart_xml_merge_enable,
        )
    )
    if is_word_pdf_context:
        parser._overlay_last_parse_stats(
            WordPdfContextRuntime.build_docx_chart_merge_stats_patch(
                enabled=parser.word_pdf_docx_chart_xml_merge_enable,
                source_file_name=source_file_name,
                apply_docx_chart_merge=lambda: parser._merge_docx_chart_xml_into_pdf_figures(
                    file_bytes=bytes(source_file_bytes)
                ),
            )
        )

    figure_blocks = parser.get_last_figure_blocks()
    parse_stats = parser.get_last_parse_stats()
    return markdown, bbox_map, table_blocks, figure_blocks, parse_stats


class DocumentProcessPoolRuntime:
    """Manage the module2 document ProcessPool lifecycle and recovery behavior."""

    def __init__(
        self,
        *,
        build_pool: BuildPool,
        parse_document_in_subprocess: ParseDocumentEntrypoint,
        logger: Any,
    ) -> None:
        self._build_pool = build_pool
        self._parse_document_in_subprocess = parse_document_in_subprocess
        self._logger = logger
        self._pool_lock = Lock()
        self._pool = self._build_pool()
        self._generation = 0

    def current_pool(self) -> Any:
        with self._pool_lock:
            return self._pool

    def shutdown_pool(self, pool: Any, *, reason: str) -> None:
        processes = getattr(pool, "_processes", None)
        if isinstance(processes, dict):
            for proc in list(processes.values()):
                if proc is None:
                    continue
                try:
                    if proc.is_alive():
                        proc.terminate()
                except Exception:
                    continue
        try:
            pool.shutdown(wait=False, cancel_futures=True)
        except Exception as exc:
            self._logger.warning(
                "module2 process pool shutdown failed (%s): %s: %s",
                reason,
                type(exc).__name__,
                exc,
            )

    def shutdown_current_pool(self, *, reason: str) -> None:
        self.shutdown_pool(self.current_pool(), reason=reason)

    def reset_pool(self, reason: str) -> int:
        with self._pool_lock:
            old_pool = self._pool
            self._pool = self._build_pool()
            self._generation += 1
            generation = self._generation
        self.shutdown_pool(old_pool, reason=reason)
        self._logger.warning("module2 process pool reset to generation=%s due to %s", generation, reason)
        return generation

    async def run_parse_in_pool(
        self,
        *,
        loop: Any,
        file_bytes: bytes,
        file_name: str,
        track: str,
        timeout_sec: float,
        context_label: str,
        source_file_name: Optional[str] = None,
        source_file_bytes: Optional[bytes] = None,
    ) -> Any:
        executor = self.current_pool()
        future = loop.run_in_executor(
            executor,
            self._parse_document_in_subprocess,
            file_bytes,
            file_name,
            track,
            source_file_name,
            source_file_bytes,
        )
        try:
            return await asyncio.wait_for(future, timeout=timeout_sec)
        except TimeoutError:
            self.reset_pool(f"parse_timeout:{context_label}")
            raise
        except BrokenProcessPool:
            self.reset_pool(f"broken_process_pool:{context_label}")
            raise
        except Exception as exc:
            message = str(exc).lower()
            if "process pool" in message or "multiprocessing" in message:
                self.reset_pool(f"process_pool_error:{context_label}")
            raise
