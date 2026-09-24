import base64
import binascii
import re
import unicodedata
from dataclasses import dataclass, field

_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "instruction_override",
        re.compile(
            r"\b(?:ignore|disregard|forget|override|bypass)\b.{0,80}"
            r"\b(?:previous|prior|above|system|developer|instructions?|rules?|prompt)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "role_impersonation",
        re.compile(
            r"(?:<\|\s*(?:system|assistant|developer)\s*\|>|\[/?INST\]|"
            r"\b(?:system|developer|assistant)\s+(?:message|prompt|instructions?)\s*:)",
            re.IGNORECASE,
        ),
    ),
    (
        "instruction_evasion",
        re.compile(
            r"\b(?:do\s+not|don't)\b.{0,40}\b(?:follow|obey|use)\b.{0,30}"
            r"\b(?:instructions?|rules?|criteria)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "score_manipulation",
        re.compile(
            r"\b(?:give|assign|return|output|award|set)\b.{0,50}"
            r"\b(?:perfect|highest|maximum|100(?:\s*(?:%|/\s*100))?)\b.{0,30}"
            r"\b(?:score|rank|rating|match)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "prompt_exfiltration",
        re.compile(
            r"\b(?:reveal|print|repeat|show|expose)\b.{0,50}"
            r"\b(?:system|developer|hidden)\b.{0,20}\b(?:prompt|instructions?|message)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
)

_BASE64_CANDIDATE = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{40,}={0,2}(?![A-Za-z0-9+/=])")


@dataclass(slots=True)
class ResumeSecurityScan:
    suspicious: bool
    flags: list[str] = field(default_factory=list)


def sanitize_extracted_text(text: str) -> tuple[str, list[str]]:
    """Normalize text and remove Unicode controls that can hide or reorder instructions."""
    normalized = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    output: list[str] = []
    removed_format = 0
    removed_control = 0
    for character in normalized:
        category = unicodedata.category(character)
        if category == "Cf":
            removed_format += 1
            continue
        if category == "Cc" and character not in {"\n", "\t"}:
            removed_control += 1
            continue
        output.append(character)

    flags: list[str] = []
    if removed_format:
        flags.append("unicode_format_controls_removed")
    if removed_control:
        flags.append("control_characters_removed")
    return "".join(output), flags


def _pattern_flags(text: str) -> list[str]:
    return [name for name, pattern in _INJECTION_PATTERNS if pattern.search(text)]


def scan_resume_for_prompt_injection(text: str) -> ResumeSecurityScan:
    """Find high-signal instructions aimed at manipulating an automated evaluator."""
    normalized, _ = sanitize_extracted_text(text)
    flags = _pattern_flags(normalized)

    for candidate in _BASE64_CANDIDATE.findall(normalized):
        try:
            padding = "=" * (-len(candidate) % 4)
            decoded = base64.b64decode(candidate + padding, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            continue
        if _pattern_flags(decoded):
            flags.append("encoded_instruction_like_text")
            break

    unique_flags = list(dict.fromkeys(flags))
    return ResumeSecurityScan(suspicious=bool(unique_flags), flags=unique_flags)
