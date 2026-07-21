# E09-04 Alerting Thresholds Execution Record

Last verified: 2026-07-21

Status: **E09-04 COMPLETE — PRODUCTION ERROR, REGRESSION, CRASH, LATENCY, AND ANALYTICS ALERTING IMPLEMENTED WITH PRIVACY, ENVIRONMENT FILTERING, COOLDOWN, AND LOW-VOLUME SAFEGUARDS**

This record contains no recipient addresses, DSNs, credentials, tokens, or other secrets. `frontend/.env` is intentionally outside the change set.

## 1. Implemented and verified

### Production issue alerts

- Mobile and backend high-priority Issue Alerts are active.
- Each rule is restricted to `environment=production` and uses project email routing with a one-hour action interval.
- Development new-issue and regression exercises both delivered email; receipt and sanitized content were confirmed at 14:32 and 14:37 IDT.
- New and regressed issues remain the dependable notification path if a metric detector does not transition.
- Expected 401/403/404/422/429 responses, permission denial, user cancellation, handled offline failures, and browser-extension noise remain excluded by E09-01 capture policy.

### Production metric monitors

The following production-only monitors are preserved:

| Monitor | ID | Query/aggregate | Window | Warning / critical | Recovery |
|---|---:|---|---|---|---|
| `BE-PROD-Internal-Error-Spike` | 1529849 | unresolved backend errors, `count()` | 10 min | >3 / >10 | <=2 |
| `BE-PROD-Affected-Users` | 1529850 | unresolved backend errors, unique users | 1 h | >3 / >5 | <=2 |
| `MOB-PROD-Error-Spike` | 1529851 | unresolved mobile errors, `count()` | 15 min | >5 / >15 | <=4 |
| `MOB-PROD-Affected-Users` | 1529855 | unresolved mobile errors, unique users | 1 h | >3 / >5 | <=2 |
| `BE-PROD-Analytics-Ingestion-Failure-Spike` | 1529862 | analytics-ingestion backend errors, `count()` | 30 min | >3 / >10 | <=2 |

Production environment filtering and the configured routing were inspected. Development detectors `1532441` and `1532770` counted matching events but did not create the expected state transition: `1532441` remains disabled, and `1532770` is retained as unreliable transition evidence. No warning/critical/recovery email claim is based on those detectors.

### Analytics ingestion

- A valid authenticated `POST /analytics/events` returned HTTP 202 (`accepted_one`).
- Supabase read-only verification found exactly one test row with `app_version=e09-04-test`, `event_name=app_open`, `platform=web`, and `properties={}`.
- The row contained no personal data, coordinates, token, free text, or other sensitive value.
- Contract-invalid events remain rejected by the API and repository tests.
- Dashboard freshness alerting is intentionally excluded: at current volume, no traffic cannot be distinguished reliably from pipeline interruption without a heartbeat system.

### Backend release

Railway production uses a literal full release tied to the deployed commit. The 2026-07-21 deployment was verified with `SENTRY_RELEASE=yesh-mishak-backend@0e65ad9207f3f096f56ad446e9d76f35e20ad37e`. A production Sentry transaction independently confirmed the same release; no synthetic production exception was generated.

### Privacy hardening

`backend/app/monitoring.py` now removes request bodies, cookies, sensitive headers, query strings, fragments, coordinates, `server_name`, SDK `geo`, non-ID user fields, `user.ip_address`, `sys.argv`, `process.argv`, generic `argv`, and explicit command-line fields. Stack local variables are disabled. Release, environment, error code, fingerprint, exception data, and stack frames are preserved.

The final privacy command returned event ID `b8f8a49975a64440bca25d0563eb7b9a`, but that event was not visible by ID or `error_code:E09_04_PRIVACY_FINAL` after the ingestion window. It is recorded as locally queued, not as delivered. No further privacy event was sent. Unit tests provide deterministic coverage of the final filter. Earlier delivered development evidence confirmed readable traceback and SDK-side removal, while city-level Geography remained Sentry transport-IP enrichment even after project IP-storage prevention; it is not an SDK event field.

## 2. Backend latency telemetry

Permanent FastAPI tracing is enabled with environment-aware sampling:

| Environment | Sampling |
|---|---:|
| local, branch-build, preview | 0% |
| development | 100% |
| production | 5% |

Only authentication, fields/map, games, notifications, and analytics-ingestion routes are retained. Raw IDs and URLs are replaced by stable groups such as `REQUEST analytics-ingestion`; unsupported routes are dropped. Request bodies, headers, cookies, query strings, fragments, coordinates, and user text are excluded. Profiling and Session Replay remain off.

Development trace `4f5bd6ad0f02437b84c92d0e3dd66773` was observed in `yesh-mishak-backend` with:

- `environment=development`
- release `yesh-mishak-backend@f9e7bf2aff557089a364579131cba18b8cc69399`
- transaction `REQUEST analytics-ingestion`
- visible duration `0.96ms`

This proves transaction delivery and duration visibility. p95/p99 queries become statistically meaningful after their minimum sampled request counts.

### Production latency rule definitions

Create the same pair for `REQUEST authentication`, `REQUEST fields-map`, `REQUEST games`, and `REQUEST analytics-ingestion`, plus an overall allowlisted-backend view:

| Signal | Filter | Minimum | Warning | Critical | Recovery | Cooldown |
|---|---|---:|---:|---:|---:|---|
| p95 duration | backend + production + selected transaction | 100 sampled requests / 15 min | >1.0s | >2.0s | <1.0s for 30 min | 30 min |
| p99 duration | backend + production + selected transaction | 300 sampled requests / 30 min | >2.5s | >5.0s | <2.5s for 60 min | 60 min |

The minimum-count condition is mandatory. If the current Sentry UI cannot combine percentile and minimum volume safely, retain these definitions as ready-to-enable rules and use the production error Issue Alerts meanwhile.

## 3. Crash-rate and ANR activation guards

The production Release Health view does not yet show a valid 50-session cohort, so percentages are not activated. These definitions are ready for operational activation once at least 50 valid production sessions exist and Sentry can enforce the denominator:

| Rule | Filter/grouping | Warning | Critical | Recovery | Cooldown |
|---|---|---:|---:|---:|---|
| Crash-free users | mobile + production; release where supported; >=50 sessions | <99.5% | <99.0% | >=99.5% for 6 h | 6 h |
| Crash-free sessions | mobile + production; release where supported; >=50 sessions | <99.7% | <99.3% | >=99.7% for 6 h | 6 h |

Before 100 sessions, use denominator-free release safeguards: investigate >=3 crashes affecting >=2 users in the newest release. Never fabricate or reclassify development/branch-build sessions.

The installed `@sentry/capacitor` Android integration includes `AnrIntegration` in its native default integration set, and the application does not disable it. ANRs are therefore covered by native production error monitoring. The ready production percentage rule is `MOB-PROD-Android-ANR`: Android + production + ANR event type, warning >=0.5%, critical >=1.0%, 24-hour window, minimum 200 Android sessions, recovery <0.5% for 24 hours, cooldown 12 hours. No synthetic ANR is required.

## 4. Entitlement and operating model

The organization was on a Business Trial during verification. Active Issue Alerts, project email routing, and the five saved production monitors were visible. Buying or upgrading a plan is outside E09-04. Operations should review entitlements before trial expiry and retain Issue Alerts as the core fallback.

Traffic calibration is normal post-launch maintenance: review after 14 production days and at least 1,000 sessions, then after 30 days and quarterly. Record sampled request counts, false positives, incident duration, release cohorts, crash-free values, and percentile distributions before changing thresholds.

## 5. Test evidence

- Backend: `354 passed` across monitoring/privacy/release/tracing, analytics, manual and Google auth, fields, games, and notifications. Existing warnings: Starlette/httpx deprecation, Supabase `gotrue` deprecation, and short test JWT key warnings.
- Frontend monitoring: `55 passed`; two expected simulated failure logs exercised fail-safe behavior.
- Frontend analytics: `10 passed`.
- Frontend auth interceptor: `6 passed`.
- Android Google client configuration validation: passed.
- Monitoring tests prove production test-trigger exclusion; native package audit proves the ANR integration is present.

## 6. Completion safeguards

- No temporary verification helper, public route, or production crash trigger remains.
- No production synthetic error or ANR was generated.
- No new integration, profiling, Replay, or paid service was enabled.
- No Sentry Support case was submitted and no third development detector was created.
- `frontend/.env` was not staged or committed.
- No merge to `main` was performed.

## 7. Production deployment and merge readiness — 2026-07-21

Decision: **READY TO MERGE — PRODUCTION DEPLOYMENT AND SMOKE VERIFICATION PASSED**

- Deployment window: 2026-07-21 17:08–17:22 IDT.
- Railway source: `codex/e09-04-alerting-thresholds`; active deployed code commit `0e65ad9207f3f096f56ad446e9d76f35e20ad37e`.
- Railway result: deployment successful; Uvicorn startup completed; public health returned HTTP 200 with `{"status":"ok"}`; runtime checks confirmed monitoring enabled, DSN present, `environment=production`, and the exact full release above.
- Production sampling: exactly 5%. Development remains 100%; local, preview, and branch-build remain 0%.
- Vercel: no deployment. The complete E09-04 diff contains no frontend runtime/build change, so the existing E09-01 Sentry variables and source-map pipeline are unaffected.
- Android/iOS: no native configuration or dependency changed. No store release is required; future builds inherit the existing mobile monitoring configuration.
- Supabase: no migration required. The existing `analytics_events` schema accepted the current API contract. The production smoke produced exactly one `e09-04-prod-02afdb2` row with `app_open`, `web`, and `{}`; the invalid event was rejected and stored zero rows.
- Analytics API: valid authenticated batch returned 202 with accepted=1/rejected=0; invalid contract returned 202 with accepted=0/rejected=1.
- Production trace: `01db892948e5471bb9863bf727ad45c1`, transaction `GET fields-map`, environment `production`, exact release above, HTTP 200, root duration 4.84s. The request was not intentionally slowed.
- Trace privacy: normalized `/fields-map`; no request headers, Authorization, cookies, body, query/fragment, coordinates, IP field, hostname, argv, or stack locals. Sentry may still display `user.geo` as transport-side enrichment without an SDK IP/geo field.
- Alerts: both production high-priority Issue Alert workflows retain Email actions, production scope, new/existing high-priority behavior, and one-hour action intervals. All five production metric monitors remain enabled with production filters. No threshold was deliberately breached.

### Rollback

1. In Railway, select the last known-good deployment immediately before `0e65ad9…` and choose Redeploy; do not alter database data or Sentry rules.
2. Set `SENTRY_RELEASE` to `yesh-mishak-backend@<the exact rollback commit SHA>` and deploy that staged variable change with the rollback code.
3. Confirm `/` returns HTTP 200, runtime environment/release checks pass, and Railway logs show clean startup.
4. Confirm Sentry production Issue Alerts remain enabled. Record the rollback trace/release and incident reason.
5. After merge, reconnect Railway production source to `main` only when `main` contains this branch commit or its merge commit; reconnecting earlier would deploy older code.
