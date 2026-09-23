import asyncio

from core.config import Settings, get_settings
from core.facts import compare_hard_constraints, extract_resume_facts
from core.jev import JevJudge
from core.models import ExtractedRequirements, MatchResult, ResumeDocument
from core.scoring import score_match


class MatchPipeline:
    def __init__(self, settings: Settings | None = None, judge: JevJudge | None = None):
        self.settings = settings or get_settings()
        self.judge = judge or JevJudge(self.settings)

    async def match(
        self,
        resume: ResumeDocument,
        extracted: ExtractedRequirements,
        *,
        resume_id: str | None = None,
        include_evidence: bool = True,
    ) -> MatchResult:
        judgment = await self.judge.judge(resume.redacted_text, extracted.requirements)
        evidence = (
            await self.judge.evidence(resume.redacted_text, extracted.requirements)
            if include_evidence
            else {}
        )
        facts = extract_resume_facts(resume.text)
        checks = compare_hard_constraints(facts, extracted.hard_constraints)
        return score_match(
            resume_name=resume.name,
            resume_id=resume_id,
            requirements=extracted.requirements,
            judgment=judgment,
            hard_constraint_checks=checks,
            evidence=evidence,
            settings=self.settings,
        )

    async def match_many(
        self,
        resumes: list[tuple[str | None, ResumeDocument]],
        extracted: ExtractedRequirements,
        *,
        include_evidence: bool = True,
    ) -> list[MatchResult]:
        results = await asyncio.gather(
            *(
                self.match(
                    document,
                    extracted,
                    resume_id=resume_id,
                    include_evidence=include_evidence,
                )
                for resume_id, document in resumes
            )
        )
        return sorted(results, key=lambda result: result.match_score, reverse=True)
