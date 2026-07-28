"""Sanitize and verify k6 load-test results before they are uploaded.

The k6 harness is written so credentials never reach disk (see
``backend/load_tests/dev_backend_baseline.js``: ``setup()`` returns no token).
This script is the defence-in-depth layer behind that guarantee:

* ``sanitize`` strips the ``setup_data`` block k6 writes into every
  ``--summary-export`` file and redacts per-request infrastructure trace
  identifiers.
* ``verify`` scans the whole results tree for credential-shaped content and
  exits non-zero if any is found, so the caller can skip the artifact upload.

Verification reports file names and match counts only - never the matched
value - because its output is itself captured in the run log.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

# Credential shapes that must never reach an artifact.
CREDENTIAL_PATTERNS: dict[str, re.Pattern[bytes]] = {
    "jwt": re.compile(rb"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    "bearer header": re.compile(rb"(?i)authorization\s*:\s*bearer\s+\S"),
    "bearer value": re.compile(rb'(?i)"bearer\s+[A-Za-z0-9_.\-]+"'),
    "setup_data block": re.compile(rb'"setup_data"'),
}

TRACE_HEADER_PATTERN = re.compile(
    r"(?im)^(x-railway-request-id|x-request-id|x-hikari-trace):.*$"
)


def sanitize(results: pathlib.Path) -> list[str]:
    """Remove credential-bearing and infrastructure-identifying content."""
    actions: list[str] = []

    for summary in sorted(results.glob("*-summary.json")):
        data = json.loads(summary.read_text(encoding="utf-8"))
        if data.pop("setup_data", None) is not None:
            summary.write_text(
                json.dumps(data, indent=2, sort_keys=True), encoding="utf-8"
            )
            actions.append(f"removed setup_data from {summary.name}")

    headers = results / "initial-health-headers.txt"
    if headers.exists():
        original = headers.read_text(encoding="utf-8")
        redacted = TRACE_HEADER_PATTERN.sub(
            lambda match: f"{match.group(1)}: [redacted]", original
        )
        if redacted != original:
            headers.write_text(redacted, encoding="utf-8")
            actions.append(f"redacted trace identifiers from {headers.name}")

    return actions


def find_credentials(results: pathlib.Path) -> list[tuple[str, str, int]]:
    """Return (file name, pattern label, match count) for every offending file."""
    offenders: list[tuple[str, str, int]] = []
    for path in sorted(results.rglob("*")):
        if not path.is_file():
            continue
        blob = path.read_bytes()
        for label, pattern in CREDENTIAL_PATTERNS.items():
            matches = pattern.findall(blob)
            if matches:
                offenders.append((path.name, label, len(matches)))
    return offenders


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=pathlib.Path)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="scan only; exit 1 if credential-shaped content is present",
    )
    args = parser.parse_args(argv)

    if not args.results.is_dir():
        print(f"::error::results directory not found: {args.results}")
        return 1

    if not args.verify:
        for action in sanitize(args.results):
            print(action)
        return 0

    offenders = find_credentials(args.results)
    if offenders:
        for name, label, count in offenders:
            print(f"::error::{name}: {count} {label} match(es)")
        print("::error::Credential-shaped content found; artifact upload will be skipped.")
        return 1

    print("Sanitization verified: no credential-shaped content in raw results.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
