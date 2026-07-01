# iOS Project Structure Audit

**Issue:** ISSUE-211
**Date:** 2026-07-01
**Audit type:** Structural/documentation review only — no native features added, no signing configured.

## Executive Summary

This audit reviews the iOS Capacitor project (`frontend/ios/`) exactly as it exists on `main` today, before any native iOS feature work begins. It confirms the project structure, Capacitor integration, and build settings are all correctly formed and safe, and that no signing material, secret, or Android file was touched. It also makes two real, previously-undocumented-at-this-level risks visible: **the app icon and splash screen are still Capacitor's stock default placeholder assets**, and **`Info.plist` has no usage-description keys for geolocation**, which the web app already uses in three places (`AddFieldModal.jsx`, `NotificationsModal.jsx`, `MapPage.jsx`) and which will crash the app on iOS the first time a native geolocation permission prompt is requested if not added before that native work begins.

Neither risk blocks continued Simulator-only or CI-only work, and neither is fixed in this issue (out of scope — audit only). Both must be resolved before any release-facing native iOS work (App Store submission, or any change that triggers a native location permission prompt) proceeds.

**Final Audit Decision: PASS WITH RISKS.** The structure is safe and usable for planning further native work, but the risks below — especially the placeholder branding assets and the missing location usage description — must be tracked and resolved before release-facing work.

## 1. Project Structure Review

| Check | Result | Evidence |
| --- | --- | --- |
| `frontend/ios/` exists | PASS | Directory present with full Capacitor-generated structure |
| `frontend/ios/App/App.xcodeproj` exists | PASS | `project.pbxproj` present and well-formed |
| Uses `App.xcodeproj`, not `App.xcworkspace` | **Confirmed correct for this project.** No standalone `frontend/ios/App/App.xcworkspace` with a committed `contents.xcworkspacedata` exists — only the workspace embedded inside `App.xcodeproj/project.xcworkspace` (which itself has no committed `contents.xcworkspacedata`, since that file is only ever produced by CocoaPods' `pod install`, which this project does not use). This was independently re-verified for this audit, not assumed from prior docs. |
| Capacitor 8/SPM structure correct | PASS | `App/CapApp-SPM/Package.swift` exists with a proper `XCLocalSwiftPackageReference "CapApp-SPM"` wired into `project.pbxproj` (confirmed at lines 125-126 and 360-373); this is the real buildable dependency graph, not a CocoaPods `Podfile` (none exists, none is expected) |
| `AppDelegate.swift` | PASS | Present, standard Capacitor bridge delegate, `import Capacitor`, `ApplicationDelegateProxy` wired for URL/Universal Link handling |
| `Info.plist` | PASS (present); see Risk Register for a content gap | Present; `CFBundleDisplayName` correctly set to `Yesh Mishak`; `CFBundleIdentifier` correctly templated to `$(PRODUCT_BUNDLE_IDENTIFIER)` |
| `Main.storyboard` | PASS | Present; correctly hosts `CAPBridgeViewController` from the `Capacitor` module |
| `LaunchScreen.storyboard` | PASS | Present; correctly references the `Splash` image resource (1366×1366 canvas) |
| `Assets.xcassets` | PASS | Present with `AppIcon.appiconset` and `Splash.imageset`; see Assets Review for content risk |
| `Package.swift` | PASS (present); see Risk Register for a path-portability note | Present, correctly declares `capacitor-swift-pm@8.4.1` and the local `CapacitorPushNotifications` plugin dependency |
| `project.pbxproj` | PASS | Present, well-formed, single target (`App`), single scheme group (`App`, `CapacitorPushNotifications`, `CapApp-SPM`) |
| No unexpected build artifacts or user-specific Xcode files committed | PASS | `git ls-files frontend/ios/` returns exactly 19 files, none of which are generated/user-specific — see §5 for the full list and scan |

**Tracked file inventory** (`git ls-files frontend/ios/`, 19 files):
```
frontend/ios/.gitignore
frontend/ios/App/App.xcodeproj/project.pbxproj
frontend/ios/App/App.xcodeproj/project.xcworkspace/xcshareddata/IDEWorkspaceChecks.plist
frontend/ios/App/App/AppDelegate.swift
frontend/ios/App/App/Assets.xcassets/AppIcon.appiconset/AppIcon-512@2x.png
frontend/ios/App/App/Assets.xcassets/AppIcon.appiconset/Contents.json
frontend/ios/App/App/Assets.xcassets/Contents.json
frontend/ios/App/App/Assets.xcassets/Splash.imageset/Contents.json
frontend/ios/App/App/Assets.xcassets/Splash.imageset/splash-2732x2732-1.png
frontend/ios/App/App/Assets.xcassets/Splash.imageset/splash-2732x2732-2.png
frontend/ios/App/App/Assets.xcassets/Splash.imageset/splash-2732x2732.png
frontend/ios/App/App/Base.lproj/LaunchScreen.storyboard
frontend/ios/App/App/Base.lproj/Main.storyboard
frontend/ios/App/App/Info.plist
frontend/ios/App/CapApp-SPM/.gitignore
frontend/ios/App/CapApp-SPM/Package.swift
frontend/ios/App/CapApp-SPM/README.md
frontend/ios/App/CapApp-SPM/Sources/CapApp-SPM/CapApp-SPM.swift
frontend/ios/debug.xcconfig
```

Everything else that exists locally after a build (`App/App/public/*`, `App/App/capacitor.config.json`, `App/App/config.xml`, `capacitor-cordova-ios-plugins/*`) is correctly excluded by `frontend/ios/.gitignore` and `frontend/ios/App/CapApp-SPM/.gitignore` — confirmed by re-running `npx cap sync ios` during this audit and observing `git status` remain clean afterward.

## 2. Assets Review

| Asset | Finding |
| --- | --- |
| App icon (`AppIcon-512@2x.png`, 1024×1024, RGB no alpha — correct format for an App Store icon) | **Still Capacitor's stock default placeholder** — a blue diagonal "X" logo on a light grid background. Visually confirmed by opening the committed file. This is the well-known default template icon Capacitor's `cap add ios` generates, not a "Yesh Mishak" branded icon. |
| Splash screen (`splash-2732x2732*.png`, all three density variants, correctly declared in `Contents.json` for 1x/2x/3x `universal` idiom) | **Also still the stock Capacitor default** — a small blue "X" mark centered on a plain white background. Visually confirmed. |
| `LaunchScreen.storyboard` wiring | Correctly references the `Splash` asset; the *mechanism* is fine, only the *content* is a placeholder. |
| `AppIcon.appiconset/Contents.json` | Uses the modern single-size (`1024x1024`, `idiom: universal`) format Xcode 14+ expects — structurally correct, not something to change. |

**Risk:** shipping either the placeholder icon or splash screen to TestFlight or the App Store would present the app under a generic template identity rather than the product's real branding, and is very likely to draw App Store review scrutiny for looking unfinished. This is a real, visible risk that must be resolved before any release-facing milestone — but redesigning/generating branded assets is explicitly out of scope for this audit issue.

## 3. Capacitor Integration Review

| Check | Result | Evidence |
| --- | --- | --- |
| `frontend/capacitor.config.ts` appId | PASS | `appId: 'com.yeshmishak.app'` — matches the approved Bundle Identifier from ISSUE-208/209 |
| `frontend/capacitor.config.ts` appName | PASS | `appName: 'Yesh Mishak'` — matches `Info.plist`'s `CFBundleDisplayName` |
| `frontend/capacitor.config.ts` webDir | PASS | `webDir: 'dist'` — matches the Vite build output directory |
| Generated iOS `capacitor.config.json` matches source config | PASS | Regenerated fresh during this audit (`npx cap sync ios`): `{"appId":"com.yeshmishak.app","appName":"Yesh Mishak","webDir":"dist","packageClassList":["PushNotificationsPlugin"]}` — this file is git-ignored (correctly; it's a build artifact, not source) |
| `npx cap config` succeeds | PASS | Ran fresh during this audit; output confirms the three values above |
| `npx cap sync ios` succeeds | PASS | Ran fresh during this audit; assets copied, `Package.swift` rewritten, `@capacitor/push-notifications@8.1.1` plugin detected; zero errors |
| No stale/Windows-specific generated path issue remains uncorrected | **Present but self-healing — see Risk Register** | The committed `App/CapApp-SPM/Package.swift` still contains a Windows-style backslash path (`path: "..\..\..\node_modules\@capacitor\push-notifications"`), an artifact of having been generated on a Windows machine in ISSUE-206. This was directly proven non-blocking: a fresh GitHub Actions macOS run triggered during this audit (`workflow_dispatch` on `main`, run [28535451568](https://github.com/sandrusipredicts/yesh_mishak/actions/runs/28535451568)) shows the CI's own `npx cap sync ios` step regenerates this file correctly on macOS before the build step runs, and the subsequent unsigned build completed with `** BUILD SUCCEEDED **`. |
| SPM package resolution is expected/correct | PASS | `project.pbxproj` has a proper `XCLocalSwiftPackageReference "CapApp-SPM"` (lines 360-365) and `XCSwiftPackageProductDependency` (lines 367-372); the fresh CI run's `xcodebuild -list` step successfully resolved the full package graph (fetching `capacitor-swift-pm` from GitHub and linking `CapApp-SPM`/`CapacitorPushNotifications` from their local paths) and listed schemes `App`, `CapacitorPushNotifications`, `CapApp-SPM` |

## 4. Build Settings Review

Inspected directly in `frontend/ios/App/App.xcodeproj/project.pbxproj`.

| Setting | Value | Assessment |
| --- | --- | --- |
| `PRODUCT_BUNDLE_IDENTIFIER` | `com.yeshmishak.app` (2 occurrences: target Debug and Release configurations) | **Consistent**, matches `capacitor.config.ts` and the approved ISSUE-208/209 identifier exactly |
| `CODE_SIGN_STYLE` | `Automatic` (target Debug and Release) | This is Capacitor's default template value, not evidence that signing is actually configured — see next row |
| `DEVELOPMENT_TEAM` | **Absent** (no occurrences anywhere in the file) | **Confirms development signing is correctly NOT falsely represented as complete.** No Team ID is committed, consistent with ISSUE-209's strategy (no organization Apple Developer team is documented) and ISSUE-210's BLOCKED status. |
| `PROVISIONING_PROFILE` / `PROVISIONING_PROFILE_SPECIFIER` | **Absent** | No stale or hardcoded provisioning profile reference exists. |
| `TargetAttributes.ProvisioningStyle` | `Automatic` | Standard inert Xcode template boilerplate from the original scaffold (`CreatedOnToolsVersion = 9.2`); does not itself enable signing without a Team ID. |
| `CODE_SIGN_IDENTITY` | `"iPhone Developer"` (project-level Debug/Release only, lines 214 and 271) | Legacy default string inherited from the original Xcode template, overridden at the target level by `CODE_SIGN_STYLE = Automatic`. This is inert boilerplate, not an active signing configuration — it does not by itself let a build actually sign anything without a selected Team. |
| `IPHONEOS_DEPLOYMENT_TARGET` | `15.0` (all 4 occurrences: project + target, Debug + Release) | Consistent everywhere. |
| `MARKETING_VERSION` / `CURRENT_PROJECT_VERSION` | `1.0` / `1` | Default initial version numbers; expected and fine for pre-release status. |
| `SWIFT_VERSION` | `5.0` | Consistent, current. |
| `ASSETCATALOG_COMPILER_APPICON_NAME` | `AppIcon` | Correctly references the (placeholder) asset catalog entry. |

**No hardcoded personal Team ID exists anywhere** — confirmed by the absence of `DEVELOPMENT_TEAM` in the file, matching the "no false signing completeness" requirement exactly.

**Build settings are compatible with the unsigned CI build**, confirmed by the fresh `workflow_dispatch` run triggered during this audit (run 28535451568, `completed success`, `** BUILD SUCCEEDED **` for `CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO CODE_SIGN_IDENTITY=""`).

## 5. Signing Status Reminder

**Unchanged from ISSUE-209/210 — restated here for visibility, not re-decided.**

- Development signing: **BLOCKED** (per `docs/ios-code-signing-configuration.md` — no macOS/Xcode/Apple Developer team/physical iPhone were available when ISSUE-210 was attempted).
- The GitHub Actions `iOS Xcode Validation` workflow passing an **unsigned** build (confirmed fresh in this audit) proves the Xcode project compiles and its dependency graph resolves on real macOS/Xcode tooling. **It does not prove physical-device readiness, TestFlight readiness, or App Store readiness** — those require real Apple signing credentials no CI runner can substitute for.
- This audit does not change, advance, or attempt to resolve that BLOCKED status. It is restated here only so a reader of this structure audit does not mistake "CI passes" for "signing is configured."

## 6. Git / Repo Hygiene Review

All required scans were run fresh during this audit.

```bash
git status                          # clean, no changes, before this issue's own doc commit
git diff --stat                     # empty
git status --ignored                # only pre-existing, unrelated ignored paths (.env, caches, venvs, logs)
git ls-files | grep -Ei "p12|mobileprovision|cer|certificate|provision|AuthKey|DerivedData|xcuserdata|xcuserstate|\.env|secret|private"
  → backend/.env.example, backend/.env.staging.example,
    docs/device-compatibility-certification-checklist.md,
    docs/device-compatibility-certification-review.md,
    frontend/.env, frontend/.env.android.example,
    frontend/.env.example, frontend/.env.staging.example
  (all pre-existing, safe, already-approved template/placeholder files —
   none contain real Apple signing material; the two "certificate" doc
   matches are Android device-compatibility docs, unrelated to iOS signing)
find . -iname "*.p12" -o -iname "*.mobileprovision" -o -iname "*.cer" -o -iname "AuthKey_*.p8" -o -iname "*.xcuserstate"
  → no results
find . -type d \( -iname "DerivedData" -o -iname "xcuserdata" \)
  → no results
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
| `.env` (real, secret-bearing) committed | **No** — only pre-existing, already-approved placeholder `.env.example`/`.env.android.example`/`.env.staging.example` templates and the tracked `frontend/.env` (which carries `skip-worktree` and only a safe placeholder value, established safe in prior issues) |
| Private keys/secrets committed | **No** |
| Android files changed | **No** — `git diff --stat -- frontend/android` is empty |
| Build artifacts committed | **No** — `App/App/public/*`, generated `capacitor.config.json`/`config.xml`, and `capacitor-cordova-ios-plugins/*` all remain correctly git-ignored after a fresh local `npx cap sync ios` |

## 7. Risk Register

| Risk | Severity | Evidence | Impact | Recommended Follow-up | Blocks Native Features? |
| --- | --- | --- | --- | --- | --- |
| App icon and splash screen are Capacitor's stock default placeholder assets, not "Yesh Mishak" branding | Medium | Visually confirmed: `AppIcon-512@2x.png` and `splash-2732x2732*.png` both show the generic blue "X" template graphic | Shipping to TestFlight/App Store under a generic template identity looks unfinished and risks review friction; internal Simulator/dev use is unaffected | Dedicated design/asset issue to generate and commit real branded icon and splash assets before any release-facing milestone | No — safe for continued Simulator/CI/dev work; blocks release readiness only |
| `Info.plist` has no `NSLocationWhenInUseUsageDescription` (or related) usage-description key | High (for future native work), None (today) | `Info.plist` inspected directly — no `NS*UsageDescription` keys present at all; the web app already calls `navigator.geolocation`/`getCurrentPosition` in `frontend/src/components/AddFieldModal.jsx`, `frontend/src/components/NotificationsModal.jsx`, and `frontend/src/pages/MapPage.jsx` | iOS terminates an app immediately (no dialog, no error message a user could act on) if it requests a protected permission without a corresponding usage-description string in `Info.plist`. Any future native geolocation integration (Capacitor Geolocation plugin, or the WebView requesting location) will crash on first use until this is added. | Add `NSLocationWhenInUseUsageDescription` (and `NSLocationAlwaysAndWhenInUseUsageDescription` if background location is ever needed) to `Info.plist` as part of the first issue that wires up native/WebView geolocation on iOS — not before it's actually needed, to avoid an unused permission prompt | **Yes** — must be resolved before any geolocation-triggering native work ships, or it will crash |
| `frontend/ios/App/CapApp-SPM/Package.swift`'s committed local package path uses Windows-style backslashes | Low | Directly inspected: `path: "..\..\..\node_modules\@capacitor\push-notifications"` | Proven non-blocking: a fresh macOS CI run regenerates this file correctly via `npx cap sync ios` before building, and the build succeeds. Only a theoretical risk if a developer opens the committed file in Xcode on macOS *without* first running `npx cap sync ios` on that machine. | Document as a known step in onboarding (already covered in `docs/ios-development-environment.md`'s workflow, which always runs `cap sync ios` before opening Xcode); no code change needed | No |
| Development signing is not configured (`CODE_SIGN_STYLE = Automatic`, no `DEVELOPMENT_TEAM`) | Informational (by design) | Confirmed absent in `project.pbxproj`; matches ISSUE-209/210's documented BLOCKED status exactly | None today — Simulator and unsigned CI builds are unaffected. Physical-device, TestFlight, and App Store work remain blocked until an organization Apple Developer team is provisioned. | Tracked by ISSUE-209/210 already; no new follow-up needed from this audit | No — blocks only physical-device/distribution work, already known |
| No `Podfile`/CocoaPods present (SPM-only) | Informational | Confirmed by design — Capacitor 8 default; `capacitor-cordova-ios-plugins/CordovaPluginsResources.podspec` exists only as a Cordova-compatibility artifact, not an active CocoaPods integration | None — this is the correct, modern Capacitor 8 default, not a gap | None | No |

## 8. Required Follow-up Issues

1. **iOS branding assets.** Generate and commit a real "Yesh Mishak" app icon and splash screen to replace the Capacitor stock defaults, before any TestFlight/App Store milestone.
2. **iOS location usage description.** Add `NSLocationWhenInUseUsageDescription` (and `NSLocationAlwaysAndWhenInUseUsageDescription` if needed) to `Info.plist` as part of the specific issue that first wires up native/WebView geolocation on iOS — this audit intentionally does not add it now, since the permission isn't requested by anything in the current native shell yet, and adding an unused permission string prematurely is not warranted.
3. Continue to track physical-device signing, TestFlight, and App Store signing as BLOCKED/future work exactly as ISSUE-209/210 already document — no change from this audit.

## 9. Final Audit Decision

**PASS WITH RISKS.**

The iOS project structure is correctly formed, matches the approved Bundle Identifier and Capacitor configuration exactly, contains no signing material or secrets, has not touched any Android file, and passes a freshly-triggered, real macOS/Xcode CI build (`workflow_dispatch` run [28535451568](https://github.com/sandrusipredicts/yesh_mishak/actions/runs/28535451568), `completed success`, unsigned build `** BUILD SUCCEEDED **`). The structure is safe to continue building future native work on top of.

Two risks are now explicitly visible and tracked (placeholder branding assets; missing location usage description) that were previously only implicit in the generated project, not documented at this level of specificity. Neither blocks continued Simulator-only or CI-only development. The location usage-description gap **does** block any future work that triggers a native geolocation permission prompt, and the placeholder branding assets **do** block release-facing milestones (TestFlight/App Store) — both are called out above with explicit follow-up recommendations rather than fixed in this audit, consistent with this issue's audit-only scope.

## 10. Files Changed in This Issue

- `docs/ios-project-structure-audit.md` (this file, new)
- `docs/product-decisions.md` (decision entry appended)

No native iOS file, Xcode project file, workflow file, or Android file was created, modified, or deleted.
