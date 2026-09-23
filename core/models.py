from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class RequirementKind(StrEnum):
    MUST_HAVE = "must_have"
    SKILL = "skill"
    NICE_TO_HAVE = "nice_to_have"


class Requirement(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    text: str = Field(min_length=2, max_length=500)
    kind: RequirementKind
    weight: int = Field(default=1, ge=1, le=3)


class HardConstraints(BaseModel):
    min_years_experience: float | None = Field(default=None, ge=0, le=80)
    required_degree: Literal["associate", "bachelor", "master", "doctorate"] | None = None
    location: str | None = Field(default=None, max_length=200)
    remote: bool | None = None


class ExtractedRequirements(BaseModel):
    requirements: list[Requirement]
    hard_constraints: HardConstraints = Field(default_factory=HardConstraints)

    @field_validator("requirements")
    @classmethod
    def unique_ids(cls, value: list[Requirement]) -> list[Requirement]:
        ids = [item.id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("requirement ids must be unique")
        return value


class ResumeDocument(BaseModel):
    name: str
    text: str
    redacted_text: str
    size_bytes: int
    source_path: str | None = None


class ResumeFacts(BaseModel):
    total_years_experience: float | None = None
    degree_level: Literal["associate", "bachelor", "master", "doctorate"] | None = None


class QuestionJudgment(BaseModel):
    value: float | str
    confidence: float | None = None
    probabilities: dict[str, float] | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class JevJudgment(BaseModel):
    answers: dict[str, QuestionJudgment]
    raw_answers: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, int | float] = Field(default_factory=dict)
    latency_ms: float = 0
    model: str


class RequirementResult(BaseModel):
    requirement: Requirement
    value: float
    normalized_score: float = Field(ge=0, le=1)
    confidence: float | None = None
    evidence: list[str] = Field(default_factory=list)
    raw_answer: dict[str, Any] = Field(default_factory=dict)


class Gap(BaseModel):
    requirement_id: str
    requirement: str
    impact: float


class HardConstraintCheck(BaseModel):
    constraint: str
    required: str
    observed: str | None
    passed: bool | None


class MatchResult(BaseModel):
    resume_id: str | None = None
    resume_name: str
    match_score: float = Field(ge=0, le=100)
    verdict: Literal["strong_match", "partial_match", "weak_match", "needs_human_review"]
    requires_human_review: bool
    missing_must_haves: list[str] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    requirement_results: list[RequirementResult]
    hard_constraint_checks: list[HardConstraintCheck] = Field(default_factory=list)
    seniority: str | None = None
    is_resume_probability: float
    raw_jev_answers: dict[str, Any] = Field(default_factory=dict)
    token_usage: dict[str, int | float] = Field(default_factory=dict)
    latency_ms: float = 0
    model_version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
