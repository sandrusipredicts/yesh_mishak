# Isolated dev backend performance baseline — 2026-07-26

## Outcome

The isolated dev backend completed all nine primary trials and all reliability
checks with **0 unexpected errors, 0 timeouts, and 0 HTTP 5xx responses**.
Public reads, authenticated reads, reversible writes, invalid authentication,
and 10-VU database-backed read pressure remained available throughout the run.

Two material follow-ups were identified:

1. `GET /notifications/unread-count` recorded a three-run median p95 of
   **848.04 ms**, missing the documented **< 500 ms** Phase B target by 348.04
   ms (69.6%).
2. A security-sensitive rate-limit contract check failed and is being tracked
   through a private security process.

The workflow is red only because that security-sensitive contract gate
deliberately fails the run. Every primary scenario passed.

## Target identity

| Item | Value |
|---|---|
| Environment | Isolated `dev` |
| Backend URL | `https://yeshmishak-dev.up.railway.app` |
| Supabase project | `yesh_mishak_dev` (`txpnyewytcfslsdicjbx`) |
| Deployed backend commit | `0fc29edc6964d736da9d322748b86596f52fc0f0` |
| Workload commit | `7caa56bdb63c6a676450a3c4e2d3620687f3533d` |
| Railway project | `[redacted-railway-project-id]` |
| Railway service | `[redacted-railway-service-id]` |
| Railway environment | `[redacted-railway-environment-id]` |
| Railway deployment | `[redacted-railway-deployment-id]` |
| GitHub Actions run | [30196456021](https://github.com/sandrusipredicts/yesh_mishak/actions/runs/30196456021) |
| Raw artifact | [8630343151](https://github.com/sandrusipredicts/yesh_mishak/actions/runs/30196456021/artifacts/8630343151), retained through 2026-08-25 |
| Artifact SHA-256 | `81c495253bad875dce8c39c89df40bdd18e477b26e7857a4cf8af74b6f627a1e` |

The backend deployment identity was taken from the successful Railway commit
status on the deployed `dev` SHA. The load-test workflow SHA is recorded
separately because the workflow branch did not deploy backend application code.

## Previous tooling and baseline

The retained implementation is:

- `backend/load_tests/game_creation_load_test.js` — k6 ISSUE-088 game-create
  scenarios.
- `backend/scripts/prepare_load_test_data.py` — synthetic user/field setup.
- `backend/scripts/measure_production_api.py` — earlier sequential API timing.
- `backend/scripts/benchmark_endpoints.py` and
  `backend/scripts/benchmark_bounds_filtering.py` — local synthetic benchmarks.

The historical records are not a complete reproducible baseline:

- The final ISSUE-088 result records 10 VUs for 60 seconds, Uvicorn with four
  workers, notifications enabled, auth-cache TTL 300 seconds, game-create p95
  **2.95 s**, 0% errors, and successful cleanup.
- It does not retain p50, p99, throughput, status distribution, raw output,
  exact target URL, deployment identifier, or tested commit.
- An older retained 10-VU/20-second debug run is a pre-fix failure, not the
  accepted baseline.
- The earlier public API timing used 20 sequential requests against production,
  so its public-endpoint p95 values are included below only as directional
  context, not as an apples-to-apples regression verdict.

The original game-write workload was not rerun. The dev environment's FCM
project/fan-out isolation is not proven, and the original flow can notify
matching users. Running it would violate this task's no-real-notifications
constraint. Game join/leave was gated for the same reason and because no
test-owned game fixture was available.

## Reproducible workload

Tool: `k6 v2.0.0+dirty (commit/8c3be52cc1-dirty, go1.26.3,
linux/amd64)`, pinned as `grafana/k6:2.0.0`.

| Scenario | Configuration | Coverage | Runs |
|---|---|---|---:|
| Public read | Constant arrival, 1 iteration/3 s, 60 s | health; unbounded, bounded, and empty fields; active and upcoming games | 3 |
| Authenticated read | Constant arrival, 1 iteration/3 s, 60 s | synthetic login setup; `/games/me`; unread count; preferences | 3 |
| Controlled write | Constant arrival, 1 iteration/5 s, 60 s | synthetic push-token save then delete; teardown delete | 3 |
| Invalid auth | 3 VUs, 12 shared iterations | invalid bearer token must return 401 envelope | 1 |
| Connection pressure | 10 VUs, 20 s | bounded fields through the database-backed read path | 1 |
| Security contract check | Withheld | Withheld — tracked through a private security process | 1 |

Every request used a 10-second timeout and an `X-Performance-Test-Run` tag.
The harness refuses non-HTTPS targets, requires the exact dev host, rejects
configured production hosts, and requires an explicit test-run ID. Credentials
came only from the GitHub `dev` environment's dedicated test-account secrets
and were never logged.

## Primary results

The percentiles below are the median of the three run-level percentiles. The
p95 range shows repeatability. Throughput is per endpoint.

| Endpoint | p50 | p95 (run range) | p99 | req/s | Samples | Statuses | Errors / timeouts / 5xx |
|---|---:|---:|---:|---:|---:|---|---|
| `GET /` | 94.09 ms | 148.68 ms (96.21–158.90) | 183.15 ms | 0.3340 | 61 | 200×61 | 0 / 0 / 0 |
| `GET /fields/` unbounded | 500.68 ms | 642.36 ms (610.33–692.48) | 673.84 ms | 0.3340 | 61 | 200×61 | 0 / 0 / 0 |
| `GET /fields/` bounded | 502.10 ms | 572.89 ms (531.06–661.91) | 611.47 ms | 0.3340 | 61 | 200×61 | 0 / 0 / 0 |
| `GET /fields/` empty bounds | 506.07 ms | 617.69 ms (540.79–633.89) | 650.73 ms | 0.3340 | 61 | 200×61 | 0 / 0 / 0 |
| `GET /games/active` | 492.84 ms | 545.93 ms (538.43–632.71) | 578.73 ms | 0.3340 | 61 | 200×61 | 0 / 0 / 0 |
| `GET /games/upcoming` | 505.88 ms | 597.89 ms (568.45–597.96) | 627.72 ms | 0.3340 | 61 | 200×61 | 0 / 0 / 0 |
| `POST /auth/login` (auth runs) | 1130.81 ms | 1130.81 ms (1114.56–1192.50) | 1130.81 ms | 0.0157 | 3 | 200×3 | 0 / 0 / 0 |
| `GET /games/me` | 891.31 ms | 1015.63 ms (963.98–1202.05) | 1216.46 ms | 0.3296 | 63 | 200×63 | 0 / 0 / 0 |
| `GET /notifications/unread-count` | 706.65 ms | **848.04 ms** (810.55–970.56) | 1052.10 ms | 0.3296 | 63 | 200×63 | 0 / 0 / 0 |
| `GET /notifications/preferences` | 703.11 ms | 859.25 ms (824.33–1072.54) | 860.98 ms | 0.3296 | 63 | 200×63 | 0 / 0 / 0 |
| `POST /notifications/push-token` | 1083.34 ms | 1225.39 ms (1221.52–1290.68) | 1267.18 ms | 0.2000 | 38 | 200×38 | 0 / 0 / 0 |
| `DELETE /notifications/push-token` | 703.23 ms | 777.37 ms (774.70–795.70) | 798.58 ms | 0.2000 | 38 | 200×38 | 0 / 0 / 0 |

Scenario throughput was 1.9999–2.0130 req/s for public reads,
1.0024–1.0061 req/s for authenticated reads, and 0.4187–0.4384 req/s for
controlled writes. No iterations were dropped.

## Edge and pressure results

| Scenario | p50 | p95 | p99 | Throughput | Requests | HTTP statuses | Result |
|---|---:|---:|---:|---:|---:|---|---|
| Invalid auth | 311.25 ms | 482.72 ms | 626.15 ms | 6.9719 req/s | 12 | 401×12 | Pass |
| 10-VU connection pressure | 534.93 ms | 846.44 ms | 934.31 ms | 6.1212 req/s | 130 | 200×130 | Pass; no exhaustion symptom |
| Security contract check | — | — | — | — | — | Withheld | **Fail** — tracked through a private security process |

The pressure test establishes that this representative read path did not
surface connection exhaustion at 10 VUs. Exact pool utilization requires
Supabase/Railway infrastructure telemetry and is not inferred from HTTP success.

Cold-start latency was not forcibly measured because restarting the shared dev
service would be an extra state-changing action. The workflow captured the
first health response before workload execution, but it cannot prove the
service was cold. External FCM/Resend latency was intentionally excluded to
avoid real side effects; Supabase network/database latency is included in the
measured endpoints.

## Comparison with retained results

| Endpoint / flow | Retained p95 | Current p95 | Difference | Assessment |
|---|---:|---:|---:|---|
| `GET /` | 361 ms | 148.68 ms | -58.8% | Directionally faster |
| `GET /fields` unbounded | 4181 ms | 642.36 ms | -84.6% | Directionally faster after bounded/RPC work |
| `GET /games/active` | 440 ms | 545.93 ms | +24.1% (+105.93 ms) | Regression candidate, but environment/load method differs; still < 1 s |
| `GET /games/upcoming` | 444 ms | 597.89 ms | +34.7% (+153.89 ms) | Regression candidate, but environment/load method differs; still < 1 s |
| `POST /games/` | 2950 ms | Not run | — | Safety-gated; no valid direct comparison |
| `GET /notifications/unread-count` | Not retained | 848.04 ms | — | New coverage; misses explicit 500 ms target |

No confirmed apples-to-apples latency regression can be claimed from the
retained data because the only final load baseline is the safety-gated game
write and the public timings used a different environment and request model.
The active/upcoming increases should be watched in the next identical dev run;
they do not currently breach the documented read target. The unread-count
target miss and the privately tracked contract failure are confirmed material
gaps.

## Cleanup and notification safety

- Each controlled-write iteration saved one token named
  `perf-baseline-<run-id>` and immediately deleted it.
- A final idempotent delete ran in teardown for every write trial.
- All 76 measured save/delete operations returned 200; teardown requests also
  completed without an HTTP failure.
- No game, player, notification, or field rows were created.
- No test-push, game-create, join, leave, FCM, or Resend endpoint was called.
- The synthetic token is not a valid provider token and was never used for
  delivery.

The write data therefore has no intended retained fixture. A direct database
row-count check remains desirable once dev database/log access is available,
but the API cleanup contract completed successfully.

## Logs and evidence

- Full k6 console logs, summary JSON, point JSON, status tags, exit codes,
  headers, metadata, CSV, Markdown, and aggregate JSON are under
  `docs/evidence/dev-backend-performance-2026-07-26/raw/`. The committed copies
  are sanitized: run-scoped bearer tokens captured in `*-summary.json`
  `setup_data`, Railway resource identifiers, and per-request trace IDs are
  redacted, and the `setup_data` block k6 writes into each summary export is
  removed entirely. No metric, status, or timing values were modified;
  regenerating the analysis from the sanitized summaries reproduces the
  aggregate outputs byte for byte. The security-sensitive contract scenario's
  raw evidence and harness implementation are withheld from this repository
  and retained through the private security process.
- The original unmodified GitHub workflow artifact remains downloadable from
  the Actions run listed above; `artifact-sha256.txt` records its
  GitHub-reported SHA-256. The ZIP is intentionally not committed to the
  repository.
- The successful staging smoke immediately before the baseline verified the
  same deployed commit: nine Tier A tests and six authenticated Tier B tests
  passed, including login, fields, `/games/me`, unread-count, invalid auth, and
  the non-admin authorization boundary.
- Railway server-log capture is pending an authenticated Railway dashboard
  session. Client-side evidence shows no 5xx/timeout to correlate; this report
  does not fabricate a backend-log review.

## Commands

The canonical command implementation is
`.github/workflows/dev-backend-performance.yml`. Its essential commands are:

```bash
docker pull grafana/k6:2.0.0
docker run --rm grafana/k6:2.0.0 version

docker run --rm --user "$(id -u):$(id -g)" \
  -v "${GITHUB_WORKSPACE}:/work" \
  -e BASE_URL -e EXPECTED_DEV_HOST -e PRODUCTION_BACKEND_HOSTS \
  -e STAGING_TEST_EMAIL -e STAGING_TEST_PASSWORD \
  -e SCENARIO=public-read -e TEST_RUN_ID="<unique-run-id>" \
  grafana/k6:2.0.0 run \
  --summary-export /work/backend/load_tests/results/public-read-run-1-summary.json \
  --out json=/work/backend/load_tests/results/public-read-run-1-points.json \
  /work/backend/load_tests/dev_backend_baseline.js

python backend/scripts/analyze_load_results.py \
  docs/evidence/dev-backend-performance-2026-07-26/raw
```

The same k6 command was repeated for all scenarios and run numbers listed
above. The workflow validates the exact host before any request and uploads
artifacts even when a contract gate fails.

Future authenticated runs must follow the
[synthetic dev test identity migration runbook](synthetic-dev-test-identity.md).
Artifacts use only the bounded label `synthetic_dev_test_identity`; the
sanitizer fails closed on mailbox, JWT, Authorization, access/refresh-token,
password-field, and credential-variable patterns before upload. The historical
identity privacy finding and remediation status remain recorded in the
incident-response document rather than being rewritten out of the baseline.

## Acceptance review

| Criterion | Status |
|---|---|
| Prior tooling/results identified | Complete |
| Reproducible workload | Complete |
| Three runs per primary scenario | Complete |
| p50/p95/p99/throughput/errors/timeouts/statuses | Complete |
| No unexpected 5xx | Complete |
| Direct prior comparison | Complete with explicit comparability limitation |
| Material gaps documented | Complete |
| Follow-up issues tracked | Performance issue published (#1026); security finding tracked privately |
| No production data/notifications | Complete |
| Test cleanup | API cleanup complete; direct DB verification pending access |
| Railway backend log review | Pending authenticated dashboard access |
