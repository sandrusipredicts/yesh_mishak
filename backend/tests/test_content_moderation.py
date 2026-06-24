"""Tests for content moderation validation (ISSUE-053)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.services.content_moderation import (
    validate_field_report,
    validate_field_submission,
    validate_game_text,
    validate_text,
)


# ═══════════════════════════════════════════════════════════
# Unit tests — validate_text
# ═══════════════════════════════════════════════════════════


def test_valid_text_passes():
    r = validate_text("Hello world", field_name="test")
    assert r.allowed is True
    assert r.violations == []


def test_empty_required_rejected():
    r = validate_text("", field_name="name", required=True)
    assert r.allowed is False
    assert "empty_required" in r.violations


def test_none_required_rejected():
    r = validate_text(None, field_name="name", required=True)
    assert r.allowed is False
    assert "empty_required" in r.violations


def test_none_optional_passes():
    r = validate_text(None, field_name="notes")
    assert r.allowed is True


def test_too_short_rejected():
    r = validate_text("a", field_name="name", min_length=2)
    assert r.allowed is False
    assert "too_short" in r.violations


def test_too_long_rejected():
    r = validate_text("a" * 201, field_name="name", max_length=200)
    assert r.allowed is False
    assert "too_long" in r.violations


def test_repeated_chars_rejected():
    r = validate_text("aaaaaaaaaa", field_name="name")
    assert r.allowed is False
    assert "repeated_characters" in r.violations


def test_denied_term_rejected():
    r = validate_text("go fuck you dude", field_name="note")
    assert r.allowed is False
    assert "denied_term" in r.violations
    assert r.severity == "critical"
    assert "offensive" not in r.message.lower()
    assert "fuck" not in r.message.lower()


def test_denied_term_case_insensitive():
    r = validate_text("KILL YOURSELF", field_name="note")
    assert r.allowed is False
    assert "denied_term" in r.violations


def test_fake_name_rejected():
    r = validate_text("test", field_name="name", check_fake_names=True)
    assert r.allowed is False
    assert "fake_name" in r.violations


def test_fake_name_case_insensitive():
    r = validate_text("ASDF", field_name="name", check_fake_names=True)
    assert r.allowed is False
    assert "fake_name" in r.violations


def test_real_name_not_flagged_as_fake():
    r = validate_text("מגרש הכדורגל נווה שאנן", field_name="name", check_fake_names=True)
    assert r.allowed is True


def test_multiple_urls_rejected():
    text = "visit https://evil.com and https://bad.com for info"
    r = validate_text(text, field_name="notes", check_urls=True)
    assert r.allowed is False
    assert "multiple_urls" in r.violations


def test_single_url_allowed():
    r = validate_text("see https://example.com", field_name="notes", check_urls=True)
    assert r.allowed is True


def test_phone_number_rejected():
    r = validate_text("call me 054-1234567", field_name="name", check_personal_data=True)
    assert r.allowed is False
    assert "personal_data_phone" in r.violations


def test_email_rejected():
    r = validate_text("contact me at user@example.com", field_name="name", check_personal_data=True)
    assert r.allowed is False
    assert "personal_data_email" in r.violations


def test_error_message_does_not_echo_offensive():
    r = validate_text("nigger field", field_name="name")
    assert r.allowed is False
    assert "nigger" not in r.message


# ═══════════════════════════════════════════════════════════
# validate_field_submission
# ═══════════════════════════════════════════════════════════


def test_valid_field_submission():
    r = validate_field_submission(name="מגרש כדורסל הרצליה")
    assert r.allowed is True


def test_field_name_required():
    r = validate_field_submission(name="")
    assert r.allowed is False
    assert "empty_required" in r.violations


def test_field_name_offensive_rejected():
    r = validate_field_submission(name="fuck you field")
    assert r.allowed is False
    assert "denied_term" in r.violations


def test_field_name_fake_rejected():
    r = validate_field_submission(name="test")
    assert r.allowed is False
    assert "fake_name" in r.violations


def test_field_name_too_short():
    r = validate_field_submission(name="a")
    assert r.allowed is False
    assert "too_short" in r.violations


def test_field_notes_spam_rejected():
    r = validate_field_submission(name="Good field", notes="!!!!!!!!")
    assert r.allowed is False
    assert "repeated_characters" in r.violations


def test_field_notes_with_phone_rejected():
    r = validate_field_submission(name="Good field", notes="call 054-1234567 for booking")
    assert r.allowed is False
    assert "personal_data_phone" in r.violations


def test_field_name_with_personal_data_rejected():
    r = validate_field_submission(name="Field by user@example.com")
    assert r.allowed is False


def test_field_notes_valid():
    r = validate_field_submission(name="מגרש טוב", notes="Open evenings, well lit")
    assert r.allowed is True


# ═══════════════════════════════════════════════════════════
# validate_field_report
# ═══════════════════════════════════════════════════════════


def test_valid_field_report():
    r = validate_field_report("Field is closed, gate is locked")
    assert r.allowed is True


def test_field_report_none_passes():
    r = validate_field_report(None)
    assert r.allowed is True


def test_field_report_offensive_rejected():
    r = validate_field_report("fuck you all")
    assert r.allowed is False


def test_field_report_spam_rejected():
    r = validate_field_report("aaaaaaaaaaaaaaa")
    assert r.allowed is False


def test_field_report_too_long_rejected():
    r = validate_field_report("x" * 1001)
    assert r.allowed is False
    assert "too_long" in r.violations


# ═══════════════════════════════════════════════════════════
# validate_game_text
# ═══════════════════════════════════════════════════════════


def test_valid_game_note():
    r = validate_game_text(age_note="18+ only")
    assert r.allowed is True


def test_game_note_offensive_rejected():
    r = validate_game_text(age_note="kill yourself if you lose")
    assert r.allowed is False


def test_cancel_reason_valid():
    r = validate_game_text(cancel_reason="Not enough players")
    assert r.allowed is True


def test_cancel_reason_offensive_rejected():
    r = validate_game_text(cancel_reason="fuck you all")
    assert r.allowed is False


def test_cancel_reason_spam_rejected():
    r = validate_game_text(cancel_reason="!!!!!!!!!!!")
    assert r.allowed is False


def test_none_game_text_passes():
    r = validate_game_text()
    assert r.allowed is True


def test_moderation_regression_profanity():
    # normal forbidden/profanity match still detected
    r = validate_text("go fuck you dude", field_name="note")
    assert r.allowed is False
    assert "denied_term" in r.violations


def test_moderation_regression_benign():
    # benign normal text still allowed
    r = validate_text("This is a clean and benign description of the field.", field_name="note")
    assert r.allowed is True
    assert r.violations == []


def test_moderation_regression_pathological_input():
    # pathological repeated-character input does not hang and returns quickly
    import time
    start_time = time.perf_counter()
    r = validate_text("%" * 10000, field_name="note", max_length=1000)
    duration = time.perf_counter() - start_time
    assert r.allowed is False
    assert "too_long" in r.violations
    assert duration < 0.1  # should be extremely fast, virtually instantaneous (less than 100ms)


def test_moderation_regression_emails():
    # normal email is still detected
    r = validate_text("contact me at user@example.com", field_name="note", check_personal_data=True)
    assert r.allowed is False
    assert "personal_data_email" in r.violations


def test_moderation_regression_malformed_emails_no_crash():
    # malformed email-like strings do not crash and are handled correctly
    cases = [
        "@",
        "foo@",
        "@bar",
        "foo@bar",
        "foo@bar.",
        "foo@bar.c",
        "foo@bar.co",
        "foo@bar@baz.com",
        "foo@bar.com.",
        "foo@@bar.com",
    ]
    for case in cases:
        r = validate_text(case, field_name="note", check_personal_data=True)
        assert isinstance(r.allowed, bool)


