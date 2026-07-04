# Android Native Google Sign-In Plugin Selection (NA-1)

## Dependency

Executes the **NA-1 (technology selection)** blocking pre-implementation task defined by `docs/native-authentication-architecture.md` (ISSUE-237, PR #790), using the credentials configured by `docs/android-google-authentication-configuration.md` (ISSUE-238, PR #791). GitHub ISSUE-239 is an iOS-credentials task and is **not** this step; NA-1 is tracked as its own documentation-only branch/PR per the repository owner's instruction.

## Scope

Evaluate the candidate technologies for obtaining a Google ID token natively on Android, select one official technology for ISSUE-240, and verify the ISSUE-237 load-bearing `serverClientId`/audience assumption against current official sources.

## Out of Scope

Implementation, plugin installation, `cap sync`, any change to package files, native projects, frontend source, backend, iOS, or push notifications.

## Executive Summary

**Selected: `@capgo/capacitor-social-login` v8 (Google provider only).** It is the actively maintained, Capacitor-8-matched plugin that implements Google sign-in through the **Android Credential Manager**, requests the **Google ID token** using the existing **Web OAuth Client ID as `serverClientId`** (exactly ISSUE-237 ADR-2/ADR-3), supports provider sign-out for the logout requirement, and is the officially recommended migration target away from the archived Codetrix plugin. The `serverClientId`/audience assumption is confirmed by current official documentation, so **ISSUE-240 is UNBLOCKED** and **NA-B1 (backend audience change) remains conditional only** — pending final on-device proof during ISSUE-240 validation, per the ISSUE-237 caveat.

## Plugin governance policy reference

Per `docs/native-plugin-governance-policy.md` (ISSUE-186): native Google sign-in requires native device capability (Credential Manager) that web code cannot access from the WebView (the GIS web flow is empirically broken there — ISSUE-236), so a plugin is justified; this document is the required deliberate-selection review. The evaluation below covers the policy's criteria (native necessity, web-API insufficiency, maintenance, security, complexity).

## Evaluation criteria

1. Capacitor 8 compatibility (project uses Capacitor 8.4.1, minSdk 24 / target 36)
2. Android Credential Manager support (ISSUE-237 ADR-2)
3. Google ID token support (raw, backend-verifiable)
4. `serverClientId` / Web OAuth Client ID support and expected token audience (ADR-3)
5. Relationship to the ISSUE-238 Android OAuth Client
6. Provider logout / credential-state clearing (ADR-8)
7. Maintenance status and documentation quality
8. Security considerations
9. Implementation complexity and build-compatibility risk
10. Known deprecations / migration concerns

## Candidate comparison table

| Criterion | 1. `@capgo/capacitor-social-login` v8 | 2. `@codetrix-studio/capacitor-google-auth` | 3. Capawesome `@capawesome/capacitor-google-sign-in` | 4. Browser Redirect (custom OAuth) | 5. Direct Credential Manager (custom native code) |
| --- | --- | --- | --- | --- | --- |
| Capacitor 8 | ✅ major version tracks Capacitor (v8 line) | ❌ documented support up to Capacitor 6; last publish ~2 years ago (3.4.0-rc.4) | ✅ current | N/A (no plugin) | ✅ (custom) |
| Credential Manager | ✅ | ❌ deprecated GMS Auth library | ✅ | ❌ (browser OAuth) | ✅ (by definition) |
| Raw Google ID token | ✅ | ✅ (legacy API) | ✅ (explicitly not verified client-side; backend verifies) | ✅ (via code exchange — different shape) | ✅ |
| Web client ID as `serverClientId` → backend-verifiable audience | ✅ documented | ⚠️ legacy equivalent existed, but moot | ✅ documented ("web client ID … serves as the server client ID that the Credential Manager API uses to request an ID token") | ❌ different flow (auth code + redirect URI) | ✅ (caller-controlled) |
| Provider sign-out | ✅ logout/credential clearing supported | ⚠️ signOut existed (legacy) | ✅ | N/A | ✅ (clearCredentialState) |
| Maintenance | ✅ active (Cap-go org); official Codetrix migration guide | ❌ "virtually archived", maintainer unreachable | ✅ active, but **sponsorware** (Insiders-first release, private registry access) | N/A | ⚠️ becomes **our** native code to maintain |
| Docs quality | ✅ dedicated Android Google guide | ⚠️ stale | ✅ high | ⚠️ scattered | ❌ none (we'd write them) |
| Complexity / build risk | Low–moderate (plugin install + `serverClientId` config) | Moderate + compatibility debt | Low–moderate + registry/sponsorship setup | High (deep links, redirect handling, app-switch UX) | High (Kotlin bridge, gradle deps, upkeep) |
| Deprecation concerns | None known; built on the platform-recommended API | ❌ built on deprecated GMS; migration guide points to Capgo | None known | Google discourages WebView OAuth; Custom-Tabs flow allowed but inferior UX | Tracks the platform API directly |
| **Decision** | **SELECTED** | **REJECTED** | **FALLBACK ONLY** | **REJECTED** (already rejected in ISSUE-237 ADR-1) | **FALLBACK ONLY** |

## Detailed evaluation

### 1. `@capgo/capacitor-social-login` v8 — SELECTED

Active plugin from the Cap-go organization; its major version explicitly tracks Capacitor's (v8 for Capacitor 8). Android implementation uses the **AndroidX Credential Manager** (the platform-recommended replacement for the deprecated GMS sign-in library). Its documentation states the **web client ID serves as the server client ID** used to request the ID token — matching ISSUE-237 ADR-3 exactly, so the returned **Google ID token** is expected to carry the existing Web OAuth Client ID as `aud`, verifiable by the unchanged backend `verify_google_token`. Supports provider logout/credential clearing (ADR-8). It is the documented migration target from the Codetrix plugin (`MIGRATION_CODETRIX.md` in its repository). MIT-licensed, freely installable from the public npm registry. Security posture: the plugin only brokers the platform credential flow; the ID token is verified server-side (unchanged). Complexity: plugin install, `serverClientId` initialization, one login call, one logout call. Build risk: low — Capacitor-8-matched; exact gradle/AGP fit is confirmed at install time in ISSUE-240 (standard risk for any plugin).

### 2. `@codetrix-studio/capacitor-google-auth` — REJECTED

Historically the most-used option, but effectively **archived**: the maintainer is unreachable, the last publish (3.4.0-rc.4) is roughly two years old, documented support stops at Capacitor 6, and the Android implementation depends on the **deprecated GMS auth library** rather than Credential Manager. Its own ecosystem points users to the Capgo plugin via an official migration guide. Adopting it would violate the governance policy's maintenance criterion on day one.

### 3. Capawesome `@capawesome/capacitor-google-sign-in` — FALLBACK ONLY

Technically excellent and current: Credential Manager on Android, web client ID as `serverClientId` for the ID token, explicit backend-verification guidance, MIT license. Rejected as the primary choice for **distribution/access reasons**: Capawesome follows a **sponsorware** model — new plugins release first to Insiders sponsors through a private npm registry — adding a sponsorship/registry dependency to the build pipeline that the Capgo plugin avoids. It is the designated **fallback** if NA-1's selection fails in practice (e.g., ISSUE-240 hits a blocking defect in the Capgo plugin), since it satisfies every technical criterion including the audience assumption.

### 4. Browser Redirect / custom OAuth redirect — REJECTED

Already rejected at the architecture level (ISSUE-237 ADR-1, "Browser Redirect"): requires deep-link/redirect infrastructure the app doesn't have, adds an app-switch to the login UX, returns an auth code (a different exchange contract than the backend's ID-token endpoint), and provides nothing over the platform-native flow. Nothing in this evaluation changes that verdict.

### 5. Direct Android Credential Manager implementation (no plugin) — FALLBACK ONLY

Writing our own thin Kotlin bridge over the Credential Manager API gives full control, zero third-party dependency, and trivially guarantees the `serverClientId` behavior. Rejected as primary because it converts a solved packaging problem into **permanent first-party native maintenance** (Kotlin code, gradle dependencies, API churn tracking) that the governance policy weighs against, and the team's delivery so far is web/Capacitor-centric. Retained as the **second fallback** if both plugins prove unusable — the architecture's contract (ID token in, nothing else changes) makes swapping to it non-disruptive.

## Selected technology

**`@capgo/capacitor-social-login` v8, Google provider, Android only** (iOS remains excluded per platform policy). Installation, initialization with `serverClientId` = the existing Web OAuth Client ID, login, and provider sign-out are all deferred to ISSUE-240.

## Rejected alternatives and reasons

See the table and detailed sections above: Codetrix (archived + deprecated GMS + no Capacitor 8), Browser Redirect (ADR-1 rejection stands), Capawesome (fallback #1 — sponsorware/registry access), direct native implementation (fallback #2 — first-party maintenance burden).

## serverClientId / ID-token audience assessment (the ISSUE-237 load-bearing assumption)

**Question:** can the selected technology request a Google ID token using the existing **Web OAuth Client ID** as `serverClientId`, so the backend keeps its current `verify_google_token` single-audience check without changes?

**Answer: YES — expected to work.** The selected plugin's official documentation states the web client ID serves as the server client ID for the Credential Manager ID-token request; Google's Credential Manager/Sign-in-with-Google documentation defines `serverClientId` as the audience of the returned ID token; and the fallback plugin's documentation independently confirms the same pattern. Per the ISSUE-237 caveat (as amended in PR #790), this remains an **expectation until proven on-device**: the ISSUE-240 Samsung SM-S928B validation must confirm the backend accepts the native token. **NA-B1 (backend audience list) is therefore NOT required now and stays conditional** — it activates as a blocking follow-up only if the on-device exchange fails audience verification.

## Android OAuth Client relationship (ISSUE-238)

The Android OAuth Client created in ISSUE-238 (`936888694089-f3hrv6kpiotr9u8ggl7pd0mi2t987er1.apps.googleusercontent.com`, package `com.yeshmishak.app`, debug SHA-1 registered) is what **authorizes the device** to use Credential Manager sign-in for this app; it is **not** passed to the plugin and is **not** the token audience. The plugin is configured only with the **Web OAuth Client ID** as `serverClientId`. Both clients live in the same Google Cloud project (`936888694089`). Constraint carried from ISSUE-238: the OAuth consent screen is in **Testing**, so ISSUE-240 validation must sign in with a configured test user.

## Logout / provider sign-out assessment

The selected plugin exposes provider logout/credential-state clearing, satisfying ISSUE-237 ADR-8: app logout (certified ISSUE-231/233 cleanup) is followed by a best-effort provider sign-out so the next login shows the account picker instead of silently reusing the previous account. Failure of the provider sign-out is non-fatal (redacted log only).

## Security considerations

1. The Google ID token remains exchange-only: never persisted, never logged (same redaction rules as `secure_storage.*` events); the plugin holds it only in memory during the flow.
2. Backend verification is unchanged: signature, audience, and `email_verified` checks stay server-side; the client trusts nothing in the token.
3. The plugin adds no Android permissions beyond Google Play services usage; the exact manifest/gradle delta will be reviewed in the ISSUE-240 PR diff (governance policy: permission bloat check).
4. Account linking, JWT model, and session pipeline are untouched (ISSUE-237 ADR-5/9).

## Implementation risks

| Risk | Mitigation |
| --- | --- |
| Gradle/AGP incompatibility at install (Capacitor 8.4.1, target 36) | Surfaces immediately in `assembleDebug`; fallback #1 (Capawesome) satisfies identical criteria |
| ID-token audience differs from expectation on device | ISSUE-240 validation step; NA-B1 activates as blocking backend follow-up |
| Consent screen in Testing blocks non-test users | Validation uses a configured test user (ISSUE-238); Production publishing is a release gate |
| Play services unavailable on device | Plugin failure path → Google option disabled with translated notice; manual login unaffected (ISSUE-237 failure map) |
| Plugin regression in future versions | Version-pin in package.json; governance policy review on upgrades |

## ISSUE-240 implementation contract

1. Install `@capgo/capacitor-social-login` (v8 line, version-pinned) — the only package.json change; `npx cap sync android` justified as a native-dependency change.
2. Initialize the Google provider with `serverClientId` = existing Web OAuth Client ID (from `VITE_GOOGLE_CLIENT_ID`).
3. Native login path in `LoginPage` behind `Capacitor.isNativePlatform()`: plugin login → obtain **Google ID token** → existing `loginWithGoogle(idToken)` → existing `saveAuthSession` (certified pipeline). Web GIS flow untouched.
4. Logout: existing `handleLogout` + best-effort provider sign-out.
5. Error handling per the ISSUE-237 failure map: cancellation silent; plugin/network/backend failures → translated error (en+he); no partial session ever.
6. Validation on Samsung SM-S928B with a configured test user, including the audience-assumption proof, session restore, logout/provider sign-out, and the standard logged-out relaunch checks.

## Final checklist

| Item | Status |
| --- | --- |
| All five candidates evaluated against all criteria | ✅ |
| Official technology selected | ✅ `@capgo/capacitor-social-login` v8 |
| Rejected alternatives documented with reasons | ✅ |
| serverClientId / audience assumption explicitly evaluated with sources | ✅ YES-expected; on-device proof in ISSUE-240 |
| ISSUE-238 Android OAuth Client relationship explained | ✅ |
| Provider sign-out assessed | ✅ |
| ISSUE-240 contract defined | ✅ |
| ISSUE-240 blocked/unblocked stated | ✅ UNBLOCKED |
| NA-B1 requirement stated | ✅ conditional only |
| No implementation / package / native / source / backend / iOS changes | ✅ |

## Final verdict

**GO.**

- **Official selected technology:** `@capgo/capacitor-social-login` v8 (Google provider, Android).
- **Why:** actively maintained and Capacitor-8-matched; Android Credential Manager implementation (ADR-2); documented `serverClientId` = Web OAuth Client ID behavior (ADR-3); provider sign-out (ADR-8); public npm/MIT with no registry or sponsorship dependency; official migration target from the archived Codetrix plugin.
- **Rejected:** `@codetrix-studio/capacitor-google-auth` (archived, deprecated GMS, no Capacitor 8); Browser Redirect (ISSUE-237 ADR-1 stands). **Fallbacks:** Capawesome plugin (sponsorware access model), direct Credential Manager native implementation (first-party maintenance burden).
- **serverClientId / backend audience compatibility:** expected to work per current official documentation of both the selected and fallback plugins; final proof on-device in ISSUE-240.
- **ISSUE-240: UNBLOCKED** (NA-1 and NA-2 both resolved).
- **NA-B1:** NOT required now — conditional only, activating as a blocking backend follow-up solely if ISSUE-240 device validation disproves the audience expectation.
- **No implementation was performed; no package, native, frontend-source, backend, or iOS files changed** — this branch contains exactly one documentation file.

Sources: [Cap-go/capacitor-social-login](https://github.com/Cap-go/capacitor-social-login) · [Capgo Android Google login docs](https://capgo.app/docs/plugins/social-login/google/android/) · [@capgo/capacitor-social-login on npm](https://www.npmjs.com/package/@capgo/capacitor-social-login) · [Codetrix→Capgo migration guide](https://github.com/Cap-go/capacitor-social-login/blob/main/MIGRATION_CODETRIX.md) · [CodetrixStudio/CapacitorGoogleAuth](https://github.com/CodetrixStudio/CapacitorGoogleAuth) · [@codetrix-studio/capacitor-google-auth on npm](https://www.npmjs.com/package/@codetrix-studio/capacitor-google-auth) · [Capawesome Google Sign-In plugin docs](https://capawesome.io/docs/sdks/capacitor/google-sign-in/) · [Capawesome Insiders/sponsorware model](https://capawesome.io/insiders/) · [Capawesome "How to Sign In with Google Using Capacitor"](https://capawesome.io/blog/how-to-sign-in-with-google-using-capacitor/)
