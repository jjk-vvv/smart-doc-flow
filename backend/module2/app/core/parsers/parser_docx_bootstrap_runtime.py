from __future__ import annotations

import os
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ..format.docx_document_runtime import DocxChartMergeRuntime, DocxDocumentRuntime, DocxViaPdfRuntime
from ..format.docx_enrichment import DocxEnrichmentRuntime
from ..format.word_input_preparation_runtime import WordPdfContextRuntime


RuntimeCallback = Callable[..., Any]
TableBlocks = List[Dict[str, Any]]
FigureBlocks = List[Dict[str, Any]]
ParseResult = Tuple[str, Dict[str, List[float]], TableBlocks]

ParsePdf = Callable[..., ParseResult]
ParseDocxViaPdf = Callable[..., ParseResult]
ParseDocx = Callable[[bytes], ParseResult]
ParseXlsx = Callable[[bytes], ParseResult]
ParsePlain = Callable[..., ParseResult]
ParseImage = Callable[[str, bytes], ParseResult]
OverlayLastParseStatsFn = Callable[[Any], None]
PeekLastFigureBlocksFn = Callable[[], FigureBlocks]
SetLastFigureBlocksFn = Callable[[FigureBlocks], None]


class DocumentDispatchRuntime:
    """Route top-level document parsing without changing downstream parser behavior."""

    def __init__(
        self,
        *,
        word_parse_via_pdf: bool,
        office_convert_enabled: bool,
        word_convert_allow_native_fallback: bool,
        text_extensions: Set[str],
        image_extensions: Set[str],
        parse_pdf: ParsePdf,
        parse_docx_via_pdf: ParseDocxViaPdf,
        parse_docx: ParseDocx,
        parse_xlsx: ParseXlsx,
        parse_plain: ParsePlain,
        parse_image: ParseImage,
    ) -> None:
        self.word_parse_via_pdf = bool(word_parse_via_pdf)
        self.office_convert_enabled = bool(office_convert_enabled)
        self.word_convert_allow_native_fallback = bool(word_convert_allow_native_fallback)
        self.text_extensions = {str(item or "").lower() for item in (text_extensions or set()) if str(item or "").strip()}
        self.image_extensions = {str(item or "").lower() for item in (image_extensions or set()) if str(item or "").strip()}
        self._parse_pdf = parse_pdf
        self._parse_docx_via_pdf = parse_docx_via_pdf
        self._parse_docx = parse_docx
        self._parse_xlsx = parse_xlsx
        self._parse_plain = parse_plain
        self._parse_image = parse_image

    def parse_document(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        track: str = "FastTrack",
        source_file_name: Optional[str] = None,
        source_file_bytes: Optional[bytes] = None,
        source_cache_identity: str = "",
    ) -> Dict[str, Any]:
        name = (file_name or "unknown").lower()
        _, ext = os.path.splitext(name)
        track_key = str(track or "").strip().lower()
        if ext == ".pdf":
            return {
                "result": self._parse_pdf(
                    file_name,
                    file_bytes,
                    track,
                    source_file_name=source_file_name,
                    source_file_bytes=source_file_bytes,
                    source_cache_identity=source_cache_identity,
                ),
                "stats_patch": {},
            }
        if ext == ".docx":
            force_native_docx = track_key in {"nativedocx", "docxnative", "docx_native"}
            docx_fallback_stats: Dict[str, Any] = {}
            if self.word_parse_via_pdf and self.office_convert_enabled and not force_native_docx:
                try:
                    return {
                        "result": self._parse_docx_via_pdf(file_name=file_name, file_bytes=file_bytes),
                        "stats_patch": {},
                    }
                except Exception as exc:
                    if not self.word_convert_allow_native_fallback:
                        raise ValueError(
                            f"DOCX->PDF parse route failed for {file_name}: {type(exc).__name__}: {exc}"
                        ) from exc
                    docx_fallback_stats = {
                        "docx_pdf_conversion_failed": True,
                        "docx_pdf_conversion_error": f"{type(exc).__name__}: {exc}",
                        "docx_pdf_native_fallback": True,
                    }
            stats_patch = dict(docx_fallback_stats)
            if force_native_docx:
                stats_patch["docx_native_forced"] = True
                stats_patch["docx_native_forced_track"] = track
            return {
                "result": self._parse_docx(file_bytes),
                "stats_patch": stats_patch,
            }
        if ext == ".xlsx":
            return {
                "result": self._parse_xlsx(file_bytes),
                "stats_patch": {},
            }
        if ext in self.text_extensions:
            return {
                "result": self._parse_plain(file_bytes, ext=ext),
                "stats_patch": {},
            }
        if ext in self.image_extensions:
            return {
                "result": self._parse_image(file_name, file_bytes),
                "stats_patch": {},
            }
        raise ValueError(f"Unsupported file type: {ext or 'unknown'}")


class ParserDocxPdfEntryRuntime:
    """Coordinate parser-owned DOCX-via-PDF bridge adapters without leaving them inline in parser.py."""

    def parse_docx_via_pdf(
        self,
        *,
        docx_via_pdf_runtime: Any,
        docx_chart_merge_runtime: Any,
        file_name: str,
        file_bytes: bytes,
        word_pdf_docx_chart_xml_merge_enable: bool,
        overlay_last_parse_stats: OverlayLastParseStatsFn,
        peek_last_figure_blocks: PeekLastFigureBlocksFn,
        set_last_figure_blocks: SetLastFigureBlocksFn,
    ) -> ParseResult:
        runtime_result = docx_via_pdf_runtime.parse_docx_via_pdf(
            file_name=file_name,
            file_bytes=file_bytes,
        )
        overlay_last_parse_stats(runtime_result.get("stats_patch"))
        overlay_last_parse_stats(
            WordPdfContextRuntime.build_docx_chart_merge_stats_patch(
                enabled=word_pdf_docx_chart_xml_merge_enable,
                source_file_name=file_name,
                apply_docx_chart_merge=lambda: self.merge_docx_chart_xml_into_pdf_figures(
                    docx_chart_merge_runtime=docx_chart_merge_runtime,
                    file_bytes=file_bytes,
                    overlay_last_parse_stats=overlay_last_parse_stats,
                    peek_last_figure_blocks=peek_last_figure_blocks,
                    set_last_figure_blocks=set_last_figure_blocks,
                ),
            )
        )
        return (
            str(runtime_result.get("markdown") or ""),
            dict(runtime_result.get("bbox_map") or {}),
            list(runtime_result.get("table_blocks") or []),
        )

    def merge_docx_chart_xml_into_pdf_figures(
        self,
        *,
        docx_chart_merge_runtime: Any,
        file_bytes: bytes,
        overlay_last_parse_stats: OverlayLastParseStatsFn,
        peek_last_figure_blocks: PeekLastFigureBlocksFn,
        set_last_figure_blocks: SetLastFigureBlocksFn,
    ) -> None:
        runtime_result = docx_chart_merge_runtime.merge_docx_chart_xml_into_pdf_figures(
            file_bytes=file_bytes,
            figure_blocks=peek_last_figure_blocks(),
        )
        set_last_figure_blocks(runtime_result.get("figure_blocks") or [])
        overlay_last_parse_stats(runtime_result.get("stats_patch"))


class ParserDispatchBundleRuntime:
    """Build pure kwargs for parser-owned top-level document dispatch runtimes."""

    def build_docx_via_pdf_kwargs(
        self,
        *,
        word_pdf_timeout_sec: int,
        word_pdf_parse_use_source_signals: bool,
        word_pdf_docx_chart_xml_merge_enable: bool,
        convert_word_bytes_to_pdf: RuntimeCallback,
        parse_pdf: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "word_pdf_timeout_sec": word_pdf_timeout_sec,
            "word_pdf_parse_use_source_signals": word_pdf_parse_use_source_signals,
            "word_pdf_docx_chart_xml_merge_enable": word_pdf_docx_chart_xml_merge_enable,
            "convert_word_bytes_to_pdf": convert_word_bytes_to_pdf,
            "parse_pdf": parse_pdf,
        }

    def build_document_dispatch_kwargs(
        self,
        *,
        word_parse_via_pdf: bool,
        office_convert_enabled: bool,
        word_convert_allow_native_fallback: bool,
        text_extensions: Set[str],
        image_extensions: Set[str],
        parse_pdf: RuntimeCallback,
        parse_docx_via_pdf: RuntimeCallback,
        parse_docx: RuntimeCallback,
        parse_xlsx: RuntimeCallback,
        parse_plain: RuntimeCallback,
        parse_image: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "word_parse_via_pdf": word_parse_via_pdf,
            "office_convert_enabled": office_convert_enabled,
            "word_convert_allow_native_fallback": word_convert_allow_native_fallback,
            "text_extensions": text_extensions,
            "image_extensions": image_extensions,
            "parse_pdf": parse_pdf,
            "parse_docx_via_pdf": parse_docx_via_pdf,
            "parse_docx": parse_docx,
            "parse_xlsx": parse_xlsx,
            "parse_plain": parse_plain,
            "parse_image": parse_image,
        }


class ParserDocxContentBundleRuntime:
    """Build pure kwargs for parser-owned DOCX content runtimes."""

    def build_docx_document_kwargs(
        self,
        *,
        nonpdf_figure_max: int,
        consume_document: RuntimeCallback,
        extract_docx_chart_and_media: RuntimeCallback,
        merge_figure_blocks: RuntimeCallback,
        consume_relaxed_root: RuntimeCallback,
        append_text_ref: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "nonpdf_figure_max": nonpdf_figure_max,
            "consume_document": consume_document,
            "extract_docx_chart_and_media": extract_docx_chart_and_media,
            "merge_figure_blocks": merge_figure_blocks,
            "consume_relaxed_root": consume_relaxed_root,
            "append_text_ref": append_text_ref,
        }

    def build_docx_chart_merge_kwargs(
        self,
        *,
        extract_docx_chart_xml_tables: RuntimeCallback,
        normalize_text: RuntimeCallback,
        find_matching_pdf_figure_index: RuntimeCallback,
        table_block_to_dataframe: RuntimeCallback,
        safe_text_list: RuntimeCallback,
    ) -> Dict[str, Any]:
        return {
            "extract_docx_chart_xml_tables": extract_docx_chart_xml_tables,
            "normalize_text": normalize_text,
            "find_matching_pdf_figure_index": find_matching_pdf_figure_index,
            "table_block_to_dataframe": table_block_to_dataframe,
            "safe_text_list": safe_text_list,
        }


class ParserDocxBootstrapRuntime:
    """Build DOCX dispatch/content runtimes so parser.py only coordinates route sequencing."""

    def build_docx_runtime_attrs(
        self,
        *,
        parser_dispatch_bundle_runtime: Any,
        parser_docx_content_bundle_runtime: Any,
        build_docx_enrichment_bundle: RuntimeCallback,
        word_pdf_timeout_sec: int,
        word_pdf_parse_use_source_signals: bool,
        word_pdf_docx_chart_xml_merge_enable: bool,
        word_parse_via_pdf: bool,
        office_convert_enabled: bool,
        word_convert_allow_native_fallback: bool,
        text_extensions: Set[str],
        image_extensions: Set[str],
        artifact_root_dir: Any,
        docx_chart_xml_enable: bool,
        docx_media_probe_enable: bool,
        docx_media_max_assets: int,
        docx_media_vision_enable: bool,
        docx_media_nested_gemini_enhance_enable: bool,
        docx_media_max_assets_unbounded: bool,
        docx_media_vision_max_assets: int,
        docx_media_vision_max_assets_unbounded: bool,
        docx_media_vision_max_bytes: int,
        docx_media_vision_chart_only: bool,
        docx_media_vision_allow_noncue: bool,
        nonpdf_figure_max: int,
        normalize_text: RuntimeCallback,
        safe_text_list: RuntimeCallback,
        looks_like_figure_cue_text: RuntimeCallback,
        normalize_dataframe_headers: RuntimeCallback,
        normalize_dataframe_matrix: RuntimeCallback,
        decorate_rows_with_meta: RuntimeCallback,
        build_header_meta: RuntimeCallback,
        parse_pdf: RuntimeCallback,
        parse_docx_via_pdf: RuntimeCallback,
        parse_docx: RuntimeCallback,
        parse_xlsx: RuntimeCallback,
        parse_plain: RuntimeCallback,
        parse_image: RuntimeCallback,
        get_last_figure_blocks: RuntimeCallback,
        set_last_figure_blocks: RuntimeCallback,
        convert_word_bytes_to_pdf: RuntimeCallback,
        consume_document: RuntimeCallback,
        merge_figure_blocks: RuntimeCallback,
        consume_relaxed_root: RuntimeCallback,
        append_text_ref: RuntimeCallback,
        find_matching_pdf_figure_index: RuntimeCallback,
        table_block_to_dataframe: RuntimeCallback,
    ) -> Dict[str, Any]:
        docx_via_pdf_runtime = DocxViaPdfRuntime(
            **parser_dispatch_bundle_runtime.build_docx_via_pdf_kwargs(
                word_pdf_timeout_sec=word_pdf_timeout_sec,
                word_pdf_parse_use_source_signals=word_pdf_parse_use_source_signals,
                word_pdf_docx_chart_xml_merge_enable=word_pdf_docx_chart_xml_merge_enable,
                convert_word_bytes_to_pdf=convert_word_bytes_to_pdf,
                parse_pdf=parse_pdf,
            )
        )
        document_dispatch_runtime = DocumentDispatchRuntime(
            **parser_dispatch_bundle_runtime.build_document_dispatch_kwargs(
                word_parse_via_pdf=word_parse_via_pdf,
                office_convert_enabled=office_convert_enabled,
                word_convert_allow_native_fallback=word_convert_allow_native_fallback,
                text_extensions=text_extensions,
                image_extensions=image_extensions,
                parse_pdf=parse_pdf,
                parse_docx_via_pdf=parse_docx_via_pdf,
                parse_docx=parse_docx,
                parse_xlsx=parse_xlsx,
                parse_plain=parse_plain,
                parse_image=parse_image,
            )
        )

        enrichment_bundle = build_docx_enrichment_bundle(
            artifact_root_dir=artifact_root_dir,
            image_extensions=image_extensions,
            docx_chart_xml_enable=docx_chart_xml_enable,
            docx_media_probe_enable=docx_media_probe_enable,
            docx_media_max_assets=docx_media_max_assets,
            docx_media_vision_enable=docx_media_vision_enable,
            docx_media_nested_gemini_enhance_enable=docx_media_nested_gemini_enhance_enable,
            docx_media_max_assets_unbounded=docx_media_max_assets_unbounded,
            docx_media_vision_max_assets=docx_media_vision_max_assets,
            docx_media_vision_max_assets_unbounded=docx_media_vision_max_assets_unbounded,
            docx_media_vision_max_bytes=docx_media_vision_max_bytes,
            docx_media_vision_chart_only=docx_media_vision_chart_only,
            docx_media_vision_allow_noncue=docx_media_vision_allow_noncue,
            nonpdf_figure_max=nonpdf_figure_max,
            normalize_text=normalize_text,
            safe_text_list=safe_text_list,
            looks_like_figure_cue_text=looks_like_figure_cue_text,
            normalize_dataframe_headers=normalize_dataframe_headers,
            normalize_dataframe_matrix=normalize_dataframe_matrix,
            decorate_rows_with_meta=decorate_rows_with_meta,
            build_header_meta=build_header_meta,
            parse_image=parse_image,
            get_last_figure_blocks=get_last_figure_blocks,
            set_last_figure_blocks=set_last_figure_blocks,
        )
        docx_enrichment = DocxEnrichmentRuntime(
            **enrichment_bundle.config_kwargs,
            **enrichment_bundle.callback_kwargs,
        )
        docx_document_runtime = DocxDocumentRuntime(
            **parser_docx_content_bundle_runtime.build_docx_document_kwargs(
                nonpdf_figure_max=nonpdf_figure_max,
                consume_document=consume_document,
                extract_docx_chart_and_media=docx_enrichment.extract_docx_chart_and_media,
                merge_figure_blocks=merge_figure_blocks,
                consume_relaxed_root=consume_relaxed_root,
                append_text_ref=append_text_ref,
            )
        )
        docx_chart_merge_runtime = DocxChartMergeRuntime(
            **parser_docx_content_bundle_runtime.build_docx_chart_merge_kwargs(
                extract_docx_chart_xml_tables=docx_enrichment.extract_docx_chart_xml_tables,
                normalize_text=normalize_text,
                find_matching_pdf_figure_index=find_matching_pdf_figure_index,
                table_block_to_dataframe=table_block_to_dataframe,
                safe_text_list=safe_text_list,
            )
        )
        return {
            "_docx_via_pdf_runtime": docx_via_pdf_runtime,
            "_document_dispatch_runtime": document_dispatch_runtime,
            "_docx_enrichment": docx_enrichment,
            "_docx_document_runtime": docx_document_runtime,
            "_docx_chart_merge_runtime": docx_chart_merge_runtime,
        }
