# E10-01 Android Release Signing Execution Plan

**Roadmap task:** E10-01 — Generate release keystore + configure signing

**Implementation boundary:** Configure and document release signing without generating, storing, or committing a real keystore or secret

## Goal and outcome

Make the Android project ready to consume an organization-owned release keystore from local, ignored configuration. A release build must use `signingConfigs.release`; a debug build must retain the existing local and CI signing behavior. Because this task explicitly forbids creating real signing material, the actual `keytool` ceremony remains a documented release-operator action.

## Current-state review

| Area | Before E10-01 | Required outcome |
| --- | --- | --- |
| Release Gradle signing | No release signing configuration | `signingConfigs.release` reads local properties and is assigned to `buildTypes.release` |
| Debug Gradle signing | Android default locally; optional `ciDebug` from `ANDROID_DEBUG_KEYSTORE_*` variables | Behavior preserved unchanged |
| Property file | No `key.properties` | Ignored local file with a tracked placeholder template |
| Keystore | None in repository | Still none in repository; operator-generated file stored externally |
| Ignore rules | Only the named CI debug keystore ignored; template keystore rules commented out | Repository-wide exclusion for `key.properties`, `*.jks`, and `*.keystore` |
| Operator guidance | General build guidance only | End-to-end generation, storage, configuration, build, verification, backup, and incident guidance |

## Design decisions

1. `frontend/android/key.properties` is the single local configuration source. Gradle resolves `storeFile` relative to `frontend/android` when it is not absolute.
2. The file contains `storeFile`, `storePassword`, `keyAlias`, and `keyPassword`. No value is duplicated in Gradle, environment defaults, documentation, or source control.
3. `signingConfigs.release` always exists and is always assigned to `buildTypes.release`. It is populated only when `key.properties` passes validation. This prevents a release build from silently inheriting debug signing.
4. Explicit artifact-producing release Gradle invocations fail early when `key.properties` is absent. Release lint and unit-test tasks remain usable without signing credentials. A present file also fails fast when a required value is blank or the referenced keystore does not exist.
5. The `ciDebug` configuration and its completeness/file checks remain independent. No release property affects `buildTypes.debug`.
6. The release keystore is generated and held outside Git under organization custody. A protected future CI release workflow is separate from the existing debug workflow.

## Implementation tasks

### Task 1 — Add repository safety controls

Files:

- Modify `.gitignore`.
- Modify `frontend/android/.gitignore`.
- Add `frontend/android/key.properties.example`.

Actions:

- Ignore `key.properties`, `*.jks`, and `*.keystore` repository-wide and within the Android subtree.
- Keep `ci-debug.keystore` ignored.
- Add only placeholder property values and warnings to the tracked example.
- Verify an ignored local `key.properties` cannot be staged accidentally.

### Task 2 — Configure Gradle release signing

File: `frontend/android/app/build.gradle`

Actions:

- Load `frontend/android/key.properties` with `java.util.Properties` when present.
- Validate the four required property names without printing their values.
- Resolve and validate the configured keystore file dynamically.
- Define `signingConfigs.release` and assign it to `buildTypes.release`.
- Fail release requests clearly when local signing configuration is absent.
- Leave the existing `ciDebugSigningValues`, partial-variable guard, keystore-file guard, and debug build-type assignment intact.

### Task 3 — Add the operator runbook

Files:

- Add `docs/android-signing.md`.
- Modify `docs/mobile-build-strategy.md`.
- Modify `docs/android-google-authentication-configuration.md`.

Actions:

- Document an interactive `keytool -genkeypair` command that does not place passwords on the command line.
- Require external encrypted storage, least-privilege access, backup, and recovery testing.
- Document copying the template, all property names, Windows path escaping, and Git-ignore verification.
- Document prerequisites, Capacitor sync, `bundleRelease`, `assembleRelease`, artifact locations, and certificate verification.
- State the CI boundary, debug-signing independence, and compromise/rotation response.
- Update existing signing-readiness and Android OAuth documentation so it distinguishes implemented Gradle wiring from the still-pending keystore operator step.

### Task 4 — Verify behavior

Use only synthetic Firebase configuration and placeholder signing values during validation; remove every temporary local file afterward.

| Scenario | Command/check | Expected result |
| --- | --- | --- |
| Gradle configuration without release secrets | `gradlew tasks` | Pass |
| Existing debug path | `gradlew assembleDebug --no-daemon` after synthetic Firebase setup | Pass and produce a debug APK |
| Missing release configuration | `gradlew bundleRelease --no-daemon` with no `key.properties` | Fail with the E10-01 missing-configuration message before producing a release bundle |
| Complete property mapping, no real key | Run a non-release Gradle configuration task with a temporary ignored `key.properties` whose `storeFile` points to an existing non-secret fixture | Pass property loading without creating a keystore |
| Incomplete properties | Run Gradle with one temporary placeholder property omitted | Fail and name only the missing property, never a value |
| Ignore coverage | `git check-ignore` for representative property and keystore paths | Pass |
| Secret/repository hygiene | Inspect `git status`, `git diff --check`, changed-file names, and tracked keystore patterns | No secret file or keystore tracked |

The negative release test is intentional: a successfully signed release cannot be produced in this task because a real keystore is expressly out of scope. The passing debug build plus configuration and failure-path checks validate the implementation without fabricating signing credentials.

### Task 5 — Publish only after validation

Actions:

- Review the complete diff and stage only the E10-01 files.
- Commit with a focused message.
- Push the isolated branch based on latest `main`.
- Open a draft PR describing security boundaries and exact verification results only after every expected-positive check passes and every expected-negative check fails for the documented reason.

## Acceptance criteria

- [ ] Release builds reference `signingConfigs.release` populated from `key.properties`.
- [ ] Release tasks cannot silently create an unsigned or debug-signed distribution artifact.
- [ ] Debug signing remains unchanged locally and in CI.
- [ ] `key.properties.example` contains placeholders only.
- [ ] `key.properties`, `*.jks`, and `*.keystore` are ignored.
- [ ] No real keystore, password, alias, private key, or machine path is committed.
- [ ] The signing runbook covers generation, custody, local properties, signed builds, and verification.
- [ ] Existing signing-readiness documentation reflects the E10-01 configuration and remaining operational handoff.
- [ ] Relevant Android positive and negative verification completes as designed.
- [ ] The PR contains only E10-01 changes and is opened after validation.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Accidental credential commit | Repository-wide ignore patterns, Android-local patterns, placeholder-only template, staged-file review |
| Unsigned release artifact | Release build type always references the release signing config; missing setup fails |
| Debug CI regression | Keep the existing environment-variable config independent and run a debug build |
| Machine-specific path committed | Store the path only in ignored `key.properties`; use a placeholder in the example |
| Lost release key blocks updates | Organization custody, encrypted backup, recovery test, restricted access |
| Signing-key change breaks upgrade continuity | Require approved Play signing recovery/upgrade process; never replace silently |

## Rollback plan

Revert the E10-01 commit. This removes the release property loader, release signing assignment, example, and documentation while restoring the previous unsigned release configuration. No credential migration or keystore rollback is required because this change creates and stores no real signing material.
