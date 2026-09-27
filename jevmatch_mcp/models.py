from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from core.models import MatchResult


class ServerStatus(BaseModel):
    """Non-secret configuration that helps an MCP client choose usable tools."""

    server: Literal["jevmatch"] = "jevmatch"
    version: str
    default_transport: Literal["stdio"] = "stdio"
    jev_model: str
    typesafe_configured: bool
    anthropic_configured: bool
    max_resumes_per_match: int
    max_requirements_per_match: int
    supported_resume_inputs: list[str] = Field(default_factory=lambda: ["inline_text", "saved_id"])


class SavedResumeSummary(BaseModel):
    """Safe metadata for a resume stored in the local JevMatch library."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    filename: str
    size_bytes: int
    created_at: datetime


class SavedResumeCatalog(BaseModel):
    count: int
    resumes: list[SavedResumeSummary]


class MatchBatchResult(BaseModel):
    count: int
    results: list[MatchResult]
