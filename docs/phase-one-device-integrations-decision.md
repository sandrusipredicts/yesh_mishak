# Phase One Device Integrations — Business Decision

**Issue:** ISSUE-289

**Date:** 2026-07-12

**Status:** Approved product/business decision — documentation only, not implemented

**Depends on:** `docs/device-integration-inventory.md` (ISSUE-288), `docs/native-plugin-governance-policy.md`, `docs/sharing-requirements.md`, `docs/native-sharing-architecture.md`, `docs/location-permission-strategy.md`, `docs/user-generated-content-policy.md`, `docs/technical-debt-inventory.md`

---

## 1. Purpose and Authority

This document is the official business decision on which native device integrations belong in the first production release ("Phase One") of yesh_mishak. It converts the technical inventory produced in `docs/device-integration-inventory.md` (ISSUE-288) into a product decision: every evaluated integration receives exactly one of three decisions — **Phase One**, **Future Version**, or **Rejected** — with a stated justification.

This is a product and business decision only. It authorizes no plugin installation, permission change, native project change, API design, or application code change. A **Phase One** decision here still requires its own future implementation issue to pass through `docs/native-plugin-governance-policy.md` (plugin proposal, architecture review, security/privacy review, explicit owner approval) before any dependency is added.

If a future issue wants to change one of these decisions (e.g. move a Future Version item into an earlier release, or reconsider a Rejected item), it must update this document first, consistent with the decision-recording rule already established in `docs/product-decisions.md`.

---

## 2. Review Summary

### 2.1 ISSUE-288 Findings (Input to This Decision)

`docs/device-integration-inventory.md` evaluated five unimplemented capabilities and ranked them by value/complexity/recommendation: Native Notifications (High), Calendar (Medium), Camera — QR (Medium), Contacts (Low), Files (Low). This document does not re-run that technical analysis; it applies business judgment on top of it to decide what actually ships in the first release, which is a narrower question than "what has value eventually."

### 2.2 Roadmap Context

The project has no single dedicated `roadmap.md`. Forward-looking product scope lives across `docs/sharing-requirements.md` (approved entities: Game, Field, Application for the first sharing phase; Game invitation, Team, Tournament, Event, Referral explicitly reserved as future/not-implemented), `docs/native-sharing-architecture.md` (QR, Team, Tournament, Event, Referral sharing reserved as future), and `docs/mobile-launch-readiness-checklist.md` (the current mobile-packaging launch gate, currently **NO-GO** pending the AUTH-001 production blocker and outstanding P2 accessibility findings). The consistent pattern across all of these is: **ship a narrow, well-verified core loop first (find a field, find/create a game, join, get reminded, share what you found) and explicitly defer breadth.** This decision follows that same pattern rather than introducing a new roadmap philosophy.

### 2.3 Current Capacitor Integrations (Re-Verified for This Decision)

Re-checking `frontend/package.json`, `frontend/src/`, and the native projects since ISSUE-288 was written (both work happened the same day) confirms one material update: **Native Share Sheet is now implemented**, not merely architected. `frontend/src/api/nativeShare.js` wires `@capacitor/share` into a validated, canonical-link-only share flow, consistent with ISSUE-284/285/286 ("game sharing flow," "field sharing flow," "optimize sharing for WhatsApp") landing after the architecture document was written. The rest of ISSUE-288's snapshot still holds.

| Package | Status | Notes |
| :--- | :--- | :--- |
| `@capacitor/geolocation` | Implemented | Governed by `docs/location-permission-strategy.md` |
| `@capacitor/push-notifications` | Implemented | Remote push (FCM/APNs); backs the existing scheduled-reminder feature |
| `@capacitor/share` | Implemented | Now wired into `frontend/src/api/nativeShare.js`; canonical-link-only, no analytics, per `docs/native-sharing-architecture.md` |
| `@aparajita/capacitor-secure-storage` | Implemented | Governed by `docs/secure-storage-architecture.md` |
| `@capgo/capacitor-social-login` | Implemented | Native Google Sign-In, per `docs/native-authentication-architecture.md` |
| `@capacitor/app`, `@capacitor/app-launcher` | Implemented | App lifecycle / deep-link handoff and external navigation handoff |
| Contacts, Calendar, Camera, Filesystem, Local Notifications | **Not installed** | Subject of this decision |

### 2.4 Product Architecture Context

`docs/mobile-application-architecture.md` and the sharing/notification architecture documents establish a consistent shared pattern: a narrow adapter layer per native capability, official Capacitor plugins preferred over community plugins, and every new plugin gated by explicit owner approval (`docs/native-plugin-governance-policy.md`). This decision keeps to that pattern — it does not introduce new architectural precedent, only a business prioritization of which adapters get built first.

---

## 3. Decision Framework

Each integration below is evaluated on seven dimensions, then assigned one decision:

| Dimension | Question |
| :--- | :--- |
| Business value | Does this materially improve activation, retention, or a metric the business tracks for the first release? |
| User value | Does this solve a real, frequent user problem in the core loop (find → join → play → come back), or is it a nice-to-have? |
| Development effort | How much net-new work (plugin integration, UI, backend support, testing) does it require before it can ship safely? |
| Maintenance cost | What is the ongoing burden — plugin upgrades, OS permission-model changes, support load — after it ships? |
| Privacy impact | Does it touch sensitive personal data (the user's own, or a third party's, e.g. contacts)? |
| Permission impact | Does it require a new OS permission prompt, and how easily can users understand and grant it? |
| Long-term roadmap impact | Does shipping it now unblock or simplify later work, or is it freestanding? |

**Decision definitions:**

- **Phase One** — Approved for the first production release. A future implementation issue may proceed (still subject to plugin governance).
- **Future Version** — Has real value but is deliberately postponed past the first release for a stated reason (low relative user value at launch, high complexity relative to launch value, privacy concerns needing more design, or better suited once the core loop has real usage data).
- **Rejected** — Not planned for this product at this time. Either it conflicts with an already-approved decision, its privacy/value tradeoff is unfavorable, or no credible product need exists.

---

## 4. Already-Implemented Integrations (Reviewed for Completeness)

These are not being decided here — they already shipped or are already architecturally approved — but are reviewed so this document gives a complete picture of the device-integration landscape at Phase One.

| Integration | Business value | User value | Dev effort (incurred) | Maintenance cost | Privacy impact | Permission impact | Roadmap impact |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| Geolocation | High — core to "find fields near me" | High — central to map browsing | Delivered | Low — official plugin, stable API | Moderate — ephemeral, never persisted per `docs/location-permission-strategy.md` §11 | Delivered — point-of-need pattern, no first-launch prompt | Complete; pattern reused by future point-of-need permission decisions |
| Push Notifications (remote) | High — proven engagement driver (scheduled reminders) | High — timely game/field updates | Delivered | Low-moderate — official plugin; TD-NOTIFY-001 (no delivery-failure monitoring) is tracked, not blocking | Low — no new data beyond what the app already holds | Delivered — one runtime prompt | Foundation the Phase One Native Notifications decision (Section 5) builds on |
| Native Share Sheet | Moderate-high — reduces friction for organic growth | Moderate-high — one-tap sharing of games/fields | Delivered | Low — official plugin, narrow adapter | Low — canonical link only, no analytics per `docs/native-sharing-architecture.md` | Delivered — no permission prompt (Share Sheet requires none) | Establishes the canonical-link pattern that any future QR/invitation work must reuse |
| Secure Storage | High — required for safe token storage | Indirect — enables reliable sessions | Delivered | Low | Low — no new user data category | Delivered — no permission prompt | Foundation for session/auth work |
| Native Google Sign-In | High — primary auth path | High — faster login | Delivered | Moderate — tracked Capacitor-version compatibility risk | Low — standard OAuth data | Delivered | Foundation for auth-dependent features |

No action is requested for this section; it exists so a reader does not need to cross-reference ISSUE-288 to see the full picture.

---

## 5. Evaluated Integrations (This Decision)

### 5.1 Native Notifications (Local)

| Dimension | Assessment |
| :--- | :--- |
| Business value | High. Reminders are the proven retention mechanism already in the product (server-scheduled push). Local notifications close a real, already-tracked reliability gap (`TD-NOTIFY-001` — no delivery-failure monitoring for push) without inventing a new feature category. |
| User value | High. A user who does not receive a push reminder because of a transient FCM/APNs failure currently gets nothing; a local, on-device fallback materially improves the odds a scheduled-game reminder actually arrives. |
| Development effort | Medium. Official plugin (`@capacitor/local-notifications`), but correctness requires reconciling locally scheduled reminders with server-side game-state changes (cancelled/rescheduled games) — real work, not integration risk. |
| Maintenance cost | Low-medium. Official, actively maintained plugin; ongoing cost is mostly the reconciliation logic, not the native integration itself. |
| Privacy impact | Low. No new data leaves the device; content mirrors what push notifications already send. |
| Permission impact | Low relative to the other four. Android's `POST_NOTIFICATIONS` is already declared; iOS shares its authorization prompt with push notifications, so no new permission dialog is expected if push permission is already requested first. |
| Long-term roadmap impact | High. A working local-notification adapter is a prerequisite building block for any future "remind me before this game" or "recurring game reminder" feature. |

**Decision: Phase One.** This is the strongest candidate in the inventory — it extends a feature already proven to matter, uses an official plugin, needs no meaningfully new permission ask, and directly addresses a documented reliability gap rather than adding new product surface.

---

### 5.2 Calendar

| Dimension | Assessment |
| :--- | :--- |
| Business value | Moderate. Calendar integration is a retention-adjacent convenience feature, not a core-loop driver; it does not change whether a user finds a field or joins a game. |
| User value | Moderate-good for the subset of users who plan games in advance and manage their life through a device calendar; limited for immediate/pickup games, which `docs/sharing-requirements.md` §6.3 treats as an equally common game state. |
| Development effort | Low relative to the other four (per ISSUE-288 §6.2) for a first-pass, write-only "add to calendar" action; recurring events (explicitly mentioned in this issue's evaluation list) are materially higher effort and are not needed for a first pass. |
| Maintenance cost | Low-moderate. No official Capacitor plugin exists; a community plugin adds an external maintenance dependency the project does not yet have for this domain. |
| Privacy impact | Low. Write-only add of data the app already owns (its own game record) to a calendar the user controls. |
| Permission impact | Moderate. Requires a new, single-purpose permission prompt (`WRITE_CALENDAR` / iOS write-only calendar access) that a first-time user has not seen from this app before. |
| Long-term roadmap impact | Moderate; does not block anything else on the roadmap. Recurring-event support, if ever built, would meaningfully increase complexity and is explicitly not part of this decision. |

**Decision: Future Version.** Real, low-complexity value, but it is not part of the core find → join → play loop the first release must prove, and it introduces a new permission prompt and an unmaintained-by-Capacitor plugin dependency for a convenience feature. Better suited once the app has live usage data showing how often scheduled (vs. immediate) games are actually created — that data does not exist yet.

---

### 5.3 Camera

| Dimension | Assessment |
| :--- | :--- |
| Business value | Moderate. Field-report photos would improve field-data quality (a real, already-tracked need per `docs/field-data-quality-checklist.md`); QR scanning is an alternate entry point into functionality (canonical links) the app already has through deep links and the browser. |
| User value | Moderate. Photo-backed field reports are more useful than text-only reports; QR scanning is a convenience, not a capability unlock, since every QR target is reachable today via a tapped link. |
| Development effort | Medium-high. Camera capture itself is a one-plugin integration (`@capacitor/camera`, official), but a *usable* feature requires an upload/moderation pipeline that does not exist yet — `docs/user-generated-content-policy.md` already flags image moderation as an open gap, currently low-effort only because images are unimplemented. Shipping Camera without that pipeline would ship an unmoderated content-upload surface, which this decision does not accept. |
| Maintenance cost | Medium. Adds an ongoing image-storage, bandwidth, and moderation-queue cost the operations side has not sized yet. |
| Privacy impact | Moderate. Photos can incidentally capture bystanders, license plates, or embedded EXIF location data — a sharper version of the location-leak concern already documented in `docs/location-permission-strategy.md` §11. |
| Permission impact | High. New `CAMERA` (and likely `READ_MEDIA_IMAGES`/photo-library) prompts on both platforms, classified High-sensitivity under `docs/native-plugin-governance-policy.md` §8.3. |
| Long-term roadmap impact | Moderate. Useful groundwork for future field-verification tooling, but not a dependency for anything else already committed. |

**Decision: Future Version.** The camera plugin itself is cheap; the moderation/storage pipeline it requires to be safe to ship is not, and that pipeline is explicitly out of scope for this decision and for ISSUE-288. Shipping Camera in Phase One without a moderation answer would create an unreviewed content-safety risk in a first release that is otherwise trying to minimize risk (see `docs/mobile-launch-readiness-checklist.md`'s NO-GO-until-verified posture). QR scanning specifically is deferred because the deep-link/browser path it would shortcut already exists and works.

---

### 5.4 Contacts

| Dimension | Assessment |
| :--- | :--- |
| Business value | Low-moderate. A contacts picker could theoretically speed up invitations, but the app already has a working, lower-risk invitation surface (Native Share Sheet + WhatsApp adapter, delivered under ISSUE-284/285/286) that lets the OS/provider handle recipient selection. |
| User value | Low relative to cost. Marginal convenience over "tap Share → pick WhatsApp contact," which most users already know how to do. |
| Development effort | High. No official `@capacitor/contacts` plugin exists; a community plugin, a picker UI, and (for any "invite a friend who's already a user" feature) a backend matching design are all net-new. |
| Maintenance cost | High. Community-maintained dependency plus an ongoing matching/privacy surface. |
| Privacy impact | Highest in this inventory. Contacts data belongs to third parties (the user's contacts) who never consented to yesh_mishak processing their information — a materially different privacy category than the app's own data. |
| Permission impact | High. Full address-book access on both platforms (iOS has no partial-contacts grant); classified High-sensitivity under `docs/native-plugin-governance-policy.md` §8.3. |
| Long-term roadmap impact | Negative-to-neutral. Directly conflicts with an already-approved decision: `docs/sharing-requirements.md` §5.4 and `docs/native-sharing-architecture.md` §13 explicitly state the app does **not** request contacts permission for sharing, and that recipient selection belongs to the OS/provider. Adopting Contacts would require reopening and reversing that decision, not extending it. |

**Decision: Rejected.** This is not a "not yet" — it is a "not this way." The product has already made and documented a deliberate decision to keep recipient selection outside the app (OS/provider-owned), and Contacts access would reverse that decision for marginal benefit over the sharing flow already shipped. If a future business need for contacts-based invitations emerges, it must come with a new product/privacy review that explicitly proposes reversing `docs/sharing-requirements.md` §5.4 — it cannot be adopted as an incremental addition.

---

### 5.5 Files

| Dimension | Assessment |
| :--- | :--- |
| Business value | Low. No current product requirement (in `docs/product-decisions.md`, `docs/sharing-requirements.md`, or elsewhere) calls for user-facing file export/import in the app. |
| User value | Low for most users; the one credible driver — personal-data export/portability (`TD-PRIVACY-002` in `docs/technical-debt-inventory.md`) — serves a small subset of users and is a compliance requirement, not a core-loop feature. |
| Development effort | Medium, and largely avoidable: `TD-PRIVACY-002` can be satisfied with a backend-generated export delivered through the existing browser/web download path, without any Capacitor Filesystem plugin at all. |
| Maintenance cost | Low if avoided as described above; medium if a native Filesystem adapter is built for a need that a simpler path already covers. |
| Privacy impact | Depends on content; for the compliance-export case, this is fundamentally a backend authorization concern (a user must only ever export their own data), not a device-integration concern. |
| Permission impact | Low-to-none if app-scoped storage is used (no runtime permission required on modern Android/iOS); only rises to High if broader shared-storage access is requested, which no current use case needs. |
| Long-term roadmap impact | Low. Offline asset caching (the other motivating idea in ISSUE-288) is better solved by HTTP/cache-layer strategy than by a native Filesystem integration, and is not part of this decision. |

**Decision: Rejected.** Not because a Filesystem plugin is unsafe, but because no evaluated use case actually needs it: the one real, compliance-driven need (data export) is better and more simply solved without adding a native dependency. This keeps Phase One's plugin surface area minimal, consistent with the governance policy's default ("Do not add a native plugin by default" — `docs/native-plugin-governance-policy.md` §2). If a genuine future need requires true device-filesystem access (e.g. offline-first map data the browser cache cannot handle), that would be a new proposal evaluated on its own merits, not a revival of this rejection.

---

## 6. Phase One Selection

**Approved for Phase One: Native Notifications (Local) only.**

Rationale for selecting exactly one new integration:

1. It is the only evaluated capability that extends an already-proven feature (server-scheduled reminders) rather than introducing new product surface.
2. It is the only one with effectively no new permission-prompt cost — Android's `POST_NOTIFICATIONS` is already declared, and iOS shares its authorization dialog with the existing push-notification flow.
3. It directly closes an already-tracked reliability gap (`TD-NOTIFY-001`), which is a stronger justification than a purely additive feature would be for a first release that is still working through its own launch-readiness gate (`docs/mobile-launch-readiness-checklist.md` is currently NO-GO for unrelated reasons, which is itself a reason to keep new scope minimal).
4. Every other evaluated integration either requires a new, unproven permission ask (Calendar, Camera), a content-moderation pipeline that does not exist (Camera), or conflicts with an already-documented product decision (Contacts), or lacks a real use case that a native plugin actually solves (Files).

No other integration meets the bar of "clearly worth the added permission, review, and maintenance surface before the first release ships."

---

## 7. Deferred Integrations (Future Version)

| Integration | Why deferred |
| :--- | :--- |
| Calendar | Low relative to launch-critical value: it is a convenience on top of the core loop, not part of it. Requires a new single-purpose permission prompt and a non-official plugin dependency. Better suited after the first release, once usage data shows how much scheduled (vs. immediate) game creation actually happens — the data needed to justify the investment does not exist yet. |
| Camera (QR scanning, field-report photos, profile pictures) | High complexity relative to launch value: the camera plugin itself is cheap, but a safe photo-upload feature requires an image-moderation and storage pipeline that is an explicitly open gap (`docs/user-generated-content-policy.md`) and out of scope for this decision. QR scanning specifically shortcuts a deep-link/browser path that already works, so it adds convenience, not capability. Revisit once a moderation pipeline decision exists. |

Both deferred items may be reconsidered for a subsequent release once the stated blocking condition (usage data for Calendar; a moderation pipeline decision for Camera) is resolved. Reconsideration requires updating this document, not silently starting implementation.

---

## 8. Rejected Integrations

| Integration | Why rejected |
| :--- | :--- |
| Contacts | Conflicts with an already-approved product decision (`docs/sharing-requirements.md` §5.4, `docs/native-sharing-architecture.md` §13) that recipient selection stays outside the app. Highest privacy cost in the inventory (third-party data, not the user's own) for marginal benefit over the sharing flow already shipped. Any future reconsideration requires a new privacy review that explicitly proposes reversing the existing sharing decision — it is not a default candidate for a later release. |
| Files | No evaluated use case requires native device-filesystem access. The one credible driver (compliance data export, `TD-PRIVACY-002`) is better solved as a backend-generated download through the existing browser path, without adding a plugin. Rejected as a *device integration*, not as a product need — the underlying compliance requirement remains tracked in `docs/technical-debt-inventory.md` and should be solved without this plugin. |

---

## 9. Final Business Decision

| Integration | Decision | Reason |
| :--- | :--- | :--- |
| Native Notifications | **Phase One** | Extends a proven feature, closes a tracked reliability gap (TD-NOTIFY-001), effectively no new permission cost |
| Calendar | **Future Version** | Low complexity but not core-loop; new permission prompt not yet justified by usage data |
| Camera | **Future Version** | Real value blocked on an unresolved moderation/storage pipeline; QR scanning shortcuts a path that already works |
| Contacts | **Rejected** | Conflicts with the already-approved decision to keep recipient selection outside the app; highest privacy cost for marginal benefit |
| Files | **Rejected** | No use case requires it; the one real need (compliance export) is better solved without a native plugin |

---

## 10. Out of Scope

Per the issue definition, this document does not:

- Design APIs for any evaluated integration.
- Implement any plugin.
- Modify any permission (manifest, `Info.plist`, or otherwise).
- Change any native project (`frontend/android/`, `frontend/ios/`).
- Change any application code.

A **Phase One** decision here is a green light to begin a separate, governed implementation issue for Native Notifications — it is not that implementation issue.

---

## 11. Decision Summary

- **Final approved Phase One integrations:** Native Notifications (Local) — 1 of 5 evaluated new integrations.
- **Deferred (Future Version) integrations:** Calendar, Camera — 2 of 5.
- **Rejected integrations:** Contacts, Files — 2 of 5.
- **Already-implemented integrations reviewed for completeness:** Geolocation, Push Notifications, Native Share Sheet, Secure Storage, Native Google Sign-In — no change to their status.
- This document introduces no application-code, plugin, permission, or native-project change. A future Native Notifications implementation issue must still complete the full plugin governance flow in `docs/native-plugin-governance-policy.md` before any dependency is added.
