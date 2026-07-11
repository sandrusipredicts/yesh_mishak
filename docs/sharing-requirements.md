# Sharing Requirements

**Issue:** ISSUE-281

**Date:** 2026-07-12

**Status:** Requirements and product design only — not implemented

**Depends on:** `docs/navigation-sharing-entry-points-audit.md`, `docs/deep-link-architecture.md`, `docs/android-app-links-strategy.md`

---

## 1. Purpose and Authority

This document is the single product-requirements reference for all future sharing work in yesh_mishak. It defines what may be shared, the canonical link contracts, cross-platform outcomes, authentication boundaries, failure states, privacy rules, and the future invitation model.

Future Sharing issues must conform to this document. A future issue may refine presentation copy or implementation details, but any change to the canonical URLs, public-data boundary, authentication behavior, or resource-state behavior must update this document first.

This issue does not add share controls, Native Share Sheet support, deep-link resource resolution, invitation delivery, store listings, or application behavior.

---

## 2. Current-State Findings

The application currently has no Share Game, Share Field, Share App, invite, or copy-link feature. It does not use the Web Share API, clipboard sharing, WhatsApp, Telegram, or SMS links.

The relevant foundation is partially available:

| Capability | Current state |
|:---|:---|
| Canonical production origin | `https://yesh-mishak.com` |
| Android App Links | Configured for the canonical HTTPS host; deployment/device verification remains separate |
| Incoming native URL handoff | Capacitor cold-start and warm-start listeners exist |
| URL validation | HTTPS, exact host, supported path, action, and UUID v4 validation exist |
| Field/game UI resolution | Not implemented for incoming links; validated field/game links currently hand off to `/` |
| iOS Universal Links | Not configured |
| Browser fallback | SPA hosting fallback exists; content-specific public landing/preview behavior is not implemented |
| Store destinations | No approved Google Play or Apple App Store listing URLs are documented |
| Share UI and invitation delivery | Not implemented |

The current validator accepts singular and plural resource paths. Singular paths are canonical and are the only forms future share features may generate:

- `https://yesh-mishak.com/game/{game_id}`
- `https://yesh-mishak.com/field/{field_id}`

Plural paths and legacy `?game_id=` / `?field_id=` inputs are compatibility inputs only. They must normalize to the canonical resource intent and must never appear in newly generated shared content.

---

## 3. Product Principles

1. **One link works everywhere.** Share HTTPS URLs, not native-only schemes. The same URL must support installed-app handoff and a useful browser fallback.
2. **Content before promotion.** A recipient should understand what was shared before being asked to install, register, or sign in whenever the public-data boundary permits it.
3. **Stable canonical identity.** A shared URL contains only a stable resource identifier, never transient state, display text, user identity, or an authentication credential.
4. **Explicit action.** Opening a link may display content or a join invitation, but it must never automatically join a game, create content, send a message, or install an app.
5. **Graceful failure.** Invalid, unavailable, deleted, or finished content produces a clear localized state with a safe route back to the map or website.
6. **Minimum public data.** Share only the information needed to identify and evaluate public content. Keep participant, creator, contact, account, and session data out of share payloads and previews.
7. **Platform consistency.** Android, iOS, and web must resolve the same canonical URL and resource state even if their handoff mechanisms differ.
8. **No install assumption.** A recipient without the app must not encounter a dead end or a native-only URL.

---

## 4. Shareability Inventory

### 4.1 Approved Shareable Entities

| Entity | Timing | Canonical destination | Decision |
|:---|:---|:---|:---|
| Game | First implementation phase | `/game/{game_id}` | Shareable when its field and permitted public game summary can be resolved |
| Field | First implementation phase | `/field/{field_id}` | Shareable when publicly visible and approved |
| Application | First implementation phase | `/` with platform-aware store actions | Shareable as a product destination |
| Game invitation | **Future / Not implemented** | `/game/{game_id}/join` | Invitation intent; never automatic enrollment |
| Team | **Future / Not implemented** | Reserved; undecided | Section reserved; requirements require a future review |
| Tournament | **Future / Not implemented** | Reserved; undecided | Section reserved; requirements require a future review |
| Event | **Future / Not implemented** | Reserved; undecided | Section reserved; requirements require a future review |
| Referral link | **Future / Out of scope** | Reserved; undecided | No referral design is approved by this document |

### 4.2 Explicitly Non-Shareable Entities

User profiles, participant lists, notification records, notification preferences, field reports, moderation state, admin pages, authentication routes, account details, device/push tokens, and user location are not shareable entities. My Games is a private navigation destination, not shareable content. Navigation-provider links are destination handoffs, not yesh_mishak sharing links.

---

## 5. Common Link Contract

### 5.1 Canonical URL Rules

| Requirement | Contract |
|:---|:---|
| Scheme | HTTPS only |
| Host | Exact canonical host `yesh-mishak.com` |
| Resource IDs | UUID v4, lowercase when generated; parsing may be case-insensitive |
| Game | `https://yesh-mishak.com/game/{game_id}` |
| Field | `https://yesh-mishak.com/field/{field_id}` |
| Game invitation | `https://yesh-mishak.com/game/{game_id}/join` — **Future / Not implemented** |
| App | `https://yesh-mishak.com/` |
| Query data | None required; unknown query parameters must not affect authorization or resource identity |
| Fragments | Must not carry identity, action, or sensitive data |

Shared links must not contain tokens, user IDs, participant IDs, email addresses, phone numbers, user coordinates, API origins, redirect URLs, creator IDs, or tracking parameters. Analytics and campaign parameters are out of scope; a later approved specification is required before generating them.

### 5.2 Installed-App Behavior

When the application is installed and the operating system has verified the canonical host:

1. The operating system opens the app for the canonical HTTPS URL.
2. The app validates scheme, host, path, action, and identifier before any resource request.
3. The resolver preserves the target intent through cold start, warm start, language selection, onboarding, and authentication.
4. An authenticated, ready user is taken directly to the target field/game surface.
5. Back/close returns to a sensible map context; it must not exit into a blank view or repeat the link action.

If OS association is unavailable or unverified, the same URL opens in the browser and follows the web fallback contract.

### 5.3 Not-Installed and Web Behavior

The canonical URL must render a mobile-friendly website response. For an accessible resource it shows the permitted public summary, an **Open in app** action when supported, platform-appropriate **Get the app** actions when approved store URLs exist, and a way to continue on the website or map.

The page must remain useful when store destinations are unavailable. It must not repeatedly redirect, open a store without a user gesture, or use a custom-scheme redirect loop. Desktop browsers use the same content and website fallback without pretending that a native app can be launched.

### 5.4 Authentication Contract

- Opening and validating a shared HTTPS URL does not require authentication.
- A public landing preview may show only the data allowlisted in this document.
- The current authenticated application may require sign-in before opening its interactive field/game surface.
- Join, leave, create, close, extend, report, or other account-affecting actions always require authentication and normal authorization.
- When sign-in, first-run language selection, or onboarding intervenes, the original validated target is stored locally only for the minimum necessary time and resumed after successful completion.
- Cancellation or failed authentication returns to a safe public landing or login state; it never performs the intended action.
- A redirect target must be an internally constructed validated intent, never an arbitrary caller-supplied URL.

---

## 6. Share Game Requirements

### 6.1 Shared Information

A generated game share message or public preview may contain:

- field name;
- sport type;
- scheduled date/time for a scheduled game, or current/ended state for an immediate game;
- current player count and maximum capacity as aggregate numbers;
- general age note only if the product confirms it is intended as public game information;
- localized status such as open, full, scheduled, finished, or cancelled; and
- the canonical game URL.

It must not contain participant names or identities, creator identity, contact details, user IDs, personal messages, exact user location, authentication state, or tokens. Field notes must not be copied into a game share message unless separately approved as public preview content.

### 6.2 Resolution and Navigation

The canonical format is:

```text
https://yesh-mishak.com/game/{game_id}
```

The resolver must retrieve a share-safe game representation, identify its field, open the field-details context, and focus the requested game. A direct game endpoint or equivalent resolver is required; scanning map-viewport results is not a reliable link-resolution mechanism.

Installed, authenticated recipients go to the game in its field context. Logged-out recipients see the public summary and, after sign-in/onboarding, return to the same game. Browser recipients see the public summary and may continue to the supported web experience.

### 6.3 Game-State Behavior

| State | Required result |
|:---|:---|
| Open with capacity | Show current public details and an authenticated Join action |
| Full | Show details and “Game is full”; do not offer Join |
| Scheduled and open | Show scheduled local date/time and Join action after authentication |
| Scheduled and full | Show scheduled local date/time and full state; no Join |
| Finished or expired | Show “This game has ended,” read-only safe summary when retained, field context if still public, and no Join |
| Cancelled | Show “This game was cancelled,” read-only safe summary when retained, and no Join |
| Deleted or unavailable | Show a neutral “Game not found or no longer available” state; do not reveal whether it was deleted, hidden, or never existed |
| Game exists but field is not public | Treat as unavailable; do not reveal the private/non-approved field through game data |
| Malformed/invalid identifier | Do not request the resource; show “Invalid link” and a safe map/home action |

Finished/cancelled game retention is a backend/product policy dependency. If a share-safe tombstone or retained record is unavailable, the link follows the deleted/unavailable result. A finished link must never reopen, recreate, or join a replacement game at the same field.

### 6.4 Game Privacy and Authorization

Possession of a game URL grants no additional permission. The backend is authoritative for visibility and allowed actions. Aggregate capacity is public; the participant list is not part of shared content or unauthenticated previews. If participant names remain visible inside the authenticated game UI, that existing application policy is separate from the sharing payload and should receive its own privacy review.

---

## 7. Share Field Requirements

### 7.1 Shared Information

A generated field share message or public preview may contain:

- approved field name;
- sport/type classification;
- approximate public location such as city when present;
- field status when public and actionable;
- selected public facility attributes such as surface, nets, water, and opening hours; and
- the canonical field URL.

The canonical link, not copied coordinates, is the primary shared destination. Exact coordinates may be used by the resolved public field page and its explicit Navigate action, but should not be duplicated in the share text. Free-text notes require moderation/public-data confirmation before inclusion in external previews.

### 7.2 Resolution and Navigation Relationship

The canonical format is:

```text
https://yesh-mishak.com/field/{field_id}
```

The link opens the field-details context on the map. It may expose the existing, separate Navigate to Field action. Sharing must not automatically open Waze, Google Maps, or Apple Maps and must not replace the canonical yesh_mishak URL with a navigation-provider URL.

If the app is installed, the validated App/Universal Link opens the target field. If it is not installed, the website displays the public field summary, map context when supported, and explicit website/store actions. Location permission is not required to view a shared field or use its destination-only navigation action.

### 7.3 Field-State Behavior

| State | Required result |
|:---|:---|
| Approved, verified, open | Show field details, map context, games allowed by their own visibility rules, and Navigate action |
| Closed or renovation and intentionally public | Show “Field temporarily unavailable,” public details, and navigation only if product policy keeps it useful |
| Pending, rejected, hidden, or non-public | Show neutral “Field not found or no longer available”; do not disclose moderation state |
| Deleted or missing | Show neutral “Field not found or no longer available” and a map/home action |
| Malformed/invalid identifier | Do not request the resource; show “Invalid link” and a map/home action |
| Valid identifier with unavailable backend/network | Show a retryable temporary error, distinct from invalid/not-found |

The backend visibility rule is authoritative. A client must not infer visibility from cached map data or reveal a pending/rejected field because a UUID is known.

---

## 8. Share App Requirements

### 8.1 Shared Destination and Message

Share App uses the stable website URL:

```text
https://yesh-mishak.com/
```

The shared message may include the localized product name and a short approved description. It must not contain a user/referrer identifier, campaign code, reward promise, or recipient data.

### 8.2 Platform Behavior

| Recipient platform | Required behavior |
|:---|:---|
| Android with app installed | Verified App Link may open the application home/map |
| Android without app | Website offers the approved Google Play listing through an explicit action; until that URL exists, continue on the website |
| iOS with app installed | Universal Link opens the application once Associated Domains/AASA are implemented and verified; otherwise website fallback |
| iOS without app | Website offers the approved Apple App Store listing through an explicit action; until that URL exists, continue on the website |
| Desktop/other web | Show the product website and platform choices; never force a mobile store |
| Unknown platform | Show the website and explicit store choices; do not guess or auto-redirect |

Store URLs must be configuration-owned, HTTPS, allowlisted, and tested. Android package identity is currently `com.yeshmishak.app`, but no Play listing is assumed. The iOS App Store ID is not yet approved/documented and must not be fabricated.

### 8.3 Future Marketing Considerations

Future work may add localized social preview metadata, approved preview imagery, smart store badges, and campaign landing content. Campaign tracking, attribution, growth experiments, and referral behavior require separate requirements and privacy review and are not authorized here.

---

## 9. Future Invitation Links — Not Implemented

All requirements in this section are **Future / Not implemented**.

### 9.1 Architecture

An invitation is an intent layered on the same public game identity:

```text
https://yesh-mishak.com/game/{game_id}/join
```

The `/join` suffix means “show this game with a join call to action.” It never means automatic join. The resolver validates the same UUID/resource/field visibility rules as Share Game, preserves the join intent through authentication/onboarding, refreshes the current game state, and then asks for explicit confirmation.

Invitation links are bearer-discoverable public links, not access-control grants. They do not bypass full, finished, cancelled, deleted, blocked-user, or other authorization rules. Version 1 has no per-recipient token, expiration token, inviter identity, or revocation model. If private/unlisted games are introduced, they require a separate signed-token architecture and threat model.

### 9.2 Delivery Channels

| Channel | Future requirement |
|:---|:---|
| WhatsApp | Compose localized text plus the canonical HTTPS join URL; encode the entire message; fall back to copy link/browser if WhatsApp is unavailable |
| Telegram | Compose localized text plus the same canonical URL using Telegram’s supported share entry point; fall back to copy link/browser |
| SMS | Open a prefilled SMS composer only after a user gesture; include concise text and URL; never select or upload contacts automatically |
| Copy link | Copy only the canonical join URL, confirm success accessibly, and provide manual selection when clipboard permission/API fails |

Channel adapters may change message presentation but must not generate different resource URLs or channel-specific access rights. Native Share Sheet implementation is explicitly out of scope for this document.

### 9.3 Invitation Outcomes

The invitation landing must handle open, full, scheduled, finished, cancelled, deleted/unavailable, invalid-ID, logged-out, and app-not-installed states according to Share Game requirements. Only an open game with capacity may reach an enabled confirmation action.

---

## 10. Security Requirements

1. Validate URL syntax, HTTPS scheme, exact canonical host, allowlisted path, allowed action, segment count, and UUID v4 format before a resource request.
2. Reject custom schemes, lookalike/subdomain hosts, credentials in URLs, encoded path confusion, extra actions, and attacker-controlled redirect destinations.
3. Perform server-side visibility and authorization checks on every resolution and action; client validation is defense in depth only.
4. Treat invalid identifiers without an API request. Treat valid-but-missing/deleted/hidden identifiers with the same neutral public response.
5. Do not expose moderation state, deletion reason, internal IDs beyond the resource UUID, database errors, or account existence.
6. Do not cache authenticated API responses into public preview metadata. Share previews require a deliberately minimized share-safe response.
7. Do not put secrets, session material, one-time login URLs, or private invitation tokens in logs, page metadata, clipboard content, or outbound messages.
8. Rate limiting and abuse controls for public resolvers must be defined during implementation without changing the visible not-found contract.
9. External share/compose links must be constructed from allowlisted provider templates with correct URL encoding and safe browser-opening flags.
10. A stale cached summary must never enable an action; refresh authoritative state before Join or other mutation.

---

## 11. Privacy Requirements

Public sharing is limited to public field facts, share-safe game facts, aggregate capacity, approved app copy, and canonical URLs. The following must never appear in generated share text, unauthenticated previews, Open Graph metadata, or link parameters:

- participant names, usernames, IDs, or membership;
- creator/organizer identity or contact information;
- email addresses, phone numbers, account/profile data, or authentication state;
- user location, origin, saved places, notification preferences, or device identifiers;
- access/refresh tokens, push tokens, internal API URLs, or diagnostic data;
- private reports, moderation notes, or unapproved field content.

Link unfurlers may request a URL without the recipient intentionally opening it. Therefore preview generation must be read-only, unauthenticated, side-effect free, and limited to the same share-safe public representation. It must never join a game, increment a product-visible counter, or expose personalized content.

---

## 12. Future Expansion — Reserved, Not Implemented

### 12.1 Team Sharing

**Future / Not implemented.** Reserve a canonical team resource and define public/private membership, roster privacy, invitation permissions, link revocation, and deleted-team behavior before assigning a URL.

### 12.2 Tournament Sharing

**Future / Not implemented.** Define tournament visibility, organizer authority, schedule/results data, participant privacy, cancellation, and archival behavior before assigning a URL.

### 12.3 Event Sharing

**Future / Not implemented.** Define how an event differs from a game/tournament, public metadata, attendance actions, location visibility, lifecycle, and cancellation before assigning a URL.

### 12.4 Referral Links

**Future / Out of scope.** The URL namespace may later reserve a referral route, but this document approves no referral identifiers, attribution, incentives, rewards, tracking, or user-growth behavior. A separate product, security, and privacy review is mandatory.

---

## 13. Out of Scope

- Referral-system design or implementation.
- Push notifications or notification navigation changes.
- Analytics, attribution, or tracking parameters.
- User-growth or marketing campaigns.
- Rewards or incentives.
- QR codes.
- Native Share Sheet design or implementation.
- Share buttons, clipboard code, channel integrations, deep-link resource resolution, backend endpoints, native configuration, or store publishing.

---

## 14. Documented Scenario Catalog

The following atomic acceptance scenarios are the baseline for future Sharing issues. There are **36 documented sharing scenarios**.

| # | Entity | Scenario | Expected outcome |
|---:|:---|:---|:---|
| 1 | Game | Installed, authenticated, open game | Open target game in field context; Join available |
| 2 | Game | Installed, logged out | Preserve target; show public/login flow; resume after authentication |
| 3 | Game | App not installed | Show share-safe web game landing |
| 4 | Game | Open game with capacity | Show current details and Join after authentication |
| 5 | Game | Full game | Show full state; no Join |
| 6 | Game | Scheduled open game | Show localized schedule and Join |
| 7 | Game | Scheduled full game | Show schedule/full state; no Join |
| 8 | Game | Finished or expired game | Show ended, read-only state; no Join |
| 9 | Game | Cancelled game | Show cancelled state; no Join |
| 10 | Game | Deleted/missing/hidden game | Neutral unavailable state |
| 11 | Game | Game on non-public field | Neutral unavailable state; no field disclosure |
| 12 | Game | Malformed/invalid game ID | No resource request; invalid-link state |
| 13 | Game | Temporary resolver/network failure | Retryable error; do not claim not found |
| 14 | Field | Installed, authenticated, public field | Open target field in map context |
| 15 | Field | Installed, logged out | Preserve target and resume after authentication |
| 16 | Field | App not installed | Show share-safe web field landing |
| 17 | Field | Approved/open field | Show public details and explicit navigation action |
| 18 | Field | Closed/renovation field kept public | Show temporarily unavailable state |
| 19 | Field | Pending/rejected/hidden field | Neutral unavailable state; no moderation disclosure |
| 20 | Field | Deleted/missing field | Neutral unavailable state |
| 21 | Field | Malformed/invalid field ID | No resource request; invalid-link state |
| 22 | Field | Temporary resolver/network failure | Retryable error; do not claim not found |
| 23 | Field | User chooses Navigate | Explicitly hand off destination; sharing does not auto-navigate |
| 24 | App | Android, app installed | Open app home through verified App Link |
| 25 | App | Android, app absent | Website with explicit approved Play action or website continuation |
| 26 | App | iOS, app installed and links configured | Open app home through Universal Link |
| 27 | App | iOS, app absent/unconfigured | Website with explicit approved App Store action or continuation |
| 28 | App | Desktop/unknown platform | Website with explicit choices; no forced store redirect |
| 29 | Invite | WhatsApp invitation | **Future:** compose canonical join URL; fallback safely |
| 30 | Invite | Telegram invitation | **Future:** compose canonical join URL; fallback safely |
| 31 | Invite | SMS invitation | **Future:** user-initiated composer; no contact access |
| 32 | Invite | Copy invitation link | **Future:** copy canonical URL; accessible success/failure |
| 33 | Invite | Join link while logged out | **Future:** preserve intent; confirm after authentication |
| 34 | Invite | Join link for full/ended/cancelled game | **Future:** show state; no confirmation action |
| 35 | Common | Wrong host, non-HTTPS, unsupported path/action | Reject or safe-home fallback; no resource request |
| 36 | Common | Link unfurler requests preview | Return public, read-only, side-effect-free metadata |

---

## 15. Future Implementation Acceptance Gate

A future Sharing implementation is not complete until it:

- generates only the canonical URLs in this document;
- passes the relevant scenario rows above on web and applicable physical devices;
- preserves targets across cold/warm start, authentication, language selection, and onboarding;
- proves neutral handling for invalid, missing, deleted, and hidden resources;
- proves that public previews and share payloads contain no prohibited data;
- verifies Android App Links and iOS Universal Links against the deployed canonical host;
- uses approved, live store listing URLs without automatic store redirects; and
- updates this document if the product contract changes.

---

## 16. Decision Record

- Games, fields, and the application are the approved shareable entities for the first sharing phase.
- Canonical sharing uses HTTPS on `yesh-mishak.com`; native-only schemes are not a sharing contract.
- Game links use `/game/{uuid}`; field links use `/field/{uuid}`; new shares never generate plural or legacy query forms.
- Viewing a public landing does not require authentication; interactive account actions do.
- Game invitations use `/game/{uuid}/join` in the future and never auto-join.
- Participant and creator identity are excluded from public shares and previews.
- Teams, tournaments, events, and referrals remain future work without assigned URL contracts.
- This document specifies 36 sharing scenarios and introduces no application-code changes.
