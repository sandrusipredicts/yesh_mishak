# Android API Communication Validation

## Summary

Android API communication was validated on the same physical Samsung SM-S928B used in ISSUE-200. A fresh frontend build, Capacitor sync, and Gradle `assembleDebug` were completed and the resulting debug APK was installed and launched.

The result is **NO-GO**. The backend still does not authorize the Capacitor WebView origin (`https://localhost`): a manual CORS preflight against every tested endpoint (`/auth/login`, `/auth/google`, `/fields/`, `/games/active`, `/notifications`, `/notifications/push-token`) returns `HTTP 400 Disallowed CORS origin` with no `Access-Control-Allow-Origin` header. In addition, an actual in-app login attempt was performed against the real API target (`http://192.168.1.10:8000`) and was blocked by the WebView's **Mixed Content policy** before any CORS check could occur, because the app page is served over `https://localhost` but the configured API target is plain `http://`. This is a second, independent blocker on top of the CORS gap documented in ISSUE-200.

Because login cannot succeed, the app never reaches an authenticated state. Fields, Games, and Notifications are only rendered after login (confirmed by reading `frontend/src/App.jsx`), so none of those screens could be exercised through real in-app navigation. Their backend endpoints were validated directly with CORS preflight requests instead, and all fail identically to `/auth/login`.

No Android native file, Gradle file, AndroidManifest, or Capacitor config was modified during this validation. No backend CORS configuration was changed.

## Test Environment

| Item | Value |
| --- | --- |
| Validation date | 2026-07-01 |
| Branch | `issue-201-validate-android-api-communication` |
| Base commit | `b4beedb` |
| Device | Samsung SM-S928B |
| Device serial | `RFCXA0GMVJA` |
| Android version | 16 |
| Android SDK level | 36 |
| Device Wi-Fi address | `192.168.1.166` (per ISSUE-200; network unchanged) |
| APK path | `frontend/android/app/build/outputs/apk/debug/app-debug.apk` |
| APK SHA-256 | `50f49e4aa73a80846fd5f7d35362087098506b4a6e65afe44fb38213d2b643e6` |
| Package ID | `com.yeshmishak.app` |
| Java runtime used for Gradle | Android Studio JBR (`C:\Program Files\Android\Android Studio\jbr`), required because the system default JDK 26 could not run the `androidJdkImage` transform |
| API target | `http://192.168.1.10:8000` (`VITE_API_URL` / `VITE_API_BASE_URL` in `frontend/.env`) |
| Capacitor WebView origin | `https://localhost` |
| Backend process | FastAPI/uvicorn running locally on the same machine, reachable at both `127.0.0.1:8000` and `192.168.1.10:8000` |

The API target is the same LAN address used in ISSUE-200 and is confirmed to be this development machine's actual LAN IPv4 address (via `ipconfig`), so it is a valid target for the physical device on the same Wi-Fi network — not `localhost`/`127.0.0.1` pointing back at the phone itself.

## Validation Commands

| Command | Result | Notes |
| --- | --- | --- |
| `git checkout main` / `git pull origin main` | PASS | Already up to date. |
| `git checkout -b issue-201-validate-android-api-communication` | PASS | Required branch created. |
| `npm run build` | PASS | Vite transformed 1,916 modules, built `dist/`. |
| `npx cap sync android` | PASS | Assets copied; push-notifications plugin detected. |
| `npx cap config` | PASS | Confirmed `com.yeshmishak.app`, `Yesh Mishak`, `dist`. |
| `.\gradlew.bat assembleDebug` (system JDK 26) | FAIL | `androidJdkImage` transform failed calling `jlink.exe` under JDK 26. Environment issue, not a project defect. |
| `.\gradlew.bat assembleDebug` (Android Studio JBR JDK) | PASS | `BUILD SUCCESSFUL`, fresh `app-debug.apk` produced. |
| `adb devices -l` | PASS | Samsung SM-S928B connected and authorized. |
| `adb install -r app-debug.apk` | PASS | Streamed installation returned `Success`. |
| Logcat clear, force-stop, launcher monkey, 10s wait | PASS | `MainActivity` resumed, process alive, no fatal exception. |
| Manual CORS preflight (curl, 5 endpoints) | FAIL | All 5 return HTTP 400, `Disallowed CORS origin`, no `Access-Control-Allow-Origin`. |
| In-app login submission (real UI tap, test credentials) | FAIL | Blocked by Mixed Content before request left the WebView; app shows generic "cannot log in" error. |
| Fields / Games / Notifications screens | NOT REACHABLE via UI | App has no unauthenticated route; login must succeed first. Endpoints validated directly via CORS preflight instead. |

## API Target Discovery

- The Android build reads `VITE_API_URL=http://192.168.1.10:8000` and `VITE_API_BASE_URL=http://192.168.1.10:8000` from `frontend/.env`.
- `192.168.1.10` was confirmed via `ipconfig` to be this development machine's actual LAN IPv4 address, and the backend responded `200` on both `http://127.0.0.1:8000/` (local) and `http://192.168.1.10:8000/` (LAN).
- This is a valid LAN target for a physical Android device, not `localhost`/`127.0.0.1`, which would incorrectly resolve to the phone itself. No change was needed here.
- The target uses plain `http://`, while the Capacitor WebView origin is `https://localhost`. This scheme mismatch is the root cause of the Mixed Content blocker described below, independent of the CORS configuration gap.

## CORS / Preflight Validation

Backend CORS configuration (`backend/app/core/config.py`, `backend/app/main.py`) defaults `CORS_ORIGINS` to `http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000`, with `http://localhost:5174`/`http://127.0.0.1:5174` appended in code. No `.env` override adds `https://localhost`. This matches the ISSUE-200 finding and confirms the gap has not been closed.

Preflight requests were sent from the development machine with `Origin: https://localhost`, matching the exact Capacitor WebView origin, against every API area in scope:

| Endpoint | Method under test | Result | Details |
| --- | --- | --- | --- |
| `/auth/login` | POST | FAIL | `HTTP 400`, body `Disallowed CORS origin`, no `Access-Control-Allow-Origin` |
| `/auth/google` | POST | FAIL | `HTTP 400`, body `Disallowed CORS origin`, no `Access-Control-Allow-Origin` |
| `/fields/` | GET | FAIL | `HTTP 400`, body `Disallowed CORS origin`, no `Access-Control-Allow-Origin` |
| `/games/active` | GET | FAIL | `HTTP 400`, body `Disallowed CORS origin`, no `Access-Control-Allow-Origin` |
| `/notifications` | GET | FAIL | `HTTP 400`, body `Disallowed CORS origin`, no `Access-Control-Allow-Origin` |
| `/notifications/push-token` | POST | FAIL | `HTTP 400`, body `Disallowed CORS origin`, no `Access-Control-Allow-Origin` |

Example:

```text
curl.exe -i -X OPTIONS "http://192.168.1.10:8000/fields/" \
  -H "Origin: https://localhost" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: authorization,content-type"

HTTP/1.1 400 Bad Request
access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
access-control-allow-credentials: true
access-control-allow-headers: authorization,content-type
content-type: text/plain; charset=utf-8

Disallowed CORS origin
```

Direct, non-preflight `GET http://192.168.1.10:8000/fields/` (no `Origin` header, simulating a plain device HTTP request) returned `HTTP 200`, confirming the backend itself is reachable and the failure is specific to browser-enforced CORS.

**Required pass condition (`Access-Control-Allow-Origin: https://localhost`) is not met for any tested endpoint. Per the task's classification rule, API communication is NO-GO.**

## Login API Validation

**Result: FAIL — blocked before reaching the backend's CORS or auth logic.**

A real login was attempted through the installed app's UI (not assumed from the screen rendering):

1. The login screen rendered with a pre-existing, visible error: `לא ניתן לטעון התחברות Google.` ("Unable to load Google sign-in.") — present before any user interaction.
2. Username `test_validation_user` and a test password were typed into the real form fields via `adb shell input`.
3. The login button was tapped, generating a real HTTP request from the WebView (not a simulated one).
4. Logcat captured the WebView's own console error at the moment of submission:

   ```text
   E/Capacitor/Console(21392): File: https://localhost/assets/index-DykuUH9_.js - Line 11 - Msg: Mixed Content:
   The page at 'https://localhost/' was loaded over HTTPS, but requested an insecure XMLHttpRequest endpoint
   'http://192.168.1.10:8000/auth/login'. This request has been blocked; the content must be served over HTTPS.
   ```

5. The app UI then displayed a generic error: `לא ניתן להתחבר. בדקו את הפרטים ונסו שוב.` ("Cannot log in. Check your details and try again.") — the same message a real user would see for wrong credentials, even though the actual cause is a network-level Mixed Content block, not invalid credentials.

**Findings:**
- The request never left the WebView as a network call the backend could log or reject; the browser blocked it client-side.
- Even if CORS were fixed today, login would still fail while the API target uses `http://` from an `https://localhost` page, because Mixed Content blocking is independent of CORS.
- The app's error handling (`frontend/src/api/auth.js`, `LoginPage`) does not distinguish network/CORS/mixed-content failures from invalid-credentials failures — both surface the same generic message. This masks the real failure from anyone testing only through the UI, which is why this issue explicitly required not assuming success from the rendered screen.
- Separately, the CORS preflight for `/auth/login` and `/auth/google` also fails (see above), so even serving the API over HTTPS would not be sufficient on its own — the CORS allowlist gap from ISSUE-200 remains unresolved.
- No `AndroidRuntime` fatal exception or app crash occurred during the login attempt; the app remained responsive and stayed on the login screen.

## Fields API Validation

**Result: NOT REACHABLE via app navigation; endpoint independently confirmed FAIL for CORS.**

- `MapPage` (the fields/map screen) is only rendered by `App.jsx` when `currentUser` is set from a successful login. Because login could not succeed, the fields screen could not be opened through real in-app navigation, and no field/map data request was observed being issued by the app during this session.
- The underlying endpoint (`GET /fields/`) was validated directly: CORS preflight from `https://localhost` returns `HTTP 400 Disallowed CORS origin` (see CORS section). A direct non-preflight GET returns `HTTP 200`, so the backend endpoint itself works, but the WebView cannot call it while unauthenticated to CORS.
- No field/map screen was observed rendering in the app during this validation; this is a documented consequence of the login blocker, not a separate fields-specific defect.

## Games API Validation

**Result: NOT REACHABLE via app navigation; endpoints independently confirmed FAIL for CORS.**

- `MyGamesPage` and any active/upcoming games view are likewise gated behind `currentUser` in `App.jsx` and could not be opened without a successful login.
- `GET /games/active` was validated directly via CORS preflight and fails identically to the other endpoints (`HTTP 400 Disallowed CORS origin`).
- Creating or joining a game requires an authenticated session and real test data; this was not attempted because login does not succeed, and per the task's rules no production data mutation was performed. This is a manual test limit caused directly by the login/network blocker, not a scope decision to skip games testing.

## Notifications API Validation

**Result: NOT REACHABLE via app navigation; endpoint independently confirmed FAIL for CORS. Push registration environment is also incomplete.**

- The in-app notifications list/preferences UI is only reachable after login, which did not succeed, so no read/unread notification request was observed from the app itself.
- `GET /notifications` was validated directly via CORS preflight and fails identically (`HTTP 400 Disallowed CORS origin`). `POST /notifications/push-token` was also checked directly and fails the same way.
- `startForegroundPushNotifications()` in `frontend/src/App.jsx` only runs after `currentUser` is set, so push token registration was never attempted by the app during this session (login blocker).
- Independently of CORS, Firebase/push is not fully configured for native Android:
  - Logcat recorded: `W/FirebaseApp(21392): Default FirebaseApp failed to initialize because no default options were found. This usually means that com.google.gms:google-services was not applied to your gradle project.`
  - No `google-services.json` file exists anywhere under `frontend/android` (confirmed by search).
  - This is a known, pre-existing limitation: native push token registration cannot function until `google-services.json` is added through the approved Firebase/Android configuration process. This validation did not add it, per the hard rule against modifying Gradle/native configuration.

## Logcat Findings

### Positive evidence
- App launched, reached `MainActivity` resumed state, and remained alive throughout both the launch and the login-attempt sessions (`pidof` returned a live PID after each check).
- No `AndroidRuntime` fatal exception and no chromium-reported uncaught JavaScript error were found in either capture.
- Capacitor served all bundled local assets (`https://localhost/`, JS bundle, CSS bundle, favicon) successfully, matching ISSUE-200.

### Negative / blocking evidence
- `E/Capacitor/Console`: Mixed Content block on the real login POST to `http://192.168.1.10:8000/auth/login` from the `https://localhost` page.
- `W/FirebaseApp`: default Firebase app failed to initialize — no `google-services.json` applied.
- Visible on-screen: Google sign-in failed to load, and the login attempt itself failed with a generic error that does not reveal the real network cause.

## Known Issues

### Blockers
1. **Backend CORS still does not allow the Capacitor origin** (carried over from ISSUE-200, reconfirmed here for `/auth/login`, `/auth/google`, `/fields/`, `/games/active`, `/notifications`, `/notifications/push-token`). All return `HTTP 400 Disallowed CORS origin` with no `Access-Control-Allow-Origin` header.
2. **Mixed Content blocks the real login request independently of CORS.** The API target is `http://192.168.1.10:8000` while the WebView origin is `https://localhost`. A browser will block this XHR outright regardless of any CORS fix, unless the API is served over HTTPS (or the WebView origin/scheme is changed through an approved configuration change, which is out of scope for this validation).
3. **Fields, Games, and Notifications screens cannot be exercised through real app navigation** because the app has no unauthenticated route and login does not succeed. This is a direct, structural consequence of blockers 1 and 2, not an independent defect in those screens.

### Non-blocking / known limitations
1. **Google Sign-In fails to load** on the login screen, as already noted in ISSUE-200; tracked separately under the dedicated OAuth work.
2. **Missing `google-services.json`** prevents Firebase from initializing, which will also block native push token registration once CORS/Mixed Content are resolved. No native/Gradle file was modified to add this, per the hard rules for this issue.
3. **The app's error handling does not distinguish network/CORS/mixed-content failures from invalid-credential failures.** This is a UX/observability gap worth tracking separately, since it makes it easy for manual testers to misdiagnose a network blocker as a login mistake.

## Risk Assessment

| Area | Risk | Assessment |
| --- | --- | --- |
| Native launch / stability | Low | App launches, stays alive, no crash during login attempt. |
| API target configuration | Low | LAN IP is valid and reachable for the physical device. |
| CORS | High | Every tested endpoint rejects the Capacitor origin. |
| Mixed Content (HTTPS page → HTTP API) | High | Independently blocks real requests regardless of CORS status. |
| Login | High | Cannot complete; real request never reaches backend logic. |
| Fields / Games / Notifications | High | Cannot be exercised at all while login is blocked; endpoints independently fail CORS. |
| Push notifications (native) | Medium | Blocked by both the login gate and missing `google-services.json`. |
| Error observability | Medium | Generic failure messages mask the true network-level cause. |

## Final Verdict

**NO-GO**

Android API communication is not functional. The backend continues to reject the Capacitor WebView origin (`https://localhost`) for every tested endpoint — login, fields, games, and notifications — with `HTTP 400 Disallowed CORS origin`. On top of that, a real in-app login attempt showed a second, independent blocker: the browser's Mixed Content policy stops the request before it can even leave the WebView, because the API target is plain HTTP while the app is served over HTTPS. Because login cannot succeed, fields, games, and notifications cannot be exercised through real navigation at all.

No Android native file, Gradle file, AndroidManifest, or Capacitor config was changed, and no backend CORS configuration was modified, per this issue's validation-only scope. Both blockers must be resolved — the CORS allowlist and the HTTP/HTTPS scheme mismatch — and revalidated with a real successful in-app login and authenticated API calls before this area can receive a GO verdict.
