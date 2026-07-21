# E09-04 Operational Alert Runbook

Last verified: 2026-07-21. This runbook contains no recipient addresses or secrets. All operational rules are production-only. Never use branch-build, preview, development, local, or controlled test events to satisfy a production threshold.

## Common response

1. Acknowledge P0 within 15 minutes and P1 within four business hours; the owner must confirm after-hours coverage.
2. Open the Sentry issue and confirm project, `environment=production`, release, dist/platform, first/last seen, count, users, and grouping.
3. Check whether Sentry ingestion is delayed or unavailable before treating silence/recovery as application health.
4. For backend alerts, inspect Railway health/logs and the normalized route, then Supabase/provider status. For mobile alerts, inspect release, event origin, device/OS, native versus JavaScript stack, and source-map/symbol status.
5. Assign the issue, link the incident/hotfix, record mitigation, and leave the metric issue open until its configured recovery condition is met.
6. Roll back only when the newest release/deploy clearly correlates with widespread impact, auth/database unavailability, or a launch crash loop. Otherwise isolate/disable the broken feature or ship a focused hotfix.

## Active rules

### Production high-priority issue — mobile

- Source: Sentry Issue Alert, `yesh-mishak-mobile`.
- Trigger: Sentry marks a new or existing issue high priority.
- Filter: `production` only.
- Severity: P1; P0 for widespread launch crash loop/outage.
- Cooldown: one hour per issue.
- Recovery: manual issue resolution after fix verification; regression may retrigger.
- First response: check event origin, release/dist, device/OS, affected users, JS/native grouping.

### Production high-priority issue — backend

- Source: Sentry Issue Alert, `yesh-mishak-backend`.
- Trigger/filter/cooldown/recovery: same lifecycle policy as mobile, production only.
- First response: check Railway, route/status/request ID, release, Supabase and external providers.
- Current caveat: backend release is `unknown`; repair deployment metadata before release comparison.

### `BE-PROD-Internal-Error-Spike` (monitor 1529849)

- Query: unresolved backend error count.
- P2/P1: above 3 / above 10 in 10 minutes.
- Recovery: at or below 2.
- Escalate P0: 25+ in 10 minutes or backend unavailable.

### `BE-PROD-Affected-Users` (monitor 1529850)

- Query: distinct internal users on unresolved backend errors.
- P2/P1: above 3 / above 5 in one hour.
- Recovery: at or below 2.
- Caveat: anonymous/unauthenticated errors may have no user and require the count monitor.

### `MOB-PROD-Error-Spike` (monitor 1529851)

- Query: unresolved mobile error count.
- P2/P1: above 5 / above 15 in 15 minutes.
- Recovery: at or below 4.
- Escalate P0: 40+ in 15 minutes or launch crash loop.

### `MOB-PROD-Affected-Users` (monitor 1529855)

- Query: distinct internal users on unresolved mobile errors.
- P2/P1: above 3 / above 5 in one hour.
- Recovery: at or below 2.
- Caveat: pre-login crashes require count/native evidence because user may be absent.

### `BE-PROD-Analytics-Ingestion-Failure-Spike` (monitor 1529862)

- Query: unresolved backend errors with `transaction:/analytics/events`.
- P2/P1: above 3 / above 10 in 30 minutes.
- Recovery: at or below 2.
- First response: confirm `analytics_events` table/migration and schema cache, Railway logs, Supabase availability, 503 rate, accepted/rejected counts, and E09-03 source status.
- Current known incident: the production table is missing; apply the tracked idempotent migration through the approved Supabase deployment process before expecting recovery.

## Suppression and correlation

- Do not resolve a metric issue while its source remains unhealthy.
- Correlate one Supabase/provider/Railway outage into one parent incident; avoid opening separate incidents for every issue group.
- Expected 401/403/404/422/429, user cancellation, permission denial, and handled offline failures remain excluded by E09-01 policy.
- A newly regressed issue or a new release can require escalation even during the one-hour notification throttle; inspect Sentry history manually when an incident is active.
- No data is unknown, not healthy. Check volume and source availability before closing.

## Deferred rule gates

- Crash-free rate: require real production sessions, at least 100 sessions and 20 users in the window; calibrate after 14 days and 1,000 sessions.
- ANR: require a real ANR event and at least 200 Android production sessions.
- Latency: require an approved source with sample minimums (p95 ≥100, p99 ≥300 requests) and a notification engine.
- Dashboard freshness: require latest-event timestamp and scheduled evaluation, not response-generation time.

## Verification and threshold review

Use non-production clones or approved controlled tests. Verify threshold, recovery, email receipt, environment, release, cooldown, duplicate suppression, and absence of secrets/private text. Never intentionally crash production. Review thresholds after 14 production days and at least 1,000 sessions or 10,000 analytics events, then monthly until stable and quarterly thereafter. Review immediately after a false positive, missed incident, trial expiry, or telemetry/source change.

## Updated production evidence — 2026-07-21

- Analytics ingestion is currently healthy: one valid production `app_open` event returned HTTP `202`, and exactly one matching row with `app_version=e09-04-test`, `platform=web`, and `properties={}` was verified. Treat a future `503 ANALYTICS_UNAVAILABLE` as a new incident.
- Railway production is configured with `SENTRY_RELEASE=yesh-mishak-backend@${{RAILWAY_GIT_COMMIT_SHA}}`, and its replacement deployment completed successfully.
- The resolved release value has not yet been observed on a post-change Sentry event. Do not represent it as verified until the following check passes.

### Pending backend release observation

On the next legitimate backend exception or safe non-production verification opportunity, inspect the Sentry event and record sanitized evidence that:

1. `environment=production`.
2. `release` starts with `yesh-mishak-backend@` and is not `unknown`.
3. The application stack trace is readable.
4. Breadcrumb URLs contain no query strings or fragments.
5. Breadcrumbs and request context contain no Authorization headers, cookies, tokens, passwords, coordinates, request bodies, DSNs, or other secrets.

Do not add a public production test route, temporary production CLI, or synthetic user-flow failure solely to complete this check.
