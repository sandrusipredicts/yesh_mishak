# Credential-exposure response — 2026-07-26

Status: CONTAINED. This file is sanitized (no full token material) and is
intentionally left uncommitted pending review.

## Exposure

The E12-10 baseline workflow artifact `dev-backend-performance-30196456021-1`
(artifact ID 8630343151, run 30196456021) contained six live HS256 access
tokens in the `setup_data` section of the six `*-summary.json` files (three
authenticated-read runs and three controlled-write runs, one login each).
All six tokens belonged to the single synthetic dev test account
(`sub 348a581f…`), were issued 2026-07-26 (~09:29–09:34 UTC), and carried a
7-day expiry (~2026-08-02). The artifact was downloadable by any
authenticated GitHub user because the repository is public. The same tokens
were briefly present in locally staged (never committed, never pushed) file
versions; the committed evidence (commit `1c7c0a4`) is fully redacted.

## Actions performed (all on 2026-07-26)

1. Verified artifact 8630343151 belonged to run 30196456021 in
   `sandrusipredicts/yesh_mishak` (name, size 180,792 bytes, unexpired).
2. Deleted only the artifact via the GitHub REST API
   (`DELETE /repos/{owner}/{repo}/actions/artifacts/8630343151`). The
   workflow run and its logs were not deleted.
3. Verified deletion: `GET` on the artifact returns HTTP 404 and the run
   now lists 0 artifacts.
4. Confirmed `POST /auth/logout` performs real server-side revocation:
   it invokes the `revoke_user_tokens` RPC, which bumps the user's
   `tokens_valid_after` under a per-user advisory lock
   (`backend/app/api/auth.py`), and request auth rejects any token with
   `iat < tokens_valid_after` as 401 `TOKEN_REVOKED`
   (`backend/app/auth/dependencies.py`). Revocation is account-scoped;
   one logout invalidates all tokens issued to the account before now,
   which covers all six exposed tokens.
5. Pre-check: one exposed token still returned HTTP 200 on
   `GET /notifications/unread-count` (tokens were live).
6. Called `POST /auth/logout` on `https://yeshmishak-dev.up.railway.app`
   with one exposed token → HTTP 200.
7. Verified each of the six exposed tokens individually now receives
   HTTP 401 `TOKEN_REVOKED` on `GET /notifications/unread-count`.
8. Deleted the temporary local token recovery file after verification.

## Residual risk and follow-ups

- Anyone who downloaded the artifact between ~2026-07-26 09:36 UTC and
  deletion could have used the tokens during that window against the dev
  backend only (dev Supabase project; no production access). The account
  is synthetic; observed data exposure limit: the test account's own
  notifications/preferences/games. Dev-side audit of unusual activity on
  the account is possible via Railway/Supabase logs once dashboard access
  is available.
- The JWT signing secret was NOT rotated; account-scoped revocation was
  sufficient for this exposure. Rotate only if broader compromise is
  suspected.
- The test account's JWT payload embeds a personal Gmail address.
  Recommendation: migrate the GitHub `dev` environment credentials to a
  dedicated synthetic identity (dedicated mailbox or alias not linked to
  a person), then delete or scrub the old test user row.
  Issue #1027 adds repository controls and the operator runbook at
  `docs/qa/synthetic-dev-test-identity.md`. Hosted mailbox creation, secret
  rotation, workflow verification, and evidence-preserving retirement remain
  pending operator actions; this note does not claim they have occurred.
- Workflow hardening: the k6 summary export includes `setup_data`; strip
  or mask tokens before `--summary-export`, and/or mark the value with
  `::add-mask::` in the workflow so future artifacts never contain
  credentials.
