from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


TableBlocks = List[Dict[str, Any]]
FigureBlocks = List[Dict[str, Any]]
ParseResult = Tuple[str, Dict[str, List[float]], TableBlocks]


class ParserStateRuntime:
    """Normalize parse results and compute parser state patches."""

    @staticmethod
    def normalize_parse_result(result: Any) -> ParseResult:
        markdown, bbox_map, table_blocks = result
        return str(markdown or ""), dict(bbox_map or {}), list(table_blocks or [])

    @classmethod
    def build_named_runtime_state(
        cls,
        runtime_result: Dict[str, Any],
        *,
        include_stats: bool = True,
        include_figure_blocks: bool = True,
    ) -> Dict[str, Any]:
        return {
            "stats": dict(runtime_result.get("stats") or {}) if include_stats else None,
            "figure_blocks": list(runtime_result.get("figure_blocks") or []) if include_figure_blocks else None,
            "result": cls.normalize_parse_result(
                (
                    runtime_result.get("markdown"),
                    runtime_result.get("bbox_map"),
                    runtime_result.get("table_blocks"),
                )
            ),
        }

    @classmethod
    def build_visual_parse_state(cls, outcome: Dict[str, Any]) -> Dict[str, Any]:
        result = outcome.get("result")
        return {
            "stats": dict(outcome.get("stats") or {}),
            "figure_blocks": list(outcome.get("figure_blocks") or []),
            "result": None if result is None else cls.normalize_parse_result(result),
        }

    @classmethod
    def build_pdf_runtime_state(
        cls,
        *,
        runtime_outcome: Dict[str, Any],
        current_stats: Dict[str, Any],
    ) -> Dict[str, Any]:
        kind = str(runtime_outcome.get("kind") or "")
        result = runtime_outcome.get("result")
        if result is None:
            raise ValueError("PDF parse runtime returned no result.")

        if kind == "visual_result":
            stats = dict(current_stats or {})
            stats.update(dict(runtime_outcome.get("stats") or {}))
            stats.update(dict(runtime_outcome.get("stats_patch") or {}))
            return {
                "stats": stats,
                "figure_blocks": None,
                "result": cls.normalize_parse_result(result),
            }

        if kind == "native_early_result":
            return {
                "stats": None,
                "figure_blocks": None,
                "result": cls.normalize_parse_result(result),
            }

        stats = dict(runtime_outcome.get("stats") or {})
        stats.update(dict(runtime_outcome.get("stats_patch") or {}))
        return {
            "stats": stats,
            "figure_blocks": list(runtime_outcome.get("figure_blocks") or []),
            "result": cls.normalize_parse_result(result),
        }

    @classmethod
    def build_xlsx_state(
        cls,
        *,
        markdown: Any,
        bbox_map: Any,
        table_blocks: Any,
        used_zip_fallback: Any,
    ) -> Dict[str, Any]:
        return {
            "stats": {"xlsx_zip_fallback": bool(used_zip_fallback)},
            "figure_blocks": [],
            "result": cls.normalize_parse_result((markdown, bbox_map, table_blocks)),
        }

    @classmethod
    def build_plain_text_state(
        cls,
        *,
        ext: str,
        plain_result: Any,
        merged_figure_blocks: FigureBlocks,
    ) -> Dict[str, Any]:
        return {
            "stats": {
                "plain_ext": (ext or ".txt").lower(),
                "plain_text_chars": len(getattr(plain_result, "text", "") or ""),
                "plain_ref_count": len(getattr(plain_result, "bbox_map", {}) or {}),
                "plain_table_count": len(getattr(plain_result, "table_blocks", []) or []),
                "plain_figure_count": len(getattr(plain_result, "figure_blocks", []) or []),
            },
            "figure_blocks": list(merged_figure_blocks or []),
            "result": cls.normalize_parse_result(
                (
                    getattr(plain_result, "markdown", ""),
                    getattr(plain_result, "bbox_map", {}),
                    getattr(plain_result, "table_blocks", []),
                )
            ),
        }


class ParserRunStateRuntime:
    """Manage mutable parser run state without mixing it into parser control flow."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._runtime_page_count = 0
        self._last_figure_blocks: FigureBlocks = []
        self._last_parse_stats: Dict[str, Any] = {}
        self._last_mineru_run_meta: Dict[str, Any] = {}

    def runtime_page_count(self) -> int:
        return int(self._runtime_page_count or 0)

    def set_runtime_page_count(self, page_count: int) -> None:
        self._runtime_page_count = max(0, int(page_count or 0))

    def peek_last_figure_blocks(self) -> FigureBlocks:
        return self._last_figure_blocks

    def get_last_figure_blocks(self) -> FigureBlocks:
        return [dict(item) for item in self._last_figure_blocks]

    def set_last_figure_blocks(self, figure_blocks: FigureBlocks) -> None:
        self._last_figure_blocks = [dict(item) for item in (figure_blocks or [])]

    def peek_last_parse_stats(self) -> Dict[str, Any]:
        return self._last_parse_stats

    def apply_runtime_stats_patch(self, stats_patch: Any) -> None:
        patch = dict(stats_patch or {})
        if not patch:
            return
        merged_stats = dict(patch)
        merged_stats.update(self._last_parse_stats)
        self._last_parse_stats = merged_stats

    def overlay_last_parse_stats(self, stats_patch: Any) -> None:
        patch = dict(stats_patch or {})
        if not patch:
            return
        merged_stats = dict(self._last_parse_stats)
        merged_stats.update(patch)
        self._last_parse_stats = merged_stats

    def apply_state_update(self, state_update: Dict[str, Any]) -> Optional[ParseResult]:
        if state_update.get("stats") is not None:
            self._last_parse_stats = dict(state_update.get("stats") or {})
        if state_update.get("figure_blocks") is not None:
            self._last_figure_blocks = list(state_update.get("figure_blocks") or [])
        result = state_update.get("result")
        if result is None:
            return None
        markdown, bbox_map, table_blocks = result
        return str(markdown or ""), dict(bbox_map or {}), list(table_blocks or [])

    def set_last_mineru_run_meta(self, mineru_run_meta: Any) -> None:
        self._last_mineru_run_meta = dict(mineru_run_meta or {})

    def get_last_mineru_run_meta(self) -> Dict[str, Any]:
        return dict(self._last_mineru_run_meta or {})

    def get_last_parse_stats(self) -> Dict[str, Any]:
        stats = dict(self._last_parse_stats)
        if self._last_mineru_run_meta:
            stats["mineru_run"] = dict(self._last_mineru_run_meta)
        return stats
