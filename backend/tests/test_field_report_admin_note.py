from __future__ import annotations

from typing import Optional

import pytest
from pydantic import ValidationError

from app.core.config import get_settings


def configure_settings(monkeypatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "test-key")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-google-client")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    get_settings.cache_clear()


def test_admin_note_whitespace_normalized_to_null(monkeypatch) -> None:
    configure_settings(monkeypatch)
    from app.api.admin import FieldReportStatusUpdate

    model = FieldReportStatusUpdate(status="resolved", admin_note="   ")
    assert model.admin_note is None


def test_admin_note_stripped(monkeypatch) -> None:
    configure_settings(monkeypatch)
    from app.api.admin import FieldReportStatusUpdate

    model = FieldReportStatusUpdate(status="resolved", admin_note="  Fixed.  ")
    assert model.admin_note == "Fixed."


def test_admin_note_none_by_default(monkeypatch) -> None:
    configure_settings(monkeypatch)
    from app.api.admin import FieldReportStatusUpdate

    model = FieldReportStatusUpdate(status="resolved")
    assert model.admin_note is None


def test_admin_note_max_length(monkeypatch) -> None:
    configure_settings(monkeypatch)
    from app.api.admin import FieldReportStatusUpdate

    with pytest.raises(ValidationError):
        FieldReportStatusUpdate(status="resolved", admin_note="x" * 1001)


def test_admin_note_at_max_length(monkeypatch) -> None:
    configure_settings(monkeypatch)
    from app.api.admin import FieldReportStatusUpdate

    model = FieldReportStatusUpdate(status="resolved", admin_note="x" * 1000)
    assert len(model.admin_note) == 1000


def test_invalid_status_rejected(monkeypatch) -> None:
    configure_settings(monkeypatch)
    from app.api.admin import FieldReportStatusUpdate

    with pytest.raises(Exception):
        FieldReportStatusUpdate(status="invalid_status")
