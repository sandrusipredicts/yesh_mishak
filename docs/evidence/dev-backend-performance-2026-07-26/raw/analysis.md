# Dev Backend Performance Results

- Tested commit: `7caa56bdb63c6a676450a3c4e2d3620687f3533d`
- Target host: `yeshmishak-dev.up.railway.app`
- GitHub run: `30196456021`
- Railway deployment ID: `[redacted-railway-deployment-id]`

## Three-run primary-scenario aggregate

| Scenario | Endpoint | Runs | p50 median | p95 median (range) | p99 median | Endpoint req/s | Requests | Error rate | Statuses | 5xx |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|
| authenticated-read | games_me | 3 | 891.31 ms | 1015.63 ms (963.98–1202.05) | 1216.46 ms | 0.3296 | 63 | 0.00% | `{"200": 63}` | 0 |
| authenticated-read | login | 3 | 1130.81 ms | 1130.81 ms (1114.56–1192.50) | 1130.81 ms | 0.0157 | 3 | 0.00% | `{"200": 3}` | 0 |
| authenticated-read | notification_preferences | 3 | 703.11 ms | 859.25 ms (824.33–1072.54) | 860.98 ms | 0.3296 | 63 | 0.00% | `{"200": 63}` | 0 |
| authenticated-read | notifications_unread | 3 | 706.65 ms | 848.04 ms (810.55–970.56) | 1052.10 ms | 0.3296 | 63 | 0.00% | `{"200": 63}` | 0 |
| controlled-write | login | 3 | 1127.50 ms | 1127.50 ms (1098.51–1152.74) | 1127.50 ms | 0.0158 | 3 | 0.00% | `{"200": 3}` | 0 |
| controlled-write | push_token_delete | 3 | 703.23 ms | 777.37 ms (774.70–795.70) | 798.58 ms | 0.2000 | 38 | 0.00% | `{"200": 38}` | 0 |
| controlled-write | push_token_save | 3 | 1083.34 ms | 1225.39 ms (1221.52–1290.68) | 1267.18 ms | 0.2000 | 38 | 0.00% | `{"200": 38}` | 0 |
| public-read | fields_bounded | 3 | 502.10 ms | 572.89 ms (531.06–661.91) | 611.47 ms | 0.3340 | 61 | 0.00% | `{"200": 61}` | 0 |
| public-read | fields_empty | 3 | 506.07 ms | 617.69 ms (540.79–633.89) | 650.73 ms | 0.3340 | 61 | 0.00% | `{"200": 61}` | 0 |
| public-read | fields_unbounded | 3 | 500.68 ms | 642.36 ms (610.33–692.48) | 673.84 ms | 0.3340 | 61 | 0.00% | `{"200": 61}` | 0 |
| public-read | games_active | 3 | 492.84 ms | 545.93 ms (538.43–632.71) | 578.73 ms | 0.3340 | 61 | 0.00% | `{"200": 61}` | 0 |
| public-read | games_upcoming | 3 | 505.88 ms | 597.89 ms (568.45–597.96) | 627.72 ms | 0.3340 | 61 | 0.00% | `{"200": 61}` | 0 |
| public-read | root | 3 | 94.09 ms | 148.68 ms (96.21–158.90) | 183.15 ms | 0.3340 | 61 | 0.00% | `{"200": 61}` | 0 |

## Run-level reliability

| Scenario | Run | Requests | Req/s | Error rate | HTTP-failed rate | Timeouts | 5xx | Dropped iterations | Exit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| authenticated-read | 1 | 64 | 1.0024 | 0.00% | 0.00% | 0 | 0 | 0 | 0 |
| authenticated-read | 2 | 64 | 1.0061 | 0.00% | 0.00% | 0 | 0 | 0 | 0 |
| authenticated-read | 3 | 64 | 1.0053 | 0.00% | 0.00% | 0 | 0 | 0 | 0 |
| connection-pressure | 1 | 130 | 6.1212 | 0.00% | 0.00% | 0 | 0 | 0 | 0 |
| controlled-write | 1 | 28 | 0.4379 | 0.00% | 0.00% | 0 | 0 | 0 | 0 |
| controlled-write | 2 | 26 | 0.4187 | 0.00% | 0.00% | 0 | 0 | 0 | 0 |
| controlled-write | 3 | 28 | 0.4384 | 0.00% | 0.00% | 0 | 0 | 0 | 0 |
| invalid-auth | 1 | 12 | 6.9719 | 0.00% | 0.00% | 0 | 0 | 0 | 0 |
| public-read | 1 | 120 | 1.9999 | 0.00% | 0.00% | 0 | 0 | 0 | 0 |
| public-read | 2 | 120 | 1.9999 | 0.00% | 0.00% | 0 | 0 | 0 | 0 |
| public-read | 3 | 126 | 2.0130 | 0.00% | 0.00% | 0 | 0 | 0 | 0 |
