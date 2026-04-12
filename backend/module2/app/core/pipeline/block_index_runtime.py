from __future__ import annotations

import re
from typing import Any, Dict, List


BlockItems = List[Dict[str, Any]]


class BlockIndexRuntime:
    """Allocate stable sequential ids for extracted table and figure blocks."""

    @staticmethod
    def next_table_index(table_blocks: BlockItems, prefix: str) -> int:
        return BlockIndexRuntime._next_index(table_blocks, "table_id", prefix)

    @staticmethod
    def next_figure_index(figure_blocks: BlockItems, prefix: str) -> int:
        return BlockIndexRuntime._next_index(figure_blocks, "figure_id", prefix)

    @staticmethod
    def _next_index(blocks: BlockItems, field_name: str, prefix: str) -> int:
        max_idx = 0
        for block in blocks:
            block_id = str(block.get(field_name, ""))
            if not block_id.startswith(prefix):
                continue
            match = re.search(r"(\d+)$", block_id)
            if not match:
                continue
            try:
                max_idx = max(max_idx, int(match.group(1)))
            except ValueError:
                continue
        return max_idx + 1
