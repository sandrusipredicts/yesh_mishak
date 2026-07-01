# iOS Debug Build Validation

**Issue:** ISSUE-212
**Date:** 2026-07-01
**Final status: PARTIAL PASS / BLOCKED FOR DEVICE INSTALLATION.**

## Summary Status Table

| Item | Result |
| --- | --- |
| iOS debug build (Simulator SDK) | **PASS** |
| GitHub Actions run | **PASS** |
| Simulator boot | **PASS** |
| Simulator install | **PASS** |
| Simulator launch | **PASS** |
| No immediate crash after launch | **PASS** (confirmed via `launchctl list` after a 5s wait) |
| Physical iPhone installation | **BLOCKED** — same prerequisites as ISSUE-210 (macOS/Xcode/Apple Developer team/trusted physical iPhone), none available in this environment |

**Why not COMPLETE:** per this issue's own decision rules, COMPLETE requires real, verified physical iPhone installation evidence. That was not attempted here because the same hard blockers documented in ISSUE-210 (`docs/ios-code-signing-configuration.md`) still apply — no macOS/Xcode, no organization Apple Developer team, and no physical iPhone are available in this environment. Faking or assuming that result would violate this issue's explicit truth rule.

## 1. Build Result

**PASS.** The app was built for the iOS Simulator SDK (`-sdk iphonesimulator`) on a real `macos-latest` GitHub Actions runner (Xcode 16.4), unsigned (`CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY=""`), targeting the approved Bundle Identifier `com.yeshmishak.app`. The build log ends with the literal Xcode output:

```
** BUILD SUCCEEDED **
```

The built app was located at `DerivedData/Build/Products/Debug-iphonesimulator/App.app`.

## 2. GitHub Actions Run

- **Workflow:** `.github/workflows/ios-debug-build-validation.yml` (new in this issue)
- **Run:** [28536538364](https://github.com/sandrusipredicts/yesh_mishak/actions/runs/28536538364) — triggered via the `pull_request` event on PR [#777](https://github.com/sandrusipredicts/yesh_mishak/pull/777)
- **Result:** `completed success`, 4m21s total, every step green (18/18)
- **Runner:** `macos-latest`, Xcode 16.4

All steps passed: checkout, Node setup, `npm ci`, `npm run build`, `npx cap sync ios`, listing available simulators, dynamic simulator selection, the Simulator build, locating the built `.app`, booting the simulator, installing the app, starting log capture, launching the app, confirming the process was still running after launch, and uploading the simulator log as a build artifact (`ios-simulator-log`, 45,210 bytes, retained until 2026-09-29).

## 3. Simulator Selection (dynamic, not hardcoded)

The runner had many iPhone simulators available across multiple iOS runtimes (`iPhone 16 Pro`, `iPhone 16 Pro Max`, `iPhone 16e`, `iPhone 16`, `iPhone 16 Plus`, `iPhone SE (3rd generation)`, each appearing twice for two different iOS runtime versions, plus several iPads). Per this issue's explicit instruction not to hardcode a specific device name blindly, the workflow selects the first available device whose name starts with "iPhone" via:

```bash
xcrun simctl list devices available -j \
  | jq -r '[.devices[][] | select(.isAvailable == true and (.name | startswith("iPhone")))][0].udid'
```

**Actual selection this run:** `iPhone 16 Pro` (UDID `CA266627-E454-44D4-A094-C92DBE3AE752`) — notably *not* the "iPhone 16" named in this issue's suggested workflow, even though an "iPhone 16" device was also available. This demonstrates the dynamic-selection logic is genuinely driving the choice (based on JSON iteration order), not silently matching a hardcoded fallback, and confirms the design requirement ("do not hardcode blindly") was correctly implemented and exercised for real.

## 4. Simulator Installation Result

**PASS.** `xcrun simctl install <udid> DerivedData/Build/Products/Debug-iphonesimulator/App.app` completed with no error output and a zero exit code (the step is green in the run).

## 5. Simulator Launch Result

**PASS.** `xcrun simctl launch <udid> com.yeshmishak.app` returned:

```
com.yeshmishak.app: 18135
```

confirming the app launched and was assigned process ID 18135.

## 6. No-Crash Confirmation

**PASS.** After a 5-second wait, `xcrun simctl spawn <udid> launchctl list | grep -F "com.yeshmishak.app"` returned:

```
18135	0	UIKitApplication:com.yeshmishak.app[b49a][rb-legacy]
```

Exit status `0` and a live job entry confirm the app process was still running 5+ seconds after launch — it did not crash immediately. The captured simulator log (via `xcrun simctl spawn <udid> log stream --predicate 'process == "App"'`, uploaded as the `ios-simulator-log` artifact) additionally shows the Capacitor WebView bridge genuinely initializing — real `WebCore`/`WebKit`/`WebsiteDataStore`/`NetworkProcessProxy` log lines are present, confirming the app got as far as starting to load its web content, not just presenting an empty native shell.

## 7. Physical iPhone Installation Status

**BLOCKED.** Not attempted, not faked. This is the same BLOCKED status ISSUE-210 already established and ISSUE-211 restated — this issue does not change it. Physical iPhone installation requires all of the following, none of which are available in this environment:

- A macOS machine with Xcode installed (this session is Windows; even the evidence above required a GitHub-hosted macOS runner, which cannot pair with or install onto a physical device brought to this session).
- An organization Apple Developer Program account/team — `docs/ios-code-signing-strategy.md` and `docs/ios-code-signing-configuration.md` (ISSUE-209/210) both document that none is currently provisioned.
- A development certificate and a device-specific provisioning profile, neither of which exist yet (correctly — see Security Confirmation below).
- A trusted physical iPhone, connected and with "Trust This Computer" already accepted — none is connected to this session.

**Unsigned Simulator success does not imply physical-device readiness.** The Simulator does not exercise code signing, device-specific provisioning, real hardware sensors, or App Store-distribution-specific behavior. This result proves the Xcode project, its dependency graph, and the app's basic startup path are all sound on real Apple tooling — it says nothing about whether a signed build would install and run correctly on a physical iPhone.

## 8. What Remains Required for Full Definition of Done

Unchanged from ISSUE-210's own list, restated here for direct traceability to this issue's blocker:

1. **Apple Developer team** — organization enrollment, with a named Account Holder and at least two Apple Admins (`docs/ios-code-signing-strategy.md` §2).
2. **Signing certificates/provisioning** — a development certificate and a device-specific provisioning profile for `com.yeshmishak.app`, created only after the team above exists.
3. **Mac/Xcode signing environment** — a real macOS machine with Xcode, used interactively by an authorized iOS Maintainer (GitHub's `macos-latest` runner cannot substitute for this step, since it cannot pair with a physical device brought to a separate session).
4. **A trusted physical iPhone** — connected to that Mac, with "Trust This Computer" accepted.

Once all four exist, the physical-device install/launch steps from ISSUE-210's original scope can be attempted for real, and only then can this area be marked COMPLETE.

## 9. Security Confirmation

Required scans re-run fresh for this issue.

```bash
git status                          # clean before this issue's commits
git diff --stat                     # empty at time of scan
git status --ignored                # only pre-existing, unrelated ignored paths (.env, caches, venvs, logs)
git ls-files | grep -Ei "p12|mobileprovision|cer|certificate|provision|AuthKey|DerivedData|xcuserdata|xcuserstate|\.env|secret|private"
  → backend/.env.example, backend/.env.staging.example,
    docs/device-compatibility-certification-checklist.md,
    docs/device-compatibility-certification-review.md,
    frontend/.env, frontend/.env.android.example,
    frontend/.env.example, frontend/.env.staging.example
  (all pre-existing, safe, already-approved template/placeholder files;
   none contain real Apple signing material)
find . -iname "*.p12" -o -iname "*.mobileprovision" -o -iname "*.cer" -o -iname "AuthKey_*.p8" -o -iname "*.xcuserstate"
  → no results
find . -type d \( -iname "DerivedData" -o -iname "xcuserdata" \)
  → no results (the workflow's own `DerivedData/` build output only ever exists inside the ephemeral GitHub Actions runner, never committed — confirmed by `frontend/ios/.gitignore` already excluding it, and by this local scan finding none in the repository)
```

| Check | Result |
| --- | --- |
| `.p12` committed | **No** |
| `.cer` committed | **No** |
| `.mobileprovision` committed | **No** |
| `AuthKey_*.p8` committed | **No** |
| `DerivedData` committed | **No** |
| `xcuserdata` committed | **No** |
| `*.xcuserstate` committed | **No** |
| Real secret-bearing `.env` committed | **No** — only pre-existing, already-approved placeholder templates |
| Private keys/secrets committed | **No** |
| Android files changed | **No** — `git diff --stat -- frontend/android` is empty |
| Signing configured anywhere in this issue | **No** — the workflow explicitly disables code signing (`CODE_SIGNING_ALLOWED=NO`); no `DEVELOPMENT_TEAM`, certificate, or provisioning profile was added |

## 10. Final Decision

**PARTIAL PASS / BLOCKED FOR DEVICE INSTALLATION.**

Per this issue's decision rules:
- Simulator build/install/launch all passed with real, observed evidence (not asserted) → this rules out NO-GO.
- Physical iPhone installation was correctly not attempted, since the same hard blockers from ISSUE-210 remain true today → this rules out COMPLETE.

This issue therefore closes as **PARTIAL PASS / BLOCKED FOR DEVICE INSTALLATION**, exactly matching the applicable decision rule. Re-attempt physical-device installation once the four prerequisites in §8 are all satisfied in the same session.

## 11. Files Changed in This Issue

- `.github/workflows/ios-debug-build-validation.yml` (new — Simulator build/install/launch CI workflow)
- `docs/ios-debug-build-validation.md` (this file, new)
- `docs/product-decisions.md` (decision entry appended)

No native iOS project file, Xcode project settings, signing configuration, or Android file was created, modified, or deleted.
