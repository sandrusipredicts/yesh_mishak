# Native Sharing Architecture

**Issue:** ISSUE-282

**Date:** 2026-07-12

**Status:** Architecture definition only - not implemented

**Depends on:** `docs/sharing-requirements.md`, `docs/deep-link-architecture.md`, `docs/external-navigation-strategy.md`, `docs/mobile-application-architecture.md`, `docs/native-plugin-governance-policy.md`

---

## 1. Purpose and Authority

This document defines the official architecture for sharing from the yesh_mishak React/Vite/Capacitor application. It translates the product requirements in ISSUE-281 into clear module boundaries, platform adapters, payload contracts, fallback behavior, and security/privacy rules for Native Share Sheet, WhatsApp, and Copy Link.

Future native-sharing implementation issues must follow this document. Any change to canonical link identity, payload ownership, public-data boundaries, or adapter responsibilities requires an architecture update before implementation.

This issue adds no plugin, share control, clipboard call, WhatsApp integration, analytics event, backend endpoint, or runtime behavior.

---

## 2. Architecture Context and Current State

The application is a shared React frontend packaged by Capacitor for Android and iOS. Platform-specific capabilities are accessed from React through narrow adapters that detect the runtime and invoke browser APIs or Capacitor plugins. Business rules and navigation state remain outside native projects.

Relevant current foundations:

| Foundation | Current state | Sharing implication |
|:---|:---|:---|
| Canonical origin | `https://yesh-mishak.com` | All shares use this HTTPS origin |
| App Link validation | Central URL validation exists in `frontend/src/utils/appLinkRoutes.js` | Outbound links must use the same route contract as inbound links |
| Native link receipt | Capacitor `getLaunchUrl()` and `appUrlOpen` are handled centrally | Shared links return through the existing inbound architecture |
| Android App Links | Repository infrastructure exists | Deployed association/device verification is still required |
| iOS Universal Links | Not complete | HTTPS links still fall back to the website until configured |
| Resource resolution | Field/game URL validation exists; content resolution remains future work | Sharing must not ship before target links resolve correctly |
| Native sharing plugin | Not installed | Any future plugin adoption follows plugin governance and Capacitor major-version alignment |
| Web sharing/clipboard | Not implemented | Browser paths require capability detection and fallbacks |
| WhatsApp sharing | Not implemented | Requires a channel adapter, not entity-specific integration |

Sharing is outbound transport. Deep-link handling is inbound navigation. They share the canonical URL contract but remain separate responsibilities.

---

## 3. Executive Architecture Decisions

1. Every mechanism embeds the same canonical HTTPS Deep Link for the selected entity.
2. Native Share Sheet is the default general-purpose action on supported native platforms; capability-aware web sharing may use the Web Share API.
3. Copy Link is the universal baseline fallback and is also available as an explicit user action.
4. WhatsApp is an explicit channel adapter using an allowlisted provider compose endpoint; it does not own or alter resource links.
5. Entity-specific, localized templates generate share titles and text from share-safe public data.
6. A shared domain layer owns canonical link and payload generation; platform adapters own only transport invocation.
7. Initial sharing records no analytics events. A structured local result contract reserves future privacy-reviewed instrumentation without adding tracking now.
8. All share attempts are user-initiated, read-only, and must not mutate game, field, invitation, or account state.

---

## 4. Target Layering and Ownership

```text
React share entry point
  -> Sharing orchestrator
       -> Resource/shareability validator
       -> Canonical link builder
       -> Localized payload factory
       -> Selected transport adapter
            -> Native Share adapter (Capacitor / Web Share API)
            -> WhatsApp adapter (allowlisted compose URL)
            -> Clipboard adapter (native/web clipboard capability)

Recipient opens canonical HTTPS link
  -> Existing OS/browser Deep Link transport
  -> Existing central URL validator
  -> Resource resolver and authenticated/public landing behavior
```

### 4.1 Responsibility Matrix

| Responsibility | Owning layer | Must not be duplicated in |
|:---|:---|:---|
| Canonical origin, route, and UUID serialization | Shared canonical link builder | UI components, WhatsApp adapter, native adapter, clipboard adapter |
| Entity eligibility and latest public state | Backend/resource resolver plus orchestration preflight | Native project, templates, transport adapters |
| Share-safe data selection | Shared payload factory using the ISSUE-281 allowlist | UI event handlers, provider adapters |
| Entity-specific text and title | Localized template registry/payload factory | Native platform code and provider URLs |
| Mechanism selection and fallback sequence | Sharing orchestrator | Entity components and native platform projects |
| Native Share Sheet invocation | Native share adapter | Canonical link builder and UI components |
| Browser Share API invocation | Native/web share adapter | Templates and resource resolver |
| WhatsApp compose invocation | WhatsApp adapter | Entity components and canonical builder |
| Clipboard invocation and result normalization | Clipboard adapter | UI components and templates |
| Success/error feedback | React UI, based on normalized adapter result | Native project and payload factory |
| Incoming link validation and resolution | Existing Deep Link validator/resolver | Sharing adapters |
| Authorization and resource visibility | Backend | Client link or payload code |

UI components provide an entity type and identifier to the orchestrator. They must not concatenate URLs, assemble channel text, call native plugins directly, or implement channel fallback rules.

### 4.2 Conceptual Interfaces

These are architecture contracts, not prescribed filenames or implementation:

```text
buildCanonicalShareLink(entityType, resourceId, intent?) -> HTTPS URL
buildSharePayload(entityType, shareSafeResource, locale, intent?) -> { title, text, url }
share(payload, mechanism) -> { outcome, mechanism, errorCategory? }
```

`outcome` is one of `shared`, `copied`, `cancelled`, `unavailable`, or `failed`. Cancellation is a normal outcome, not an application error.

---

## 5. Canonical Link Architecture

### 5.1 Decision: One Deep Link for Every Mechanism

**Yes. Every sharing mechanism uses the same canonical Deep Link for the same entity and intent.**

| Entity/intent | Canonical link |
|:---|:---|
| Game | `https://yesh-mishak.com/game/{game_id}` |
| Field | `https://yesh-mishak.com/field/{field_id}` |
| Application | `https://yesh-mishak.com/` |
| Future game invitation | `https://yesh-mishak.com/game/{game_id}/join` |

Native Share Sheet, WhatsApp, and Copy Link must embed or copy the identical canonical URL returned by the shared link builder. Singular routes are generated. Plural routes and legacy query forms may be accepted by inbound compatibility parsing but are never generated.

### 5.2 Provider-Specific Link Decision

Provider-specific **resource links are not allowed**. There is no WhatsApp-specific game URL, native-only resource scheme, channel token, or alternate field URL.

Provider-specific **transport launch URLs are allowed only inside an adapter**, for example an allowlisted WhatsApp compose endpoint whose encoded text contains the canonical yesh_mishak URL. A transport URL is ephemeral, is not displayed as the shared resource identity, and must not change authorization, attribution, or destination semantics.

### 5.3 Link Generation Ownership

A single shared frontend domain module owns outbound link generation from a configured canonical origin, an allowlisted entity route, and a validated UUID v4. App sharing uses the allowlisted root route without an identifier. The module must produce an absolute HTTPS URL and must reject unsupported entities, actions, malformed IDs, or non-production hosts for production shares.

The inbound Deep Link validator remains independently authoritative when a recipient opens the result. Outbound generation never bypasses inbound validation. Server-rendered preview/canonical metadata must follow the same documented route contract and must not introduce a second URL format.

---

## 6. Share Payload and Text Architecture

### 6.1 Payload Contract

The normalized payload passed to a transport contains:

| Field | Purpose | Rule |
|:---|:---|:---|
| `title` | Short entity-aware title where the platform supports it | Localized; public information only |
| `text` | Human-readable context | Localized template; canonical URL not manually duplicated when the API has a separate URL field |
| `url` | Recipient destination | Canonical absolute HTTPS Deep Link only |

Adapters may map or combine these fields to match provider APIs, but they cannot add entity data. If a provider accepts only text, the adapter combines localized text and canonical URL exactly once. If the provider accepts `title`, `text`, and `url` separately, it passes the normalized fields without embedding the URL twice.

### 6.2 Decision: Entity-Specific Templates

Every approved shareable entity has its own template because recipients need different context:

| Entity | Template content |
|:---|:---|
| Game | Field name, sport, scheduled/current state, aggregate capacity when available, canonical link |
| Field | Approved field name, sport/type or approximate city when available, canonical link |
| Application | Product name, short approved description, canonical website link |
| Future invitation | Invitation call to action plus game-safe context and canonical `/join` link |

Templates share formatting helpers and privacy rules but do not collapse into one generic sentence. Missing optional fields are omitted cleanly rather than rendered as placeholders or guessed values.

### 6.3 Localization Strategy

- The payload uses the sender's active app locale at the moment sharing is invoked.
- Templates live in the existing localization system and follow Hebrew/English RTL/LTR rules.
- Dates and times use locale-aware formatting and the product's approved time-zone behavior.
- Provider names and canonical URLs are not translated.
- Transport adapters receive finalized text and do not localize it.
- The receiving landing page localizes independently for the recipient; shared text does not force the recipient's app language.

### 6.4 Future Customization

Version 1 uses approved fixed templates. Free-form editing inside yesh_mishak, per-user signatures, inviter names, campaign text, and provider-specific entity templates are not part of this architecture. A platform share sheet may allow the user to edit content after handoff because that editing belongs to the operating system/recipient app.

Future template customization must remain optional, preserve the canonical URL, apply the public-data allowlist, and receive product/privacy review before implementation.

---

## 7. Native Share Sheet

### 7.1 When It Is Used

The Native Share Sheet is used when a user selects the general **Share** action on Android or iOS and the native sharing capability is available. On compatible browsers, the same general action may use the Web Share API as progressive enhancement. Explicit WhatsApp and Copy Link actions use their dedicated adapters instead.

Sharing is triggered only from a direct user gesture after the resource and payload are prepared. It must never open automatically on link arrival, page load, notification receipt, authentication completion, or resource refresh.

### 7.2 Supported Platforms

| Platform | Primary invocation | Required fallback |
|:---|:---|:---|
| Android Capacitor | Future approved Capacitor 8-compatible share plugin | Copy Link |
| iOS Capacitor | Same approved Capacitor plugin | Copy Link |
| Mobile/desktop web with Web Share API | `navigator.share` after capability check | Copy Link |
| Web without Web Share API | Do not show a nonfunctional sheet action, or route general Share to Copy Link | Manual-selection fallback if clipboard also fails |

Plugin selection and installation are separate implementation work governed by `docs/native-plugin-governance-policy.md`. An official Capacitor plugin is preferred if compatible and approved; this document does not authorize a dependency change.

### 7.3 Information Passed

The adapter receives only the normalized `title`, `text`, and canonical `url`. It passes no files, images, coordinates, participant data, user identity, authentication data, internal API URL, or provider-specific resource link.

### 7.4 Fallback and Errors

1. Validate resource eligibility and build the payload before invoking the sheet.
2. Check runtime/plugin/API availability.
3. Invoke the native or browser share capability.
4. If unavailable or invocation fails before handoff, offer/attempt Copy Link according to the user's selected general Share action and show localized feedback.
5. If Copy Link fails, show the canonical URL in a selectable field with a manual-copy instruction.

User cancellation returns `cancelled`, closes any loading state, and shows no alarming error. Unsupported capability returns `unavailable`. Platform/plugin failure returns `failed` with a normalized category and a safe fallback. Raw native exceptions and provider details are not shown to users.

A platform API generally cannot prove that a recipient app sent or delivered content. A resolved invocation is treated as handoff, not delivery confirmation.

---

## 8. WhatsApp Share

### 8.1 Sharing Flow

1. User selects the explicit WhatsApp action.
2. The orchestrator validates the current resource and requests the entity-specific localized payload.
3. The WhatsApp adapter combines the finalized text and canonical URL exactly once.
4. The adapter URL-encodes the complete message and opens an allowlisted WhatsApp share/compose endpoint from the user gesture.
5. WhatsApp lets the user choose a recipient and send; yesh_mishak never selects contacts or sends automatically.

### 8.2 Native App and Browser Behavior

On Android/iOS, the adapter may use a verified provider-supported universal/HTTPS compose link that the OS can hand to the installed WhatsApp application. A future native capability check or approved launcher may be used only inside the adapter. A raw `whatsapp://` resource contract is not required and must not replace the canonical link.

If WhatsApp is missing or native launch is unavailable, the adapter may open the provider's supported browser experience. If that experience cannot compose the share, return to a usable app state and offer Copy Link. Do not redirect to an app store without explicit user confirmation, loop between native and web URLs, or claim the message was sent.

On desktop web, the adapter may use the supported WhatsApp web compose experience. Popup blocking or provider rejection is a normalized failure followed by Copy Link/manual-copy fallback.

### 8.3 Text and Link Rules

WhatsApp receives the same entity template and canonical link as the Native Share Sheet. The adapter may add only transport-required separators/encoding. It must not add inviter identity, phone number, tracking data, channel identifiers, shortened URLs, or a second link.

The URL must be visible in the composed message so it remains usable when link previews are unavailable. Open Graph preview content is owned by the canonical web landing architecture, not the WhatsApp adapter.

---

## 9. Copy Link

### 9.1 Clipboard Flow

1. User selects Copy Link, or another sharing mechanism enters its documented fallback.
2. Validate the entity type and identifier and generate the canonical absolute URL.
3. Check the active platform's clipboard capability and required secure/user-gesture context.
4. Write only the canonical URL, not the full share message.
5. Return a normalized result so the UI can provide feedback.

### 9.2 Supported Platforms

| Platform | Clipboard path | Fallback |
|:---|:---|:---|
| Android/iOS Capacitor | Approved native clipboard capability/plugin if required | Selectable URL |
| Secure-context web with Clipboard API | `navigator.clipboard.writeText` after capability check | Selectable URL |
| Browser without permission/API support | No hidden/deprecated clipboard trick | Selectable URL with manual-copy instruction |

Clipboard plugin adoption, if needed, is separate governed implementation work. The adapter may choose the runtime path; callers remain platform-agnostic.

### 9.3 Success and Failure Feedback

On confirmed write, show a short localized accessible status such as **Link copied**, announced through an appropriate live region without moving focus. Do not show success before the write promise/callback confirms completion.

Permission denial, unavailable API, insecure context, native failure, or rejected write produces a non-technical message and a selectable canonical URL. The user remains on the same game/field/app surface. Failures do not clear state, navigate away, or expose raw errors.

---

## 10. Deep Link Integration

All mechanisms integrate at the canonical URL boundary:

| Outbound mechanism | Embedded/copied destination | Inbound handling |
|:---|:---|:---|
| Native Share Sheet | Canonical entity HTTPS link | OS App/Universal Link or browser -> central validator -> resolver |
| WhatsApp | Same canonical link inside encoded text | Recipient tap -> same OS/browser path |
| Copy Link | Same canonical link only | Recipient paste/tap -> same OS/browser path |
| Future QR | Same canonical link encoded in QR | Scan -> same OS/browser path |

No transport adapter resolves incoming links. No inbound resolver invokes sharing. The shared canonical link works whether the app is installed or not and preserves ISSUE-281 authentication, public-preview, finished/deleted resource, and website fallback behavior.

### 10.1 Invalid and Unavailable Resources

- The outbound orchestrator validates the local entity type/UUID and refreshes or checks shareability where required before presenting a share payload.
- The recipient-side resolver always validates again because resources can change after sharing.
- Malformed identifiers are rejected before a resource request and show the standard invalid-link state.
- Valid but deleted, hidden, rejected, or missing resources use the same neutral unavailable state.
- Expired/finished or cancelled games use the retained read-only state defined by ISSUE-281 when available and expose no Join action.
- Temporary network/backend failures remain retryable and are not mislabeled as invalid or deleted.

Possession of a canonical link never grants authorization or freezes resource state.

---

## 11. Analytics Decision

### 11.1 Initial Architecture

**Share events are not tracked in the initial sharing implementation.** No analytics SDK, event emission, dashboard, attribution parameter, or server-side share counter is authorized by this document.

Therefore, what is tracked initially is: **nothing**. The normalized adapter outcome exists for UI behavior and testing only and must not be persisted or transmitted as analytics.

### 11.2 Future Instrumentation Boundary

A later separately approved analytics/privacy issue may consume normalized outcomes at the orchestrator boundary. If approved, the maximum non-content event dimensions are:

- mechanism category: native sheet, WhatsApp, or copy link;
- entity type: game, field, or app;
- runtime/platform category;
- outcome category: handoff, copied, cancelled, unavailable, or failed; and
- coarse error category, without raw exception text.

The following are intentionally not tracked even in that future model: canonical/full URL, game or field ID, user ID, recipient/contact, selected target application, shared text, field coordinates, user location, authentication token/state, clipboard contents, phone number, delivery/read status, or free-form error data. No analytics parameter may be added to the canonical link without revising ISSUE-281 and this architecture.

---

## 12. Security Architecture

1. The outbound builder accepts only allowlisted entity types/actions and UUID v4 identifiers and emits HTTPS on the exact canonical host.
2. The inbound validator independently checks scheme, exact host, path, action, segment count, and identifier before resolving.
3. Provider compose/launcher hosts and schemes are fixed in channel adapters; resource data cannot select a provider host.
4. Text and URL values are encoded at the transport boundary exactly once to prevent parameter or message injection.
5. Resource visibility and authorization are enforced by the backend; client validation is defense in depth.
6. Deleted, hidden, rejected, and missing resources return the same neutral public result without moderation/deletion disclosure.
7. Malformed identifiers cause no resource request. Valid but unavailable resources never fall back to a different resource.
8. Expired, finished, full, or cancelled games refresh authoritative state before any action and never auto-join.
9. Sharing is initiated only by a direct user gesture. Link preview fetches and inbound link opens are read-only and side-effect free.
10. Raw platform/provider exceptions are normalized; logs must not include complete URLs, payload text, identifiers, tokens, or clipboard contents.

---

## 13. Privacy Architecture

Share payloads contain public information only. They must never contain:

- user, creator, organizer, participant, or referrer identifiers;
- participant names, contact details, recipient data, or account/profile information;
- user location, navigation origin, saved location, or device location;
- authentication/access/refresh tokens, session state, push tokens, or internal API URLs;
- private notes, moderation state, reports, notification preferences, or diagnostic data.

Field sharing does not include the sender's location. Exact public field coordinates are resolved from the canonical field resource only for map/navigation display and are not copied into share text. Game sharing uses aggregate capacity, not a participant roster. Native/provider adapters receive only the minimized normalized payload needed for the explicit handoff.

The app does not request contacts permission for WhatsApp, Native Share Sheet, or SMS-style future sharing. Recipient selection belongs to the operating system/provider outside yesh_mishak.

---

## 14. Error and Fallback Matrix

| Condition | Required result |
|:---|:---|
| Invalid local entity/ID | Disable/reject share; no transport invocation |
| Resource became unavailable before share | Neutral unavailable feedback; do not share stale private content |
| Native/Web Share API unavailable | Copy canonical link |
| Native Share Sheet cancelled | Normal cancellation; no error toast and no automatic fallback |
| Native Share invocation fails | Offer/attempt Copy Link, then selectable URL |
| WhatsApp unavailable | Browser provider experience when usable, then Copy Link |
| WhatsApp/browser popup blocked | Copy Link or selectable URL |
| Clipboard write succeeds | Accessible localized “Link copied” feedback |
| Clipboard unavailable/denied/fails | Selectable canonical URL and manual-copy guidance |
| Recipient opens malformed link | Invalid-link state; no resource request |
| Recipient opens deleted/hidden resource | Neutral unavailable state |
| Recipient opens expired/finished game | Read-only ended state when retained; no Join |
| Network failure during recipient resolution | Retryable temporary error |

Fallbacks must be finite. They must not loop, navigate away from the source content unexpectedly, or claim successful delivery.

---

## 15. Future Expansion - Reserved, Not Implemented

### 15.1 QR Sharing

**Future / Not implemented.** A QR code may encode only the same canonical HTTPS link returned by the shared link builder. QR rendering/scanning, accessibility, download safety, and visual error correction require separate requirements. QR must not introduce a QR-specific resource URL.

### 15.2 Team Sharing

**Future / Not implemented.** Add a team entity/template only after public/private team visibility, roster privacy, permissions, deletion, and canonical route are approved. It must reuse the same builder/payload/adapter layers.

### 15.3 Tournament Sharing

**Future / Not implemented.** Add a tournament entity/template only after organizer authority, schedule/results visibility, lifecycle, and canonical route are approved. Transport adapters remain unchanged.

### 15.4 Event Sharing

**Future / Not implemented.** Add an event entity/template only after event identity, attendance/privacy rules, location visibility, lifecycle, and canonical route are approved. Transport adapters remain unchanged.

### 15.5 Referral Sharing

**Future / Not implemented and currently out of scope.** Referral identity, attribution, rewards, consent, abuse controls, expiration, and privacy require a separate product/security architecture. Referral parameters or identifiers must not be added to current canonical links.

---

## 16. Out of Scope

- Installing or selecting a Capacitor share/clipboard plugin.
- Adding share buttons, menus, templates, translations, adapters, or tests.
- Calling Native Share Sheet, Web Share API, WhatsApp, or clipboard APIs.
- Implementing game/field Deep Link resource resolution or public preview endpoints.
- Configuring iOS Universal Links or changing Android App Links.
- Analytics implementation, dashboards, attribution, campaigns, or share counters.
- QR codes, teams, tournaments, events, referrals, rewards, or invitations.
- Contact access, recipient selection, delivery confirmation, or message status.
- Application, native-project, dependency, environment, or backend changes.

---

## 17. Architectural Decision Register

This document records **20 architectural decisions**.

| ID | Decision |
|:---|:---|
| AD-01 | Every mechanism uses the same canonical HTTPS Deep Link for the same entity/intent |
| AD-02 | Singular `/game/{uuid}` and `/field/{uuid}` routes are the only generated resource forms |
| AD-03 | Provider-specific resource links are prohibited; provider transport URLs are adapter-only |
| AD-04 | A shared domain module exclusively owns canonical outbound link generation |
| AD-05 | The inbound validator independently revalidates every opened shared link |
| AD-06 | Entity-specific localized templates generate normalized title/text/URL payloads |
| AD-07 | Transport adapters never select entity data or localize payloads |
| AD-08 | Native Share Sheet is the primary general-share path on capable native platforms |
| AD-09 | Compatible web platforms may use Web Share API as progressive enhancement |
| AD-10 | Copy Link is the explicit universal baseline and terminal automated fallback |
| AD-11 | Copy Link writes only the canonical URL, not the full message |
| AD-12 | WhatsApp is an explicit channel adapter and never sends or selects contacts automatically |
| AD-13 | General-share cancellation is normal and does not trigger fallback or error feedback |
| AD-14 | Adapter handoff is not interpreted as message delivery confirmation |
| AD-15 | Sharing is user-initiated and has no game/account side effects |
| AD-16 | Initial sharing emits and persists no analytics events |
| AD-17 | Future analytics, if separately approved, consume normalized outcomes at the orchestrator only |
| AD-18 | Share payloads contain public data only and exclude identity, location, and authentication data |
| AD-19 | Backend visibility/authorization remains authoritative for current resource state |
| AD-20 | Future entities reuse the same builder, payload factory, orchestrator, adapters, and inbound resolver |

---

## 18. Future Implementation Gate

Before any native sharing issue is complete, it must prove that:

- the relevant plugin/API was separately approved and is compatible with the project's Capacitor major version;
- no entity component constructs URLs, templates, or provider links directly;
- Native Share Sheet, WhatsApp, and Copy Link output the identical canonical URL for the same entity/intent;
- entity templates are localized and contain only ISSUE-281-approved public fields;
- capability absence, cancellation, provider failure, clipboard denial, and manual-copy fallback behave as specified;
- outbound and inbound validation cover malformed, wrong-host, unsupported-path, deleted, hidden, and expired resources;
- no user identifier, participant data, user location, token, full URL, or payload text is logged or tracked;
- Android/iOS physical-device behavior and browser fallbacks are verified; and
- the initial implementation contains no analytics emission.

---

## 19. Decision Summary

- **Canonical link:** Yes, every mechanism uses the same canonical entity Deep Link.
- **Provider links:** Allowed only to invoke an allowlisted transport; never as alternate resource identity.
- **Link owner:** One shared canonical link builder.
- **Payload owner:** One localized entity-template/payload layer.
- **Invocation owner:** One adapter per native/web transport.
- **Invalid resources:** Validate before share and again on receipt; malformed IDs are invalid, while deleted/hidden resources are neutrally unavailable.
- **Analytics:** Nothing is tracked initially.
- **Privacy:** Public information only; no user identifiers, user location, or authentication tokens.
- **Future:** QR, team, tournament, event, and referral sharing are reserved and not implemented.
