#!/usr/bin/env python3
"""Fail closed on identity or credential material in active QA surfaces.

The active dev smoke and performance workflows must receive credentials only
through the GitHub ``dev`` Environment.  This check deliberately reports only
file names and bounded finding categories; it never prints matched content.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import NamedTuple

SYNTHETIC_IDENTITY_LABEL = "synthetic_dev_test_identity"

PROTECTED_PATHS = (
    ".github/workflows/staging-smoke-tests.yml",
    ".github/workflows/dev-backend-performance.yml",
    "backend/load_tests/dev_backend_baseline.js",
    "backend/scripts/sanitize_load_results.py",
    "frontend/scripts/run-staging-smoke.mjs",
    "frontend/tests/staging/helpers.js",
    "frontend/tests/staging/api.smoke.spec.js",
    "docs/qa/staging-smoke-tests.md",
    "docs/qa/dev-backend-performance-baseline-2026-07-26.md",
    "docs/qa/synthetic-dev-test-identity.md",
    "docs/evidence/dev-backend-performance-2026-07-26/incident-response-2026-07-26.md",
)

EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}"
)
JWT_PATTERN = re.compile(
    r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
)
GITHUB_TOKEN_PATTERN = re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}")
BEARER_VALUE_PATTERN = re.compile(
    r"(?i)\bbearer\s+([A-Za-z0-9][A-Za-z0-9_.-]{19,})"
)
SHELL_CREDENTIAL_ECHO_PATTERN = re.compile(
    r"(?im)^\s*(?:echo|printf)\b[^\n]*"
    r"\$\{?STAGING_TEST_(?:EMAIL|PASSWORD)\b"
)
JS_CREDENTIAL_ECHO_PATTERN = re.compile(
    r"(?is)console\.(?:log|error|warn)\s*\([^)]*"
    r"process\.env\.STAGING_TEST_(?:EMAIL|PASSWORD)"
)
PYTHON_CREDENTIAL_ECHO_PATTERN = re.compile(
    r"(?is)print\s*\([^)]*(?:os\.environ|os\.getenv)\s*\(?\s*"
    r"[\"']STAGING_TEST_(?:EMAIL|PASSWORD)"
)
ENV_DUMP_PATTERN = re.compile(r"(?im)^\s*(?:env|printenv)\s*$")
AUTOMATIC_WORKFLOW_TRIGGER_PATTERN = re.compile(
    r"(?m)^  (?:push|pull_request|schedule):"
)

ALLOWED_LITERAL_DOMAINS = frozenset(
    {"example.com", "example.net", "example.org"}
)


class Finding(NamedTuple):
    path: str
    category: str


def _mailbox_literal_is_allowed(value: str) -> bool:
    domain = value.rsplit("@", maxsplit=1)[-1].lower()
    return domain in ALLOWED_LITERAL_DOMAINS or domain.endswith(".invalid")


def scan_text(path: str, text: str) -> list[Finding]:
    """Return bounded findings without retaining matched secret material."""
    categories: set[str] = set()

    if any(
        not _mailbox_literal_is_allowed(match.group(0))
        for match in EMAIL_PATTERN.finditer(text)
    ):
        categories.add("non_placeholder_mailbox_literal")
    if JWT_PATTERN.search(text):
        categories.add("jwt_literal")
    if GITHUB_TOKEN_PATTERN.search(text):
        categories.add("github_token_literal")
    if any(
        not match.group(1).lower().startswith(("invalid.synthetic.", "invalid-"))
        for match in BEARER_VALUE_PATTERN.finditer(text)
    ):
        categories.add("bearer_credential_literal")
    if (
        SHELL_CREDENTIAL_ECHO_PATTERN.search(text)
        or JS_CREDENTIAL_ECHO_PATTERN.search(text)
        or PYTHON_CREDENTIAL_ECHO_PATTERN.search(text)
        or ENV_DUMP_PATTERN.search(text)
    ):
        categories.add("credential_echo_or_environment_dump")

    return [Finding(path=path, category=category) for category in sorted(categories)]


def _workflow_contract_findings(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for relative in (
        ".github/workflows/staging-smoke-tests.yml",
        ".github/workflows/dev-backend-performance.yml",
    ):
        path = root / relative
        if not path.is_file():
            findings.append(Finding(relative, "required_workflow_missing"))
            continue
        text = path.read_text(encoding="utf-8")
        required_fragments = (
            "workflow_dispatch:",
            "environment: dev",
            "secrets.STAGING_TEST_EMAIL",
            "secrets.STAGING_TEST_PASSWORD",
            SYNTHETIC_IDENTITY_LABEL,
        )
        if any(fragment not in text for fragment in required_fragments):
            findings.append(Finding(relative, "dev_identity_workflow_contract_missing"))
        if "prepare_load_test_data.py" in text:
            findings.append(Finding(relative, "legacy_token_minting_helper_referenced"))
        if AUTOMATIC_WORKFLOW_TRIGGER_PATTERN.search(text):
            findings.append(Finding(relative, "automatic_hosted_qa_trigger"))

    return findings


def scan_repository(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for relative in PROTECTED_PATHS:
        path = root / relative
        if not path.is_file():
            if relative == "docs/qa/synthetic-dev-test-identity.md":
                findings.append(Finding(relative, "required_runbook_missing"))
            continue
        findings.extend(scan_text(relative, path.read_text(encoding="utf-8")))
    findings.extend(_workflow_contract_findings(root))
    return sorted(set(findings), key=lambda finding: (finding.path, finding.category))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="repository root (defaults to the current checkout)",
    )
    args = parser.parse_args(argv)

    findings = scan_repository(args.root.resolve())
    if findings:
        for finding in findings:
            print(f"::error::{finding.path}: {finding.category}")
        print(
            "::error::QA identity hygiene check failed; matched values were suppressed."
        )
        return 1

    print(
        "QA identity hygiene verified: protected paths contain no identity or "
        "credential material."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
