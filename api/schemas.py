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
    text: str = Field(min_length=1)


class RenameResumeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class JDFetchRequest(BaseModel):
    url: str


class JDTextResponse(BaseModel):
    text: str


class RequirementRequest(BaseModel):
    jd_text: str = Field(min_length=1)


class MatchRequest(BaseModel):
    resume_ids: list[str] = Field(default_factory=list)
    resumes: list[InlineResume] = Field(default_factory=list)
    jd_text: str | None = None
    requirements: list[Requirement] | None = None
    hard_constraints: HardConstraints = Field(default_factory=HardConstraints)
    include_evidence: bool = True


class MatchResponse(BaseModel):
    results: list[MatchResult]
