# Sentry Configuration Guide (E09-01)

Audience: the project owner. This is a step-by-step setup guide for turning on crash reporting after implementation has landed. No real values (DSNs, tokens, org/project slugs) appear in this document or anywhere in the repository — every value below is described, not filled in.

## 1. Create the Sentry Organization and Projects

1. Create (or select) one Sentry **organization** for the project.
2. Create one **mobile project** (platform: JavaScript/React or Capacitor) — this single project receives events from the React frontend, the Android WebView, the Android native layer, and (once the iOS phase completes) the iOS WKWebView/native layer. Combining Android and iOS here avoids fragmenting alerts/dashboards across two mobile-adjacent projects; they're kept distinguishable within the one project via the `dist` tag (see [Release strategy](#5-release-and-dist-values)).
3. Create one **backend project** (platform: Python/FastAPI) for the backend.
4. Do not create a third project unless a clear technical need emerges later — the architecture doc explains why two projects are sufficient.

## 2. Obtain the DSNs

Each project has its own DSN (found in Sentry under **Project Settings → Client Keys (DSN)**).

| Value | Project | Secret? | Client-visible? |
|---|---|---|---|
| Mobile project DSN | Mobile | No | Yes — DSNs are write-only ingest keys, safe to embed in a client bundle or native app |
| Backend project DSN | Backend | No (kept as an env var for easy rotation, not because it's sensitive) | No — stays server-side |

## 3. Create the Auth Token (for uploads)

Under **Organization Settings → Auth Tokens**, create a token scoped to:
- `project:releases` (release creation)
- `project:write` or the debug-files/source-maps upload scope (needed for both JS source-map upload and, later, iOS dSYM upload)

This token is used by CI to upload JS source maps (both platforms' builds) and, once the iOS phase lands, iOS dSYMs. **This is a secret.** It must never be committed, printed, or embedded in any client bundle.

## 4. Environment Variables and Secrets Matrix

Do not put any real value from this table into a tracked file. Names only are already wired into the repository; values are configured per-platform below.

| Name | Layer | Secret? | Client-visible? | Where to obtain | Where to store | Restart/redeploy needed? |
|---|---|---|---|---|---|---|
| `VITE_SENTRY_DSN` | Frontend | No | Yes | Mobile project → Client Keys | Vercel env vars; GitHub Actions repo variable (`vars.VITE_SENTRY_DSN`) for CI builds | Rebuild |
| `VITE_SENTRY_ENVIRONMENT` | Frontend | No | Yes | Set explicitly per deploy target (`development`/`production`) | Vercel env vars (per environment); CI sets `branch-build` itself | Rebuild |
| `VITE_SENTRY_RELEASE` | Frontend | No | Yes | Computed at build time (CI already does this for Android; wire similarly for Vercel — see §6) | CI/deploy-time env var, not a static value | Rebuild |
| `VITE_SENTRY_DIST` | Frontend | No | Yes | Computed at build time (see §5) | CI/deploy-time env var | Rebuild |
| `VITE_SENTRY_ENABLED` | Frontend | No | Yes | Only set to `true` for local integration testing | Local `.env.local`, never committed | Rebuild (dev server restart) |
| `SENTRY_DSN` | Backend | No (rotation-friendly, stored as env var) | No | Backend project → Client Keys | Railway env vars | Redeploy |
| `SENTRY_ENVIRONMENT` | Backend | No | No | Set explicitly per deploy target | Railway env vars (per environment) | Redeploy |
| `SENTRY_RELEASE` | Backend | No | No | Computed at deploy time from the Railway/GitHub commit SHA | Railway env vars, ideally auto-injected by a deploy hook | Redeploy |
| `SENTRY_ENABLED` | Backend | No | No | Only set to `true` for local integration testing | Local `.env`, never committed | Restart |
| `SENTRY_AUTH_TOKEN` | CI only | **Yes** | No | Organization Settings → Auth Tokens (§3) | GitHub Actions secret (`secrets.SENTRY_AUTH_TOKEN`) | N/A (CI-scoped) |
| `SENTRY_ORG` | CI only | No | No | Organization slug (URL segment) | GitHub Actions repository variable (`vars.SENTRY_ORG`) | N/A |
| `SENTRY_MOBILE_PROJECT` | CI only | No | No | Mobile project slug | GitHub Actions repository variable (`vars.SENTRY_MOBILE_PROJECT`) | N/A |
| `SENTRY_BACKEND_PROJECT` (referenced in the backend deploy process, not yet CI-wired) | Deploy-time | No | No | Backend project slug | Railway/deploy config, if a backend upload step is added later | N/A |

## 5. Release and `dist` Values

Format already wired into CI: `yesh-mishak@<short-sha>` (the interim format — see [`docs/e09-01-crash-reporting-execution-plan.md`](e09-01-crash-reporting-execution-plan.md) for why the full `yesh-mishak@<version>+<sha>` format isn't reachable yet). `dist` values already produced by the Android CI workflow: `android-branch-<run-number>`. The equivalent for iOS (`ios-branch-<run-number>`) is wired in `.github/workflows/ios-debug-build-validation.yml` but not yet exercised end-to-end (no signed archive build exists yet).

## 6. GitHub Actions Setup

Already wired in this repository (no owner action needed beyond adding the actual secret/variable values below):

- `.github/workflows/android-build-validation.yml` reads `vars.VITE_SENTRY_DSN`, `secrets.SENTRY_AUTH_TOKEN`, `vars.SENTRY_ORG`, `vars.SENTRY_MOBILE_PROJECT` for its branch-build APK job.
- `.github/workflows/ios-debug-build-validation.yml` reads the same `secrets.SENTRY_AUTH_TOKEN`, `vars.SENTRY_ORG`, `vars.SENTRY_MOBILE_PROJECT` for its (currently unsigned, Simulator-only) dSYM-upload step.

**Owner action**: add these to the repository (Settings → Secrets and variables → Actions):
- Secret: `SENTRY_AUTH_TOKEN`
- Variables: `VITE_SENTRY_DSN`, `SENTRY_ORG`, `SENTRY_MOBILE_PROJECT`

Without these, both workflows continue to build successfully — they only log a warning and skip the Sentry-related step (verified during implementation; see the execution plan's test results).

## 7. Vercel Setup (Frontend Production/Preview)

**Not yet wired** — the repository has no Vercel-specific build script beyond the plain `npm run build`. Owner action required:

1. In the Vercel project's environment variables, add `VITE_SENTRY_DSN`, `SENTRY_AUTH_TOKEN` (mark as **sensitive/encrypted** — this is the upload token, not a DSN), `SENTRY_ORG`, `SENTRY_MOBILE_PROJECT` for the Production environment; set `VITE_SENTRY_ENVIRONMENT=production` there.
2. For Preview deployments, set `VITE_SENTRY_ENVIRONMENT=development` (or leave unset — the app defaults to `development` for any non-dev-server build with no explicit override, never `production`).
3. `VITE_SENTRY_RELEASE`/`VITE_SENTRY_DIST`: Vercel exposes `VERCEL_GIT_COMMIT_SHA` automatically as a system environment variable. Set `VITE_SENTRY_RELEASE` to reference it (Vercel supports referencing other env vars in its dashboard, or this can be computed in a `vercel-build` script). This wiring is **not yet implemented** in this repository — it's the direct Vercel-side equivalent of the "Resolve Sentry release identifier" step already present in `android-build-validation.yml`.
4. Without `SENTRY_AUTH_TOKEN` configured in Vercel, the production build still succeeds (the Sentry Vite plugin is skipped), but source maps are **not** uploaded or stripped from the deploy output. **Configuring this token in Vercel is required to actually get the delete-after-upload safety net for public source-map exposure — until then, hidden source maps remain in the deploy output with no `sourceMappingURL` reference (not linked from the JS, but still fetchable if the exact filename is guessed).**

## 8. Railway Setup (Backend)

**Not yet wired** — no `railway.json`/`railway.toml` exists in this repository (deploy is Railway-console-configured). Owner action required:

1. In the Railway project's environment variables, add `SENTRY_DSN`, and set `SENTRY_ENVIRONMENT=production` for the production service.
2. `SENTRY_RELEASE`: Railway exposes `RAILWAY_GIT_COMMIT_SHA` as a built-in variable. Set `SENTRY_RELEASE` to reference it (Railway supports variable references in its dashboard) using the same interim format (`yesh-mishak@<short-sha>`).
3. Without `SENTRY_DSN` configured, the backend starts and runs normally with monitoring disabled (verified via `test_init_monitoring_disabled_without_dsn` in `backend/tests/test_monitoring.py`).

## 9. Future iOS CI Values

Once the iOS phase reaches a real signed archive build (a prerequisite not yet in place — see the execution plan's deferred iOS checklist), the same `SENTRY_AUTH_TOKEN`/`SENTRY_ORG`/`SENTRY_MOBILE_PROJECT` already configured for Android/frontend cover iOS too — no new token or project is anticipated. The guarded dSYM-upload step already present in `.github/workflows/ios-debug-build-validation.yml` will begin actually uploading once a real `.dSYM` bundle exists in a signed archive's output.

## 10. Test-Event Procedures (Safe, Redacted Verification)

### Frontend
1. Confirm `VITE_SENTRY_DSN`/`VITE_SENTRY_ENVIRONMENT` are configured for a non-production build (e.g. a Vercel preview, or `VITE_SENTRY_ENABLED=true` locally).
2. Open the app, open the browser devtools console.
3. Run `window.__monitoringTest.triggerReactRenderError()` — this only exists when the resolved environment is not `production` and either the dev server or an explicit `VITE_SENTRY_TEST_TRIGGER_ENABLED=true` build flag is set (see `frontend/src/monitoring/index.js`).
4. Confirm the event appears in the Sentry mobile project, tagged with the expected (non-production) environment and release.
5. Confirm the stack trace resolves to source file names, not minified output (requires `SENTRY_AUTH_TOKEN` configured for that build — see §7).
6. Confirm no token, email, password, or coordinate value appears anywhere in the event payload.

### Android
1. Trigger a manual `workflow_dispatch` run of `android-build-validation.yml` with the Sentry variables configured.
2. Install the resulting debug APK on a physical device.
3. Trigger `window.__monitoringTest.triggerReactRenderError()` via a remote WebView debugging session (`chrome://inspect`), or `window.__monitoringTest.triggerTestNativeCrash()` for a genuine native crash test (bridges to `Sentry.nativeCrash()` — this is a real, unconditional native crash; only reachable under the same non-production gate).
4. Restart the app if needed for the native crash report to flush and upload.
5. Confirm device model, Android OS version, app version, environment (`branch-build`), and release all appear correctly on the event.

### Backend
1. With `SENTRY_DSN`/`SENTRY_ENVIRONMENT` configured for a non-production deployment (or `SENTRY_ENABLED=true` locally):
2. `GET /__test/sentry-trigger` — this route only exists when the resolved environment is not `production` (see `backend/app/main.py`); it intentionally raises a `RuntimeError`.
3. Confirm the event appears in the backend project with the correct environment/release tags and a readable Python stack trace.
4. Confirm no `Authorization` header, cookie, password, or token value appears anywhere in the event.
5. Confirm the API's own response (a normal `500 INTERNAL_SERVER_ERROR` JSON body) is unaffected by whether the Sentry call succeeded.

## 11. Alert Setup

Configure these alert rules in the Sentry dashboard (owner action — not automatable from this repository per the task's scope, which explicitly excludes external alert-tool integration):

| Alert | Threshold | Recipient |
|---|---|---|
| New fatal issue | Any new unique fingerprint | Project owner email |
| Regression of a resolved issue | Any reoccurrence | Project owner email |
| Sudden error spike | >10x baseline in 1 hour | Project owner email |
| Android ANR spike | >1% of sessions ANR in a release | Project owner email |
| Backend internal error spike | >2% of requests error in 15 min | Project owner email |
| High affected-user count | >5 distinct users in 24h | Project owner email |

Email is sufficient for the initial rollout; no Slack/PagerDuty integration was added, per the task's explicit scope exclusion.

## 12. Secret Classification Summary

- **Public/client-visible configuration** (safe to embed in a client bundle or native app, not a secret): both DSNs, all `environment`/`release`/`dist` values.
- **Deployment variables** (not secret, but not meant to be public either — kept in platform env-var stores for convenience/rotation): `SENTRY_ENVIRONMENT`, `SENTRY_RELEASE` on both frontend and backend.
- **Secret** (must never be committed, printed, or embedded client-side): `SENTRY_AUTH_TOKEN` only.
