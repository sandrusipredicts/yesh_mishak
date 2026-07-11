# Deep Link Architecture

**Issue:** ISSUE-267
**Date:** 2026-07-08
**Dependency:** `docs/navigation-sharing-entry-points-audit.md` (ISSUE-266)
**Status:** Architecture definition only — no implementation

---

## 1. Purpose

Deep Links allow users to open specific content within the yesh_mishak application from external sources — shared WhatsApp messages, push notification taps, marketing campaigns, or direct URLs. Without deep links, every external entry lands on the map at the default center, and users must manually find the relevant field or game.

This architecture builds on the ISSUE-266 entry points audit, which documented:
- All current internal navigation paths and their limitations
- The absence of any sharing, deep linking, or external URL handling
- The incomplete push notification click-through flow
- The identifiers and resource states needed for link resolution
- The recommended URL route contract

This document defines the complete deep link architecture — URL structure, routing strategy, platform integration, auth handling, and error behavior — so that implementation can proceed with a stable, approved contract.

---

## 2. Current State Summary

From `docs/navigation-sharing-entry-points-audit.md`:

- **Routing model:** Custom client-side routing via `window.history.pushState` and React state in `App.jsx`. Not React Router. Three routes: `/` (MapPage), `/my-games` (MyGamesPage), `/admin` (AdminPage). No dynamic route parameters.
- **No deep link configuration:** No Android intent filters, no iOS URL schemes or universal links, no `appUrlOpen` listener in Capacitor, no custom URL scheme registered on any platform.
- **Notification target data exists but resolution is incomplete:** Push notification payloads carry `game_id` and `field_id`. The service worker constructs `/?game_id={id}` on notification tap, but this query parameter is never consumed by the frontend on page load. In-app notification inbox navigation works via `handleNotificationTarget()`, which finds a field by ID and opens `FieldDetailsPanel`.
- **No sharing features:** No share buttons, no clipboard API, no WhatsApp links, no Web Share API usage anywhere in the codebase.
- **Content is UUID-identifiable:** `field_id` and `game_id` are UUID v4 values. `GET /fields/{field_id}` exists as a public endpoint. No direct `GET /games/{game_id}` public endpoint exists.

---

## 3. Deep Link Principles

1. **Stable canonical URLs.** Each shareable resource has exactly one canonical URL path. URLs do not change over time, do not depend on app version, and do not encode transient state.

2. **UUID-based resource resolution.** Links resolve content by a single UUID identifier. No composite keys, no slug-based lookups, no encoded query strings as primary identifiers.

3. **Server remains source of truth.** The client never trusts locally cached state for deep link resolution. Every deep link triggers a fresh API call to the backend to verify the resource exists, is accessible, and is in the expected state.

4. **Links must tolerate logged-out users.** A deep link arriving when the user is not authenticated must store the intent, present login, and resume navigation after successful authentication.

5. **Links must tolerate missing or expired resources.** A deep link to a deleted game, closed field, or non-existent resource must show a clear, localized message — never crash, never show a blank screen, never leave the user in a broken state.

6. **Universal contract.** The same URL structure must work across all platforms and entry vectors: web browser, Android Capacitor WebView, future iOS, WhatsApp message previews, push notification taps, and marketing campaigns. Platform-specific mechanics (intent filters, universal links, `appUrlOpen`) are transport layers — they all resolve to the same canonical path.

---

## 4. Canonical URL Structure

### 4.1 Supported Routes

| Route | Purpose | Required Parameter | Example |
|:---|:---|:---|:---|
| `/field/{field_id}` | Open field details | UUID | `/field/a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| `/game/{game_id}` | Open game details (via its field) | UUID | `/game/f1e2d3c4-b5a6-7890-1234-567890abcdef` |
| `/game/{game_id}/join` | Open game with join intent | UUID | `/game/f1e2d3c4-b5a6-7890-1234-567890abcdef/join` |
| `/m/{slug}` | Future marketing / campaign link | Alphanumeric slug | `/m/summer-2026` |

### 4.2 Path Parameters as Canonical Identifiers

Resource identifiers must be path parameters, not query parameters. Path parameters are:

- **Canonical:** `/game/abc-123` is the one true URL for that game.
- **Cacheable and indexable:** Standard HTTP semantics treat different paths as different resources.
- **Unambiguous:** No risk of parameter collisions or ordering issues.
- **Share-friendly:** Clean URLs display well in WhatsApp previews and social cards.

### 4.3 Legacy Query Parameter Compatibility

The existing service worker constructs `/?game_id={game_id}` for push notification taps. This format should be supported temporarily as a **legacy input** — the deep link resolver should parse it and redirect internally to the canonical `/game/{game_id}` route. It must not be used as the public contract, must not be documented in user-facing materials, and must not be generated by any new code.

| Format | Status | Behavior |
|:---|:---|:---|
| `/game/{game_id}` | Canonical | Primary resolution path |
| `/?game_id={game_id}` | Legacy | Parse and resolve as `/game/{game_id}`; do not generate |
| `/?field_id={field_id}` | Legacy | Parse and resolve as `/field/{field_id}`; do not generate |

---

## 5. Game Links

### 5.1 Route Definition

| Route | Intent | Example |
|:---|:---|:---|
| `/game/{game_id}` | View game details | `/game/f1e2d3c4-b5a6-7890-1234-567890abcdef` |
| `/game/{game_id}/join` | View game and auto-prompt join | `/game/f1e2d3c4-b5a6-7890-1234-567890abcdef/join` |

### 5.2 Required Identifier

`game_id` — UUID v4 format. Validated client-side before API call.

### 5.3 Expected Behavior by Game State

| Game State | `/game/{id}` Behavior | `/game/{id}/join` Behavior |
|:---|:---|:---|
| Open (has capacity) | Show field panel with game details | Show field panel + auto-trigger join flow |
| Full | Show field panel, "game is full" message | Show field panel, "game is full" (no join) |
| Finished/closed | Show field panel, "game has ended" message | Show field panel, "game has ended" (no join) |
| Cancelled | Show field panel, "game was cancelled" message | Show field panel, "game was cancelled" (no join) |
| Scheduled (future, open) | Show field panel with scheduled time + join button | Show field panel + auto-trigger join flow |
| Scheduled (future, full) | Show field panel with scheduled time, "game is full" | Show field panel, "game is full" (no join) |
| Missing/deleted | "Game not found" fallback screen | "Game not found" fallback screen |

### 5.4 Logged-Out Behavior

1. Store deep link intent (`game_id` + optional `/join` flag).
2. Show login screen.
3. After successful login, resume: fetch game → resolve field → open field panel with game.

### 5.5 Backend Requirement

A direct `GET /games/{game_id}` public endpoint must be added. Currently, games are only accessible through `GET /fields/{field_id}` (which includes active/upcoming games) or user-specific endpoints like `GET /games/me`. The deep link resolver needs to map `game_id` → `field_id` → field UI state.

The endpoint should return at minimum: `game_id`, `field_id`, `status`, `sport_type`, `scheduled_at`, `players_present`, `max_players`.

### 5.6 Frontend Requirement

The route resolver must:
1. Parse `game_id` from URL path.
2. Call `GET /games/{game_id}` to get the game and its `field_id`.
3. Call `GET /fields/{field_id}` to get full field data (or combine into one call if the backend endpoint includes field data).
4. Set `selectedField` state to open `FieldDetailsPanel` with the target game visible.
5. If `/join` path suffix is present and game is joinable, auto-trigger the join flow.

---

## 6. Field Links

### 6.1 Route Definition

| Route | Intent | Example |
|:---|:---|:---|
| `/field/{field_id}` | View field details | `/field/a1b2c3d4-e5f6-7890-abcd-ef1234567890` |

### 6.2 Required Identifier

`field_id` — UUID v4 format. Validated client-side before API call.

### 6.3 Expected Behavior by Field State

| Field State | Behavior |
|:---|:---|
| Approved + verified + open | Map opens, flies to field location, opens `FieldDetailsPanel` |
| Pending approval | "This field is pending approval" message. Panel does not open. |
| Rejected | "Field not found" fallback screen |
| Closed / renovation | "This field is temporarily unavailable" message |
| Missing / deleted | "Field not found" fallback screen |

### 6.4 Logged-Out Behavior

1. Store deep link intent (`field_id`).
2. Show login screen.
3. After successful login, resume: fetch field → fly to field → open field panel.

### 6.5 Backend Requirement

`GET /fields/{field_id}` already exists. It returns field data including active and upcoming games. Must return consistent 404 for non-existent fields. Should distinguish between "not found" (404) and "exists but not accessible" (field pending/rejected — the current behavior of filtering these out results in 404, which is acceptable for security).

### 6.6 Frontend Requirement

The route resolver must:
1. Parse `field_id` from URL path.
2. Call `GET /fields/{field_id}`.
3. If found: set map center to field coordinates, set `selectedField` state.
4. If not found: show "Field not found" fallback.

---

## 7. Notification Links

### 7.1 Payload Structure

Existing notification payloads include:

| Field | Type | Present In | Purpose |
|:---|:---|:---|:---|
| `type` | String | All notifications | Notification category (e.g., `game_created`, `player_joined_game`) |
| `game_id` | UUID | Game-related notifications | Target game identifier |
| `field_id` | UUID | Game-related notifications | Target field identifier |
| `notification_id` | UUID | All notifications | Notification record identifier |
| `field_name` | String | Game-related notifications | Display name (template variable) |
| `scheduled_at` | ISO 8601 | Scheduled game notifications | When game starts |

### 7.2 Notification → Canonical Route Mapping

Push notification taps should resolve into the same canonical routes:

| Notification Type | Target Route | Resolution |
|:---|:---|:---|
| `game_created` | `/game/{game_id}` | Open field with new game |
| `player_joined_game` | `/game/{game_id}` | Open field with user's game |
| `game_closed` | `/game/{game_id}` | Open field, show "game ended" |
| `game_extended` | `/game/{game_id}` | Open field with extended game |
| `scheduled_game_cancelled` | `/game/{game_id}` | Open field, show "game cancelled" |
| `scheduled_game_reminder` | `/game/{game_id}` | Open field with upcoming game |
| `test_push` | `/` | Home / map |

### 7.3 Tap Behavior by App State

| App State | Background Notification Tap | Foreground Notification |
|:---|:---|:---|
| App killed | Open app → auth check → resolve canonical route → navigate | Show in-app toast/banner with action button → navigate on tap |
| App backgrounded | Resume app → resolve canonical route → navigate | N/A (app not visible) |
| App foregrounded | N/A (notification shown in-app) | Show in-app toast/banner → navigate on tap |

### 7.4 Existing Gap

From ISSUE-266: The service worker constructs `/?game_id={game_id}` but the frontend does not parse this on load. The fix is twofold:

1. **Short-term:** Add `URLSearchParams` parsing on MapPage mount to handle the legacy `?game_id` format.
2. **Long-term:** Update the service worker to construct canonical `/game/{game_id}` URLs. The deep link resolver handles the rest.

The in-app notification inbox (`handleNotificationTarget`) already correctly resolves `field_id`/`game_id` to UI state. This pattern should be reused by the deep link resolver.

---

## 8. Future Marketing Links

### 8.1 Route Family

| Route | Purpose | Example |
|:---|:---|:---|
| `/m/{slug}` | Campaign or marketing landing | `/m/summer-2026` |
| `/m/{slug}?ref={source}` | Campaign with attribution | `/m/summer-2026?ref=instagram` |

### 8.2 Design Constraints

- Marketing links must not replace or alias game/field canonical links. `/m/cool-game` must not be an alternative path to `/game/{game_id}`.
- Slugs are alphanumeric with hyphens, resolved server-side to a target screen or resource.
- Tracking parameters (`ref`, `utm_source`, etc.) may be present but must not be required for resource resolution. The link must work identically with or without tracking parameters.
- Marketing links can map to: app home, onboarding flow, specific field, specific game, or a static landing page.

### 8.3 Implementation

Marketing links are out of scope for the initial deep link implementation. The route family `/m/{slug}` is reserved. Implementation should be a separate future issue that adds:
- A backend endpoint to resolve slugs to target screens.
- Client-side handling in the deep link resolver.
- Analytics event emission on marketing link arrival.

---

## 9. Routing Strategy

### 9.1 Central Deep Link Resolver

All deep link resolution must flow through a single central resolver layer. This avoids scattering link handling across components and ensures consistent auth gating, error handling, and loading states.

```
URL/intent arrives
  │
  ├─ 1. Route Parsing
  │     Parse pathname into { type, id, action }
  │     Handle legacy query params (/?game_id=X → /game/X)
  │     Validate UUID format
  │     If unrecognized → Fallback (unknown route)
  │
  ├─ 2. Auth Gate
  │     If not authenticated:
  │       Store intent { type, id, action }
  │       Show login screen
  │       On login success → resume from step 3
  │     If authenticated → continue
  │
  ├─ 3. Resource Fetch
  │     Call appropriate API endpoint:
  │       /field/{id} → GET /fields/{field_id}
  │       /game/{id} → GET /games/{game_id} (new endpoint)
  │     Show loading indicator during fetch
  │
  ├─ 4. Resource State Validation
  │     Check HTTP status and resource state:
  │       404 → "Not found" fallback
  │       Field pending/rejected → appropriate message
  │       Game closed/cancelled → appropriate message
  │       Accessible → continue
  │
  ├─ 5. UI Target Resolution
  │     Map resource to UI state:
  │       Field → setSelectedField, fly to coordinates
  │       Game → resolve field_id, setSelectedField with game context
  │       Game/join → same as game + auto-trigger join
  │     Navigate to MapPage if not already there
  │
  └─ 6. Fallback
        If any step fails:
          Show localized error message
          Provide "Go to Map" button
          Never crash, never show blank screen
```

### 9.2 Intent Storage

When a deep link arrives for a logged-out user, the intent must be stored so it survives the login flow:

| Storage | Contents | Lifetime |
|:---|:---|:---|
| `sessionStorage` (web) / in-memory (native) | `{ type: 'game', id: 'uuid', action: 'join' }` | Cleared after resolution or on explicit navigation away |

### 9.3 Integration with Existing Navigation

The resolver must be compatible with the existing `App.jsx` pathname routing model:

- `/field/{id}` and `/game/{id}` are recognized as valid pathnames.
- After resolution, the pathname can be normalized to `/` (since MapPage handles all content display).
- Back navigation from a deep-linked panel returns to the map, not to the external source.
- The resolver does not require React Router — it can be implemented as a function that runs on mount and on `popstate` events.

---

## 10. Unsupported Links

| Scenario | Example | Expected Behavior |
|:---|:---|:---|
| Unknown route | `/settings`, `/profile`, `/xyz` | Show "Page not found" with "Go to Map" button |
| Invalid UUID | `/game/not-a-uuid`, `/field/123` | Show "Invalid link" message |
| Unsupported `target_type` | Notification with `type: 'unknown'` | Navigate to home `/` |
| Missing required parameter | `/game/` (no game_id), `/field/` (no field_id) | Show "Invalid link" message |
| Legacy query link | `/?game_id=X` | Parse and resolve as `/game/X` (compatibility) |
| Unsupported app version | Link format from future version | Show "Please update the app" if format is unrecognizable |
| Unsupported platform | iOS link before iOS build exists | Web fallback — link opens in mobile browser |

---

## 11. Expired / Invalid Resource Links

| Scenario | HTTP Response | User-Facing Behavior |
|:---|:---|:---|
| Deleted/missing game | 404 | "Game not found" message with "Go to Map" button |
| Closed/finished game | 200 (game data with terminal status) | "This game has ended" message. Field panel visible with game info. |
| Full game | 200 (game data with `full` status) | "This game is full" message. Field panel visible. No join button. |
| Past scheduled game | 200 (game data, `scheduled_at` in past) | Show game as finished or started. Field panel visible. |
| Deleted/missing field | 404 | "Field not found" message with "Go to Map" button |
| Pending field | 404 (filtered by visibility rules) | "Field not found" message |
| Rejected field | 404 (filtered by visibility rules) | "Field not found" message |
| User without permission | 401 / 403 | Redirect to login (401) or "Access denied" (403) |
| Network failure | Timeout / connection error | "Could not load content. Check your connection." with retry button |

---

## 12. Auth-State Matrix

| Auth State | Deep Link Behavior | Post-Auth Action |
|:---|:---|:---|
| Logged in, session valid | Resolve link immediately — fetch resource, open UI | N/A |
| Logged out | Store intent → show login → resume on success | Retrieve stored intent → resolve link |
| Expired session | Session validation fails → clear session → same as logged out | Same as logged out |
| New user (first launch) | Store intent → language selection → onboarding → login → resume | Retrieve stored intent → resolve link |
| Admin | Same as logged in. Admin links (`/admin`) are separate and do not use deep link resolver. | N/A |

---

## 13. Resource-State Matrix

### 13.1 Field States

| Field State | API Response | Deep Link UI |
|:---|:---|:---|
| Approved + open | 200 with field data + games | Fly to field, open FieldDetailsPanel |
| Pending | 404 (not visible) | "Field not found" fallback |
| Rejected | 404 (not visible) | "Field not found" fallback |
| Closed | 200 with `status: 'closed'` | "Field temporarily unavailable" |
| Renovation | 200 with `status: 'renovation'` | "Field temporarily unavailable" |
| Missing | 404 | "Field not found" fallback |

### 13.2 Game States

| Game State | API Response | Deep Link UI | Join Available? |
|:---|:---|:---|:---|
| Open | 200, `status: 'open'` | Field panel + game details | Yes |
| Full | 200, `status: 'full'` | Field panel + "game is full" | No |
| Finished | 200, `status: 'finished'` | Field panel + "game has ended" | No |
| Cancelled | 200, `status: 'cancelled'` | Field panel + "game was cancelled" | No |
| Scheduled (future, open) | 200, `scheduled_at` in future | Field panel + scheduled time | Yes |
| Scheduled (future, full) | 200, `scheduled_at` in future, `status: 'full'` | Field panel + "game is full" | No |
| Missing | 404 | "Game not found" fallback | No |

---

## 14. Platform Architecture

### 14.1 Web Browser

| Aspect | Architecture |
|:---|:---|
| URL arrival | Browser navigates to `https://yesh-mishak.com/game/{id}` |
| SPA routing | Server serves `index.html` for all paths (SPA fallback). Client-side resolver parses pathname. |
| Auth | Same-origin session/token in storage. Auth gate in resolver. |
| Meta tags | Server-side or edge-function injection for Open Graph tags (title, description, image) on `/field/{id}` and `/game/{id}` paths. Required for WhatsApp/social previews. |

### 14.2 Android (Capacitor WebView)

| Aspect | Architecture |
|:---|:---|
| URL arrival | Android App Link: intent filter matches `https://yesh-mishak.com/*` → app opens |
| Capacitor handler | `CapacitorApp.addListener('appUrlOpen', (event) => { ... })` receives URL |
| Resolver | Same client-side deep link resolver as web — parses `event.url` pathname |
| Verification | `.well-known/assetlinks.json` hosted on domain for verified App Links |
| Fallback | If app not installed, URL opens in Chrome → web SPA handles it |

### 14.3 Future iOS

| Aspect | Architecture |
|:---|:---|
| URL arrival | Universal Link: Associated Domains entitlement + `apple-app-site-association` file |
| Capacitor handler | Same `appUrlOpen` listener |
| Resolver | Same client-side resolver |
| Verification | AASA file hosted at `https://yesh-mishak.com/.well-known/apple-app-site-association` |
| Status | **Blocked** — no iOS build/signing path available |

### 14.4 WhatsApp / Browser Handoff

| Aspect | Architecture |
|:---|:---|
| Share format | `https://yesh-mishak.com/game/{game_id}` — plain HTTPS URL |
| WhatsApp preview | Open Graph meta tags provide title, description, image |
| Tap behavior | If app installed: App Link/Universal Link opens app. If not: opens in browser. |
| No custom scheme | `yeshmishak://` is NOT used — WhatsApp does not reliably handle custom schemes |

### 14.5 Push Notification Tap

| Aspect | Architecture |
|:---|:---|
| Payload | Notification data includes `game_id`, `field_id`, `type` |
| Service worker (web) | Constructs canonical URL `/game/{game_id}` → `clients.openWindow()` or `postMessage` to focused client |
| Native (Android) | Capacitor `pushNotificationActionPerformed` listener receives data → resolver processes `game_id`/`field_id` |
| Resolver | Same deep link resolver — notification data mapped to canonical route internally |

---

## 15. Backend Architecture Requirements

| Requirement | Status | Details |
|:---|:---|:---|
| `GET /fields/{field_id}` | **Exists** | Returns field with active/upcoming games. Returns 404 for non-visible fields. |
| `GET /games/{game_id}` | **Must be added** | Must return game data including `field_id`, `status`, `sport_type`, `scheduled_at`, `players_present`, `max_players`. Returns 404 for missing games. |
| Consistent 404 | **Required** | Non-existent resources return 404. Pending/rejected fields return 404 (no information leakage). |
| Stable UUID handling | **Exists** | UUID validation regex in `errors.py`. Invalid UUIDs return 400. |
| Server as source of truth | **Required** | Client must not cache game/field state from deep link context. Always fetch fresh data on deep link arrival. |
| No trust in client state | **Required** | Link parameters are untrusted input. Server validates resource existence, user authorization, and game joinability independently. |

---

## 16. Frontend Architecture Requirements

| Requirement | Details |
|:---|:---|
| Central deep link resolver | Single function/module that handles all deep link resolution. Called on app mount, on `popstate`, and on `appUrlOpen`. |
| Loading state | Show loading indicator during resource fetch. Never show blank screen. |
| Auth redirect + continuation | Store `{ type, id, action }` intent before redirecting to login. Resume after login. |
| Resource fetch | Call API endpoint for the target resource. Handle 200, 404, network error. |
| UI target opening | Set `selectedField` state for field/game links. Fly map to field coordinates. Open `FieldDetailsPanel`. |
| Error/fallback UI | Localized error messages for not-found, unavailable, and network failure. "Go to Map" button. |
| Back navigation | Back from deep-linked panel returns to map view, not to external source. `history.replaceState` after resolution. |
| Compatibility | Must work with existing `App.jsx` pathname routing. No React Router migration required. The resolver integrates alongside the current `pathname` state check. |

---

## 17. Native Architecture Requirements

### 17.1 Android App Links

| Requirement | Details |
|:---|:---|
| Intent filter | Add `<intent-filter>` with `android:scheme="https"`, `android:host="yesh-mishak.com"`, `android:autoVerify="true"` to `AndroidManifest.xml` |
| Asset links | Host `.well-known/assetlinks.json` on the web domain with the app's signing certificate fingerprint |
| `appUrlOpen` listener | Add `CapacitorApp.addListener('appUrlOpen', handler)` in `App.jsx` |

### 17.2 iOS Universal Links

| Requirement | Details |
|:---|:---|
| Associated Domains | Add `applinks:yesh-mishak.com` to the app entitlements |
| AASA file | Host `apple-app-site-association` at `https://yesh-mishak.com/.well-known/apple-app-site-association` |
| `appUrlOpen` listener | Same Capacitor listener as Android |
| Status | **Blocked** — no iOS build path |

### 17.3 Push Notification Action Handling

| Requirement | Details |
|:---|:---|
| Web (service worker) | Update `notificationclick` handler to construct canonical `/game/{id}` URL and `postMessage` to focused client |
| Native (Capacitor) | Add `PushNotifications.addListener('pushNotificationActionPerformed')` handler that extracts `game_id`/`field_id` and feeds to resolver |

---

## 18. Security and Abuse Considerations

| Concern | Mitigation |
|:---|:---|
| Private data exposure via link | Links carry only UUIDs. No user names, scores, or personal data in URLs. Resource access requires authentication. |
| Authorization bypass | Server validates all access. `GET /fields/{id}` and future `GET /games/{id}` enforce visibility rules. Pending/rejected fields return 404. |
| UUID validation | Client-side regex validation before API call. Backend validates UUID format and returns 400 for invalid IDs. |
| Notification data leakage | Push notification payloads carry `game_id` and `field_id` only — no sensitive user data. Notification titles use generic templates. |
| Open redirects | Deep link resolver only navigates to known internal routes (`/field/{id}`, `/game/{id}`, `/`). No arbitrary URL following. Marketing links (`/m/{slug}`) resolve server-side to internal targets only — never to external URLs. |
| Marketing link abuse | `/m/{slug}` slugs are resolved server-side with a whitelist. Unrecognized slugs return a "not found" page. Slugs cannot redirect to external domains. |
| Rate limiting | Existing API rate limits apply to deep link resource fetches. No additional rate limiting needed at the link resolution layer. |

---

## 19. Non-Goals

This issue is documentation-only. The following are explicitly out of scope:

- No deep link implementation in frontend code.
- No Android intent filter or `assetlinks.json` configuration.
- No iOS universal link or AASA file configuration.
- No `appUrlOpen` listener implementation.
- No WhatsApp share UI or share buttons.
- No backend endpoint changes (including the recommended `GET /games/{game_id}`).
- No push notification click handler changes.
- No React Router migration (the architecture is compatible with the current routing model).
- No new automated tests.
- No marketing link slug resolution system.
- No Open Graph meta tag service.

---

## 20. Recommended Implementation Sequence

| Order | Issue Scope | Dependencies | Estimated Complexity |
|:---:|:---|:---|:---|
| 1 | Backend: Add `GET /games/{game_id}` public endpoint | None | Low |
| 2 | Frontend: Central deep link resolver module | Issue 1 (game endpoint) | Medium |
| 3 | Frontend: Route handling for `/field/{field_id}` | Issue 2 (resolver) | Low |
| 4 | Frontend: Route handling for `/game/{game_id}` | Issues 1 + 2 | Low |
| 5 | Frontend: Join intent handling (`/game/{id}/join`) | Issues 2 + 4 | Low |
| 6 | Frontend: Auth intent storage + post-login resume | Issue 2 | Medium |
| 7 | Frontend: Push notification target routing (fix service worker + add `appUrlOpen`) | Issue 2 | Medium |
| 8 | Frontend: Legacy `/?game_id` query param compatibility | Issue 2 | Low |
| 9 | Android: Intent filters + `assetlinks.json` for App Links | Issues 2–5 + deployed domain | Medium |
| 10 | Frontend: WhatsApp / share UI (share button, link construction) | Issues 3 + 4 | Medium |
| 11 | Backend + Frontend: Open Graph meta tags for link previews | Deployed domain | Medium |
| 12 | iOS: Universal Links + AASA file | iOS build path + deployed domain | Medium |
| 13 | Marketing: `/m/{slug}` resolution system | Issues 2 + backend slug service | Low–Medium |

---

## 21. Architecture Verdict

**READY FOR APPROVAL**

The deep link architecture is fully defined. All link types (game, field, notification, marketing) are documented with their URL structure, resolution flow, auth behavior, resource-state handling, and platform-specific requirements.

### Prerequisites Before Implementation

| Prerequisite | Status | Blocking? |
|:---|:---|:---|
| ISSUE-266 entry points audit | Merged (PR #829) | No — complete |
| This architecture document approved | Pending | Yes — must be approved before implementation begins |
| Web domain deployed (`yesh-mishak.com` or equivalent) | Unknown | Yes — required for App Links, Universal Links, and Open Graph |
| iOS build path | Blocked | No — Android-first implementation; iOS tracked separately |

### Implementation Can Begin When

1. This document is approved.
2. A web domain is available or a decision is made to proceed with local/staging URLs first.
3. The `GET /games/{game_id}` backend endpoint is scoped and assigned.

---

## 22. Definition of Done Checklist

- [x] Purpose explained
- [x] Current state summarized from ISSUE-266
- [x] Deep link principles defined
- [x] Canonical URL structure defined (`/field/{id}`, `/game/{id}`, `/game/{id}/join`, `/m/{slug}`)
- [x] Game links fully specified (states, auth, backend/frontend requirements)
- [x] Field links fully specified (states, auth, backend/frontend requirements)
- [x] Notification links fully specified (payload, mapping, tap behavior, existing gaps)
- [x] Marketing links reserved and constrained
- [x] Routing strategy defined (central resolver, 6-step flow)
- [x] Unsupported links behavior defined
- [x] Expired/invalid resource behavior defined
- [x] Auth-state matrix included
- [x] Resource-state matrix included
- [x] Platform architecture covered (web, Android, iOS, WhatsApp, push)
- [x] Backend architecture requirements documented
- [x] Frontend architecture requirements documented
- [x] Native architecture requirements documented
- [x] Security and abuse considerations documented
- [x] Non-goals explicitly stated
- [x] Implementation sequence recommended (13 ordered issues)
- [x] Architecture verdict stated (READY FOR APPROVAL)
- [x] Scope confirmed documentation-only
