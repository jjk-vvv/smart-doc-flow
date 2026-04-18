from __future__ import annotations

from datetime import datetime
from typing import Any

from . import document_io_support as io_support
from . import interaction_support as interaction


def build_health_response() -> dict[str, Any]:
    agent = interaction._get_agent()
    return {
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "libreoffice_available": io_support._libreoffice_available(),
        "ai_available": agent.available,
        "modules": {
            "office_pdf": True,
            "pypdf2": io_support.PyPDF2 is not None,
            "python_docx": io_support.docx is not None,
            "zhipuai": agent.available,
        },
    }


__all__ = ["build_health_response"]
