"""ISSUE-074: Production API response time measurement.

Measures real production API response times by making HTTP requests
to the deployed backend. No mocks — real network, real database.

Environment variables:
    PROD_API_BASE_URL  — Required. e.g. https://your-api.example.com
    PROD_USER_JWT      — Optional. JWT for authenticated user endpoints.
    PROD_ADMIN_JWT     — Optional. JWT for admin endpoints.

Security:
    - Never prints token values.
    - Skips authenticated endpoints when tokens are missing.
    - Does not create or modify any data unless explicitly opted in.

Usage:
    $env:PROD_API_BASE_URL = "https://your-api-url"
    $env:PROD_USER_JWT = "..."       # optional
    $env:PROD_ADMIN_JWT = "..."      # optional
    cd backend
    .venv\\Scripts\\python.exe -m scripts.measure_production_api
    .venv\\Scripts\\python.exe -m scripts.measure_production_api --runs 30
    .venv\\Scripts\\python.exe -m scripts.measure_production_api --json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urljoin

try:
    import httpx
except ImportError:
    httpx = None

try:
    import requests as requests_lib
except ImportError:
    requests_lib = None


def _get_http_client():
    """Return a minimal HTTP adapter wrapping httpx or requests."""
    if httpx is not None:
        client = httpx.Client(timeout=30.0, follow_redirects=True)

        def do_request(method: str, url: str, headers: dict | None = None, json_body: dict | None = None):
            if method == "GET":
                resp = client.get(url, headers=headers)
            elif method == "POST":
                resp = client.post(url, headers=headers, json=json_body)
            else:
                resp = client.get(url, headers=headers)
            return resp.status_code

        return do_request, "httpx"

    if requests_lib is not None:
        session = requests_lib.Session()

        def do_request(method: str, url: str, headers: dict | None = None, json_body: dict | None = None):
            if method == "GET":
                resp = session.get(url, headers=headers, timeout=30)
            elif method == "POST":
                resp = session.post(url, headers=headers, json=json_body, timeout=30)
            else:
                resp = session.get(url, headers=headers, timeout=30)
            return resp.status_code

        return do_request, "requests"

    print("ERROR: Neither httpx nor requests is installed.", file=sys.stderr)
    print("Install one:  pip install httpx   OR   pip install requests", file=sys.stderr)
    sys.exit(1)


def _measure(
    do_request,
    method: str,
    url: str,
    headers: dict | None = None,
    json_body: dict | None = None,
    runs: int = 20,
) -> dict:
    times = []
    status_codes = []
    errors = 0

    for _ in range(runs):
        start = time.perf_counter()
        try:
            status = do_request(method, url, headers=headers, json_body=json_body)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)
            status_codes.append(status)
            if status >= 500:
                errors += 1
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)
            status_codes.append(0)
            errors += 1

    if not times:
        return {"runs": runs, "error": "no successful requests"}

    times_sorted = sorted(times)
    p95_idx = max(0, int(len(times_sorted) * 0.95) - 1)

    code_dist = {}
    for c in status_codes:
        code_dist[c] = code_dist.get(c, 0) + 1

    return {
        "runs": runs,
        "min_ms": round(min(times), 1),
        "max_ms": round(max(times), 1),
        "avg_ms": round(statistics.mean(times), 1),
        "median_ms": round(statistics.median(times), 1),
        "p95_ms": round(times_sorted[p95_idx], 1),
        "stdev_ms": round(statistics.stdev(times), 1) if len(times) > 1 else 0,
        "errors": errors,
        "status_distribution": code_dist,
    }


def main():
    parser = argparse.ArgumentParser(description="ISSUE-074 production API response time measurement")
    parser.add_argument("--runs", type=int, default=20, help="Number of runs per endpoint (default: 20)")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of table")
    args = parser.parse_args()

    base_url = os.environ.get("PROD_API_BASE_URL", "").rstrip("/")
    user_jwt = os.environ.get("PROD_USER_JWT", "")
    admin_jwt = os.environ.get("PROD_ADMIN_JWT", "")

    if not base_url:
        print("ERROR: PROD_API_BASE_URL environment variable is required.", file=sys.stderr)
        print("Example: $env:PROD_API_BASE_URL = 'https://your-api.example.com'", file=sys.stderr)
        sys.exit(1)

    do_request, http_lib = _get_http_client()

    user_headers = {"Authorization": f"Bearer {user_jwt}"} if user_jwt else None
    admin_headers = {"Authorization": f"Bearer {admin_jwt}"} if admin_jwt else None

    now_utc = datetime.now(timezone.utc).isoformat()

    endpoints = [
        {
            "name": "GET /",
            "method": "GET",
            "path": "/",
            "headers": None,
            "body": None,
            "auth": "none",
            "safe": True,
        },
        {
            "name": "GET /fields",
            "method": "GET",
            "path": "/fields",
            "headers": None,
            "body": None,
            "auth": "none",
            "safe": True,
        },
        {
            "name": "GET /fields (bounded)",
            "method": "GET",
            "path": "/fields?north=33.0&south=31.0&east=35.5&west=34.0",
            "headers": None,
            "body": None,
            "auth": "none",
            "safe": True,
        },
        {
            "name": "GET /games/active",
            "method": "GET",
            "path": "/games/active",
            "headers": None,
            "body": None,
            "auth": "none",
            "safe": True,
        },
        {
            "name": "GET /games/upcoming",
            "method": "GET",
            "path": "/games/upcoming",
            "headers": None,
            "body": None,
            "auth": "none",
            "safe": True,
        },
        {
            "name": "GET /notifications",
            "method": "GET",
            "path": "/notifications/",
            "headers": user_headers,
            "body": None,
            "auth": "user",
            "safe": True,
        },
        {
            "name": "GET /notifications/unread-count",
            "method": "GET",
            "path": "/notifications/unread-count",
            "headers": user_headers,
            "body": None,
            "auth": "user",
            "safe": True,
        },
        {
            "name": "GET /notifications/preferences",
            "method": "GET",
            "path": "/notifications/preferences",
            "headers": user_headers,
            "body": None,
            "auth": "user",
            "safe": True,
        },
        {
            "name": "GET /admin/stats",
            "method": "GET",
            "path": "/admin/stats",
            "headers": admin_headers,
            "body": None,
            "auth": "admin",
            "safe": True,
        },
        {
            "name": "GET /admin/monitoring",
            "method": "GET",
            "path": "/admin/monitoring",
            "headers": admin_headers,
            "body": None,
            "auth": "admin",
            "safe": True,
        },
    ]

    results = {}
    skipped = []

    is_json = args.json

    if not is_json:
        print(f"Production API Response Time Measurement")
        print(f"Base URL: {base_url}")
        print(f"HTTP library: {http_lib}")
        print(f"Timestamp: {now_utc}")
        print(f"Runs per endpoint: {args.runs}")
        print(f"User JWT provided: {'yes' if user_jwt else 'no'}")
        print(f"Admin JWT provided: {'yes' if admin_jwt else 'no'}")
        print()

    for ep in endpoints:
        name = ep["name"]
        auth_level = ep["auth"]

        if auth_level == "user" and not user_jwt:
            skipped.append({"name": name, "reason": "PROD_USER_JWT not provided"})
            if not is_json:
                print(f"  SKIP  {name} — no user JWT")
            continue
        if auth_level == "admin" and not admin_jwt:
            skipped.append({"name": name, "reason": "PROD_ADMIN_JWT not provided"})
            if not is_json:
                print(f"  SKIP  {name} — no admin JWT")
            continue

        url = f"{base_url}{ep['path']}"
        if not is_json:
            print(f"  RUN   {name} ...", end="", flush=True)

        result = _measure(
            do_request,
            ep["method"],
            url,
            headers=ep["headers"],
            json_body=ep["body"],
            runs=args.runs,
        )
        result["auth"] = auth_level
        result["url_path"] = ep["path"]
        results[name] = result
        if not is_json:
            print(f" avg={result['avg_ms']:.0f}ms  p95={result['p95_ms']:.0f}ms  status={result['status_distribution']}")

    output = {
        "metadata": {
            "base_url": base_url,
            "http_library": http_lib,
            "timestamp": now_utc,
            "runs_per_endpoint": args.runs,
            "user_jwt_provided": bool(user_jwt),
            "admin_jwt_provided": bool(admin_jwt),
        },
        "results": results,
        "skipped": skipped,
    }

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print()
        print(f"{'Endpoint':<36} {'Auth':>6} {'Min':>8} {'Avg':>8} {'Med':>8} {'P95':>8} {'Max':>8} {'Err':>4}  Status")
        print("-" * 105)
        for name, r in results.items():
            codes = " ".join(f"{c}:{n}" for c, n in sorted(r["status_distribution"].items()))
            print(
                f"{name:<36} {r['auth']:>6} {r['min_ms']:>7.0f} {r['avg_ms']:>7.0f} "
                f"{r['median_ms']:>7.0f} {r['p95_ms']:>7.0f} {r['max_ms']:>7.0f} "
                f"{r['errors']:>4}  {codes}"
            )
        if skipped:
            print()
            print("Skipped endpoints:")
            for s in skipped:
                print(f"  {s['name']} — {s['reason']}")

        print()
        print("All times in milliseconds. Errors include 5xx responses and connection failures.")
        print()
        print("Endpoints not measured (unsafe for automated production runs):")
        print("  POST /auth/login — requires real credentials; risk of account lockout")
        print("  POST /auth/google — requires real Google ID token")
        print("  POST /games/ — creates real data in production database")


if __name__ == "__main__":
    main()
