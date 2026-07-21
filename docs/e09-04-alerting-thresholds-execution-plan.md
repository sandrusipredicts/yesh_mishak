# E09-04 — Alerting Thresholds Execution Plan

Status: **READY WITH BLOCKERS**

Planning branch: `codex/e09-04-alerting-thresholds-plan`

Starting `main` commit: `5167afa209d033ac54158db26b4a0f626be8072d`

Audit date: 2026-07-21

Recommended implementation branch (not created): `codex/e09-04-alerting-thresholds`

This is an audit and implementation-ready plan. It does not authorize or perform any Sentry, telemetry, application, or production change. Statements marked **repository-confirmed** come from the commit above. Statements marked **dashboard-unverified** require the owner to inspect the live Sentry organization. Package presence alone is not treated as proof that a telemetry stream exists.

## 1. Executive summary

E09-01 provides a sound error-event foundation: React/Capacitor errors, React Error Boundary failures, Android native crashes, and explicitly captured unexpected FastAPI exceptions can reach separate mobile and backend Sentry projects. Local reporting is off by default; deployed builds with a DSN report; Android branch builds use `environment=branch-build`; production must be explicitly tagged. Android JS, Error Boundary, and native crash delivery were physically verified. iOS and live Railway-to-backend delivery remain unverified.

Error alert implementation can begin after the owner audits the live projects, subscription, recipients, and existing rules. Backend rules cannot be enabled until a protected non-production Railway event is observed with correct tags. Crash-rate alerts cannot be enabled until real Release Health session data is visible and statistically meaningful. Latency alerts cannot be built from current Sentry telemetry because both SDKs set `tracesSampleRate: 0` and no repository evidence shows transactions/spans. Therefore:

- **Latency decision: C — latency collection is a separate prerequisite task.**
- **Crash-rate decision: C — crash-rate collection requires a prerequisite task unless the dashboard audit proves valid Release Health sessions already exist.** This conservative decision is based on absent repository configuration and absent owner/dashboard evidence, not an assertion that the bundled native SDK cannot auto-track sessions.
- **Final readiness: READY WITH BLOCKERS.** The error-alert subset is implementation-ready after owner decisions; backend, crash-rate, ANR-rate, plan-specific metric, and latency rules remain gated.

## 2. Current repository state

The audit started after fetching `origin`, fast-forwarding local `main` to `5167afa209d033ac54158db26b4a0f626be8072d`, and confirming local `main` matched `origin/main`. The only pre-existing working-tree change was `frontend/.env`. It was preserved exactly, excluded from inspection output used in this document, and must never be staged or committed. This planning branch changes documentation only.

## 3. E09-01 implementation baseline

Repository-confirmed baseline:

| Layer | Initialization/capture | Environment/release | Safety |
|---|---|---|---|
| React/Capacitor | `frontend/src/monitoring/index.js`; `@sentry/capacitor` wrapping React/native | explicit `VITE_SENTRY_ENVIRONMENT`, `VITE_SENTRY_RELEASE`, `VITE_SENTRY_DIST`; safe fallbacks | `sendDefaultPii:false`, redaction, expected-error filters, tracing 0 |
| React boundary | `ErrorBoundary.componentDidCatch` calls wrapper `captureException` | inherits current scope | safe no-op if disabled |
| Android native | Capacitor Sentry Gradle module; shared init; `nativeCrash()` test gate | branch CI injects release/dist/environment | physical JS/boundary/native delivery verified |
| iOS preparation | shared JS design, workflow dSYM upload guard, Xcode dSYM format | planned `ios-branch-<run>` dist | package resolution/build/delivery not verified; current checked-in SPM manifest has no Sentry dependency |
| FastAPI | `backend/app/monitoring.py`; exception handlers explicitly capture unexpected exceptions | explicit `SENTRY_ENVIRONMENT`/`SENTRY_RELEASE` | bodies/cookies/query removed, sensitive fields redacted, tracing 0, auto-5xx capture disabled to prevent duplicates |
| Source maps | guarded Vite plugin, hidden maps, upload/delete when token exists | same frontend release/dist variables | token is CI-only secret; missing token skips upload |

E09-01’s real Android verification is evidence that event delivery and tags worked for that branch artifact, not proof of current production volume, sessions, ANRs, alerts, quota, or every future release.

## 4. Existing mobile telemetry

Currently collected when monitoring is enabled:

- Unhandled JavaScript exceptions captured by the Sentry runtime.
- React render errors captured by the Error Boundary.
- Explicit exceptions/messages through the monitoring wrapper.
- Android native crashes through the Capacitor native integration; a real test was observed.
- Breadcrumbs and safe device/OS/app context supplied by the SDK after redaction.
- Internal user ID only, set/cleared through the wrapper’s user lifecycle; no email or username is intended.
- Tags include environment, release, dist, build type, and best-effort native app version/build.

Not repository-proven: production events currently arriving, iOS events, session envelopes, crash-free values, ANRs, transactions, profiles, replay, or adoption metrics.

## 5. Existing backend telemetry

`init_monitoring()` enables reporting only when a DSN exists and the resolved environment is non-local, or local override is explicitly true. FastAPI/Starlette automatic failed-status capture is disabled. The application exception handlers call one explicit capture point for unexpected exceptions and attach safe tags: request ID, normalized route supplied by the caller, method, status, and error code. Expected HTTP outcomes are not automatically reported merely because they are 4xx/5xx responses. `capture_unexpected_message` exists for deliberate call sites.

Production configuration is documented for Railway, but a real Railway event has never been owner-confirmed in the backend project. Thus code readiness is **yes**; live production delivery is **dashboard-unverified**.

## 6. Existing Release Health/session state

No explicit `autoSessionTracking`, session start/end API, or Release Health configuration appears in application code. A bundled mobile SDK may have version-specific native defaults, but package presence/default documentation is insufficient evidence. The authoritative test is the live mobile project: Releases → a real release → Release Health, with non-test production sessions and plausible counts.

Current status of sessions, crashed sessions, abnormal sessions, adoption, crash-free users, and crash-free sessions: **dashboard-unverified and unavailable for alert design until observed**.

## 7. Existing latency/transaction state

Both frontend and backend initialize Sentry with `tracesSampleRate: 0`. No custom transaction/span/measurement calls were found in the E09-01 monitoring path. Therefore Sentry Performance cannot currently be relied on for transaction duration, p50, p75, p95, or p99. The repository has separate API request/response-time metric infrastructure, but this audit found no evidence that it feeds an operational alerting service; it is not a substitute until its retention, coverage, query, and notification path are validated.

## 8. Existing ANR state

Android native integration can potentially report ANRs depending on the resolved native SDK version/defaults and runtime configuration. No explicit ANR enablement, timeout, rate, or test is present, and no live ANR observation was supplied. ANR count/rate is therefore **dashboard-unverified**. Do not create an ANR-rate rule until an event or documented test confirms event type, environment, release, and session denominator.

## 9. Existing Sentry alert state

Repository documentation contains earlier suggested alerts, but the repository cannot reveal live issue/metric monitors, migrated rules, default rules, recipients, notification preferences, or ownership. In 2026 Sentry’s UI may describe threshold detection as Monitors and notification routing as Alerts; the implementation owner must map this plan to the live UI. No alert was created or changed during this task.

## 10. Current plan/quota capability

Subscription name, trial expiry, paid entitlements, error quota, span quota, retention, notification limits, spike protection, and metric-monitor availability are **unknown until owner inspection**. Product packaging changes over time. Before implementation, record screenshots/date and obtain a post-trial entitlement answer for every selected feature. Do not rely on a trial-only option.

Owner audit checklist:

1. Organization Settings → Subscription/Usage: plan, trial end, error quota, span quota, retention, on-demand spend, spike protection, and current usage.
2. Mobile and backend Settings/Alerts/Monitors: existing/default rules, available condition types, action channels, and edit permissions.
3. Notification settings: alert emails enabled for primary and backup; project/team notifications not muted.
4. Projects/Teams: project ownership, team membership, primary and backup recipients.
5. Test whether error-count, unique-user, crash-free, percentile/span, no-data, quota, and recovery notification conditions are actually selectable on the post-trial plan.

If any required metric monitor is unavailable, retain issue alerts and create an operational dashboard/manual weekly review; do not approximate a percentage with misleading low-volume counts.

## 11. Monitoring gaps

- Backend live delivery and tags not verified.
- iOS dependency resolution, native delivery, sessions, and dSYM symbolication pending.
- Production session/Release Health evidence absent.
- Transactions/spans deliberately absent.
- ANR evidence absent.
- Live alerts, recipients, ownership, subscription, quota, retention, and notification preferences unknown.
- Production frontend release injection is documented as an external wiring step and must be rechecked; missing/`unknown` release impairs release regression rules.
- Frontend and backend use compatible release format only when deployment injects the same commit-derived value; compatibility is designed, not live-proven.
- No Sentry-native uptime/no-data telemetry is proven. Railway health/logs or a separately approved uptime monitor may be needed.

## 12. Scope included

Audit, threshold recommendations, environment filters, rule inventory, decision gates, owner checklist, privacy/cost analysis, incident mapping, test design, and documentation-only implementation sequencing.

## 13. Scope excluded

No alert/monitor creation, tracing, sampling change, profiling, Replay, product analytics, SDK addition, code behavior change, production test crash, public crash endpoint, external integration, dependency installation, implementation branch, merge, or push.

## 14. Error-alert architecture

Use Issue Alerts for discrete lifecycle signals: new fatal/unhandled issue, regression, new native crash, and new unexpected backend exception. Use Metric Monitors only for aggregation: repeat volume, affected users, failure counts/rates, or rapid release spikes. A new issue alert should not fire for every event in that issue.

Minimum initial set after prerequisites:

1. Mobile production new fatal/unhandled issue (P1).
2. Mobile production resolved-issue regression (P1).
3. Backend production new unhandled exception (P1; after live delivery verification).
4. Backend production resolved-issue regression (P1; after verification).
5. Mobile repeated-error spike (P1/P0 thresholds, if metric monitors supported).
6. Backend internal-error spike (P1/P0 thresholds, if supported).

Crash-rate, ANR, latency, unique-user, and release-regression metric rules are added only after denominators/queries and entitlements are proven.

## 15. Crash-rate architecture

Primary production SLO recommendation: **crash-free users**, supported by crash-free sessions and native-crash count. Users best represent impact and avoid one looping user dominating the headline; sessions detect launch/restart loops faster; native crash count is a denominator-free backstop. Never use native crash count alone as the SLO.

Low-volume guard: do not evaluate percentage rules below 100 production sessions and 20 distinct production users in the chosen window/release. Before that, use new native fatal Issue Alerts and a count spike requiring at least 3 events and 2 affected users. Exclude branch-build/development events and documented protected test events.

## 16. Latency-alert architecture

Decision C makes latency telemetry a separate prerequisite. That issue must choose one source of truth and validate route normalization. Recommended initial scope is backend only: overall API plus authentication, fields/map, game create/join, and notifications. Frontend startup/map initialization and dependency/database spans are phase two after privacy/quota validation.

Do not enable tracing under E09-04. When separately approved, begin with an evidence-based low sample rate (provisional candidate 5% production, 100% protected non-production test traffic), cap/estimate spans, exclude sensitive parameters, normalize routes, and measure overhead. Final sampling belongs to the prerequisite, not this plan.

## 17. Issue Alerts versus Metric Alerts

| Situation | Mechanism | Reason |
|---|---|---|
| New fatal/unhandled issue | Issue Alert | lifecycle event; immediate triage |
| Resolved issue regresses | Issue Alert | built-in regression semantics |
| First Android native crash | Issue Alert | high signal without denominator |
| First backend unexpected exception | Issue Alert | high signal; explicit capture |
| Repeated single issue | Metric Monitor | count/window aggregation and cooldown |
| Many users affected | Metric Monitor | unique-user aggregation |
| Error/5xx spike | Metric Monitor | volume/rate aggregation |
| Crash-free degradation | Metric Monitor | session/user denominator |
| p95/p99 latency | Metric Monitor | span percentile aggregation |
| P3 information | Digest/dashboard | avoid interrupt noise |

## 18. Environment strategy

Actual tags are `local`, `development`, `branch-build`, and `production`. Frontend absent explicit tag defaults to local on dev server and development otherwise; backend defaults to local. Every immediate rule must filter `environment:production`. Where the UI supports negative guards, also exclude `local`, `development`, `branch-build`, and any future `preview`. Rules must fail closed if environment is missing: quarantine/mute the event and create a configuration defect, never treat it as production. Branch-build rules, if desired, route to a non-operational digest only. Test crashes never enter production.

## 19. Severity model

| Severity | Meaning | Response | Routing/after hours |
|---|---|---|---|
| P0 | widespread outage/crash loop or critical release regression | acknowledge ≤15 min; mitigate ≤60 min | primary + backup email; owner must explicitly decide after-hours coverage |
| P1 | urgent production defect with credible impact | acknowledge ≤4 business hours; investigate same day | responsible owner email; backup on no acknowledgement |
| P2 | contained/low-impact degradation | review next business day, target disposition ≤3 business days | owner email digest/low-urgency route |
| P3 | informational | weekly digest only | no immediate email |

Email is the only approved initial destination. Names, addresses, mobile/frontend owner, backend owner, backup, and after-hours promise are owner decisions.

## 20. Provisional thresholds

All values are recommendations for owner review, production-only, and explicitly provisional.

| Signal | P2/warning | P1/critical | P0 | Window/minimum | Cooldown | Recovery |
|---|---:|---:|---:|---|---|---|
| Single mobile issue events | 3 | 10 | 25 | 15 min; ≥2 users for P1 unless fatal | 60 min | <2/15 min for 30 min |
| All mobile error events | 5 | 15 | 40 | 15 min; ≥2 users for P1 | 60 min | below warning for 30 min |
| Android native crashes | 2 | 5 | 10 | 30 min; or ≥3 in newest release | 60 min | 0 for 60 min |
| Backend unexpected/5xx captures | 3 | 10 | 25 | 10 min; exclude expected statuses | 30 min | <2/10 min for 30 min |
| Auth internal failures | 2 | 5 | 10 | 10 min; never count ordinary 401/403 | 30 min | 0 for 30 min |
| Crash-free users | <99.5% | <99.0% | <97.0% | rolling 24 h; ≥20 users and ≥100 sessions | 6 h | ≥99.5% for 6 h |
| Crash-free sessions | <99.7% | <99.3% | <98.0% | rolling 24 h; ≥100 sessions | 6 h | ≥99.7% for 6 h |
| ANR rate | ≥0.5% | ≥1.0% | ≥2.0% | 24 h; ≥200 Android sessions | 12 h | <0.5% for 24 h |
| Core endpoint p95 | >1.0 s | >2.0 s | >5.0 s | 15 min; ≥100 sampled tx | 30 min | <1.0 s for 30 min |
| Core endpoint p99 | >2.5 s | >5.0 s | >10 s | 30 min; ≥300 sampled tx | 60 min | <2.5 s for 60 min |

Issue lifecycle alerts have no warning threshold: new fatal/unhandled or regression is P1, deduplicated by issue, with a 60-minute action interval. Escalate to P0 only when volume/user/release criteria independently cross P0.

## 21. Baseline/calibration strategy

Use a hybrid gate suited to low launch volume: calibrate after **14 production days and at least 1,000 valid production sessions**, whichever occurs later. For user-based thresholds also require at least 100 active users; if that takes more than 30 days, review counts manually at day 30 but do not declare percentage thresholds calibrated. Each release gets at least 48 hours or 100 sessions before release-specific percentages, except count-based fatal rules remain active immediately.

At calibration record daily events, unique users, crash-free users/sessions, p50/p75/p95/p99, traffic and peak-hour variation, release cohorts, false positives, alert duration, and recoveries. Compare weekdays/weekends and latest versus prior release. Approve threshold changes in a short decision record and schedule 30-day review, then quarterly review.

## 22. Warning and critical thresholds

Warnings create P2 work without paging. Critical thresholds route P1. P0 is reserved for clearly widespread conditions or release crash loops and requires stronger counts/denominators. Do not derive P0 from a single user/session percentage. When the live Sentry UI permits one threshold per monitor, create paired warning/critical monitors only if their notifications can be deduplicated; otherwise use one critical monitor and dashboard warning review.

## 23. Cooldown strategy

Issue alerts notify once on creation/regression, then suppress repeat activity for 60 minutes. Mobile/error metric alerts use 60 minutes; backend spikes 30 minutes; crash-free 6 hours; ANR 12 hours; latency 30–60 minutes. A cooldown suppresses repeat notification for the same continuing breach, not a new regression/new release/P0 escalation. If the product cannot express that exception, document manual escalation rather than duplicating rules.

## 24. Recovery-notification strategy

Enable recovery only where recipients can receive it and the metric can sustain a healthy period. Use the recovery values in §20, never “one healthy sample.” Issue resolution is manual after fix verification; it is not metric recovery. A manually resolved issue that remains unhealthy must regress/reopen and notify according to the regression rule. During testing, prove both breach and recovery email delivery.

## 25. Alert-fatigue prevention

- Alert on new/regressed issue, not every event; add count and unique-user minima.
- Let Sentry grouping deduplicate, but inspect split fingerprints and cross-layer duplicates.
- Filter production exactly; isolate branch tests and future iOS dist.
- Continue E09-01 filtering for cancellations, permission denial, expected 401/403/404/422/429, handled offline/network errors, and extension noise.
- Treat provider/Railway/Supabase outages as correlated incidents: one parent incident, suppress child issue storms after root cause is known.
- Use separate warning/critical and sustained recovery; avoid P3 immediate mail.
- Do not alert on rate limiting/validation unless a separate aggregate rule proves abnormal volume and product impact.
- If quota/ingestion/Sentry outage occurs, monitoring becomes “unknown,” not healthy.

## 26. Mobile alert rules

| Alert | Type/filter | Threshold | First step / escalation |
|---|---|---|---|
| `MOB-PROD-New-Fatal` | Issue; mobile; `environment:production`; fatal/unhandled | once/new issue; P1; 60m action interval | open event, release/device/OS/dist; P0 at ≥25/15m or launch loop |
| `MOB-PROD-Regression` | Issue; production; regressed | once/regression; P1 | compare fixed/current release and fingerprint; rollback if newest release widespread |
| `MOB-PROD-Error-Spike` | Metric; production errors | 5 warning, 15 critical, 40 P0/15m | group top issues/users; suppress expected outage children |
| `MOB-PROD-Native-Crash` | Issue + metric; platform Android/native | new crash P1; 2/5/10 per 30m | inspect native stack/symbolication; rollback P0 release loop |
| `MOB-PROD-Affected-Users` | Metric; production | provisional ≥3 warning, ≥5 critical/1h | validate internal user IDs; assess cohort |

Initial implementation should create only the first two plus native new-crash lifecycle alert; add metrics after entitlement/query verification.

## 27. Backend alert rules

| Alert | Type/filter | Threshold | First step / escalation |
|---|---|---|---|
| `BE-PROD-New-Unhandled` | Issue; backend; `environment:production`; unexpected exception | once/new; P1 | open issue, request ID/route; check Railway logs/health |
| `BE-PROD-Regression` | Issue; production; regressed | once; P1 | compare deploy/release and root cause |
| `BE-PROD-Internal-Spike` | Metric; status 500/error captures | 3/10/25 per 10m | Railway then Supabase/dependencies; P0 if unavailable |
| `BE-PROD-Auth-Internal` | Metric; normalized auth routes, internal errors only | 2/5/10 per 10m | validate login/refresh; ordinary auth denial excluded |
| `BE-PROD-Integration` | Metric; safe error code/provider tag | 3 warning, 10 critical/30m | check provider status; parent incident on outage |

No backend rule is enabled before §32 verification.

## 28. Release-specific alert rules

Require non-`unknown` release and valid dist. Compare latest production release with prior stable cohort. For the first 100 sessions use count rules (≥3 crashes and ≥2 users); afterward allow percentage thresholds. Old versions remain visible but do not cause latest-release rollback unless the same regression affects them. Missing release creates P2 configuration work, not an operational page.

## 29. ANR alert rules

Deferred until real ANR event/session denominator and plan feature exist. Proposed `MOB-PROD-Android-ANR`: production + Android + ANR event type; P2 ≥0.5%, P1 ≥1%, P0 ≥2% over 24 hours with ≥200 sessions; 12-hour cooldown; recovery <0.5% for 24 hours. Inspect device/OS/main-thread stack and latest release. Never equate ANR absence with zero if ANR collection is unverified.

## 30. Recipient and ownership model

Owner must record, without committing private addresses:

- Primary operational email and backup email.
- Mobile/frontend owner and backend owner.
- Who acknowledges, assigns the Sentry issue, opens the incident/hotfix, resolves, and handles regression.
- P0 after-hours coverage and what happens when the primary is unavailable.

Proposed flow: recipient replies/marks acknowledged in the agreed channel, assigns the Sentry issue to the responsible owner, links a tracker/hotfix, posts mitigation, verifies recovery, then resolves. Backup takes P0 after 15 minutes and P1 after four business hours if unacknowledged. This timing is not binding until owner approval.

## 31. Incident-response mapping

Every configured rule must copy its row from §§26–29 into its description/runbook URL. Common diagnostics: open issue; confirm production/environment/release/dist; inspect affected users/devices/OS; compare release volume; check Railway health/logs; check Supabase and push/email provider status; identify Sentry ingestion delay; choose rollback, feature disablement, or hotfix. Escalate P0 on widespread impact, auth/database unavailability, launch crash loop, or thresholds in §20. P2 produces a tracked issue; P1 same-day investigation; P0 immediate mitigation.

## 32. Backend live-event prerequisite

Planning may finish, but backend alert rules are not finalized/enabled until one protected real deployed event appears in `yesh-mishak-backend` with expected environment, release, stack, route, and redaction.

Safe procedure:

1. Create/use a temporary non-production Railway service or protected staging deployment with `SENTRY_ENVIRONMENT=development` (never production), a non-production DSN/project routing as approved, and the existing test route available.
2. Restrict access using existing deployment authentication/network controls; do not expose a public crash endpoint.
3. Confirm the deployed commit/release value without printing DSN/token.
4. An authorized owner calls `GET /__test/sentry-trigger` once through the protected path.
5. Confirm expected 500 response and normal API behavior; then find exactly one backend Sentry event.
6. Verify project, environment, release, route/method/status/error code, readable stack, and absence of bodies, query, cookies, authorization, tokens, coordinates, private text, and secrets.
7. Remove/disable access by removing the temporary deployment or returning it to production-gated configuration. The route is already absent when environment resolves to production.
8. Record event ID/date/screenshots in a private verification record, not this repository if it contains sensitive context.

Only then reproduce the intended production filters in a disabled/draft rule and obtain owner approval before enabling.

## 33. Latency telemetry decision

**Decision C: latency collection is a separate prerequisite task.** Current transactions/spans are deliberately zero. Enabling useful backend/frontend tracing, route normalization, sampling, quota forecasting, and privacy review is materially larger than alert configuration. See follow-up issue LAT-PREREQ in §51.

## 34. Crash-rate telemetry decision

**Decision C: crash-rate collection requires a prerequisite task unless live dashboard evidence upgrades it to A.** Repository evidence does not prove sessions. If the owner observes credible production Release Health data across ≥100 sessions, records SDK/platform/release coverage, and validates crash attribution with a protected non-production test, change the implementation decision to **A: sessions already collected** without code changes. If sessions are absent/incomplete, do not fold behavior changes silently into alert configuration; execute CRASH-HEALTH-PREREQ.

## 35. Tracing/session sampling decision

Tracing remains 0 in this task. No transaction/span sampling change is authorized. Error events remain governed by current SDK behavior. Session sampling is not guessed: audit whether sessions are full-count envelopes and what SDK controls exist. Any enable/correction requires owner-approved scope, quota/cost/privacy/overhead test, rollback, and separate implementation.

## 36. Privacy review

E09-01 sets `sendDefaultPii:false`; removes request bodies, cookies, and query strings; strips URL query/fragment; redacts authorization/token/password/secret/credential/DSN/push-token/verification keys and exact coordinate keys; and retains only internal user ID. Expected filters reduce benign sensitive context. This is a strong baseline but notification email may include title, exception message, culprit, breadcrumbs, tags, and excerpts depending on Sentry templates/settings.

Before enabling email, send one synthetic non-production event containing sentinel values in every prohibited category and inspect the event plus received email. Also test free-form exception messages and breadcrumb message text, because key-based redaction does not guarantee arbitrary string content is safe. If any sentinel leaks, block alerts and fix redaction/capture discipline first. Never include password, access/refresh/Google tokens, authorization/cookies, push tokens, coordinates, bodies, verification links/tokens, private text, DB credentials, DSNs, or environment secrets. Use internal user ID only.

## 37. Cost and quota review

Errors consume error quota; tracing would consume spans/transactions and can multiply volume per request; Release Health/alerts and retention depend on current packaging. Exhausted quota or spike protection can drop/delay telemetry and make alerts falsely silent. Sampling reduces cost but changes percentile confidence and count interpretation. Before implementation:

- Capture plan, trial end, quotas, retention, overage behavior, spike protection, notification/monitor entitlements, and 30-day usage.
- Estimate errors/day from baseline; estimate spans as sampled requests × average spans/request × 30 days before any tracing approval.
- Reserve headroom (recommended ≥50% at launch) and create a manual weekly usage check or supported quota warning.
- Decide whether overages are disabled; document consequence and owner.
- Recheck after trial expiry and at 50/75/90% usage.

No plan-specific numeric entitlement is asserted by this repository audit.

## 38. File-by-file/configuration plan

Expected implementation changes, only where the prerequisite proves necessary:

| File/config | Proposed future change | Gate |
|---|---|---|
| Sentry mobile/backend dashboards | minimal rules from §§26–27 | owner/plan/filter approval |
| `docs/sentry-configuration-guide.md` | replace legacy suggestions with approved rule names/filters | after configuration |
| `docs/crash-reporting-incident-workflow.md` | severity, acknowledgement, recovery, ownership | owner decision |
| new alert runbook/checklist | IDs, links, test evidence, review cadence | no secrets/addresses |
| frontend monitoring config | only explicit session correction if prerequisite proves absent | separate approval |
| backend/frontend monitoring | no tracing here; prerequisite-owned implementation | LAT-PREREQ |
| CI/deploy variables | ensure production environment/release/dist only | owner deploy audit |

Prefer manual initial configuration. No production-code change is expected for error lifecycle alerts.

## 39. Sentry manual-configuration plan

1. Owner completes dashboard/plan/recipient audit and records decisions.
2. Verify projects, production events/tags, release metadata, sessions/ANRs/transactions, and backend prerequisite.
3. Inventory existing/default rules; disable nothing without separate approval; identify duplicates.
4. Create draft/disabled minimum rules with exact production filters and descriptions/runbooks.
5. Peer-review query, threshold, cooldown, recovery, recipient, plan entitlement, and privacy.
6. Test using non-production clones routed to the same approved test email; never loosen production filters on the real rule.
7. After evidence, reproduce reviewed configuration for production and obtain explicit owner enablement approval.
8. Screenshot/export rule definitions and add sanitized configuration record.
9. Review after 24 hours, 7 days, calibration gate, trial expiry, and each material release.

## 40. Optional automation/API plan

Not recommended initially: there are few rules, UI capabilities/2026 naming may evolve, and manual review is safer while thresholds are provisional. If rule drift or multi-project repetition later justifies automation, create a separate issue. Use a scoped organization token stored only in GitHub secrets/approved secret manager, least scopes needed to read/write monitors/alerts, never a tracked token. Require read-only inventory and JSON diff dry run, stable rule keys, idempotent create/update, no delete by default, secret scanning, test organization/project, rollback from exported definitions, and owner approval. Manual configuration is insufficient only once drift/repeatability measurably causes errors.

## 41. Environment variables and secrets

Existing public/deploy metadata: mobile DSN, environment, release, dist; backend DSN is server-side deployment configuration. `SENTRY_AUTH_TOKEN` is secret. Future automation token is a separate least-privilege secret. Never print or commit values. Alerts must filter the actual environment tags and reject missing production metadata. No new variable is needed for initial error rules.

## 42. Edge-case matrix

Legend: “manual” means owner/dashboard verification is mandatory. Tests use synthetic non-production data, query previews, or disabled clones—never an intentional production crash.

| # | Edge case | Expected behavior / fire? / severity | Suppression & test / manual |
|---:|---|---|---|
| 1 | No production events | unknown, not healthy; no percentage alert; P2 readiness blocker | query empty project; manual |
| 2 | Extremely low traffic | count lifecycle only; no rate page | denominator gates; replay/query preview; manual |
| 3 | One test crash gives 0% | no production alert | non-prod environment + min sample; protected test; manual |
| 4 | Branch test event | never production page | exact env filter; branch trigger; manual email check |
| 5 | New release one session | count rule only, no rate | ≥100 sessions/48h; query preview; manual |
| 6 | Sessions missing | crash-rate disabled; blocker | no-data shown as unknown; dashboard audit; manual |
| 7 | Transactions missing | latency disabled; blocker | Decision C; Performance audit; manual |
| 8 | Trial expires | retain only proven post-trial rules; P2 operational risk | entitlement review before/after date; manual |
| 9 | Metric alerts unavailable | issue alerts + dashboard review only | do not fake metric; UI entitlement test; manual |
| 10 | Email disabled | rule not ready; P1 config defect | test email and preferences; manual |
| 11 | Preferences suppress alert | rule not ready | primary+backup test; manual |
| 12 | Rule has no recipient | keep disabled; P1 config defect | configuration review/test; manual |
| 13 | Resolved issue regresses | fire P1 once | regression rule, 60m; resolve/test clone; manual |
| 14 | Fingerprint changes | may create new P1 issue; correlate manually | grouping review; synthetic variants; manual |
| 15 | Same bug JS/native | one incident, alerts may both fire | dedupe in incident process; paired test; manual |
| 16 | Backend root cause splits groups | metric spike + one parent incident | suppress children after correlation; synthetic groups; manual |
| 17 | Third-party outage | aggregate P1/P0 by impact; expected retries P2/no page | provider tag/cooldown; mocked outage; manual |
| 18 | Railway restart spike | P1 only if sustained/count crossed | 10m window/30m cooldown; staging restart; manual |
| 19 | Supabase outage | backend P0 if unavailable/widespread | parent incident; mocked failure/status check; manual |
| 20 | Frontend network loss | no operational error alert for handled offline | existing filter; offline test; manual |
| 21 | Launch crash loop | P0 count/session signal | new-release exception to cooldown; protected branch native test; manual |
| 22 | ANR without crash | ANR P1/P0 only after telemetry proven | independent ANR rule; safe non-prod ANR test; manual |
| 23 | Latency without errors | latency rule after prerequisite | independent metric; controlled non-prod delay; manual |
| 24 | Errors with normal latency | error rule still fires | independent signals; synthetic error; manual |
| 25 | High p95 tiny volume | no alert | ≥100 sampled tx; query sample-size test; manual |
| 26 | One slow request affects p99 | no alert below ≥300 tx; otherwise P2/P1 | sustained window; mock one outlier; manual |
| 27 | Threshold continuously breached | one alert then cooldown; reminders only by policy | test sustained series; manual |
| 28 | Recovery never fires | incident stays open; investigate config P1 | sustained healthy series test; manual |
| 29 | Duplicate rules | retain one route/parent incident | inventory and disabled clone test; manual |
| 30 | Cooldown hides regression | new release/regression/P0 bypass where supported | regression during cooldown test; manual |
| 31 | Production tag missing | quarantine, no production page; P2 config defect | missing-tag query; manual |
| 32 | Release tag missing | error alert may fire; release rules disabled; P2 | `release:unknown` audit; manual |
| 33 | Old versions report | lifecycle alerts remain; latest-release comparison isolates | release filters; query historic cohort; manual |
| 34 | Ingestion delayed | alerts may be late; monitoring unknown | check Sentry status/timestamp; delayed test; manual |
| 35 | Sentry unavailable | no false recovery; invoke fallback health checks | status review/incident drill; manual |
| 36 | Error quota exhausted | telemetry unknown; P1 monitoring risk | usage thresholds/manual check; manual |
| 37 | Backend never verified | backend rules stay disabled | execute §32; manual mandatory |
| 38 | iOS begins later | non-prod validation, then same mobile rules split by dist/platform | no paging until verified; device test; manual |
| 39 | iOS dist differs | expected platform dist; release must match policy | metadata comparison test; manual |
| 40 | Email leaks context | block rule and fix redaction; P0 privacy incident if real secret | sentinel test; manual mandatory |
| 41 | Owner unavailable | backup acknowledges/escalates | roster drill; manual |
| 42 | Overnight false positive | honor approved after-hours model; tune next day | test schedule/recipient; manual |
| 43 | Manual resolve while unhealthy | regress/reopen and alert per rule | metric remains active; test resolution; manual |
| 44 | Rule accidentally changes | detect in scheduled configuration review/export | monthly diff; manual |
| 45 | Test trigger remains in branch builds | acceptable non-prod only; never production alert | hard production gate + env rule; CI/build test; manual |

## 43. Automated test plan

During implementation, preserve and run existing monitoring unit tests: frontend config/redaction/filter/client and backend monitoring tests. Add repository tests only if code/config changes occur: environment/release fail-closed behavior, route normalization, session setting, sampling function, redaction of new span/session context, and production test-trigger absence. A sanitized rule-definition linter may validate required name, project, production filter, threshold/window, cooldown, recovery, recipient placeholder, and no secrets if configuration is tracked. Existing auth/onboarding/map/location/games/notifications/crash-reporting/backend exception/Android gates and iOS build preparation remain regression scope.

Alert firing itself cannot be proven by unit tests; it needs controlled dashboard/manual verification.

## 44. Manual mobile verification

Use a branch-build/non-production release and disabled/test rule clones. Trigger existing JS, React Boundary, and native test paths; verify event, grouping, environment/release/dist/device/OS, redaction, single issue email, count warning/critical using repeated controlled events, cooldown, and recovery. Never intentionally crash production or let test sessions contaminate production. Crash-rate testing waits for valid sessions and uses non-production release health.

## 45. Manual backend verification

First execute §32. Then with a protected non-production deployment and test clones: create a new exception, resolve/regress it, generate controlled repeated exceptions for warning/critical, stop and wait for recovery, verify route/query and duplicates, inspect redaction/email, and confirm production rule filters would exclude every test. Do not add a public production endpoint.

## 46. Alert-email verification

Primary and backup each confirm receipt, timestamp, subject/rule, severity, project, environment, release, safe issue link, and absence of sentinel secrets/private context. Check spam, organization membership, project access, per-user notification preferences, action recipient, and recovery email. Store only sanitized evidence.

## 47. Recovery verification

For every metric rule, cross warning/critical in a test environment, maintain breach through one evaluation, stop events or restore latency, remain healthy for the specified recovery duration, and confirm exactly one recovery notification. Confirm manual issue resolution does not impersonate metric recovery and a subsequent new breach can notify after cooldown.

## 48. Owner actions

1. Provide primary/backup recipients, component owners, acknowledgement/assignment process, and after-hours decision.
2. Complete mobile/backend Issues, Releases, Release Health, Crash Free Users/Sessions, Performance/Transactions, Alerts/Monitors, notification, ownership, and existing-rule audit.
3. Record subscription/trial/quota/retention/feature capabilities and confirm post-trial support.
4. Verify frontend production and protected backend events plus environment/release/dist.
5. Execute backend live-event prerequisite.
6. Decide/execute crash-health and latency prerequisites.
7. Approve provisional thresholds, sample gates, cooldowns, recoveries, and email routing.
8. Authorize enabling separately after controlled tests; this plan grants no such authorization.

## 49. Risks

Low-volume percentages, missing metadata, assumed SDK defaults, grouping splits/merges, cross-layer duplicates, trial-only features, quota exhaustion, ingestion delays, notification suppression, sensitive exception strings, alert fatigue, iOS metadata divergence, and lack of true uptime/no-data signal. Controls are denominator gates, exact filters, dashboard evidence, minimal initial rules, sentinel privacy tests, cooldown/recovery, entitlement review, and staged implementation.

## 50. Blockers

- Owner/dashboard audit of sessions, ANRs, transactions, existing alerts, recipients, ownership, and plan/quota.
- Protected Railway-to-backend event and tag/redaction verification before backend rules.
- Crash-rate prerequisite or evidence sufficient to upgrade decision C to A.
- Latency prerequisite completion before latency rules.
- Owner approval of thresholds/routing/after-hours and confirmation email delivery.
- iOS remains excluded from operational reliance until native integration and delivery are verified.

## 51. Follow-up issues

### LAT-PREREQ — Establish privacy-safe latency telemetry

Objective: select and validate the latency source of truth before alerts. Audit existing request-metrics storage first; compare it with minimal Sentry backend tracing. Define backend-only initial endpoints (overall, auth, fields/map, game create/join, notifications), normalized route names, candidate 5% production sampling subject to measured traffic, 100% protected test sampling, span/transaction quota estimate, retention, cost, privacy (no IDs/query/body/coordinates/tokens), overhead budget, database/external dependency scope, p50/p75/p95/p99 query validation, low-volume minimums, controlled delay test, rollback to 0, and explicit owner approval. Frontend startup/map spans are a second phase. Acceptance: ≥1,000 representative sampled transactions, correct percentiles, safe data, acceptable overhead/cost, and documented rollback. Do not create automatically.

### CRASH-HEALTH-PREREQ — Validate or establish Release Health

Objective: prove production session lifecycle and crash attribution for React/Capacitor Android, then iOS. Audit SDK-resolved defaults and dashboard envelopes; determine whether configuration is required; define lifecycle semantics, background/abnormal sessions, release/dist/environment, quota/cost/privacy, protected non-prod crash test, production sample gate, and rollback. Acceptance: plausible session counts, crash/abnormal attribution, ≥100 production sessions and ≥20 users for provisional alerts, no test contamination. Do not create automatically.

### IOS-MONITORING-VERIFY — Complete iOS Sentry integration verification

Resolve SPM/native dependency, build on Mac, produce/upload dSYM, verify JS/Error Boundary/native event and session metadata on a physical iPhone, then add iOS to mobile rules with platform/dist filters.

### MONITORING-UPTIME — Decide no-data/availability source

Evaluate Railway/platform health and an approved uptime mechanism because error silence is not proof of health. Define protected endpoint, recipient, cost, and provider-outage behavior separately.

## 52. iOS considerations

iOS shares the intended mobile project and release format, with `ios-*` dist, but current physical/native/dSYM/session verification is pending and the checked-in SPM package does not show Sentry. Do not assume iOS native events or crash-free metrics. When iOS arrives, test on non-production first, verify matching release and distinct dist/platform, symbolication, user/session lifecycle, privacy, and email routing. Existing mobile production rules may include iOS only after evidence; during rollout use a platform-specific observation view to avoid Android baseline distortion.

## 53. Acceptance criteria

- [x] Repository error collection, environments, release/dist, filtering, redaction, source maps, Android/iOS/backend status audited.
- [x] Sessions, crash-free, transactions/percentiles, ANRs, backend live delivery, alerts, and plan/quota explicitly classified as proven or unverified.
- [x] Issue versus metric strategy, minimum rule set, thresholds, calibration, severity, cooldown, recovery, noise controls, incident actions, privacy, cost, edge cases, file/config plan, tests, owner actions, iOS, and follow-ups defined.
- [x] Latency decision C and crash-rate decision C resolved conservatively.
- [x] Backend prerequisite and safe procedure defined.
- [ ] Owner/dashboard evidence and decisions completed.
- [ ] Backend live event verified.
- [ ] Crash/latency prerequisites completed or crash sessions proven.
- [ ] Controlled alert/email/recovery tests completed during implementation.
- [x] Planning task configured no alert, changed no telemetry, production code, dependency, secret, or external project.

## 54. Definition of Done

Planning is done when this document is reviewed and committed alone while preserving `frontend/.env`. Implementation is done only later when blockers are cleared, the approved minimum rules are configured manually, every test in §§43–47 passes, evidence is sanitized, owner accepts post-trial cost/capability, runbooks are linked, and a 24-hour/7-day/calibration review is scheduled. E09-04 must not be represented as fully operational while crash-rate or latency prerequisites remain open.

## 55. Recommended implementation order

1. Owner completes dashboard, plan, recipient, ownership, and metadata audit.
2. Verify frontend production metadata and protected backend live delivery.
3. Resolve privacy sentinel/email test in non-production.
4. Draft/test/approve the four production Issue Alerts (mobile/backend new + regression), then native new-crash alert.
5. Add error count/unique-user metrics only if supported and baseline/query valid.
6. Complete CRASH-HEALTH-PREREQ; add crash-free and ANR rules after sample gates.
7. Complete LAT-PREREQ; add backend p95, then p99; frontend latency later.
8. Calibrate after 14 days and ≥1,000 sessions; review trial expiry/quota and false positives.
9. Complete iOS verification and deliberately expand mobile rules.

## 56. Final readiness decision

**READY WITH BLOCKERS.** The plan is complete and the production error Issue Alert subset can move to implementation after the live-project/recipient/plan audit. The overall objective is not unconditionally ready: backend alerts need a protected real delivery verification; crash-rate and ANR rules need real Release Health/ANR evidence; latency requires a separate telemetry prerequisite; plan/quota and email ownership remain owner decisions. These blockers prevent false confidence while allowing the high-value, low-noise error lifecycle work to proceed in the recommended implementation branch after explicit authorization.

No alert was configured. No tracing, session setting, sample rate, profiling, Replay, analytics, production telemetry, application behavior, SDK, dependency, or external Sentry project was changed. `frontend/.env` was untouched. No secret was intentionally read into or written by this plan, staged, or committed. `main` was only fast-forwarded to match `origin/main`; it was not modified by a new commit or merged. Nothing was pushed.

---

## 57. Implementation report — 2026-07-21

Status: **E09-04 PARTIALLY COMPLETE — ALL CURRENTLY SAFE SENTRY ERROR ALERTS CONFIGURED — DOCUMENTED TELEMETRY AND DEPLOYMENT BLOCKERS REMAIN**

Implementation branch: `codex/e09-04-alerting-thresholds`, created from `main` at `5167afa209d033ac54158db26b4a0f626be8072d`. The planning branch was pushed as explicitly authorized. The implementation branch was not pushed or merged.

### 57.1 Fresh E09-01 findings

The live organization contains `yesh-mishak-mobile` and `yesh-mishak-backend`. Android branch-build JavaScript, React Error Boundary, and native fatal events are visible with `environment=branch-build`, commit-derived release, Android dist, device/OS, and internal user context. Backend Railway-to-Sentry delivery is now verified by three production events on `/analytics/events`; however, backend release is `unknown`, so release-specific backend alerts remain blocked. No ANR issue was found. Sentry Traces shows no tracing data, consistent with repository `tracesSampleRate: 0`.

Release Health is active for the mobile SDK, but the only evidenced release cohort is branch-build test traffic: one audited release had roughly 17 sessions, crash-free session rate 100%, and inconsistent/very-low user statistics after controlled crashes. There is no validated production session denominator. Crash-rate and ANR-rate production monitors were therefore not created.

### 57.2 Fresh E09-02 findings

E09-02 is a first-party, Supabase-backed, anonymous volume pipeline. It accepts only `app_open` and `screen_view`, batches up to 20 events, keeps a 100-event in-memory queue, retries retryable failures three times with exponential backoff, and silently drops overflow, logged-out, non-retryable, and exhausted-retry events. It stores event name, closed-enum screen, platform, optional app version, and bounded event timestamp for 90 days. It stores no user/anonymous identifier, session ID, environment, release, crash/error, latency, queue backlog, dropped-event counter, or dead-letter record.

The live backend event proves production ingestion currently returns `503 ANALYTICS_UNAVAILABLE` because `public.analytics_events` is missing from the Supabase schema cache. The repository migration exists, but the production migration has not been applied or refreshed. Consequently E09-02 currently supplies none of the intended live production dashboard counts, denominators, freshness, or health metrics.

### 57.3 Fresh E09-03 findings

E09-03 is the application’s own admin UI, not Grafana/Kibana or an external dashboard provider. It reads database-side aggregates and shows app opens, screen views, platform, share actions/outcomes/success rate, response generation time, and client refresh time. It intentionally adds no sessions, DAU/retention, crash/error, ANR, or latency telemetry. Its “data freshness” is response-generation time, not latest raw-event time, so it cannot detect stale ingestion. With the production analytics table missing, the analytics source is unavailable rather than healthy.

The older Admin Monitoring dashboard, independent of E09-03, does expose Supabase-backed API request count, 5xx count/rate, overall average/p50/p95/max response duration, push delivery, scheduled job status, and source availability. It has no external alert engine, p99, endpoint-specific percentiles, or reliable no-data/freshness schedule.

### 57.4 Live Sentry plan and quota

The organization is on a Business Plan Trial with 12 days remaining at audit time and no billing details/payment method. Current usage showed 7 accepted errors of 1,000,000 trial errors, zero dropped/over-quota/spike-protected errors, zero spans, zero replays, and zero application-metric bytes. Trial allowances shown included 100M spans, 300 cron monitors, and 10 uptime monitors, but none may be treated as a permanent entitlement. Post-trial monitor availability and quotas remain an owner blocker.

### 57.5 Existing alert corrections

Two pre-existing default Issue Alerts—one per project—were preserved and modified in place. Before correction they covered all environments, notified on every trigger, and had already triggered for branch-build test errors. After correction:

| Rule | Project | Trigger | Environment | Throttle | Action |
|---|---|---|---|---|---|
| Send a notification for high priority issues | mobile | new or existing issue marked high priority | production | 1 hour per issue | email: suggested assignees, fallback recently active members |
| Send a notification for high priority issues | backend | new or existing issue marked high priority | production | 1 hour per issue | email: suggested assignees, fallback recently active members |

No existing rule was deleted. The environment correction prevents future `branch-build` events from paging production recipients. Historical triggers remain visible as evidence.

### 57.6 Metric monitors created

All monitors use Sentry Errors as the authoritative source, `environment=production`, static warning/critical thresholds, explicit recovery, and the project’s existing email alert route. Sentry generates the display title; the stable operational name is the first token in the description.

| ID | Operational name | Project/query | Warning / critical | Window | Recovery | Result |
|---:|---|---|---|---|---|---|
| 1529849 | `BE-PROD-Internal-Error-Spike` | backend `count()`, `is:unresolved` | >3 / >10 | 10 min | ≤2 | created; no ongoing issue |
| 1529850 | `BE-PROD-Affected-Users` | backend `count_unique(user)`, unresolved | >3 / >5 users | 1 hour | ≤2 | created; no ongoing issue |
| 1529851 | `MOB-PROD-Error-Spike` | mobile `count()`, unresolved | >5 / >15 | 15 min | ≤4 | created; no ongoing issue |
| 1529855 | `MOB-PROD-Affected-Users` | mobile `count_unique(user)`, unresolved | >3 / >5 users | 1 hour | ≤2 | created; no ongoing issue |
| 1529862 | `BE-PROD-Analytics-Ingestion-Failure-Spike` | backend unresolved errors, `transaction:/analytics/events` | >3 / >10 | 30 min | ≤2 | created; query validated |

The project-level alerts provide a one-hour notification throttle after a monitor creates/updates an issue. Metric issues resolve only at the explicit values above. No synthetic production events were generated to cross thresholds.

### 57.7 Alert families not configured

- Crash-free users/sessions: Sentry supports these metric types, but no valid production denominator or low-volume guard could be proven. Branch-build test sessions must not drive production operations.
- Native-only crash spike: the attempted production query combining native platform and unhandled status returned an invalid/unsupported metric query while no production native cohort exists. It was not saved. New native fatals remain covered by the production high-priority Issue Alert once real production native events exist.
- ANR count/rate: no ANR event and no valid production session denominator.
- Latency: Sentry has zero spans. The database dashboard’s p95 has no alert engine and cannot safely become a Sentry span alert without new telemetry.
- App startup/map initialization/database dependency duration: not collected.
- Dropped/duplicate/invalid-schema/backlog/ingestion-lag metrics: E09-02 does not persist them.
- Dashboard refresh/query/staleness alerts: E09-03 has no scheduler/alert provider, and generated-at is not source freshness.
- Missing-event/no-data: current low traffic and missing environment dimensions make zero ambiguous.

### 57.8 Privacy change

The live backend issue showed SDK-generated HTTP breadcrumbs in addition to the already-redacted top-level request. `backend/app/monitoring.py` now applies URL query/fragment stripping and recursive sensitive-key redaction to every breadcrumb before delivery. Tests cover Authorization headers, cookies, and token-bearing URLs. No DSN, token, recipient address, or production value is stored in the repository.

### 57.9 Verification and blockers

Verified in the live UI: projects, backend delivery, environment/release metadata, branch-build crash, release sessions, absent ANRs/traces, existing alerts, production filters, one-hour throttles, metric query/threshold/recovery definitions, project email routing, trial/usage, and production analytics failure. Email delivery itself was not forced because that would require a synthetic production breach; only prior live alert history and the configured Email action were inspected.

Repository verification: the focused monitoring-redaction suite passed (`10 passed`). Broader backend monitoring/analytics/dashboard collection was attempted but the existing local virtual environment lacks `python-multipart`, a dependency now required by the merged field-photo route; collection stopped before those tests could run. No dependency was installed and no generated/dependency file was changed.

Remaining blockers:

1. Apply `backend/migrations/analytics_events.sql` to production Supabase, refresh schema cache if required, and verify accepted events plus E09-03 counts.
2. Inject a real backend `SENTRY_RELEASE` on Railway.
3. Collect sufficient real production Release Health data before crash-rate monitors.
4. Produce/observe a production ANR signal before ANR alerts.
5. Choose and implement a latency/freshness alert source in separate work; do not enable broad tracing implicitly.
6. Confirm post-trial Sentry entitlements and permanent plan before relying on metric monitors.
7. Assign named component owners/backup and verify actual email receipt with an approved controlled test.

The operational response details are maintained in `docs/e09-04-alerting-runbook.md`.

---

## 58. Deployment-blocker resolution report — 2026-07-21

This section supersedes the implementation-state and blocker statements in §57 where they conflict with the evidence below.

Status: **E09-04 PARTIALLY COMPLETE — SAFE PRODUCTION ERROR ALERTS CONFIGURED — ANALYTICS INGESTION VERIFIED — BACKEND RELEASE CONFIGURED — RELEASE OBSERVATION, CRASH-RATE, ANR, LATENCY, EMAIL, AND PLAN ENTITLEMENT VERIFICATION REMAIN**

### 58.1 Production analytics ingestion

Production inspection found that `public.analytics_events` already exists and matches the tracked migration: seven expected columns/defaults/nullability rules, primary key, four check constraints, two secondary indexes, RLS enabled with no policies, no triggers, and both expected security-definer functions. `service_role` has the required select/insert/delete and function-execute capabilities. An additional effective `TRUNCATE` capability was observed but was neither used nor changed. No migration was reapplied, no cleanup ran, and no schema/cache operation was forced.

A single authenticated test event conforming to the anonymous analytics contract was submitted through the real production `POST /analytics/events` endpoint with `app_version=e09-04-test`. The response was HTTP `202` with `accepted_one`, not `503`. A read-only database query found exactly one matching row: `event_name=app_open`, `platform=web`, `properties={}`, and `app_version=e09-04-test`. No user identifier, coordinates, free text, token, cookie, request body, or other sensitive property was stored. This verifies current PostgREST schema-cache visibility and production analytics ingestion.

### 58.2 Railway backend release

Railway production service `yesh_mishak` was configured with `SENTRY_RELEASE=yesh-mishak-backend@${{RAILWAY_GIT_COMMIT_SHA}}`. No other Railway variable was changed. Railway staged one change, built a replacement deployment, and reported `Deployment successful` with the new deployment active. Real Railway-to-Sentry backend delivery had already been verified before this variable change.

The resolved post-change release has **not** yet been observed on a Sentry event. No temporary production CLI, helper, route, user-flow failure, merge, or extra cleanup deployment was added solely to manufacture an event. Exact pending statement: **Post-change backend release metadata remains pending verification on the next naturally occurring legitimate backend exception or safe non-production verification opportunity; do not claim that `yesh-mishak-backend@<commit-sha>` has already been observed in Sentry.**

At that opportunity, confirm `environment=production`; release starts with `yesh-mishak-backend@` and is not `unknown`; the stack trace is readable; and breadcrumbs/request context contain no query strings, fragments, Authorization headers, cookies, tokens, passwords, coordinates, request bodies, DSNs, or secrets.

### 58.3 Repository verification

`python-multipart==0.0.20`, already pinned in `backend/requirements.txt`, was installed only into the existing local virtual environment. The combined monitoring, analytics-ingestion, and admin-engagement suites passed: `100 passed` with existing third-party/test-key warnings. No dependency declaration or generated file changed.

### 58.4 Remaining blockers

1. Observe and inspect the configured backend release on the next legitimate safe Sentry event.
2. Collect a valid production Release Health denominator before crash-rate monitors; branch-build sessions are insufficient.
3. Produce or naturally observe a production ANR signal and valid Android session denominator before ANR rules.
4. Select and implement an approved latency/freshness source separately; Sentry currently has zero spans and broad tracing was not enabled.
5. Confirm permanent post-trial Sentry metric-monitor entitlements, quota, retention, and cost.
6. Assign named primary/backup responders and verify actual alert and recovery email receipt with an approved controlled test.
