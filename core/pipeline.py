import asyncio

from core.config import Settings, get_settings
from core.facts import compare_hard_constraints, extract_resume_facts
from core.jev import JevJudge
from core.models import ExtractedRequirements, JevJudgment, MatchResult, ResumeDocument
from core.scoring import score_match
from core.security import scan_resume_for_prompt_injection


class MatchPipeline:
    def __init__(self, settings: Settings | None = None, judge: JevJudge | None = None):
        self.settings = settings or get_settings()
        self.judge = judge or JevJudge(self.settings)
        self._resume_semaphore = asyncio.Semaphore(self.settings.max_concurrent_resumes)

    async def match(
        self,
        resume: ResumeDocument,
        extracted: ExtractedRequirements,
        *,
        resume_id: str | None = None,
        include_evidence: bool = True,
    ) -> MatchResult:
        if len(extracted.requirements) > self.settings.max_requirements_per_match:
            raise ValueError(
                "A match may contain at most "
                f"{self.settings.max_requirements_per_match} requirements."
            )
        security_scan = scan_resume_for_prompt_injection(resume.text)
        security_flags = list(dict.fromkeys([*resume.security_flags, *security_scan.flags]))
        if security_scan.suspicious:
            return self._rejected_result(
                resume,
                resume_id=resume_id,
                reasons=["Instruction-like content may be trying to manipulate the evaluator."],
                security_flags=security_flags,
            )

        preflight = await self.judge.preflight(resume.redacted_text)
        is_resume = self._probability(preflight, "is_resume")
        prompt_injection = self._probability(preflight, "prompt_injection")
        rejection_reasons: list[str] = []
        if is_resume is None:
            rejection_reasons.append("The resume-content preflight did not return a valid result.")
        elif is_resume < self.settings.resume_probability_threshold:
            rejection_reasons.append("The uploaded content does not appear to be a resume or CV.")
        if prompt_injection is None:
            rejection_reasons.append(
                "The prompt-injection preflight did not return a valid result."
            )
        elif prompt_injection >= self.settings.prompt_injection_threshold:
            rejection_reasons.append(
                "The document may contain instructions intended to manipulate automated scoring."
            )
            security_flags.append("model_detected_prompt_injection")
        if rejection_reasons:
            return self._rejected_result(
                resume,
                resume_id=resume_id,
                reasons=rejection_reasons,
                security_flags=list(dict.fromkeys(security_flags)),
                preflight=preflight,
                is_resume_probability=is_resume,
                prompt_injection_probability=prompt_injection,
            )

        scoring_judgment = await self.judge.judge(resume.redacted_text, extracted.requirements)
        judgment = JevJudgment(
            answers={**preflight.answers, **scoring_judgment.answers},
            raw_answers={**preflight.raw_answers, **scoring_judgment.raw_answers},
            usage=self._sum_usage(preflight.usage, scoring_judgment.usage),
            latency_ms=preflight.latency_ms + scoring_judgment.latency_ms,
            model=scoring_judgment.model,
        )
        evidence = (
            await self.judge.evidence(resume.redacted_text, extracted.requirements)
            if include_evidence
            else {}
        )
        facts = extract_resume_facts(resume.text)
        checks = compare_hard_constraints(facts, extracted.hard_constraints)
        result = score_match(
            resume_name=resume.name,
            resume_id=resume_id,
            requirements=extracted.requirements,
            judgment=judgment,
            hard_constraint_checks=checks,
            evidence=evidence,
            settings=self.settings,
        )
        result.security_flags = list(dict.fromkeys(security_flags))
        result.prompt_injection_probability = prompt_injection
        return result

    @staticmethod
    def _probability(judgment: JevJudgment, key: str) -> float | None:
        answer = judgment.answers.get(key)
        if answer is None:
            return None
        try:
            return max(0.0, min(1.0, float(answer.value)))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _sum_usage(
        first: dict[str, int | float], second: dict[str, int | float]
    ) -> dict[str, int | float]:
        result = dict(first)
        for key, value in second.items():
            result[key] = result.get(key, 0) + value
        return result

    def _rejected_result(
        self,
        resume: ResumeDocument,
        *,
        resume_id: str | None,
        reasons: list[str],
        security_flags: list[str],
        preflight: JevJudgment | None = None,
        is_resume_probability: float | None = None,
        prompt_injection_probability: float | None = None,
    ) -> MatchResult:
        return MatchResult(
            resume_id=resume_id,
            resume_name=resume.name,
            status="rejected",
            rejection_reasons=reasons,
            security_flags=security_flags,
            verdict="needs_human_review",
            requires_human_review=True,
            is_resume_probability=is_resume_probability,
            prompt_injection_probability=prompt_injection_probability,
            raw_jev_answers=preflight.raw_answers if preflight else {},
            token_usage=preflight.usage if preflight else {},
            latency_ms=round(preflight.latency_ms, 1) if preflight else 0,
            model_version=preflight.model if preflight else self.settings.jev_model,
        )

    async def match_many(
        self,
        resumes: list[tuple[str | None, ResumeDocument]],
        extracted: ExtractedRequirements,
        *,
        include_evidence: bool = True,
    ) -> list[MatchResult]:
        async def match_with_limit(resume_id: str | None, document: ResumeDocument) -> MatchResult:
            async with self._resume_semaphore:
                return await self.match(
                    document,
                    extracted,
                    resume_id=resume_id,
                    include_evidence=include_evidence,
                )

        results = await asyncio.gather(
            *(match_with_limit(resume_id, document) for resume_id, document in resumes)
        )
        return sorted(
            results,
            key=lambda result: (result.status == "scored", result.match_score or 0),
            reverse=True,
        )
