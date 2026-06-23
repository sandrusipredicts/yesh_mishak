# Notification Stress Test Results — ISSUE-038

**Date:** 2026-06-23
**Executed by:** Automated pytest suite
**Environment:** Local development (FakeSupabase in-memory test infrastructure)
**Push delivery:** Mocked (no real FCM calls)
**Branch:** `issue-038-execute-notification-stress-testing`

## Test Environment

| Property | Value |
| --- | --- |
| Runtime | Python 3.14.3, pytest 8.3.4 |
| Backend framework | FastAPI with TestClient |
| Database | FakeSupabase (in-memory, same API surface as Supabase client) |
| Push delivery | Mocked — returns `{"ok": true}` or raises `Exception` for failure scenarios |
| Users | Synthetic (`stress-user-NNNN`, `stress-organizer`, `stress-admin`) |
| Data isolation | All data created in-memory per test, automatically cleaned up |

## Test Limitations

1. **No real database.** Tests use FakeSupabase, not PostgreSQL. This validates application logic (dedup checks, row creation, filtering) but does not measure real DB query latency, index performance, or connection pool behavior.
2. **No real concurrency.** Tests execute sequentially within a single thread. True race conditions (e.g., concurrent cancellation from ISSUE-030) cannot be fully simulated. The `scheduled_game_cancelled` dedup gap is confirmed by calling the function twice sequentially, which documents the absence of application-level dedup.
3. **No real push delivery.** FCM network latency and failure modes are mocked. Push fan-out timing reflects only the application loop, not network I/O.
4. **No frontend testing.** Inbox rendering performance and polling behavior are not measured.
5. **Execution times are in-memory baselines** — real database times will be higher. The times establish that application logic itself is not a bottleneck.

## Dataset Sizes Used

| Scenario | Dataset Size |
| --- | --- |
| Bulk fan-out | 100 and 1,000 recipients |
| Repeated game creation | 50 users, 10 games (500 total notifications) |
| Unread counter | 100, 500, and 1,000 notifications per user |
| Large inbox | 100, 500, and 1,000 notifications per user |
| Reminder batch | 50 games x 10 players (500) and 200 games x 10 players (2,000) |
| Retention cleanup | 1,000 old + 1,000 fresh and 5,000 old + 5,000 fresh |
| Duplicate prevention | 100 users, 5 repeated calls per event type |

## Scenario Results

### Scenario 1: Bulk game_created Fan-Out

| Test | Recipients | Notifications Created | Duplicates | Time | Result |
| --- | --- | --- | --- | --- | --- |
| Fan-out 100 | 100 | 100 | 0 | 0.001s | PASS |
| Fan-out 1,000 | 1,000 | 1,000 | 0 | 0.022s | PASS |
| Fan-out with push failure | 100 | 100 | 0 | N/A | PASS |

**Findings:**
- Notification row creation scales linearly with recipient count.
- Zero duplicates at all tested levels.
- Push failures (mocked `Exception`) do not block notification row creation — all 100 in-app notifications were created despite 100% push failure rate.

### Scenario 2: Repeated Game Creation / Dedup Verification

| Test | Users | Games | Total Notifications | Duplicates | Result |
| --- | --- | --- | --- | --- | --- |
| Same game called twice | 50 | 1 | 50 (second call: 0) | 0 | PASS |
| 10 different games | 50 | 10 | 500 | 0 | PASS |

**Findings:**
- Application-level dedup correctly prevents duplicate `game_created` notifications for the same user+game.
- Each new game correctly generates its own set of notifications.

### Scenario 3: Unread Counter Under Many Notifications

| Test | Notifications | Unread Count | Time | Result |
| --- | --- | --- | --- | --- |
| 100 notifications | 100 | 100 | 0.009s | PASS |
| 500 notifications | 500 | 500 | 0.009s | PASS |
| 1,000 notifications | 1,000 | 1,000 | 0.009s | PASS |
| Mark single read | 100 | 99 after read | N/A | PASS |
| Mark all read (200) | 200 | 0 after read-all | N/A | PASS |
| Cross-user isolation | 50 each | A=0, B=50 after A read-all | N/A | PASS |

**Findings:**
- Unread count is correct at all tested levels.
- Mark single read decreases count by exactly 1.
- Mark all read sets count to exactly 0.
- No cross-user contamination: read-all for user A does not affect user B's count.

### Scenario 4: Large Inbox Retrieval

| Test | Notifications | Response Time | Payload Size | Result |
| --- | --- | --- | --- | --- |
| 100 rows | 100 | 0.008s | 24,001 bytes | PASS |
| 500 rows | 500 | 0.017s | 120,001 bytes | PASS |
| 1,000 rows | 1,000 | 0.024s | 240,001 bytes | PASS |

**Findings:**
- Response time scales linearly with row count.
- At 1,000 rows the payload is ~240 KB. This is manageable but suggests that pagination should be considered as a follow-up if user notification counts grow significantly beyond 1,000.
- No server errors or failures at any tested level.
- Other users' notifications are correctly excluded from the response.

### Scenario 5: Scheduled Reminder Batch Stress

| Test | Games | Players/Game | Total Notifications | Time | Result |
| --- | --- | --- | --- | --- | --- |
| 50 games | 50 | 10 | 500 | 0.007s | PASS |
| 200 games | 200 | 10 | 2,000 | 0.057s | PASS |
| Rerun (idempotent) | 1 | 10 | 10 (rerun: 0) | N/A | PASS |

**Findings:**
- Reminder generation scales linearly with game count.
- `scheduled_reminder_processed_at` prevents re-processing on subsequent runs.
- Existing notification check prevents duplicates even if `processed_at` is not set.
- All processed/skipped/created counts are correct.

### Scenario 6: Retention Cleanup Stress

| Test | Old Rows | Fresh Rows | Deleted | Remaining | Time | Result |
| --- | --- | --- | --- | --- | --- | --- |
| 1k + 1k | 1,000 | 1,000 | 1,000 | 1,000 | 0.019s | PASS |
| 5k + 5k | 5,000 | 5,000 | 5,000 | 5,000 | 0.285s | PASS |
| Rerun (idempotent) | 100 | 0 | 100 (rerun: 0) | 0 | N/A | PASS |

**Findings:**
- Only notifications older than 90 days are deleted. Fresh notifications are untouched.
- `push_tokens` and `notification_preferences` tables are unaffected.
- Cleanup is idempotent — second run deletes 0.
- At 10,000 total rows (5k old + 5k fresh), cleanup takes ~0.3s in-memory. Real DB performance will depend on index efficiency.

### Scenario 7: Duplicate Prevention for All Protected Event Types

| Event Type | Protection | Repeated Calls | Duplicates | Result |
| --- | --- | --- | --- | --- |
| `game_created` | App check + DB unique index | 5x | 0 | PASS |
| `game_closed` | App check + DB unique index | 5x | 0 | PASS |
| `game_extended` (same end time) | App check + DB unique index | 5x | 0 | PASS |
| `game_extended` (3 different end times) | Separate notifications per end time | 3x | 0 (30 total, correct) | PASS |
| `scheduled_game_reminder` | App check + processed_at + DB unique index | 5x | 0 | PASS |
| `scheduled_game_cancelled` | **No dedup** (ISSUE-030 known gap) | 2x | **10 users with duplicates** | PASS (documents known gap) |

**Findings:**
- All protected event types (`game_created`, `game_closed`, `game_extended`, `scheduled_game_reminder`) correctly prevent duplicates under repeated function calls.
- `game_extended` correctly creates separate notifications for different end times.
- `scheduled_game_cancelled` confirmed to have **no application-level or DB-level dedup**. Two sequential calls (creator cancel + admin cancel) created 21 rows for 10 users (10 from first call + 11 from second, including the organizer who was added as recipient for admin cancellation). This confirms the ISSUE-030 finding.

## Metrics Summary

| Metric | Value |
| --- | --- |
| Total stress tests executed | 27 |
| Tests passed | 27 |
| Tests failed | 0 |
| Critical issues found | 0 |
| Duplicate rows (protected types) | 0 |
| Duplicate rows (unprotected: `scheduled_game_cancelled`) | 10 users (known ISSUE-030 gap) |
| Cross-user contamination | None detected |
| Negative unread counts | None detected |
| Push failure blocking notification creation | Not observed |
| Cleanup deleting wrong rows | Not observed |
| Backend errors/crashes | None |

## Performance Baselines (In-Memory)

These are application-logic-only times. Real DB times will be higher.

| Operation | Scale | Time |
| --- | --- | --- |
| game_created fan-out | 100 recipients | 0.001s |
| game_created fan-out | 1,000 recipients | 0.022s |
| GET /notifications/unread-count | 1,000 notifications | 0.009s |
| GET /notifications | 100 rows | 0.008s |
| GET /notifications | 1,000 rows | 0.024s |
| Reminder batch | 200 games x 10 players | 0.057s |
| Retention cleanup | 5,000 old + 5,000 fresh | 0.285s |

## Issues Found

### Critical Issues

**None.**

### Non-Critical Issues / Known Gaps

1. **`scheduled_game_cancelled` has no dedup protection (ISSUE-030).** Confirmed: sequential calls create duplicate notification rows. This is a known gap documented in ISSUE-030. The recommended follow-up (add `scheduled_game_cancelled` to the partial unique index `idx_notifications_user_type_game_unique`) remains the approved fix.

2. **Large inbox payload size.** At 1,000 notifications, `GET /notifications` returns ~240 KB. While functional, this may become a concern for users with very high notification volumes. **Recommendation:** Consider adding server-side pagination as a follow-up if inbox sizes regularly exceed 500 rows.

3. **Retention cleanup at scale.** At 5,000 old rows, in-memory cleanup takes 0.285s. The `lt()` filter scans all rows. On a real database with 100k+ rows, performance depends on whether PostgreSQL uses the `created_at` index efficiently for the `< cutoff` predicate. **Recommendation:** Monitor real cleanup times if the notifications table grows large.

## Follow-Up Recommendations

| # | Recommendation | Priority | Related Issue |
| --- | --- | --- | --- |
| 1 | Add `scheduled_game_cancelled` to unique notifications index | Low | ISSUE-030 |
| 2 | Add server-side pagination to `GET /notifications` | Low | New |
| 3 | Run these stress tests against a real staging database to measure actual DB query latency | Medium | ISSUE-037 future guidance |
| 4 | Add concurrent request testing using a load testing tool (k6, locust) for true race condition validation | Medium | ISSUE-037 scenario 7 |

## Conclusion

The notification system passes all stress test scenarios at the tested load levels. Application logic correctly handles fan-out, dedup, unread counting, inbox retrieval, reminder batching, and retention cleanup. No critical issues were found. The one known gap (`scheduled_game_cancelled` dedup) was confirmed and is already documented in ISSUE-030 with an approved follow-up. The stress test suite is now available as a repeatable pytest suite at `backend/tests/test_notification_stress.py`.
