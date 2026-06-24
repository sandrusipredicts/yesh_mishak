"""Basic content moderation for user-generated text.

Read-only validation — rejects clearly invalid content, does not mutate input.
This is basic enforcement per ISSUE-052 UGC policy, not full abuse prevention.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

FAKE_NAME_PATTERNS = {
    "test", "testing", "asdf", "qwerty", "fake", "fake field", "xxx",
    "aaa", "bbb", "ccc", "abc", "123", "null", "undefined", "none",
    "delete me", "temp", "tmp",
}

DENIED_TERMS = [
    "נאצי",
    "היטלר",
    "nigger",
    "fuck you",
    "kill yourself",
    "kys",
]

DENIED_PATTERNS = [re.compile(re.escape(t), re.IGNORECASE) for t in DENIED_TERMS]

URL_PATTERN = re.compile(r"https?://\S+", re.IGNORECASE)

REPEATED_CHAR_PATTERN = re.compile(r"(.)\1{7,}")

PHONE_PATTERN = re.compile(
    r"(?<!\d)0\d[\d\-]{6,11}(?!\d)"
    r"|(?<!\d)\+972[\d\-]{7,12}(?!\d)"
)
def _contains_email_like_token(text: str) -> bool:
    tokens = text.split()
    punctuation_to_strip = ".,!?()[]{}<>;:\"'*"
    
    for token in tokens:
        token = token.strip(punctuation_to_strip)
        if not token:
            continue
        
        # Require exactly one '@'
        if token.count('@') != 1:
            continue
            
        local_part, domain_part = token.split('@')
        
        # Require non-empty local part
        if not local_part:
            continue
            
        # Require non-empty domain part
        if not domain_part:
            continue
            
        # Require at least one '.' in the domain
        if '.' not in domain_part:
            continue
            
        # Require final TLD length >= 2
        domain_segments = domain_part.split('.')
        tld = domain_segments[-1]
        if len(tld) < 2:
            continue
            
        return True
        
    return False

MAX_LENGTH_DEFAULT = 1000
MAX_LENGTH_SHORT = 200
MIN_LENGTH_NAME = 2


@dataclass
class ModerationResult:
    allowed: bool
    violations: list[str] = field(default_factory=list)
    severity: str = "low"
    message: str = ""
    field_name: str = ""


def _severity_rank(s: str) -> int:
    return {"critical": 3, "high": 2, "medium": 1, "low": 0}.get(s, 0)


def _merge(target: ModerationResult, other: ModerationResult) -> None:
    if other.violations:
        target.violations.extend(other.violations)
        target.allowed = False
        if _severity_rank(other.severity) > _severity_rank(target.severity):
            target.severity = other.severity
        if not target.message:
            target.message = other.message


def validate_text(
    text: str | None,
    *,
    field_name: str = "text",
    required: bool = False,
    min_length: int = 0,
    max_length: int = MAX_LENGTH_DEFAULT,
    check_fake_names: bool = False,
    check_personal_data: bool = False,
    check_urls: bool = False,
) -> ModerationResult:
    result = ModerationResult(allowed=True, field_name=field_name)

    if text is None or text.strip() == "":
        if required:
            result.allowed = False
            result.violations.append("empty_required")
            result.severity = "medium"
            result.message = f"{field_name} is required"
        return result

    stripped = text.strip()

    if len(stripped) < min_length:
        result.violations.append("too_short")
        result.allowed = False
        result.severity = "low"
        result.message = f"{field_name} is too short"

    if len(stripped) > max_length:
        result.violations.append("too_long")
        result.allowed = False
        result.severity = "low"
        result.message = f"{field_name} exceeds maximum length"
        return result

    if REPEATED_CHAR_PATTERN.search(stripped):
        result.violations.append("repeated_characters")
        result.allowed = False
        result.severity = "medium"
        result.message = f"{field_name} contains invalid repeated characters"

    for pattern in DENIED_PATTERNS:
        if pattern.search(stripped):
            result.violations.append("denied_term")
            result.allowed = False
            result.severity = "critical"
            result.message = "Content violates community guidelines"
            break

    if check_fake_names and stripped.lower() in FAKE_NAME_PATTERNS:
        result.violations.append("fake_name")
        result.allowed = False
        result.severity = "high"
        result.message = "Field name appears to be a test or fake submission"

    if check_urls:
        urls = URL_PATTERN.findall(stripped)
        if len(urls) >= 2:
            result.violations.append("multiple_urls")
            result.allowed = False
            result.severity = "medium"
            result.message = f"{field_name} contains too many URLs"

    if check_personal_data:
        if PHONE_PATTERN.search(stripped):
            result.violations.append("personal_data_phone")
            result.allowed = False
            result.severity = "high"
            result.message = f"{field_name} must not contain phone numbers"
        if _contains_email_like_token(stripped):
            result.violations.append("personal_data_email")
            result.allowed = False
            result.severity = "high"
            result.message = f"{field_name} must not contain email addresses"

    return result


def validate_field_submission(
    name: str | None,
    notes: str | None = None,
    opening_hours: str | None = None,
    city: str | None = None,
) -> ModerationResult:
    combined = ModerationResult(allowed=True)

    _merge(
        combined,
        validate_text(
            name,
            field_name="name",
            required=True,
            min_length=MIN_LENGTH_NAME,
            max_length=MAX_LENGTH_SHORT,
            check_fake_names=True,
            check_personal_data=True,
        ),
    )

    if notes is not None:
        _merge(
            combined,
            validate_text(
                notes,
                field_name="notes",
                max_length=MAX_LENGTH_DEFAULT,
                check_urls=True,
                check_personal_data=True,
            ),
        )

    if opening_hours is not None:
        _merge(
            combined,
            validate_text(
                opening_hours,
                field_name="opening_hours",
                max_length=MAX_LENGTH_SHORT,
            ),
        )

    if city is not None:
        _merge(
            combined,
            validate_text(
                city,
                field_name="city",
                max_length=MAX_LENGTH_SHORT,
                check_fake_names=True,
            ),
        )

    return combined


def validate_field_report(description: str | None) -> ModerationResult:
    return validate_text(
        description,
        field_name="description",
        max_length=MAX_LENGTH_DEFAULT,
        check_urls=True,
    )


def validate_game_text(
    age_note: str | None = None,
    cancel_reason: str | None = None,
) -> ModerationResult:
    combined = ModerationResult(allowed=True)

    if age_note is not None:
        _merge(
            combined,
            validate_text(
                age_note,
                field_name="age_note",
                max_length=MAX_LENGTH_SHORT,
            ),
        )

    if cancel_reason is not None:
        _merge(
            combined,
            validate_text(
                cancel_reason,
                field_name="cancel_reason",
                max_length=MAX_LENGTH_DEFAULT,
            ),
        )

    return combined
