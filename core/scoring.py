from core.config import Settings, get_settings
from core.models import (
    Gap,
    HardConstraintCheck,
    JevJudgment,
    MatchResult,
    Requirement,
    RequirementKind,
    RequirementResult,
)


def score_match(
    *,
    resume_name: str,
    requirements: list[Requirement],
    judgment: JevJudgment,
    hard_constraint_checks: list[HardConstraintCheck] | None = None,
    resume_id: str | None = None,
    evidence: dict[str, list[str]] | None = None,
    settings: Settings | None = None,
) -> MatchResult:
    settings = settings or get_settings()
    evidence = evidence or {}
    results: list[RequirementResult] = []
    missing: list[str] = []
    needs_review = False

    for requirement in requirements:
        answer = judgment.answers.get(requirement.id)
        if answer is None:
            raise ValueError(f"Jev response is missing requirement answer: {requirement.id}")
        value = float(answer.value)
        normalized = value if requirement.kind == RequirementKind.MUST_HAVE else value / 4
        normalized = max(0.0, min(1.0, normalized))
        results.append(
            RequirementResult(
                requirement=requirement,
                value=value,
                normalized_score=normalized,
                confidence=answer.confidence,
                evidence=evidence.get(requirement.id, []),
                raw_answer=answer.raw,
            )
        )
        if requirement.kind == RequirementKind.MUST_HAVE:
            if normalized < settings.missing_must_have_threshold:
                missing.append(requirement.text)
            elif normalized < settings.uncertain_must_have_threshold:
                needs_review = True
        elif (
            answer.confidence is not None and answer.confidence < settings.low_confidence_threshold
        ):
            needs_review = True

    is_resume = judgment.answers.get("is_resume")
    is_resume_probability = float(is_resume.value) if is_resume else 0.0
    if is_resume_probability < settings.resume_probability_threshold:
        needs_review = True

    total_weight = sum(item.requirement.weight for item in results)
    weighted = sum(item.normalized_score * item.requirement.weight for item in results)
    score = (weighted / total_weight * 100) if total_weight else 0.0
    if missing:
        score = min(score, settings.must_have_score_cap)

    checks = hard_constraint_checks or []
    if any(check.passed is False for check in checks):
        needs_review = True

    if needs_review:
        verdict = "needs_human_review"
    elif score >= settings.strong_match_threshold:
        verdict = "strong_match"
    elif score >= settings.partial_match_threshold:
        verdict = "partial_match"
    else:
        verdict = "weak_match"

    gaps = sorted(
        [
            Gap(
                requirement_id=item.requirement.id,
                requirement=item.requirement.text,
                impact=round(item.requirement.weight * (1 - item.normalized_score), 3),
            )
            for item in results
        ],
        key=lambda gap: gap.impact,
        reverse=True,
    )
    seniority = judgment.answers.get("seniority")
    return MatchResult(
        resume_id=resume_id,
        resume_name=resume_name,
        match_score=round(score, 1),
        verdict=verdict,
        requires_human_review=needs_review,
        missing_must_haves=missing,
        gaps=gaps,
        requirement_results=results,
        hard_constraint_checks=checks,
        seniority=str(seniority.value) if seniority else None,
        is_resume_probability=is_resume_probability,
        raw_jev_answers=judgment.raw_answers,
        token_usage=judgment.usage,
        latency_ms=round(judgment.latency_ms, 1),
        model_version=judgment.model,
    )
