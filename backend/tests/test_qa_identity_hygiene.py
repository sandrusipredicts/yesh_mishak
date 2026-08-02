"""Regression coverage for the synthetic dev QA identity boundary."""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER_PATH = REPO_ROOT / "backend" / "scripts" / "check_qa_identity_hygiene.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_qa_identity_hygiene", CHECKER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_active_repository_qa_surfaces_are_clean() -> None:
    checker = _load_checker()

    assert checker.scan_repository(REPO_ROOT) == []


def test_reserved_example_mailboxes_and_bounded_label_are_allowed() -> None:
    checker = _load_checker()
    text = "reserved@example.invalid\nidentity=synthetic_dev_test_identity\n"

    assert checker.scan_text("fixture.txt", text) == []


def test_non_placeholder_mailbox_token_and_echo_are_rejected() -> None:
    checker = _load_checker()
    mailbox = "qa" + chr(64) + "project-mail.test"
    jwt_value = "eyJ" + "a" * 12 + "." + "b" * 12 + "." + "c" * 12
    github_token = "gh" + "p_" + "d" * 24
    text = (
        f"mailbox={mailbox}\n"
        f"token={jwt_value}\n"
        f"github={github_token}\n"
        'echo "${STAGING_TEST_PASSWORD}"\n'
    )

    categories = {finding.category for finding in checker.scan_text("unsafe.txt", text)}

    assert categories == {
        "credential_echo_or_environment_dump",
        "github_token_literal",
        "jwt_literal",
        "non_placeholder_mailbox_literal",
    }


def test_hosted_qa_workflows_cannot_gain_automatic_triggers(tmp_path: Path) -> None:
    checker = _load_checker()
    workflow_dir = tmp_path / ".github" / "workflows"
    workflow_dir.mkdir(parents=True)
    workflow = """on:
  workflow_dispatch:
  schedule:
    - cron: '0 0 * * *'
environment: dev
secrets.STAGING_TEST_EMAIL
secrets.STAGING_TEST_PASSWORD
synthetic_dev_test_identity
"""
    for name in ("staging-smoke-tests.yml", "dev-backend-performance.yml"):
        (workflow_dir / name).write_text(workflow, encoding="utf-8")

    findings = checker._workflow_contract_findings(tmp_path)

    assert {finding.category for finding in findings} == {
        "automatic_hosted_qa_trigger"
    }


def test_checker_output_never_echoes_matched_values(tmp_path: Path, capsys) -> None:
    checker = _load_checker()
    mailbox = "qa" + chr(64) + "project-mail.test"
    target = tmp_path / ".github" / "workflows"
    target.mkdir(parents=True)
    (target / "staging-smoke-tests.yml").write_text(mailbox, encoding="utf-8")

    assert checker.main([str(tmp_path)]) == 1

    output = capsys.readouterr().out
    assert mailbox not in output
    assert "matched values were suppressed" in output
