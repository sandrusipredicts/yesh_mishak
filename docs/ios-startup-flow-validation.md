# iOS Startup Flow Validation

**Issue:** ISSUE-213
**Date:** 2026-07-01
**Prerequisite confirmed:** ISSUE-212 (PR [#777](https://github.com/sandrusipredicts/yesh_mishak/pull/777)) is merged into `main` (merge commit `9bd2c93`).

## Executive Summary

This goes beyond ISSUE-212's "does it build/install/launch and stay alive" check to prove the app's actual **startup flow** works correctly on a real macOS/Xcode iOS Simulator: the launch screen mechanism completes, the Capacitor WebView genuinely initializes and loads real content, the initial route renders visually correct with no crash, and the configured backend is reachable with no CORS or Mixed Content blocker.

A new workflow, `.github/workflows/ios-startup-flow-validation.yml`, was created and actually run (not just written) on a real `macos-latest` GitHub Actions runner. Run [28544475969](https://github.com/sandrusipredicts/yesh_mishak/actions/runs/28544475969) (triggered via the `pull_request` event on PR [#778](https://github.com/sandrusipredicts/yesh_mishak/pull/778)) `completed success` in 6m36s with all 24 steps green. The two previously-existing iOS workflows (`iOS Xcode Validation`, `iOS Debug Build Validation`) were also re-triggered by the same PR (since it touches `frontend/package.json`, a shared trigger path) and both remained `completed success`, confirming no regression.

**Strongest evidence: a real post-launch screenshot downloaded directly from the CI run's artifact shows the app's actual React UI rendered correctly** — the language-selection screen (`עברית` / `English`), with correct Hebrew RTL text rendering, correct layout, and no blank/white/crashed screen. This is the app's genuine first route (`App.jsx`: `if (!isLanguageSelected) return <LanguageSelectionScreen />`), confirming initial routing worked exactly as the source code specifies.

**Final decision: PASS.**

## Validation Environment

| Item | Value |
| --- | --- |
| Runner | GitHub Actions `macos-latest` |
| Xcode version | 16.4 (confirmed from build tool paths in the log) |
| Simulator selected | `iPhone 17 Pro` (UDID `D4E7F36F-A62E-458E-A0A4-0A5DB6256FB3`) — selected dynamically, not hardcoded (see below) |
| Bundle Identifier | `com.yeshmishak.app` (unchanged, approved value from ISSUE-208/209) |
| API target | `https://yeshmishak-production.up.railway.app` — the real, permanent, live production backend, baked in via a new `npm run build:ios` (`vite build --mode ios`) reading a git-ignored, CI-only `frontend/.env.ios` written inline in the workflow, mirroring the proven Android `build:android` pattern |

**Simulator selection note:** the runner offered several iPhone models (`iPhone 17 Pro`, plus others visible in the `xcrun simctl list devices available` step output). The workflow's dynamic-selection logic (`xcrun simctl list devices available -j | jq -r '[.devices[][] | select(.isAvailable == true and (.name | startswith("iPhone")))][0].udid'`) picked `iPhone 17 Pro` — a newer model than ISSUE-212's run picked (`iPhone 16 Pro`), on the same runner image label (`macos-latest`), just at a later point in time. This confirms the "never hardcode a specific device" design decision from ISSUE-212 continues to pay off as GitHub's runner images evolve.

## Workflow Used

`.github/workflows/ios-startup-flow-validation.yml` (new in this issue). Steps, in order: checkout, Node 22 setup, `npm ci`, write ephemeral `.env.ios`, `npm run build:ios`, `npx cap sync ios`, list available simulators, dynamically select an iPhone simulator, build for the Simulator SDK (unsigned), locate the built `.app`, boot the simulator, install the app, start log capture, launch by bundle ID, wait 10s for startup to settle, confirm the process is still running, capture a post-launch screenshot, stop log capture and print it, scan the log for fatal indicators, run a separate backend CORS/reachability check, upload the log and screenshot as build artifacts.

## Build Result

**PASS.** `npm run build:ios` succeeded (Vite, iOS mode). The subsequent Xcode Simulator build ended with the literal output:

```
** BUILD SUCCEEDED **
```

Built app located at `DerivedData/Build/Products/Debug-iphonesimulator/App.app`.

## Simulator Boot Result

**PASS.** `xcrun simctl boot` + `xcrun simctl bootstatus -b` completed with no error; the step is green in the run.

## App Install Result

**PASS.** `xcrun simctl install <udid> App.app` completed with no error output and a zero exit code.

## App Launch Result

**PASS.** `xcrun simctl launch <udid> com.yeshmishak.app` returned:

```
com.yeshmishak.app: 22217
```

confirming the app launched and was assigned process ID 22217. After a 10-second wait, `xcrun simctl spawn <udid> launchctl list | grep -F "com.yeshmishak.app"` returned:

```
22217	0	UIKitApplication:com.yeshmishak.app[93c2][rb-legacy]
```

— exit status `0`, process still alive. No immediate crash.

## Launch Screen Evidence / Limitation

**Structural mechanism confirmed (ISSUE-211 audit); direct visual capture of the splash itself was not attempted.** `LaunchScreen.storyboard` was already confirmed correctly wired to the `Splash` image asset in ISSUE-211's structure audit. This issue's screenshot was deliberately taken after a 10-second settle delay specifically to capture the app *past* the launch screen, in its fully-loaded state — which is itself indirect but strong evidence the launch screen completed normally and did not hang: if the launch screen had frozen or the app had stalled during native startup, the screenshot would show the splash image (or a blank/frozen native view) instead of real rendered web content, and the WebKit page-load-lifecycle log evidence below would be absent entirely. Capturing the splash screen itself mid-transition would require a screenshot taken within roughly the first second after launch, which was not attempted in this run; this is noted as a minor limitation, not a failure — the more important question ("does startup make it past the launch screen into working content") is answered conclusively yes.

## WebView Initialization Evidence

**PASS, directly confirmed via real WebKit process/page lifecycle log lines**, captured by `xcrun simctl spawn <udid> log stream --predicate 'process == "App"'` and uploaded as the `ios-startup-log` artifact. Key excerpts, in chronological order:

```
[com.apple.WebKit:Loading] WebPageProxy::constructor, site isolation enabled 0
[com.apple.WebKit:Process] WebProcessProxy::addExistingWebPage: webPage=..., pageProxyID=7, webPageID=8
[com.apple.WebKit:Loading] WebPageProxy::loadRequest:
[com.apple.WebKit:Loading] WebPageProxy::loadRequestWithNavigationShared:
[com.apple.WebKit:Loading] WebPageProxy::didStartProvisionalLoadForFrame: frameID=8589934593, isMainFrame=1
[com.apple.WebKit:ResourceLoading] FrameLoader::transitionToCommitted: Clearing provisional document loader
[com.apple.WebKit:Loading] WebPageProxy::didCommitLoadForFrame: frameID=8589934593, isMainFrame=1
[com.apple.WebKit:ResourceLoading] SubResourceLoader::didFinishLoading  (×3, distinct resourceIDs 20/27/28)
[com.apple.WebKit:ResourceLoading] FrameLoader::checkLoadCompleteForThisFrame: Finished frame load
[com.apple.WebKit:Loading] WebPageProxy::didFinishLoadForFrame: frameID=8589934593, isMainFrame=1
```

This is the complete, real WebKit page-load lifecycle: a navigation was requested, started, committed, its subresources (the built JS/CSS bundle and other static assets) finished loading individually, and the main frame reported a finished load with no interruption or error logged in between. No fallback to an error page, no `WKNavigationDelegate` failure callback pattern, and no fatal indicator anywhere in this sequence.

## API Connectivity Evidence

**Two-part evidence, as anticipated by this issue's own instructions**, since the app requires login before making any automatic backend API call:

1. **In-app network evidence: none automatically visible in this run, and this is expected, not a gap.** A fresh Simulator install with no persisted session lands on the language-selection screen (confirmed by the screenshot below), then would proceed to the login screen — neither of which calls the backend automatically. The `process == "App"` log filter shows real WebView/page-load activity but does not expose granular per-request network trace detail at the level curl would (WebKit's own network logging is more limited than what was observed for Android's Chrome-based WebView in earlier issues). No CORS or Mixed Content error appears anywhere in the captured log, which is itself meaningful: if the app *had* attempted a request and been blocked, that failure is one of this workflow's explicit hard-fail scan patterns (see below) and would have failed the run.
2. **Backend reachability + CORS evidence (safe, read-only, clearly separate from in-app proof):** a dedicated workflow step ran, from the same CI job, immediately after the Simulator checks:
   ```
   GET https://yeshmishak-production.up.railway.app/  → HTTP 200
   OPTIONS https://yeshmishak-production.up.railway.app/fields/
     Origin: https://localhost
     → HTTP/2 200
     → access-control-allow-origin: https://localhost
   ```
   This confirms the exact backend and exact origin (`https://localhost`, the Capacitor WebView's real origin) the app would use are both reachable and correctly CORS-configured, **without** mutating any data (`GET /` and `OPTIONS /fields/` only — no write endpoint was called).

**This is explicitly backend/API reachability evidence, not in-app network proof**, per this issue's own required framing.

## Initial Routing Evidence

**PASS, confirmed visually.** A screenshot was captured via `xcrun simctl io <udid> screenshot` after the 10-second settle wait and uploaded as the `ios-startup-screenshot` artifact. It was downloaded and reviewed directly for this report. It shows:

- A correctly rendered card titled "Choose your language" / "You can change this later from Settings."
- Two language options: "עברית — Use Hebrew and right-to-left layout" (rendered in real, correctly-shaped Hebrew script) and "English — Use English and left-to-right layout".
- Correct fonts, correct card/shadow styling, correct status bar, no layout corruption, no blank/white screen, no error overlay.

This is exactly `frontend/src/App.jsx`'s actual first conditional route for a fresh install: `if (!isLanguageSelected) return <LanguageSelectionScreen onSelected={...} />`. The screenshot is not a generic "the WebView is showing something" result — it is a precise visual match for this specific app's real first-run UI, including correct RTL Hebrew text shaping, which would not render correctly if the WebView, fonts, or React app had failed to initialize properly.

## Logs Reviewed

- Full `ios_startup_log.txt` (captured via `log stream --predicate 'process == "App"'` for the duration of boot → launch → 10s settle), printed inline in the "Stop log capture and print captured logs" step and uploaded as the `ios-startup-log` artifact.
- The "Select an available iPhone simulator" and "Show available simulators" step output, confirming the real device pool available on the runner.
- The "Backend API reachability + CORS check" step output (full HTTP response headers).

## Crash/Error Scan Result

**PASS — zero matches for any hard-fail pattern.** The workflow's dedicated scan step searched the captured log for:

```
Fatal error|Terminating app due to uncaught exception|SIGABRT|EXC_BAD_ACCESS|NSInvalidArgumentException|Mixed Content|blocked by CORS|WebView failed
```

Output: `No hard-fail patterns found.`

A separate, deliberately non-blocking watch pattern (`Could not load`) was also scanned, since that phrase is sometimes legitimately benign (e.g. an optional/missing resource that doesn't affect functionality) and this issue's instructions explicitly warn against failing on harmless Apple Simulator noise. Output: `(none found)` — so in this specific run there was nothing ambiguous to document either; the log was entirely clean.

## Known Limitations

- **This validates iOS Simulator startup, not physical iPhone startup.** Simulator behavior does not exercise real hardware, real sensors, or code-signing-dependent behavior.
- **Physical iPhone remains BLOCKED by ISSUE-210 signing prerequisites** (no macOS/Xcode locally, no organization Apple Developer team, no physical iPhone available in this environment) — unchanged by this issue, not attempted, not implied by this Simulator success.
- **This is not full end-to-end auth testing.** No login was attempted; the app was validated up to and including its first unauthenticated route, per this issue's explicit scope ("The goal is not to test full user auth").
- **This is not TestFlight/App Store validation.** No signing, distribution, or App Store Connect process was exercised.
- **This is not push notification validation.** No APNs, Firebase, or push flow was exercised; `@capacitor/push-notifications` compiles as a dependency but was not functionally tested.
- **In-app network request proof is indirect, not direct**, for the reason explained above (the app's first two screens don't call the backend automatically) — mitigated by the separate, clearly-labeled curl-based reachability/CORS check.
- **The launch screen splash itself was not directly screenshotted** (only the post-settle state was); its correct wiring was independently confirmed structurally in ISSUE-211, and its successful completion is strongly implied (not directly captured) by the clean transition to fully-rendered content.

## Final Decision

**PASS.**

All required startup-flow areas were validated with real, observed evidence from an actual GitHub Actions macOS Simulator run — not assumptions: the app builds, installs, boots, and launches; the Capacitor WebView genuinely initializes and completes a full page-load lifecycle with zero fatal, CORS, or Mixed Content indicators; the initial route renders visually correct (confirmed by direct screenshot review, showing the app's real first-run language-selection UI with correct Hebrew RTL rendering); and the configured production backend is reachable with correct CORS for the Capacitor origin. The two pre-existing iOS workflows also remained green throughout. Physical iPhone validation remains explicitly out of scope and BLOCKED per ISSUE-210, as documented above — this does not reduce the PASS decision for the Simulator-scoped goal this issue set out to validate.

## Files Changed in This Issue

- `.github/workflows/ios-startup-flow-validation.yml` (new — Simulator startup-flow validation CI workflow)
- `frontend/package.json` (added `build:ios` script, mirroring `build:android`)
- `frontend/.env.ios.example` (new — safe HTTPS-only template, mirrors `.env.android.example`)
- `.gitignore` (added `.env.ios`)
- `docs/ios-startup-flow-validation.md` (this file, new)
- `docs/product-decisions.md` (decision entry appended)

No native iOS project file, Xcode signing configuration, or Android file was created, modified, or deleted.
