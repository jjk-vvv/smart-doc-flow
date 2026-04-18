from __future__ import annotations

PLATFORM_FACTS = "\n".join(
    (
        "Product name: Smart Doc Flow.",
        "Module 1 (doc-processing): upload, preview, ask questions, edit, and export documents.",
        "Module 2 (deepread extraction): extract structured fields and validate source positioning.",
        "Module 3 (fusion): fill templates and combine multi-source materials.",
        "Module 4 (knowledge nexus): inspect graph relationships from upstream outputs.",
        "Authentication: registration, login, logout, session handling, reset-password flows.",
        "Assistant responsibility: explain product capabilities, guide next steps, and help troubleshoot workflows without inventing unsupported features.",
    )
)

CHAT_FALLBACK_TEXT = (
    "\u5f53\u524d\u5e73\u53f0\u52a9\u624b\u94fe\u8def\u6682\u65f6\u4e0d\u7a33\u5b9a\uff0c"
    "\u4f60\u53ef\u4ee5\u5148\u6309\u5f53\u524d\u9875\u9762\u7ee7\u7eed\u64cd\u4f5c\uff0c"
    "\u6216\u8005\u544a\u8bc9\u6211\u4f60\u60f3\u5b8c\u6210\u7684\u76ee\u6807\uff0c"
    "\u6211\u4f1a\u7ed9\u4f60\u4e00\u4e2a\u66f4\u5177\u4f53\u7684\u624b\u52a8\u5904\u7406\u8def\u5f84\u3002"
)

__all__ = ["CHAT_FALLBACK_TEXT", "PLATFORM_FACTS"]
