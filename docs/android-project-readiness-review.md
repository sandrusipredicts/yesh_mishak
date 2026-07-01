# Android Project Readiness Review

## Executive Summary

This review re-verifies, with fresh commands run directly against the current `main` branch, every gate required before Android foundation work can be considered complete and the team moves on to iOS: project/config integrity, the debug build, the startup flow, and API communication. It supersedes no prior document — it re-confirms ISSUE-197 through ISSUE-204 and the subsequent field-creation bug fix are all still true on disk today, and it adds one new, non-blocking observation (a safe-area CSS console error) that had not been called out before.

Three of the four required gates pass on fresh evidence: **Android Project Status**, **Debug Build Status**, and **Startup Flow Status**. The fourth, **API Communication Status**, remains **NO-GO**, for exactly the two reasons already root-caused in ISSUE-201/202: the backend does not authorize the Capacitor origin (`https://localhost`) for CORS, and the configured API target is plain HTTP while the WebView is HTTPS, which triggers Mixed Content blocking independent of CORS. Neither blocker has been fixed yet — ISSUE-203 intentionally implemented only the Network Security Config half of the ISSUE-202 policy, and left the CORS allowlist and HTTPS API target as explicit follow-up work, which is still outstanding as of this review.

**Final decision: NO-GO for full Android Foundation completion.** The native/build/startup foundation is solid and reproducible. The project cannot be marked complete while real API calls (login, fields, games, notifications) are blocked end-to-end. No code, config, or build file was changed to produce this review — this is a verification/evidence document only.

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

## API Communication Status: NO-GO

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

**This gate remains NO-GO.** No new attempt was made in this review to fix backend CORS or change the API base URL, per this issue's scope (documentation/review only; a "real blocking issue" here is not a *new* discovery — it is the same, already-tracked, already-scoped-for-a-later-issue blocker from ISSUE-201/202/203). Fixing it here would be out of scope and would blur ownership of that follow-up work.

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

## Evidence Table

| Gate | Status | Primary Evidence |
| --- | --- | --- |
| Android Project | PASS | Fresh `cap config`/`cap doctor` output; manifest/Gradle package-identity grep; `network_security_config.xml` content unchanged since ISSUE-203 |
| Debug Build | PASS | `BUILD SUCCESSFUL` clean `assembleDebug` under JBR; reproduced JDK 26 failure for contrast; APK SHA-256 `efc6e0f9...` |
| Startup Flow | PASS | Live PID after cold launch; zero fatal exceptions in logcat; device screenshot showing rendered login UI |
| API Communication | NO-GO | Fresh CORS preflight `400 Disallowed CORS origin`; unchanged `http://` API target in `frontend/.env`; unchanged backend `CORS_ORIGINS` default |

## Known Issues / Non-blocking Warnings

1. **System JDK 26 cannot build the project.** Must set `JAVA_HOME` to the Android Studio JBR for every Gradle invocation. Environment issue, not a project defect (per ISSUE-201/204).
2. **`flatDir` Gradle warning.** Emitted from the generated Capacitor/Cordova bridge configuration on every configure phase. Cosmetic; does not block the build (per ISSUE-198/204).
3. **Kotlin stdlib instrumentation conflict.** Affects only the `androidTest`/instrumentation APK path (`kotlin-stdlib:1.8.22` vs. `kotlin-stdlib-jdk7`/`jdk8:1.6.21`), not `assembleDebug`. Out of scope for this review per its explicit instructions; tracked separately since ISSUE-197.
4. **Google Sign-In fails to load** on the login screen. Visible again in this review's screenshot; tracked separately under dedicated OAuth work (per ISSUE-200/201).
5. **Missing `google-services.json`.** Firebase cannot initialize; native push token registration cannot function until this is provisioned through the approved secure process (per ISSUE-201/204).
6. **New: safe-area CSS injection console error on cold start.** `Error injecting safe area CSS: TypeError: Cannot read properties of null (reading 'style')`, logged 3 times via `Capacitor/Console` immediately after the WebView loads. Did not prevent the login screen from rendering or becoming interactive. Not previously documented in ISSUE-200/201. Recommend a follow-up investigation into the safe-area CSS injection code path (likely a `document.querySelector` returning `null` before some layout element exists in the Capacitor WebView), but this does not block the startup gate for this review.

## Blockers

1. **Backend CORS does not authorize `https://localhost`.** Every tested endpoint (`/auth/login`, `/auth/google`, `/fields/`, `/games/active`, `/notifications`, `/notifications/push-token` per ISSUE-201, re-confirmed here for `/fields/`) returns `400 Disallowed CORS origin`. Fix is a backend `CORS_ORIGINS` configuration change — explicitly out of scope for this review and for ISSUE-203.
2. **Android API target is plain HTTP while the WebView is HTTPS.** This independently blocks real requests via Mixed Content, regardless of the CORS fix. Fix is pointing the Android build at an HTTPS backend (deployed staging/production, or an HTTPS tunnel) — explicitly out of scope for this review and for ISSUE-203.

Both blockers were root-caused in ISSUE-201, policy-scoped in ISSUE-202, and intentionally left unimplemented by ISSUE-203's narrow scope. This review confirms, with fresh commands, that neither has been resolved since.

## Final Decision

**NO-GO for full Android Foundation completion.**

Three of four required gates — Android Project, Debug Build, and Startup Flow — pass on fresh, reproducible evidence. The project structure is sound, the debug build is reproducible given the correct JDK, and the app launches and renders without crashing on a physical device. However, the Android Foundation cannot be marked complete while the fourth required gate, API Communication, remains blocked: no real API call (login, fields, games, or notifications) can currently succeed from the Android app, for two independently-confirmed reasons (CORS allowlist gap and HTTP/HTTPS scheme mismatch). Per this review's acceptance criteria, Android Foundation can only be marked complete when all required gates pass — that condition is not met.

## Android Foundation Completion Checklist

| # | Item | Status |
| --- | --- | --- |
| 1 | Capacitor Android project structure correct and package identity aligned (ISSUE-197/198) | Done |
| 2 | Android development environment documented (ISSUE-194/196) | Done |
| 3 | Debug build reproducible with documented JDK requirement (this review) | Done |
| 4 | Startup flow validated on physical device, no crashes (ISSUE-200, re-confirmed this review) | Done |
| 5 | Android network security policy defined (ISSUE-202) | Done |
| 6 | Network Security Config implemented per policy (ISSUE-203) | Done |
| 7 | Android build troubleshooting guide available (ISSUE-204) | Done |
| 8 | Backend CORS allowlist authorizes the Capacitor origin (`https://localhost`) | **Not done** |
| 9 | Android API target points at an HTTPS backend | **Not done** |
| 10 | Full API communication revalidated end-to-end (login, fields, games, notifications) with a GO verdict | **Not done — blocked by #8 and #9** |

**Android Foundation status: Incomplete.** Items 1–7 are done and evidenced. Items 8–10 remain outstanding and are the required follow-up work before this review's decision can flip to GO. Recommend opening the two follow-up issues identified in ISSUE-202/203 (backend CORS configuration; Android HTTPS API target) before scheduling iOS foundation work, since the same CORS/HTTPS requirements will very likely apply to the iOS WebView origin as well.
