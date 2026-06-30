# Native Plugin Governance Policy

**ISSUE:** 186
**Date:** 2026-06-30
**Status:** Approved policy reference
**Scope:** Documentation and audit only - no plugin changes, no native project generation

---

## 1. Purpose

This document defines the official governance policy for adding, reviewing, and maintaining Capacitor and native plugins in the Yesh Mishak mobile application.

Uncontrolled plugin adoption creates dependency risk, permission bloat, platform bugs, maintenance burden, security/privacy exposure, and release instability. This policy ensures that every native plugin is deliberately chosen, properly reviewed, and actively maintained.

---

## 2. Default Rule

**Do not add a native plugin by default.**

Prefer:

1. Web platform APIs (Geolocation API, Notifications API, Fetch, etc.)
2. Existing app architecture (backend endpoints, React state, axios client)
3. Backend-side solutions (server-sent events, webhooks, backend push via FCM HTTP v1)

A plugin must justify its long-term maintenance cost before adoption. The burden of proof is on the proposer, not on the reviewer.

---

## 3. When a Plugin Is Allowed

A plugin is allowed when ALL of the following are true:

| Criterion | Requirement |
| :--- | :--- |
| Native capability | The feature requires native device capability not available to web code |
| Web API insufficient | Browser/web APIs are unavailable, unreliable, or insufficient for the use case |
| Actively maintained | The plugin has recent releases, active issue handling, and a responsive maintainer |
| Platform support | The plugin supports all required platforms (Android, iOS, or both) |
| License | The plugin has acceptable license terms (MIT, Apache 2.0, or similar permissive license) |
| Permissions | The plugin does not request unnecessary OS permissions |
| Feature importance | The feature is important enough to justify native dependency risk |
| Failure behavior | Graceful failure/fallback behavior is defined for when the plugin is unavailable |

---

## 4. When a Plugin Is Rejected

A plugin should be rejected when ANY of the following are true:

| Criterion | Reason |
| :--- | :--- |
| Minor code savings | It only saves a small amount of code that could be written directly |
| Duplicates web functionality | It duplicates existing browser/web functionality that works in Capacitor WebView |
| Poorly maintained | Last release is old, issues are unanswered, maintainer appears inactive |
| Unclear ownership | Repository has unclear ownership, is archived, or has been abandoned |
| Excessive permissions | Requires broad permissions without strong justification |
| Security/privacy risk | Introduces security or privacy risk not needed for the current feature set |
| Single-platform only | Supports only one platform when the feature must work cross-platform |
| Build fragility | Makes the release/signing/build process significantly more fragile |
| Unacceptable license | License is copyleft (GPL), proprietary, or incompatible with the project |

---

## 5. When to Build Custom Native Code

Custom native code (Android Kotlin/Java, iOS Swift/Objective-C) is considered when:

| Criterion | Explanation |
| :--- | :--- |
| No reliable plugin exists | The feature is needed but no actively maintained plugin covers it |
| Existing plugins are unsafe | Available plugins are abandoned, have known vulnerabilities, or are architecturally unsound |
| Small, controlled scope | The native code surface is small enough to maintain in-house |
| Tight control needed | Platform-specific behavior must be tightly controlled (e.g., exact permission timing, specific OS API version handling) |
| Permission minimization | Custom code allows requesting fewer permissions than a general-purpose plugin |

Custom native code must follow the same review checklist as external plugins (Section 7), except for the external maintenance and license checks.

---

## 6. Approval Flow

### 6.1 Approval Owner

For this project, **explicit owner approval is required before adding any new Capacitor or native plugin.**

### 6.2 Approval Steps

| Step | Responsibility | Action |
| :--- | :--- | :--- |
| 1. Feature justification | Product/technical owner | Approves whether the feature is needed |
| 2. Plugin proposal | Developer | Fills out the Plugin Proposal Template (Section 7) |
| 3. Architecture review | Technical maintainer | Reviews dependency and architecture impact |
| 4. Security/privacy review | Technical maintainer + owner | Required if permissions, user data, location, camera, microphone, contacts, notifications, files, or identifiers are involved |
| 5. Approval decision | Owner | Approves, rejects, or requests changes |
| 6. Documentation | Developer | Records the decision in `docs/product-decisions.md` |

### 6.3 No Implicit Approval

Adding a plugin to `package.json` without completing the approval flow is not permitted. A PR that adds a new native plugin without a documented proposal and approval should be rejected.

---

## 7. Plugin Proposal Template

Every new plugin request must include the following information. This template should be included in the PR description or a linked decision document.

```
## Plugin Proposal

### Plugin
- **Plugin name:**
- **npm package:**
- **Version:**
- **Repository:**
- **License:**

### Scope
- **Native platforms affected:** Android / iOS / Both
- **Feature requiring this plugin:**
- **Why web API is insufficient:**

### Permissions
- **Android permissions required:**
- **iOS permissions required:**
- **User data accessed:**
- **Is location, camera, microphone, contacts, files, or tracking involved?** Yes / No

### Security / Privacy
- **Does the plugin transmit data to third parties?** Yes / No
- **Does it include analytics or tracking SDKs?** Yes / No
- **Privacy review required?** Yes / No
- **Security impact assessment:**

### Maintenance
- **Last release date:**
- **Open issues count:**
- **Capacitor version compatibility:**
- **Is there a Capacitor team / official plugin?** Yes / No
- **Maintenance risk assessment:**

### Build Impact
- **Bundle size impact:**
- **Native build configuration changes:**
- **Does it require signing or build process changes?** Yes / No

### Alternatives
- **Alternative options considered:**
- **Why this plugin was chosen over alternatives:**

### Failure Behavior
- **What happens if the plugin fails or is unavailable?**
- **Fallback strategy:**
- **Testing plan:**

### Approval
- **Proposed by:**
- **Reviewed by:**
- **Approval decision:** Approved / Rejected / Deferred
- **Date:**
```

---

## 8. Permission Governance

### 8.1 Principles

1. Permissions must be minimal. Request only what the feature requires.
2. Permission prompts must be user-understandable. The user must know why the app is asking.
3. Permissions must be tied to a visible feature. No permission should be added "just in case."
4. Permission timing matters. Request permissions at the moment the user triggers the feature, not at app launch.

### 8.2 Platform Permission Review

Before any production release:

- **Android:** Review `AndroidManifest.xml` for `<uses-permission>` declarations. Remove any permission not tied to an active, approved feature.
- **iOS:** Review `Info.plist` for usage description strings (`NS*UsageDescription`). Every permission must have a clear, user-facing explanation.

### 8.3 High-Sensitivity Permissions

The following permissions require stricter review and explicit owner approval:

| Permission Category | Examples | Review Level |
| :--- | :--- | :--- |
| Location | `ACCESS_FINE_LOCATION`, `NSLocationWhenInUseUsageDescription` | High - must justify precision level |
| Notifications | `POST_NOTIFICATIONS`, push notification entitlement | High - must define opt-in flow |
| Camera | `CAMERA`, `NSCameraUsageDescription` | High - must justify access |
| Microphone | `RECORD_AUDIO`, `NSMicrophoneUsageDescription` | High - must justify access |
| Contacts | `READ_CONTACTS`, `NSContactsUsageDescription` | High - must justify access |
| Photos/Files | `READ_MEDIA_*`, `NSPhotoLibraryUsageDescription` | High - must justify access |
| Bluetooth | `BLUETOOTH_*`, `NSBluetoothUsageDescription` | High - must justify access |
| Background services | `FOREGROUND_SERVICE`, background modes | High - must justify battery impact |
| Tracking identifiers | `AD_ID`, `NSUserTrackingUsageDescription` | High - requires privacy review |

---

## 9. Security and Privacy Rules

### 9.1 Plugin Security Requirements

1. Plugins must not expose secrets (API keys, tokens, credentials) to logs, crash reporters, or external services.
2. Plugins must not bypass backend authorization. Native code must not make privileged API calls that skip JWT verification.
3. Plugins must not collect unnecessary personal data.
4. Plugins must not include hidden analytics or tracking SDKs without explicit approval.

### 9.2 Privacy Review Triggers

A privacy review is required when a plugin:

- Accesses location data
- Accesses files, photos, or media
- Accesses camera or microphone
- Accesses contacts or calendar
- Uses device identifiers (advertising ID, hardware IDs)
- Transmits data to third-party servers
- Includes any analytics, crash reporting, or tracking SDK

### 9.3 Third-Party SDK Policy

Any third-party SDK bundled through a plugin that has analytics, tracking, or data collection behavior requires:

1. Explicit owner approval
2. Documentation of what data is collected
3. Verification that data collection complies with applicable privacy regulations
4. Configuration to minimize data collection where possible

---

## 10. Maintenance Rules

### 10.1 Plugin Selection Preferences

In order of preference:

1. **Official Capacitor plugins** (`@capacitor/*`) - maintained by the Capacitor team
2. **Well-maintained community plugins** - recent releases, active issues, responsive maintainer
3. **Custom native code** - when no reliable plugin exists
4. **Forked plugins** - last resort, only when a critical fix is needed on an abandoned plugin

### 10.2 Version and Compatibility

1. Document plugin version and owner in the plugin audit section of this document.
2. Review all plugins before major Capacitor version upgrades.
3. Review all plugins before production mobile releases.
4. Pin plugin versions to avoid unexpected breaking changes.

### 10.3 Plugin Health Checks

Periodically verify:

| Check | Frequency |
| :--- | :--- |
| Plugin still actively maintained | Before each major release |
| No known security vulnerabilities | Before each major release |
| Compatible with current Capacitor version | Before Capacitor upgrades |
| Permissions still minimal and justified | Before each production release |
| No deprecated APIs used by plugin | Before platform SDK upgrades |

---

## 11. Plugin Decision Documentation

Every plugin decision (approved, rejected, or deferred) must be recorded in `docs/product-decisions.md` with:

- Plugin name and npm package
- Decision (approved / rejected / deferred)
- Rationale
- Date
- Owner who approved or rejected

This creates an audit trail and prevents re-debating settled decisions.

---

## 12. Current Plugin Audit

Audit performed 2026-06-30 on `main` branch.

### 12.1 Installed Capacitor Packages

| Package | Version | Type | Classification |
| :--- | :--- | :--- | :--- |
| `@capacitor/core` | ^8.4.1 | Runtime dependency | **Required** - Capacitor runtime, not a plugin |
| `@capacitor/android` | ^8.4.1 | Runtime dependency | **Required** - Android platform support |
| `@capacitor/cli` | ^8.4.1 | Dev dependency | **Required** - Capacitor CLI tooling |
| `@capacitor/push-notifications` | ^8.1.1 | Runtime dependency | **Acceptable** - official Capacitor plugin, needed for native push notifications |

### 12.2 Plugin Assessment

**`@capacitor/push-notifications` (^8.1.1):**

| Criterion | Assessment |
| :--- | :--- |
| Native capability needed | Yes - native push tokens (FCM/APNs) require native code |
| Web API insufficient | Yes - Web Push API does not work in Capacitor WebView (no service worker) |
| Actively maintained | Yes - official Capacitor team plugin |
| Platform support | Android and iOS |
| License | MIT |
| Permissions | `POST_NOTIFICATIONS` (Android) - justified for push notification feature |
| Feature importance | High - push notifications are a core user engagement feature |
| Failure behavior | Graceful - app functions without push; web fallback exists for browser |

**Verdict: Acceptable under this policy.**

### 12.3 Previously Evaluated Plugins

| Plugin | Status | Reason |
| :--- | :--- | :--- |
| `@codetrix-studio/capacitor-google-auth` | **Not installed** | Evaluated for native Google Sign-In but requires Capacitor ^6.0.0, incompatible with Capacitor 8. Tracked as active blocker B-01 in `docs/epic-03-completion-review.md`. |

### 12.4 Native Project Files

| Item | Status |
| :--- | :--- |
| `frontend/android/` | Exists - Android project generated via `npx cap add android` (PR #740) |
| `frontend/ios/` | Does not exist - iOS project deferred to a future issue |

### 12.5 Current Permissions

**Android (`AndroidManifest.xml`):**

| Permission | Justification | Status |
| :--- | :--- | :--- |
| `android.permission.INTERNET` | Required for all network communication | Acceptable |
| `android.permission.POST_NOTIFICATIONS` | Required for push notifications via `@capacitor/push-notifications` | Acceptable |

**iOS:** No iOS project exists. No permissions declared.

### 12.6 Audit Verdict

**PASS.** All installed plugins are official Capacitor packages. The one functional plugin (`@capacitor/push-notifications`) is justified, actively maintained, and uses minimal permissions. No unauthorized or abandoned plugins are present.

---

## 13. Summary

1. **Default: no plugin.** Prefer web APIs, existing architecture, or backend solutions.
2. **Allowed when justified.** Native capability needed, web API insufficient, plugin maintained, permissions minimal.
3. **Rejected when risky.** Poor maintenance, excessive permissions, duplicates web functionality, single-platform.
4. **Custom native code as alternative.** When no reliable plugin exists and the scope is small.
5. **Owner approval required.** Every new plugin needs explicit approval with a completed proposal template.
6. **Permissions are minimal.** Every permission tied to a visible feature, reviewed before release.
7. **Security/privacy enforced.** No secret exposure, no unnecessary data collection, privacy review for sensitive access.
8. **Maintenance tracked.** Plugin health reviewed before major releases and Capacitor upgrades.
