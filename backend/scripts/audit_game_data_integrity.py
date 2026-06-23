"""Game data integrity audit.

Read-only audit that detects inconsistent, orphaned, invalid, or suspicious
game records. Does not modify any data.

Usage:
    python -m scripts.audit_game_data_integrity          # live Supabase
    python -m scripts.audit_game_data_integrity --json   # machine-readable output
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.routers.game_lifecycle import ACTIVE_GAME_STATUSES

ALLOWED_GAME_STATUSES = ["open", "full", "finished", "cancelled"]
ACTIVE_FIELD_STATUS = "open"
APPROVED_FIELD_STATUS = "approved"


@dataclass
class Finding:
    check: str
    severity: str  # critical / warning / info
    game_id: str | None
    reason: str
    data: dict[str, Any] = field(default_factory=dict)
    suggested_fix: str | None = None


def run_audit(supabase: Any) -> list[Finding]:
    games = supabase.table("games").select("*").execute().data
    fields_rows = supabase.table("fields").select("*").execute().data
    users_rows = supabase.table("users").select("id").execute().data
    game_players_rows = supabase.table("game_players").select("*").execute().data

    fields_by_id = {str(f["id"]): f for f in fields_rows}
    user_ids = {str(u["id"]) for u in users_rows}

    findings: list[Finding] = []

    for game in games:
        gid = str(game.get("id", ""))
        findings.extend(_check_field_reference(game, gid, fields_by_id))
        findings.extend(_check_creator(game, gid, user_ids))
        findings.extend(_check_status(game, gid))
        findings.extend(_check_participant_counts(game, gid))
        findings.extend(_check_status_count_contradictions(game, gid))
        findings.extend(_check_inactive_field(game, gid, fields_by_id))
        findings.extend(_check_scheduled_consistency(game, gid))
        findings.extend(_check_timestamps(game, gid))

    findings.extend(
        _check_game_players(games, game_players_rows, user_ids, fields_by_id)
    )

    return findings


def _check_field_reference(
    game: dict, gid: str, fields_by_id: dict
) -> list[Finding]:
    findings: list[Finding] = []
    field_id = game.get("field_id")
    if not field_id:
        findings.append(
            Finding(
                check="games_without_valid_fields",
                severity="critical",
                game_id=gid,
                reason="game.field_id is null",
                suggested_fix="Investigate and assign a valid field or mark game as cancelled",
            )
        )
    elif str(field_id) not in fields_by_id:
        findings.append(
            Finding(
                check="games_without_valid_fields",
                severity="critical",
                game_id=gid,
                reason="field_id points to a missing field",
                data={"field_id": str(field_id)},
                suggested_fix="Field may have been deleted; mark game as cancelled",
            )
        )
    return findings


def _check_creator(
    game: dict, gid: str, user_ids: set[str]
) -> list[Finding]:
    findings: list[Finding] = []
    created_by = game.get("created_by")
    if not created_by:
        findings.append(
            Finding(
                check="games_without_valid_creators",
                severity="critical",
                game_id=gid,
                reason="game.created_by is null",
                suggested_fix="Creator user may have been deleted; review game history",
            )
        )
    elif str(created_by) not in user_ids:
        findings.append(
            Finding(
                check="games_without_valid_creators",
                severity="critical",
                game_id=gid,
                reason="creator does not exist in users table",
                data={"created_by": str(created_by)},
                suggested_fix="Creator user deleted; game is orphaned",
            )
        )
    return findings


def _check_status(game: dict, gid: str) -> list[Finding]:
    findings: list[Finding] = []
    status = game.get("status")
    if status not in ALLOWED_GAME_STATUSES:
        findings.append(
            Finding(
                check="invalid_game_status",
                severity="critical",
                game_id=gid,
                reason=f"status '{status}' not in allowed values",
                data={"status": status, "allowed": ALLOWED_GAME_STATUSES},
                suggested_fix="Update to a valid status or investigate migration gap",
            )
        )
    return findings


def _check_participant_counts(game: dict, gid: str) -> list[Finding]:
    findings: list[Finding] = []
    pp = game.get("players_present")
    mp = game.get("max_players")

    if pp is None:
        findings.append(
            Finding(
                check="invalid_participant_counts",
                severity="warning",
                game_id=gid,
                reason="players_present is null",
            )
        )
    elif pp < 0:
        findings.append(
            Finding(
                check="invalid_participant_counts",
                severity="critical",
                game_id=gid,
                reason="players_present is negative",
                data={"players_present": pp},
                suggested_fix="Set players_present to 0 or correct count",
            )
        )

    if mp is None:
        findings.append(
            Finding(
                check="invalid_participant_counts",
                severity="warning",
                game_id=gid,
                reason="max_players is null",
            )
        )
    elif mp <= 0:
        findings.append(
            Finding(
                check="invalid_participant_counts",
                severity="critical",
                game_id=gid,
                reason="max_players is <= 0",
                data={"max_players": mp},
                suggested_fix="Set max_players to a positive value",
            )
        )

    if pp is not None and mp is not None and pp > mp:
        findings.append(
            Finding(
                check="invalid_participant_counts",
                severity="critical",
                game_id=gid,
                reason="players_present exceeds max_players",
                data={"players_present": pp, "max_players": mp},
                suggested_fix="Reduce players_present or increase max_players",
            )
        )
    return findings


def _check_status_count_contradictions(game: dict, gid: str) -> list[Finding]:
    findings: list[Finding] = []
    status = game.get("status")
    pp = game.get("players_present")
    mp = game.get("max_players")

    if pp is None or mp is None or status not in ALLOWED_GAME_STATUSES:
        return findings

    if status == "full" and pp < mp:
        findings.append(
            Finding(
                check="status_count_contradictions",
                severity="warning",
                game_id=gid,
                reason="status is 'full' but players_present < max_players",
                data={"status": status, "players_present": pp, "max_players": mp},
                suggested_fix="Set status to 'open' or correct player count",
            )
        )

    if status == "open" and pp >= mp:
        findings.append(
            Finding(
                check="status_count_contradictions",
                severity="warning",
                game_id=gid,
                reason="status is 'open' but players_present >= max_players",
                data={"status": status, "players_present": pp, "max_players": mp},
                suggested_fix="Set status to 'full' or correct player count",
            )
        )

    return findings


def _check_inactive_field(
    game: dict, gid: str, fields_by_id: dict
) -> list[Finding]:
    findings: list[Finding] = []
    status = game.get("status")
    if status not in ACTIVE_GAME_STATUSES:
        return findings

    field_id = game.get("field_id")
    if not field_id or str(field_id) not in fields_by_id:
        return findings

    f = fields_by_id[str(field_id)]

    if f.get("status") != ACTIVE_FIELD_STATUS:
        findings.append(
            Finding(
                check="games_on_inactive_fields",
                severity="warning",
                game_id=gid,
                reason=f"active game on field with status '{f.get('status')}'",
                data={"field_id": str(field_id), "field_status": f.get("status")},
                suggested_fix="Close or cancel this game",
            )
        )

    if f.get("approval_status") != APPROVED_FIELD_STATUS:
        findings.append(
            Finding(
                check="games_on_inactive_fields",
                severity="warning",
                game_id=gid,
                reason=f"active game on field with approval_status '{f.get('approval_status')}'",
                data={
                    "field_id": str(field_id),
                    "approval_status": f.get("approval_status"),
                },
                suggested_fix="Close or cancel this game",
            )
        )

    if not f.get("verified"):
        findings.append(
            Finding(
                check="games_on_inactive_fields",
                severity="warning",
                game_id=gid,
                reason="active game on unverified field",
                data={"field_id": str(field_id), "verified": f.get("verified")},
                suggested_fix="Close or cancel this game, or verify the field",
            )
        )

    return findings


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _check_scheduled_consistency(game: dict, gid: str) -> list[Finding]:
    findings: list[Finding] = []
    status = game.get("status")
    scheduled_at = _parse_ts(game.get("scheduled_at"))

    if scheduled_at and status in ACTIVE_GAME_STATUSES:
        now = datetime.now(timezone.utc)
        if scheduled_at < now:
            findings.append(
                Finding(
                    check="scheduled_game_inconsistencies",
                    severity="info",
                    game_id=gid,
                    reason="scheduled_at is in the past but game is still active",
                    data={"scheduled_at": str(scheduled_at), "status": status},
                    suggested_fix="Game may need expiration check or manual close",
                )
            )

    return findings


def _check_timestamps(game: dict, gid: str) -> list[Finding]:
    findings: list[Finding] = []
    created_at = _parse_ts(game.get("created_at"))

    if created_at is None:
        findings.append(
            Finding(
                check="time_data_sanity",
                severity="warning",
                game_id=gid,
                reason="created_at is null or unparseable",
            )
        )

    started_at = _parse_ts(game.get("started_at"))
    if created_at and started_at and started_at < created_at:
        findings.append(
            Finding(
                check="time_data_sanity",
                severity="info",
                game_id=gid,
                reason="started_at is before created_at",
                data={
                    "started_at": str(started_at),
                    "created_at": str(created_at),
                },
            )
        )

    status = game.get("status")
    if status == "cancelled" and not game.get("cancelled_at"):
        findings.append(
            Finding(
                check="time_data_sanity",
                severity="warning",
                game_id=gid,
                reason="status is cancelled but cancelled_at is missing",
                suggested_fix="Set cancelled_at to the time the game was cancelled",
            )
        )

    return findings


def _check_game_players(
    games: list[dict],
    game_players_rows: list[dict],
    user_ids: set[str],
    fields_by_id: dict,
) -> list[Finding]:
    findings: list[Finding] = []
    game_ids = {str(g["id"]) for g in games if g.get("id")}
    games_by_id = {str(g["id"]): g for g in games if g.get("id")}

    players_by_game: dict[str, list[dict]] = {}
    seen_pairs: set[tuple[str, str]] = set()

    for gp in game_players_rows:
        gp_game_id = str(gp.get("game_id", ""))
        gp_user_id = str(gp.get("user_id", ""))

        if gp_game_id not in game_ids:
            findings.append(
                Finding(
                    check="participant_table_inconsistencies",
                    severity="critical",
                    game_id=gp_game_id,
                    reason="game_players row points to missing game",
                    data={"game_player_id": str(gp.get("id", ""))},
                    suggested_fix="Delete orphaned game_players row",
                )
            )
            continue

        if gp_user_id not in user_ids:
            findings.append(
                Finding(
                    check="participant_table_inconsistencies",
                    severity="warning",
                    game_id=gp_game_id,
                    reason="participant points to missing user",
                    data={
                        "user_id": gp_user_id,
                        "game_player_id": str(gp.get("id", "")),
                    },
                    suggested_fix="Remove orphaned game_players row",
                )
            )

        pair = (gp_game_id, gp_user_id)
        if pair in seen_pairs:
            findings.append(
                Finding(
                    check="participant_table_inconsistencies",
                    severity="warning",
                    game_id=gp_game_id,
                    reason="duplicate participant row for same game/user",
                    data={"user_id": gp_user_id},
                    suggested_fix="Remove duplicate game_players row",
                )
            )
        seen_pairs.add(pair)

        players_by_game.setdefault(gp_game_id, []).append(gp)

    for game in games:
        gid = str(game.get("id", ""))
        if game.get("status") not in ACTIVE_GAME_STATUSES:
            continue
        actual_count = len(players_by_game.get(gid, []))
        recorded_count = game.get("players_present")
        if recorded_count is not None and actual_count != recorded_count:
            findings.append(
                Finding(
                    check="participant_table_inconsistencies",
                    severity="warning",
                    game_id=gid,
                    reason="players_present does not match actual participant rows",
                    data={
                        "players_present": recorded_count,
                        "actual_rows": actual_count,
                    },
                    suggested_fix="Update players_present to match game_players count",
                )
            )

    return findings


def format_findings(findings: list[Finding]) -> str:
    if not findings:
        return "No findings. All game data is consistent."

    grouped: dict[str, list[Finding]] = {}
    for f in findings:
        grouped.setdefault(f.check, []).append(f)

    lines: list[str] = []
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    for check_name in sorted(grouped):
        items = sorted(grouped[check_name], key=lambda x: severity_order.get(x.severity, 3))
        lines.append(f"\n=== {check_name} ({len(items)} finding(s)) ===")
        for item in items:
            lines.append(
                f"  [{item.severity.upper()}] game={item.game_id}: {item.reason}"
            )
            if item.data:
                lines.append(f"    data: {item.data}")
            if item.suggested_fix:
                lines.append(f"    fix: {item.suggested_fix}")

    critical = sum(1 for f in findings if f.severity == "critical")
    warning = sum(1 for f in findings if f.severity == "warning")
    info = sum(1 for f in findings if f.severity == "info")
    lines.append(
        f"\nTotal: {len(findings)} finding(s) — "
        f"{critical} critical, {warning} warning, {info} info"
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Game data integrity audit")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    from app.db.supabase import get_supabase_client

    supabase = get_supabase_client()
    findings = run_audit(supabase)

    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2, default=str))
    else:
        print(format_findings(findings))

    critical_count = sum(1 for f in findings if f.severity == "critical")
    sys.exit(1 if critical_count > 0 else 0)


if __name__ == "__main__":
    main()
