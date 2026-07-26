# Performance baseline follow-up issue drafts

The performance follow-up below was published as issue #1026 on 2026-07-26
(after an initial automated creation attempt failed with HTTP 403
`Resource not accessible by integration`).

A second, security-sensitive finding from the same baseline run is tracked
privately as a GitHub Security Advisory and is intentionally not described in
this repository until remediation is deployed.

## Draft 1 — unread-count performance (published as #1026)

**Title:** `perf: optimize GET /notifications/unread-count to meet 500 ms p95`

### Finding

The isolated-dev backend baseline completed three comparable authenticated-read
runs with zero errors, timeouts, or 5xx responses, but
`GET /notifications/unread-count` missed its documented Phase B target.

- Three-run median p50: **706.65 ms**
- Three-run median p95: **848.04 ms** (run range **810.55–970.56 ms**)
- Three-run median p99: **1052.10 ms**
- Samples: **63**, all HTTP 200
- Mean endpoint throughput: **0.3296 req/s**
- Target: **p95 < 500 ms**

Evidence:
<https://github.com/sandrusipredicts/yesh_mishak/actions/runs/30196456021>.

Tested backend deployment:
`0fc29edc6964d736da9d322748b86596f52fc0f0`; k6 `v2.0.0`.

### Scope

Profile the authenticated user lookup plus unread-count query on the isolated
dev deployment, confirm whether the optimized count path or fallback path is
used, and remove avoidable database/network round trips. Do not weaken
authorization or count correctness.

### Acceptance criteria

- Repeat the same `authenticated-read` workload for at least three 60-second
  runs.
- Median run p95 is < 500 ms.
- 0 unexpected errors, 0 timeouts, and 0 5xx responses.
- Response contract and unread-count correctness remain covered.
- Include query/backend logs and before/after raw k6 artifacts.
