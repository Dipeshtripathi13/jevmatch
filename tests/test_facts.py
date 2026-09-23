from datetime import date

from core.facts import compare_hard_constraints, detect_degree, experience_months
from core.models import HardConstraints, ResumeFacts


def test_experience_months_unions_overlapping_ranges():
    text = "Role A: Jan 2020 - Dec 2021\nRole B: Jan 2021 - Dec 2022"
    assert experience_months(text, date(2024, 1, 1)) == 36


def test_experience_months_supports_present():
    assert experience_months("Engineer June 2023 to Present", date(2024, 5, 1)) == 12


def test_invalid_date_range_is_ignored():
    assert experience_months("Engineer 2024 - 2020") is None


def test_detects_highest_degree():
    assert detect_degree("Bachelor of Science, then Master of Science") == "master"
    assert detect_degree("No degree stated") is None


def test_hard_constraint_comparison_is_deterministic():
    checks = compare_hard_constraints(
        ResumeFacts(total_years_experience=4.5, degree_level="master"),
        HardConstraints(min_years_experience=5, required_degree="bachelor"),
    )
    assert checks[0].passed is False
    assert checks[1].passed is True
