import os

import pytest

from core.config import Settings
from core.jev import JevJudge
from core.models import Requirement, RequirementKind


@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv("RUN_LIVE_TESTS") != "1", reason="set RUN_LIVE_TESTS=1")
async def test_live_jev_smoke():
    result = await JevJudge(Settings()).judge(
        "Software engineer. Built Python services from 2020 to 2024.",
        [Requirement(id="r1", text="Python", kind=RequirementKind.SKILL, weight=1)],
    )
    assert result.model
    assert 0 <= float(result.answers["is_resume"].value) <= 1
