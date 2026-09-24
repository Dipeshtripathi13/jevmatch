import json
from pathlib import Path

import pytest
from typesafe_sdk import SystemOneResponse, TypeSafeAPIConnectionError

from core.config import Settings
from core.jev import JevEvaluationError, JevJudge
from core.models import Requirement, RequirementKind


class MockJevClient:
    async def system_one(self, state, questions):
        assert "candidate@example.com" not in state["resume_text"]
        fixture = json.loads(Path("tests/fixtures/jev_response.json").read_text())
        fixture["answers"] = {key: fixture["answers"][key] for key in questions}
        return SystemOneResponse.model_validate_json(json.dumps(fixture))


class MockPreflightClient:
    def __init__(self):
        self.state = None
        self.questions = None

    async def system_one(self, state, questions):
        self.state = state
        self.questions = questions
        return SystemOneResponse.model_validate(
            {
                "model": "jev-1.13.0",
                "answers": {
                    "is_resume": {"type": "noul", "noul": 0.96},
                    "prompt_injection": {"type": "noul", "noul": 0.03},
                },
                "usage": {"input_tokens": 40, "output_tokens": 4},
            }
        )


class FailingJevClient:
    async def system_one(self, state, questions):
        raise TypeSafeAPIConnectionError("offline")


class MockSemanticEvidenceClient:
    def __init__(self):
        self.calls = []

    async def system_one(self, state, questions):
        self.calls.append((state, questions))
        answers = {}
        state_text = state.get("tagged_resume_passages", state.get("resume_text", ""))
        passages = dict(line.split("| ", 1) for line in state_text.splitlines() if "| " in line)
        passage_ids = list(passages)
        for key, question in questions.items():
            if key.startswith("where_"):
                target = next(
                    (
                        passage_id
                        for passage_id in passage_ids
                        if "RAG assistant" in passages[passage_id]
                    ),
                    passage_ids[0],
                )
                other_probability = 0.1 / max(1, len(passage_ids) - 1)
                probabilities = {
                    passage_id: 0.9 if passage_id == target else other_probability
                    for passage_id in passage_ids
                }
                if len(passage_ids) == 1:
                    probabilities[target] = 1.0
                answers[key] = {
                    "type": "choice",
                    "choice": target,
                    "confidence": 0.9,
                    "probabilities": probabilities,
                }
            elif key.startswith("exists_"):
                answers[key] = {
                    "type": "noul",
                    "noul": 0.95 if key.startswith("exists_r1_") else 0.05,
                }
            elif key.startswith("verify_"):
                candidate = question.instructions["candidate_passage"]
                answers[key] = {
                    "type": "noul",
                    "noul": 0.92 if "RAG assistant" in candidate else 0.1,
                }
        return SystemOneResponse.model_validate(
            {
                "model": "jev-1.13.0",
                "answers": answers,
                "usage": {"input_tokens": 100, "output_tokens": 20},
            }
        )


@pytest.mark.asyncio
async def test_mocked_jev_response_matches_real_shape():
    judge = JevJudge(Settings(), client=MockJevClient())
    result = await judge.judge(
        "[EMAIL REDACTED]\nSenior engineer",
        [
            Requirement(id="r1", text="Python", kind=RequirementKind.MUST_HAVE, weight=3),
            Requirement(id="r2", text="FastAPI", kind=RequirementKind.SKILL, weight=2),
        ],
    )
    assert result.answers["r1"].value == 0.94
    assert result.answers["r2"].value == 3
    assert result.usage["input_tokens"] == 520


@pytest.mark.asyncio
async def test_preflight_structures_resume_as_untrusted_data():
    client = MockPreflightClient()
    judge = JevJudge(Settings(), client=client)

    result = await judge.preflight("Software engineer with Python experience")

    assert result.answers["is_resume"].value == 0.96
    assert result.answers["prompt_injection"].value == 0.03
    assert client.state["document_type"] == "untrusted_resume_candidate_evidence"
    assert client.state["resume_text"].startswith("Software engineer")
    assert "untrusted" in client.state["security_rule"]
    assert set(client.questions) == {"is_resume", "prompt_injection"}


@pytest.mark.asyncio
async def test_connection_failure_becomes_safe_domain_error():
    judge = JevJudge(Settings(), client=FailingJevClient())

    with pytest.raises(JevEvaluationError, match="Could not connect to TypeSafe"):
        await judge.preflight("Software engineer with Python experience")


def test_fixture_validates_as_sdk_response():
    payload = Path("tests/fixtures/jev_response.json").read_text()
    response = SystemOneResponse.model_validate_json(payload)
    assert response.scores["r2"].score == 3


@pytest.mark.asyncio
async def test_evidence_uses_semantic_retrieval_then_verifies_verbatim_lines():
    client = MockSemanticEvidenceClient()
    judge = JevJudge(Settings(), client=client)
    semantic_line = "Built a RAG assistant used by clinicians."
    evidence = await judge.evidence(
        "\n".join(
            [
                "Machine learning engineer",
                semantic_line,
                "Maintained deployment pipelines.",
            ]
        ),
        [
            Requirement(
                id="r1",
                text="Retrieval-augmented generation systems",
                kind=RequirementKind.SKILL,
                weight=3,
            ),
            Requirement(
                id="r2",
                text="Kubernetes cluster administration",
                kind=RequirementKind.SKILL,
                weight=2,
            ),
        ],
    )

    assert evidence == {"r1": [semantic_line]}
    assert len(client.calls) == 2
    retrieval_state, retrieval_questions = client.calls[0]
    assert "L001| Built a RAG assistant" in retrieval_state["tagged_resume_passages"]
    assert retrieval_state["document_type"] == "untrusted_tagged_resume_passages"
    assert "where_r1_0" in retrieval_questions
    assert (
        "Retrieval-augmented generation"
        in retrieval_questions["where_r1_0"].instructions["requirement"]
    )
    assert all(
        not key.startswith("verify_r2_") for _, questions in client.calls for key in questions
    )


@pytest.mark.asyncio
async def test_evidence_skips_choice_when_resume_has_one_searchable_line():
    client = MockSemanticEvidenceClient()
    judge = JevJudge(Settings(), client=client)
    semantic_line = "Built a RAG assistant used by clinicians."

    evidence = await judge.evidence(
        semantic_line,
        [
            Requirement(
                id="r1",
                text="Retrieval-augmented generation systems",
                kind=RequirementKind.SKILL,
                weight=3,
            )
        ],
    )

    assert evidence == {"r1": [semantic_line]}
    assert set(client.calls[0][1]) == {"exists_r1_0"}
