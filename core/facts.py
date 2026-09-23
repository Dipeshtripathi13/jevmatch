import calendar
import re
from datetime import date

from core.models import HardConstraintCheck, HardConstraints, ResumeFacts

MONTHS = {name.lower(): number for number, name in enumerate(calendar.month_name) if name}
MONTHS.update({name.lower(): number for number, name in enumerate(calendar.month_abbr) if name})
MONTH_TOKEN = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
    r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
DATE_RANGE_RE = re.compile(
    rf"(?P<start_month>{MONTH_TOKEN})?\s*(?P<start_year>(?:19|20)\d{{2}})\s*"
    rf"(?:-|–|—|to)\s*(?:(?P<end_month>{MONTH_TOKEN})?\s*"
    rf"(?P<end_year>(?:19|20)\d{{2}})|(?P<present>present|current|now))",
    re.IGNORECASE,
)

DEGREE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("doctorate", re.compile(r"\b(?:ph\.?d\.?|doctor(?:ate| of philosophy))\b", re.I)),
    ("master", re.compile(r"\b(?:m\.?s\.?|m\.?a\.?|mba|master(?:'s)?|mtech)\b", re.I)),
    ("bachelor", re.compile(r"\b(?:b\.?s\.?|b\.?a\.?|bachelor(?:'s)?|btech)\b", re.I)),
    ("associate", re.compile(r"\b(?:a\.?s\.?|a\.?a\.?|associate(?:'s)?)\b", re.I)),
]
DEGREE_RANK = {"associate": 1, "bachelor": 2, "master": 3, "doctorate": 4}


def _month_index(year: int, month: int) -> int:
    return year * 12 + month - 1


def _parse_month(value: str | None, default: int) -> int:
    if not value:
        return default
    return MONTHS[value.lower()[:3]]


def experience_months(text: str, today: date | None = None) -> int | None:
    """Return unioned months across explicit resume date ranges, avoiding overlap."""
    today = today or date.today()
    occupied: set[int] = set()
    for match in DATE_RANGE_RE.finditer(text):
        start_year = int(match.group("start_year"))
        start_month = _parse_month(match.group("start_month"), 1)
        if match.group("present"):
            end_year, end_month = today.year, today.month
        else:
            end_year = int(match.group("end_year"))
            end_month = _parse_month(match.group("end_month"), 12)
        start = _month_index(start_year, start_month)
        end = _month_index(end_year, end_month)
        if end < start or start_year < 1950 or end_year > today.year + 1:
            continue
        occupied.update(range(start, end + 1))
    return len(occupied) if occupied else None


def detect_degree(text: str) -> str | None:
    for degree, pattern in DEGREE_PATTERNS:
        if pattern.search(text):
            return degree
    return None


def extract_resume_facts(text: str, today: date | None = None) -> ResumeFacts:
    months = experience_months(text, today)
    return ResumeFacts(
        total_years_experience=round(months / 12, 1) if months is not None else None,
        degree_level=detect_degree(text),
    )


def compare_hard_constraints(
    facts: ResumeFacts, constraints: HardConstraints
) -> list[HardConstraintCheck]:
    checks: list[HardConstraintCheck] = []
    if constraints.min_years_experience is not None:
        observed = facts.total_years_experience
        checks.append(
            HardConstraintCheck(
                constraint="minimum experience",
                required=f"{constraints.min_years_experience:g} years",
                observed=f"{observed:g} years" if observed is not None else None,
                passed=(observed >= constraints.min_years_experience)
                if observed is not None
                else None,
            )
        )
    if constraints.required_degree:
        observed_degree = facts.degree_level
        checks.append(
            HardConstraintCheck(
                constraint="degree",
                required=constraints.required_degree,
                observed=observed_degree,
                passed=(DEGREE_RANK[observed_degree] >= DEGREE_RANK[constraints.required_degree])
                if observed_degree
                else None,
            )
        )
    if constraints.location:
        checks.append(
            HardConstraintCheck(
                constraint="location",
                required=constraints.location,
                observed=None,
                passed=None,
            )
        )
    if constraints.remote is not None:
        checks.append(
            HardConstraintCheck(
                constraint="remote arrangement",
                required="remote" if constraints.remote else "on-site/hybrid",
                observed=None,
                passed=None,
            )
        )
    return checks
