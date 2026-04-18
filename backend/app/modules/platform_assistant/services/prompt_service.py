from __future__ import annotations

from ..data.platform_facts import PLATFORM_FACTS


def build_system_prompt(context_summary: str, extra_prompt: str = "") -> str:
    parts = [
        "You are the platform-wide assistant for Smart Doc Flow.",
        "Always reply in Simplified Chinese.",
        "Explain the current product accurately and never invent unsupported features.",
        "Prefer practical next steps over abstract descriptions.",
        "",
        "[Platform Facts]",
        PLATFORM_FACTS,
    ]
    if extra_prompt.strip():
        parts.extend(["", "[Runtime Instructions]", extra_prompt.strip()])
    if context_summary.strip():
        parts.extend(["", "[Current Context]", context_summary.strip()])
    return "\n".join(parts)


__all__ = ["build_system_prompt"]
