# Android Project Readiness Review

## Executive Summary

**Update (ISSUE-207, 2026-07-01): Android Foundation is now COMPLETE.** ISSUE-206 fixed both root blockers this review originally found (backend CORS and the HTTP/HTTPS scheme mismatch). This document has been re-validated end-to-end with fresh commands against the current `main` branch and against the app's **real, permanent, live production backend** (`https://yeshmishak-production.up.railway.app`) — not a temporary tunnel — superseding the original NO-GO below. See the "ISSUE-207 Re-validation" evidence added to the API Communication Status section and the updated Final Decision at the bottom of this document. The original ISSUE-205 findings are preserved below for traceability.

---

This review re-verifies, with fresh commands run directly against the current `main` branch, every gate required before Android foundation work can be considered complete and the team moves on to iOS: project/config integrity, the debug build, the startup flow, and API communication. It supersedes no prior document — it re-confirms ISSUE-197 through ISSUE-204 and the subsequent field-creation bug fix are all still true on disk today, and it adds one new, non-blocking observation (a safe-area CSS console error) that had not been called out before.

Three of the four required gates pass on fresh evidence: **Android Project Status**, **Debug Build Status**, and **Startup Flow Status**. The fourth, **API Communication Status**, remains **NO-GO**, for exactly the two reasons already root-caused in ISSUE-201/202: the backend does not authorize the Capacitor origin (`https://localhost`) for CORS, and the configured API target is plain HTTP while the WebView is HTTPS, which triggers Mixed Content blocking independent of CORS. Neither blocker has been fixed yet — ISSUE-203 intentionally implemented only the Network Security Config half of the ISSUE-202 policy, and left the CORS allowlist and HTTPS API target as explicit follow-up work, which is still outstanding as of this review.

**Original decision (ISSUE-205, now superseded): NO-GO for full Android Foundation completion.** The native/build/startup foundation is solid and reproducible. The project cannot be marked complete while real API calls (login, fields, games, notifications) are blocked end-to-end. No code, config, or build file was changed to produce this review — this is a verification/evidence document only.

## Android Project Status: PASS

Verified directly against the current repository state, not assumed from prior docs:

| Item | Expected | Found | Result |
| --- | --- | --- | --- |
| Capacitor `appId` | `com.yeshmishak.app` | `com.yeshmishak.app` (`frontend/capacitor.config.ts`) | PASS |
| Capacitor `appName` | `Yesh Mishak` | `Yesh Mishak` | PASS |
| Capacitor `webDir` | `dist` | `dist` | PASS |
| Gradle `namespace` | `com.yeshmishak.app` | `com.yeshmishak.app` (`android/app/build.gradle`) | PASS |
| Gradle `applicationId` | `com.yeshmishak.app` | `com.yeshmishak.app` | PASS |
| Native Java package path | `com/yeshmishak/app/` | `android/app/src/main/java/com/yeshmishak/app/MainActivity.java` | PASS |
| `AndroidManifest.xml` `package` attribute (source) | absent (owned by Gradle) | absent — confirmed via `grep` on the source manifest | PASS |
| Merged manifest `networkSecurityConfig` | `@xml/network_security_config` | present, confirmed in `app/build/intermediates/merged_manifest/debug/processDebugMainManifest/AndroidManifest.xml` | PASS |
| Merged manifest `usesCleartextTraffic` | absent (default deny) | absent | PASS |
| `network_security_config.xml` | `cleartextTrafficPermitted="false"`, system CAs only | confirmed unchanged since ISSUE-203, no cleartext exception, no user CA trust, no pinning | PASS |
| `minSdkVersion` / `compileSdkVersion` / `targetSdkVersion` | consistent, modern | `24` / `36` / `36` (`android/variables.gradle`) | PASS |
| `cap doctor` | Android healthy | `[success] Android looking great!` | PASS |
| Frontend lint | clean | `npx eslint .` — no errors, no warnings | PASS |

No Android native file, Gradle file, manifest, or Capacitor config was modified to produce this result — all of the above was read directly from the repository as it exists on `main`.

## Debug Build Status: PASS

| Item | Result |
| --- | --- |
| System default JDK | `26.0.1` (Oracle) — confirmed still incompatible |
| Required JDK | Android Studio JBR `21.0.10`, at `C:\Program Files\Android\Android Studio\jbr` |
| `assembleDebug` with system JDK 26 | **FAILS**, reproduced fresh (see Commands Executed) — same `androidJdkImage`/`jlink.exe` failure as ISSUE-201/203 |
| `assembleDebug` with JBR JDK 21, clean build | **BUILD SUCCESSFUL** in 35s, 130 actionable tasks |
| APK produced | `frontend/android/app/build/outputs/apk/debug/app-debug.apk`, 6,237,267 bytes |
| APK SHA-256 | `efc6e0f96b00e08063ff03342f608407f27a6abbd1046ae260bc6a9910fa1f2a` |
| `flatDir` warning | Present twice per build, from generated Capacitor/Cordova config — confirmed non-blocking, build still succeeds |
| `:app:processDebugMainManifest` | `BUILD SUCCESSFUL`, manifest merges cleanly |

The Kotlin stdlib instrumentation/androidTest conflict documented in ISSUE-197/204 was not re-triggered in this review because `assembleDebug` — the required debug build gate per this issue's explicit scope — does not build the instrumentation APK. Per ISSUE-204's classification guidance, this remains a separately tracked, non-blocking item and does not affect this gate.

## Startup Flow Status: PASS

Re-validated on a physical device rather than assumed from ISSUE-200's prior report:

| Item | Result |
| --- | --- |
| Device | Samsung SM-S928B, serial `RFCXA0GMVJA`, Android 16 |
| Fresh install (`adb install -r`) | `Success` |
| Cold launch (`force-stop` + `monkey` launcher intent) | `MainActivity` became `ResumedActivity`; PID `31227` stayed alive through the observation window |
| `AndroidRuntime` fatal exception / `FATAL EXCEPTION` | **0 occurrences** in the full logcat capture |
| Bundled asset load | Login screen rendered fully (Hebrew UI, login/register tabs, username/password fields, login button) — confirmed via device screenshot |
| Known non-blocking issue (carried over) | Google Sign-In load error still visible on screen, as in ISSUE-200/201; tracked separately under OAuth work |
| **New non-blocking observation** | `E/Capacitor/Console`: `Error injecting safe area CSS: TypeError: Cannot read properties of null (reading 'style')`, logged 3 times immediately on cold start. Did not prevent rendering, did not crash the app, and the login screen was fully interactive in the follow-up screenshot. Not previously called out in ISSUE-200/201; recorded here as a new known issue for future investigation (see Known Issues below). |

No native crash, no blank screen, no routing failure. Startup remains healthy exactly as ISSUE-200 concluded, with one new minor console error identified.

## API Communication Status: PASS (as of ISSUE-207; historical NO-GO below)

### ISSUE-207 Re-validation (2026-07-01) — PASS, against the real permanent production backend

ISSUE-206 fixed both root causes identified below. This section re-runs the same checks with fresh commands, this time against the app's actual, permanent, live production backend rather than a temporary local tunnel, and adds real physical-device evidence.

**Discovering the real permanent backend.** Neither documented candidate URL was actually live: `frontend/.env.staging.example`'s staging URL and the guessed production URL from `docs/production-config-readiness.md` both resolve only to Railway's default "no active deployment" placeholder page (`200 OK`, but the generic Railway ASCII-art page, not the app). The real production API URL was recovered by downloading the live `https://yesh-mishak.vercel.app` production web app's own JS bundle and extracting the `railway.app` URL it actually calls: **`https://yeshmishak-production.up.railway.app`**. This returned `{"status":"ok"}` — the app's real root endpoint — confirming it is genuinely live.

| Item | Result |
| --- | --- |
| Backend CORS fix present on `main` | `backend/app/main.py` unconditionally appends `https://localhost` to `cors_origins`, confirmed at commit `ab6f8d1` |
| **Real production backend already has the fix deployed** | Fresh CORS preflight against `https://yeshmishak-production.up.railway.app` for all 6 endpoints (`/auth/login`, `/auth/google`, `/fields/`, `/games/active`, `/notifications`, `/notifications/push-token`) returns `HTTP 200` with `access-control-allow-origin: https://localhost` — confirming Railway auto-deploys from `main` and production is already correctly configured, with **no manual deployment step needed** |
| Android build environment fix present | `frontend/package.json` has `build:android` (`vite build --mode android`); `frontend/.env.android.example` documents an HTTPS-only target (updated in this issue to reference the confirmed-live production URL); `.env.android` is git-ignored |
| `npm run build:android` (pointed at the real production URL) | Built successfully; verified the output bundle contains `https://yeshmishak-production.up.railway.app` and **zero** occurrences of any `192.168.*` LAN address or `http://` API target |
| `npx cap sync android` / `npx cap doctor` | Sync succeeded, plugin detected; `cap doctor` reported `Android looking great! 👌` |
| `gradlew assembleDebug` (Android Studio JBR Java 21) | `BUILD SUCCESSFUL` in 18s |
| Install/launch on physical device (Samsung SM-S928B) | Installed, launched, `MainActivity` resumed with a live PID |
| **Real API request from the installed app against real production** | The app rendered the map with **live production field markers** near Yeruham, sourced from `GET /fields/` — a public, unauthenticated endpoint, so this is unambiguous proof the request reached and was answered by the real production backend, not a cached or local fallback. Tapping the notifications bell also opened a working notifications inbox with no error state. |
| Logcat across the full device session (10,946 lines) | **Zero** `FATAL EXCEPTION`, **zero** `CORS`/`Access-Control` errors, **zero** `Mixed Content` errors. Only a known, already-documented, non-blocking warning (`Foreground push notification setup failed. ReferenceError: Notification is not defined`) |
| Backend test suite | `python -m pytest -q` — 631 passed |
| Frontend lint | `npx eslint .` — clean |

**No production data was mutated during this validation.** Only read-only requests were exercised: the public `GET /fields/` (real map data, no auth), and opening the notifications inbox (read-only). No account was created, no field/game was submitted, and no write operations were performed against production.

This directly satisfies the ISSUE-201/202/203 follow-up work item "Revalidate Android API communication ... once both of the above land," and goes further than a generic tunnel-based proof: it confirms the actual, real, permanent backend the shipped app will use is already correctly configured today, with no additional deployment step required.

### Original ISSUE-205 findings (historical, now fixed by ISSUE-206)

Re-checked directly against the live local backend rather than assumed from ISSUE-201:

| Item | Result |
| --- | --- |
| Android API target (`frontend/.env`) | `VITE_API_URL=http://192.168.1.10:8000` / `VITE_API_BASE_URL=http://192.168.1.10:8000` — unchanged since ISSUE-200/201, still plain HTTP |
| Backend `CORS_ORIGINS` (`backend/app/core/config.py` default, no `.env` override) | `http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000` (+ `:5174` variants hardcoded in `main.py`) — still does not include `https://localhost` |
| CORS preflight, fresh check: `OPTIONS /fields/` with `Origin: https://localhost` | `HTTP 400`, body `Disallowed CORS origin`, no `Access-Control-Allow-Origin` header — **unchanged from ISSUE-201** |
| Direct backend reachability (`GET /`, no browser Origin) | `HTTP 200` — backend itself is healthy and reachable |
| Root cause #1 (carried over from ISSUE-201/202) | Backend CORS allowlist still does not authorize the Capacitor WebView origin |
| Root cause #2 (carried over from ISSUE-201/202) | API target is still `http://`, while the Capacitor WebView loads over `https://localhost` — Chromium's Mixed Content policy blocks real requests independent of CORS, as directly observed via console log in ISSUE-201 |
| ISSUE-203 scope check | ISSUE-203 implemented **only** the Network Security Config half of the ISSUE-202 policy (cleartext-disabled, system-CA-only). It explicitly did not touch CORS or the API base URL, and this review confirms neither has been addressed since |

**This gate was NO-GO at the time of the original ISSUE-205 review.** No new attempt was made in ISSUE-205 to fix backend CORS or change the API base URL, per that issue's scope. Both blockers were subsequently fixed in ISSUE-206 and independently re-confirmed against the real production backend in ISSUE-207 above.

## Commands Executed

All commands were run from a clean, up-to-date `main` before branching, then repeated for this review on `issue-205-android-project-readiness-review`.

**Repo state:**
```powershell
git status
git branch --show-current
git pull origin main
git checkout -b issue-205-android-project-readiness-review
```
Result: working tree clean before branching; `main` already up to date with `origin/main` (latest commit `4ec86cc`, the field-creation fix).

**Frontend build / Capacitor:**
```powershell
cd frontend
npm run build
npx cap sync android
npx cap config
npx cap doctor
npx eslint .
```
Results: Vite build succeeded (1,916 modules, ~617 kB main bundle); `cap sync` copied assets and detected the push-notifications plugin; `cap config` confirmed `appId`/`appName`/`webDir`; `cap doctor` reported `Android looking great! 👌`; `eslint .` returned clean with no errors.

**Java / Gradle:**
```powershell
java -version
"C:\Program Files\Android\Android Studio\jbr\bin\java" -version
cd android
.\gradlew.bat --version                          # with system JDK 26 on PATH
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
.\gradlew.bat --version                          # with JBR JAVA_HOME
.\gradlew.bat --stop
.\gradlew.bat assembleDebug                      # reproduced with system JDK 26 (JAVA_HOME unset)
.\gradlew.bat --stop
.\gradlew.bat clean assembleDebug                # with JBR JAVA_HOME
.\gradlew.bat assembleDebug                       # re-run to capture flatDir warning text
.\gradlew.bat :app:processDebugMainManifest
```
Results: system Java confirmed `26.0.1`; JBR confirmed `21.0.10`; Gradle `8.14.3` in both cases; `assembleDebug` under system JDK 26 failed with the known `androidJdkImage`/`jlink.exe` error; `assembleDebug` under JBR succeeded (`BUILD SUCCESSFUL` in 35s, clean build, 130 actionable tasks); manifest processing succeeded.

**Device / startup:**
```powershell
$ADB = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
& $ADB devices -l
& $ADB install -r ".\app\build\outputs\apk\debug\app-debug.apk"
& $ADB logcat -c
& $ADB shell am force-stop com.yeshmishak.app
& $ADB shell monkey -p com.yeshmishak.app -c android.intent.category.LAUNCHER 1
Start-Sleep -Seconds 10
& $ADB shell dumpsys activity activities | Select-String "ResumedActivity"
& $ADB shell pidof com.yeshmishak.app
& $ADB logcat -d -v time
& $ADB shell input keyevent KEYCODE_WAKEUP
& $ADB exec-out screencap -p
```
Results: device `RFCXA0GMVJA` (Samsung SM-S928B) detected and authorized; install succeeded; `MainActivity` resumed with a live PID; zero `AndroidRuntime`/`FATAL EXCEPTION` entries; login screen rendered correctly in a device screenshot; one new non-blocking console error identified (safe-area CSS injection).

**API communication:**
```powershell
curl.exe -s -o NUL -w "%{http_code}" http://192.168.1.10:8000/
curl.exe -i -X OPTIONS "http://192.168.1.10:8000/fields/" `
  -H "Origin: https://localhost" `
  -H "Access-Control-Request-Method: GET" `
  -H "Access-Control-Request-Headers: authorization,content-type"
```
Results: backend root returned `200`; CORS preflight for the Capacitor origin returned `400 Disallowed CORS origin` with no `Access-Control-Allow-Origin` header — unchanged from ISSUE-201.

## Commands Executed — ISSUE-207 Re-validation

Run fresh on `issue-207-finalize-android-foundation-completion`, branched from `main` at commit `ab6f8d1` (ISSUE-206 merged).

**Repo state:**
```powershell
git status
git checkout main
git pull origin main
git checkout -b issue-207-finalize-android-foundation-completion
```
Result: working tree clean before branching; `main` up to date, `ab6f8d1` ("Fix Android WebView API communication (ISSUE-206)") present in history.

**Confirm ISSUE-206 changes present:**
```bash
grep -n "https://localhost" backend/app/main.py
grep -n "build:android" frontend/package.json
grep -n "\.env\.android" .gitignore
ls frontend/.env.android.example docs/android-api-configuration.md docs/android-project-readiness-review.md
```
Results: all present and confirmed on `main`.

**Locating and verifying a real permanent HTTPS backend:**
```powershell
curl.exe https://yesh-mishak-api-staging.railway.app/       # Railway placeholder page, not live
curl.exe https://yesh-mishak-api.railway.app/                # Railway placeholder page, not live
curl.exe https://yesh-mishak.vercel.app/assets/index-*.js -o prod-bundle.js
grep -o "https://[a-zA-Z0-9.-]*railway[a-zA-Z0-9./-]*" prod-bundle.js
curl.exe https://yeshmishak-production.up.railway.app/       # {"status":"ok"} — real, live
curl.exe -i -X OPTIONS "https://yeshmishak-production.up.railway.app/fields/" -H "Origin: https://localhost" -H "Access-Control-Request-Method: GET" -H "Access-Control-Request-Headers: authorization,content-type"
```
Results: found the real production backend (`https://yeshmishak-production.up.railway.app`) by extracting it from the live web app's own bundle; confirmed it is genuinely live (`{"status":"ok"}`); confirmed CORS preflight already passes (`200`, correct `Access-Control-Allow-Origin`) for all 6 endpoints in the ISSUE-201 matrix, with no manual deployment step needed.

**Frontend Android build (pointed at the real production URL):**
```powershell
cd frontend
# frontend/.env.android (git-ignored): VITE_API_URL=https://yeshmishak-production.up.railway.app
npm run build:android
npx cap sync android
npx cap doctor
npx eslint .
cd backend && python -m pytest -q
```
Results: build succeeded with mode `android`; bundle verified to contain the production URL with zero `192.168`/`http://` occurrences; sync succeeded; `cap doctor` reported `Android looking great! 👌`; lint clean; 631 backend tests passed.

**Android debug build:**
```powershell
cd android
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
.\gradlew.bat --version
.\gradlew.bat --stop
.\gradlew.bat assembleDebug
```
Results: Launcher/Daemon JVM confirmed JBR `21.0.10`; `BUILD SUCCESSFUL` in 18s.

**Device install/launch/API validation against real production:**
```powershell
$ADB = "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe"
& $ADB devices -l
& $ADB install -r ".\app\build\outputs\apk\debug\app-debug.apk"
& $ADB logcat -c
& $ADB shell am force-stop com.yeshmishak.app
& $ADB shell monkey -p com.yeshmishak.app -c android.intent.category.LAUNCHER 1
& $ADB shell dumpsys activity activities | Select-String "ResumedActivity"
& $ADB shell input keyevent KEYCODE_WAKEUP
& $ADB exec-out screencap -p
& $ADB logcat -d -v time
```
Results: device `RFCXA0GMVJA` detected; install succeeded; app launched and resumed with a live PID; device screenshot showed the map screen with **live production field markers** rendered from a real `GET /fields/` call; opening the notifications inbox worked with no error state; full-session logcat (10,946 lines) contained zero `FATAL EXCEPTION`, zero `CORS`/`Access-Control`, and zero `Mixed Content` entries — only the known, already-documented push-notification console warning.

No production data was written or mutated during this validation; only read-only requests (`GET /fields/`, notifications inbox open) were exercised.

**Cleanup:** removed the local `frontend/.env.android` test file (git-ignored, never committed), rebuilt with the default `npm run build` + `npx cap sync android` to restore the repository to its normal local-dev state before finishing.

## Evidence Table

| Gate | Status | Primary Evidence |
| --- | --- | --- |
| Android Project | PASS | Fresh `cap config`/`cap doctor` output; manifest/Gradle package-identity grep; `network_security_config.xml` content unchanged since ISSUE-203 |
| Debug Build | PASS | `BUILD SUCCESSFUL` clean `assembleDebug` under JBR; reproduced JDK 26 failure for contrast; APK SHA-256 `efc6e0f9...` |
| Startup Flow | PASS | Live PID after cold launch; zero fatal exceptions in logcat; device screenshot showing rendered login UI |
| API Communication | NO-GO at time of original ISSUE-205 review; **PASS as of ISSUE-207** | CORS preflight now `200` on all 6 endpoints against the real, permanent, live production backend; real device evidence (live field markers rendered from `GET /fields/`, notifications inbox opened); zero CORS/Mixed Content/fatal errors across full-session logcat |

## Known Issues / Non-blocking Warnings

1. **System JDK 26 cannot build the project.** Must set `JAVA_HOME` to the Android Studio JBR for every Gradle invocation. Environment issue, not a project defect (per ISSUE-201/204).
2. **`flatDir` Gradle warning.** Emitted from the generated Capacitor/Cordova bridge configuration on every configure phase. Cosmetic; does not block the build (per ISSUE-198/204).
3. **Kotlin stdlib instrumentation conflict.** Affects only the `androidTest`/instrumentation APK path (`kotlin-stdlib:1.8.22` vs. `kotlin-stdlib-jdk7`/`jdk8:1.6.21`), not `assembleDebug`. Out of scope for this review per its explicit instructions; tracked separately since ISSUE-197.
4. **Google Sign-In fails to load** on the login screen. Visible again in this review's screenshot; tracked separately under dedicated OAuth work (per ISSUE-200/201).
5. **Missing `google-services.json`.** Firebase cannot initialize; native push token registration cannot function until this is provisioned through the approved secure process (per ISSUE-201/204).
6. **New: safe-area CSS injection console error on cold start.** `Error injecting safe area CSS: TypeError: Cannot read properties of null (reading 'style')`, logged 3 times via `Capacitor/Console` immediately after the WebView loads. Did not prevent the login screen from rendering or becoming interactive. Not previously documented in ISSUE-200/201. Recommend a follow-up investigation into the safe-area CSS injection code path (likely a `document.querySelector` returning `null` before some layout element exists in the Capacitor WebView), but this does not block the startup gate for this review.

## Blockers

**Status: Resolved by ISSUE-206, independently confirmed against real production by ISSUE-207.**

1. ~~Backend CORS does not authorize `https://localhost`.~~ **Fixed** — `backend/app/main.py` now unconditionally allows this origin. Every tested endpoint returns `200` with the correct `Access-Control-Allow-Origin` header, confirmed both locally and against the real live production backend.
2. ~~Android API target is plain HTTP while the WebView is HTTPS.~~ **Fixed** — Android builds now use `npm run build:android` with a dedicated, git-ignored `frontend/.env.android` that must be HTTPS, documented in `docs/android-api-configuration.md` and demonstrated end-to-end against real production in this review.

Both blockers were root-caused in ISSUE-201, policy-scoped in ISSUE-202, intentionally left unimplemented by ISSUE-203's narrow scope, and fixed in ISSUE-206. This review (ISSUE-207) confirms, with fresh commands and real device evidence against the app's actual permanent production backend, that both fixes are present on `main` and working end-to-end with no further deployment action required.

## Final Decision

**COMPLETE.**

All four required gates now pass on fresh, reproducible evidence:

| Gate | Status |
| --- | --- |
| Android Project | PASS |
| Debug Build | PASS |
| Startup Flow | PASS |
| API Communication | **PASS** (was NO-GO in ISSUE-205; fixed by ISSUE-206; re-confirmed by ISSUE-207 against the real, permanent, live production backend with real device evidence) |

The project structure is sound, the debug build is reproducible given the correct JDK, the app launches and renders without crashing on a physical device, and a real API call succeeded from the installed app against the app's actual production backend — live field markers rendered on the map from a genuine `GET /fields/` response, with zero CORS, Mixed Content, or fatal errors anywhere in the session logcat. The production backend was independently confirmed to already have the ISSUE-206 CORS fix deployed (Railway auto-deploys from `main`), so no further infrastructure action is needed. Per this review's acceptance criteria, Android Foundation is marked complete now that all required gates pass with evidence against a permanent (not temporary) backend.

## Android Foundation Completion Checklist

| # | Item | Status |
| --- | --- | --- |
| 1 | Capacitor Android project structure correct and package identity aligned (ISSUE-197/198) | Done |
| 2 | Android development environment documented (ISSUE-194/196) | Done |
| 3 | Debug build reproducible with documented JDK requirement (ISSUE-205, re-confirmed ISSUE-207) | Done |
| 4 | Startup flow validated on physical device, no crashes (ISSUE-200, re-confirmed ISSUE-205/207) | Done |
| 5 | Android network security policy defined (ISSUE-202) | Done |
| 6 | Network Security Config implemented per policy (ISSUE-203) | Done |
| 7 | Android build troubleshooting guide available (ISSUE-204) | Done |
| 8 | Backend CORS allowlist authorizes the Capacitor origin (`https://localhost`) | **Done (ISSUE-206; confirmed live in production by ISSUE-207)** |
| 9 | Android API target points at an HTTPS backend | **Done (ISSUE-206; `.env.android.example` now references the confirmed-live production URL)** |
| 10 | Full API communication revalidated end-to-end (login, fields, games, notifications) with a GO verdict, against a permanent backend | **Done (ISSUE-207)** — real device evidence against `https://yeshmishak-production.up.railway.app`, not a temporary tunnel |

**Android Foundation status: COMPLETE.** All 10 items are done and evidenced. Recommend using this same "extract the real backend URL from the live web bundle, verify CORS, then build Android against it" pattern as a starting point for iOS foundation work, and separately recommend standing up a real, dedicated staging backend deployment so future Android/iOS development doesn't need to target production or a temporary tunnel.
