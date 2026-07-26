# Token exposure window audit — status: PARTIALLY COMPLETED

**Summary: no evidence of misuse was found, and misuse cannot be conclusively
ruled out.** Database-side checks were completed and are clean. The
authenticated request-log review could not be performed because the historical
logs are no longer reachable. Because per-request user attribution does not
exist in this system's telemetry, **read-only use of the exposed tokens cannot
be excluded.**

Sanitized by construction: no email addresses, tokens, token fragments, IP
addresses, or infrastructure secrets appear below.

| Audit strand | Outcome |
|---|---|
| Residue and unexpected-write checks (dev database) | **Completed — clean** |
| Request-volume review across the window | **Completed — all rows attributable** |
| Account last-login signal | **Inconclusive** — value predates the window |
| Authenticated request-log review | **Unavailable** — retention/console limits |
| Read-only token use | **Cannot be ruled out** |

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

## Access paths — first attempt (blocked), later resolved

The audit was initially blocked. Recorded for provenance:

| Path | Result at first attempt |
|---|---|
| Railway CLI | Not installed; no session |
| Supabase CLI | Not installed; no session |
| Connected browser session | None connected |
| Local database credentials | Present, but scoped to the **production** project — wrong target and out of bounds for this audit |

Access was subsequently provided through an authenticated console session, and
the query set below was run by the project owner against the isolated dev
project. No credentials were requested, read for use, or exposed at any point,
and no production system was queried.

## Query set (executed — see Results below)

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

## Results — executed 2026-07-26

The read-only query set (`e12-10-audit-queries.sql`) was run against the
isolated dev project, and the dev backend service identity was confirmed from
the console before any query was run: correct dev environment, correct dev
service domain, correct deployment.

### Database checks — clean

| Check | Violations |
|---|---|
| Performance-test push-token residue (token prefix) | 0 |
| Any push-token row remaining for the test account | 0 |
| Games created by the test account | 0 |
| Game-player rows for the test account | 0 |
| Notifications for the test account created in the window | 0 |
| Field reports submitted by the test account | 0 |
| Notification-preference rows created in the window | 0 |
| Identity rows for the test account | 0 |

This closes the database cleanup question: no performance-test push token,
installation, game, player, notification, or field record remains, and no
unexpected write of any kind was made by the account. Because any write
performed with a stolen token would have persisted regardless of what request
telemetry captured, **write abuse is positively excluded.**

### Request-volume review — all rows attributable

Every request-volume row inside the exposure window was attributable to the
known CI run or to documented containment activity: the tail of the known run,
one pre-revocation authenticated check, six post-revocation rejections (one per
exposed token), and the revocation request itself. No unexplained rows were
observed.

The six post-revocation rejections are independent confirmation at the data
layer that revocation took effect on every exposed token.

*Boundary note:* the review's lower bound was derived from the last request
timestamp in the committed evidence, which excludes the withheld
security-sensitive scenario. The real run therefore continued slightly past
that bound, which is why rows appear at the very start of the reviewed range.
They are expected, not anomalous.

### Account last-login signal — inconclusive

The account's stored last-login value predates the exposure window, so it
carries no attribution value here. It also means the logins performed during
the known run are not reflected in that field, which suggests the last-login
update path may not be functioning in this environment. That is unverified and
is recorded as a follow-up observation, not a finding of this audit.

### Authenticated request-log review — UNAVAILABLE

Searches for authentication success and logout events over the exposure window
returned no results, and the console does not permit selecting a window that
far back. **This is a retention and tooling limitation, not evidence that no
logins occurred.** No conclusion in either direction may be drawn from it.

## Residual limitation

Per-request user attribution does not exist in this system's telemetry:

- request metrics are stored without any user identifier, by deliberate design;
- request logs record no user identity and no user agent;
- the historical authentication logs are no longer reachable.

Consequently **read-only use of the exposed tokens during the window cannot be
conclusively ruled out.** Someone who read data with a stolen token would have
left no attributable trace. What can be stated positively is that no write, no
residue, and no unexplained request volume exists, and that the exposure was
bounded to roughly 87 minutes against an isolated dev environment holding only
synthetic test data.

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

The audit is **partially completed**.

**Proven:** the direct database cleanup check is satisfied — no residue and no
unexpected writes — and all request volume in the window is accounted for.

**Permanently unprovable:** the authenticated request-log review. The logs have
aged out, so this acceptance item cannot be satisfied retrospectively no matter
how much time is spent on it.

**Residual risk:** read-only use of the exposed tokens cannot be excluded.
Accepting that residual is an owner decision, not something this document can
settle. It is the one item standing between issue #914 and closure.

Mitigating context for that decision: the environment is an isolated dev
deployment containing synthetic test data, the account is a synthetic test
identity, exposure lasted roughly 87 minutes, all tokens were revoked and each
verified rejected, and the root cause has been fixed so no future run writes a
credential to an artifact.
