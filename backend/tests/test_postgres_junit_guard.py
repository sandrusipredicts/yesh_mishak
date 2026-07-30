from __future__ import annotations

from pathlib import Path

import pytest

from scripts.verify_postgres_junit_reports import (
    PostgreSQLJUnitVerificationError,
    RequiredReport,
    verify_required_reports,
)


ANALYTICS_MODULE = "test_analytics_events_migration_postgres"
AUTHENTICATION_AUDIT_MODULE = "test_authentication_audit_events_migration_postgres"
AUTHENTICATION_AUDIT_RETENTION_MODULE = (
    "test_authentication_audit_retention_migration_postgres"
)
SECURITY_ATTRIBUTION_MODULE = (
    "test_security_request_attribution_migration_postgres"
)


def _write_report(
    path: Path,
    *,
    module_name: str,
    skipped: bool = False,
    failed: bool = False,
    errored: bool = False,
) -> None:
    result = (
        "<skipped/>"
        if skipped
        else "<failure/>"
        if failed
        else "<error/>"
        if errored
        else ""
    )
    path.write_text(
        (
            '<testsuites tests="1">'
            '<testsuite tests="1">'
            f'<testcase classname="tests.{module_name}" name="test_executed">'
            f"{result}"
            "</testcase>"
            "</testsuite>"
            "</testsuites>"
        ),
        encoding="utf-8",
    )


def _requirements(
    analytics_report: Path,
    authentication_audit_report: Path,
    authentication_audit_retention_report: Path,
    security_attribution_report: Path,
) -> tuple[
    RequiredReport,
    RequiredReport,
    RequiredReport,
    RequiredReport,
]:
    return (
        RequiredReport(analytics_report, ANALYTICS_MODULE),
        RequiredReport(authentication_audit_report, AUTHENTICATION_AUDIT_MODULE),
        RequiredReport(
            authentication_audit_retention_report,
            AUTHENTICATION_AUDIT_RETENTION_MODULE,
        ),
        RequiredReport(
            security_attribution_report,
            SECURITY_ATTRIBUTION_MODULE,
        ),
    )


def test_guard_rejects_reports_containing_only_analytics(tmp_path: Path) -> None:
    analytics = tmp_path / "analytics.xml"
    mislabeled_authentication = tmp_path / "authentication.xml"
    retention = tmp_path / "retention.xml"
    attribution = tmp_path / "attribution.xml"
    _write_report(analytics, module_name=ANALYTICS_MODULE)
    _write_report(mislabeled_authentication, module_name=ANALYTICS_MODULE)
    _write_report(
        retention,
        module_name=AUTHENTICATION_AUDIT_RETENTION_MODULE,
    )
    _write_report(attribution, module_name=SECURITY_ATTRIBUTION_MODULE)

    with pytest.raises(
        PostgreSQLJUnitVerificationError,
        match="authentication_audit_events",
    ):
        verify_required_reports(
            _requirements(
                analytics,
                mislabeled_authentication,
                retention,
                attribution,
            )
        )


def test_guard_rejects_reports_containing_only_authentication_audit(
    tmp_path: Path,
) -> None:
    mislabeled_analytics = tmp_path / "analytics.xml"
    authentication = tmp_path / "authentication.xml"
    retention = tmp_path / "retention.xml"
    attribution = tmp_path / "attribution.xml"
    _write_report(mislabeled_analytics, module_name=AUTHENTICATION_AUDIT_MODULE)
    _write_report(authentication, module_name=AUTHENTICATION_AUDIT_MODULE)
    _write_report(
        retention,
        module_name=AUTHENTICATION_AUDIT_RETENTION_MODULE,
    )
    _write_report(attribution, module_name=SECURITY_ATTRIBUTION_MODULE)

    with pytest.raises(
        PostgreSQLJUnitVerificationError,
        match="analytics_events",
    ):
        verify_required_reports(
            _requirements(
                mislabeled_analytics,
                authentication,
                retention,
                attribution,
            )
        )


def test_guard_rejects_missing_retention_module(tmp_path: Path) -> None:
    analytics = tmp_path / "analytics.xml"
    authentication = tmp_path / "authentication.xml"
    mislabeled_retention = tmp_path / "retention.xml"
    attribution = tmp_path / "attribution.xml"
    _write_report(analytics, module_name=ANALYTICS_MODULE)
    _write_report(authentication, module_name=AUTHENTICATION_AUDIT_MODULE)
    _write_report(
        mislabeled_retention,
        module_name=AUTHENTICATION_AUDIT_MODULE,
    )
    _write_report(attribution, module_name=SECURITY_ATTRIBUTION_MODULE)

    with pytest.raises(
        PostgreSQLJUnitVerificationError,
        match="authentication_audit_retention",
    ):
        verify_required_reports(
            _requirements(
                analytics,
                authentication,
                mislabeled_retention,
                attribution,
            )
        )


def test_guard_rejects_missing_security_attribution_module(
    tmp_path: Path,
) -> None:
    analytics = tmp_path / "analytics.xml"
    authentication = tmp_path / "authentication.xml"
    retention = tmp_path / "retention.xml"
    mislabeled_attribution = tmp_path / "attribution.xml"
    _write_report(analytics, module_name=ANALYTICS_MODULE)
    _write_report(authentication, module_name=AUTHENTICATION_AUDIT_MODULE)
    _write_report(
        retention,
        module_name=AUTHENTICATION_AUDIT_RETENTION_MODULE,
    )
    _write_report(
        mislabeled_attribution,
        module_name=AUTHENTICATION_AUDIT_MODULE,
    )

    with pytest.raises(
        PostgreSQLJUnitVerificationError,
        match="security_request_attribution",
    ):
        verify_required_reports(
            _requirements(
                analytics,
                authentication,
                retention,
                mislabeled_attribution,
            )
        )


def test_guard_accepts_all_executed_non_skipped_modules(tmp_path: Path) -> None:
    analytics = tmp_path / "analytics.xml"
    authentication = tmp_path / "authentication.xml"
    retention = tmp_path / "retention.xml"
    attribution = tmp_path / "attribution.xml"
    _write_report(analytics, module_name=ANALYTICS_MODULE)
    _write_report(authentication, module_name=AUTHENTICATION_AUDIT_MODULE)
    _write_report(
        retention,
        module_name=AUTHENTICATION_AUDIT_RETENTION_MODULE,
    )
    _write_report(attribution, module_name=SECURITY_ATTRIBUTION_MODULE)

    assert verify_required_reports(
        _requirements(analytics, authentication, retention, attribution)
    ) == {
        ANALYTICS_MODULE: 1,
        AUTHENTICATION_AUDIT_MODULE: 1,
        AUTHENTICATION_AUDIT_RETENTION_MODULE: 1,
        SECURITY_ATTRIBUTION_MODULE: 1,
    }


@pytest.mark.parametrize(
    "skipped_module",
    [
        ANALYTICS_MODULE,
        AUTHENTICATION_AUDIT_MODULE,
        AUTHENTICATION_AUDIT_RETENTION_MODULE,
        SECURITY_ATTRIBUTION_MODULE,
    ],
)
def test_guard_rejects_any_skipped_postgresql_test(
    tmp_path: Path,
    skipped_module: str,
) -> None:
    analytics = tmp_path / "analytics.xml"
    authentication = tmp_path / "authentication.xml"
    retention = tmp_path / "retention.xml"
    attribution = tmp_path / "attribution.xml"
    _write_report(
        analytics,
        module_name=ANALYTICS_MODULE,
        skipped=skipped_module == ANALYTICS_MODULE,
    )
    _write_report(
        authentication,
        module_name=AUTHENTICATION_AUDIT_MODULE,
        skipped=skipped_module == AUTHENTICATION_AUDIT_MODULE,
    )
    _write_report(
        retention,
        module_name=AUTHENTICATION_AUDIT_RETENTION_MODULE,
        skipped=skipped_module == AUTHENTICATION_AUDIT_RETENTION_MODULE,
    )
    _write_report(
        attribution,
        module_name=SECURITY_ATTRIBUTION_MODULE,
        skipped=skipped_module == SECURITY_ATTRIBUTION_MODULE,
    )

    with pytest.raises(
        PostgreSQLJUnitVerificationError,
        match="skipped PostgreSQL tests",
    ):
        verify_required_reports(
            _requirements(
                analytics,
                authentication,
                retention,
                attribution,
            )
        )


@pytest.mark.parametrize("result_kind", ["failure", "error"])
def test_guard_rejects_failures_and_errors(
    tmp_path: Path,
    result_kind: str,
) -> None:
    analytics = tmp_path / "analytics.xml"
    authentication = tmp_path / "authentication.xml"
    retention = tmp_path / "retention.xml"
    attribution = tmp_path / "attribution.xml"
    _write_report(
        analytics,
        module_name=ANALYTICS_MODULE,
        failed=result_kind == "failure",
        errored=result_kind == "error",
    )
    _write_report(authentication, module_name=AUTHENTICATION_AUDIT_MODULE)
    _write_report(
        retention,
        module_name=AUTHENTICATION_AUDIT_RETENTION_MODULE,
    )
    _write_report(attribution, module_name=SECURITY_ATTRIBUTION_MODULE)

    with pytest.raises(
        PostgreSQLJUnitVerificationError,
        match="failures or errors",
    ):
        verify_required_reports(
            _requirements(
                analytics,
                authentication,
                retention,
                attribution,
            )
        )
