# Device Integration Inventory

**Issue:** ISSUE-288

**Date:** 2026-07-12

**Status:** Documentation and architecture inventory only — not implemented

**Depends on:** `docs/native-plugin-governance-policy.md`, `docs/sharing-requirements.md`, `docs/native-sharing-architecture.md`, `docs/location-permission-strategy.md`, `docs/user-generated-content-policy.md`, `docs/mobile-application-architecture.md`

---

## 1. Purpose and Authority

This document is the single reference inventory of native device capabilities the yesh_mishak Capacitor application already uses and the device capabilities that remain future opportunities. It exists so that future feature issues (invitations, calendar reminders, QR sharing, field-photo reporting, data export, local reminders) start from an approved shared understanding of current state, product value, complexity, and governance requirements instead of re-auditing the project each time.

This issue adds no plugin, permission, UI, API, database schema, analytics event, or native code. Every recommendation below is a future opportunity, not an approved implementation. Any future issue that adopts one of these integrations must still pass through `docs/native-plugin-governance-policy.md` (plugin proposal, permission governance, security/privacy review, owner approval) before any dependency, permission, or code change is made.

---

## 2. Audit Methodology

This inventory was produced by reviewing, without modifying:

1. `frontend/package.json` — installed Capacitor plugins and their versions.
2. `frontend/capacitor.config.ts`, `frontend/android/app/src/main/AndroidManifest.xml`, and `frontend/ios/` — native project state and declared permissions.
3. `docs/native-plugin-governance-policy.md` — plugin approval rules, permission governance, and the existing plugin audit (Section 12).
4. `docs/sharing-requirements.md` and `docs/native-sharing-architecture.md` — approved and future sharing scope, including the existing reservation of QR, team, tournament, event, and referral sharing as future/out of scope.
5. `docs/location-permission-strategy.md` — the project's approved pattern for permission-at-point-of-need, fallback behavior, and Hebrew user-facing copy, used here as the template for evaluating other sensitive permissions.
6. `docs/user-generated-content-policy.md` and `docs/field-data-quality-checklist.md` — confirmation that field photos (`image_url`) are an approved but **not yet implemented** content type.
7. `docs/product-decisions.md`, `docs/mobile-notifications-screen-audit.md`, `docs/notification-stress-test-results.md` — confirmation of how the existing notification system (server-scheduled reminders delivered via FCM push) works today.
8. `docs/ios-project-creation.md`, `docs/android-project-structure-audit.md` — current native project readiness for each platform.

---

## 3. Current State Summary

### 3.1 Installed Capacitor Packages

| Package | Version | Category | Relevant to this inventory |
| :--- | :--- | :--- | :--- |
| `@capacitor/core` | ^8.4.1 | Runtime | Required runtime, not a device integration |
| `@capacitor/android` | ^8.4.1 | Platform | Android native project support |
| `@capacitor/ios` | ^8.4.1 | Platform | iOS native project support |
| `@capacitor/cli` | ^8.4.1 | Dev tooling | Build tooling |
| `@capacitor/app` | ^8.1.0 | Plugin | App state/URL-open lifecycle (deep links), not a device capability in scope here |
| `@capacitor/app-launcher` | ^8.0.0 | Plugin | Launching other installed apps/URLs (e.g. navigation handoff), not in scope here |
| `@capacitor/geolocation` | ^8.2.0 | Plugin | Location — already implemented and governed by `docs/location-permission-strategy.md`; not re-evaluated here |
| `@capacitor/push-notifications` | ^8.1.1 | Plugin | Remote push (FCM/APNs) — already implemented; distinct from the Native Notifications (local) capability evaluated in Section 8 |
| `@capacitor/share` | ^8.0.0 | Plugin | Native Share Sheet — approved architecture exists (`docs/native-sharing-architecture.md`), implementation pending |
| `@aparajita/capacitor-secure-storage` | ^8.0.0 | Plugin | Secure storage — already implemented, not a device I/O capability in scope here |
| `@capgo/capacitor-social-login` | 8.3.33 | Plugin | Native Google Sign-In — already implemented, not in scope here |

**No plugin is installed today for Contacts, Calendar, Camera, Filesystem, or Local Notifications.** These five capabilities are the subject of this inventory.

### 3.2 Existing Device Integrations (Baseline, Not Re-Evaluated)

| Capability | Status | Reference |
| :--- | :--- | :--- |
| Geolocation | Implemented, permission-at-point-of-need pattern | `docs/location-permission-strategy.md` |
| Remote push notifications (FCM/APNs) | Implemented; server-scheduled reminders are delivered through this channel today | `docs/native-plugin-governance-policy.md` §12.2, `docs/product-decisions.md` (scheduled reminder job) |
| Native Share Sheet | Architecture approved, plugin not yet added | `docs/native-sharing-architecture.md` |
| Secure storage | Implemented | `docs/secure-storage-architecture.md` |
| Native Google Sign-In | Implemented | `docs/native-authentication-architecture.md` |
| Android App Links / iOS Universal Links (deep linking) | Partially implemented | `docs/deep-link-architecture.md`, `docs/android-app-links-strategy.md` |

### 3.3 Native Project Readiness

| Platform | Status |
| :--- | :--- |
| Android | `frontend/android/` exists and is buildable; `AndroidManifest.xml` declares `INTERNET`, `POST_NOTIFICATIONS`, `ACCESS_COARSE_LOCATION`, `ACCESS_FINE_LOCATION` |
| iOS | `frontend/ios/` exists (generated via `docs/ios-project-creation.md`); Xcode validation on macOS is still pending per that document |

Any future integration below must account for iOS Xcode validation still being outstanding as a prerequisite, independent of this inventory.

### 3.4 Roadmap Context

The project has no single dedicated `roadmap.md`. Forward-looking scope is tracked per-capability across `docs/sharing-requirements.md` §9 and §12 (future invitations, teams, tournaments, events, referrals), `docs/native-sharing-architecture.md` §15 (future QR, team, tournament, event, referral sharing), and `docs/user-generated-content-policy.md` (future field photos, future comments). This inventory cross-references those reservations rather than duplicating or re-deciding them.

---

## 4. Scope

### 4.1 In Scope

- Evaluating Contacts, Calendar, Camera, Files, and Native (local) Notifications as future device integrations.
- For each: product value, user benefit, technical complexity, privacy considerations, security considerations, required permissions, and Capacitor/Android/iOS support.
- Recommending a relative implementation priority for each capability.

### 4.2 Out of Scope

- Designing APIs, UI, database schema, or analytics for any of these capabilities.
- Referral features or social-graph design.
- Background services.
- Native code implementation of any kind.
- Installing, evaluating-for-installation-approval, or configuring any plugin (that remains a separate governed step under `docs/native-plugin-governance-policy.md`).
- Re-deciding sharing, invitation, QR, team, tournament, event, or referral product scope already reserved in `docs/sharing-requirements.md` and `docs/native-sharing-architecture.md`. This document references those reservations; it does not change them.
- Any application code, dependency, environment, or backend change.

---

## 5. Contacts

### 5.1 Evaluated Use Cases

- **Inviting friends** — letting a user pick device contacts to invite to the app or to a game.
- **Sharing games with contacts** — a contacts-based recipient picker as an alternative to the generic Share Sheet/WhatsApp channels already architected in `docs/native-sharing-architecture.md`.

### 5.2 Relationship to Existing Architecture

`docs/sharing-requirements.md` §5.4 and `docs/native-sharing-architecture.md` §13 already establish that the app does not request contacts permission for Native Share Sheet, WhatsApp, or SMS-style sharing, and that recipient selection belongs to the OS/provider outside yesh_mishak. A future contacts-picker feature would be a product change to that decision, not an extension of it, and would require updating those documents first.

### 5.3 Assessment

| Dimension | Assessment |
| :--- | :--- |
| Product value | Moderate — could reduce friction for invitations, but the existing share-adapter model (Native Share Sheet, WhatsApp, Copy Link) already lets the OS/provider handle recipient selection without the app touching the address book. |
| User benefit | Faster invite flow for users with many contacts already using WhatsApp/SMS habitually; limited benefit for users who already share via the existing channels. |
| Technical complexity | High — requires a contacts-read plugin (e.g. a community `@capacitor-community/contacts`-class plugin; no official `@capacitor/contacts` package exists), a picker UI, matching contacts to registered accounts (a backend concern, out of scope here), and de-duplication/pagination for large address books. |
| Privacy considerations | Highest sensitivity in this inventory. Contacts data includes third parties who never consented to yesh_mishak processing their information. Any read of the address book must be scoped to the minimum fields needed (name/phone) and must never be uploaded in bulk to the backend without an explicit, reviewed matching design. |
| Security considerations | Contact data must never be logged, cached beyond the picker session, or transmitted unencrypted. A future design must define retention (ideally zero server-side retention of non-users' contact data). |
| Required permissions | Android: `READ_CONTACTS`. iOS: `NSContactsUsageDescription` (full address-book access — iOS has no partial-contacts grant). Both are classified **High — must justify access** under `docs/native-plugin-governance-policy.md` §8.3. |
| Capacitor support | No official `@capacitor/contacts` plugin. Community plugins exist but must independently pass the plugin governance checklist (maintenance, license, permissions) before proposal. |
| Android support | Full native support via `READ_CONTACTS`; runtime permission dialog required. |
| iOS support | Full native support via `Contacts` framework; App Store review scrutinizes contacts access and requires a clear, specific usage string. |
| Recommended implementation priority | **Low.** Highest privacy/security cost in this inventory, contradicts an existing documented decision to avoid contacts access, and the value it adds on top of the already-architected share channels is marginal. |

---

## 6. Calendar

### 6.1 Evaluated Use Cases

- Adding a scheduled game to the user's device calendar.
- Calendar-based reminders (as an alternative/complement to push reminders).
- Future recurring events (e.g. a recurring weekly game).
- Platform differences between Android (Calendar Provider) and iOS (EventKit).

### 6.2 Assessment

| Dimension | Assessment |
| :--- | :--- |
| Product value | Good — scheduled games are a core entity (`docs/sharing-requirements.md` §6 already models "scheduled" as a first-class game state); letting users add them to a calendar they already check is a natural extension. |
| User benefit | Users get a reminder mechanism that works even if the app is uninstalled or notifications are disabled, and that integrates with existing personal scheduling habits. |
| Technical complexity | Low relative to the other capabilities — a single "Add to calendar" action per game is a narrow, one-directional write (app → calendar) with no read of existing calendar data required, and no picker/matching logic. Recurring events add moderate complexity (recurrence rules differ between the Android Calendar Provider and iOS EventKit) and are a future extension, not part of a first pass. |
| Privacy considerations | Low-to-moderate — the app would write game time/location/title to the user's own calendar, which is data the app already has and controls (its own scheduled-game record), not third-party data. The calendar entry itself could later be visible to anyone the user shares their calendar with, which is a user choice outside the app's control and should be disclosed in the permission-request copy. |
| Security considerations | Write-only calendar access is lower risk than read access. If a future version ever reads the calendar (e.g. to detect conflicts), that read must be scoped and justified separately. |
| Required permissions | Android: `WRITE_CALENDAR` (and `READ_CALENDAR` only if conflict-checking or event lookup/update is added later). iOS: `NSCalendarsUsageDescription` (technically `NSCalendarsWriteOnlyAccessUsageDescription` on iOS 17+, which is a more limited, more privacy-friendly grant than full calendar access). Classified **High — must justify access** under `docs/native-plugin-governance-policy.md` §8.3, though the write-only iOS 17+ grant is a materially smaller ask than full read/write access. |
| Capacitor support | No official `@capacitor/calendar` plugin. Community plugins exist (covering both Android Calendar Provider and iOS EventKit) and would need to pass the standard governance review. |
| Android support | Full native support via the Calendar Provider content resolver. |
| iOS support | Full native support via EventKit; iOS 17+ offers a write-only permission tier that fits this use case well. |
| Recommended implementation priority | **Medium.** Meaningful user benefit for a core entity (scheduled games), comparatively low technical complexity for the write-only first-pass use case, and a permission footprint that can be minimized (write-only) more than most other integrations in this inventory. |

---

## 7. Camera

### 7.1 Evaluated Use Cases

- QR code scanning (e.g. scanning a code to open a field/game, complementing the QR sharing already reserved as future/not-implemented in `docs/native-sharing-architecture.md` §15.1).
- Future QR sharing/generation (encoding the same canonical link already defined in `docs/sharing-requirements.md` §5).
- Profile picture support (capturing/selecting a user avatar image).
- Field reporting with photos (attaching a photo to a field report; this is the `image_url` capability already flagged as **not yet implemented** in `docs/user-generated-content-policy.md`).

### 7.2 Assessment

| Dimension | Assessment |
| :--- | :--- |
| Product value | Good — field-report photos directly improve the field-data-quality workflow already described in `docs/field-data-quality-checklist.md` (photos are listed as a data source `if available`), and QR scanning gives an additional, frictionless entry point into the same canonical links `docs/native-sharing-architecture.md` already treats as the single source of truth. Profile pictures are a lower-value personalization feature. |
| User benefit | Field photos let reporters substantiate a report without typing a long description; QR scanning is a fast, familiar interaction for joining a game/field a user sees advertised physically (e.g. a poster at a field); profile pictures improve personalization but do not unlock new functionality. |
| Technical complexity | Medium overall, but the two use cases differ: QR **scanning** needs a barcode-reading plugin and camera preview UI, but no upload/storage pipeline. Photo **capture for reports/avatars** needs the camera/gallery plugin plus an upload pipeline (compression, storage, and a moderation step consistent with `docs/user-generated-content-policy.md`'s existing image-moderation gap, itself flagged there as low-effort today only because images aren't implemented). QR **generation/sharing** is client-side rendering of the existing canonical URL and adds negligible complexity once the canonical link builder from `docs/native-sharing-architecture.md` exists. |
| Privacy considerations | Camera access itself is moderate risk (it is point-in-time and user-initiated, unlike contacts or location). The bigger privacy surface is what happens to captured images afterward: field-report photos could incidentally contain bystanders or license plates and would need the same moderation posture already anticipated in `docs/user-generated-content-policy.md`; profile pictures are self-portraits chosen by the user and are lower risk. |
| Security considerations | Uploaded images need virus/content scanning before storage, size/type limits to prevent abuse, and must not leak EXIF metadata (e.g. embedded GPS coordinates) into public field-report or avatar data without explicit review — this is a sharper version of the location-leak concern already documented in `docs/location-permission-strategy.md` §11. QR **scanning** must treat decoded content as untrusted input and route it through the same canonical URL validator described in `docs/sharing-requirements.md` §10, never trusting a scanned URL directly. |
| Required permissions | Android: `CAMERA`, plus `READ_MEDIA_IMAGES` (Android 13+) if gallery selection is also offered. iOS: `NSCameraUsageDescription`, plus `NSPhotoLibraryUsageDescription` for gallery selection. Classified **High — must justify access** under `docs/native-plugin-governance-policy.md` §8.3. |
| Capacitor support | `@capacitor/camera` is an official, actively maintained Capacitor plugin covering capture and gallery selection — the preferred option under the plugin governance preference order (§10.1). QR scanning needs a separate barcode-reading plugin (official-adjacent options exist, e.g. Google's ML Kit-based Capacitor plugin); no barcode scanning ships in `@capacitor/camera` itself. |
| Android support | Full native support for both camera capture and ML Kit-based barcode scanning. |
| iOS support | Full native support for both camera capture (AVFoundation via the plugin) and barcode scanning (AVFoundation/Vision-based). |
| Recommended implementation priority | **Medium.** Field-report photos and QR scanning both extend capabilities the product already anticipates (`image_url`, canonical link scanning) rather than introducing new product surface, but each still needs a moderation/validation pipeline decision before implementation, which keeps this from being a quick win. |

---

## 8. Files

### 8.1 Evaluated Use Cases

- Exporting data (e.g. a user's own game history, or a field-report export for reviewers).
- Importing future content.
- Sharing generated files (e.g. sharing an exported file through the OS share sheet).
- Offline assets (caching map tiles or field data for offline use).

### 8.2 Assessment

| Dimension | Assessment |
| :--- | :--- |
| Product value | Lowest in this inventory. No current product requirement (in `docs/product-decisions.md`, `docs/sharing-requirements.md`, or elsewhere) calls for user-facing data export/import or offline asset bundling. Offline map/field caching is a real but separate performance concern already partially covered by ordinary HTTP caching, not by a Filesystem plugin. |
| User benefit | Data export mainly benefits a small subset of users (data portability requests) and administrators; the `docs/technical-debt-inventory.md` item TD-PRIVACY-002 ("No account deletion/export process") is a compliance-driven export need, but that is a backend/data-portability feature, not primarily a native Filesystem integration. |
| Technical complexity | Medium — writing files to app-scoped storage is simple with `@capacitor/filesystem`, but a real export feature needs a defined file format, a generation pipeline (likely backend-driven for anything beyond trivial data), and a share/save handoff (which can reuse the `@capacitor/share` plugin already installed rather than needing new Filesystem-specific UI). Import adds file-picker and validation/parsing complexity with no current use case to validate against. |
| Privacy considerations | Depends entirely on what is exported. A GDPR-style personal-data export (TD-PRIVACY-002) must be scoped to the requesting user's own data only, which is a backend authorization concern more than a device-integration concern. |
| Security considerations | Exported files written to shared/external storage could be read by other apps on older Android versions without scoped storage; app-scoped storage (the default for `@capacitor/filesystem`) avoids this. Any import feature must treat file contents as untrusted input. |
| Required permissions | With `@capacitor/filesystem`'s default app-scoped directories, **no runtime permission is required** on modern Android (API 29+, scoped storage) or iOS (app sandbox). Broader "Downloads"-style shared storage access would require `READ_MEDIA_*`/legacy `WRITE_EXTERNAL_STORAGE` on Android — classified **High** under §8.3 — but is avoidable for most realistic export use cases by using app-scoped storage plus the existing Share plugin to hand the file to the user's chosen destination. |
| Capacitor support | `@capacitor/filesystem` is an official, actively maintained plugin. |
| Android support | Full native support; scoped storage (API 29+) is the recommended, lower-permission path. |
| iOS support | Full native support within the app sandbox; broader access requires the document-picker/Files integration, which is a larger scope than app-scoped export. |
| Recommended implementation priority | **Low.** No current product requirement drives this, the one real motivating case (compliance data export, TD-PRIVACY-002) is primarily a backend feature that could ship without any Capacitor Filesystem plugin at all (e.g. emailing/downloading a file via the browser/web view), and offline assets are better addressed by caching strategy than by a native Files integration. |

---

## 9. Native Notifications (Local)

### 9.1 Evaluated Use Cases

- Local notifications (scheduled on-device, independent of network connectivity).
- Scheduled reminders (as a complement to the existing server-scheduled, FCM-delivered reminders).
- Future game reminders.
- Notification permissions and platform differences.

### 9.2 Relationship to the Existing Notification System

This is the capability most directly connected to a proven, already-implemented product feature. Today, "scheduled reminders" are generated by a **server-side batch job** and delivered to the device as **remote push** via `@capacitor/push-notifications` (FCM/APNs) — see `docs/native-plugin-governance-policy.md` §12.2 and the scheduled-reminder job described throughout `docs/product-decisions.md`. Local notifications are a distinct capability: they are scheduled **on the device itself** (via `@capacitor/local-notifications`, not `@capacitor/push-notifications`) and fire without a network round-trip or server job at delivery time. The two are complementary, not redundant — local notifications would give reliable reminder delivery even during a network/backend outage or if push delivery fails (a gap already tracked as TD-NOTIFY-001 in `docs/technical-debt-inventory.md`, "no notification delivery failure monitoring").

### 9.3 Assessment

| Dimension | Assessment |
| :--- | :--- |
| Product value | Highest in this inventory. Reminders are a proven, already-valued feature (an entire notification system already exists), and local notifications close a real reliability gap (push delivery failure, described in TD-NOTIFY-001) without needing new product concepts. |
| User benefit | More reliable "your game starts soon" reminders that do not depend on FCM/APNs delivery succeeding at the right moment, and that can work for reminders scheduled well in advance without depending on the server-side batch job's timing. |
| Technical complexity | Medium — scheduling itself is straightforward with `@capacitor/local-notifications`, but a correct implementation needs to reconcile local-scheduled reminders with server-side game-state changes (a game the user was reminded about could be cancelled, rescheduled, or already ended by the time the local notification fires), which requires either periodic re-sync logic or accepting a documented staleness window. |
| Privacy considerations | Low — local notifications do not require transmitting any additional data off-device; the notification payload (game/field name, time) is data the app already holds and already sends via existing push notifications. |
| Security considerations | Low — no new attack surface beyond what push notifications already have, since content is generated by the same trusted app logic rather than received from a network payload. The main risk is stale/incorrect local reminders (e.g. reminding about a cancelled game) misleading a user, which is a correctness concern rather than a security one. |
| Required permissions | Android 13+ (API 33+): `POST_NOTIFICATIONS` — **already declared** in `AndroidManifest.xml` for push notifications, so no new Android permission is needed. iOS: local and remote notifications share the same `UNUserNotificationCenter` authorization request, so if push notification permission is already granted, no additional iOS permission prompt is required for local notifications. Classified **High — must define opt-in flow** under §8.3, but the opt-in flow may already exist if push permission is requested first. |
| Capacitor support | `@capacitor/local-notifications` is an official, actively maintained Capacitor plugin, matching the plugin governance preference order (§10.1) for official plugins first. |
| Android support | Full native support via `AlarmManager`/`WorkManager` under the hood; Android's background-execution limits on some OEM skins can delay exact-time delivery and would need testing. |
| iOS support | Full native support via `UNUserNotificationCenter`; iOS enforces a per-app pending-notification limit (64 scheduled notifications) that a reminder feature must design around if many games are reminder-eligible at once. |
| Recommended implementation priority | **High.** Directly extends a feature already proven valuable, uses an official plugin, requires no new permission prompt beyond what push notifications likely already obtain, and closes a documented reliability gap (TD-NOTIFY-001) — the main remaining work is state-reconciliation logic, not native integration risk. |

---

## 10. Cross-Cutting Governance Notes

1. **None of these five capabilities are approved for implementation by this document.** Each still requires a completed Plugin Proposal (`docs/native-plugin-governance-policy.md` §7), architecture/security/privacy review, and explicit owner approval before any plugin is added to `package.json`.
2. **Permission minimization applies across all five.** Where a narrower permission tier exists (iOS 17+ write-only calendar access; app-scoped Filesystem storage requiring no runtime permission; reusing an already-granted push-notification authorization for local notifications), the narrower tier is the default recommendation, consistent with §8.1 of the governance policy ("Permissions must be minimal").
3. **Every one of Contacts, Calendar, Camera, and Files touches the "High-Sensitivity Permissions" table** in `docs/native-plugin-governance-policy.md` §8.3 and therefore requires explicit owner approval and a defined opt-in flow before any request is shown to a user. Local Notifications is the only capability in this inventory that can likely avoid a second permission prompt.
4. **Privacy review triggers already exist** for four of the five capabilities per `docs/native-plugin-governance-policy.md` §9.2 (location, files/photos/media, camera/microphone, contacts/calendar all explicitly listed). Any future proposal for Contacts, Calendar, Camera, or Files must complete that privacy review regardless of this inventory's priority ranking.
5. **QR, team, tournament, event, and referral product scope is not re-decided here.** This inventory evaluates the device *capability* (camera-based scanning); the product scope for what QR should encode remains governed by `docs/native-sharing-architecture.md` §15.1, which already reserves QR as future/not-implemented and restricts it to encoding the same canonical link used by every other share mechanism.

---

## 11. Out of Scope (Restated)

Per the issue definition, this document does not design or specify:

- APIs
- UI
- Database schema
- Analytics
- Referral features
- Social graph
- Background services
- Native code implementation

---

## 12. Summary

- **Total device integrations documented:** 5 (Contacts, Calendar, Camera, Files, Native Notifications), evaluated against the 5 already-implemented native integrations (Geolocation, Push Notifications, Native Share Sheet architecture, Secure Storage, Native Google Sign-In) that establish the project's baseline.
- **No plugin is installed today** for any of the five evaluated capabilities.
- **Highest-priority opportunity:** Native (local) Notifications — extends a proven feature, uses an official plugin, and likely needs no new permission prompt.
- **Lowest-priority opportunities:** Files (no current product requirement) and Contacts (highest privacy cost, and in tension with an existing documented decision to avoid contacts access for sharing).
- **All five require the full plugin governance flow** (`docs/native-plugin-governance-policy.md`) — proposal, architecture review, security/privacy review, and explicit owner approval — before any implementation work begins.

### 12.1 Recommended Implementation Priority

| Integration | Value | Complexity | Recommendation |
| :--- | :--- | :--- | :--- |
| Native Notifications | ⭐⭐⭐⭐⭐ | Medium | High |
| Calendar | ⭐⭐⭐⭐ | Low | Medium |
| Camera (QR) | ⭐⭐⭐⭐ | Medium | Medium |
| Contacts | ⭐⭐⭐ | High | Low |
| Files | ⭐⭐ | Medium | Low |
