from datetime import datetime

from pydantic import BaseModel, Field

from core.models import HardConstraints, MatchResult, Requirement


class ResumeResponse(BaseModel):
    id: str
    name: str
    filename: str
    size_bytes: int
    created_at: datetime


class InlineResume(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=200_000)


class RenameResumeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class JDFetchRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2_048)


class JDTextResponse(BaseModel):
    text: str


class RequirementRequest(BaseModel):
    jd_text: str = Field(min_length=1, max_length=2_000_000)


class MatchRequest(BaseModel):
    resume_ids: list[str] = Field(default_factory=list, max_length=100)
    resumes: list[InlineResume] = Field(default_factory=list, max_length=100)
    jd_text: str | None = Field(default=None, max_length=2_000_000)
    requirements: list[Requirement] | None = None
    hard_constraints: HardConstraints = Field(default_factory=HardConstraints)
    include_evidence: bool = True


class MatchResponse(BaseModel):
    results: list[MatchResult]
