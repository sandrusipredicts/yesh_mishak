# Cross-Platform Behavior Standards

## 1. Overview and Purpose
This document defines the official, unified cross-platform behavior standards for the `yesh_mishak` application across Web, Android, and iOS platforms.
As the codebase moves from a single web target to native mobile distributions (Capacitor/WebView), these standards ensure that security invariants, storage boundary rules, session lifecycles, and user-facing error behaviors remain identical and consistent.
Adhering to these standards prevents platform drift, guards against session hijacking, and enforces security-first fail-closed rules uniformly.

---

## 2. Supported Platforms
The application supports and targets three platforms:
- **Web**: Standard single-page application (React + Vite) targeting desktop and mobile browsers.
- **Android**: Capacitor WebView wrapper container targeting Android 7.0+ (API level 24+).
- **iOS**: Capacitor WebView wrapper container targeting iOS 15.0+.

---

## 3. Behavior Classification Language
To maintain clarity regarding what has been physically tested and verified versus design intent, the following terms are strictly enforced:

- **VALIDATED**: The behavior is fully implemented in production code, covered by automated test suites, and proven to work via testing on physical hardware (specifically verified on a physical Samsung SM-S928B for Android).
- **EXPECTED**: The behavior represents the approved target design for unimplemented features or platforms, but has not yet been proven via physical hardware verification.
- **BLOCKED**: Implementation, configuration, or final testing is paused or prevented due to the lack of physical hardware, credentials, or environment access.
- **NOT SUPPORTED**: Features, flows, or storage mechanisms that are explicitly excluded from design and implementation scopes due to platform limitations, security invariants, or product boundaries (e.g., running Google Sign-In via standard WebViews on mobile).

---

## 4. Authentication Standards

### Google Login
- **Web (VALIDATED)**: Google Sign-In is initiated via the Google Identity Services (GIS) JavaScript SDK client button.
- **Android (VALIDATED)**: Google Sign-In is initiated natively using Android Credential Manager ("Sign in with Google") via the `@capgo/capacitor-social-login` plugin, requested with the `serverClientId` set to the web OAuth client ID.
- **iOS (EXPECTED / BLOCKED)**: iOS Google Sign-In must run natively via the `@capgo/capacitor-social-login` plugin (configured with the iOS-specific Client ID and Web Client ID as `serverClientId`), avoiding any web-based OAuth redirects or WebView script execution.

### Native vs. Web Login
- Native runtimes must detect their environment using `Capacitor.isNativePlatform()`.
- On native, the web GIS button script is **NOT SUPPORTED** and must not load. The UI must render a native button trigger that redirects control to the native plug-in.

### Backend Token Exchange (VALIDATED)
- When a Google ID token is obtained (natively or via web), it is exchanged via the single backend endpoint `POST /auth/google`.
- The Google ID token is treated as exchange-only; it is never stored locally and is discarded immediately after the exchange resolves or fails.

### Account-Linking 409 Behavior (VALIDATED)
- If a Google login email matches an existing manual account with a password hash, the backend returns a `409 Conflict` with the stable machine-readable code `ACCOUNT_LINKING_REQUIRED`.
- The frontend catches this code, stops the login pipeline, displays a localized Hebrew message, and ensures **no session storage or token state is created**.

---

## 5. Session Lifecycle Standards

### Save Session
- **Web (VALIDATED)**: The internal app JWT is saved in plaintext `localStorage` as a compatibility tier.
- **Android (VALIDATED)**: The internal app JWT is written to Keystore-backed secure storage (`@aparajita/capacitor-secure-storage`). Local user metadata is cached in `localStorage` without credential details.
- **iOS (EXPECTED)**: The internal app JWT must be written to iOS Keychain secure storage (`@aparajita/capacitor-secure-storage`). Plaintext storage of the JWT on native iOS is **NOT SUPPORTED**.
- **Write Failure (VALIDATED)**: If secure storage writes fail permanently after one retry, the session is kept in-memory only for the current run, and an amber persistence warning banner is displayed.

### Restore Session
- **Startup Read (VALIDATED)**: On native startup, the stored JWT is read from secure storage.
- **No-Flicker Rule (VALIDATED)**: Startup enters a blocking `auth-checking` screen. The login screen must never flash before session validation completes.
- **Read Timeout (VALIDATED)**: Read attempts are bounded by a 5-second deadline (`SECURE_STORAGE_INIT_TIMEOUT_MS`). Hung bridge calls must reject, clearing the state and redirecting to the login screen.

### Validate Session (VALIDATED)
- A restored session token must be validated against `GET /games/me` before the authenticated UI renders.

### Fail-Closed Standards (VALIDATED)
- Any read failure, corrupt token, timeout, or backend 401 response must trigger `clearSession()`, clearing all cached state across memory, localStorage, and secure storage, returning the user to the login screen.

### Logout Cleanup (VALIDATED)
- Triggering logout bumps the session epoch to invalidate pending async work, invokes `POST /auth/logout` with the pinned token (best-effort), and synchronously clears in-memory tokens, metadata, and secure storage.
- If secure storage delete fails after one retry, a red warning banner is shown, but the UI remains logged out.

### App Relaunch Behavior (VALIDATED)
- Relaunching the app after logout or 401 invalidation must start in the logged-out state with zero residual authentication headers sent to the server.

### Resume Revalidation (VALIDATED)
- On app resume or visibility change, the session must revalidate against `GET /games/me` if (and only if) an active token is cached in memory. Overlapping validation requests must be deduplicated.

---

## 6. Storage Standards

### Android Secure Storage (VALIDATED)
- Storage of the app JWT is delegated to `@aparajita/capacitor-secure-storage`, which stores values encrypted with AES-GCM inside `WSSecureStorageSharedPreferences.xml` via Android Keystore.

### iOS Expected Keychain Behavior (EXPECTED / BLOCKED)
- Storage of the app JWT must use iOS Keychain APIs via `@aparajita/capacitor-secure-storage`. Secure keychain synchronization to iCloud must be evaluated and configured appropriately (or disabled if token sharing violates local device boundary rules).

### Web Fallback (VALIDATED)
- Plaintext `localStorage` is used for token persistence on the web target only. Storing plaintext JWTs in native WebViews is **NOT SUPPORTED**.

### Backup/Restore Expectations (VALIDATED)
- **Android**: `android:allowBackup="false"` is set, and cloud/device-transfer rules (`backup_rules.xml` / `data_extraction_rules.xml`) explicitly exclude all directories. Stale WebView local storage, credentials, and settings do not survive app uninstallation.
- **iOS (EXPECTED / BLOCKED)**: iOS backups (via iTunes or iCloud) must be configured to exclude local application directories and avoid backing up cached session state or WebView local storage.

---

## 7. Error Handling Standards

### Stable Backend Error Codes (VALIDATED)
- The backend API must communicate failure reasons using machine-readable error codes (e.g. `ACCOUNT_LINKING_REQUIRED`, `INVALID_CREDENTIALS`).

### Hebrew User-Facing Messages (VALIDATED)
- User-facing error states in the UI must render localized Hebrew text.
- Example for account linking block: `"כבר קיים חשבון עם האימייל הזה. התחבר עם סיסמה כדי להמשיך."`

### Generic Fallback Behavior (VALIDATED)
- If an unhandled or undocumented API error is received, the client must display a safe, generic error message (e.g., `auth.signInUnexpectedError`) and fail closed. Raw tracebacks or database errors must never be shown.

### Native Picker Cancellation Behavior (VALIDATED)
- User cancellation of the native credential picker is a normal user choice, not an error. The UI must fail silently and return to the login screen without error banners or warnings.

---

## 8. Environment and Origin Standards

### Production Backend URL (VALIDATED)
- The production app must connect to the official production API endpoint. No development environment APIs, staging credentials, or temporary servers may be compiled into production builds.

### Dev Localhost Behavior (VALIDATED)
- Development builds select the API URL dynamically based on environment configuration. Native debug builds connect to the configured development server host.

### No LAN/IP Leakage (VALIDATED)
- Production mobile builds must never leak local development network IPs or LAN URLs.

### Capacitor WebView Origins (VALIDATED)
- **Web (Vite)**: Origin matches the deployment domain (e.g., Vercel).
- **Android**: WebView origin is `https://localhost` (or `http://localhost`).
- **iOS**: WebView origin is `app://localhost` (or `http://localhost`).
- Backend CORS configurations must strictly allowlist only these designated Capacitor app origins.

---

## 9. Validation Standards

### Continuous Integration (CI) (VALIDATED)
- CI proves compilation, code style compliance (lint), package resolution, and Node-based automated testing. It does not replace native environment or hardware validation.

### Playwright Automated Tests (VALIDATED)
- Mocked native plugin bridges run inside Playwright to verify state-machine transitions, deadlines, fail-closed bounds, and cleanup order.

### Android Physical Device Validation (VALIDATED)
- Verifies native Credential Manager UI, Keystore secure storage validation via ADB `run-as`, auto-backup validation via ADB `bmgr`, and device reboot/force-stop lifecycle behaviors.

### iOS Physical Device Validation (EXPECTED / BLOCKED)
- Must verify iOS Keychain reads/writes, native credentials picker rendering, Apple URL scheme deep-link routing, and Console log audits for credential exposure.

### Simulator Limitations
- Simulators are **NOT SUPPORTED** for verifying keystore-backed isolation, real platform credential managers, push notification receipts, or production keychain boundaries. Simulator checks are useful for UI layout and basic javascript logic validation, but **must never be treated as physical-device validation**.

### Required Validation Evidence
- Merged native pull requests require:
  - Playwright test status reports.
  - ADB/Console log sweeps proving zero credential leaks (`eyJ` patterns, access tokens).
  - Explicit device specifications (e.g., Android model, OS version).

---

## 10. Release Gate Definitions

- **Engineering Complete**: Code changes written, compiled, linted, and verified by Node/Playwright automated test suites.
- **Android Validated**: Code successfully deployed to a physical Android device and verified against the manual testing checklist.
- **iOS Blocked**: iOS-specific code/configuration is outstanding or cannot be verified due to lack of environment/credentials.
- **Hardware Blocked**: Validation is blocked due to the lack of physical target hardware (specifically, no physical iPhone).
- **Product Done**: Code meets all acceptance criteria, and physical validation checklist has passed on all supported platforms (Web, Android, and iOS).

---

## 11. No-Touch / Governance Rules
- **No Style Refactoring**: Code relating to security layers, storage boundaries, or session epochs must not be refactored for stylistic reasons.
- **No Token Storage Fallback**: Writing a JWT to native localStorage or sessionStorage as a fallback recovery path is strictly forbidden.
- **No Wildcard CORS**: Wildcard `*` CORS origins are prohibited on the backend.
- **Strict Device Verification**: No native feature may be marked as `Product Done` or merged to `main` without physical verification on both Android and iOS targets, unless a platform exclusion has been explicitly approved in writing.

---

## 12. Current Open Gates

The following items are active gates that remain open due to hardware limitations:
- **ISSUE-240 (GitHub ID: #329) - Physical iPhone Validation**: **Hardware-Blocked**. Android native login is validated, but iOS validation is blocked.
- **ISSUE-245 (GitHub ID: #334) - Session Transfer Validation**: **iOS Gate Open**. Android verification complete; final product sign-off is blocked by iOS validation.
- **ISSUE-246 (GitHub ID: #335) - Security Review Gate**: **iOS Gate Open**. Report merged, but final sign-off is blocked by ISSUE-240.

---

## 13. Acceptance Criteria for Future Native/Mobile Issues
1. Must define the validation scope up front (which platforms are in-scope).
2. Must specify physical device validation steps.
3. Must ensure that all custom exceptions fail closed.
4. Must run log scans to verify that no access tokens or raw credentials are leaked to local logs or console warnings.
