"""ISSUE-082: Bounded vs unbounded GET /fields performance comparison.

Measures response time, payload size, fields returned, and Supabase query count
for GET /fields with and without viewport bounds at 500, 1,000, and 5,000 fields.

All measurements use FakeSupabase (in-memory). No real database or network.
Results are labeled SYNTHETIC -- they measure Python/FastAPI processing cost only,
not Supabase HTTP latency or PostgreSQL query time.

Usage:
    cd backend
    .venv\\Scripts\\python.exe -m scripts.benchmark_bounds_filtering
    .venv\\Scripts\\python.exe -m scripts.benchmark_bounds_filtering --json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)

REGULAR_USER = {
    "id": "00000000-0000-0000-0000-000000000002",
    "email": "user@bench.test",
    "name": "Bench User",
    "username": "benchuser",
    "phone_number": None,
    "role": "user",
    "status": "active",
    "google_sub": None,
    "password_hash": "",
    "last_login": NOW.isoformat(),
}

GAME_TEMPLATE = {
    "field_id": None,
    "creator_id": None,
    "sport_type": "football",
    "max_players": 10,
    "players_present": 1,
    "status": "open",
    "created_at": NOW.isoformat(),
    "expires_at": (NOW + timedelta(hours=2)).isoformat(),
    "scheduled_at": None,
    "age_note": None,
    "min_age": None,
    "max_age": None,
}

# Israel bounding box: lat 29.5-33.3, lng 34.2-35.9
ISRAEL_LAT_MIN = 29.5
ISRAEL_LAT_MAX = 33.3
ISRAEL_LNG_MIN = 34.2
ISRAEL_LNG_MAX = 35.9

# Tel Aviv viewport (typical user view at zoom ~14)
VIEWPORT_BOUNDS = {
    "north": 32.15,
    "south": 31.95,
    "east": 34.85,
    "west": 34.70,
}


def _make_fields_spread(count: int) -> list[dict[str, Any]]:
    """Generate fields spread across Israel with ~20% clustered in Tel Aviv viewport."""
    fields = []
    tel_aviv_count = int(count * 0.2)

    for i in range(tel_aviv_count):
        frac = i / max(tel_aviv_count - 1, 1)
        fields.append({
            "id": f"field-tlv-{i:05d}",
            "name": f"Tel Aviv Field {i}",
            "lat": 31.95 + frac * 0.2,
            "lng": 34.70 + frac * 0.15,
            "sport_type": "football",
            "city": "Tel Aviv",
            "surface_type": "grass",
            "verified": True,
            "approval_status": "approved",
            "status": "open",
            "created_at": "2026-01-01T00:00:00+00:00",
            "lighting": True,
        })

    outside_count = count - tel_aviv_count
    for i in range(outside_count):
        frac = i / max(outside_count - 1, 1)
        lat = ISRAEL_LAT_MIN + frac * (ISRAEL_LAT_MAX - ISRAEL_LAT_MIN)
        lng = ISRAEL_LNG_MIN + frac * (ISRAEL_LNG_MAX - ISRAEL_LNG_MIN)
        # Skip fields that fall inside the viewport
        if (VIEWPORT_BOUNDS["south"] <= lat <= VIEWPORT_BOUNDS["north"]
                and VIEWPORT_BOUNDS["west"] <= lng <= VIEWPORT_BOUNDS["east"]):
            lat = ISRAEL_LAT_MIN + 0.1
            lng = ISRAEL_LNG_MIN + 0.1
        fields.append({
            "id": f"field-il-{i:05d}",
            "name": f"Israel Field {i}",
            "lat": round(lat, 7),
            "lng": round(lng, 7),
            "sport_type": "both",
            "city": "Other",
            "surface_type": "synthetic",
            "verified": True,
            "approval_status": "approved",
            "status": "open",
            "created_at": "2026-01-01T00:00:00+00:00",
            "lighting": False,
        })

    return fields


def _make_games_for_fields(fields: list[dict], ratio: float = 0.15) -> list[dict[str, Any]]:
    """Create active games for a fraction of fields."""
    games = []
    game_count = int(len(fields) * ratio)
    for i in range(game_count):
        g = deepcopy(GAME_TEMPLATE)
        g["id"] = f"game-{i:05d}"
        g["field_id"] = fields[i % len(fields)]["id"]
        g["creator_id"] = REGULAR_USER["id"]
        g["created_by"] = REGULAR_USER["id"]
        games.append(g)
    return games


class FakeResponse:
    def __init__(self, data: list[dict[str, Any]]):
        self.data = data
        self.count = len(data)


class CountingQuery:
    """FakeTableQuery that counts how many .execute() calls are made."""

    call_counter: dict[str, int] = {}

    def __init__(self, table_name: str, rows: list[dict[str, Any]]):
        self.table_name = table_name
        self.rows = rows
        self.filters: list[tuple[str, Any]] = []
        self.in_filters: list[tuple[str, list]] = []
        self._range: tuple[int, int] | None = None
        self._limit: int | None = None
        self.insert_payload: Any = None
        self.update_payload: dict | None = None

    def select(self, columns: str, **kwargs: Any) -> "CountingQuery":
        return self

    def eq(self, col: str, val: Any) -> "CountingQuery":
        self.filters.append((col, val))
        return self

    def neq(self, col: str, val: Any) -> "CountingQuery":
        return self

    def in_(self, col: str, vals: list) -> "CountingQuery":
        self.in_filters.append((col, vals))
        return self

    def gte(self, col: str, val: Any) -> "CountingQuery":
        self.filters.append(("__gte", (col, val)))
        return self

    def lte(self, col: str, val: Any) -> "CountingQuery":
        self.filters.append(("__lte", (col, val)))
        return self

    def is_(self, col: str, val: str) -> "CountingQuery":
        self.filters.append(("__is_null", (col, val)))
        return self

    def limit(self, n: int) -> "CountingQuery":
        self._limit = n
        return self

    def range(self, start: int, end: int) -> "CountingQuery":
        self._range = (start, end)
        return self

    def order(self, col: str, desc: bool = False) -> "CountingQuery":
        return self

    def insert(self, payload: Any) -> "CountingQuery":
        self.insert_payload = payload
        return self

    def update(self, payload: dict) -> "CountingQuery":
        self.update_payload = payload
        return self

    def execute(self) -> FakeResponse:
        CountingQuery.call_counter[self.table_name] = (
            CountingQuery.call_counter.get(self.table_name, 0) + 1
        )

        if self.insert_payload is not None:
            if isinstance(self.insert_payload, list):
                return FakeResponse(data=self.insert_payload)
            return FakeResponse(data=[self.insert_payload])

        rows = self.rows
        for col, val in self.filters:
            if col == "__gte":
                c, threshold = val
                rows = [r for r in rows if r.get(c) is not None and r[c] >= threshold]
            elif col == "__lte":
                c, threshold = val
                rows = [r for r in rows if r.get(c) is not None and r[c] <= threshold]
            elif col == "__is_null":
                c, _ = val
                rows = [r for r in rows if r.get(c) is None]
            else:
                rows = [r for r in rows if r.get(col) == val]

        for col, vals in self.in_filters:
            rows = [r for r in rows if r.get(col) in vals]

        if self.update_payload is not None:
            for r in rows:
                r.update(self.update_payload)
            return FakeResponse(data=rows)

        if self._range is not None:
            start, end = self._range
            rows = rows[start:end + 1]
        elif self._limit is not None:
            rows = rows[:self._limit]

        return FakeResponse(data=rows)


class CountingSupabase:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]):
        self.tables = tables

    def table(self, name: str) -> CountingQuery:
        if name not in self.tables:
            self.tables[name] = []
        return CountingQuery(name, self.tables[name])

    def rpc(self, name: str, params: dict) -> Any:
        class FakeRpc:
            def execute(self) -> Any:
                return FakeResponse(data=[{"game": {}}])
        return FakeRpc()


def _build_data(field_count: int, game_ratio: float = 0.15):
    fields = _make_fields_spread(field_count)
    games = _make_games_for_fields(fields, ratio=game_ratio)
    participants = []
    for g in games:
        participants.append({
            "id": f"part-{g['id']}",
            "game_id": g["id"],
            "user_id": REGULAR_USER["id"],
            "joined_at": NOW.isoformat(),
        })
    return {
        "users": [deepcopy(REGULAR_USER)],
        "fields": fields,
        "games": games,
        "game_players": participants,
        "notifications": [],
        "notification_preferences": [],
        "push_tokens": [],
        "field_reports": [],
        "user_moderation_audit": [],
    }


def _run_measurement(client, url: str, runs: int, tables: dict) -> dict:
    """Run a GET request multiple times and collect metrics."""
    times = []
    response_sizes = []
    fields_returned = []
    query_counts_per_run = []

    for _ in range(runs):
        CountingQuery.call_counter.clear()

        start = time.perf_counter()
        resp = client.get(url)
        elapsed_ms = (time.perf_counter() - start) * 1000

        times.append(elapsed_ms)
        body = resp.json()
        body_bytes = len(json.dumps(body).encode("utf-8"))
        response_sizes.append(body_bytes)
        fields_returned.append(len(body) if isinstance(body, list) else 0)
        query_counts_per_run.append(dict(CountingQuery.call_counter))

    times_sorted = sorted(times)
    p95_idx = max(0, int(len(times_sorted) * 0.95) - 1)

    total_queries = {}
    for qc in query_counts_per_run:
        for table, count in qc.items():
            total_queries[table] = total_queries.get(table, 0) + count
    avg_queries = {t: round(c / runs, 1) for t, c in total_queries.items()}

    return {
        "runs": runs,
        "fields_returned": fields_returned[0],
        "response_bytes": response_sizes[0],
        "response_kb": round(response_sizes[0] / 1024, 1),
        "avg_ms": round(statistics.mean(times), 2),
        "median_ms": round(statistics.median(times), 2),
        "p95_ms": round(times_sorted[p95_idx], 2),
        "min_ms": round(min(times), 2),
        "max_ms": round(max(times), 2),
        "avg_queries_per_request": avg_queries,
        "total_avg_queries": round(sum(avg_queries.values()), 1),
    }


def main():
    parser = argparse.ArgumentParser(description="ISSUE-082 bounds filtering benchmark")
    parser.add_argument("--runs", type=int, default=10, help="Runs per measurement (default: 10)")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    args = parser.parse_args()

    # Monkeypatch before importing app
    import app.db.supabase

    field_counts = [500, 1000, 5000]
    all_results = {}

    bounded_url = (
        f"/fields/?north={VIEWPORT_BOUNDS['north']}"
        f"&south={VIEWPORT_BOUNDS['south']}"
        f"&east={VIEWPORT_BOUNDS['east']}"
        f"&west={VIEWPORT_BOUNDS['west']}"
    )
    unbounded_url = "/fields/"

    from unittest.mock import patch

    # Routers use `from app.db.supabase import get_supabase_client` which
    # binds the original function locally. We must patch every module that
    # imported it so they all call through to our fake.
    fake_supabase = CountingSupabase({})
    getter = lambda: fake_supabase

    patches = [
        patch("app.db.supabase.get_supabase_client", getter),
        patch("app.db.supabase.get_supabase_service_role_client", getter),
        patch("app.routers.fields.get_supabase_client", getter),
        patch("app.routers.game_payloads.get_supabase_client", getter),
        patch("app.routers.game_lifecycle.get_supabase_client", getter),
        patch("app.routers.game_lifecycle.get_now", return_value=NOW),
    ]

    from fastapi.testclient import TestClient
    from app.main import app as fastapi_app
    client = TestClient(fastapi_app)

    for p in patches:
        p.start()

    try:
      for field_count in field_counts:
        tables = _build_data(field_count)
        fake_supabase.tables = tables

        tel_aviv_count = int(field_count * 0.2)

        unbounded = _run_measurement(client, unbounded_url, args.runs, tables)
        bounded = _run_measurement(client, bounded_url, args.runs, tables)

        all_results[field_count] = {
            "total_fields_in_db": field_count,
            "fields_in_viewport": tel_aviv_count,
            "unbounded": unbounded,
            "bounded": bounded,
        }
    finally:
      for p in patches:
          p.stop()

    if args.json:
        print(json.dumps(all_results, indent=2))
        return

    print()
    print("=" * 100)
    print("ISSUE-082: Bounded vs Unbounded GET /fields -- Synthetic Benchmark")
    print("=" * 100)
    print()
    print(f"Methodology: FakeSupabase (in-memory), FastAPI TestClient, {args.runs} runs per measurement")
    print(f"Viewport: Tel Aviv area (north={VIEWPORT_BOUNDS['north']}, south={VIEWPORT_BOUNDS['south']}, "
          f"east={VIEWPORT_BOUNDS['east']}, west={VIEWPORT_BOUNDS['west']})")
    print(f"Data distribution: 20% of fields inside viewport, 80% outside")
    print(f"Game ratio: 15% of fields have active games")
    print(f"NOTE: Times measure Python/FastAPI processing only -- no real DB or network latency")
    print()

    print(f"{'':-<100}")
    print(f"{'Fields in DB':>14} | {'Mode':<12} | {'Returned':>8} | {'Payload':>10} | "
          f"{'Avg ms':>8} | {'P95 ms':>8} | {'DB Queries':>10}")
    print(f"{'':-<100}")

    for fc in field_counts:
        r = all_results[fc]
        ub = r["unbounded"]
        bd = r["bounded"]

        print(f"{fc:>14,} | {'unbounded':<12} | {ub['fields_returned']:>8,} | "
              f"{ub['response_kb']:>8.1f} KB | {ub['avg_ms']:>8.1f} | {ub['p95_ms']:>8.1f} | "
              f"{ub['total_avg_queries']:>10.0f}")
        print(f"{'':>14} | {'bounded':<12} | {bd['fields_returned']:>8,} | "
              f"{bd['response_kb']:>8.1f} KB | {bd['avg_ms']:>8.1f} | {bd['p95_ms']:>8.1f} | "
              f"{bd['total_avg_queries']:>10.0f}")

        reduction_fields = (1 - bd['fields_returned'] / max(ub['fields_returned'], 1)) * 100
        reduction_payload = (1 - bd['response_bytes'] / max(ub['response_bytes'], 1)) * 100
        reduction_time = (1 - bd['avg_ms'] / max(ub['avg_ms'], 0.001)) * 100
        reduction_queries = (1 - bd['total_avg_queries'] / max(ub['total_avg_queries'], 0.001)) * 100

        print(f"{'':>14} | {'reduction':<12} | {reduction_fields:>7.0f}% | "
              f"{reduction_payload:>8.0f}%    | {reduction_time:>7.0f}% | {'':>8} | "
              f"{reduction_queries:>8.0f}%")
        print(f"{'':-<100}")

    print()
    print("Query breakdown (avg per request):")
    for fc in field_counts:
        r = all_results[fc]
        print(f"\n  {fc:,} fields:")
        for mode in ("unbounded", "bounded"):
            qs = r[mode]["avg_queries_per_request"]
            parts = ", ".join(f"{t}={c}" for t, c in sorted(qs.items()))
            print(f"    {mode:12s}: {parts}")

    print()
    print("All times in milliseconds. Payload sizes are uncompressed JSON.")
    print("Production responses are gzip-compressed (~30% of raw size).")
    print()


if __name__ == "__main__":
    main()
