# Android Network Security Requirements

## Summary

This document defines the Android network security policy that must be satisfied before Android API communication is re-attempted. It is a policy definition only: no Android native file, Gradle file, manifest, or Capacitor configuration was changed while producing it.

Policy decision in brief:

- **HTTPS only.** Production and staging Android builds must talk to an HTTPS backend. A plain-HTTP LAN backend (e.g. `http://192.168.1.10:8000`, used in ISSUE-200/ISSUE-201) is **not** an acceptable release or staging target, and it is not sufficient for meaningful Android debug validation either.
- **No cleartext in release.** The release build must not enable cleartext traffic, globally or for any domain. `android:usesCleartextTraffic="true"` must never be added as a shortcut.
- **Certificates.** Production must use a publicly trusted TLS certificate (already true today via Railway). No custom/user-installed CA trust in release. Certificate pinning is explicitly deferred, not required now.
- **Network Security Config XML.** No `network_security_config.xml` exists today, and none is added by this issue. A path and manifest reference are proposed for a future fix issue, to be used only if a scoped debug-only cleartext exception is actually needed.
- This policy does not fix the ISSUE-201 CORS or Mixed Content blockers by itself. It defines the constraints the fix must operate within. Actual implementation is out of scope here.

## Background

ISSUE-201 validated Android-to-backend API communication and returned **NO-GO** for two independent reasons:

1. **CORS:** the backend rejects the Capacitor WebView origin `https://localhost` for every tested endpoint (`HTTP 400 Disallowed CORS origin`, no `Access-Control-Allow-Origin` header).
2. **Mixed Content:** the API target used during validation was `http://192.168.1.10:8000` (plain HTTP), while the Capacitor WebView loads the app at `https://localhost`. The WebView's Chromium engine blocked the real login XHR client-side with a Mixed Content error, before the request ever reached the network or the backend's CORS logic.

Before attempting a fix, this issue defines what a compliant Android network security policy actually requires, so that the fix in a later issue does not "solve" ISSUE-201 by weakening security (e.g. blanket cleartext, disabling TLS validation, or wildcard CORS).

## Current State

Inspected directly for this issue:

| Item | Finding |
| --- | --- |
| `frontend/android/app/src/main/AndroidManifest.xml` | No `android:usesCleartextTraffic` attribute. No `android:networkSecurityConfig` attribute on `<application>`. Declares `INTERNET` and `POST_NOTIFICATIONS` permissions only. |
| `frontend/android/app/src/main/res/xml/` | Contains only `config.xml` (Cordova/Capacitor widget config, unrelated to network security) and `file_paths.xml` (FileProvider paths). **No `network_security_config.xml` exists.** |
| Merged manifest (`./gradlew.bat :app:processDebugMainManifest` output, all three intermediate manifest artifacts) | Confirmed no `networkSecurityConfig` or `usesCleartextTraffic` attribute is injected by Capacitor, the push-notifications plugin, or any other dependency. |
| `frontend/android/variables.gradle` | `minSdkVersion = 24`, `compileSdkVersion = 36`, `targetSdkVersion = 36`. |
| `frontend/android/app/src/main/java/com/yeshmishak/app/MainActivity.java` | Unmodified `BridgeActivity` subclass with no body. No custom `WebSettings.setMixedContentMode()` call and no custom `TrustManager`/certificate-pinning code exists anywhere under `frontend/android`. |
| `frontend/capacitor.config.ts` | No `server.androidScheme` or `server.cleartext` override. Capacitor's default `androidScheme` is `"https"`, which is why the WebView origin is `https://localhost`. |
| `frontend/.env` (used for the ISSUE-200/201 debug build) | `VITE_API_URL=http://192.168.1.10:8000` — plain HTTP LAN address. |
| `frontend/.env.example` | `VITE_API_URL=http://localhost:8000` — HTTP, intended for local web browser development only. |
| `frontend/.env.staging.example` | `VITE_API_URL=https://yesh-mishak-api-staging.railway.app` — already HTTPS. |
| `docs/production-config-readiness.md` | Confirms web production already runs HTTPS end-to-end: frontend on Vercel (`https://yesh-mishak.vercel.app`), backend on Railway (`https://yesh-mishak-api.railway.app` or equivalent), and notes "Railway provides HTTPS by default." |

**Because `targetSdkVersion = 36` (well above the API 28 threshold where Android defaults `usesCleartextTraffic` to `false`) and no manifest attribute or Network Security Config overrides it, native OS-level cleartext traffic is already disabled by default for this app.** The ISSUE-201 failure was not caused by a native cleartext block — it was the WebView's own Mixed Content check, which is a separate mechanism (see "Network Security Config Decision" below). No regression exists today; the risk is a future change accidentally weakening this default.

## HTTPS Policy

**Decision: HTTPS-only for the API in every environment except a developer's own local web browser session.**

- Production and staging Android builds **must** use an HTTPS API base URL. An HTTP LAN backend (`http://192.168.1.10:8000` or any other private IP) is **not allowed** for release or staging builds.
- Android debug validation (installing a debug APK on a physical device or emulator to test real API calls) **must** use either:
  - a deployed HTTPS backend the team already operates (the Railway staging URL in `.env.staging.example`, or a dedicated Railway/other HTTPS preview environment), or
  - an HTTPS tunnel (e.g. a reverse-proxy tunnel such as Cloudflare Tunnel or ngrok) that fronts the local dev backend with a real TLS certificate, so the API target is `https://` even while iterating locally.
- Plain LAN HTTP (as used in ISSUE-200/ISSUE-201) may still be used for narrow, low-level reachability smoke tests (e.g. "can the phone's IP stack reach the dev machine's port 8000 at all") but must **not** be treated as a stand-in for real API/feature validation, because it cannot exercise the actual request path the WebView uses in production.

**Why an HTTP API from an HTTPS Capacitor WebView is not acceptable, even temporarily:**

1. Capacitor's default `androidScheme` is `https`, so the WebView always loads the app itself over `https://localhost`. Any XHR/fetch the app's JavaScript makes to a plain `http://` endpoint is a same-page HTTPS→HTTP request, which Chromium classifies as **active mixed content** and blocks outright, regardless of CORS headers. This was directly observed in ISSUE-201's logcat capture.
2. Downgrading the WebView origin to `http://` instead of fixing the API is not an acceptable alternative: it would remove Capacitor's default WebView origin protections, is inconsistent with Google's Play Store expectations for network security, and does not match how the app is actually distributed (the web production deployment is HTTPS end-to-end).
3. Relaxing the WebView's mixed-content enforcement in code (`WebSettings.setMixedContentMode(MIXED_CONTENT_ALWAYS_ALLOW)`) would be a deliberate security downgrade that allows any HTTP resource to load inside an otherwise-HTTPS page — this is explicitly out of scope and against this policy's intent.
4. Plaintext HTTP on a shared Wi-Fi network (the exact scenario in ISSUE-200/201) exposes API tokens, session data, and request/response bodies to anyone else on that network. This is unacceptable for authenticated endpoints such as `/auth/login`, regardless of whether the immediate blocker is CORS or Mixed Content.

## Certificate Requirements

- **Production backend must present a publicly trusted TLS certificate** issued by a CA already trusted by the Android system trust store (e.g. via Railway's managed TLS, which is already in place per `docs/production-config-readiness.md`). No action is required to obtain this — it already exists for the current Railway deployment.
- **No user-installed or custom CA trust in release.** The app must not add a Network Security Config `<trust-anchors>` override that trusts user-added or custom CAs in the release build. Android already excludes user-installed CAs from apps targeting API 24+ by default when no Network Security Config is present; this default must be preserved. A documented enterprise MDM/proxy-inspection use case would be required to justify any exception, and none exists for this project today.
- **Certificate pinning is deferred, not required now.** Rationale:
  - The current production backend (Railway) is a managed platform where the team does not control certificate issuance or rotation directly. Pinning against a specific certificate or public key introduces an operational risk: if Railway rotates the certificate (renewal, CA migration, infrastructure change) without the pin being updated and shipped in a new app release first, the app would hard-fail all API connectivity for every installed user until an app update is pushed and adopted.
  - Standard TLS chain-of-trust validation against the public CA system already protects against passive network eavesdropping and most on-path tampering, which is the primary threat this policy addresses today.
  - Pinning should be revisited if/when: the backend moves to infrastructure the team controls end-to-end (making rotation coordination feasible), the threat model expands to include sophisticated on-path MITM (e.g. targeted attacks, hostile network environments for the app's user base), or a compliance requirement mandates it. That evaluation is out of scope for this issue.

## Cleartext Traffic Policy

- **Release:** cleartext traffic is disabled, with no exceptions. No `android:usesCleartextTraffic="true"`, no Network Security Config `<base-config cleartextTrafficPermitted="true">`, and no domain-specific `<domain-config>` cleartext exception in the release build variant. This is already the default state today (see "Current State") and must not be changed.
- **Debug/local:** the preferred path is the same as production — use an HTTPS backend or HTTPS tunnel for the debug build too, so debug and release behave identically and no cleartext exception is ever needed.
  - An optional, narrowly-scoped **debug-only** cleartext exception may be added later *if and only if* HTTPS tunneling is genuinely impractical for a specific local workflow. If used, it must:
    - apply only to the `debug` build variant (a debug-specific Network Security Config, or a Network Security Config referenced only from a debug-variant manifest, never merged into `release`),
    - target one specific LAN host/IP by exact domain/IP entry (e.g. the developer machine's current LAN IP), never a wildcard or the whole `cleartextTrafficPermitted` base config,
    - be treated as a temporary developer convenience, not a supported production pattern.
  - No global cleartext flag and no wildcard/domainless cleartext `<domain-config>` are acceptable in any variant, debug included.
- **Important:** allowing cleartext for a host via Network Security Config does **not** by itself solve the ISSUE-201 Mixed Content failure. Network Security Config governs whether the Android OS network stack permits a cleartext *socket connection* to a given host (this affects native HTTP clients and, since Android 8, resource loads WebView delegates through the OS network stack). It does **not** change Chromium's separate Mixed Content policy, which blocks an HTTPS-loaded page's JavaScript from making an HTTP XHR/fetch call regardless of what the OS-level cleartext policy allows. Fixing Mixed Content requires either serving the API over HTTPS, or explicitly relaxing the WebView's mixed-content mode in native code (`MainActivity`/`WebSettings`) — the latter is a real security downgrade this policy does not recommend and this issue does not perform.

## Network Security Config Decision

**Decision: no `network_security_config.xml` file is added in this issue.**

Reasoning:
- This issue's scope is to define policy, not to implement a fix. Adding a Network Security Config file and wiring it into the manifest is an implementation action that belongs to the follow-up fix issue, once the team has decided whether a debug-only cleartext exception is actually needed (it may not be, if HTTPS tunneling is adopted instead).
- Adding the file now, unused or only partially justified, would risk exactly the kind of "quiet broad network work" this issue's hard rules prohibit.
- As shown above, a Network Security Config alone would not resolve the Mixed Content blocker from ISSUE-201, so adding it in isolation would not change the NO-GO outcome — it must be paired with either an HTTPS API target (preferred) or an explicit, separately-reviewed WebView mixed-content code change (not recommended).

If a debug-only cleartext exception is later approved by a follow-up issue, the proposed implementation is:

- **File path:** `frontend/android/app/src/main/res/xml/network_security_config.xml`
- **Proposed content shape** (illustrative only, not applied here):
  ```xml
  <?xml version="1.0" encoding="utf-8"?>
  <network-security-config>
      <base-config cleartextTrafficPermitted="false" />
      <domain-config cleartextTrafficPermitted="true">
          <domain includeSubdomains="false">192.168.1.10</domain>
      </domain-config>
  </network-security-config>
  ```
- **Manifest reference** (debug-variant only), on the `<application>` element in `frontend/android/app/src/main/AndroidManifest.xml` or a debug-source-set-specific manifest override:
  ```xml
  <application
      android:networkSecurityConfig="@xml/network_security_config"
      ...>
  ```
- The follow-up issue must confirm this reference is scoped so it never applies to the `release` build variant, and must re-state that this alone does not fix WebView Mixed Content — it would only be useful for any native (non-WebView) HTTP calls Capacitor plugins might make directly against the same LAN host.

## Environment Matrix

| Environment | Allowed API base URL scheme | Notes |
| --- | --- | --- |
| Local web development (browser, `npm run dev`) | `http://localhost:8000` (or `127.0.0.1`) | Acceptable. The dev server itself is also served over `http://localhost:5173`, so this is a same-scheme, same-machine loopback case with no Mixed Content exposure and no WebView involved. This is what `.env.example` already documents. |
| Android debug validation (physical device/emulator, debug APK) | `https://` only — deployed HTTPS backend (e.g. Railway staging) or an HTTPS tunnel to the local backend | Plain LAN HTTP (`http://192.168.1.x:8000`) must not be used for real feature validation; it is not representative of the release request path and is blocked by Mixed Content, as ISSUE-201 demonstrated. |
| Staging | `https://` only | Already the case: `frontend/.env.staging.example` points to `https://yesh-mishak-api-staging.railway.app`. |
| Production / release | `https://` only | Already the case for web (Vercel + Railway, per `docs/production-config-readiness.md`). Android release builds must use the same HTTPS production API URL; no HTTP fallback of any kind. |

Local HTTP (`http://localhost:8000`) is valid only for the local web browser development row above. It must never be treated as a release-valid or Android-debug-valid configuration.

## Relationship to ISSUE-201 Blockers

- **CORS blocker:** this policy does not change backend CORS configuration. It requires that whatever origin the Android WebView presents (`https://localhost`, per Capacitor's default `androidScheme`) be added to the backend's CORS allowlist as an explicit, non-wildcard entry, in a follow-up fix issue. This document does not perform that change.
- **Mixed Content blocker:** this policy directly addresses the root cause by requiring the API target to be HTTPS in every environment where the Capacitor WebView is used (debug validation, staging, production). Once the API base URL used by the Android build is `https://`, the page (`https://localhost`) and the API (`https://...`) share a secure scheme, and the Mixed Content block ISSUE-201 observed no longer applies. This document does not change the actual `VITE_API_URL`/`VITE_API_BASE_URL` value used by the Android build — that is implementation work for the follow-up issue.
- **What still needs implementing (explicitly out of scope here):**
  1. Add the exact Capacitor origin (`https://localhost`) to the backend's `CORS_ORIGINS` allowlist, through the backend's normal configuration process — not a code-level wildcard.
  2. Point the Android build's API base URL at an HTTPS backend (deployed staging/production Railway URL, or an HTTPS tunnel for local iteration) instead of the LAN HTTP address used in ISSUE-200/201.
  3. Only if genuinely needed after adopting HTTPS: add a scoped, debug-only Network Security Config cleartext exception as described above.
  4. Re-run an ISSUE-201-style validation (CORS preflight, real in-app login, fields/games/notifications) against the corrected HTTPS target to confirm a GO outcome.

## Risks

| Risk | Assessment |
| --- | --- |
| Team "fixes" ISSUE-201 by adding `android:usesCleartextTraffic="true"` globally | High impact if it happened — explicitly forbidden by this policy and by the issue's hard rules. |
| Team assumes a Network Security Config cleartext exception alone fixes Mixed Content | Would produce a false sense of resolution; explicitly called out as insufficient in this document. |
| Debug-only cleartext exception accidentally ships in release (e.g. via a shared manifest instead of a debug-only one) | Must be prevented structurally (debug-variant-only manifest/resource), not just by intent, when/if that exception is implemented. |
| Certificate pinning deferred indefinitely without documented threat-model review | Low risk today given standard CA trust is sufficient for the current threat model; should be revisited if the backend's operational model or threat model changes. |
| Local HTTP dev convenience gets carried into a staging/production config by copy-pasting `.env` values | `.env.example` already models HTTP only for local dev, and `.env.staging.example` already models HTTPS; this must remain true and be checked in any future PR touching environment config. |

## Required Follow-up Work

1. **Configure backend CORS** to explicitly allow the Capacitor origin `https://localhost` (and any other real app origins), without using a wildcard.
2. **Point the Android API target at an HTTPS backend** — either the existing Railway staging/production URL or a new HTTPS tunnel for local development iteration — replacing the LAN HTTP address used in ISSUE-200/ISSUE-201.
3. **Optional:** add a scoped, debug-only Network Security Config cleartext exception (path and manifest reference proposed above) only if HTTPS tunneling proves impractical for a specific workflow, with an explicit statement that it does not by itself resolve WebView Mixed Content.
4. **Revalidate Android API communication** (repeat ISSUE-201's login/fields/games/notifications validation) against the corrected HTTPS target and updated CORS allowlist, to confirm GO before proceeding with further native feature work.

## Final Verdict

**GO** — as a policy document.

This issue defines clear, unambiguous answers for HTTPS usage, certificate requirements, cleartext traffic, Network Security Config, and per-environment API URL scheme, and explicitly states that Network Security Config alone does not resolve WebView Mixed Content. The policy does not itself resolve the ISSUE-201 CORS or Mixed Content blockers — that implementation work is intentionally deferred to the follow-up issue(s) listed above — but the requirements needed to guide that fix without weakening security are now fully defined.
