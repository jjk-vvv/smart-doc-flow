from __future__ import annotations

import re

from .text_utils import normalize_markdown_text, repair_text


class Assistant1MarkdownCleaner:
    def clean(self, markdown_text: str) -> str:
        text = normalize_markdown_text(markdown_text)
        lines = [line.rstrip() for line in text.splitlines()]

        cleaned: list[str] = []
        previous_norm = ""
        blank_streak = 0
        for raw_line in lines:
            line = repair_text(raw_line)
            if line.startswith("<!--") and line.endswith("-->"):
                continue
            norm = re.sub(r"\s+", " ", line).strip()
            if not norm:
                blank_streak += 1
                if blank_streak <= 1:
                    cleaned.append("")
                continue

            blank_streak = 0
            if norm == previous_norm and not norm.startswith("|"):
                continue
            previous_norm = norm
            cleaned.append(self._clean_inline_spacing(line))

        result = "\n".join(cleaned).strip()
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result + "\n"

    def _clean_inline_spacing(self, line: str) -> str:
        if line.startswith("|"):
            return line
        line = re.sub(r"[ \t]{2,}", " ", line)
        line = re.sub(r"\s+([,.;:!?])", r"\1", line)
        line = re.sub(r"([（(])\s+", r"\1", line)
        line = re.sub(r"\s+([）)])", r"\1", line)
        return line.strip()
