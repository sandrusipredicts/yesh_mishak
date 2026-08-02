"""Regression coverage for credential hygiene in the k6 performance harness.

Context: a baseline run once uploaded an artifact containing live access
tokens because the k6 script returned the token from ``setup()`` and k6
serializes that value into every ``--summary-export`` file as ``setup_data``.

These tests lock in both layers of the fix:

1. the harness itself never returns a credential from ``setup()``; and
2. ``backend/scripts/sanitize_load_results.py`` strips and detects
   credential-shaped content, failing closed when any is present.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import textwrap

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
K6_SCRIPT = REPO_ROOT / "backend" / "load_tests" / "dev_backend_baseline.js"
SANITIZER = REPO_ROOT / "backend" / "scripts" / "sanitize_load_results.py"

# Structurally valid but entirely synthetic - not issued by any environment.
FAKE_JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    ".eyJzdWIiOiJzeW50aGV0aWMtdGVzdC1zdWJqZWN0In0"
    ".c3ludGhldGljLXNpZ25hdHVyZS1mb3ItdGVzdGluZw"
)

CREDENTIAL_MARKERS = ("token", "password", "secret", "authorization", "bearer")


def _load_sanitizer():
    sys.path.insert(0, str(SANITIZER.parent))
    try:
        import sanitize_load_results

        return sanitize_load_results
    finally:
        sys.path.pop(0)


# --- Layer 1: the harness never hands a credential to k6 --------------------


def test_setup_returns_no_credential_literal() -> None:
    """Static guard: setup() must not build an object carrying a credential."""
    source = K6_SCRIPT.read_text(encoding="utf-8")
    start = source.index("export function setup()")
    body = source[start : source.index("\n}", start)]

    assert "token:" not in body, "setup() must not place a token in its return value"
    assert "password" not in body.lower()
    # The preflight must explicitly opt out of returning what it fetched.
    assert "return {}" in body, "setup() must return an empty object"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_setup_data_contains_no_credentials_when_executed(tmp_path: pathlib.Path) -> None:
    """Dynamic guard: execute setup() with stubbed k6 modules and inspect it.

    This is what k6 would serialize into ``setup_data``, so asserting on the
    real return value catches regressions a static check could miss.
    """
    harness = tmp_path / "harness.mjs"
    harness.write_text(
        textwrap.dedent(
            f"""
            import {{ readFileSync }} from "node:fs";

            const source = readFileSync({json.dumps(str(K6_SCRIPT))}, "utf8");

            // Minimal k6 stubs. login() succeeds and hands back a fake JWT, so
            // if setup() leaked its token the assertion below would catch it.
            const loginBody = {{
              access_token: {json.dumps(FAKE_JWT)},
              user: {{ id: "synthetic-user" }},
            }};
            const response = {{
              status: 200,
              timings: {{ duration: 1.0 }},
              json: () => loginBody,
              body: JSON.stringify(loginBody),
            }};
            const httpStub = new Proxy(
              {{ expectedStatuses: () => null }},
              {{ get: (target, prop) => prop in target ? target[prop] : () => response }}
            );
            const stubs = {{
              http: httpStub,
              check: () => true,
              fail: (message) => {{ throw new Error(message); }},
              sleep: () => {{}},
              Trend: class {{ add() {{}} }},
              Counter: class {{ add() {{}} }},
              Rate: class {{ add() {{}} }},
            }};

            // Rewrite k6 imports to the stubs and expose the module's exports.
            let code = source
              .replace(/^import[^;]+;$/gm, "")
              .replace(/^export default function\\s*\\(/gm, "function __defaultExport(")
              .replace(/^export (function|const|let|class) /gm, "$1 ");
            code += "\\nreturn {{ setup, options }};";

            const factory = new Function(
              ...Object.keys(stubs),
              "__ENV",
              code
            );
            const env = {{
              SCENARIO: "authenticated-read",
              BASE_URL: "https://dev.invalid",
              EXPECTED_DEV_HOST: "dev.invalid",
              TEST_RUN_ID: "regression-test",
              STAGING_TEST_EMAIL: "synthetic@example.invalid",
              STAGING_TEST_PASSWORD: "synthetic-password",
            }};
            const mod = factory(...Object.values(stubs), env);
            process.stdout.write(JSON.stringify(mod.setup() ?? null));
            """
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        ["node", str(harness)], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, f"harness failed: {result.stderr}"

    setup_data = json.loads(result.stdout)
    serialized = json.dumps(setup_data).lower()

    assert FAKE_JWT.lower() not in serialized, "setup() leaked the access token"
    assert "eyj" not in serialized, "setup() returned a JWT-shaped value"
    for marker in CREDENTIAL_MARKERS:
        assert marker not in serialized, f"setup() returned a {marker!r} field"
    assert setup_data == {}, f"setup() must return an empty object, got {setup_data!r}"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_harness_rejects_a_production_target_without_sending_load(
    tmp_path: pathlib.Path,
) -> None:
    """Evaluate module configuration only and prove production is denied."""
    harness = tmp_path / "production-guard.mjs"
    harness.write_text(
        textwrap.dedent(
            f"""
            import {{ readFileSync }} from "node:fs";

            const source = readFileSync({json.dumps(str(K6_SCRIPT))}, "utf8");
            const noResponse = () => {{ throw new Error("network call attempted"); }};
            const httpStub = new Proxy(
              {{ expectedStatuses: () => null }},
              {{ get: () => noResponse }}
            );
            const stubs = {{
              http: httpStub,
              check: () => true,
              fail: (message) => {{ throw new Error(message); }},
              sleep: () => {{}},
              Trend: class {{ add() {{}} }},
              Counter: class {{ add() {{}} }},
              Rate: class {{ add() {{}} }},
            }};
            let code = source
              .replace(/^import[^;]+;$/gm, "")
              .replace(/^export default function\\s*\\(/gm, "function __defaultExport(")
              .replace(/^export (function|const|let|class) /gm, "$1 ");
            code += "\\nreturn {{ setup, options }};";

            const factory = new Function(...Object.keys(stubs), "__ENV", code);
            const env = {{
              SCENARIO: "public-read",
              BASE_URL: "https://production.example",
              EXPECTED_DEV_HOST: "production.example",
              PRODUCTION_BACKEND_HOSTS: "production.example",
              TEST_RUN_ID: "production-guard",
            }};
            factory(...Object.values(stubs), env);
            """
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        ["node", str(harness)], capture_output=True, text=True, timeout=60
    )

    assert result.returncode != 0
    assert "Refusing to run against a production backend host" in result.stderr
    assert "network call attempted" not in result.stderr


# --- Layer 2: the sanitizer strips and the verifier fails closed -----------


def _write_summary(results: pathlib.Path, name: str, *, with_setup_data: bool) -> pathlib.Path:
    payload: dict[str, object] = {"metrics": {"http_reqs": {"count": 61}}, "root_group": {}}
    if with_setup_data:
        payload["setup_data"] = {"syntheticPushToken": "perf-baseline-x", "token": FAKE_JWT}
    path = results / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_sanitizer_strips_setup_data_and_trace_headers(tmp_path: pathlib.Path) -> None:
    sanitizer = _load_sanitizer()
    results = tmp_path / "results"
    results.mkdir()

    summary = _write_summary(results, "authenticated-read-run-1-summary.json", with_setup_data=True)
    (results / "initial-health-headers.txt").write_text(
        "HTTP/2 200\nx-railway-request-id: abc123\nx-request-id: def456\n"
        "x-hikari-trace: iad1.trg5\nx-railway-edge: iad1\n",
        encoding="utf-8",
    )

    sanitizer.sanitize(results)

    cleaned = json.loads(summary.read_text(encoding="utf-8"))
    assert "setup_data" not in cleaned
    assert FAKE_JWT not in summary.read_text(encoding="utf-8")
    assert cleaned["metrics"] == {"http_reqs": {"count": 61}}, "metrics must be preserved"

    headers = (results / "initial-health-headers.txt").read_text(encoding="utf-8")
    assert "abc123" not in headers and "iad1.trg5" not in headers
    assert "x-railway-edge: iad1" in headers, "non-identifying headers must be preserved"


def test_summary_export_has_no_bearer_token_after_sanitizing(tmp_path: pathlib.Path) -> None:
    sanitizer = _load_sanitizer()
    results = tmp_path / "results"
    results.mkdir()
    _write_summary(results, "controlled-write-run-1-summary.json", with_setup_data=True)

    sanitizer.sanitize(results)

    assert sanitizer.find_credentials(results) == []


def test_verification_fails_when_a_jwt_is_injected(tmp_path: pathlib.Path) -> None:
    """A credential the sanitizer does not rewrite must still fail the run."""
    sanitizer = _load_sanitizer()
    results = tmp_path / "results"
    results.mkdir()
    _write_summary(results, "public-read-run-1-summary.json", with_setup_data=False)

    # Console logs are not rewritten by sanitize(), so this models a leak path
    # the stripper cannot cover - the verifier is the backstop.
    (results / "authenticated-read-run-1-console.log").write_text(
        f"debug: Authorization: Bearer {FAKE_JWT}\n", encoding="utf-8"
    )

    offenders = sanitizer.find_credentials(results)
    assert offenders, "verifier missed an injected JWT"
    assert any(label == "jwt" for _, label, _ in offenders)

    exit_code = sanitizer.main([str(results), "--verify"])
    assert exit_code == 1, "verification must fail closed on injected credentials"


@pytest.mark.parametrize(
    ("content", "expected_label"),
    [
        ("account=reserved@example.invalid\n", "mailbox"),
        ('{"access_token":"opaque-value"}\n', "sensitive field"),
        ("STAGING_TEST_PASSWORD was unexpectedly present\n", "sensitive field"),
    ],
)
def test_verification_rejects_mailbox_and_sensitive_fields(
    tmp_path: pathlib.Path, content: str, expected_label: str
) -> None:
    sanitizer = _load_sanitizer()
    results = tmp_path / "results"
    results.mkdir()
    (results / "unsafe.log").write_text(content, encoding="utf-8")

    offenders = sanitizer.find_credentials(results)

    assert any(label == expected_label for _, label, _ in offenders)
    assert sanitizer.main([str(results), "--verify"]) == 1


def test_verification_passes_on_clean_results(tmp_path: pathlib.Path) -> None:
    sanitizer = _load_sanitizer()
    results = tmp_path / "results"
    results.mkdir()
    _write_summary(results, "public-read-run-1-summary.json", with_setup_data=False)
    (results / "public-read-run-1-console.log").write_text("no credentials\n", encoding="utf-8")

    assert sanitizer.main([str(results), "--verify"]) == 0


def test_verifier_output_never_echoes_the_credential(tmp_path: pathlib.Path, capsys) -> None:
    """Failure output must name files, not leak the value it found."""
    sanitizer = _load_sanitizer()
    results = tmp_path / "results"
    results.mkdir()
    (results / "leak.log").write_text(f"Bearer {FAKE_JWT}\n", encoding="utf-8")

    sanitizer.main([str(results), "--verify"])

    captured = capsys.readouterr().out
    assert "leak.log" in captured
    assert FAKE_JWT not in captured
    assert "eyJ" not in captured


def test_verifier_output_never_echoes_a_mailbox(tmp_path: pathlib.Path, capsys) -> None:
    sanitizer = _load_sanitizer()
    results = tmp_path / "results"
    results.mkdir()
    mailbox = "reserved@example.invalid"
    (results / "leak.log").write_text(mailbox, encoding="utf-8")

    sanitizer.main([str(results), "--verify"])

    captured = capsys.readouterr().out
    assert "leak.log" in captured
    assert mailbox not in captured
