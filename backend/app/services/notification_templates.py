"""Centralized notification templates for all 7 notification types.

Templates are keyed by (notification_type, language_code).
Approved copy sourced from ISSUE-034 (docs/product-decisions.md).
"""

from __future__ import annotations

from typing import Any

DEFAULT_LANGUAGE = "he"

TEMPLATES: dict[tuple[str, str], dict[str, str]] = {
    # 1. game_created
    ("game_created", "he"): {
        "title": "נפתח משחק חדש",
        "body": "נפתח משחק {sport_type} במגרש {field_name}",
    },
    ("game_created", "en"): {
        "title": "New game opened",
        "body": "A new {sport_type} game opened at {field_name}",
    },
    # 2. player_joined_game
    ("player_joined_game", "he"): {
        "title": "שחקן חדש הצטרף למשחק שלך",
        "body": "{player_name} הצטרף למשחק שלך ב-{field_name}",
    },
    ("player_joined_game", "en"): {
        "title": "A new player joined your game",
        "body": "{player_name} joined your game at {field_name}",
    },
    ("player_joined_game_fallback", "he"): {
        "title": "שחקן חדש הצטרף למשחק שלך",
        "body": "שחקן חדש הצטרף למשחק שלך ב-{field_name}",
    },
    ("player_joined_game_fallback", "en"): {
        "title": "A new player joined your game",
        "body": "A new player joined your game at {field_name}",
    },
    # 3. game_closed
    ("game_closed", "he"): {
        "title": "המשחק נסגר",
        "body": "המשחק במגרש {field_name} נסגר על ידי המארגן.",
    },
    ("game_closed", "en"): {
        "title": "Game closed",
        "body": "The game at {field_name} was closed by the organizer.",
    },
    # 4. game_extended
    ("game_extended", "he"): {
        "title": "המשחק הוארך",
        "body": "שעת הסיום החדשה של המשחק היא {time}",
    },
    ("game_extended", "en"): {
        "title": "Game extended",
        "body": "The new game end time is {time}",
    },
    # 5a. scheduled_game_cancelled (creator)
    ("scheduled_game_cancelled_creator", "he"): {
        "title": "המשחק בוטל",
        "body": "המשחק במגרש {field_name} בוטל על ידי המארגן",
    },
    ("scheduled_game_cancelled_creator", "en"): {
        "title": "Game cancelled",
        "body": "The game at {field_name} was cancelled by the organizer",
    },
    # 5b. scheduled_game_cancelled (admin)
    ("scheduled_game_cancelled_admin", "he"): {
        "title": "המשחק בוטל",
        "body": "המשחק במגרש {field_name} בוטל על ידי מנהל",
    },
    ("scheduled_game_cancelled_admin", "en"): {
        "title": "Game cancelled",
        "body": "The game at {field_name} was cancelled by an admin",
    },
    # 6. scheduled_game_reminder
    ("scheduled_game_reminder", "he"): {
        "title": "תזכורת למשחק שמתקרב",
        "body": "המשחק שלך מתחיל בעוד שעה. אל תשכח להגיע בזמן.",
    },
    ("scheduled_game_reminder", "en"): {
        "title": "Upcoming game reminder",
        "body": "Your game starts in one hour. Don't forget to arrive on time.",
    },
    # 7. field_report_status_changed
    ("field_report_status_changed_in_review", "he"): {
        "title": "עדכון לדיווח שלך",
        "body": "הדיווח שלך על {field_name} נמצא בבדיקה.",
    },
    ("field_report_status_changed_in_review", "en"): {
        "title": "Your field report was updated",
        "body": "Your report about {field_name} is under review.",
    },
    ("field_report_status_changed_resolved", "he"): {
        "title": "עדכון לדיווח שלך",
        "body": "הדיווח שלך על {field_name} טופל.",
    },
    ("field_report_status_changed_resolved", "en"): {
        "title": "Your field report was updated",
        "body": "Your report about {field_name} has been resolved.",
    },
    ("field_report_status_changed_rejected", "he"): {
        "title": "עדכון לדיווח שלך",
        "body": "הדיווח שלך על {field_name} נדחה.",
    },
    ("field_report_status_changed_rejected", "en"): {
        "title": "Your field report was updated",
        "body": "Your report about {field_name} was rejected.",
    },
    # 8. test_push
    ("test_push", "he"): {
        "title": "בדיקת התראות",
        "body": "התראות Push מוכנות.",
    },
    ("test_push", "en"): {
        "title": "Test notification",
        "body": "Push notifications are ready.",
    },
}


def render_notification_template(
    notification_type: str,
    language: str,
    variables: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Render a notification template with the given variables.

    Falls back to Hebrew if the requested language template is missing.
    Falls back to the fallback body variant for player_joined_game when
    player_name is empty.
    """
    variables = variables or {}

    effective_type = notification_type
    if notification_type == "player_joined_game":
        player_name = str(variables.get("player_name") or "").strip()
        if not player_name:
            effective_type = "player_joined_game_fallback"
        else:
            variables = {**variables, "player_name": player_name}

    if notification_type == "field_report_status_changed":
        new_status = variables.pop("new_status", "resolved")
        effective_type = f"field_report_status_changed_{new_status}"

    if notification_type == "scheduled_game_cancelled":
        cancelled_by_role = variables.pop("cancelled_by_role", "creator")
        effective_type = f"scheduled_game_cancelled_{cancelled_by_role}"

    template = TEMPLATES.get((effective_type, language))
    if template is None:
        template = TEMPLATES.get((effective_type, DEFAULT_LANGUAGE))
    if template is None:
        raise ValueError(
            f"No template found for ({notification_type}, {language})"
        )

    return {
        "title": template["title"].format_map(variables),
        "body": template["body"].format_map(variables),
    }
