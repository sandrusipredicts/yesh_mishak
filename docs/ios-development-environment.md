# iOS Development Environment Setup

## Purpose

This is the official setup guide for developing the Capacitor iOS app (`frontend/ios/`). It exists so a new developer with a Mac can go from a fresh clone to a running app in the iOS Simulator, understand exactly which steps require a Mac versus which are already validated automatically in CI, and know what is genuinely future work (physical device testing, Apple Developer signing, TestFlight, App Store).

This document is setup guidance only. It does not add or require APNs, Firebase, push notifications, native login, TestFlight, App Store publishing, or any signing secret — those are explicitly out of scope here and are called out as future work in the relevant sections below.

## 1. Prerequisites

| Requirement | Why | Mac required? |
| --- | --- | --- |
| **macOS** | Xcode only runs on macOS. There is no way to build, open, or run the iOS project on Windows or Linux. | N/A — this is the Mac requirement itself |
| **Xcode** (current stable release) | Provides the iOS SDK, Simulator, and `xcodebuild` toolchain. The GitHub Actions CI validation in this repo currently runs against **Xcode 16.4** on `macos-latest` — install a version at or near that for the closest match to CI. | Yes |
| **Xcode Command Line Tools** | `xcodebuild`, `git`, and related CLI tools. Usually installed alongside Xcode, but can be missing if Xcode was installed via the App Store without ever being opened. Install with `xcode-select --install` if `xcodebuild -version` fails. | Yes |
| **Node.js 22** | Matches the version used in `.github/workflows/ios-xcode-validation.yml` (`node-version: 22`). The repo's `frontend/package.json` does not pin an `engines` field, but using 22 avoids any CI/local mismatch. | No (any OS) |
| **npm** | Ships with Node.js; used for `npm ci` / `npm run build`. | No |
| **Git** | To clone the repo and manage branches. | No |
| **Capacitor project location** | The iOS project lives at `frontend/ios/`, generated from and synced with the web app in `frontend/`. You do not create it from scratch — it is already committed to `main` (see `docs/ios-project-creation.md`). You only ever `npx cap sync ios` it after changes; you do not run `npx cap add ios` again unless the directory is deliberately removed. | No (this fact applies everywhere) |

You do **not** need an Apple Developer account, certificates, or provisioning profiles to complete this guide through "run in Simulator." Those are covered separately in [Section 5](#5-apple-developer-configuration) and [Section 6](#6-certificates-preparation) as later, optional steps.

## 2. Repository Setup

These steps work on any OS, but you'll need to be on a Mac before [Section 3](#3-opening-the-project) to actually open Xcode.

```bash
git clone https://github.com/sandrusipredicts/yesh_mishak.git
cd yesh_mishak
git checkout main
git pull origin main

cd frontend
npm ci
npm run build
npx cap config
npx cap sync ios
```

What each command does:
- `npm ci` — installs exact dependency versions from `frontend/package-lock.json`, including `@capacitor/ios`. Prefer this over `npm install` for a clean, reproducible environment.
- `npm run build` — runs `vite build`, producing `frontend/dist/`. The iOS project's copy of the web app (`frontend/ios/App/App/public/`) is regenerated from this on every `cap sync`, and is git-ignored — never edit it directly.
- `npx cap config` — prints the resolved Capacitor configuration; use it to sanity-check `appId` (`com.yeshmishak.app`), `appName` (`Yesh Mishak`), and `webDir` (`dist`) before proceeding.
- `npx cap sync ios` — copies the freshly built web app into `frontend/ios/App/App/public/`, regenerates the Capacitor-managed config files, and updates the Swift Package Manager plugin list. **Run this every time you change frontend code and want to see it in the iOS app.**

None of these commands require Xcode or macOS-specific tooling — you can (and CI does) run all of them on Linux/macOS runners identically.

## 3. Opening the Project

**This project uses Capacitor 8 with Swift Package Manager (SPM), not CocoaPods.** This is a real, structural fact about this specific project, confirmed directly by inspecting the generated files — do not assume the opposite.

Concretely, this means:
- There is **no standalone `frontend/ios/App/App.xcworkspace` with a committed `contents.xcworkspacedata`**. That file is only ever produced by CocoaPods' `pod install`, and this project does not run `pod install` or have a `Podfile`.
- The workspace embedded inside `frontend/ios/App/App.xcodeproj/project.xcworkspace` exists as a bundle directory, but has no committed `contents.xcworkspacedata` of its own — Xcode synthesizes it implicitly the first time you open the `.xcodeproj`.
- The actual, real, buildable project is **`frontend/ios/App/App.xcodeproj`**. Its `project.pbxproj` already has the local `CapApp-SPM` Swift package wired in directly (`XCLocalSwiftPackageReference "CapApp-SPM"`), which in turn pulls in `capacitor-swift-pm` (the Capacitor runtime) and any Capacitor plugins (currently `@capacitor/push-notifications`) as SPM dependencies.

**To open the project:**
```bash
open frontend/ios/App/App.xcodeproj
```
Or in Xcode: **File → Open...** and select `frontend/ios/App/App.xcodeproj`.

Do **not** look for or expect an `App.xcworkspace` file at the top level of `frontend/ios/App/` — if you don't find one, that is expected, not a broken checkout. If you ever do see one appear (e.g., from a future switch back to CocoaPods), that would be a deliberate project change, not something to assume is already true today.

On first open, Xcode will automatically resolve the SPM package graph (fetching `capacitor-swift-pm` from GitHub and linking the local packages). This requires network access and can take a minute or two the first time; subsequent opens are fast because packages are cached.

## 4. iOS Simulator Setup

1. **Install simulators:** Xcode → Settings → Platforms (or **Xcode → Settings → Components** on older Xcode versions) → download an iOS Simulator runtime if none is installed yet.
2. **Select a simulator:** with `App.xcodeproj` open, use the scheme/device selector at the top of the Xcode window to choose a simulator device (e.g., "iPhone 16"). The `App` scheme is the one to select — the workspace also lists `CapacitorPushNotifications` and `CapApp-SPM` as build targets/schemes, but those are library dependencies, not the app itself.
3. **Run from Xcode:** press the Run button (▶) or `Cmd+R`. Xcode builds and launches the app in the selected simulator.
4. **Optional CLI validation with `xcodebuild`** (no Xcode GUI needed, useful for scripting or a quick sanity check before opening Xcode):
   ```bash
   cd frontend/ios/App
   xcodebuild -list -project App.xcodeproj
   ```
   This should print `Targets: App`, `Schemes: App, CapacitorPushNotifications, CapApp-SPM` — if it doesn't, something is wrong with the checkout or SPM resolution (see [Troubleshooting](#8-troubleshooting)).

**Simulator validation limitations** (know these before relying on simulator testing alone):
- The Simulator does not exercise real push notifications, real device sensors/GPS accuracy, real camera hardware, or App Store-distribution-specific behavior.
- Simulator builds are typically unsigned/ad-hoc and do not prove code-signing correctness for a real device.
- Performance in the Simulator (especially on Apple Silicon Macs) does not reliably represent performance on physical iPhone hardware, particularly for older/lower-end devices.
- Simulator testing is a good, fast first pass — it is not a substitute for physical device validation before shipping (see [Section 10](#10-final-readiness-status)).

## 5. Apple Developer Configuration

**Nothing in this section is required to build/run in the Simulator.** It only becomes necessary once you need to run on a **physical iPhone**, distribute via **TestFlight**, or submit to the **App Store** — none of which are in scope for this issue.

- **Apple Developer account:** required for any of the above. A free Apple ID can run on your own physical device for a limited time (personal team, 7-day provisioning); a paid Apple Developer Program membership ($99/year) is required for TestFlight and App Store distribution, and for provisioning that doesn't expire weekly.
- **Team selection:** in Xcode, select `App` target → **Signing & Capabilities** tab → choose your Team from the dropdown. This is a per-developer-machine setting, not something to hardcode into the committed project.
- **Bundle ID / app identifier:** already set and committed — `com.yeshmishak.app` (`PRODUCT_BUNDLE_IDENTIFIER` in `App.xcodeproj`, matching Capacitor's `appId` and the Android `applicationId`). Do not change this casually; it must stay registered and consistent across platforms and any Apple Developer portal App ID registration.
- **Signing & Capabilities overview:** this tab in Xcode is where you toggle "Automatically manage signing" (see [Section 6](#6-certificates-preparation)) and add capabilities (push notifications, associated domains, etc.) — none of which are configured in this project yet, per this issue's scope.
- **Certificates/profiles preparation:** covered in detail in [Section 6](#6-certificates-preparation) below.

**Do not commit any Apple Developer secret, private key, certificate (`.p12`, `.cer`), or provisioning profile (`.mobileprovision`) to this repository.** None currently exist in this project, and none should be added without a dedicated, explicitly-scoped issue for signing/distribution setup.

## 6. Certificates Preparation

This section explains the concepts so a future signing-setup issue has clear groundwork — it does not configure any of this now.

- **Development certificate:** a cryptographic identity (public/private key pair) that identifies you or your team to Apple, used to sign builds that can run on a physical device you control. With "Automatically manage signing" enabled in Xcode, this is generated and managed for you per-Team; with manual signing, you generate and download it yourself via the Apple Developer portal.
- **Provisioning profile:** binds together an App ID (bundle identifier), a set of certificates, and (for development profiles) a list of registered device UDIDs, authorizing a specific signed build to run on specific devices. Distribution profiles (for TestFlight/App Store) don't list devices — they authorize distribution through Apple's own channels instead.
- **Automatic vs. manual signing:**
  - *Automatic* (Xcode-managed): Xcode creates/renews certificates and profiles as needed when you select a Team. Simplest for individual development; least CI-friendly, since it can require interactive Apple ID login.
  - *Manual*: you (or CI) explicitly reference a specific certificate and provisioning profile. More setup work, but scriptable and reproducible — the right approach if/when this project sets up signed CI builds or TestFlight automation.
- **What's needed later, not now:**
  - **Physical iPhone testing:** a development certificate + a development provisioning profile that includes that device's UDID (or automatic signing with a Team selected and the device connected/trusted).
  - **TestFlight:** a paid Apple Developer Program membership, a distribution certificate, an App Store distribution provisioning profile, and an App Store Connect app record.
  - **App Store submission:** everything TestFlight needs, plus App Store Connect metadata (screenshots, description, privacy details, etc.) and Apple review.
- **Production signing is explicitly future work.** No certificates, profiles, Team ID, or Apple Developer account credentials are configured in this repository today. This must be set up in a dedicated, separately-scoped issue before any TestFlight/App Store work begins — not folded into environment setup.

## 7. GitHub Actions macOS Validation

`.github/workflows/ios-xcode-validation.yml` runs on a real GitHub-hosted `macos-latest` runner (currently Xcode 16.4) so the team gets Xcode-level validation without every contributor needing a Mac for every change. It triggers on `workflow_dispatch` and on pull requests touching the workflow file, `frontend/ios/**`, `frontend/package.json`, `frontend/package-lock.json`, or `frontend/capacitor.config.ts`.

**What it proves (confirmed by real runs, e.g. [run 28526601772](https://github.com/sandrusipredicts/yesh_mishak/actions/runs/28526601772) and [run 28526407797](https://github.com/sandrusipredicts/yesh_mishak/actions/runs/28526407797), both `completed success`):**
- `npm ci` and `npm run build` succeed on macOS (not just whatever OS a contributor develops on).
- `npx cap sync ios` succeeds and produces a valid `frontend/ios/App/App.xcodeproj`.
- Real Xcode recognizes the project: `xcodebuild -list -project App.xcodeproj` resolves the full SPM package graph and lists the `App`, `CapacitorPushNotifications`, and `CapApp-SPM` schemes.
- An **unsigned** generic-iOS-platform build compiles successfully (`CODE_SIGNING_ALLOWED=NO`, `CODE_SIGNING_REQUIRED=NO`, `CODE_SIGN_IDENTITY=""` — the observed run output ends with the literal `** BUILD SUCCEEDED **`).

**What it does NOT prove:**
- **Real iPhone runtime behavior.** A `generic/platform=iOS` build compiles code; it never boots a simulator or a physical device, so runtime crashes, UI bugs, or plugin behavior differences are not caught by this workflow.
- **App Store or TestFlight readiness.** No signing, certificates, or provisioning profiles are involved — the build is intentionally unsigned.
- **Push notifications.** The `@capacitor/push-notifications` plugin is present as a dependency and successfully compiles, but no APNs configuration, entitlement, or runtime push flow is validated.
- **Apple signing of any kind.** No Apple Developer account, Team, certificate, or profile is used anywhere in this workflow.

See `docs/ios-project-creation.md` for the full history of this workflow's creation and its first passing run's detailed evidence.

## 8. Troubleshooting

| Symptom | Cause / Fix |
| --- | --- |
| `xcodebuild -version` fails or is not found | Xcode Command Line Tools aren't installed/selected. Run `xcode-select --install`, and if you have multiple Xcode versions, `sudo xcode-select --switch /Applications/Xcode.app`. |
| Wrong Node version in use | `frontend/package.json` has no `engines` pin, but CI uses Node 22 — mismatches can cause different `npm ci` resolution or build output. Use `nvm use 22` (or equivalent) before running any `npm`/`npx` command. |
| `npx cap sync ios` fails or seems to do nothing | Make sure `npm run build` was run first — `cap sync` copies `frontend/dist/`, which won't exist (or will be stale) otherwise. Also confirm you're running the command from inside `frontend/`, not the repo root. |
| Xcode shows "Missing package product" or SPM resolution errors | Usually a stale package cache. In Xcode: **File → Packages → Reset Package Caches**, then **File → Packages → Resolve Package Versions**. From the CLI, `xcodebuild -list -project App.xcodeproj` will also trigger resolution and surface the same errors with more detail. |
| Code signing errors when trying to run on a real device or with automatic signing enabled | Expected if no Apple Developer Team is selected yet — see [Section 5](#5-apple-developer-configuration). For Simulator-only work, code signing is not required; make sure you're building for a Simulator destination, not "Any iOS Device" or a connected physical device. |
| No simulators listed / "Simulator not found" | Install a Simulator runtime via Xcode → Settings → Platforms, then restart Xcode. `xcrun simctl list devices` from the CLI shows currently installed simulators. |
| Xcode behaving strangely after switching branches or Xcode versions | Clean derived data: Xcode → Settings → Locations → click the arrow next to "Derived Data" to reveal it in Finder, then delete the `App-*` folder for this project (or the whole `DerivedData` directory). Never commit `DerivedData/` — it's already excluded by `frontend/ios/.gitignore`. |
| Stale/unexpected files under `frontend/ios/App/App/public/` or `capacitor.config.json` mismatched with `capacitor.config.ts` | These are generated by `cap sync` and git-ignored — never hand-edit them. Re-run `npm run build && npx cap sync ios` to regenerate them from the current source. If they still look wrong, check you're on the correct branch and that `frontend/dist/` isn't leftover from an old build (`rm -rf frontend/dist` then rebuild). |
| A Windows-generated `Package.swift` has backslash paths instead of forward slashes | Known artifact if the project was ever synced on Windows (see `docs/ios-project-creation.md`). Fix by running `npx cap sync ios` on macOS/Linux, which regenerates `Package.swift` with correct POSIX paths — confirmed to resolve cleanly in the passing CI runs referenced above. |

## 9. New Developer Checklist

Legend: 🖥️ = requires a Mac · 🤖 = already validated automatically by GitHub Actions on every relevant PR

- [ ] 🤖 Clone the repo, `git checkout main`, `git pull origin main`
- [ ] 🤖 `cd frontend && npm ci`
- [ ] 🤖 `npm run build`
- [ ] 🤖 `npx cap config` — confirm `appId`/`appName`/`webDir`
- [ ] 🤖 `npx cap sync ios`
- [ ] 🖥️ Install Xcode (match `.github/workflows/ios-xcode-validation.yml`'s version where possible — currently Xcode 16.4) and Command Line Tools
- [ ] 🖥️🤖 Open `frontend/ios/App/App.xcodeproj` in Xcode (also validated headlessly in CI via `xcodebuild -list`)
- [ ] 🖥️ Let Xcode resolve the SPM package graph on first open
- [ ] 🖥️ Select the `App` scheme and an installed iOS Simulator device
- [ ] 🖥️🤖 Build (also validated headlessly in CI as an unsigned `generic/platform=iOS` build)
- [ ] 🖥️ Run in the Simulator (`Cmd+R`) — **not yet validated by CI**, since CI only compiles, it doesn't boot a simulator
- [ ] 🖥️ *(Only when needed)* Configure an Apple Developer Team for physical-device signing — see Sections 5–6
- [ ] 🖥️ *(Future issue, not part of this checklist today)* Physical iPhone validation, TestFlight, App Store submission

## 10. Final Readiness Status

| Area | Status |
| --- | --- |
| iOS project generation | **COMPLETE** (ISSUE-206 / `docs/ios-project-creation.md`) — `frontend/ios/` exists, committed, and correctly reflects `capacitor.config.ts` |
| Xcode CI validation | **COMPLETE** — `.github/workflows/ios-xcode-validation.yml` passes on real `macos-latest` runners; project recognized, SPM resolved, unsigned build succeeds |
| Local Mac developer setup | **Documented** (this document) — no local Mac was used to write or verify this guide's commands beyond what CI already exercises; a developer with a Mac should follow Sections 2–4 and report back if any step diverges from what's written here |
| Physical iPhone validation | **Future issue** — not started; requires a real device, a Mac, and at minimum a free Apple ID for development signing |
| Apple signing / TestFlight / App Store | **Future issue** — not started; requires a paid Apple Developer Program membership, dedicated certificate/profile setup, and App Store Connect configuration, all explicitly out of scope for this issue |

## Related Documents

- `docs/ios-project-creation.md` — how `frontend/ios/` was generated, its structure, and the first passing CI run's full evidence.
- `docs/android-development-environment.md` — the Android equivalent of this guide, for reference on conventions.
- `docs/mobile-application-architecture.md` — cross-platform architecture context.
