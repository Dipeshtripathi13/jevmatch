import re

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?\d{1,3}[\s.()-]*)?(?:\(?\d{3}\)?[\s.-]*)\d{3}[\s.-]*\d{4}(?!\w)"
)
URL_RE = re.compile(r"\b(?:https?://|www\.|linkedin\.com/|github\.com/)\S+", re.IGNORECASE)
ADDRESS_RE = re.compile(
    r"(?im)^\s*\d{1,6}\s+[A-Za-z0-9.' -]{2,60}\s+"
    r"(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|drive|dr|court|ct|way)"
    r"(?:\s+(?:apt|unit|#)\s*\w+)?(?:,?\s+[^\n]{2,45})?$"
)
NAME_RE = re.compile(r"^[A-Z][A-Za-z'’-]*(?:\.?\s+[A-Z][A-Za-z'’-]*){1,3}\.?$")
TITLE_WORDS = {
    "analyst",
    "architect",
    "consultant",
    "data",
    "designer",
    "developer",
    "director",
    "engineer",
    "junior",
    "lead",
    "manager",
    "principal",
    "product",
    "scientist",
    "senior",
    "software",
    "specialist",
    "staff",
}


def _redact_header_name(lines: list[str]) -> list[str]:
    result = list(lines)
    inspected = 0
    for index, line in enumerate(lines):
        candidate = line.strip()
        if not candidate:
            continue
        inspected += 1
        candidate_words = {word.lower().strip(".") for word in candidate.split()}
        if (
            inspected <= 3
            and NAME_RE.fullmatch(candidate)
            and len(candidate) <= 80
            and not candidate_words.intersection(TITLE_WORDS)
        ):
            result[index] = "[NAME REDACTED]"
            break
        if inspected >= 3:
            break
    return result


def redact_pii(text: str) -> str:
    """Remove common direct identifiers before text leaves the local machine."""
    redacted = "\n".join(_redact_header_name(text.splitlines()))
    redacted = EMAIL_RE.sub("[EMAIL REDACTED]", redacted)
    redacted = PHONE_RE.sub("[PHONE REDACTED]", redacted)
    redacted = URL_RE.sub("[URL REDACTED]", redacted)
    redacted = ADDRESS_RE.sub("[ADDRESS REDACTED]", redacted)
    return redacted
