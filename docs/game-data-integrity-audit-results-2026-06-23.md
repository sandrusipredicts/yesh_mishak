# Game Data Integrity Audit Report

**Date:** 2026-06-23
**Environment:** Supabase (configured via backend `.env`)
**Audit tool:** `backend/scripts/audit_game_data_integrity.py` (ISSUE-050)
**Data modified:** None. This audit is read-only.

## Commands Run

```bash
cd backend
python -m scripts.audit_game_data_integrity
python -m scripts.audit_game_data_integrity --json
```

Both commands completed successfully. Exit code: `0` (no critical findings).

## Summary

| Metric | Count |
|--------|-------|
| Total checks executed | 9 |
| Total findings | 5 |
| Critical | 0 |
| Warning | 5 |
| Info | 0 |

## Findings by Check

### time_data_sanity (5 findings)

All 5 findings are the same issue: `created_at` is null or unparseable on game records.

| # | Severity | Game ID | Reason |
|---|----------|---------|--------|
| 1 | WARNING | `4d013332-ebfc-47d9-bd40-b3bd970b8ca9` | created_at is null or unparseable |
| 2 | WARNING | `3b30eaf3-f578-4a7b-83e4-695170f4cecf` | created_at is null or unparseable |
| 3 | WARNING | `67091872-c3cd-4971-9fe0-7231ae00b861` | created_at is null or unparseable |
| 4 | WARNING | `ef7680f0-45b9-4dd5-a46f-fe29a2e24ea2` | created_at is null or unparseable |
| 5 | WARNING | `2f404246-97b7-48ba-a968-77a90f64d3f8` | created_at is null or unparseable |

### Checks with No Findings

The following checks returned zero findings:

- `games_without_valid_fields` — all games reference valid fields
- `games_without_valid_creators` — all games have valid creators
- `invalid_game_status` — all game statuses are valid
- `invalid_participant_counts` — all player counts are within valid ranges
- `status_count_contradictions` — no status/count mismatches
- `games_on_inactive_fields` — no active games on inactive fields
- `scheduled_game_inconsistencies` — no stale scheduled games
- `participant_table_inconsistencies` — game_players table is consistent

## Analysis

The 5 warnings all share the same root cause: these game records have a null or unparseable `created_at` value. The schema defines `created_at timestamptz not null default now()`, so these records were likely created before the NOT NULL constraint was applied, or the column was not returned by the Supabase select query.

This is a low-severity data quality issue. The games are otherwise valid — they have correct fields, creators, statuses, and participant counts.

## Recommended Follow-Up

- **Investigate `created_at` nulls**: Query the 5 affected game records directly in Supabase to determine whether `created_at` is truly null in the database or whether the audit's select query does not return it. If truly null, backfill with the game's `started_at` value as a reasonable approximation.
- No other remediation is needed at this time.

## JSON Output

Full JSON results saved to: [`audit-results/game-data-integrity-audit-2026-06-23.json`](audit-results/game-data-integrity-audit-2026-06-23.json)
