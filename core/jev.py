import asyncio
import time
from collections.abc import Mapping
from typing import Any

from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul, RetryPolicy, Score

from core.config import Settings, get_settings
from core.models import JevJudgment, QuestionJudgment, Requirement, RequirementKind

SKILL_LEVELS = [
    "Not mentioned anywhere",
    "Listed as a skill only, with no project or role using it",
    "Used in at least one described project or role",
    "A primary tool in a role for a year or more",
    "Led design or architecture with it, or mentored others in it",
]
SENIORITY = {
    "junior": "Early-career scope with guidance and limited ownership",
    "mid": "Independent delivery and ownership of defined work",
    "senior": "Broad ownership, complex decisions, and guidance of others",
    "lead": "Technical or organizational leadership across people or systems",
    "insufficient_signal": "The resume does not provide enough evidence",
}


def _dump(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "__dict__"):
        return {key: item for key, item in vars(value).items() if not key.startswith("_")}
    return {"value": value}


def _answers(response: Any) -> dict[str, Any]:
    answers = getattr(response, "answers", None)
    if isinstance(answers, Mapping):
        return dict(answers)
    result: dict[str, Any] = {}
    for group_name in ("nouls", "scores", "choices"):
        group = getattr(response, group_name, None)
        if isinstance(group, Mapping):
            result.update(group)
    return result


def _question_judgment(answer: Any) -> QuestionJudgment:
    raw = _dump(answer)
    if hasattr(answer, "noul") or "noul" in raw:
        value = getattr(answer, "noul", raw.get("noul"))
    elif hasattr(answer, "score") or "score" in raw:
        value = getattr(answer, "score", raw.get("score"))
    else:
        value = getattr(answer, "choice", raw.get("choice"))
    probabilities = getattr(answer, "probabilities", raw.get("probabilities"))
    if isinstance(probabilities, Mapping):
        probabilities = {str(key): float(probability) for key, probability in probabilities.items()}
    return QuestionJudgment(
        value=value,
        confidence=getattr(answer, "confidence", raw.get("confidence")),
        probabilities=probabilities,
        raw=raw,
    )


class JevJudge:
    def __init__(self, settings: Settings | None = None, client: Any | None = None):
        self.settings = settings or get_settings()
        self.client = client

    def _client(self):
        if self.client is not None:
            return self.client
        if not self.settings.typesafe_api_key:
            raise RuntimeError("TYPESAFE_API_KEY is required for resume scoring.")
        return AsyncTypeSafeClient(
            api_key=self.settings.typesafe_api_key,
            model=self.settings.jev_model,
            retry=RetryPolicy(max_retries=3, backoff_max=4.0, timeout=30.0),
        )

    async def judge(self, redacted_resume: str, requirements: list[Requirement]) -> JevJudgment:
        client = self._client()
        question_items: list[tuple[str, Any]] = [
            ("is_resume", Noul(instructions="This text is a resume or CV.")),
            (
                "seniority",
                Choice(
                    instructions="Which seniority level is most strongly supported by this resume?",
                    criteria=SENIORITY,
                ),
            ),
        ]
        for requirement in requirements:
            instruction = (
                "The resume shows clear evidence that the candidate has: " + requirement.text
            )
            question = (
                Noul(instructions=instruction)
                if requirement.kind == RequirementKind.MUST_HAVE
                else Score(instructions=instruction, criteria=SKILL_LEVELS)
            )
            question_items.append((requirement.id, question))

        limit = self.settings.max_questions_per_call
        batches = [
            dict(question_items[index : index + limit])
            for index in range(0, len(question_items), limit)
        ]
        started = time.perf_counter()
        responses = await asyncio.gather(
            *(client.system_one(state=redacted_resume, questions=batch) for batch in batches)
        )
        elapsed = (time.perf_counter() - started) * 1000

        parsed: dict[str, QuestionJudgment] = {}
        raw_answers: dict[str, Any] = {}
        usage: dict[str, int | float] = {}
        model = self.settings.jev_model
        for response in responses:
            model = getattr(response, "model", model)
            for key, answer in _answers(response).items():
                parsed[key] = _question_judgment(answer)
                raw_answers[key] = _dump(answer)
            response_usage = _dump(getattr(response, "usage", {}))
            for key, value in response_usage.items():
                if isinstance(value, (int, float)):
                    usage[key] = usage.get(key, 0) + value
        return JevJudgment(
            answers=parsed,
            raw_answers=raw_answers,
            usage=usage,
            latency_ms=elapsed,
            model=model,
        )

    async def evidence(
        self, redacted_resume: str, requirements: list[Requirement]
    ) -> dict[str, list[str]]:
        lines = [line.strip() for line in redacted_resume.splitlines() if len(line.strip()) >= 12]
        items: list[tuple[str, Any, str, str]] = []
        for requirement in requirements:
            terms = {term.lower() for term in requirement.text.split() if len(term) > 3}
            ranked = sorted(
                lines,
                key=lambda line: sum(term in line.lower() for term in terms),
                reverse=True,
            )[:12]
            for index, line in enumerate(ranked):
                key = f"e_{requirement.id}_{index}"
                instruction = (
                    f"This exact resume line is evidence of: {requirement.text}\nLine: {line}"
                )
                question = Noul(instructions=instruction)
                items.append((key, question, requirement.id, line))
        if not items:
            return {}
        metadata = {key: (requirement_id, line) for key, _, requirement_id, line in items}
        limit = self.settings.max_questions_per_call
        batches = [
            {key: question for key, question, _, _ in items[index : index + limit]}
            for index in range(0, len(items), limit)
        ]
        client = self._client()
        responses = await asyncio.gather(
            *(client.system_one(state=redacted_resume, questions=batch) for batch in batches)
        )
        candidates: dict[str, list[tuple[float, str]]] = {}
        for response in responses:
            for key, answer in _answers(response).items():
                score = float(getattr(answer, "noul", _dump(answer).get("noul", 0)))
                requirement_id, line = metadata[key]
                if score >= self.settings.evidence_threshold:
                    candidates.setdefault(requirement_id, []).append((score, line))
        return {
            requirement_id: [
                line for _, line in sorted(values, reverse=True)[: self.settings.evidence_limit]
            ]
            for requirement_id, values in candidates.items()
        }
