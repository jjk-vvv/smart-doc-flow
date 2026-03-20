from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Assistant1HistoryMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: Literal["system", "user", "assistant", "developer"] = "user"
    content: str = Field(default="", max_length=20000)


class Assistant1ClientCaps(BaseModel):
    model_config = ConfigDict(extra="ignore")

    supports_replace: bool = True


class Assistant1ChatStreamRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    message: str = Field(..., min_length=1, max_length=8000)
    session_id: Optional[str] = Field(default=None, max_length=128)
    file_hash: str = Field(default="", max_length=128)
    history: List[Assistant1HistoryMessage] = Field(default_factory=list, max_length=24)
    top_k: int = Field(default=5, ge=1, le=8)
    max_steps: int = Field(default=6, ge=1, le=10)
    debug: bool = False
    resume_run_id: str = Field(default="", max_length=128)
    after_seq: int = Field(default=0, ge=0)
    client_caps: Assistant1ClientCaps = Field(default_factory=Assistant1ClientCaps)
    extra_context: Dict[str, Any] = Field(default_factory=dict)
