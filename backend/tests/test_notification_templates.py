"""ISSUE-035: Notification template module tests.

Verifies render_notification_template produces correct output for all
7 notification types in Hebrew and English, including fallback scenarios.
"""

import pytest

from app.services.notification_templates import (
    DEFAULT_LANGUAGE,
    TEMPLATES,
    render_notification_template,
)


# ═══════════════════════════════════════════════════════════════
# 1. game_created — Hebrew
# ═══════════════════════════════════════════════════════════════


def test_game_created_hebrew():
    result = render_notification_template(
        "game_created", "he",
        {"sport_type": "football", "field_name": "מגרש הפועל"},
    )
    assert result["title"] == "נפתח משחק חדש"
    assert result["body"] == "נפתח משחק football במגרש מגרש הפועל"


# ═══════════════════════════════════════════════════════════════
# 2. game_created — English
# ═══════════════════════════════════════════════════════════════


def test_game_created_english():
    result = render_notification_template(
        "game_created", "en",
        {"sport_type": "basketball", "field_name": "City Court"},
    )
    assert result["title"] == "New game opened"
    assert result["body"] == "A new basketball game opened at City Court"


# ═══════════════════════════════════════════════════════════════
# 3. player_joined_game — with player name
# ═══════════════════════════════════════════════════════════════


def test_player_joined_game_with_name():
    result = render_notification_template(
        "player_joined_game", "he",
        {"player_name": "דני", "field_name": "מגרש הפועל"},
    )
    assert result["title"] == "שחקן חדש הצטרף למשחק שלך"
    assert result["body"] == "דני הצטרף למשחק שלך ב-מגרש הפועל"


# ═══════════════════════════════════════════════════════════════
# 4. player_joined_game — fallback (empty player name)
# ═══════════════════════════════════════════════════════════════


def test_player_joined_game_fallback_empty_name():
    result = render_notification_template(
        "player_joined_game", "he",
        {"player_name": "", "field_name": "מגרש הפועל"},
    )
    assert result["title"] == "שחקן חדש הצטרף למשחק שלך"
    assert result["body"] == "שחקן חדש הצטרף למשחק שלך ב-מגרש הפועל"


# ═══════════════════════════════════════════════════════════════
# 5. player_joined_game — fallback (None player name)
# ═══════════════════════════════════════════════════════════════


def test_player_joined_game_fallback_none_name():
    result = render_notification_template(
        "player_joined_game", "en",
        {"player_name": None, "field_name": "City Court"},
    )
    assert result["title"] == "A new player joined your game"
    assert result["body"] == "A new player joined your game at City Court"


# ═══════════════════════════════════════════════════════════════
# 6. game_closed — Hebrew
# ═══════════════════════════════════════════════════════════════


def test_game_closed_hebrew():
    result = render_notification_template(
        "game_closed", "he", {"field_name": "מגרש הפועל"},
    )
    assert result["title"] == "המשחק נסגר"
    assert result["body"] == "המשחק במגרש מגרש הפועל נסגר על ידי המארגן."


# ═══════════════════════════════════════════════════════════════
# 7. game_extended — Hebrew
# ═══════════════════════════════════════════════════════════════


def test_game_extended_hebrew():
    result = render_notification_template(
        "game_extended", "he", {"time": "18:30"},
    )
    assert result["title"] == "המשחק הוארך"
    assert result["body"] == "שעת הסיום החדשה של המשחק היא 18:30"


# ═══════════════════════════════════════════════════════════════
# 8. scheduled_game_cancelled — creator role
# ═══════════════════════════════════════════════════════════════


def test_scheduled_game_cancelled_creator():
    result = render_notification_template(
        "scheduled_game_cancelled", "he",
        {"field_name": "מגרש הפועל", "cancelled_by_role": "creator"},
    )
    assert result["title"] == "המשחק בוטל"
    assert result["body"] == "המשחק במגרש מגרש הפועל בוטל על ידי המארגן"


# ═══════════════════════════════════════════════════════════════
# 9. scheduled_game_cancelled — admin role
# ═══════════════════════════════════════════════════════════════


def test_scheduled_game_cancelled_admin():
    result = render_notification_template(
        "scheduled_game_cancelled", "en",
        {"field_name": "City Court", "cancelled_by_role": "admin"},
    )
    assert result["title"] == "Game cancelled"
    assert result["body"] == "The game at City Court was cancelled by an admin"


# ═══════════════════════════════════════════════════════════════
# 10. scheduled_game_reminder — Hebrew
# ═══════════════════════════════════════════════════════════════


def test_scheduled_game_reminder_hebrew():
    result = render_notification_template("scheduled_game_reminder", "he")
    assert result["title"] == "תזכורת למשחק שמתקרב"
    assert result["body"] == "המשחק שלך מתחיל בעוד שעה. אל תשכח להגיע בזמן."


# ═══════════════════════════════════════════════════════════════
# 11. test_push — English (current default)
# ═══════════════════════════════════════════════════════════════


def test_test_push_english():
    result = render_notification_template("test_push", "en")
    assert result["title"] == "Test notification"
    assert result["body"] == "Push notifications are ready."


# ═══════════════════════════════════════════════════════════════
# 12. Fallback to Hebrew for unsupported language
# ═══════════════════════════════════════════════════════════════


def test_fallback_to_hebrew_for_unknown_language():
    result = render_notification_template(
        "game_created", "fr",
        {"sport_type": "football", "field_name": "Parc"},
    )
    assert result["title"] == "נפתח משחק חדש"
    assert result["body"] == "נפתח משחק football במגרש Parc"


# ═══════════════════════════════════════════════════════════════
# 13. ValueError for unknown notification type
# ═══════════════════════════════════════════════════════════════


def test_unknown_type_raises_value_error():
    with pytest.raises(ValueError, match="No template found"):
        render_notification_template("unknown_type", "he")


# ═══════════════════════════════════════════════════════════════
# 14. Default language is Hebrew
# ═══════════════════════════════════════════════════════════════


def test_default_language_is_hebrew():
    assert DEFAULT_LANGUAGE == "he"


# ═══════════════════════════════════════════════════════════════
# 15. All 7 types have Hebrew templates
# ═══════════════════════════════════════════════════════════════


def test_all_types_have_hebrew_templates():
    required_types = [
        "game_created",
        "player_joined_game",
        "player_joined_game_fallback",
        "game_closed",
        "game_extended",
        "scheduled_game_cancelled_creator",
        "scheduled_game_cancelled_admin",
        "scheduled_game_reminder",
        "test_push",
    ]
    for notification_type in required_types:
        assert (notification_type, "he") in TEMPLATES, (
            f"Missing Hebrew template for {notification_type}"
        )


# ═══════════════════════════════════════════════════════════════
# 16. All 7 types have English templates
# ═══════════════════════════════════════════════════════════════


def test_all_types_have_english_templates():
    required_types = [
        "game_created",
        "player_joined_game",
        "player_joined_game_fallback",
        "game_closed",
        "game_extended",
        "scheduled_game_cancelled_creator",
        "scheduled_game_cancelled_admin",
        "scheduled_game_reminder",
        "test_push",
    ]
    for notification_type in required_types:
        assert (notification_type, "en") in TEMPLATES, (
            f"Missing English template for {notification_type}"
        )
