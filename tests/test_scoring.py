from core.config import Settings
from core.models import (
    JevJudgment,
    QuestionJudgment,
    Requirement,
    RequirementKind,
)
from core.scoring import score_match


def requirements():
    return [
        Requirement(id="r1", text="Python", kind=RequirementKind.MUST_HAVE, weight=3),
        Requirement(id="r2", text="FastAPI", kind=RequirementKind.SKILL, weight=2),
    ]


def judgment(must_have=0.9, skill=3, confidence=0.9, is_resume=0.99):
    return JevJudgment(
        answers={
            "is_resume": QuestionJudgment(value=is_resume),
            "seniority": QuestionJudgment(value="senior", confidence=0.8),
            "r1": QuestionJudgment(value=must_have),
            "r2": QuestionJudgment(value=skill, confidence=confidence),
        },
        model="jev-1.13.0",
    )


def test_weighted_score_is_plain_code():
    result = score_match(
        resume_name="candidate.txt", requirements=requirements(), judgment=judgment()
    )
    assert result.match_score == 84.0
    assert result.verdict == "strong_match"
    assert result.seniority == "senior"


def test_missing_must_have_caps_score():
    result = score_match(
        resume_name="candidate.txt",
        requirements=requirements(),
        judgment=judgment(must_have=0.2, skill=4),
    )
    assert result.match_score == 50.0
    assert result.missing_must_haves == ["Python"]


def test_uncertainty_routes_to_human_review():
    settings = Settings()
    result = score_match(
        resume_name="candidate.txt",
        requirements=requirements(),
        judgment=judgment(must_have=0.5),
        settings=settings,
    )
    assert result.requires_human_review is True
    assert result.verdict == "needs_human_review"


def test_low_score_confidence_routes_to_review():
    result = score_match(
        resume_name="candidate.txt",
        requirements=requirements(),
        judgment=judgment(confidence=0.3),
    )
    assert result.requires_human_review is True
