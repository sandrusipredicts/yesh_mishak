"""Fail closed unless every required PostgreSQL migration module executed."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
import sys
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class RequiredReport:
    path: Path
    module_name: str


class PostgreSQLJUnitVerificationError(RuntimeError):
    pass


def verify_report(requirement: RequiredReport) -> int:
    if not requirement.path.is_file():
        raise PostgreSQLJUnitVerificationError(
            f"PostgreSQL pytest report is missing: {requirement.path}"
        )
    try:
        root = ET.parse(requirement.path).getroot()
    except (ET.ParseError, OSError) as exc:
        raise PostgreSQLJUnitVerificationError(
            f"PostgreSQL pytest report is unreadable: {requirement.path}"
        ) from exc

    test_cases = root.findall(".//testcase")
    if not test_cases:
        raise PostgreSQLJUnitVerificationError(
            f"zero PostgreSQL tests executed in {requirement.path}"
        )
    if root.findall(".//failure") or root.findall(".//error"):
        raise PostgreSQLJUnitVerificationError(
            f"PostgreSQL failures or errors are present in {requirement.path}"
        )
    if root.findall(".//skipped"):
        raise PostgreSQLJUnitVerificationError(
            f"skipped PostgreSQL tests are present in {requirement.path}"
        )

    executed_module_cases = [
        case
        for case in test_cases
        if requirement.module_name
        in case.attrib.get("classname", "").split(".")
    ]
    if not executed_module_cases:
        raise PostgreSQLJUnitVerificationError(
            f"required PostgreSQL module did not execute: {requirement.module_name}"
        )
    return len(executed_module_cases)


def verify_required_reports(requirements: Iterable[RequiredReport]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for requirement in requirements:
        counts[requirement.module_name] = verify_report(requirement)
    return counts


DEFAULT_REQUIREMENTS = (
    RequiredReport(
        Path("analytics-postgres-results.xml"),
        "test_analytics_events_migration_postgres",
    ),
    RequiredReport(
        Path("authentication-audit-postgres-results.xml"),
        "test_authentication_audit_events_migration_postgres",
    ),
    RequiredReport(
        Path("authentication-audit-retention-postgres-results.xml"),
        "test_authentication_audit_retention_migration_postgres",
    ),
    RequiredReport(
        Path("security-attribution-postgres-results.xml"),
        "test_security_request_attribution_migration_postgres",
    ),
)


def main() -> int:
    try:
        counts = verify_required_reports(DEFAULT_REQUIREMENTS)
    except PostgreSQLJUnitVerificationError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    evidence = ", ".join(
        f"{module}={count} executed"
        for module, count in counts.items()
    )
    print(f"PostgreSQL evidence: {evidence}; 0 failed, 0 skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
