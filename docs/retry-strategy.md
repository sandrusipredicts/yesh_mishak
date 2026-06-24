# Retry Strategy

## Scope

This specification defines when yesh_mishak clients should retry failed operations automatically, when they should show a manual retry option, and when retry must not happen.

It applies to the current React frontend and future mobile clients that call the existing backend API. It is a policy document only; it does not change runtime behavior.

Covered API/action categories:

* Notification fetch, unread-count polling, and notification read actions.
* Field and map loading.
* User profile/session/admin identity loading.
* Game actions.
* Field creation and field report submission.
* Admin list loads and moderation actions.
* Push token registration, removal, foreground setup, and test push.
* Auth/session operations.

## Non-goals

This document does not implement retry logic.

It does not:

* Add retry libraries.
* Change frontend runtime behavior.
* Change backend runtime behavior.
* Refactor API clients.
* Change API contracts.
* Add offline action queues.
* Add cache persistence.
* Add service worker or PWA retry behavior.
* Change database schema or migrations.

## API Classification Table

| Category | Current API examples | Request type | Retry classification | Recommended limit | UX expectation |
|---|---|---:|---|---|---|
| Backend health/status | `GET /` | Idempotent read | Manual retry button | User-triggered only | Show visible error and retry button |
| Field/map load | `GET /fields/`, `GET /fields/{id}` | Idempotent read | Auto retry for transient failure, then manual retry | 3 total attempts, 500 ms -> 1.5 s -> 3 s with jitter | Keep map usable when possible; show visible map error after attempts fail |
| Active/upcoming games load | `GET /games/active/`, `GET /games/upcoming/` | Idempotent read | Auto retry for transient failure, then manual retry | 3 total attempts, 500 ms -> 1.5 s -> 3 s with jitter | Show stale/empty state only if clearly labeled; show retry button after failure |
| My games | `GET /games/me` | Idempotent read | Manual retry button; optional auto retry on initial load | 2-3 total attempts if auto retry is added | Show loading, then visible error and retry button |
| User/admin identity | `GET /admin/me`; stored session reads | Auth-sensitive read | Manual retry for network/5xx; no retry for 401/403 | 1 retry max for transient network/5xx | 401 clears session or redirects; 403 shows access denied |
| Notification preferences load | `GET /notifications/preferences` | Idempotent read | Manual retry button; optional auto retry on modal open | 2 total attempts | Show modal error; do not overwrite existing local selections until load succeeds |
| Notification list fetch | `GET /notifications` | Idempotent read | Manual retry button in inbox/modal | 2-3 total attempts | Keep existing list if available; show refresh/retry affordance |
| Unread-count polling | `GET /notifications/unread-count` | Idempotent read / polling | Background polling retry | Next normal poll; no aggressive burst retry | Keep last known count where possible; avoid alarming the user |
| Notification mark read | `PATCH /notifications/{id}/read`, `PATCH /notifications/read-all` | Idempotent-like state update if backend tolerates repeats | Manual retry only | User-triggered only | Optimistic UI may be allowed only with rollback; never spin in background |
| Auth login/register | `POST /auth/login`, `POST /auth/register`, `POST /auth/google` | User-auth action | No auto retry | User-triggered only | Show validation/auth error; keep submit disabled during in-flight request |
| Availability checks | `POST /auth/check-username`, `POST /auth/check-email` | Read-like validation via POST | Debounced/manual retry; optional auto retry for network only | 2 total attempts if auto retry is added | Do not block form permanently on transient failure; no retry for validation result |
| Game creation | `POST /games/` | Non-idempotent create | Retry only after user confirmation and status check | User-triggered only | Prevent double-submit; if timeout occurs, refresh relevant games before allowing retry |
| Game join/leave/extend/close | `POST /games/{id}/join`, `/leave`, `/extend`, `/close` | Non-idempotent or state-changing action | Retry only after user confirmation and status check | User-triggered only | Disable action during request; on failure refresh game state; never auto-retry timeout/network drops |
| Field creation | `POST /fields/` | Non-idempotent create | Retry only after user confirmation | User-triggered only | Prevent double-submit; warn that repeated submission may create duplicates unless backend idempotency exists |
| Field report submission | `POST /field-reports` | Non-idempotent create | Retry only after user confirmation | User-triggered only | Prevent double-submit; keep form data so user can retry manually |
| Notification preference save | `PUT /notifications/preferences` | State update, effectively replace/upsert | Manual retry button | User-triggered only | Disable save during request; show clear success/failure |
| Push token registration | `POST /notifications/push-token` | Token upsert/register | Manual retry button; no hidden repeat loop | User-triggered only | Keep browser permission state separate from server registration result |
| Push token removal | `DELETE /notifications/push-token` | State-changing delete | Manual retry button | User-triggered only | If removal fails, keep local token until server success or clearly show partial failure |
| Test push | `POST /notifications/test-push` | Intentional side effect | No auto retry | User-triggered only | Each click may send a notification; never auto-repeat |
| Foreground push setup | Firebase foreground messaging setup | Local/external setup | Silent best-effort or low-priority retry on app lifecycle | 1 delayed retry max if implemented | Log non-sensitive diagnostic; do not block app usage |
| Admin list loads | `GET /admin/fields`, `/admin/games`, `/admin/users`, `/admin/field-reports`, `/admin/stats` | Idempotent reads | Manual retry button; optional initial auto retry for transient failures | 2-3 total attempts | Keep admin screen stable; show retry button |
| Admin field approval/rejection/status | `POST /admin/fields/{id}/approve`, `/reject`, `PATCH /admin/fields/{id}/status` | State-changing moderation | Retry only after user confirmation and list refresh | User-triggered only | Per-row loading lock; refresh row/list after failure before retry |
| Admin game close/extend | `POST /admin/games/{id}/close`, `/extend` | State-changing action | Retry only after user confirmation and list refresh | User-triggered only | Per-game loading lock; avoid duplicate close/extend |
| Admin user moderation | `POST /admin/users/{id}/ban`, `/unban`, `/suspend`, `/unsuspend` | State-changing moderation | Retry only after user confirmation and user refresh | User-triggered only | Per-user loading lock; require reason again only if action is re-opened |

## Retry Decision Matrix

| Request/action type | Network error | Timeout | 5xx / `DATABASE_ERROR` | 502/503 external service | 429 rate limit | 401 auth | 403 permission | 400/422 validation | 404 not found | 409/business conflict |
|---|---|---|---|---|---|---|---|---|---|---|
| Idempotent GET reads | Auto retry, then manual | Auto retry, then manual | Auto retry, then manual | Auto retry, then manual | Wait `Retry-After` if present, then manual | No retry; re-auth | No retry | No retry | No retry; show missing state | No retry |
| Background polling GETs | Retry on next poll | Retry on next poll | Retry on next poll | Retry on next poll | Back off polling interval | No retry; stop polling until auth fixed | Stop polling | No retry | No retry | No retry |
| Auth login/register | Manual only | Manual only | Manual only | Manual only | Cooldown; manual after wait | No retry; show auth error | No retry | No retry | No retry | No retry |
| Read-like validation POSTs | Optional auto retry once | Optional auto retry once | Manual | Manual | Cooldown | No retry | No retry | No retry | No retry | No retry |
| Non-idempotent user actions | No auto retry | No auto retry | No auto retry | No auto retry unless backend confirms primary action did not happen | Cooldown; manual after wait | No retry; re-auth | No retry | No retry | Refresh state | Refresh state |
| Admin state changes | No auto retry | No auto retry | No auto retry | No auto retry | Cooldown; manual after wait | No retry; re-auth | No retry | No retry | Refresh list | Refresh list |
| Push token operations | Manual only | Manual only | Manual only | Manual only | Cooldown | No retry; re-auth | No retry | No retry | Manual only, depending on action | No retry |
| Test push | No auto retry | No auto retry | No auto retry | No auto retry | Cooldown | No retry | No retry | No retry | No retry | No retry |

## Retryable vs Non-retryable Failures

Retryable failures:

* Browser network error, offline transition, DNS failure, or API unreachable.
* Client timeout on idempotent reads.
* Backend `500` or `DATABASE_ERROR` on idempotent reads.
* Backend `502` or `503` on idempotent reads and external-service setup flows.
* `429` only after the server-provided cooldown, or after a conservative client cooldown if no `Retry-After` exists.

Conditionally retryable failures:

* Timeout or network failure after a state-changing request only after the client refreshes the relevant resource and the user confirms another attempt.
* Read-like validation POSTs, such as username/email availability checks, may retry once for network failure because the operation should not mutate durable state.
* Push token registration/removal may be manually retried because the user explicitly controls the push setup flow.

Non-retryable failures:

* `400` and `422` validation failures.
* `401` authentication failures.
* `403` authorization failures.
* `404` not found, unless the user changes context and deliberately requests a fresh load.
* `409` or business-rule conflicts such as game full, already joined, field closed, or not allowed.
* Any non-idempotent action where the client cannot prove whether the server applied the first attempt.

## Retry Limits

Default automatic retry policy for safe reads:

* Maximum attempts: 3 total attempts, including the initial request.
* Delay: 500 ms before attempt 2, 1.5 s before attempt 3.
* Longer page-level loads may use 500 ms, 1.5 s, 3 s if the initial request is not counted in the delay table.
* Jitter: add random jitter of approximately +/- 20% to avoid synchronized retry bursts.
* Stop retrying immediately when the browser reports offline.
* Stop retrying immediately for non-retryable HTTP statuses.
* Surface a visible UI error after the final failed attempt.

Default manual retry policy:

* One user click starts one request.
* Buttons must be disabled while the request is in flight.
* Retrying a state-changing action must happen only after the UI has shown the latest known resource state or asked for confirmation.

Default polling retry policy:

* Do not add burst retries to polling endpoints.
* On transient failure, wait until the next scheduled poll.
* On repeated failures, increase the polling interval up to a reasonable maximum.
* Resume the normal interval after a successful poll.

Default rate-limit policy:

* Honor `Retry-After` if provided.
* If no server cooldown is provided, wait at least 30 seconds before allowing another automatic read retry.
* Do not automatically retry write actions after rate limiting.

## UX Behavior

Silent background retry is appropriate for:

* Notification unread-count polling.
* Safe GET refreshes when existing visible data remains usable.
* Foreground push setup only if failure does not affect the primary app workflow.

Visible loading state is required for:

* Initial page or modal loads.
* Manual retry clicks.
* Form submissions.
* Admin row actions.
* Game actions.

Visible retry button is required for:

* Failed page-level or modal-level reads after retry attempts are exhausted.
* Admin list load failures.
* My games load failures.
* Notification preferences/list load failures.
* Backend health/status failures.

No retry button is appropriate for:

* Validation errors where user input must change.
* Auth or permission failures.
* Business-rule conflicts.
* Test push auto-repeat prevention.

Stale cached data:

* Allowed for field/map and notification list views only if clearly treated as a temporary fallback.
* Not allowed for form validation, admin moderation decisions, game join/leave/close/extend decisions, or auth/session state.
* Must not be used as proof that a state-changing retry is safe.

User-facing messages after retries fail:

* Network/offline: "No internet connection. Please check your network and try again."
* Timeout: "The connection timed out. Please try again."
* Server/5xx: "A temporary server error occurred. Please try again."
* Rate limit: "Too many requests. Please wait a moment."
* State-changing timeout: "We could not confirm whether the action completed. Refreshing the latest status before retrying."

## Safety/idempotency Rules

* Never auto-retry non-idempotent user actions unless the backend provides a documented idempotency key or equivalent guarantee.
* Disable submit/action buttons while a request is in flight.
* Keep a per-resource loading lock for row-level admin actions and per-game actions.
* After timeout or network loss during a state-changing action, refresh the relevant resource before allowing a retry.
* Do not auto-repeat actions that can create duplicate notifications, duplicate fields, duplicate reports, duplicate games, duplicate moderation audit rows, or duplicate test pushes.
* Avoid optimistic UI for destructive or moderation actions unless rollback behavior is explicit.
* Treat POST endpoints as non-idempotent by default, even when they are conceptually read-like, unless this document explicitly classifies them otherwise.
* Mark notification-read actions may be treated as idempotent-like only if repeating them does not create duplicate rows or side effects.

## Observability and Logging Expectations

Client logging should capture:

* Request category, endpoint family, retry attempt number, final status category, and elapsed time.
* Whether the failure was network, timeout, HTTP status, rate limit, or unknown.
* Whether the user manually retried after a failure.
* Whether retry was skipped because the request was non-idempotent.

Server logging should capture:

* Request path, method, authenticated user ID when available, request ID, sanitized error category, and traceback for 5xx failures.
* External service failures, especially Firebase/FCM failures, without leaking credentials or raw tokens.

Do not expose to users:

* Access tokens, authorization headers, Firebase tokens, Google credentials, passwords, raw Supabase/PostgREST errors, SQL details, stack traces, or internal request bodies.

## Examples

### Notification Fetch

`GET /notifications` and `GET /notifications/unread-count` are safe reads.

Unread-count polling should retry only by waiting for the next poll. It should not show a disruptive error every time a background poll fails. The notification list can show a manual retry button if the user opened the inbox and the fetch failed.

Mark-read operations should not auto-retry in the background. A failed mark-read can show a visible error and allow the user to click again.

### Field Load

`GET /fields/` and `GET /fields/{id}` are idempotent and can use automatic retry for network, timeout, and 5xx failures.

After the automatic attempts fail, the map should show a visible error and a manual retry option. The app may keep already loaded fields visible, but must not present stale data as newly refreshed.

### User Profile

Stored local session data is not retried because it is local state.

`GET /admin/me` and future `GET /me` style endpoints should retry only for transient network or 5xx failures. `401` must clear or refresh the session flow. `403` must show access denied and must not retry.

### Game Join

`POST /games/{id}/join` is a state-changing action. It must not be automatically retried after network loss or timeout because the first request may have succeeded.

If join fails with a transient error, the UI should refresh the game state, show whether the user is already joined or whether the game is full, and allow another user-confirmed attempt only if the latest state still permits joining.

### Field Creation

`POST /fields/` creates a pending field and may create duplicates if repeated. It must not be automatically retried.

The form should keep the user's input after a transient failure and let the user retry manually. Submit must be disabled while the request is in flight. If the request timed out, the app should warn that the previous attempt may have succeeded before allowing another submission.

### Admin Moderation

Admin actions such as approve/reject field, update field status, close/extend game, and ban/suspend/unban/unsuspend user are state-changing and may write audit records or send notifications.

They must not be automatically retried. The UI should lock the relevant row while the action is in flight. On failure, refresh the list or row before allowing another admin-confirmed attempt.

## Recommended Follow-up Implementation Issues

1. Add a shared frontend retry helper for idempotent GET requests only, with status-aware stop conditions.
2. Add or standardize manual retry buttons for remaining page/modal read failures.
3. Add request timeout handling in the shared API client with user-facing timeout messages.
4. Add rate-limit cooldown UI that honors `Retry-After`.
5. Add state refresh before manual retry for game actions and admin moderation actions.
6. Add structured client-side logging for retry attempts without exposing secrets.
7. Add backend idempotency keys for selected create/action endpoints if future auto retry for writes becomes necessary.
8. Add mobile-specific stale data and local cache policy before implementing mobile offline persistence.

## Definition of Done Checklist

* Retry strategy document exists at `docs/retry-strategy.md`.
* Every current API/action category is classified.
* Retryable and non-retryable failures are defined.
* Retry limits, backoff, jitter, and stop conditions are defined.
* UX expectations are defined for silent retry, visible loading, manual retry, stale data, and user-facing errors.
* Safety and anti-duplication rules are defined.
* Observability/logging expectations are defined.
* Product decisions document references this specification.
* No runtime behavior is changed by this specification.

## Implementation Status

ISSUE-064 implements the first narrow frontend retry pass:

* Shared helper: `frontend/src/api/retry.js`.
* Auto-retry applied only to field/map loads and active/upcoming games reads.
* Non-idempotent actions, auth flows, admin actions, notification writes, push operations, backend health, MyGames, admin list loads, notification preferences/list loads, and unread-count polling remain manual/no-retry per this strategy.
