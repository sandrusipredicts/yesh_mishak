# Android Google Authentication Configuration (ISSUE-238)

## Dependency

Implements the **NA-2 (Google Cloud console setup)** pre-implementation task defined by `docs/native-authentication-architecture.md` (ISSUE-237, PR #790). Per that architecture (ADR-3/ADR-4), the Android OAuth Client authorizes the device sign-in flow, while the **existing Web OAuth Client ID remains the `serverClientId`** and the expected token audience.

## Scope

Collect and record everything required to create the Android OAuth Client in Google Cloud Console: package name, signing mode, SHA-1/SHA-256 fingerprints, the existing Web OAuth Client ID reference, and the exact console steps — plus the status of each configuration item.

## Out of Scope

Native Login implementation, plugin installation, any backend/frontend/native/package change, `cap sync`, push notifications, release-keystore creation, Play App Signing enrollment.

## Configuration summary

| Item | Value / Status |
| --- | --- |
| Android package name | `com.yeshmishak.app` (verified in `frontend/capacitor.config.ts` `appId` and `frontend/android/app/build.gradle` `applicationId` — identical) |
| Current signing mode | **Debug only.** `gradlew signingReport` shows the release variant with `Config: null / Store: null` — no release signing config and no Play App Signing exist yet |
| Debug keystore | `%USERPROFILE%\.android\debug.keystore`, alias `AndroidDebugKey` (default credentials), certificate valid until 2056-06-21 |
| Debug SHA-1 | `44:74:72:31:C5:EF:83:3F:8F:9F:94:82:97:49:C6:E5:BE:48:84:9B` |
| Debug SHA-256 | `5F:32:96:5D:E2:FF:3D:2C:C0:5C:7E:5D:D7:77:AF:0D:14:EE:F9:77:64:98:55:41:84:D9:D3:C3:C0:EA:5E:73` |
| Fingerprint source | `frontend/android> .\gradlew.bat signingReport` (run 2026-07-03; debug/debugAndroidTest variants identical, as expected — same keystore) |
| Release SHA-1 / SHA-256 | **Do not exist yet** — no release keystore is configured. Must be collected separately when release signing is set up; **never assume they equal the debug values** |
| Play App Signing SHA-1 / SHA-256 | **Not applicable yet** — app not enrolled; when enrolled, Google's app-signing certificate fingerprints (from Play Console → App integrity) must be added to the same Android OAuth Client |
| Google Cloud project | Project number `936888694089` (identifiable from the existing client ID prefix; full project name intentionally not recorded here) |
| Existing Web OAuth Client ID (the ISSUE-237 `serverClientId`) | `936888694089-fu96…h71.apps.googleusercontent.com` (partially redacted; full value lives in `frontend/.env` as `VITE_GOOGLE_CLIENT_ID` and mirrors backend `google_client_id`) — **must remain unchanged** |
| Android OAuth Client ID | **CREATED (2026-07-03, by the account owner):** `936888694089-f3hrv6kpiotr9u8ggl7pd0mi2t987er1.apps.googleusercontent.com` |
| SHA-1 added to Android OAuth Client | **YES** — the debug SHA-1 above was entered at client creation (the Android client form requires it) |
| OAuth consent screen status | **Testing** (publishing status) |
| Test users configured | **YES** (emails redacted — managed in the console by the account owner) |
| OAuth access restricted to test users | **YES** — while in Testing, only the configured test users can complete Google sign-in |
| SHA-256 recorded | **YES — recorded here for audit/future compatibility.** Google Cloud's Android OAuth Client form takes SHA-1 only; SHA-256 is documented for Play App Signing/asset-links future use |
| Validation target | Samsung SM-S928B (Galaxy S24 Ultra), Android 16 — the device used for all prior certifications; runs **debug-signed** builds, so the debug fingerprints above are the ones that matter for NA-3/NA-V validation. **Because the consent screen is in Testing, Samsung validation must sign in with one of the configured test users** |

**No secrets are recorded in this document:** certificate fingerprints and OAuth client IDs are public identifiers; keystore passwords listed below are the well-known Android debug defaults; no private keys, API secrets, or tokens appear here.

## Google Cloud Console steps (operator runbook — execute as the account owner)

1. Open **Google Cloud Console** (`console.cloud.google.com`).
2. Select the **same project** that owns the existing Web OAuth client (project number `936888694089` — verify the prefix of `VITE_GOOGLE_CLIENT_ID` matches).
3. Go to **APIs & Services → Credentials**.
4. Confirm the **OAuth consent screen** is configured (it must be — the existing web Google login works in production).
5. Click **Create Credentials → OAuth client ID**.
6. Application type: **Android**.
7. Package name: `com.yeshmishak.app`
8. SHA-1 certificate fingerprint: `44:74:72:31:C5:EF:83:3F:8F:9F:94:82:97:49:C6:E5:BE:48:84:9B`
9. Save the Android OAuth Client.
10. Record the resulting **Android OAuth Client ID** in this document — **DONE** (recorded above, 2026-07-03).
11. SHA-256: the Android client form does not take it; it is recorded in this document as the audit reference (step complete).
12. Confirm the **existing Web OAuth Client ID remains unchanged** — **CONFIRMED**; it continues to serve as the `serverClientId` per ISSUE-237 ADR-3, and nothing about the web client was edited.

**Runbook executed by the account owner on 2026-07-03.** Additional outcome: the OAuth consent screen publishing status is **Testing** with test users configured, so sign-in is restricted to those test users until the app is moved to Production.

Fingerprint re-collection commands (for future keys/machines):

```powershell
# Preferred (from the Android project):
cd frontend/android
.\gradlew.bat signingReport

# Fallback (default debug keystore, well-known default credentials):
keytool -list -v -keystore "%USERPROFILE%\.android\debug.keystore" -alias androiddebugkey -storepass android -keypass android
```

Note: this machine's debug keystore alias reports as `AndroidDebugKey` (case-insensitive match to the default `androiddebugkey`).

## Risks / follow-up items

1. ~~BLOCKING: Android OAuth Client creation~~ — **RESOLVED 2026-07-03:** the Android OAuth Client was created by the account owner and is recorded above. NA-3 is no longer blocked by NA-2.
2. **Testing-mode restriction (accepted for this phase):** the consent screen is in **Testing**, so only configured test users can sign in. This is sufficient for NA-3 development and NA-V Samsung validation (which must use a test user), but **the publishing status must move to Production before native Google login ships to real users** — carry this as a release-gate follow-up item.
3. **Debug-keystore locality:** the debug SHA-1 above belongs to *this development machine's* keystore. Building the APK on another machine/CI produces a different debug fingerprint that must be added to the same Android OAuth Client as an additional fingerprint entry.
4. **Release signing (future):** before any release build ships with native Google login, a release keystore (or Play App Signing) must be created and its SHA-1 added to the Android OAuth Client. Tracked as part of the existing release-readiness work, not this phase.
5. `.env` remains the source of truth for the full web client ID; do not duplicate the full value into more places than necessary.

## Final checklist

| Item | Status |
| --- | --- |
| Package name confirmed (`com.yeshmishak.app`, capacitor + gradle agree) | ✅ |
| Signing mode identified (debug only; release/Play App Signing not configured) | ✅ |
| Debug SHA-1 collected via `gradlew signingReport` | ✅ |
| Debug SHA-256 collected and recorded | ✅ |
| Release / Play App Signing fingerprints | N/A yet — explicitly documented as separate future values |
| Web OAuth Client ID referenced as `serverClientId` (unchanged) | ✅ |
| Google Cloud project identified (by number) | ✅ |
| Console runbook with paste-ready values | ✅ |
| Android OAuth Client created (ID recorded) | ✅ (2026-07-03, by account owner) |
| SHA-1 added to Android OAuth Client | ✅ |
| OAuth consent screen status recorded (Testing) | ✅ |
| Test users configured; access restricted to test users | ✅ |
| Samsung validation constrained to a configured test user | ✅ (recorded as a validation requirement) |
| No secrets committed | ✅ |
| No implementation/plugin/protected-path changes | ✅ |

## Final verdict

**GO.** The NA-2 configuration is complete: package name, debug SHA-1/SHA-256, and signing mode are verified and recorded; the Android OAuth Client exists with the debug SHA-1 registered and its client ID recorded above; the existing Web OAuth Client ID is confirmed unchanged as the `serverClientId`; the OAuth consent screen is in **Testing** with test users configured, which is sufficient for development and device validation. **NA-3 (native Google login implementation) is unblocked**, subject to two standing constraints: (1) Samsung SM-S928B validation must sign in with one of the configured test users while the consent screen remains in Testing; (2) moving the publishing status to Production is a release-gate follow-up before native Google login ships to real users.
