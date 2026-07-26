# Token exposure window audit — status: NOT PERFORMED (blocked on access)

This file records an audit that could **not** be carried out, and the exact
inputs prepared for whoever can run it. It is deliberately not a clean bill of
health: no dev backend or database logs were inspected, so no statement is
made about whether the exposed tokens were used.

Sanitized by construction: no email addresses, tokens, token fragments, IP
addresses, or infrastructure secrets appear below.

## Exposure window

| Boundary | Timestamp (UTC) | Source |
|---|---|---|
| Tokens first issued | 2026-07-26T09:29:31Z | `iat` of the earliest exposed token |
| Tokens last issued | 2026-07-26T09:34:49Z | `iat` of the latest exposed token |
| Artifact became downloadable | 2026-07-26T09:36:29Z | artifact creation time |
| Revocation completed | before 2026-07-26T11:03:40Z | containment record commit `4b7038e` |

Maximum exposure: approximately **87 minutes**, ending when all six tokens were
revoked and individually verified as HTTP 401 `TOKEN_REVOKED`. The artifact was
downloadable by any authenticated GitHub user during that period because the
repository is public.

## Attribution baseline for the known CI run

Any authenticated activity by the synthetic test account inside the exposure
window that falls **outside** these parameters is unattributable and warrants
investigation.

| Parameter | Known-good value |
|---|---|
| GitHub Actions run | 30196456021, attempt 1 |
| Target host | the isolated dev backend |
| Request window | 2026-07-26T09:26:26Z to 2026-07-26T09:36:16Z |
| Total measured requests | 13,355 metric points across 11 k6 summaries |
| Request marker header | `X-Performance-Test-Run` present on every request |
| Test-run ID prefix | `30196456021-1-` |
| Client | k6 2.0.0 running in GitHub-hosted CI |
| Write operations | push-token save/delete only, all returning 200 |
| Endpoints touched | health, fields, games (active/upcoming/me), notifications (unread-count, preferences, push-token), login |

## Access paths attempted

| Path | Result |
|---|---|
| Railway CLI | Not installed; `~/.railway` holds only a version file, no session |
| Supabase CLI | Not installed; `~/.supabase` holds only telemetry, no session |
| Connected browser session | No browser connected |
| Local Supabase credentials | Present, but scoped to the **production** project, not the dev project — wrong target and out of bounds for this audit |

No credentials were requested, read for use, or exposed.

## Queries to run once access exists

1. **Backend request logs** for the dev deployment, 2026-07-26T09:36:29Z to
   the revocation time. Filter to requests authenticated as the synthetic test
   account. Every legitimate request carries the `X-Performance-Test-Run`
   header and a test-run ID beginning `30196456021-1-`; anything authenticated
   as that account **without** those markers is unattributable.
2. **Source addresses and user agents** for those requests. The known run
   originates from GitHub-hosted CI and identifies as k6. Any other client
   signature in the window is unattributable.
3. **Requests outside 09:26:26Z–09:36:16Z** but before revocation — the known
   run had ended by 09:36:16Z, so authenticated activity after that point and
   before revocation is unattributable by definition.
4. **Write operations** by the account in the window. The only expected writes
   are push-token save/delete pairs. Any game creation, join, leave, profile
   mutation, notification preference change, or field write is unattributable.
5. **Read access** to profile, notification, or game data beyond the endpoints
   listed in the attribution baseline.

## Database cleanup verification (also outstanding)

API-level cleanup is already evidenced: all 76 measured save/delete operations
returned 200 and a teardown delete ran for every write trial. What remains is
direct confirmation in the dev database that:

- no push-token rows remain whose token value begins `perf-baseline-30196456021-`;
- no rows remain whose installation identifier begins `perf-30196456021-`;
- no game, player, notification, or field rows were created by the account
  during the run window.

## Subsequent verification run — hardening proven, exposure still unaudited

A manual baseline run was dispatched after the harness and workflow were
hardened. It is recorded here because it is easy to mistake for closure of
this audit, and it is not.

| Item | Value |
|---|---|
| Run | 30203359972 (`workflow_dispatch`, on `main`) |
| Conclusion | success |
| Scenarios | all 11 completed, exit code 0, both failure counters 0 |
| Status distribution | 779 × 200 and 12 × 401 (the 401s are the invalid-auth contract) |
| Artifact scan | no `setup_data` key, no JWT-shaped string, no `Authorization`/`Bearer` header, no email address, no credential value, no withheld security-scenario content |
| Cleanup | teardown returned 200 on all three controlled-write runs; save/delete counts matched; the cleanup failure counter never incremented |

Every summary export in that artifact has top-level keys `metrics` and
`root_group` only, so the credential no longer reaches disk at the source
rather than being scrubbed afterwards. Issue #1028 was closed on this evidence.

**What this run does and does not establish.** It proves the hardening works:
a full run now produces artifacts free of credentials, and the fail-closed
verification gate held. It says **nothing** about whether the six tokens
exposed on 2026-07-26 were used by anyone during the ~87-minute window. Those
are different questions, separated in time, and only the first has been
answered. The audit described above remains outstanding.

## Conclusion

The audit is **outstanding, not clean**. Absence of findings here reflects
absence of inspection, not absence of misuse. Two dependent items therefore
remain open: the Railway/Supabase log review and the direct database cleanup
check, both recorded as pending in the baseline QA report and tracked in
issue #914.
