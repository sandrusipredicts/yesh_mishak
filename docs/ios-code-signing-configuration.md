# iOS Code Signing Configuration

**Issue:** ISSUE-210
**Status:** BLOCKED — prerequisites not met
**Date:** 2026-07-01
**Approved Bundle Identifier (from ISSUE-208/209):** `com.yeshmishak.app`

## 1. Current Signing Status

**No signing configuration was applied in this issue.** The Xcode project (`frontend/ios/App/App.xcodeproj/project.pbxproj`) was **not modified**. It remains exactly as ISSUE-206/208 left it: Capacitor's default `CODE_SIGN_STYLE = Automatic`, no `DEVELOPMENT_TEAM` committed, and the approved Bundle Identifier already applied. This is the same "no real signing configured" state described in `docs/ios-code-signing-strategy.md` §1.1, unchanged by this issue.

## 2. Why This Issue Is Blocked

ISSUE-210 requires configuring development signing and validating install/launch on a **physical iPhone**, which in turn requires macOS + Xcode + Apple Developer team access + a trusted physical iPhone all being available in the same session. None of these are available here. Per this issue's own explicit instructions: *"If any of these prerequisites are missing, stop and produce a BLOCKED/PARTIAL readiness report. Do not fake completion."* This report does that.

### Prerequisite Checklist

| # | Prerequisite | Result | Evidence |
| --- | --- | --- | --- |
| 1 | Latest `main`, clean working tree, before branching | **PASS** | `git status` → clean; `git pull origin main` → already up to date at merge of PR #774 (ISSUE-209) before branching |
| 2 | Branch `issue-210-configure-ios-code-signing` created | **PASS** | Created from `main` at commit `60ffcc5` |
| 3 | macOS available | **FAIL** | `uname -a` → `MINGW64_NT-10.0-26200 ... Msys` (Windows). This session has no macOS environment. |
| 4 | Xcode installed | **FAIL** | `which xcodebuild` → not found. Xcode cannot run on Windows; this is a direct consequence of #3, not a separate installable gap. |
| 5 | Apple Developer account/team access available | **FAIL** | `docs/ios-code-signing-strategy.md` §1.1 and §10 explicitly document: *"no organization Apple Developer Program account is documented"* and *"Physical iPhone development ... Blocked: no organization team documented."* This is not a local-machine limitation — it is the organization's current, approved, documented state. No Team ID, Account Holder, or Apple Admin is named anywhere in the repository (by design — see strategy §2, §6.1: this material belongs in a private access register, not Git, and none has been provisioned yet regardless). |
| 6 | A physical iPhone connected and trusted | **FAIL** | No physical iOS device is attached to this session. Detecting/trusting a device also requires macOS + Xcode (or at minimum `libimobiledevice`-class tooling), which are unavailable here regardless of whether a device were physically present. |
| 7 | Approved Bundle Identifier from ISSUE-208 already applied | **PASS** | Confirmed directly: `frontend/capacitor.config.ts` → `appId: 'com.yeshmishak.app'`. `frontend/ios/App/App.xcodeproj/project.pbxproj` → `PRODUCT_BUNDLE_IDENTIFIER = com.yeshmishak.app;` (2 occurrences, Debug and Release configurations). Both match the approved identifier recorded in `docs/ios-code-signing-strategy.md`'s header (`com.yeshmishak.app`). No identifier was guessed or changed. |
| 8 | Signing strategy from ISSUE-209 exists | **PASS** | `docs/ios-code-signing-strategy.md` exists, is marked "Approved strategy; implementation not started," and was read in full before starting this issue. |
| 9 | Existing unsigned iOS GitHub Actions validation still present | **PASS** | `.github/workflows/ios-xcode-validation.yml` exists, unchanged. Latest runs on `main`-tracking branches are `completed success` (e.g. runs `28529244393` and `28529063997`, both from the ISSUE-208 PR, `completed success`). |

**Result: 3 of 9 prerequisites fail — all three (#3, #4, #5) are hard blockers per this issue's own decision rules** ("If Xcode/macOS is missing: BLOCKED" and "If Apple Developer access is missing: BLOCKED"). Item #6 (physical iPhone) also fails independently and cannot be evaluated at all without #3/#4 first.

## 3. What Was NOT Done (by design, per the hard safety rules)

- No Xcode signing settings were opened or changed. `frontend/ios/App/App.xcodeproj/project.pbxproj` has zero diff versus `main` (`git diff --stat` is empty).
- No Apple Team was selected or configured — none exists to select (see prerequisite #5).
- No development certificate, provisioning profile, or entitlement was created, requested, or committed.
- No build was attempted for iOS Simulator or physical iPhone — `xcodebuild` is not available on this machine, and attempting to fabricate a result would violate this issue's explicit "Do not fake completion" instruction.
- No app was installed or launched on a physical iPhone — none is connected.
- The GitHub Actions workflow (`.github/workflows/ios-xcode-validation.yml`) was **not modified**. It continues to validate an unsigned build only, exactly as ISSUE-209's strategy requires ("The existing unsigned workflow must not be converted into a signed workflow").
- No GitHub Secret was added.
- No TestFlight, App Store, APNs, Firebase, Push Notifications, or Native Login configuration was touched.
- No Android file was touched.

## 4. Signing Details (per required documentation fields)

| Field | Value |
| --- | --- |
| Apple Team used | **None** — no organization Apple Developer team is documented or available (see prerequisite #5) |
| Bundle Identifier | `com.yeshmishak.app` (confirmed matching in `capacitor.config.ts` and `project.pbxproj`; unchanged by this issue) |
| Signing mode selected | **None configured.** The project's existing default (`CODE_SIGN_STYLE = Automatic`, no committed `DEVELOPMENT_TEAM`) is unchanged. Per `docs/ios-code-signing-strategy.md` §3.3, automatic signing is the *allowed* mode for local physical-device development once an organization team exists — but none exists yet, so this remains theoretical, not applied. |
| Simulator build result | **Not run.** No macOS/Xcode available in this session. |
| Physical iPhone install result | **Not run.** No macOS/Xcode/device available in this session. |
| Physical iPhone launch result | **Not run.** No macOS/Xcode/device available in this session. |

## 5. What Remains Future Work

Unchanged from `docs/ios-code-signing-strategy.md`'s own final decision table — this issue did not move any of these forward, since doing so requires the missing prerequisites:

- Enroll/verify an organization Apple Developer Program membership and name the Account Holder, Apple Admins, iOS Maintainers, Release Manager, Security/DevOps Owner, and Product Release Approver (strategy §2, §11).
- Register the `com.yeshmishak.app` App ID to the organization team (strategy §10).
- Configure physical-device development signing on a Mac with Xcode once the team exists, without committing machine-specific settings (strategy §3.2, §3.3).
- TestFlight distribution signing, via a separate protected workflow and `ios-testflight` GitHub Environment (strategy §4).
- App Store production signing, via the protected `ios-production` environment and full approval gate (strategy §5).
- CI-signed builds of any kind — the current CI remains, and must remain, unsigned (strategy §8).
- APNs / Push Notifications — explicitly out of scope for this issue and not started.

## 6. Security Confirmation

- **No certificates committed.** Confirmed via `git ls-files | grep -Ei "p12|cer|certificate"` — only pre-existing, unrelated matches (`.env.example` template files, two Android device-compatibility docs matched on the generic word "certificate"). No `.p12`/`.cer` file exists anywhere in the working tree (`find . -iname "*.p12" -o -iname "*.cer"` → no results).
- **No provisioning profiles committed.** `git ls-files | grep -i mobileprovision` and `find . -iname "*.mobileprovision"` → no results.
- **No secrets committed.** `git ls-files | grep -Ei "secret|private|AuthKey"` → no matches beyond the pre-existing, already-approved `.env.example`/`.env.staging.example`/`frontend/.env` files, none of which contain Apple signing material. `find . -iname "AuthKey_*.p8"` → no results.
- **No private keys committed.** No `.p8`, `.pem`, or exported-Keychain-style file exists anywhere in the repository.
- **No `xcuserdata`, `DerivedData`, or `.xcuserstate` committed.** `find . -iname "*.xcuserstate"` → no results; `frontend/ios/.gitignore` already excludes `DerivedData` and `xcuserdata` (inherited unchanged from ISSUE-206).
- **`git status` / `git diff --stat` are both empty** — this issue produced no code or project-file change of any kind, only this documentation file.

## 7. Final Decision

**BLOCKED.**

Per this issue's decision rules:
- *"If Xcode/macOS is missing: BLOCKED."* — True here.
- *"If Apple Developer access is missing: BLOCKED."* — True here, and independently documented as true for the whole organization in ISSUE-209.
- *"Never mark COMPLETE unless the physical iPhone install Definition of Done is actually met."* — It was not attempted, let alone met.

This issue cannot proceed past the prerequisite check in the current environment. Re-attempt this issue from a session that has:
1. A macOS machine with Xcode installed (matching or close to the version already validated in CI, currently Xcode 16.4), and
2. Confirmed organization Apple Developer Program access with a named Account Holder/Admin per `docs/ios-code-signing-strategy.md` §2 (this is itself future work per ISSUE-209 §11, item 1 — it must happen before this issue can succeed, not as part of it), and
3. A physical iPhone, connected and unlocked, with "Trust This Computer" already accepted.

## 8. Files Changed in This Issue

- `docs/ios-code-signing-configuration.md` (this file, new)
- `docs/product-decisions.md` (decision entry appended)

No other file was created, modified, or deleted.
