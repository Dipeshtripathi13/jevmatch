import json
from pathlib import Path

import pytest
from typesafe_sdk import SystemOneResponse

from core.config import Settings
from core.jev import JevJudge
from core.models import Requirement, RequirementKind


class MockJevClient:
    async def system_one(self, state, questions):
        assert "candidate@example.com" not in state
        fixture = json.loads(Path("tests/fixtures/jev_response.json").read_text())
        fixture["answers"] = {key: fixture["answers"][key] for key in questions}
        return SystemOneResponse.model_validate_json(json.dumps(fixture))


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


def test_fixture_validates_as_sdk_response():
    payload = Path("tests/fixtures/jev_response.json").read_text()
    response = SystemOneResponse.model_validate_json(payload)
    assert response.scores["r2"].score == 3
