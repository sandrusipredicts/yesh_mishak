"""ISSUE-073: Backend endpoint performance benchmark.

Measures response times for key API endpoints using the FastAPI TestClient
with FakeSupabase. No real database or external services required.

Usage:
    cd backend
    .venv\\Scripts\\python.exe -m scripts.benchmark_endpoints
    .venv\\Scripts\\python.exe -m scripts.benchmark_endpoints --runs 50
    .venv\\Scripts\\python.exe -m scripts.benchmark_endpoints --json
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

# Initialize mock data structure early
NOW = datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)

ADMIN_USER = {
    "id": "00000000-0000-0000-0000-000000000001",
    "email": "admin@bench.test",
    "name": "Bench Admin",
    "username": "benchadmin",
    "phone_number": None,
    "role": "admin",
    "status": "active",
    "google_sub": None,
    "password_hash": "", # populated dynamically
    "last_login": NOW.isoformat(),
}

REGULAR_USER = {
    "id": "00000000-0000-0000-0000-000000000002",
    "email": "user@bench.test",
    "name": "Bench User",
    "username": "benchuser",
    "phone_number": None,
    "role": "user",
    "status": "active",
    "google_sub": None,
    "password_hash": "", # populated dynamically
    "last_login": NOW.isoformat(),
}

FIELD_TEMPLATE = {
    "name": "Bench Field",
    "lat": 31.0,
    "lng": 34.9,
    "city": "bench-city",
    "sport_type": "both",
    "surface_type": "grass",
    "lighting": True,
    "verified": True,
    "approval_status": "approved",
    "status": "open",
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

NOTIFICATION_TEMPLATE = {
    "user_id": None,
    "type": "game_created",
    "title": "New game",
    "body": "A new game was created",
    "game_id": None,
    "field_id": None,
    "read_at": None,
    "created_at": NOW.isoformat(),
}


def _make_fields(count: int) -> list[dict[str, Any]]:
    fields = []
    for i in range(count):
        f = deepcopy(FIELD_TEMPLATE)
        f["id"] = f"field-{i:04d}"
        f["name"] = f"Field {i}"
        fields.append(f)
    return fields


def _make_games(fields: list[dict], creator_id: str, count: int) -> list[dict[str, Any]]:
    games = []
    for i in range(count):
        g = deepcopy(GAME_TEMPLATE)
        g["id"] = f"game-{i:04d}"
        g["field_id"] = fields[i % len(fields)]["id"]
        g["creator_id"] = creator_id
        g["created_by"] = creator_id
        games.append(g)
    return games


def _make_notifications(user_id: str, games: list[dict], count: int) -> list[dict[str, Any]]:
    notifs = []
    for i in range(count):
        n = deepcopy(NOTIFICATION_TEMPLATE)
        n["id"] = f"notif-{i:04d}"
        n["user_id"] = user_id
        n["game_id"] = games[i % len(games)]["id"] if games else None
        n["field_id"] = games[i % len(games)]["field_id"] if games else None
        notifs.append(n)
    return notifs


class FakeResponse:
    def __init__(self, data: list[dict[str, Any]]):
        self.data = data
        self.count = len(data)


class FakeBenchQuery:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows
        self.filters: list[tuple[str, Any]] = []
        self.in_filters: list[tuple[str, list]] = []
        self.selected_columns: str | None = None
        self.insert_payload: dict | list | None = None
        self.update_payload: dict | None = None
        self._limit: int | None = None
        self._range: tuple[int, int] | None = None
        self._order_col: str | None = None
        self._order_desc: bool = False

    def select(self, columns: str, **kwargs: Any) -> "FakeBenchQuery":
        self.selected_columns = columns
        return self

    def eq(self, col: str, val: Any) -> "FakeBenchQuery":
        self.filters.append((col, val))
        return self

    def neq(self, col: str, val: Any) -> "FakeBenchQuery":
        return self

    def in_(self, col: str, vals: list) -> "FakeBenchQuery":
        self.in_filters.append((col, vals))
        return self

    def gte(self, col: str, val: Any) -> "FakeBenchQuery":
        self.filters.append(("__gte", (col, val)))
        return self

    def lte(self, col: str, val: Any) -> "FakeBenchQuery":
        self.filters.append(("__lte", (col, val)))
        return self

    def is_(self, col: str, val: str) -> "FakeBenchQuery":
        self.filters.append(("__is_null", (col, val)))
        return self

    def limit(self, n: int) -> "FakeBenchQuery":
        self._limit = n
        return self

    def range(self, start: int, end: int) -> "FakeBenchQuery":
        self._range = (start, end)
        return self

    def order(self, col: str, desc: bool = False) -> "FakeBenchQuery":
        self._order_col = col
        self._order_desc = desc
        return self

    def insert(self, payload: dict | list) -> "FakeBenchQuery":
        self.insert_payload = payload
        return self

    def update(self, payload: dict) -> "FakeBenchQuery":
        self.update_payload = payload
        return self

    def execute(self) -> FakeResponse:
        if self.insert_payload is not None:
            if isinstance(self.insert_payload, list):
                self.rows.extend(self.insert_payload)
                return FakeResponse(data=self.insert_payload)
            row = {"id": f"new-{id(self)}", **self.insert_payload}
            self.rows.append(row)
            return FakeResponse(data=[row])

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


class FakeBenchSupabase:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]):
        self.tables = tables

    def table(self, name: str) -> FakeBenchQuery:
        if name not in self.tables:
            self.tables[name] = []
        return FakeBenchQuery(self.tables[name])

    def rpc(self, name: str, params: dict) -> Any:
        class FakeRpc:
            def execute(self) -> Any:
                return FakeResponse(data=[{"game": {}}])
        return FakeRpc()


def _build_test_data(field_count: int = 50, game_count: int = 20, notif_count: int = 30):
    fields = _make_fields(field_count)
    games = _make_games(fields, REGULAR_USER["id"], game_count)
    notifications = _make_notifications(REGULAR_USER["id"], games, notif_count)
    participants = []
    for g in games:
        participants.append({
            "id": f"part-{g['id']}",
            "game_id": g["id"],
            "user_id": REGULAR_USER["id"],
            "joined_at": NOW.isoformat(),
        })

    return {
        "users": [deepcopy(ADMIN_USER), deepcopy(REGULAR_USER)],
        "fields": fields,
        "games": games,
        "game_players": participants,
        "notifications": notifications,
        "field_reports": [],
        "user_moderation_audit": [],
        "push_tokens": [],
        "notification_preferences": [],
    }


# Build fake database
tables = _build_test_data(field_count=50, game_count=20)
fake_supabase = FakeBenchSupabase(tables)

# MONKEYPATCH get_supabase_client BEFORE importing app modules
import app.db.supabase
app.db.supabase.get_supabase_client = lambda: fake_supabase
app.db.supabase.get_supabase_service_role_client = lambda: fake_supabase

# Now import components from the app safely
from fastapi.testclient import TestClient
from app.auth.jwt import create_access_token
from app.auth.passwords import hash_password
from app.core.config import get_settings
from app.main import app

def _get_token(user: dict) -> str:
    return create_access_token(
        subject=user["id"],
        email=user["email"],
    )


def _run_benchmark(
    client: TestClient,
    method: str,
    url: str,
    headers: dict | None = None,
    json_body: dict | None = None,
    runs: int = 20,
    reset_fn: Callable[[], None] | None = None,
) -> dict:
    times = []
    status_codes = []

    for _ in range(runs):
        if reset_fn:
            reset_fn()
            
        start = time.perf_counter()
        if method == "GET":
            resp = client.get(url, headers=headers)
        elif method == "POST":
            resp = client.post(url, headers=headers, json=json_body)
        else:
            resp = client.get(url, headers=headers)
        elapsed_ms = (time.perf_counter() - start) * 1000
        times.append(elapsed_ms)
        status_codes.append(resp.status_code)

    times_sorted = sorted(times)
    p95_idx = max(0, int(len(times_sorted) * 0.95) - 1)

    return {
        "runs": runs,
        "status_codes": list(set(status_codes)),
        "min_ms": round(min(times), 2),
        "max_ms": round(max(times), 2),
        "avg_ms": round(statistics.mean(times), 2),
        "median_ms": round(statistics.median(times), 2),
        "p95_ms": round(times_sorted[p95_idx], 2),
        "stdev_ms": round(statistics.stdev(times), 2) if len(times) > 1 else 0,
    }


def main():
    parser = argparse.ArgumentParser(description="ISSUE-073 backend endpoint benchmark")
    parser.add_argument("--runs", type=int, default=20, help="Number of runs per endpoint")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of table")
    parser.add_argument("--fields", type=int, default=50, help="Number of test fields")
    parser.add_argument("--games", type=int, default=20, help="Number of test games")
    args = parser.parse_args()

    # Pre-hash password so verification is realistic
    hashed = hash_password("password")
    ADMIN_USER["password_hash"] = hashed
    REGULAR_USER["password_hash"] = hashed
    
    # Reload test data with hashed passwords
    global tables, fake_supabase
    tables = _build_test_data(field_count=args.fields, game_count=args.games)
    fake_supabase.tables = tables

    user_token = _get_token(REGULAR_USER)
    auth_headers = {"Authorization": f"Bearer {user_token}"}

    # Reset function to revert Supabase state back to start before mutating endpoints
    original_tables = deepcopy(tables)
    def reset_supabase():
        fake_supabase.tables.clear()
        for k, v in original_tables.items():
            fake_supabase.tables[k] = deepcopy(v)

    # Patch get_now for consistency
    from unittest.mock import patch
    now_patch = patch("app.routers.games.get_now", return_value=NOW)
    now_patch2 = patch("app.routers.game_lifecycle.get_now", return_value=NOW)

    benchmarks = [
        # Required by ISSUE-073
        ("GET /fields", "GET", "/fields", None, None, None),
        ("GET /fields (bounded)", "GET", "/fields?north=32.0&south=30.5&east=35.5&west=34.0", None, None, None),
        ("GET /games/active", "GET", "/games/active", None, None, None),
        ("POST /auth/login", "POST", "/auth/login", None, {"username": "benchuser", "password": "password"}, None),
        ("POST /games/", "POST", "/games/", auth_headers, {
            "field_id": "field-0020",
            "sport_type": "football",
            "players_present": 2,
            "max_players": 10,
            "age_note": "friendly game",
            "min_age": 18,
            "max_age": 40,
            "scheduled_at": None
        }, reset_supabase),
    ]

    client = TestClient(app)
    results = {}

    with now_patch, now_patch2:
        for name, method, url, headers, body, reset_fn in benchmarks:
            result = _run_benchmark(
                client, method, url, headers=headers, json_body=body, runs=args.runs, reset_fn=reset_fn
            )
            results[name] = result

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print(f"\nBackend Endpoint Benchmark — {args.runs} runs each")
        print(f"Test data: {args.fields} fields, {args.games} games")
        print(f"Environment: FakeSupabase (in-memory), FastAPI TestClient (no network)")
        print()
        print(f"{'Endpoint':<36} {'Min':>8} {'Avg':>8} {'Med':>8} {'P95':>8} {'Max':>8} {'StDev':>8}  Status")
        print("-" * 110)
        for name, r in results.items():
            codes = ",".join(str(c) for c in r["status_codes"])
            print(
                f"{name:<36} {r['min_ms']:>7.1f} {r['avg_ms']:>7.1f} "
                f"{r['median_ms']:>7.1f} {r['p95_ms']:>7.1f} {r['max_ms']:>7.1f} "
                f"{r['stdev_ms']:>7.1f}  {codes}"
            )
        print()
        print("All times in milliseconds.")


if __name__ == "__main__":
    main()
