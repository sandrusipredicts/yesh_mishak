# Secure Storage Technology Selection (ISSUE-228)

## 1. Purpose

Select the secure storage technology that implements the "secure tier" defined in `docs/secure-storage-architecture.md` (ISSUE-227). This document evaluates the candidates against the criteria from the issue (Security, Maintenance, Community Support, Capacitor Compatibility) plus the architecture-fit constraints, and records a recommendation.

**The recommendation in this document is pending user approval. No package is installed and no code is changed by this issue.**

## 2. Scope

- Evaluation of secure storage technologies for the Android (Capacitor) app and the web build.
- A scored comparison, a recommended solution, a runner-up, and rejection rationale for the rest.

## 3. Non-goals

- No package installation; `package.json` and `package-lock.json` are unchanged.
- No implementation (ISSUE-229), no auth behavior changes, no frontend/backend/native code changes.
- No iOS validation. Candidates' iOS behavior is mentioned as informational only and does not drive the decision (hard constraint from the approved architecture, section 16).
- No re-opening of ISSUE-227 architecture decisions.

## 4. Inputs from ISSUE-226 Audit

- The access token and profile fields currently live in plain `localStorage`, including inside the native WebView — nothing is Keystore-backed today.
- No storage plugin of any kind is installed (`frontend/package.json`: Capacitor 8.4.1 core/android/ios/push-notifications only).
- Five call sites access storage directly; the abstraction (ISSUE-227, section 8) will be the only consumer of whatever technology is selected.

## 5. Inputs from ISSUE-227 Architecture

The selected technology must:

1. Provide the **secure tier**: hardware/OS-backed secret storage on Android (Keystore).
2. Sit **behind the storage abstraction** — its API shape must map onto `getToken/setToken/clearToken/...`.
3. Support **fail-closed** behavior: storage failures must be detectable (surfaced as errors, not silent fallback).
4. Coexist with the **web fallback tier**: the web build must keep working, with `localStorage` allowed only behind the abstraction.

## 6. Technology Selection Criteria

From the issue: Security, Maintenance, Community Support, Capacitor Compatibility. Refined into measurable criteria:

- **A. Security** — Android Keystore-backed; no plaintext secrets on Android; no silent insecure fallback on Android; per-app isolation; failures detectable.
- **B. Maintenance** — recent releases; active repository; low abandonment risk; documentation quality; TypeScript support.
- **C. Community support** — adoption signals (stars/usage); issue responsiveness; compatibility reports.
- **D. Capacitor compatibility** — declared Capacitor 8.x support; clean React/Vite/Capacitor integration; minimal native complexity; predictable Android builds (project: minSdk 24, target/compile SDK 36).
- **E. Web fallback** — web build must not break; fallback routes through the abstraction; web `localStorage` acceptable for browser compatibility only.
- **F. Cost/license** — free/open-source strongly preferred; commercial only with explicit approval.

## 7. Candidate Summary

| # | Candidate | Type | License | Latest release |
| --- | --- | --- | --- | --- |
| 1 | `@capacitor/preferences` | Official Capacitor plugin | MIT | 8.0.1 (2026-02-12) |
| 2 | `capacitor-secure-storage-plugin` (martinkasa) | Community plugin | MIT | 0.13.0 (2026-01-10) |
| 3 | `@aparajita/capacitor-secure-storage` | Community plugin | MIT | 8.0.0 (2026-02-10) |
| 4 | Ionic Identity Vault | Commercial (Ionic enterprise) | Proprietary, paid subscription | — |
| 5 | Custom Capacitor plugin (Android Keystore) | In-house | n/a | — |
| 6 | Web `localStorage` behind abstraction | Web fallback tier | n/a | — |

Evidence retrieved 2026-07-02 from registry.npmjs.org and api.github.com. Candidate 6 is not a competing option — it is the already-decided web fallback tier (ISSUE-227 section 16), listed for completeness.

## 8. Detailed Candidate Evaluation

### 8.1 `@capacitor/preferences`

- **Evidence:** npm 8.0.1, published 2026-02-12; peerDependency `@capacitor/core >=8.0.0`; MIT; repo `ionic-team/capacitor-plugins` (668 stars, actively pushed as of 2026-07-02). Official README: "simple key/value persistent store for **lightweight data**".
- **Android mechanism:** plain `SharedPreferences` — **not encrypted, not Keystore-backed**.
- **Assessment:** Fails criterion A outright for secrets. First-party quality and Capacitor 8 support are excellent, so it remains a legitimate option for the **non-secret persistent tier** later (language, onboarding state) if ever needed — but it cannot be the secure tier.

### 8.2 `capacitor-secure-storage-plugin` (martinkasa)

- **Evidence:** npm 0.13.0, published 2026-01-10; peerDependency `@capacitor/core >=8.0.0`; MIT; repo `martinkasa/capacitor-secure-storage-plugin`: 214 stars, 32 open issues, last push 2026-04-10.
- **Android mechanism (README):** "implemented by AndroidKeyStore and SharedPreferences" — values encrypted with a Keystore-managed key. README warns API < 18 falls back to base64-only; irrelevant here (minSdk 24).
- **Web:** values stored in `localStorage` base64-encoded (explicitly not secure, for development/browser compatibility) — acceptable only behind our abstraction per criterion E.
- **iOS (informational only):** Keychain via SwiftKeychainWrapper.
- **API:** basic get/set/remove/clear/keys with string values; maps directly onto the abstraction.
- **Assessment:** Meets A (on Android ≥ API 18), D, E, F. Maintenance is adequate but slower: still 0.x versioning after years, ~3-month release gaps, 32 open issues.

### 8.3 `@aparajita/capacitor-secure-storage`

- **Evidence:** npm 8.0.0, published 2026-02-10; MIT; repo `aparajita/capacitor-secure-storage`: 165 stars, **3 open issues**, last push 2026-02-12. Plugin major version is deliberately aligned with the Capacitor major (v8.0.0 ↔ Capacitor 8); npm description: "Capacitor 8+ plugin that provides secure storage for iOS and Android".
- **Android mechanism (README):** "data is encrypted using AES [with a key from] the Android KeyStore, then stored in SharedPreferences" — Keystore-backed, no plaintext at rest.
- **Web:** README states data is stored **unencrypted** in `localStorage` so the plugin is usable in browser development, with an explicit warning not to treat web as production-secure — matching our architecture's web-fallback-tier posture exactly.
- **iOS (informational only):** system Keychain, with optional iCloud-keychain sync (would not be used or validated in this phase).
- **API:** fully typed TypeScript API, typed values, key prefixing/namespacing, promise-based errors (failures are rejected promises → supports fail-closed detection).
- **Packaging note:** v8.0.0 lists `@capacitor/core`/`@capacitor/android` etc. in `dependencies` (^8.0.2) rather than `peerDependencies`; npm will dedupe against the app's Capacitor 8.4.1, but this is tracked as a minor risk (section 16).
- **Assessment:** Meets A, D, E, F. Strongest maintenance signal of the community options: version-locked to Capacitor majors, near-empty issue tracker, releases tracking Capacitor releases. Single-maintainer risk noted in section 16.

### 8.4 Ionic Identity Vault

- **Evidence:** Ionic's commercial enterprise SDK (ionic.io); proprietary license; requires a paid enterprise subscription; closed source.
- **Mechanism:** Keystore/StrongBox-backed with biometric session options — technically the most featureful.
- **Assessment:** Fails criterion F (hard constraint 1–2: prefer open-source; paid requires strong technical reason). The open-source candidates satisfy every technical requirement of the ISSUE-227 architecture, so there is no justifying gap. Rejected unless the user overrides.

### 8.5 Custom Capacitor plugin (Android Keystore / AndroidX Security)

- **Evidence:** would be built in-house over `android.security.keystore`. Note: Google **deprecated** the Jetpack `security-crypto` library (`EncryptedSharedPreferences`) — a custom plugin today should target the Keystore APIs directly, which is exactly the work the community plugins already encapsulate.
- **Assessment:** Maximum control, but highest cost: native code to write, test, and maintain ourselves; duplicates well-maintained MIT plugins; expands this phase's scope. Justified only if no existing plugin were suitable — not the case. Rejected.

### 8.6 Web `localStorage` behind the abstraction

- Already decided by ISSUE-227 (section 16) as the temporary web fallback tier. Both surviving plugin candidates ship a web implementation that lands on `localStorage` anyway; the abstraction will route web storage explicitly, so the plugin choice does not change web behavior. Not a competing candidate.

## 9. Comparison Matrix

Scoring: 2 = strong, 1 = acceptable, 0 = fail. Candidates 4–6 excluded (rejected on constraints / not a competitor).

| Criterion | `@capacitor/preferences` | `capacitor-secure-storage-plugin` | `@aparajita/capacitor-secure-storage` |
| --- | --- | --- | --- |
| A. Security (Android Keystore, no plaintext, fail-closed detectable) | 0 (plain SharedPreferences) | 2 | 2 |
| B. Maintenance (releases, activity, docs, TS) | 2 | 1 | 2 |
| C. Community support | 2 | 1 | 1 |
| D. Capacitor 8 compatibility | 2 | 2 | 2 |
| E. Web fallback behavior | 1 | 1 | 1 |
| F. Cost/license | 2 (MIT) | 2 (MIT) | 2 (MIT) |
| **Total** | **9 (disqualified by A=0)** | **9** | **10** |

Security is a gating criterion: any candidate scoring 0 on A is disqualified for the secure tier regardless of total.

## 10. Security Analysis

- Both surviving candidates encrypt values with an Android-Keystore-managed key before persisting to SharedPreferences: secrets are never at rest in plaintext, keys are hardware-backed where the device supports it, and data is per-app isolated by the OS.
- Neither silently falls back to insecure storage on Android; failures surface as rejected promises, satisfying the fail-closed requirement (ISSUE-227 section 15). The aparajita plugin's typed error model makes failure classification (needed by ISSUE-232) somewhat cleaner.
- The martinkasa API<18 base64 fallback is unreachable at minSdk 24.
- `@capacitor/preferences` stores plaintext and is disqualified for secrets.

## 11. Android/Native Analysis

- Project baseline: Capacitor 8.4.1, minSdk 24, compile/target SDK 36.
- martinkasa: peerDependency `@capacitor/core >=8.0.0` — explicit Capacitor 8 support; plain plugin install, no extra Gradle configuration documented.
- aparajita: v8.0.0 explicitly targets Capacitor 8 (major-version alignment policy); no extra Gradle configuration documented; ships with a demo covering Android.
- Both are standard Capacitor plugins: `npm install` + `npx cap sync android` in the implementation issue — no custom native code required on our side.
- Uninstall/reinstall behavior on Android clears app data including Keystore-encrypted values for both (documented behavior to fold into ISSUE-230/ISSUE-233 restoration policy).

## 12. Web Fallback Analysis

- martinkasa web: base64-in-localStorage (obfuscation only). aparajita web: unencrypted localStorage with an explicit "not for production web" warning.
- Neither breaks a Vite/React web build; both are importable in web bundles.
- Per ISSUE-227, web traffic goes through the abstraction regardless; the abstraction may use the plugin's web implementation or plain `localStorage` directly — functionally equivalent, decided at implementation time in ISSUE-229. Web security posture is unchanged by the plugin choice, as designed.

## 13. Maintenance and Community Support Analysis

| Signal (2026-07-02) | martinkasa | aparajita |
| --- | --- | --- |
| Latest release | 0.13.0 — 2026-01-10 | 8.0.0 — 2026-02-10 |
| Last repo push | 2026-04-10 | 2026-02-12 |
| Stars | 214 | 165 |
| Open issues | 32 | 3 |
| Versioning signal | 0.x after 6+ years | Major tracks Capacitor major |
| TypeScript | Types provided, minimal API | Fully typed, richer API |
| Maintainers | Effectively one | One (prolific Capacitor plugin author) |

Both carry single-maintainer risk; the abstraction layer (ISSUE-227 section 8) deliberately limits the blast radius of a future migration to one module.

## 14. Cost/Licensing Analysis

- `@capacitor/preferences`, martinkasa, aparajita: MIT — free, permissive, no cost. ✔
- Ionic Identity Vault: paid enterprise subscription — rejected under hard constraints 1–2; no technical gap justifies the cost.
- Custom plugin: no license cost but highest engineering cost.

## 15. Capacitor 8 Compatibility Analysis

- martinkasa 0.13.0: `peerDependencies: { "@capacitor/core": ">=8.0.0" }` — declared compatibility. ✔
- aparajita 8.0.0: built for "Capacitor 8+" (npm description), Capacitor 8 packages in its dependency set. ✔
- `@capacitor/preferences` 8.0.1: first-party. ✔ (but disqualified on security)
- Identity Vault: compatible but rejected on cost. Custom plugin: compatible by construction but rejected on maintenance cost.

## 16. Implementation Risk Analysis

| Risk | Affects | Mitigation |
| --- | --- | --- |
| Single-maintainer abandonment | both community plugins | All access behind the abstraction — swap costs one module |
| `dependencies` (not peer) packaging of Capacitor in aparajita 8.0.0 | aparajita | npm dedupes ^8.0.2 against app's 8.4.1; verify singleton at install time in ISSUE-229 |
| 0.x semver / 32 open issues | martinkasa | Would pin exact version; monitored — runner-up only |
| Keystore edge cases on specific OEM devices | both | Fail-closed policy (ISSUE-227 §15) + failure taxonomy in ISSUE-232 |
| Web build regressions from plugin import | both | Web routes through abstraction; covered by existing Playwright suite in ISSUE-229 validation |

## 17. Recommended Solution

**`@aparajita/capacitor-secure-storage` v8.x — Recommended pending user approval.**

Rationale: it is the only candidate scoring top marks on both gating security criteria and maintenance — Android Keystore-backed AES with no plaintext at rest, explicit Capacitor 8 alignment (plugin major tracks Capacitor major), MIT license, near-empty issue tracker, fully typed API whose promise-rejection error model fits the fail-closed requirement, and an API shape that maps one-to-one onto the ISSUE-227 abstraction interface.

## 18. Runner-up Solution

**`capacitor-secure-storage-plugin` (martinkasa) 0.13.x.** Equivalent Android security model (AndroidKeyStore + SharedPreferences) and declared Capacitor 8 peer support; loses on maintenance signals (0.x versioning, slower cadence, 32 open issues) and a coarser, less-typed API. A fully acceptable fallback if the recommended plugin proves problematic during ISSUE-229.

## 19. Rejected Options and Reasons

| Option | Reason |
| --- | --- |
| `@capacitor/preferences` | Plain, unencrypted SharedPreferences — fails the gating security criterion for secrets. May still serve the non-secret persistent tier later. |
| Ionic Identity Vault | Commercial/paid; hard constraints require open-source unless a technical gap exists — none does. |
| Custom Keystore plugin | Highest build-and-maintain cost; duplicates maintained MIT plugins; Jetpack `security-crypto` deprecation means writing raw Keystore code in-house — unjustified while suitable plugins exist. |
| Web `localStorage` | Not a competitor — it is the already-decided temporary web fallback tier behind the abstraction. |

## 20. Final Decision Pending Approval

The recommendation is **not** the team decision until explicitly approved by the project owner. Approval of this document (via PR review/merge) constitutes selecting `@aparajita/capacitor-secure-storage` as the agreed solution per the issue's acceptance criterion ("פתרון נבחר") and DoD ("הצוות עובד מול פתרון מוסכם"). If the owner prefers the runner-up or another option, this document is amended before merge.

## 21. Mapping to ISSUE-229 Implementation

| This decision | ISSUE-229 action |
| --- | --- |
| Selected plugin | `npm install @aparajita/capacitor-secure-storage` + `npx cap sync android` (first package change, done in ISSUE-229 — not here) |
| Pin strategy | Save exact/caret version per repo convention; verify Capacitor dedupe (single `@capacitor/core`) |
| Abstraction wiring | Implement `getToken/setToken/clearToken/...` over the plugin's typed API; web routes to fallback tier |
| Fail-closed | Map plugin promise rejections to the failure policy (detailed in ISSUE-232) |
| Validation | Android emulator storage round-trip + existing Playwright web suite; no iOS validation |

## 22. Approval Checklist

- [ ] Evaluation criteria and evidence accepted (sections 6–16)
- [ ] Recommended solution approved: `@aparajita/capacitor-secure-storage` (section 17) — or an alternative named by the owner
- [ ] Runner-up accepted as documented fallback (section 18)
- [ ] Rejections accepted, including no paid solution (section 19)
- [ ] Understanding confirmed: installation happens only in ISSUE-229, not in this issue

Approval is recorded by the owner's explicit confirmation and the merge of this document's PR.
