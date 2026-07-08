# Navigation and Sharing Entry Points Audit

**Issue:** ISSUE-266
**Date:** 2026-07-08
**Branch:** `issue-266-navigation-sharing-entry-points`
**Commit (main at audit):** `ae8cd48`
**Status:** Documentation-only — no code changes

---

## 1. Purpose

Before implementing Deep Links and external sharing, all current navigation entry points, content identifiers, and platform capabilities must be documented. This audit serves as the reference for future Deep Links and Navigation work.

---

## 2. Current Internal Navigation Entry Points

### 2.1 Routing Model

The app uses **manual client-side routing** via `window.history.pushState` and React state — not React Router. Navigation is managed in `App.jsx` with a `pathname` state variable that determines which page renders.

**Source:** `frontend/src/App.jsx:320-341`

```
navigateTo(path) → window.history.pushState(null, '', path) + setPathname(path)
```

### 2.2 Route Table

| Path | Component | Auth Required | Guard | Notes |
|:---|:---|:---|:---|:---|
| `/` | `MapPage` | Yes | Logged in + onboarding complete | Primary app surface; all field/game interaction happens here |
| `/my-games` | `MyGamesPage` | Yes | Logged in + onboarding complete | User's game history; back button returns to `/` |
| `/admin` | `AdminPage` | Yes | Admin role via `AdminRoute` | Admin dashboard; forbidden redirects to `/` |
| `/login` | `LoginPage` | No | Shown when `currentUser` is null | Google OAuth + email/password login |
| `/register` | — | No | Part of `LoginPage` flow | Registration is inline within the login component |

**No dynamic route parameters exist** — no `:id`, `:fieldId`, `:gameId` segments.

### 2.3 Navigation Triggers

| Source | Target | Method | File:Line |
|:---|:---|:---|:---|
| Auth toolbar "My Games" button | `/my-games` | `navigateTo('/my-games')` | `App.jsx:334` |
| MyGamesPage back button | `/` | `navigateTo('/')` via `onBack` prop | `App.jsx:326` |
| Admin forbidden | `/` | `window.history.replaceState(null, '', '/')` | `App.jsx:267` |
| Login success | `/` (MapPage) | `setCurrentUser(user)` — page re-renders | `App.jsx:258` |
| Logout | Login page | `setCurrentUser(null)` — page re-renders | `App.jsx:248` |
| Onboarding complete | `/` (MapPage) | `setIsOnboardingDone(true)` — page re-renders | `App.jsx:263` |
| `popstate` event | Current URL | `setPathname(window.location.pathname)` | `App.jsx:185-193` |

---

## 3. Current Field-Related Entry Points

### 3.1 Field Discovery

Fields are discovered through viewport-based map browsing only. There is no search, URL-based field access, or shared field link capability.

| Entry Point | How User Arrives | What Opens |
|:---|:---|:---|
| Map marker tap | User browses map, taps a field marker | `FieldDetailsPanel` (slide-in panel, no URL change) |
| Notification inbox tap | User taps a game notification that references a `field_id` | `FieldDetailsPanel` (after field lookup by ID) |
| Add Field button | User taps "+" button on map | `AddFieldModal` (modal, no URL change) |

### 3.2 Field Details Panel

**Source:** `frontend/src/components/FieldDetailsPanel.jsx`

Displays field name, coordinates, sport type, surface, amenities, opening hours, notes. Contains:

| Action | What It Does | Deep Link Candidate? |
|:---|:---|:---|
| Navigate to Field | Opens Waze or Google Maps with destination coords | No — external app delegation |
| Open Game | Opens `OpenGameModal` to create a game on this field | Yes — future `field/{id}/create-game` |
| Report Field | Opens `FieldReportModal` to submit a report | No |
| Close panel | Returns to map | No |

### 3.3 Field Identifiers

| Property | Format | Source | Example |
|:---|:---|:---|:---|
| `field.id` | UUID v4 | Supabase auto-generated | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| `field.name` | String (2–200 chars) | User-submitted | `מגרש הפועל באר שבע` |
| `field.lat` / `field.lng` | Float | User-submitted (GPS or manual pin) | `31.2530, 34.7915` |
| `field.city` | String (optional) | User-submitted | `באר שבע` |

### 3.4 Field States

| State | Visibility | Deep Link Behavior |
|:---|:---|:---|
| `approved` + `verified` + `open` | Visible on map | Link should resolve normally |
| `pending` | Not visible to regular users | Link should show "field pending approval" or 404 |
| `rejected` | Not visible | Link should show "field not found" |
| `closed` | Not visible (filtered out) | Link should show "field temporarily closed" |
| `renovation` | Not visible (filtered out) | Link should show "field under renovation" |
| Deleted/missing | Does not exist | Link should show "field not found" |

**Backend visibility filter** (`fields.py`): `verified=True AND approval_status='approved' AND status='open'`

---

## 4. Current Game-Related Entry Points

### 4.1 Game Discovery

Games are discovered through fields — there is no standalone game list on the map page, no game search, and no direct game URL.

| Entry Point | How User Arrives | What Opens |
|:---|:---|:---|
| Field marker with active game | User taps field marker showing game indicator | `FieldDetailsPanel` → `GamePanel` inline |
| Notification inbox tap | User taps game notification with `game_id` | Field lookup → `FieldDetailsPanel` → `GamePanel` |
| My Games page | User navigates to `/my-games` from toolbar | `MyGamesPage` — read-only list, no actions |
| Push notification tap (background) | User taps system notification | Service worker navigates to `/?game_id={id}` (see §4.3) |

### 4.2 Game Panel Actions

**Source:** `frontend/src/components/GamePanel.jsx`

| Action | What It Does | Auth Required | Deep Link Candidate? |
|:---|:---|:---|:---|
| Join game | `POST /games/{game_id}/join` | Yes | Yes — future `game/{id}/join` |
| Leave game | `POST /games/{game_id}/leave` | Yes | No |
| Close game | `POST /games/{game_id}/close` | Yes (creator only) | No |
| Extend game | `POST /games/{game_id}/extend` | Yes (creator only) | No |

### 4.3 Push Notification → Game Navigation

The service worker constructs a `/?game_id={game_id}` URL on notification tap:

**Source:** `frontend/public/firebase-messaging-sw.js:32-52`

```javascript
const targetUrl = data.game_id ? `/?game_id=${data.game_id}` : '/'
```

**Gap:** This `?game_id` query parameter is **not consumed by MapPage on page load**. The service worker constructs the URL, but the frontend has no code to parse `window.location.search` for `game_id` on mount. The notification click handler only works when the service worker focuses an existing client, which then navigates via `handleNotificationTarget` using the notification object — not the URL.

If the app is closed and a new window opens at `/?game_id=X`, the game_id parameter is ignored.

### 4.4 Game Identifiers

| Property | Format | Source | Example |
|:---|:---|:---|:---|
| `game.id` | UUID v4 | Supabase auto-generated | `f1e2d3c4-b5a6-7890-1234-567890abcdef` |
| `game.field_id` | UUID v4 | Reference to field | Same format |
| `game.scheduled_at` | ISO 8601 datetime | User-submitted (optional) | `2026-07-10T18:00:00Z` |
| `game.sport_type` | `football` or `basketball` | User-selected | `football` |

### 4.5 Game States

| State | Joinable | Deep Link Behavior |
|:---|:---|:---|
| `open` | Yes | Link should open field panel with game visible, join button active |
| `full` | No | Link should open field panel with game visible, "game full" shown |
| `finished` | No | Link should show "game has ended" |
| `cancelled` | No | Link should show "game was cancelled" |
| Expired (past `expires_at`) | No | Link should show "game has ended" |
| Not yet started (`scheduled_at` in future) | Yes (if open) | Link should show game with countdown/scheduled time |
| Missing/deleted | N/A | Link should show "game not found" |

**Game lifecycle:** Games expire 2 hours after `started_at`. Scheduled games have `scheduled_at` in the future.

---

## 5. Current Notification-Related Entry Points

### 5.1 Notification Infrastructure

| Layer | Technology | Status |
|:---|:---|:---|
| Push delivery | Firebase Cloud Messaging (FCM) | Implemented |
| Foreground handler | `firebase/messaging` `onMessage()` | Implemented (`firebaseMessaging.js`) |
| Background handler | Service worker `onBackgroundMessage()` | Implemented (`firebase-messaging-sw.js`) |
| Click handler | Service worker `notificationclick` | Implemented — navigates to `/` or `/?game_id=X` |
| Token management | Backend `/notifications/push-token` | Implemented |
| Notification inbox | `NotificationInboxModal` | Implemented |
| Preferences | `NotificationsModal` (distance, city, field) | Implemented |

### 5.2 Notification Types

| Type | Trigger | Contains `game_id` | Contains `field_id` | Navigation Target |
|:---|:---|:---|:---|:---|
| `game_created` | New game matches user preferences | Yes | Yes | Field with game |
| `player_joined_game` | Someone joins user's game | Yes | Yes | Field with game |
| `game_closed` | Game user was in was closed | Yes | Yes | Field (game ended) |
| `game_extended` | Game user was in was extended | Yes | Yes | Field with game |
| `scheduled_game_cancelled` | Scheduled game cancelled | Yes | Yes | Field (game cancelled) |
| `scheduled_game_reminder` | 1 hour before scheduled game | Yes | Yes | Field with game |
| `test_push` | Manual test from preferences | No | No | Home `/` |

### 5.3 Notification → Content Navigation Flow

```
Push received (background) → Service worker shows system notification
  → User taps notification
    → notificationclick handler
      → If existing app window: focus it (does NOT navigate to game)
      → If no app window: openWindow('/?game_id=X')
        → MapPage loads (game_id query param NOT consumed)
```

```
Push received (foreground) → Notification API shows browser notification
  → User taps notification
    → No click handler for foreground notifications — browser default behavior
```

```
Notification inbox (in-app) → User taps notification row
  → handleNotificationTarget(notification)
    → Looks up field by notification.field_id or notification.game_id
    → Opens FieldDetailsPanel with matched field
    → Closes inbox
```

**Gap summary:** Only the in-app notification inbox correctly navigates to the target field/game. Background notification taps have incomplete navigation (existing window doesn't navigate, new window ignores query params).

---

## 6. Current Share/Link Capabilities

### 6.1 Existing Share Features

**None.** The application has no sharing functionality:

- No "Share Field" button
- No "Share Game" button
- No "Invite Players" button
- No "Copy Link" button
- No `navigator.share()` (Web Share API) usage
- No `navigator.clipboard.writeText()` usage
- No WhatsApp links (`wa.me` or `whatsapp://`)
- No social media sharing
- No QR code generation
- No link construction for external sharing

### 6.2 External Navigation (Not Sharing)

The only external links the app creates are destination-only navigation deep links:

| Provider | URL Format | Source |
|:---|:---|:---|
| Waze | `https://waze.com/ul?ll={lat},{lng}&navigate=yes` | `FieldDetailsPanel.jsx:117` |
| Google Maps | `https://www.google.com/maps/dir/?api=1&destination={lat},{lng}` | `FieldDetailsPanel.jsx:118` |

These carry **field destination coordinates only** — no user location, no game context, no app identity.

---

## 7. WhatsApp Sharing Assumptions and Future Requirements

### 7.1 Current State

No WhatsApp integration exists. No code references WhatsApp anywhere in the codebase.

### 7.2 Future Requirements

For WhatsApp game sharing to work, the following would be needed:

| Requirement | Details |
|:---|:---|
| Shareable URL | A web-accessible URL that resolves to a specific field or game (e.g., `https://yeshmishak.app/game/{game_id}`) |
| URL routing | Frontend must handle `/game/{game_id}` and `/field/{field_id}` routes |
| Deep link handling | Native app must intercept the URL and open the correct content |
| WhatsApp link format | `https://wa.me/?text={encoded_message_with_url}` or `whatsapp://send?text={encoded}` |
| Open Graph metadata | Server-side rendered `<meta>` tags for link preview (title, description, image) |
| Auth gate | Unauthenticated users landing on a shared link need login → redirect back to content |
| Fallback | If app not installed, the web URL must work in a mobile browser |

### 7.3 WhatsApp Share Message Template (Suggested)

```
🏟️ {field_name}
⚽ {sport_type} game — {players_present}/{max_players} players
🕐 {scheduled_time or "Now"}

Join: https://yeshmishak.app/game/{game_id}
```

---

## 8. Future Push Notification Entry Points

### 8.1 Current Gaps

| Gap | Impact | Fix Required |
|:---|:---|:---|
| Background notification tap does not navigate to game when existing window focused | User taps notification, app focuses but stays on current view | Service worker must `postMessage` to client with target game/field |
| `?game_id` query parameter not consumed on page load | New window opened from notification ignores the game_id | MapPage must parse `URLSearchParams` on mount and navigate to target |
| Foreground notification click has no handler | Browser notification from foreground push is not actionable | Add click handler or use `onMessage` to show in-app toast with action |

### 8.2 Future Push Notification Deep Link Flow

```
Push notification tap
  → App intercepts with Capacitor App.addListener('appUrlOpen')
    → Parse URL path: /game/{game_id} or /field/{field_id}
      → Navigate to target content
      → If not authenticated: store target, show login, redirect after auth
      → If resource not found: show appropriate error
```

---

## 9. External URL / Deep Link Candidates

### 9.1 Current Deep Link Configuration

**None exists on any platform:**

| Platform | Configuration | Status |
|:---|:---|:---|
| Android | No intent filters for URL handling in `AndroidManifest.xml` | Not configured |
| Android | No custom URL scheme (`yeshmishak://`) | Not configured |
| iOS | No `CFBundleURLTypes` or `CFBundleURLSchemes` in `Info.plist` | Not configured |
| iOS | No Associated Domains / Universal Links | Not configured |
| Web | No server-side routing for `/field/{id}` or `/game/{id}` | Not configured |
| Capacitor | No `appUrlOpen` listener in `App.jsx` | Not configured |

### 9.2 Recommended Deep Link Route Contract

| Route | Target | Required ID | Example |
|:---|:---|:---|:---|
| `/field/{field_id}` | FieldDetailsPanel for a specific field | UUID | `/field/a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| `/game/{game_id}` | FieldDetailsPanel with game focused | UUID | `/game/f1e2d3c4-b5a6-7890-1234-567890abcdef` |
| `/game/{game_id}/join` | Join game flow (auto-join if authenticated) | UUID | `/game/f1e2d3c4.../join` |
| `/map` | Map page (default center) | None | `/map` |
| `/map?lat={lat}&lng={lng}&zoom={z}` | Map at specific location | Coordinates | `/map?lat=31.25&lng=34.79&zoom=16` |

### 9.3 URL Scheme Options

| Scheme | Type | Pros | Cons |
|:---|:---|:---|:---|
| `https://yeshmishak.app/...` | Universal/App Link | Works in browsers, WhatsApp previews, no install needed | Requires domain, server-side routing, `.well-known/assetlinks.json` (Android) / `apple-app-site-association` (iOS) |
| `yeshmishak://...` | Custom URL scheme | Simple to implement, works without domain | No fallback for non-installed users, no browser support, no WhatsApp preview |
| `https://yeshmishak.app/...` + custom scheme fallback | Hybrid | Best coverage | More complex implementation |

**Recommendation:** Use universal/app links (`https://` scheme) as the primary mechanism, with custom URL scheme as a native-only fallback. This ensures WhatsApp link previews work and non-installed users land on a web page.

---

## 10. Required Identifiers for Links

| Identifier | Format | Available From | Used In |
|:---|:---|:---|:---|
| `field_id` | UUID v4 | `GET /fields/`, `GET /fields/{id}`, notification payload | Field deep links, game context |
| `game_id` | UUID v4 | `GET /games/active`, `GET /games/upcoming`, notification payload | Game deep links, join links |
| `scheduled_at` | ISO 8601 | Game creation payload, `GET /games/*` responses | Display only — not needed in URLs |
| `user_id` | UUID v4 | Auth session | Not exposed in shared links (privacy) |
| `sport_type` | `football` / `basketball` | Game/field data | Display only — not needed in URLs |

**Minimum viable deep link:** `field_id` or `game_id` alone is sufficient to resolve all content. The backend `GET /fields/{field_id}` endpoint returns the field with its active and upcoming games. No additional parameters are required in the URL.

---

## 11. Auth-State Behavior

| Auth State | Current Behavior | Deep Link Expected Behavior |
|:---|:---|:---|
| Logged in, session valid | App renders MapPage | Navigate directly to target field/game |
| Logged out | App renders LoginPage | Store target URL → show login → redirect after success |
| Session expired | Detected on `appStateChange` or `visibilitychange` → cleared → LoginPage | Same as logged out — store target, login, redirect |
| Token invalid | `getMyGames()` validation fails → session cleared → LoginPage | Same as logged out |
| Admin path | AdminRoute checks role | Deep links should never route to admin |

**Session validation flow** (`App.jsx:59-112`):
1. `initSessionStorage()` loads secure storage
2. On native: `validateStoredSession()` calls `getMyGames()` to verify token
3. On web: reads `getStoredUser()` directly
4. On app resume: re-validates via `appStateChange` or `visibilitychange`
5. Invalid → `clearSession()` → `setCurrentUser(null)` → LoginPage

**Deep link auth gate pattern:**
```
URL arrives → check currentUser
  → If authenticated: resolve content, navigate
  → If not authenticated: store intent (field_id/game_id)
    → Show LoginPage
    → On login success: retrieve stored intent, navigate to content
```

---

## 12. Resource-State Behavior

### 12.1 Field States on Deep Link Arrival

| Field State | What User Should See | API Response |
|:---|:---|:---|
| Approved + open | FieldDetailsPanel with full details and games | `GET /fields/{id}` returns field data |
| Pending approval | "This field is pending approval" message | `GET /fields/{id}` may return 404 (not `verified`) |
| Rejected | "Field not found" | `GET /fields/{id}` returns 404 |
| Closed / renovation | "Field temporarily unavailable" | `GET /fields/{id}` returns field but `status != 'open'` |
| Does not exist | "Field not found" | `GET /fields/{id}` returns 404 |

### 12.2 Game States on Deep Link Arrival

| Game State | What User Should See | Join Available? |
|:---|:---|:---|
| Open (active, has capacity) | GamePanel with join button | Yes |
| Full (active, max players reached) | GamePanel showing "game full" | No |
| Finished (expired or closed) | "This game has ended" | No |
| Cancelled | "This game was cancelled" | No |
| Scheduled (future, open) | GamePanel with scheduled time + join button | Yes |
| Scheduled (future, full) | GamePanel with scheduled time, "game full" | No |
| Does not exist | "Game not found" | No |

### 12.3 Combined Resolution

For a `game_id` deep link, the resolution chain is:
1. `GET /games/{game_id}` (not currently exposed as a standalone endpoint — games are fetched via field)
2. Alternative: use notification target flow — `getFields()` → find field containing game
3. Or add: `GET /games/{game_id}` endpoint that returns game with its `field_id` → then `GET /fields/{field_id}`

**Backend gap:** No direct `GET /games/{game_id}` public endpoint exists. Games are accessed through fields (`GET /fields/{field_id}` includes active/upcoming games) or through user-specific endpoints (`GET /games/me`). A dedicated endpoint may be needed for deep link resolution.

---

## 13. Platform Considerations

### 13.1 Web Browser

| Aspect | Current State | Deep Link Impact |
|:---|:---|:---|
| Routing | `window.history.pushState` — all paths serve `index.html` | Server must be configured to serve `index.html` for all routes (SPA fallback) |
| URL handling | Only `/`, `/my-games`, `/admin` recognized | New routes (`/field/{id}`, `/game/{id}`) must be added to App.jsx |
| Query params | Not consumed | Must add `URLSearchParams` parsing for `?game_id`, `?field_id` |
| Meta tags | Static `index.html` | Open Graph tags for link previews require server-side rendering or a meta tag service |

### 13.2 Android (Capacitor WebView)

| Aspect | Current State | Deep Link Impact |
|:---|:---|:---|
| App launch | `singleTask` launch mode, MAIN/LAUNCHER intent only | Must add intent filters for URL handling |
| URL interception | No `appUrlOpen` listener | Must add `CapacitorApp.addListener('appUrlOpen')` |
| Intent filters | None | Must add `<data android:scheme="https" android:host="yeshmishak.app" />` |
| Asset links | No `.well-known/assetlinks.json` | Required for verified app links |
| Custom scheme | None | Optional: `<data android:scheme="yeshmishak" />` |

### 13.3 iOS (Future)

| Aspect | Current State | Deep Link Impact |
|:---|:---|:---|
| URL schemes | No `CFBundleURLTypes` | Must add custom scheme and/or universal links |
| Associated domains | Not configured | Must add `com.apple.developer.associated-domains` entitlement |
| AASA file | Not present | Must host `apple-app-site-association` on web domain |
| Build status | No iOS build/signing path | Blocked until iOS development begins |

### 13.4 Capacitor Plugin Requirements

| Plugin | Current Status | Needed For |
|:---|:---|:---|
| `@capacitor/app` | Installed, used for `appStateChange` only | Deep link handling via `appUrlOpen` event |
| `@capacitor/share` | Not installed | Native share sheet (optional, Web Share API may suffice) |
| `@capacitor/clipboard` | Not installed | Copy link functionality (optional) |
| `@capacitor/browser` | Not installed | Opening external links in in-app browser (optional) |

---

## 14. Risks and Blockers

| Severity | Risk/Blocker | Impact | Mitigation |
|:---|:---|:---|:---|
| High | No web domain for deep links | Cannot create universal/app links without a hosted domain | Must deploy web app to `yeshmishak.app` or equivalent before implementing verified deep links |
| High | No `GET /games/{game_id}` public endpoint | Cannot resolve game deep links directly — must search through fields | Add a lightweight `GET /games/{game_id}` endpoint returning game + field_id |
| Medium | No server-side rendering for meta tags | WhatsApp/social previews will show generic page title, not field/game-specific content | Add server-side meta tag injection or a dedicated meta endpoint |
| Medium | Service worker notification click does not navigate existing windows | Users who tap notifications while app is open don't reach the target content | Fix service worker to `postMessage` with target to client window |
| Medium | `?game_id` query parameter not consumed on load | New windows from notifications don't navigate to the referenced game | Add `URLSearchParams` parsing in MapPage mount |
| Medium | iOS build path unavailable | Cannot test or deploy iOS deep links | Track as blocker; implement Android-first |
| Low | UUIDs are long for URLs | Share links will be verbose (36-char IDs) | Acceptable; could add short slugs later but not required for MVP |
| Low | No rate limiting on deep link resolution | Potential for abuse of `GET /fields/{id}` or future `GET /games/{id}` | Existing endpoints already have rate limits; deep link resolution uses the same endpoints |

---

## 15. Recommended Future Route / Deep Link Contract

### 15.1 URL Structure

```
https://yeshmishak.app/field/{field_id}           → Open field details
https://yeshmishak.app/game/{game_id}             → Open field with game focused
https://yeshmishak.app/game/{game_id}/join         → Open game and prompt join
https://yeshmishak.app/map                         → Open map at default center
https://yeshmishak.app/map?lat={lat}&lng={lng}     → Open map at coordinates
```

### 15.2 Resolution Flow

```
URL received
  ├─ Parse route: extract resource type + ID
  ├─ Auth check: if not logged in → store intent → login → resume
  ├─ API call: GET /fields/{id} or GET /games/{id}
  ├─ State check: is resource accessible?
  │   ├─ Yes → navigate to content
  │   └─ No → show appropriate error message
  └─ Platform handling:
      ├─ Web: client-side route matching in App.jsx
      ├─ Android: intent filter → appUrlOpen → route matching
      └─ iOS: universal link → appUrlOpen → route matching
```

### 15.3 Implementation Prerequisites

| Prerequisite | Required Before |
|:---|:---|
| Web domain deployed | Universal/app links |
| `GET /games/{game_id}` endpoint | Game deep link resolution |
| Client-side route parsing for `/field/{id}` and `/game/{id}` | Any deep link |
| Auth intent storage (store target URL across login) | Deep links for logged-out users |
| Android intent filters | Android deep links |
| iOS associated domains + AASA file | iOS deep links |
| Open Graph meta tag service | WhatsApp/social media link previews |

---

## 16. Final Readiness Verdict for Starting Deep Links

### Assessment

| Area | Ready? | Notes |
|:---|:---|:---|
| Field identifiers (UUID) | Yes | Stable, available from API |
| Game identifiers (UUID) | Yes | Stable, available from API |
| Field API (`GET /fields/{id}`) | Yes | Public endpoint exists |
| Game API (`GET /games/{id}`) | **No** | Must be added — games are only accessible via fields or user-specific endpoints |
| Frontend routing | **Partially** | Must add route parsing for `/field/{id}` and `/game/{id}` |
| Android native config | **No** | No intent filters or URL handling configured |
| iOS native config | **No** | Blocked — no build path |
| Notification navigation | **Partially** | In-app inbox works; push notification click-through is incomplete |
| Sharing UI | **No** | No share buttons, no link construction, no clipboard/share API |
| Web domain | **Unknown** | Depends on deployment infrastructure |
| Auth intent flow | **No** | No mechanism to store deep link target across login |

### Verdict

**READY TO BEGIN PLANNING AND IMPLEMENTATION** with the following conditions:

1. **Backend:** A public `GET /games/{game_id}` endpoint must be added before game deep links can work.
2. **Frontend:** Route parsing (`/field/{id}`, `/game/{id}`) must be added to `App.jsx`.
3. **Android:** Intent filters must be added to `AndroidManifest.xml` for URL handling.
4. **Auth:** A deep link intent storage mechanism must be implemented for unauthenticated users.
5. **iOS:** Remains blocked until build path exists.

The current architecture supports deep links — all content is identifiable by UUID, the API can resolve individual fields, and the frontend already has a pattern for navigating to a specific field from a notification. The work is additive, not a refactor.

---

## 17. Out of Scope

- No frontend code changes
- No backend code changes
- No Android native code changes
- No iOS code changes
- No deep link implementation
- No route additions
- No sharing UI implementation
- No permission changes
- No test changes

---

## 18. Definition of Done Checklist

- [x] Internal navigation entry points documented (routes, triggers, guards)
- [x] Field-related entry points documented (discovery, details, identifiers, states)
- [x] Game-related entry points documented (discovery, actions, identifiers, states)
- [x] Notification-related entry points documented (push, inbox, click handling, gaps)
- [x] Share/link capabilities documented (none exist)
- [x] WhatsApp sharing assumptions and future requirements documented
- [x] Future push notification entry points documented
- [x] External URL / deep link candidates documented
- [x] Required identifiers documented (field_id, game_id, formats)
- [x] Auth-state behavior documented (logged in, logged out, expired)
- [x] Resource-state behavior documented (field states, game states, combined resolution)
- [x] Platform considerations documented (web, Android, iOS)
- [x] Risks and blockers documented
- [x] Recommended future route / deep link contract documented
- [x] Final readiness verdict stated
- [x] Scope confirmed documentation-only
