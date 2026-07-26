#!/usr/bin/env python3
"""Aggregate k6 dev-backend baseline artifacts into JSON, CSV, and Markdown."""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

PRIMARY_SCENARIOS = {"public-read", "authenticated-read", "controlled-write"}
SUMMARY_RE = re.compile(r"^(?P<scenario>.+?)(?:-run-(?P<run>\d+))?-summary$")


def _metric_value(metrics: dict[str, Any], name: str, key: str, default: float = 0.0) -> float:
    metric = metrics.get(name, {})
    values = metric.get("values") or metric
    if key == "rate" and key not in values and "value" in values:
        key = "value"
    value = values.get(key, default)
    return float(value) if value is not None else default


def _load_statuses(points_path: Path) -> dict[str, Counter[str]]:
    statuses: dict[str, Counter[str]] = defaultdict(Counter)
    if not points_path.exists():
        return statuses

    with points_path.open(encoding="utf-8") as stream:
        for line in stream:
            try:
                point = json.loads(line)
            except json.JSONDecodeError:
                continue
            if point.get("type") != "Point" or point.get("metric") != "http_status_count":
                continue
            data = point.get("data") or {}
            tags = data.get("tags") or {}
            endpoint = str(tags.get("endpoint") or "unknown")
            status = str(tags.get("status") or "unknown")
            statuses[endpoint][status] += int(data.get("value") or 0)
    return statuses


def _parse_summary(path: Path) -> dict[str, Any]:
    match = SUMMARY_RE.match(path.stem)
    if not match:
        raise ValueError(f"Unrecognized summary filename: {path.name}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    metrics = payload.get("metrics") or {}
    scenario = match.group("scenario")
    run_number = int(match.group("run") or 1)
    statuses = _load_statuses(path.with_name(path.name.replace("-summary.json", "-points.json")))
    exit_path = path.with_name(path.name.replace("-summary.json", "-exit-code.txt"))
    exit_code = int(exit_path.read_text(encoding="utf-8").strip()) if exit_path.exists() else None

    endpoint_rows: list[dict[str, Any]] = []
    request_count = int(_metric_value(metrics, "http_reqs", "count"))
    scenario_throughput_rps = round(_metric_value(metrics, "http_reqs", "rate"), 4)
    for metric_name, metric in sorted(metrics.items()):
        if not metric_name.startswith("latency_"):
            continue
        values = metric.get("values") or metric
        endpoint = metric_name.removeprefix("latency_")
        distribution = dict(sorted(statuses.get(endpoint, {}).items()))
        endpoint_requests = sum(distribution.values())
        endpoint_5xx = sum(
            count
            for status, count in distribution.items()
            if status.isdigit() and 500 <= int(status) <= 599
        )
        endpoint_rows.append(
            {
                "endpoint": endpoint,
                "requests": endpoint_requests,
                "p50_ms": round(float(values.get("p(50)", 0.0)), 2),
                "p95_ms": round(float(values.get("p(95)", 0.0)), 2),
                "p99_ms": round(float(values.get("p(99)", 0.0)), 2),
                "avg_ms": round(float(values.get("avg", 0.0)), 2),
                "max_ms": round(float(values.get("max", 0.0)), 2),
                "throughput_rps": round(
                    scenario_throughput_rps * endpoint_requests / request_count, 4
                )
                if request_count
                else 0.0,
                "unexpected_status_count": sum(
                    count for status, count in distribution.items() if status != "200"
                )
                if scenario in PRIMARY_SCENARIOS
                else 0,
                "unexpected_5xx_count": endpoint_5xx,
                "status_distribution": distribution,
            }
        )

    return {
        "scenario": scenario,
        "run": run_number,
        "exit_code": exit_code,
        "throughput_rps": scenario_throughput_rps,
        "request_count": request_count,
        "error_rate": round(_metric_value(metrics, "unexpected_error_rate", "rate"), 6),
        "http_failed_rate": round(_metric_value(metrics, "http_req_failed", "rate"), 6),
        "timeout_count": int(_metric_value(metrics, "timeout_count", "count")),
        "unexpected_5xx_count": int(_metric_value(metrics, "unexpected_5xx_count", "count")),
        "dropped_iterations": int(_metric_value(metrics, "dropped_iterations", "count")),
        "endpoints": endpoint_rows,
        "summary_file": path.name,
    }


def _aggregate_primary(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, Any]]]] = defaultdict(list)
    for run in runs:
        if run["scenario"] not in PRIMARY_SCENARIOS:
            continue
        for endpoint in run["endpoints"]:
            grouped[(run["scenario"], endpoint["endpoint"])].append((run, endpoint))

    aggregates = []
    for (scenario, endpoint), values in sorted(grouped.items()):
        status_total: Counter[str] = Counter()
        for _, endpoint_row in values:
            status_total.update(endpoint_row["status_distribution"])
        aggregates.append(
            {
                "scenario": scenario,
                "endpoint": endpoint,
                "runs": len(values),
                "median_p50_ms": round(statistics.median(v[1]["p50_ms"] for v in values), 2),
                "median_p95_ms": round(statistics.median(v[1]["p95_ms"] for v in values), 2),
                "median_p99_ms": round(statistics.median(v[1]["p99_ms"] for v in values), 2),
                "p95_range_ms": [
                    round(min(v[1]["p95_ms"] for v in values), 2),
                    round(max(v[1]["p95_ms"] for v in values), 2),
                ],
                "mean_endpoint_throughput_rps": round(
                    statistics.mean(v[1]["throughput_rps"] for v in values), 4
                ),
                "total_requests": sum(v[1]["requests"] for v in values),
                "status_distribution": dict(sorted(status_total.items())),
                "error_rate": round(
                    sum(v[1]["unexpected_status_count"] for v in values)
                    / max(1, sum(v[1]["requests"] for v in values)),
                    6,
                ),
                "total_unexpected_5xx": sum(
                    v[1]["unexpected_5xx_count"] for v in values
                ),
            }
        )
    return aggregates


def _read_metadata(results_dir: Path) -> dict[str, str]:
    metadata: dict[str, str] = {}
    path = results_dir / "metadata.txt"
    if not path.exists():
        return metadata
    for line in path.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            metadata[key] = value
    return metadata


def _write_csv(path: Path, runs: list[dict[str, Any]]) -> None:
    fields = [
        "scenario",
        "run",
        "endpoint",
        "requests",
        "p50_ms",
        "p95_ms",
        "p99_ms",
        "avg_ms",
        "max_ms",
        "endpoint_throughput_rps",
        "scenario_throughput_rps",
        "error_rate",
        "timeout_count",
        "unexpected_5xx_count",
        "status_distribution",
        "exit_code",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for run in runs:
            for endpoint in run["endpoints"]:
                writer.writerow(
                    {
                        "scenario": run["scenario"],
                        "run": run["run"],
                        "endpoint": endpoint["endpoint"],
                        "requests": endpoint["requests"],
                        "p50_ms": endpoint["p50_ms"],
                        "p95_ms": endpoint["p95_ms"],
                        "p99_ms": endpoint["p99_ms"],
                        "avg_ms": endpoint["avg_ms"],
                        "max_ms": endpoint["max_ms"],
                        "endpoint_throughput_rps": endpoint["throughput_rps"],
                        "scenario_throughput_rps": run["throughput_rps"],
                        "error_rate": run["error_rate"],
                        "timeout_count": run["timeout_count"],
                        "unexpected_5xx_count": run["unexpected_5xx_count"],
                        "status_distribution": json.dumps(
                            endpoint["status_distribution"], sort_keys=True
                        ),
                        "exit_code": run["exit_code"],
                    }
                )


def _write_markdown(
    path: Path,
    metadata: dict[str, str],
    runs: list[dict[str, Any]],
    aggregates: list[dict[str, Any]],
) -> None:
    lines = [
        "# Dev Backend Performance Results",
        "",
        f"- Tested commit: `{metadata.get('tested_commit_sha', 'unknown')}`",
        f"- Target host: `{metadata.get('target_host', 'unknown')}`",
        f"- GitHub run: `{metadata.get('github_run_id', 'unknown')}`",
        f"- Railway deployment ID: `{metadata.get('railway_deployment_id', 'unknown')}`",
        "",
        "## Three-run primary-scenario aggregate",
        "",
        "| Scenario | Endpoint | Runs | p50 median | p95 median (range) | p99 median | Endpoint req/s | Requests | Error rate | Statuses | 5xx |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for row in aggregates:
        low, high = row["p95_range_ms"]
        lines.append(
            "| {scenario} | {endpoint} | {runs} | {p50:.2f} ms | "
            "{p95:.2f} ms ({low:.2f}–{high:.2f}) | {p99:.2f} ms | "
            "{rps:.4f} | {requests} | {error_rate:.2%} | `{statuses}` | {errors} |".format(
                scenario=row["scenario"],
                endpoint=row["endpoint"],
                runs=row["runs"],
                p50=row["median_p50_ms"],
                p95=row["median_p95_ms"],
                low=low,
                high=high,
                p99=row["median_p99_ms"],
                rps=row["mean_endpoint_throughput_rps"],
                requests=row["total_requests"],
                error_rate=row["error_rate"],
                statuses=json.dumps(row["status_distribution"], sort_keys=True),
                errors=row["total_unexpected_5xx"],
            )
        )

    lines.extend(
        [
            "",
            "## Run-level reliability",
            "",
            "| Scenario | Run | Requests | Req/s | Error rate | HTTP-failed rate | Timeouts | 5xx | Dropped iterations | Exit |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for run in runs:
        lines.append(
            "| {scenario} | {run} | {requests} | {rps:.4f} | {errors:.2%} | "
            "{failed:.2%} | {timeouts} | {server_errors} | {dropped} | {exit_code} |".format(
                scenario=run["scenario"],
                run=run["run"],
                requests=run["request_count"],
                rps=run["throughput_rps"],
                errors=run["error_rate"],
                failed=run["http_failed_rate"],
                timeouts=run["timeout_count"],
                server_errors=run["unexpected_5xx_count"],
                dropped=run["dropped_iterations"],
                exit_code=run["exit_code"],
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results_dir", type=Path)
    args = parser.parse_args()

    results_dir = args.results_dir.resolve()
    summaries = sorted(results_dir.glob("*-summary.json"))
    if not summaries:
        raise SystemExit(f"No k6 summary files found in {results_dir}")

    runs = [_parse_summary(path) for path in summaries]
    aggregates = _aggregate_primary(runs)
    metadata = _read_metadata(results_dir)
    output = {
        "metadata": metadata,
        "runs": runs,
        "primary_aggregates": aggregates,
    }

    (results_dir / "analysis.json").write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write_csv(results_dir / "analysis.csv", runs)
    _write_markdown(results_dir / "analysis.md", metadata, runs, aggregates)
    print(f"Analyzed {len(runs)} k6 summaries in {results_dir}")


if __name__ == "__main__":
    main()
