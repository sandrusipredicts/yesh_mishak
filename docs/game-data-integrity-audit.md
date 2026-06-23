# Game Data Integrity Audit

## What It Does

A read-only audit that scans all game records and detects inconsistencies, orphaned references, invalid values, and suspicious state. It does **not** modify any data.

## How to Run

From the `backend/` directory:

```bash
# Human-readable output
python -m scripts.audit_game_data_integrity

# Machine-readable JSON
python -m scripts.audit_game_data_integrity --json
```

Requires `SUPABASE_URL` and `SUPABASE_KEY` environment variables (uses the regular Supabase client).

Exit code: `0` if no critical findings, `1` if any critical finding exists.

## Checks Performed

| # | Check Name | Severity | Description |
|---|-----------|----------|-------------|
| 1 | `games_without_valid_fields` | critical | `field_id` is null or points to a deleted field |
| 2 | `games_without_valid_creators` | critical | `created_by` is null or points to a deleted user |
| 3 | `invalid_game_status` | critical | `status` is not in `[open, full, finished, cancelled]` |
| 4 | `invalid_participant_counts` | critical/warning | `players_present` negative, null, or exceeds `max_players`; `max_players` <= 0 or null |
| 5 | `status_count_contradictions` | warning | `full` but under capacity, or `open` but at/over capacity |
| 6 | `games_on_inactive_fields` | warning | Active game on a closed/renovation/unapproved/unverified field |
| 7 | `scheduled_game_inconsistencies` | info | `scheduled_at` in the past but game still active |
| 8 | `participant_table_inconsistencies` | critical/warning | `players_present` vs actual `game_players` rows mismatch, orphaned rows, duplicate rows, missing users |
| 9 | `time_data_sanity` | warning/info | Missing `created_at`, `started_at` before `created_at`, cancelled but no `cancelled_at` |

## Severity Levels

- **critical** — Data integrity violation. The record is broken and should be investigated immediately.
- **warning** — Inconsistency that may indicate a bug or stale data. Should be reviewed.
- **info** — Suspicious but potentially valid state. Monitor or investigate when convenient.

## Output Format

### Human-readable (default)

```
=== games_without_valid_fields (1 finding(s)) ===
  [CRITICAL] game=abc-123: field_id points to a missing field
    data: {'field_id': 'def-456'}
    fix: Field may have been deleted; mark game as cancelled

Total: 1 finding(s) — 1 critical, 0 warning, 0 info
```

### JSON (`--json`)

```json
[
  {
    "check": "games_without_valid_fields",
    "severity": "critical",
    "game_id": "abc-123",
    "reason": "field_id points to a missing field",
    "data": {"field_id": "def-456"},
    "suggested_fix": "Field may have been deleted; mark game as cancelled"
  }
]
```

## What It Does NOT Do

- Does not modify, repair, or delete any data
- Does not require admin authentication (uses Supabase client directly)
- Does not check frontend behavior
- Does not validate field data (that's a separate concern)
