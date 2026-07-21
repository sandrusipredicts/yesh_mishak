# E09-04 Operational Alert Runbook

Last verified: 2026-07-21. This runbook contains no recipient addresses or secrets. Operational alerts are production-only; `development`, `branch-build`, `preview`, `local`, and test events never satisfy production thresholds.

## Common response

1. Confirm project, `environment=production`, release, platform/dist, event time, issue grouping, count, and affected users.
2. Check Sentry ingestion health before interpreting silence or recovery.
3. Backend: inspect Railway health/logs, normalized route group, Supabase, and provider status. Mobile: inspect release, JS/native origin, device/OS, symbolication, crash-free cohort, and ANR main-thread stack where applicable.
4. Correlate provider/Railway/Supabase outages into one parent incident and suppress duplicate child work.
5. Assign the issue, link the incident or focused fix, and resolve only after the source is healthy.
6. Treat P2 as tracked investigation, P1 as same-day response, and P0 as immediate mitigation for widespread outage, auth/database unavailability, or launch crash loop.

## Active notification path

Mobile and backend high-priority Issue Alerts:

- project-specific, `production` only;
- new and regressed issues;
- project email action;
- one-hour action interval per issue;
- readable stack and release/environment checks required before triage.

Development new-issue and regression exercises both delivered sanitized email. This is the accepted notification-delivery evidence.

## Active production monitors

| Monitor | Warning | Critical | Recovery | Response |
|---|---:|---:|---:|---|
| `BE-PROD-Internal-Error-Spike` (1529849), 10 min | >3 | >10 | <=2 | Railway, Supabase/providers; P0 at 25+ or outage |
| `BE-PROD-Affected-Users` (1529850), 1 h | >3 | >5 | <=2 | identify cohort; pair with count for anonymous traffic |
| `MOB-PROD-Error-Spike` (1529851), 15 min | >5 | >15 | <=4 | top issues/releases/devices; P0 at 40+ or launch loop |
| `MOB-PROD-Affected-Users` (1529855), 1 h | >3 | >5 | <=2 | inspect internal IDs; pair with count before login |
| `BE-PROD-Analytics-Ingestion-Failure-Spike` (1529862), 30 min | >3 | >10 | <=2 | endpoint 5xx/503, Railway, table/schema cache, Supabase |

Development detector `1532441` is disabled. Detector `1532770` is retained as unreliable for state transitions. They are not alert-delivery evidence and must not be cloned again within E09-04.

## Analytics checks

For an ingestion incident:

1. Confirm valid authenticated requests no longer return 202.
2. Distinguish contract rejection from `ANALYTICS_UNAVAILABLE`/503.
3. Check `analytics_events` existence, schema cache, Railway logs, and Supabase availability.
4. Never use response-generation time as latest-event freshness.

Baseline evidence: one valid `app_open` returned 202 and exactly one sanitized `e09-04-test` row was verified; invalid contracts remain rejected.

## Latency operations

Tracing is 5% in production, 100% in development, and off locally/preview/branch-build. Allowed names are `REQUEST authentication`, `REQUEST fields-map`, `REQUEST games`, `REQUEST notifications`, and `REQUEST analytics-ingestion`.

For each selected route group and overall allowlisted backend:

- p95: warning >1.0s, critical >2.0s over 15 minutes, minimum 100 samples, recovery <1.0s for 30 minutes, cooldown 30 minutes.
- p99: warning >2.5s, critical >5.0s over 30 minutes, minimum 300 samples, recovery <2.5s for 60 minutes, cooldown 60 minutes.

Do not activate a percentile rule without its minimum-count guard. Trace `4f5bd6ad0f02437b84c92d0e3dd66773` verifies development delivery, normalized naming, full release, and visible duration.

## Crash and ANR operations

Activate crash-free rules only when a valid production cohort has at least 50 sessions and the denominator can be enforced:

- crash-free users: warning <99.5%, critical <99.0%, recovery >=99.5% for 6 hours, cooldown 6 hours;
- crash-free sessions: warning <99.7%, critical <99.3%, recovery >=99.7% for 6 hours, cooldown 6 hours.

Before 100 sessions, investigate >=3 newest-release crashes affecting >=2 users. Android ANR rule: warning >=0.5%, critical >=1.0%, 24-hour window, minimum 200 Android sessions, recovery <0.5% for 24 hours, cooldown 12 hours. Native ANR collection is supplied by the installed Sentry Android integration.

## Privacy checks

Backend events and transactions must exclude hostnames, command-line arguments, raw IP/geo fields, request bodies, cookies, sensitive headers, query/fragment data, coordinates, local variables, and non-ID user fields. Preserve stack frames, release, environment, error code, and fingerprint.

Sentry may display city-level Geography derived from the transport IP even when the SDK payload has no IP/geo and project IP-storage prevention is active. Record this separately; never infer that the application sent a geo field.

## Release and maintenance

Railway uses `SENTRY_RELEASE=yesh-mishak-backend@${{RAILWAY_GIT_COMMIT_SHA}}`. On each naturally occurring production backend issue, confirm the resolved release starts with `yesh-mishak-backend@`, includes a commit SHA, and is not `unknown`.

Review thresholds after 14 production days and 1,000 sessions, after significant traffic/release changes, and quarterly. Review Sentry plan entitlements before trial expiry. Keep Issue Alerts active as the fallback path and never intentionally crash production for verification.
