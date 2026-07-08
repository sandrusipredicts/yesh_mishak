# Android App Links Strategy

**Issue:** ISSUE-268
**Date:** 2026-07-08
**Dependency:** `docs/deep-link-architecture.md` (ISSUE-267)
**Status:** Strategy definition only — no implementation

---

## 1. Executive Decision

Android App Links will be the sole mechanism for external URL → app navigation on Android. No custom URL schemes (`yeshmishak://`) will be used. App Links use verified HTTPS URLs, which means the same link works in-app, in the browser (if the app is not installed), and in WhatsApp or other messaging apps without platform-specific workarounds.

Key decisions:

- **HTTPS only.** All App Links use `https://` scheme. No `http://`, no custom schemes.
- **Product-owned domain.** A dedicated, product-controlled HTTPS domain serves as the canonical App Links identity. The Railway backend URL, Supabase URL, localhost, and raw IPs are not used as the public identity domain.
- **Verified App Links.** `android:autoVerify="true"` ensures Android verifies domain ownership via `assetlinks.json`, so links open directly in the app without the disambiguation dialog.
- **Broad host scope.** The manifest intent filter captures all paths under the canonical domain. Route-level filtering is handled by the frontend deep link resolver, not by narrowing the intent filter.

---

## 2. Current Android State

From `docs/deep-link-architecture.md` Section 2 and direct inspection of the Android project:

| Aspect | Current Value |
|:---|:---|
| Package name | `com.yeshmishak.app` (from `capacitor.config.ts`) |
| Launch mode | `singleTask` (from `AndroidManifest.xml`) |
| Existing intent filters | `MAIN` / `LAUNCHER` only — no deep link intent filters |
| Custom URL schemes | None registered |
| `appUrlOpen` listener | Not implemented |
| `assetlinks.json` | Not hosted anywhere |
| Deep link handling | None — all external URLs open in browser, not in app |
| Permissions | `INTERNET`, `POST_NOTIFICATIONS`, `ACCESS_COARSE_LOCATION`, `ACCESS_FINE_LOCATION` |
| Capacitor plugins | `SocialLogin` (Google only) |
| Debug signing | Default Android debug keystore (`~/.android/debug.keystore`) |
| Release signing | Not configured — no release keystore or Play Store upload key exists |

The `singleTask` launch mode is already correct for App Links — it ensures that tapping a link when the app is already running brings the existing task to the foreground rather than creating a new activity instance.

---

## 3. App Links Objective

Enable verified Android App Links so that when a user taps a link like `https://<canonical-domain>/fields/<field_id>` in WhatsApp, Chrome, or a push notification, the yesh_mishak Android app opens directly to the corresponding content — without a browser disambiguation dialog, without a custom scheme, and with a web fallback if the app is not installed.

---

## 4. Domain Ownership Strategy

### 4.1 Requirement

Android App Links require a domain that the team controls and can host files on. Specifically:

1. The domain must serve `https://<domain>/.well-known/assetlinks.json` over HTTPS with a valid TLS certificate.
2. The `assetlinks.json` response must have `Content-Type: application/json`.
3. The domain must be reachable by Android's verification service at install time and periodically thereafter.

### 4.2 Decision

A **product-owned HTTPS domain** must be selected and controlled before App Links can be enabled. The exact domain is a prerequisite blocker — this document uses `<canonical-domain>` as a placeholder.

### 4.3 Domain Options

| Option | Example | Pros | Cons |
|:---|:---|:---|:---|
| Custom product domain | `yeshmishak.app` | Full control, professional, stable | Requires purchase and DNS/hosting setup |
| Custom subdomain | `app.yeshmishak.co.il` | Leverages existing domain if one exists | Depends on root domain ownership |
| Vercel/Netlify deployed domain | `yeshmishak.vercel.app` | Free, HTTPS by default, easy `.well-known` hosting | Tied to platform, less professional |

The team must select and register the domain before implementation begins.

---

## 5. Canonical Link Domain

### 5.1 Rules

- One canonical domain is chosen. All App Links, share URLs, and `assetlinks.json` reference this single domain.
- The canonical domain appears in `AndroidManifest.xml` intent filters, in `assetlinks.json`, and in all user-facing shared links.
- If the domain changes in the future, the old domain must continue to serve `assetlinks.json` and redirect to the new domain during a transition period.

### 5.2 Placeholder

This document uses `<canonical-domain>` wherever the production domain would appear. Replace with the actual domain once selected.

---

## 6. Disallowed Domains

The following must **never** be used as the canonical App Links domain:

| Domain Type | Example | Reason |
|:---|:---|:---|
| Railway backend URL | `yesh-mishak-production.up.railway.app` | Infrastructure URL, not product identity. Railway can change or rotate the subdomain. Not user-facing. |
| Supabase project URL | `*.supabase.co` | Third-party infrastructure. Not controlled by the team for `.well-known` hosting. |
| Localhost | `localhost`, `10.0.2.2` | Not routable. Android verification cannot reach it. |
| Raw IP addresses | `192.168.x.x`, `34.x.x.x` | No TLS certificate. Not stable. Not verifiable. |
| Temporary deployment URLs | `preview-xyz.vercel.app` | Ephemeral. Will break when preview is deleted. |
| Capacitor WebView origin | `https://localhost` | Internal Capacitor WebView origin. Not a real domain. |

These URLs may appear in internal configuration (API base URLs, CORS origins) but must not be exposed as the public App Links identity.

---

## 7. URL Path Strategy

### 7.1 Canonical Paths

From `docs/deep-link-architecture.md` Section 4, adapted to Android URL patterns:

| URL Pattern | Purpose | Parameter | Status |
|:---|:---|:---|:---|
| `https://<canonical-domain>/fields/<field_id>` | Open field details | UUID v4 | Implementation-ready (`GET /fields/{field_id}` exists) |
| `https://<canonical-domain>/games/<game_id>` | Open game details | UUID v4 | Blocked (`GET /games/{game_id}` does not exist) |
| `https://<canonical-domain>/games/<game_id>/join` | Open game with join intent | UUID v4 | Blocked (same dependency) |
| `https://<canonical-domain>/my-games` | Open user's games list | None | Implementation-ready (existing route) |
| `https://<canonical-domain>/invite/<game_id>` | Future: shareable game invitation | UUID v4 | Future — not in MVP |

### 7.2 Path Convention

The ISSUE-267 architecture defined routes as `/field/{id}` and `/game/{id}` (singular). For Android App Links URLs, this document uses `/fields/{id}` and `/games/{id}` (plural) to align with REST API conventions and the backend endpoint paths (`GET /fields/{field_id}`, `GET /games/{game_id}`). The frontend deep link resolver must accept both singular and plural forms and normalize internally.

### 7.3 Query Parameters

Query parameters (`?ref=`, `?utm_source=`) are allowed but never required for resource resolution. The deep link resolver strips tracking parameters before resolving the resource.

---

## 8. Manifest Intent-Filter Strategy

### 8.1 Approach

A single intent filter with `android:autoVerify="true"` captures all HTTPS traffic for the canonical domain. Path-level filtering is handled by the frontend deep link resolver, not by the manifest.

### 8.2 Planned Intent Filter Structure

The following intent filter will be added to `AndroidManifest.xml` inside the existing `<activity>` element, alongside the existing `MAIN`/`LAUNCHER` filter:

```xml
<intent-filter android:autoVerify="true">
    <action android:name="android.intent.action.VIEW" />
    <category android:name="android.intent.category.DEFAULT" />
    <category android:name="android.intent.category.BROWSABLE" />
    <data android:scheme="https" />
    <data android:host="<canonical-domain>" />
</intent-filter>
```

### 8.3 Design Rationale

| Decision | Rationale |
|:---|:---|
| Single `<data>` element with host only | Captures all paths. Avoids maintaining a path whitelist in the manifest that must stay in sync with the frontend resolver. |
| `android:autoVerify="true"` | Triggers automatic App Link verification via `assetlinks.json`. Without this, Android shows a disambiguation dialog. |
| `https` scheme only | No `http` — all links are HTTPS. No custom scheme — custom schemes bypass verification and are unreliable in messaging apps. |
| No `android:pathPattern` | Route filtering is the deep link resolver's responsibility. The manifest delegates all matched URLs to the app; the resolver handles unknown routes with a fallback screen. |
| Alongside existing LAUNCHER filter | The LAUNCHER filter is required for normal app launch. The new VIEW filter handles incoming URLs. Both coexist on the same activity. |

### 8.4 Compatibility with `singleTask`

The existing `android:launchMode="singleTask"` is required for App Links. When the app is already running and a link is tapped:

1. Android delivers the URL via `onNewIntent()` to the existing activity.
2. Capacitor's `appUrlOpen` listener fires with the new URL.
3. The deep link resolver processes the URL without restarting the app.

If the app is not running, Android launches it normally and delivers the URL via the initial intent.

---

## 9. assetlinks.json Strategy

### 9.1 Purpose

The Digital Asset Links file (`assetlinks.json`) proves to Android that the domain owner authorizes the app to handle its URLs. Android fetches this file at install time (and periodically after) to verify the App Link claim.

### 9.2 Hosting Location

The file must be served at:

```
https://<canonical-domain>/.well-known/assetlinks.json
```

### 9.3 File Structure

```json
[
  {
    "relation": ["delegate_permission/common.handle_all_urls"],
    "target": {
      "namespace": "android_app",
      "package_name": "com.yeshmishak.app",
      "sha256_cert_fingerprints": [
        "<DEBUG_FINGERPRINT>",
        "<RELEASE_FINGERPRINT>"
      ]
    }
  }
]
```

### 9.4 Hosting Requirements

| Requirement | Details |
|:---|:---|
| URL | `https://<canonical-domain>/.well-known/assetlinks.json` |
| Protocol | HTTPS with valid TLS certificate (no self-signed) |
| Content-Type | `application/json` |
| Status code | 200 |
| Redirects | Allowed but not recommended — Android follows redirects but some OEMs have bugs |
| Caching | Should be cacheable but updatable. Use reasonable `Cache-Control` (e.g., `max-age=3600`). |
| Availability | Must be reachable by Google's verification servers. No IP restrictions, no auth. |

### 9.5 Hosting Options

| Option | How | Pros | Cons |
|:---|:---|:---|:---|
| Static file on web frontend | Deploy `.well-known/assetlinks.json` alongside the SPA | Simple, same deployment pipeline | Requires web frontend deployment to the canonical domain |
| CDN / edge function | Serve from Vercel/Netlify/Cloudflare | Fast, cached globally | Adds platform dependency |
| Backend route | Add `GET /.well-known/assetlinks.json` to the backend | Centralized | Backend may not be on the canonical domain |

The recommended approach is to serve `assetlinks.json` as a static file from the web frontend deployment on the canonical domain, since the SPA must be hosted there anyway for web-based deep link fallback.

---

## 10. SHA-256 Certificate Fingerprint Strategy

### 10.1 What Fingerprints Are

Android App Links verification matches the `sha256_cert_fingerprints` in `assetlinks.json` against the certificate used to sign the installed APK. If the fingerprints don't match, verification fails and links open in the browser instead of the app.

### 10.2 Debug Fingerprint

The debug keystore is auto-generated by Android SDK and lives at `~/.android/debug.keystore` (or `%USERPROFILE%\.android\debug.keystore` on Windows).

Extract with:

```bash
keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android
```

The debug fingerprint is developer-machine-specific. It must be included in `assetlinks.json` during development to enable local testing of App Links. It should be removed before production release.

### 10.3 Release Fingerprint

The release fingerprint comes from the production signing key. This key does not exist yet. It will be created when the app is prepared for Play Store submission or production distribution.

**The release fingerprint is a hard blocker for production App Links.**

### 10.4 Multiple Fingerprints

`assetlinks.json` supports multiple fingerprints in the `sha256_cert_fingerprints` array. During development, include both debug and release fingerprints. For production, include only the release fingerprint (and Google Play's upload key fingerprint if using Play App Signing).

---

## 11. Debug vs Release Signing Strategy

### 11.1 Debug Signing

| Aspect | Details |
|:---|:---|
| Keystore | `~/.android/debug.keystore` (auto-generated) |
| Alias | `androiddebugkey` |
| Password | `android` |
| Purpose | Local development and testing |
| Fingerprint in assetlinks.json | Yes — during development only |
| Machine-specific | Yes — each developer has a different debug fingerprint |

### 11.2 Release Signing

| Aspect | Details |
|:---|:---|
| Keystore | Must be created — does not exist yet |
| Alias | To be determined |
| Password | Must be securely stored — not in version control |
| Purpose | Production builds, Play Store submission |
| Fingerprint in assetlinks.json | Yes — required for production App Links |
| Machine-specific | No — same key used for all production builds |

### 11.3 Development Workflow

1. **During development:** Include the developer's debug fingerprint in `assetlinks.json`. App Links will verify on that developer's device.
2. **For CI/staging builds:** Include the CI signing key fingerprint if different from debug.
3. **For production:** Replace debug fingerprint with release fingerprint. If using Play App Signing, also include Google's signing key fingerprint.

---

## 12. Play Store / Production Signing Considerations

### 12.1 Play App Signing

If the app is distributed via Google Play, Google re-signs the APK/AAB with its own key (Play App Signing). This means the fingerprint in `assetlinks.json` must match Google's signing key, not the local upload key.

To get Google's signing key fingerprint:
1. Go to Play Console → App → Setup → App signing.
2. Copy the SHA-256 fingerprint from the "App signing key certificate" section.
3. Add this fingerprint to `assetlinks.json`.

### 12.2 Upload Key vs Signing Key

| Key | Where It Lives | Purpose | Fingerprint in assetlinks.json? |
|:---|:---|:---|:---|
| Upload key | Developer/CI machine | Signs the AAB before uploading to Play Console | No — Google re-signs with the signing key |
| App signing key | Google Play servers | Signs the final APK delivered to users | **Yes** — this is what's installed on devices |
| Debug key | Developer machine | Signs debug builds | Only during development |

### 12.3 Current Status

No Play Store account or signing keys exist for `com.yeshmishak.app`. This is a prerequisite blocker for production App Links.

---

## 13. Link Verification Behavior

### 13.1 How Android Verifies App Links

1. **At install time:** Android reads the app's manifest, finds intent filters with `autoVerify="true"`, and extracts the declared hosts.
2. **Verification request:** For each host, Android fetches `https://<host>/.well-known/assetlinks.json`.
3. **Fingerprint match:** Android checks that the installed app's signing certificate fingerprint appears in the `sha256_cert_fingerprints` array.
4. **Result:**
   - **Match:** Links for that host open directly in the app (no disambiguation dialog).
   - **No match / fetch failed:** Links open in the browser or show a disambiguation dialog.

### 13.2 Verification Timing

| Event | Verification Behavior |
|:---|:---|
| App installed | Verification runs immediately |
| App updated | Verification runs again if intent filters changed |
| Domain DNS changes | No automatic re-verification — user must reinstall or clear app defaults |
| `assetlinks.json` updated | Android may re-verify periodically (implementation varies by OEM/version) |
| Device reboot | No re-verification |

### 13.3 Verification Failure Modes

| Failure | Effect | Recovery |
|:---|:---|:---|
| `assetlinks.json` not reachable | Links open in browser | Fix hosting, reinstall app |
| Wrong Content-Type | Verification fails silently | Fix server response headers |
| Fingerprint mismatch | Links open in browser | Update `assetlinks.json` with correct fingerprint |
| Domain redirect loop | Verification fails | Fix redirect chain |
| Self-signed TLS certificate | Verification fails | Use a valid CA-signed certificate |

### 13.4 Testing Verification

Verification can be tested during development using `adb`:

```bash
# Check verification status
adb shell pm get-app-links com.yeshmishak.app

# Force re-verification
adb shell pm verify-app-links --re-verify com.yeshmishak.app

# Manually approve for testing (bypasses assetlinks.json)
adb shell pm set-app-links --package com.yeshmishak.app 0 all
```

---

## 14. Routing Handoff into the Web App

### 14.1 Flow

When an App Link is tapped:

```
User taps https://<canonical-domain>/fields/<field_id>
  │
  ├─ App installed + verified
  │   │
  │   ├─ App not running
  │   │   → Android launches MainActivity
  │   │   → Capacitor loads WebView
  │   │   → Initial intent contains URL
  │   │   → App.jsx mounts → deep link resolver reads URL → resolves resource
  │   │
  │   └─ App already running (singleTask)
  │       → Android calls onNewIntent() on existing MainActivity
  │       → Capacitor fires appUrlOpen event
  │       → App.jsx listener → deep link resolver processes URL
  │
  └─ App not installed OR verification failed
      → Chrome opens URL
      → SPA fallback serves index.html
      → Client-side resolver processes URL in browser
```

### 14.2 Capacitor Integration Point

The Capacitor `@capacitor/app` plugin provides the `appUrlOpen` event. The listener must be added in `App.jsx`:

```javascript
import { App as CapacitorApp } from '@capacitor/app'

CapacitorApp.addListener('appUrlOpen', (event) => {
  // event.url contains the full URL
  // Pass to deep link resolver
  deepLinkResolver.resolve(event.url)
})
```

This listener is not yet implemented. Its implementation is a separate issue per the ISSUE-267 sequence (Step 7 / Step 9).

### 14.3 Initial Launch URL

When the app is launched cold via an App Link, the URL is available via:

```javascript
const launchUrl = await CapacitorApp.getLaunchUrl()
if (launchUrl?.url) {
  deepLinkResolver.resolve(launchUrl.url)
}
```

Both `getLaunchUrl()` (cold start) and `appUrlOpen` (warm resume) must be handled.

---

## 15. Supported Route Mapping

| Android App Link URL | Deep Link Resolver Route | Target UI | Backend Dependency | Ready? |
|:---|:---|:---|:---|:---|
| `https://<canonical-domain>/fields/<field_id>` | `/fields/<field_id>` | Fly to field → open FieldDetailsPanel | `GET /fields/{field_id}` (exists) | Yes |
| `https://<canonical-domain>/games/<game_id>` | `/games/<game_id>` | Resolve field → open FieldDetailsPanel with game | `GET /games/{game_id}` (missing) | No |
| `https://<canonical-domain>/games/<game_id>/join` | `/games/<game_id>/join` | Same as above + auto-trigger join | `GET /games/{game_id}` (missing) | No |
| `https://<canonical-domain>/my-games` | `/my-games` | Open MyGamesPage | `GET /games/me` (exists) | Yes |
| `https://<canonical-domain>/invite/<game_id>` | `/invite/<game_id>` | Future: shareable invitation | TBD | No (future) |
| `https://<canonical-domain>/` | `/` | Open MapPage (home) | None | Yes |

---

## 16. Unsupported Route Behavior

When the app receives a URL that does not match any supported route:

| Scenario | Example URL | Behavior |
|:---|:---|:---|
| Unknown path | `https://<canonical-domain>/settings` | Show "Page not found" fallback with "Go to Map" button |
| Invalid UUID in path | `https://<canonical-domain>/fields/not-a-uuid` | Show "Invalid link" fallback |
| Admin path | `https://<canonical-domain>/admin` | Not a public App Link. If received, show "Page not found" fallback. Admin access is internal-only. |
| Path with no resource ID | `https://<canonical-domain>/fields/` | Show "Invalid link" fallback |
| Completely unknown domain path | `https://<canonical-domain>/api/v1/health` | Show "Page not found" fallback (API paths should not reach the app) |
| Legacy query format | `https://<canonical-domain>/?game_id=<id>` | Parse and resolve as `/games/<id>` (backward compatibility) |

The fallback screen must always provide a "Go to Map" button so the user is never stranded.

---

## 17. Notification Link Interaction

### 17.1 Current Notification Flow

Push notifications currently arrive via Firebase Cloud Messaging (FCM). The notification payload includes `game_id` and `field_id`. The service worker constructs `/?game_id={id}` on background notification tap, but this is not consumed by the frontend.

### 17.2 App Links and Notifications

App Links and push notification taps are separate entry vectors that converge on the same deep link resolver:

| Entry Vector | URL/Data Source | Resolver Input |
|:---|:---|:---|
| App Link (external URL tap) | `event.url` from `appUrlOpen` | Full URL pathname |
| Push notification tap (background) | Notification data payload `{ game_id, field_id }` | Constructed canonical route |
| Push notification tap (foreground) | In-app notification object | `handleNotificationTarget()` (existing) |

### 17.3 Notification → Resolver Bridge

When a push notification is tapped (background/killed state), the handler should construct a canonical route from the notification data and feed it to the deep link resolver:

```
Notification tap → extract game_id → construct /games/<game_id> → resolver
```

This avoids duplicating resolution logic between the notification handler and the App Link handler.

### 17.4 Dependency on Game Resolver

Since most notification types reference a `game_id`, the notification → resolver bridge depends on the same `GET /games/{game_id}` endpoint that game App Links need. Until this endpoint exists, notification taps can fall back to using the `field_id` from the notification payload (if present) and resolving via `GET /fields/{field_id}`.

---

## 18. Backend Dependency Gaps

| Gap | Impact | Severity | Resolution |
|:---|:---|:---|:---|
| No `GET /games/{game_id}` endpoint | Game links (`/games/<id>`) and game join links (`/games/<id>/join`) cannot resolve directly. Must look up game through field. | **High** | Add public `GET /games/{game_id}` returning `game_id`, `field_id`, `status`, `sport_type`, `scheduled_at`, `players_present`, `max_players`. |
| No SPA fallback on canonical domain | If app is not installed, the URL must serve the web SPA so the browser-based resolver can handle it. | **High** | Deploy web frontend to canonical domain with catch-all `index.html` fallback. |
| No `assetlinks.json` hosting | Android cannot verify App Links without this file. | **High** | Host at `https://<canonical-domain>/.well-known/assetlinks.json`. |
| No Open Graph meta tags | Shared links in WhatsApp/social show no preview. | **Medium** | Add server-side or edge-rendered OG tags for `/fields/<id>` and `/games/<id>` paths. Not required for App Links to function, but needed for link shareability. |

---

## 19. Testing Strategy

### 19.1 Pre-Implementation Testing

Before implementing App Links:

| Test | Method | Purpose |
|:---|:---|:---|
| Domain reachability | `curl -I https://<canonical-domain>/.well-known/assetlinks.json` | Verify hosting works |
| assetlinks.json validity | Google's [Statement List Generator](https://developers.google.com/digital-asset-links/tools/generator) | Validate JSON structure |
| Debug fingerprint extraction | `keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey -storepass android` | Get fingerprint for testing |

### 19.2 Post-Implementation Testing

| Test | Method | Expected Result |
|:---|:---|:---|
| Verification status | `adb shell pm get-app-links com.yeshmishak.app` | Shows `verified` for canonical domain |
| Field link opens app | `adb shell am start -a android.intent.action.VIEW -d "https://<canonical-domain>/fields/<valid-uuid>"` | App opens, flies to field, shows FieldDetailsPanel |
| Game link opens app | `adb shell am start -a android.intent.action.VIEW -d "https://<canonical-domain>/games/<valid-uuid>"` | App opens, shows game details (requires backend endpoint) |
| Invalid UUID | `adb shell am start -a android.intent.action.VIEW -d "https://<canonical-domain>/fields/not-a-uuid"` | App shows "Invalid link" fallback |
| Unknown route | `adb shell am start -a android.intent.action.VIEW -d "https://<canonical-domain>/xyz"` | App shows "Page not found" fallback |
| App not running | Force stop app, tap link | App launches cold, resolves link |
| App backgrounded | Background app, tap link | App resumes, resolves link |
| Logged-out user | Clear session, tap link | Login screen shown, link resolved after login |
| App not installed | Uninstall app, tap link in Chrome | Browser opens URL, SPA handles it |
| WhatsApp share | Send link in WhatsApp, tap it | App opens (if installed) or browser opens |

### 19.3 Automated Testing

Automated App Link testing is limited because verification requires a live domain and a signed APK. Recommended automated tests:

| Test | Scope | Automation |
|:---|:---|:---|
| Deep link resolver unit tests | URL parsing, route matching, UUID validation | Playwright / Vitest |
| Intent filter declaration | Verify manifest contains correct intent filter | Gradle / manifest parsing script |
| `assetlinks.json` format | Validate JSON structure | CI script with JSON schema validation |

---

## 20. Security Considerations

| Concern | Mitigation |
|:---|:---|
| Spoofed App Links | `autoVerify="true"` + `assetlinks.json` ensures only the verified app can claim the domain's URLs. Other apps cannot intercept links. |
| URL parameter injection | UUIDs are validated client-side (regex) and server-side (400 on invalid format). No SQL injection or path traversal risk via UUID parameters. |
| Sensitive data in URLs | URLs contain only resource type and UUID. No user names, auth tokens, session IDs, or personal data in the URL. |
| Man-in-the-middle | HTTPS-only scheme. No HTTP fallback. TLS protects URL in transit. |
| assetlinks.json tampering | File must be served over HTTPS from the canonical domain. Domain compromise would be required to tamper. Standard domain security practices apply. |
| Open redirect via deep links | The resolver only navigates to known internal routes. No arbitrary URL following. Unknown routes show a fallback screen, not a redirect. |
| Rate limiting on deep link API calls | Existing API rate limits apply. Each deep link resolution triggers at most one API call (`GET /fields/{id}` or `GET /games/{id}`). No amplification risk. |
| Admin route exposure | `/admin` is not included in App Links routes. Admin access remains internal-only. Even if an `/admin` URL is constructed, the deep link resolver shows "Page not found", and the backend enforces admin authorization independently. |

---

## 21. Rollout Plan

### Phase 1: Prerequisites (before any implementation)

| Step | Action | Owner | Status |
|:---|:---|:---|:---|
| 1 | Select and register canonical domain | Team decision | Pending |
| 2 | Deploy web SPA to canonical domain with catch-all fallback | Frontend / DevOps | Pending |
| 3 | Host `assetlinks.json` at `/.well-known/assetlinks.json` | Frontend / DevOps | Pending |
| 4 | Extract debug certificate SHA-256 fingerprint | Android developer | Pending |
| 5 | Confirm Android package name is `com.yeshmishak.app` | Team confirmation | Pending |

### Phase 2: Field Links (first implementation)

| Step | Action | Dependency |
|:---|:---|:---|
| 6 | Add App Link intent filter to `AndroidManifest.xml` | Steps 1–5 |
| 7 | Implement `appUrlOpen` listener in `App.jsx` | Step 6 |
| 8 | Implement deep link resolver for `/fields/<field_id>` | Step 7 |
| 9 | Test field links on device via `adb` | Step 8 |
| 10 | Verify App Link verification passes | Steps 3 + 6 |

### Phase 3: Game Links (requires backend work)

| Step | Action | Dependency |
|:---|:---|:---|
| 11 | Add `GET /games/{game_id}` backend endpoint | Backend team |
| 12 | Add `/games/<game_id>` route to deep link resolver | Steps 8 + 11 |
| 13 | Add `/games/<game_id>/join` route with join intent | Step 12 |
| 14 | Test game links on device | Step 13 |

### Phase 4: Notification Integration

| Step | Action | Dependency |
|:---|:---|:---|
| 15 | Update service worker to construct canonical URLs | Step 8 |
| 16 | Add Capacitor push notification action handler | Step 8 |
| 17 | Bridge notification tap → deep link resolver | Steps 15 + 16 |

### Phase 5: Production Release

| Step | Action | Dependency |
|:---|:---|:---|
| 18 | Create release signing keystore | Team decision |
| 19 | Add release fingerprint to `assetlinks.json` | Step 18 |
| 20 | Remove debug fingerprint from `assetlinks.json` | Step 19 |
| 21 | If using Play App Signing: add Google's signing key fingerprint | Play Console setup |
| 22 | Final verification on production-signed build | Steps 19–21 |

---

## 22. Implementation Checklist

| # | Item | Status |
|:---|:---|:---|
| 1 | Canonical domain selected and controlled | Pending |
| 2 | `assetlinks.json` hosted at `/.well-known/assetlinks.json` | Pending |
| 3 | Android package name confirmed as `com.yeshmishak.app` | Confirmed |
| 4 | Debug SHA-256 fingerprint extracted | Pending |
| 5 | Release SHA-256 fingerprint available | Pending (no release key) |
| 6 | Intent filter added to `AndroidManifest.xml` | Not started |
| 7 | `appUrlOpen` listener implemented in `App.jsx` | Not started |
| 8 | `getLaunchUrl()` cold-start handling implemented | Not started |
| 9 | Deep link resolver module created | Not started |
| 10 | `/fields/<field_id>` route handling implemented | Not started |
| 11 | `/games/<game_id>` route handling implemented | Blocked (no backend endpoint) |
| 12 | `/games/<game_id>/join` route handling implemented | Blocked (no backend endpoint) |
| 13 | `/my-games` route handling implemented | Not started |
| 14 | Unknown/invalid route fallback implemented | Not started |
| 15 | Auth intent storage + post-login resume implemented | Not started |
| 16 | Legacy `?game_id` query parameter compatibility | Not started |
| 17 | Push notification → resolver bridge implemented | Not started |
| 18 | App Link verification tested on device | Not started |
| 19 | WhatsApp share link tested | Not started |
| 20 | Production signing key created | Not started |
| 21 | Play App Signing fingerprint added (if applicable) | Not started |

---

## 23. Final Readiness Verdict

**READY FOR IMPLEMENTATION WITH DOMAIN/CERTIFICATE PREREQUISITES**

The Android App Links strategy is fully defined. The technical approach is sound: verified HTTPS App Links on a product-owned domain, broad host-scope intent filter with app-level routing, `assetlinks.json` verification, and a phased rollout starting with field links.

### Blockers

| # | Blocker | Why It Blocks | Resolution |
|:---|:---|:---|:---|
| 1 | **Canonical domain must be selected and controlled** | Intent filter `android:host`, `assetlinks.json` hosting, and all shared URLs depend on the domain. No implementation can begin without it. | Team must select, register, and configure DNS/hosting for the product domain. |
| 2 | **`assetlinks.json` hosting must be available** | Android App Link verification will fail without this file. Links will open in the browser instead of the app. | Deploy the file to `https://<canonical-domain>/.well-known/assetlinks.json` as part of the web frontend deployment. |
| 3 | **Android package name must be confirmed** | `assetlinks.json` includes the package name. Changing it after release breaks verification and requires a new Play Store listing. | Currently `com.yeshmishak.app` — confirm this is the final production package name. |
| 4 | **SHA-256 fingerprints for debug/release must be collected** | Without fingerprints, `assetlinks.json` cannot be populated. Debug fingerprint needed for development testing; release fingerprint needed for production. | Extract debug fingerprint immediately. Create release keystore when production build path is established. |
| 5 | **Game detail resolver endpoint needed before game links are production-grade** | `GET /games/{game_id}` does not exist. Game links and notification-to-game resolution cannot work without it. Field links can proceed independently. | Add `GET /games/{game_id}` public endpoint to the backend. |

### What Can Proceed Now

- Field links (`/fields/<field_id>`) are implementation-ready once blockers 1–4 are resolved. The backend `GET /fields/{field_id}` endpoint already exists.
- The deep link resolver module can be built and tested locally with mock data before the domain is live.
- Debug fingerprint extraction can happen immediately.

### What Cannot Proceed

- Game links and join links require blocker 5 (backend endpoint).
- Production App Link verification requires all 5 blockers resolved.
- Play Store distribution requires release signing key and Play App Signing setup.

---

## 24. Definition of Done Checklist

- [x] Executive decision stated (verified HTTPS App Links, product-owned domain, no custom schemes)
- [x] Current Android state documented (manifest, config, permissions, no existing deep links)
- [x] App Links objective defined
- [x] Domain ownership strategy specified (product-owned, placeholder documented)
- [x] Canonical link domain rules established
- [x] Disallowed domains listed with rationale
- [x] URL path strategy defined (4 route patterns + future invite)
- [x] Manifest intent-filter strategy defined (broad host scope, autoVerify)
- [x] assetlinks.json strategy defined (hosting, structure, requirements)
- [x] SHA-256 certificate fingerprint strategy defined (debug + release)
- [x] Debug vs release signing strategy documented
- [x] Play Store / production signing considerations covered
- [x] Link verification behavior explained (timing, failures, testing commands)
- [x] Routing handoff into web app documented (cold start + warm resume)
- [x] Supported route mapping table included
- [x] Unsupported route behavior defined
- [x] Notification link interaction documented
- [x] Backend dependency gaps identified (4 gaps with severity)
- [x] Testing strategy defined (pre-implementation, post-implementation, automated)
- [x] Security considerations documented (8 concerns with mitigations)
- [x] Rollout plan defined (5 phases, 22 steps)
- [x] Implementation checklist included (21 items with status)
- [x] Final readiness verdict stated (READY FOR IMPLEMENTATION WITH DOMAIN/CERTIFICATE PREREQUISITES)
- [x] Five blockers explicitly listed
- [x] Scope confirmed documentation-only
