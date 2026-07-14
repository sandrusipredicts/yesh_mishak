from __future__ import annotations

import pytest

from app.services.notification_templates import render_notification_template


def test_field_report_status_in_review_he() -> None:
    result = render_notification_template(
        "field_report_status_changed",
        "he",
        {"new_status": "in_review", "field_name": "מגרש מרכזי"},
    )
    assert result["title"] == "עדכון לדיווח שלך"
    assert "מגרש מרכזי" in result["body"]
    assert "בבדיקה" in result["body"]


def test_field_report_status_resolved_en() -> None:
    result = render_notification_template(
        "field_report_status_changed",
        "en",
        {"new_status": "resolved", "field_name": "Central Court"},
    )
    assert result["title"] == "Your field report was updated"
    assert "Central Court" in result["body"]
    assert "resolved" in result["body"]


def test_field_report_status_rejected_en() -> None:
    result = render_notification_template(
        "field_report_status_changed",
        "en",
        {"new_status": "rejected", "field_name": "Central Court"},
    )
    assert "rejected" in result["body"]


def test_field_report_status_falls_back_to_hebrew() -> None:
    result = render_notification_template(
        "field_report_status_changed",
        "fr",
        {"new_status": "resolved", "field_name": "Central Court"},
    )
    assert result["title"] == "עדכון לדיווח שלך"


def test_field_report_status_unknown_raises() -> None:
    with pytest.raises(ValueError):
        render_notification_template(
            "field_report_status_changed",
            "en",
            {"new_status": "unknown_status", "field_name": "Court"},
        )


def test_all_three_statuses_have_templates() -> None:
    for status in ("in_review", "resolved", "rejected"):
        for lang in ("he", "en"):
            result = render_notification_template(
                "field_report_status_changed",
                lang,
                {"new_status": status, "field_name": "Test"},
            )
            assert result["title"]
            assert result["body"]
