# E10-05 — Android versionCode / versionName Bump Strategy

**Roadmap task:** E10-05 — Define Android versionCode/versionName bump strategy

**Scope:** Documentation, Gradle/CI validation, and a one-time normalization of the initial
`versionName`. No Google Play upload, no production release, no application ID change, no
signing change, no iOS work.

This document is the Android-specific implementation of the project-wide
[Release Versioning Policy](release-versioning-policy.md). Read that document first for the
general SemVer rules; this document defines where those values live for Android, how they are
validated, and the exact bump procedure.

## 1. Audit of prior repository state

Audited on branch `codex/e10-05-android-version-strategy`, created from `main` at `6741ec8`.

| Item | Finding |
| --- | --- |
| `frontend/android/app/build.gradle` `defaultConfig` | `versionCode 1`, `versionName "1.0"` — hardcoded literals |
| `frontend/android/app/build.gradle.kts` | Does not exist (project uses Groovy Gradle only) |
| `frontend/android/build.gradle`, `variables.gradle` | No version values; only SDK/toolchain versions |
| `frontend/package.json` `"version"` | `"0.0.0"` — Vite scaffold default, unrelated to the Android app, never read by Gradle |
| `.github/workflows/android-build-validation.yml` | Did not set or override `versionCode`/`versionName`; the only reference was a comment in the Sentry-release-identifier step noting `versionName` was still a placeholder |
| Other Android CI/build scripts (`frontend/scripts/*.mjs`) | None read or write Android version values |
| `docs/mobile-build-strategy.md` | Already documented `versionCode 1` / `versionName "1.0"` as "initial values... should be updated before first release" (§8.2, §11.2, §11.6) |
| `docs/release-versioning-policy.md` | Already defines the project-wide SemVer policy and flags "no single app-wide version source of truth" as a known gap (§7, §14) |
| Git tags | None exist |
| Play Console uploads | None — `frontend/android/` was added in PR #740; no signed release has ever been produced (confirmed via `docs/mobile-build-strategy.md` §11.7 audit verdict: "NOT YET READY for production release") |

**Conclusion:** no automated versioning existed, debug and release build types shared the same
`defaultConfig` version (no per-variant override), CI did not override the committed version,
and no prior Play Console upload exists — so the repository's current `versionCode` is a safe
initial baseline with no owner confirmation blocking it.

## 2. Single source of truth

`frontend/android/app/build.gradle`, top of file, is the **only** authoritative location:

```groovy
def appVersionCode = 1
def appVersionName = "1.0.0"
```

`defaultConfig` reads these two variables (`versionCode appVersionCode`, `versionName
appVersionName`) instead of literals, so there is exactly one place to edit per bump. No other
file may declare or duplicate a version number for the Android app:

- `frontend/package.json` `"version"` remains the unrelated Vite scaffold value and must not be
  read for Android release identity.
- CI (`android-build-validation.yml`) must not set, override, or compute `versionCode`/
  `versionName` — it only validates the committed values (§4) and builds from them.
- Documentation (`docs/mobile-build-strategy.md`, `docs/release-versioning-policy.md`) references
  this file rather than restating the current numbers, to avoid drift.

## 3. Version format

`versionName` **must** follow strict `MAJOR.MINOR.PATCH` (three numeric components, no
pre-release suffix, no leading `v`), per the [Release Versioning
Policy](release-versioning-policy.md#3-version-format). The pre-existing project-wide MAJOR/
MINOR/PATCH increment rules (§4 of that document) apply unchanged to the Android app: MAJOR for
breaking changes, MINOR for backward-compatible features (resets PATCH to `0`), PATCH for fixes.

The previous value `"1.0"` did not satisfy this format (two components, not three). It is
normalized to `"1.0.0"` as part of this task (§7) — a documentation/format correction, not a
release, since no Android artifact has ever been uploaded to Play Console.

## 4. versionCode strategy

- `versionCode` is a positive integer, strictly increasing.
- Increase it by exactly `1` for every artifact intended for upload to any Google Play Console
  track (Internal, Closed, Open, or Production).
- Never reuse a previously uploaded value.
- Do not derive it from `versionName` (no `major*10000+minor*100+patch` scheme) — this repository
  has no such conversion approved, and an arbitrary integer avoids surprises when PATCH exceeds
  99 or when a hotfix needs to slot between two existing codes.
- Ordinary PR/branch builds (the `android-debug-build` job, `workflow_dispatch`-triggered) consume
  the committed `versionCode` as-is and are **not** considered store releases. Multiple CI runs
  may share a `versionCode`/`versionName` pair as long as none of those artifacts is independently
  uploaded to Play Console (see §6, "CI-generated builds").
- A version bump is a deliberate, separate commit made only when preparing an artifact that will
  actually be uploaded.

| Release purpose | versionName | versionCode |
| --- | ---: | ---: |
| Initial baseline (current) | `1.0.0` | `1` |
| First Play Console upload (any track) | `1.0.0` | `2`* |
| Bug-fix release | `1.0.1` | `3` |
| Feature release | `1.1.0` | `4` |
| Major release | `2.0.0` | `5` |

\* If `versionCode 1` is ever itself uploaded to Play Console before this table is revisited,
start the next bump from the actual highest uploaded value instead (§9, "Existing Play Console
history").

## 5. Validation

Two layers validate the same rule (`versionCode` positive integer; `versionName` matches
`^\d+\.\d+\.\d+$`), so an invalid value can never reach a build artifact:

### 5.1 Gradle (authoritative, always runs)

`frontend/android/app/build.gradle` validates `appVersionCode`/`appVersionName` immediately after
declaring them, before any task runs:

```groovy
if (!(appVersionCode instanceof Integer) || appVersionCode <= 0) {
    throw new GradleException("Invalid Android versionCode '${appVersionCode}': must be a positive integer. ...")
}
if (!(appVersionName instanceof String) || !(appVersionName ==~ /^\d+\.\d+\.\d+$/)) {
    throw new GradleException("Invalid Android versionName '${appVersionName}': must follow MAJOR.MINOR.PATCH ...")
}
```

Any Gradle invocation (`assembleDebug`, `assembleRelease`, `bundleRelease`, `tasks`, etc.) fails
immediately and clearly if the committed values are invalid. This is the enforcement layer that
protects release artifacts — Node/CI validation (below) is a fast pre-check, not a substitute.

### 5.2 Node script (fast PR-time pre-check, no Android toolchain required)

`frontend/scripts/validate-android-version.mjs` parses the same two `def` lines out of
`frontend/android/app/build.gradle` with a regex and applies the identical rules. It is wired
into CI (§6) so a bad version value fails a PR in seconds, without requiring the JDK/Android SDK
toolchain that the full Gradle build needs.

- `npm run android:version:validate` — validates the real committed file, prints the resolved
  `versionCode`/`versionName` on success.
- `npm run test:android-version` — unit/CLI tests for the parser (`frontend/scripts/validate-android-version.test.mjs`),
  covering zero/negative/non-integer `versionCode`, missing-patch/empty/non-numeric `versionName`,
  and missing `def` lines.

### 5.3 Inspecting a built artifact

`frontend/android/app/build.gradle` also registers a `printVersion` task that prints the resolved
values without a full assemble:

```bash
cd frontend/android
./gradlew :app:printVersion
# applicationId=com.yeshmishak.app
# versionCode=1
# versionName=1.0.0
```

To confirm the version actually embedded in a built APK/AAB, use Android's `aapt` (already
required in CI for `apksigner`, so no new dependency):

```bash
AAPT="$ANDROID_HOME/build-tools/<version>/aapt"
"$AAPT" dump badging app/build/outputs/apk/debug/app-debug.apk | grep -E 'package:|versionCode|versionName'
# package: name='com.yeshmishak.app' versionCode='1' versionName='1.0.0' ...
```

For an AAB, extract the base module's `AndroidManifest.xml` with `bundletool` or run
`aapt2 dump badging` against a built universal APK.

## 6. CI behavior

`.github/workflows/android-build-validation.yml`:

- `firebase-config-validation` job (runs on every PR touching Android-relevant paths): now also
  runs `npm run test:android-version` and `npm run android:version:validate` immediately after
  the existing Firebase config test. Neither step sets or mutates any version value — they only
  read and validate the committed `build.gradle`.
- `android-debug-build` job (runs only on `workflow_dispatch`, unchanged trigger): builds
  `assembleDebug` from whatever `versionCode`/`versionName` is committed on the built commit. It
  does not bump, override, or compute a version. The Sentry-release-identifier step's comment was
  updated to reference this document instead of describing `"1.0"` as a placeholder, since the
  interim commit-SHA-only release format (`docs/e09-01-crash-reporting-execution-plan.md`) is
  unchanged — that format still applies until the first real release bump lands.
- CI-produced debug APKs are build/test artifacts, not Play Console uploads, so they are exempt
  from the strict-increase rule (§4).

## 7. Change made in this task

`frontend/android/app/build.gradle`:

```diff
- versionCode 1
- versionName "1.0"
+ versionCode appVersionCode  // = 1
+ versionName appVersionName  // = "1.0.0"
```

`versionCode` is unchanged (`1`). `versionName` is normalized from `"1.0"` to `"1.0.0"` to satisfy
strict SemVer — a format fix, not a release, since no artifact carrying either value has ever been
uploaded to Play Console (§1).

## 8. Release bump procedure

1. Decide the bump type (patch, minor, major) using the [Release Versioning
   Policy](release-versioning-policy.md#4-increment-rules) increment rules.
2. Edit `frontend/android/app/build.gradle`:
   - Update `appVersionName` to the new `MAJOR.MINOR.PATCH` string (reset `PATCH` to `0` on a
     MINOR bump; reset `MINOR` and `PATCH` to `0` on a MAJOR bump).
   - Increment `appVersionCode` by `1`.
3. Run validation: `npm run android:version:validate` (from `frontend/`).
4. Build the release artifact: `./gradlew bundleRelease` (or `assembleRelease`), from
   `frontend/android/`, with release signing configured per `docs/android-signing.md`.
5. Inspect the artifact per §5.3 and confirm `versionCode`/`versionName` match what was committed.
6. Run the relevant automated tests (`npm run test:android-version`, existing Android/frontend
   suites).
7. Commit the version bump as its own commit (or as part of a release-preparation commit) —
   never bundle it silently inside an unrelated feature commit.
8. Only after the build is approved, create the Git tag (`vMAJOR.MINOR.PATCH`, per
   `docs/release-versioning-policy.md#8-release-branch--git-tag-rules`).
9. Before uploading to Play Console, confirm the new `versionCode` exceeds the highest value ever
   uploaded to that application, per Play Console itself — not just this repository's history
   (§9, "Existing Play Console history"). This confirmation is a manual owner step (§10).

### Worked examples

Patch bump:

```diff
- def appVersionCode = 12
- def appVersionName = "1.3.2"
+ def appVersionCode = 13
+ def appVersionName = "1.3.3"
```

Minor bump:

```diff
- def appVersionCode = 13
- def appVersionName = "1.3.3"
+ def appVersionCode = 14
+ def appVersionName = "1.4.0"
```

## 9. Edge cases

| Case | Handling |
| --- | --- |
| Duplicate `versionCode` (already uploaded) | Gradle validation only checks format/positivity, not Play Console history — the release-bump procedure (§8, step 9) requires a manual confirmation against Play Console before every upload. This repository has no automated Play Console API check. |
| `versionName` changed, `versionCode` unchanged | Valid Gradle-wise, but the release-bump procedure (§8) always pairs a `versionName` bump with a `versionCode` increment; treat a PR that changes one without the other as needing explicit justification in review. |
| `versionCode` changed, `versionName` unchanged | Allowed and expected for internal-test-only builds that don't change user-facing version (§4). Must be an intentional, documented commit. |
| Concurrent branches bump from the same baseline | Whichever branch merges second must rebase and re-increment `appVersionCode` before producing a store artifact — Gradle cannot detect this automatically; it is a merge-review responsibility. |
| CI-generated builds | Multiple `workflow_dispatch` runs from the same commit share the same version; this is fine because none is uploaded to Play Console independently (§4, §6). |
| Downgrade installation | Android/Play Console reject installing a lower `versionCode` over an existing higher one without uninstalling first. Testers must be told to uninstall before sideloading an older debug APK. |
| Capacitor sync (`npx cap sync android`) | Verified in this task: `npx cap sync android` does not touch `versionCode`/`versionName` in `app/build.gradle` — it only regenerates `capacitor.build.gradle`, `capacitor.settings.gradle`, and the synced web assets. |
| Debug vs. release variant | Both variants share the same `defaultConfig` `versionCode`/`versionName` (no `buildTypes`-level override or suffix exists today). If a future need arises for a `-debug` suffix or `versionNameSuffix`, document it here explicitly rather than adding it silently. |
| Invalid `versionName` (`"release-final"`, `"1.0"`, `""`, whitespace) | Rejected by both the Gradle build (§5.1) and the Node validator (§5.2) with a clear, specific error message referencing this document. |
| Existing Play Console history exceeding repo value | Not applicable yet — confirmed in §1 that no Android artifact has ever been uploaded. If this changes, the next release must use a `versionCode` higher than the Play Console maximum regardless of what is committed here. |

## 10. Manual owner follow-ups

None of these block completing this task, but they must happen before the **first real Play
Console upload**:

1. Confirm in Play Console whether any APK/AAB has ever actually been uploaded (this audit found
   no repository or CI evidence of one, but Play Console is the authoritative source).
2. If an upload exists, provide its highest `versionCode` so the next release can start above it.
3. Approve `1.0.0` as the public `versionName` for the first store release (or provide a
   different value).
4. Confirm whether internal Play testing builds should consume sequential official version codes
   or a separate internal counter.
5. Confirm the Git tag format `vX.Y.Z` (already the project default per
   `docs/release-versioning-policy.md#8-release-branch--git-tag-rules`).

## 11. Verification performed

Environment note: this machine has no `java`/Android SDK on `PATH` by default, but Android
Studio's bundled JBR (`Android Studio/jbr`, OpenJDK 21.0.10) and a local Android SDK
(`build-tools` 35/36/37) are installed and were used directly.

Environment note 2: building directly inside this repository's checkout (which lives under a
OneDrive-synced folder) hit a reproducible Windows file-lock error in
`:app:mergeDebugResources` (`Unable to delete directory ...merged_res_blame_folder...`) —
OneDrive's sync agent contends for file handles Gradle's incremental resource merge needs to
delete and recreate. This is an environment/tooling issue unrelated to this task's changes: the
same failure reproduced identically before any Gradle file was edited. It was worked around for
local verification only by building from a copy of `frontend/android` (plus a symlink to
`frontend/node_modules`, since Capacitor's generated `capacitor.settings.gradle` resolves plugin
projects via `../node_modules/...`) outside the OneDrive tree; no repository file changed as a
result. CI (GitHub Actions `ubuntu-latest` runners) is not affected by this, since it does not run
under OneDrive.

| Check | Result |
| --- | --- |
| `npm run test:android-version` | PASS — 13/13 tests |
| `npm run android:version:validate` (real `build.gradle`) | PASS — `versionCode=1 versionName=1.0.0` |
| `npm run build:android` | PASS |
| `npx cap sync android` | PASS — confirmed no version-value change (§9) |
| `./gradlew assembleDebug` (synthetic, non-secret Firebase config) | PASS — `BUILD SUCCESSFUL`, produced `app-debug.apk` |
| `./gradlew :app:printVersion` | PASS — `applicationId=com.yeshmishak.app`, `versionCode=1`, `versionName=1.0.0` |
| `aapt dump badging app-debug.apk` | PASS — `package: name='com.yeshmishak.app' versionCode='1' versionName='1.0.0'` |
| Negative: `appVersionName = "1.0"` | PASS (as a validation test) — Gradle fails clearly: `Invalid Android versionName '1.0': must follow MAJOR.MINOR.PATCH ...` |
| Negative: `appVersionCode = 0` | PASS (as a validation test) — Gradle fails clearly: `Invalid Android versionCode '0': must be a positive integer.` |
| Restore to committed values, rebuild | PASS |

No real Firebase project, signing keystore, or other secret was used or committed; the synthetic
`google-services.json` used for the debug build was deleted after verification and was never
staged (it is also repository-ignored).
