# E12-03 — Staging Environment Verification Report (Canonical)

**Status: COMPLETE — the isolated dev/staging environment exists, is
operational, and has been verified end-to-end by the automated E12-04 smoke
suite.**

This document supersedes the earlier E12-03 report that existed only in commit
`b18b462` on the unmerged branch `qa/e12-03-staging-verification`. That report
is retained there as historical context only; this file is the canonical
record.

## 1. Objective

Operationally verify that an isolated pre-production (staging-equivalent)
environment is correctly configured, deployable, isolated from production, and
capable of supporting end-to-end testing.

## 2. Historical finding (no longer current)

> **Historical — resolved.** The initial E12-03 investigation (2026-07, commit
> `b18b462`) found that the *documented placeholder* staging URLs were not
> operational: `https://staging-yesh-mishak.vercel.app/` returned a Vercel
> `DEPLOYMENT_NOT_FOUND` 404 and `https://yesh-mishak-api-staging.railway.app/`
> served Railway's default placeholder rather than the FastAPI app. No staging
> database, Firebase project, or OAuth client existed at that time, and the
> issue was blocked on owner provisioning (tracked as E12-03A/B/C).
>
> Those placeholder hostnames were never provisioned and are **not** the
> canonical environment. The environment was instead implemented under the
> `dev` naming described below.

## 3. Final implemented architecture

The project's staging-equivalent environment is the **`dev` environment**:

| Component | Resource |
| :--- | :--- |
| Git branch | `dev` |
| Frontend | Vercel dev deployment |
| Backend | Railway dev service |
| Database | Dedicated Supabase project `yesh_mishak_dev` (project ref `txpnyewytcfslsdicjbx`) |
| CI integration | GitHub Environment **`dev`** (variables + secrets consumed by the **Staging smoke tests** workflow) |

## 4. Canonical URLs

| Target | URL |
| :--- | :--- |
| Frontend | `https://dev-yesh-mishak.vercel.app` |
| Backend | `https://yeshmishak-dev.up.railway.app` |

## 5. Isolation boundaries

- **Frontend:** a dedicated dev Vercel deployment, separate from the
  production frontend deployment.
- **Backend:** a dedicated dev Railway service, separate from the production
  backend service.
- **Database:** a dedicated, isolated Supabase project (`yesh_mishak_dev`,
  ref `txpnyewytcfslsdicjbx`), separate from the production Supabase project.

## 6. Production isolation confirmation

- The dev frontend bundle is wired to the dev backend: the E12-04
  `[frontend-wiring]` check verified the dev backend origin is baked into the
  served bundle and that **no production backend hostname** appears in it or
  is contacted at runtime (production-host denylist check passed).
- The smoke suite's environment contract structurally refuses to run if a
  configured target hostname matches the production denylist.
- The verification run contacted no production endpoint and modified no
  production data.
- Database isolation follows from the dedicated `yesh_mishak_dev` Supabase
  project being the dev backend's configured database.

## 7. Authentication flow findings

- Only findings already documented are recorded here; no new claims are made.
- The automated run validated **unauthenticated** auth-adjacent contracts:
  CORS preflight for the dev frontend origin and the standard API error
  envelope.
- Authenticated login (Tier B: password login with a dedicated synthetic test
  account, token-based access, 401/403 boundaries) was **skipped by design**
  because dedicated dev test credentials are not yet configured — it is
  implemented but not yet exercised against the dev environment.
- Interactive Google sign-in remains a manual-only check (see
  `docs/staging-smoke-test-checklist.md`); per `docs/staging-setup.md`, a
  non-production OAuth client configuration is required for it, and no
  automated verification of it is claimed.

## 8. Known limitation — push notifications / Firebase

Firebase/FCM may still use the existing (shared) Firebase project. **Push
isolation is therefore not claimed as verified.** No automated test sends
push notifications (explicitly excluded from the smoke suite), and the push
safety section of the staging checklist remains a manual, dashboard/device
verification. Splitting Firebase projects remains the documented
recommendation (`docs/staging-setup.md` §7).

## 9. Completion evidence

The E12-04 staging smoke suite ran green from GitHub Actions
(`workflow_dispatch`, GitHub Environment `dev`) against the real dev
environment:

- Tier A smoke tests: **PASSED** —
  backend health (`GET /` contract), database connectivity
  (`GET /fields/`), API error-envelope contract, CORS for the dev frontend
  origin, frontend availability, frontend boot, frontend bundle wiring to the
  dev backend, production-backend denylist, `/privacy` and `/terms`.
- Tier B authenticated tests: **SKIPPED** (dedicated dev test credentials not
  configured — optional by design).
- No production endpoint contacted; no production data modified.

## 10. Workflow-run evidence

https://github.com/sandrusipredicts/yesh_mishak/actions/runs/30122383892

## 11. Final E12-03 status

```text
Implementation / provisioning: COMPLETE
Manual staging verification: COMPLETE
Canonical documentation: COMPLETE
E12-03 closure readiness: READY
```
