# Android API Configuration

## Summary

This document describes how Android (Capacitor) builds are configured to talk to the backend, and the two fixes that resolved the ISSUE-205 API Communication NO-GO:

1. **Backend CORS** now explicitly allows the Capacitor Android WebView origin `https://localhost`.
2. **Android builds use a dedicated `vite --mode android` environment** (`frontend/.env.android`, git-ignored) so the API target is always an HTTPS backend, never a developer's plain-HTTP LAN address.

Both were validated end-to-end on a physical device: CORS preflight now returns `200` with `Access-Control-Allow-Origin: https://localhost` for every previously-failing endpoint, and a real login submitted through the installed app's UI succeeded (the app transitioned from the login screen to onboarding after receiving a real JWT), with no Mixed Content or CORS errors in logcat.

**ISSUE-207 update:** independently re-validated on `main` after ISSUE-206 merged, this time against the app's real, permanent, live production backend rather than a temporary tunnel. Neither `frontend/.env.staging.example`'s staging URL nor the guessed production URL in `docs/production-config-readiness.md` are actually live (both resolve only to Railway's placeholder page); the real production API URL, `https://yeshmishak-production.up.railway.app`, was recovered from the live `https://yesh-mishak.vercel.app` web app's own JS bundle and confirmed reachable (`{"status":"ok"}`). CORS preflight against this real backend already passes for all 6 endpoints — Railway auto-deploys from `main`, so no manual deployment step was needed. A fresh device install pointed at this real backend rendered live production field markers on the map from a genuine `GET /fields/` call, with zero CORS/Mixed Content/fatal errors in the full-session logcat. No production data was written during this validation. `frontend/.env.android.example` was updated to reference this confirmed-live URL. See `docs/android-project-readiness-review.md` for the complete evidence and the final Android Foundation COMPLETE decision.

## What Changed

### 1. Backend CORS (`backend/app/main.py`)

The backend already hardcoded a small set of always-allowed local development origins (Vite dev server ports) regardless of the `CORS_ORIGINS` environment variable. A second, similarly-unconditional entry was added for the Capacitor Android origin:

```python
# The Capacitor Android WebView always loads the bundled app from this fixed
# origin (Capacitor's default androidScheme is "https"), in every build
# variant including release. Browsers set the Origin header from the actual
# page origin, so only the app's own WebView can send this Origin - it is
# not a wildcard and does not expose the API to arbitrary websites.
for mobile_app_origin in ("https://localhost",):
    if mobile_app_origin not in cors_origins:
        cors_origins.append(mobile_app_origin)
```

This applies in every environment (local, staging, production) because the same Capacitor app — including release builds — always loads from `https://localhost`. It is a single fixed literal origin, not a wildcard: a browser sets the `Origin` header from the page's own origin, so no arbitrary external website can spoof this value. This is the standard, widely-used approach for allowing a hybrid app's own WebView to call its backend.

No `CORS_ORIGINS` environment variable change was required or made; this entry is unconditional in code, matching the existing pattern for the other hardcoded dev origins.

### 2. Android-specific build environment (frontend)

Previously, an Android build used whatever `frontend/.env` happened to be present locally — which is how a plain-HTTP LAN address (`http://192.168.1.10:8000`) ended up baked into the app in ISSUE-200/201, triggering Mixed Content blocking (the Capacitor WebView always loads at `https://localhost`, so an HTTP API target is always a scheme mismatch).

Two small additions fix this without touching the existing local-dev workflow:

- **`frontend/package.json`**: added a `build:android` script:
  ```json
  "build:android": "vite build --mode android"
  ```
- **`frontend/.env.android.example`** (new, committed, safe): a template for a git-ignored `frontend/.env.android` file. Vite automatically loads `.env.android` when building with `--mode android`, and mode-specific values override the plain `.env` for the same keys — so a developer's regular `.env` (used for local browser development) is never touched or required to change.
- **`.gitignore`**: added `.env.android` alongside the existing `.env` entry, so a real, filled-in `frontend/.env.android` is never committed.

To build for Android:
```powershell
cd frontend
copy .env.android.example .env.android   # first time only, then fill in real values
npm run build:android
npx cap sync android
```

`frontend/.env.example` (used for local browser development) is unchanged — `http://localhost:8000` remains correct there, because both the dev server and the API are same-scheme `http://localhost`, so there is no Mixed Content concern in a plain browser tab.

## Environment Matrix

| Environment | Command | API URL source | Scheme |
| --- | --- | --- | --- |
| Local browser dev | `npm run dev` | `frontend/.env` | `http://` (same-scheme as the dev server; fine) |
| Android build/validation | `npm run build:android` | `frontend/.env.android` (git-ignored, from `.env.android.example`) | **Must be `https://`** |
| Production/staging web | Vercel-injected env vars | Vercel dashboard | `https://` |

**Never put a personal LAN IP or plain `http://` address in a committed file.** `frontend/.env.android.example` intentionally ships with a placeholder-safe HTTPS value as an example, not a LAN address, and the real `frontend/.env.android` is git-ignored.

## Validation Performed

All commands were run fresh on this issue's branch, on a physical Samsung SM-S928B device.

| Step | Command | Result |
| --- | --- | --- |
| Backend CORS preflight (all 6 previously-failing endpoints from ISSUE-201) | `curl -X OPTIONS ... -H "Origin: https://localhost"` against `/auth/login`, `/auth/google`, `/fields/`, `/games/active`, `/notifications`, `/notifications/push-token` | All return `200 OK` with `Access-Control-Allow-Origin: https://localhost` (previously `400 Disallowed CORS origin`) |
| Backend test suite | `python -m pytest -q` | 631 passed, no regressions |
| Frontend build (Android mode) | `npm run build:android` | Bundle contains the configured HTTPS URL; verified zero occurrences of `192.168` or any `http://` API target in the built JS |
| Frontend lint | `npx eslint .` | Clean |
| Capacitor sync | `npx cap sync android` | Assets copied, push-notifications plugin detected |
| Android debug build | `gradlew.bat assembleDebug` (Android Studio JBR Java 21) | `BUILD SUCCESSFUL` |
| Install/launch | `adb install -r` + `adb shell monkey ...` | App installed, launched, `MainActivity` resumed, no fatal exceptions |
| **Real login through the installed app's UI** | Typed real credentials into the actual login form, tapped the login button | App showed "מתחבר..." (logging in), then transitioned to the onboarding screen — proof a real `POST /auth/login` succeeded and returned a usable JWT |
| Logcat during the successful login | `adb logcat -d -v time` | Zero `CORS`, zero `Mixed Content`, zero `FATAL EXCEPTION` entries; only an unrelated, pre-existing push-notification warning (`Notification is not defined`, expected in a WebView without native push wiring) |

Because the app's own build-time API target for this validation pass was the local dev backend (exposed over HTTPS through a temporary tunnel for testing purposes only — not committed anywhere), this proves the fix generically: any HTTPS backend reachable from the device, combined with the new CORS entry, resolves both blockers. Real day-to-day Android builds should point `frontend/.env.android`'s `VITE_API_URL` at a real, team-operated HTTPS backend (e.g. a deployed staging/production URL) rather than a temporary tunnel.

## Why This Is Not an Insecure Workaround

- No global or wildcard CORS origin was added — only the one, fixed, non-spoofable Capacitor origin.
- No cleartext traffic was enabled anywhere (the ISSUE-203 Network Security Config, which disables cleartext and trusts only system CAs, is untouched).
- No `android:usesCleartextTraffic` attribute was added.
- No LAN IP or secret was committed; `.env.android` is git-ignored and `.env.android.example` contains only a placeholder-safe HTTPS example.
- Package ID, Gradle configuration, and Capacitor app identity were not changed.

## Follow-up

- `frontend/.env.android.example` now points at the confirmed-live production backend (`https://yeshmishak-production.up.railway.app`, discovered and verified in ISSUE-207). `frontend/.env.staging.example`'s URL still does not resolve to an active deployment — standing up a real, dedicated staging backend is recommended so routine Android development doesn't need to target production directly.
- Consider adding an automated check (CI or a pre-build script) that fails the Android build if `VITE_API_URL` in the active environment does not start with `https://`, to prevent this regression from recurring.
- Consider updating `docs/production-config-readiness.md`'s guessed production URL to the confirmed real one, since they currently disagree (the guessed URL is not live; the real one is `https://yeshmishak-production.up.railway.app`) — out of scope for this document, flagged for a documentation-cleanup follow-up.
