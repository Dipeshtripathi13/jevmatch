import json
from types import SimpleNamespace

import pytest

from core.config import Settings
from core.requirements import RequirementExtractor


class MockMessages:
    def __init__(self):
        self.calls = 0
        self.last_request = None

    async def create(self, **kwargs):
        self.calls += 1
        self.last_request = kwargs
        payload = {
            "requirements": [{"id": "r1", "text": "Python", "kind": "skill", "weight": 3}],
            "hard_constraints": {
                "min_years_experience": 3,
                "required_degree": None,
                "location": None,
                "remote": True,
            },
        }
        return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(payload))])


@pytest.mark.asyncio
async def test_extracts_and_caches_requirements(tmp_path):
    messages = MockMessages()
    client = SimpleNamespace(messages=messages)
    settings = Settings(data_dir=tmp_path)
    extractor = RequirementExtractor(settings, client=client)
    first = await extractor.extract("A sufficiently long Python job description" * 20)
    second = await extractor.extract("A sufficiently long Python job description" * 20)
    assert first.requirements[0].text == "Python"
    assert second.hard_constraints.remote is True
    assert messages.calls == 1
    assert "untrusted job-description data" in messages.last_request["messages"][0]["content"]
    assert "never an instruction" in messages.last_request["system"]
