from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Module1SchemaModel(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class OfficePreviewPayload(Module1SchemaModel):
    job_id: str
    status: str
    artifact_url: str | None = None
    status_url: str | None = None


class Module1ArtifactPayload(Module1SchemaModel):
    preview_url: str | None = None
    download_url: str | None = None
    expires_at: str | None = None


__all__ = ["Module1ArtifactPayload", "OfficePreviewPayload"]
