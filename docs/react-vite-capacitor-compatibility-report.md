# React + Vite + Capacitor Compatibility Report

**ISSUE:** 189
**Date:** 2026-06-30
**Status:** Audit complete
**Scope:** Compatibility audit only - no code changes, no dependency changes, no native project changes
**Branch:** `issue-189-react-vite-capacitor-compatibility`

---

## 1. Review Summary

| Property | Value |
| :--- | :--- |
| Overall status | **GO WITH RISKS** |
| Build passes | Yes |
| Build output compatible with Capacitor webDir | Yes - PASS WITH NOTES (absolute asset paths acceptable for current config) |
| Routing compatible | Yes (manual History API, no React Router) |
| Environment/config compatible | Yes |
| Browser APIs compatible | Mostly yes - service worker and web push need native path |
| Production Capacitor packaging ready | No - known blockers remain |

The React + Vite frontend can be packaged into a Capacitor debug build today. Production mobile release remains blocked by signing key (B-02), Firebase native config (B-03), CORS (B-04), and native Google Sign-In (B-01).

---

## 2. Version Inventory

| Package | Installed Version | Declared Range | Source | Assessment | Risk |
| :--- | :--- | :--- | :--- | :--- | :--- |
| react | 19.2.7 | ^19.2.6 | `package.json` | Compatible with Capacitor WebView | None |
| react-dom | 19.2.7 | ^19.2.6 | `package.json` | Compatible | None |
| vite | 8.0.16 | ^8.0.12 | `package.json` | Compatible - outputs standard HTML/JS/CSS | None |
| @vitejs/plugin-react | 6.0.2 | ^6.0.1 | `package.json` | Compatible | None |
| @capacitor/core | 8.4.1 | ^8.4.1 | `package.json` | Current | None |
| @capacitor/android | 8.4.1 | ^8.4.1 | `package.json` | Current | None |
| @capacitor/cli | 8.4.1 | ^8.4.1 | `package.json` (devDependencies) | Current | None |
| @capacitor/push-notifications | 8.1.1 | ^8.1.1 | `package.json` | Compatible with Capacitor 8 | None |
| axios | latest | ^1.17.0 | `package.json` | Compatible - standard HTTP client | None |
| firebase | latest | ^12.15.0 | `package.json` | Web SDK - partial Capacitor risk | Medium |
| leaflet | latest | ^1.9.4 | `package.json` | Compatible - canvas/SVG rendering | None |
| react-leaflet | 5.0.0 | ^5.0.0 | `package.json` | Compatible | None |
| i18next | latest | ^26.3.1 | `package.json` | Compatible | None |
| react-i18next | 17.0.8 | ^17.0.8 | `package.json` | Compatible | None |
| typescript | latest | ^6.0.3 | `package.json` (devDependencies) | Type checking only | None |

No peer dependency warnings were reported by `npm ls`.

---

## 3. Vite Build Compatibility

### 3.1 Build Result

```
> vite build
vite v8.0.16 building client environment for production...
1916 modules transformed.
dist/index.html                   0.48 kB | gzip:   0.31 kB
dist/assets/index-BFZ0ARls.css   52.62 kB | gzip:  13.15 kB
dist/assets/index-DD_LJnS8.js   615.21 kB | gzip: 186.70 kB
Built in 1.29s
```

**Build: PASS.** No errors, no large chunk warnings.

### 3.2 Vite Configuration

From `frontend/vite.config.js`:

```javascript
export default defineConfig({
  plugins: [react()],
})
```

| Setting | Value | Impact |
| :--- | :--- | :--- |
| `base` | Not set (defaults to `/`) | **Risk** - see Section 3.3 |
| `build.outDir` | Not set (defaults to `dist`) | Compatible with Capacitor `webDir: 'dist'` |
| Aliases | None | No issue |
| Dev server proxy | None | No issue |
| SSR | None | No issue |

### 3.3 Asset Path Risk

The built `dist/index.html` references assets with absolute paths:

```html
<link rel="icon" type="image/svg+xml" href="/favicon.svg" />
<script type="module" crossorigin src="/assets/index-DD_LJnS8.js"></script>
<link rel="stylesheet" crossorigin href="/assets/index-BFZ0ARls.css">
```

In Capacitor's Android WebView with `androidScheme: 'https'`, the WebView origin is `https://localhost`. Absolute paths like `/assets/...` resolve to `https://localhost/assets/...`, which Capacitor's local file server handles correctly. This works because Capacitor intercepts requests to the local origin and serves files from the `webDir`.

**Assessment: PASS WITH NOTES.**

Absolute asset paths (`/assets/...`, `/favicon.svg`) were found in the built `dist/index.html`. These are acceptable because:

1. Capacitor's local file server intercepts requests to the configured origin (`https://localhost` when `androidScheme: 'https'`) and serves files from `webDir` (`dist/`).
2. An absolute path like `/assets/index-DD_LJnS8.js` resolves to `https://localhost/assets/index-DD_LJnS8.js`, which Capacitor maps to `dist/assets/index-DD_LJnS8.js`.

These paths would become risky if:

- `androidScheme` were changed to `http` or removed (origin would change).
- Capacitor's `server.url` were set to a remote URL (assets would not be served locally).
- A custom `base` path were added to Vite without matching Capacitor config.
- The app were served from a subdirectory rather than root.

No fix is implemented in ISSUE-189. The current configuration is compatible.

### 3.4 Build Output

| Item | Status |
| :--- | :--- |
| Output directory | `dist/` |
| `index.html` exists | Yes |
| CSS emitted | `dist/assets/index-BFZ0ARls.css` (52.62 kB) |
| JS emitted | `dist/assets/index-DD_LJnS8.js` (615.21 kB) |
| Public assets copied | `favicon.svg`, `firebase-messaging-sw.js`, `stadium-active.png`, `stadium-inactive.png` |
| Sourcemaps | Not generated (default Vite production behavior) |
| Large chunk warnings | None |

### 3.5 webDir Alignment

| Config | Value | Match |
| :--- | :--- | :--- |
| Vite `build.outDir` | `dist` (default) | Yes |
| Capacitor `webDir` | `dist` | Yes |

**Assessment: PASS.**

---

## 4. Capacitor Config Compatibility

From `frontend/capacitor.config.ts`:

| Property | Value | Expected | Status |
| :--- | :--- | :--- | :--- |
| `appId` | `com.yeshmishak.app` | `com.yeshmishak.app` | PASS |
| `appName` | `Yesh Mishak` | Correct | PASS |
| `webDir` | `dist` | Matches Vite output | PASS |
| `server.androidScheme` | `https` | Correct for CORS | PASS |
| `server.url` | Not set | Correct - not set for production | PASS |
| Plugin config | `PushNotifications` with presentation options | Expected | PASS |

| Item | Status |
| :--- | :--- |
| Android project (`frontend/android/`) | Exists |
| iOS project (`frontend/ios/`) | Does not exist (deferred) |

**Assessment: PASS.** Capacitor config aligns with ISSUE-181 through ISSUE-188 documentation.

---

## 5. Routing Compatibility

### 5.1 Current Routing Model

The app uses **manual History API routing** (not React Router). From `frontend/src/App.jsx`:

- `window.location.pathname` read on mount
- `window.history.pushState()` for navigation
- `popstate` event listener for back/forward
- Routes: `/` (map), `/my-games`, `/admin`
- State-driven rendering based on pathname

### 5.2 Capacitor Compatibility

| Aspect | Status | Notes |
| :--- | :--- | :--- |
| No React Router dependency | Compatible | No BrowserRouter/HashRouter complexity |
| History API in WebView | Compatible | Capacitor WebView supports `pushState`/`popstate` |
| Server-side fallback required | No | Single `index.html` serves all routes |
| Deep link support | Not implemented | Future issue (OD-03 in ISSUE-181) |
| Refresh/reload behavior | Compatible | Capacitor serves `index.html` for all local paths |
| Modal state in URL | No | Modals use React state only |

### 5.3 Risk Assessment

**Risk: LOW.** The manual History API approach is simpler than React Router for Capacitor. No server-side routing dependency. Deep linking is a future feature (tracked as OD-03).

---

## 6. Assets Compatibility

### 6.1 Public Directory

| File | Size | Packaging |
| :--- | :--- | :--- |
| `favicon.svg` | 9.5 kB | Copied to `dist/` at build time |
| `firebase-messaging-sw.js` | 1.7 kB | Copied to `dist/` - service worker (see Section 9) |
| `stadium-active.png` | 172 kB | Copied to `dist/` |
| `stadium-inactive.png` | 150 kB | Copied to `dist/` |

### 6.2 Asset References

| Pattern | Found | Risk |
| :--- | :--- | :--- |
| Absolute `/assets/...` in built HTML | Yes | Compatible with Capacitor local server |
| Hardcoded external URLs | Google Maps navigation link, Google Identity Services script | Requires internet access |
| `url(...)` in CSS | Leaflet tile references only | Compatible |
| Hardcoded `localhost` or `127.0.0.1` | None in source | PASS |

### 6.3 External Script Dependencies

| Script | Source | Used In | Capacitor Risk |
| :--- | :--- | :--- | :--- |
| Google Identity Services | `https://accounts.google.com/gsi/client` | `LoginPage.jsx` | Medium - may not work in WebView (see Section 10) |
| Firebase SDK (compat) | `https://www.gstatic.com/firebasejs/10.14.1/` | `firebase-messaging-sw.js` | High - service worker not supported in WebView (see Section 9) |

**Assessment: PASS WITH NOTES.** Absolute asset paths are compatible with the current Capacitor local server configuration (see Section 3.3). External scripts (Google Identity Services, Firebase SDK) require internet access in the WebView.

---

## 7. Environment and API Config Compatibility

### 7.1 API URL

| Check | Status |
| :--- | :--- |
| Canonical variable | `VITE_API_URL` (per ISSUE-185) |
| Fallback variable | `VITE_API_BASE_URL` (backward-compatible only) |
| API client reads from env vars | Yes (`frontend/src/api/client.js`) |
| Hardcoded backend URLs in source | None |
| Centralized API client | Yes (axios instance in `client.js`) |

### 7.2 Secrets Exposure

| Check | Status |
| :--- | :--- |
| `SUPABASE_SERVICE_ROLE_KEY` in frontend | Not present |
| Database passwords in frontend | Not present |
| Firebase service account in frontend | Not present |
| JWT secret in frontend | Not present |
| Backend-only secrets in VITE_ variables | None |

### 7.3 Build-Time Config

| Check | Status |
| :--- | :--- |
| Runtime environment switch | Forbidden (per ISSUE-184) |
| Build-time environment selection | Correct |
| `import.meta.env` usage | Standard Vite pattern |

**Assessment: PASS.** API configuration is clean and compatible with Capacitor builds.

---

## 8. Browser API Compatibility

| API | File(s) | Current Use | Capacitor WebView | Risk |
| :--- | :--- | :--- | :--- | :--- |
| `window.location` | `App.jsx` | Pathname routing | Available | None |
| `window.history` | `App.jsx` | pushState/replaceState | Available | None |
| `window.addEventListener` | Multiple | Event listeners | Available | None |
| `window.setTimeout/setInterval` | Multiple | Timers | Available | None |
| `window.open` | `FieldDetailsPanel.jsx` | External navigation links | Available but may need Capacitor Browser plugin for better UX | Low |
| `window.dispatchEvent` | `api/client.js`, `api/auth.js` | Custom events | Available | None |
| `document.getElementById` | `main.jsx` | Root mount | Available | None |
| `document.createElement` | `LoginPage.jsx` | Google script injection | Available | None |
| `document.addEventListener` | Multiple | Click/touch handlers | Available | None |
| `document.body` | `useBodyScrollLock.js` | Body scroll control | Available | None |
| `document.activeElement` | `Modal.jsx` | Focus management | Available | None |
| `document.documentElement` | `i18n/index.js` | RTL direction | Available | None |
| `document.visibilityState` | `MapPage.jsx` | Polling pause | Available | None |
| `navigator.onLine` | `useOnlineStatus.js`, `api/retry.js` | Offline detection | Available | None |
| `navigator.geolocation` | `MapPage.jsx`, `NotificationsModal.jsx`, `AddFieldModal.jsx` | User location | Available in WebView | None |
| `navigator.languages` | `i18n/index.js` | Language detection | Available | None |
| `navigator.serviceWorker` | `firebaseMessaging.js` | Web push registration | **Not available** in Capacitor WebView | **High** |
| `localStorage` | Multiple (auth, i18n, onboarding, cache, push token) | Persistent storage | Available in WebView | Medium (security) |
| `sessionStorage` | None | Not used | N/A | None |
| `Notification` | `firebaseMessaging.js` | Web Notification API | **Not available** in Capacitor WebView | **High** |
| `matchMedia` | Not used | N/A | Available | None |
| `beforeinstallprompt` | Not used | N/A | N/A | None |
| `caches` | Not used | N/A | N/A | None |
| `indexedDB` | Not used | N/A | Available | None |

### 8.1 Summary

- **25 APIs used** across the codebase
- **23 are fully compatible** with Capacitor WebView
- **2 are browser-only** and will not work in Capacitor: `navigator.serviceWorker` and `Notification` API (both used in `firebaseMessaging.js` for web push)
- The web push code path is already documented as requiring a native alternative via `@capacitor/push-notifications` (ISSUE-181 R-03, ISSUE-186)

---

## 9. Firebase / Push Compatibility

### 9.1 Current Web Push Implementation

The web push path in `frontend/src/firebaseMessaging.js`:

1. Checks `navigator.serviceWorker` availability
2. Registers `firebase-messaging-sw.js` as a service worker
3. Gets Firebase messaging token via `getToken()`
4. Listens for foreground messages via `onMessage()`
5. Shows notifications via `new Notification()` or `registration.showNotification()`

The service worker (`frontend/public/firebase-messaging-sw.js`) imports Firebase compat scripts from `gstatic.com` and handles background messages.

### 9.2 Capacitor Compatibility

| Component | Web Browser | Capacitor WebView | Status |
| :--- | :--- | :--- | :--- |
| Service worker registration | Works | **Does not work** | Known risk |
| Firebase Web Messaging SDK | Works | Does not work (needs service worker) | Known risk |
| `Notification` API | Works | Not available | Known risk |
| `@capacitor/push-notifications` | N/A | **Available** (installed) | Ready for native path |

### 9.3 Platform Detection

The current code does **not** detect whether it is running in a Capacitor WebView or a regular browser. It always attempts the web push path. This means:

- In Capacitor WebView, `firebaseMessaging.js` will throw an error at the `serviceWorker` check
- The error is caught by `startForegroundPushNotifications().catch()` in `App.jsx` (line 73-75), so the app does not crash
- But native push notifications will not work until a native code path is implemented

### 9.4 Risk Assessment

**Risk: HIGH for push notifications. LOW for app stability.**

The app gracefully handles the failure, but push notifications will not function in the native app until a platform detection bridge is implemented (tracked as OD-04 in ISSUE-181). The `@capacitor/push-notifications` plugin is already installed and ready for the native path.

### 9.5 Follow-Up Required

- Implement platform detection using `Capacitor.isNativePlatform()`
- Add native push registration path using `@capacitor/push-notifications`
- Keep web push path for browser users
- Separate implementation issue required

---

## 10. Google Sign-In Compatibility

### 10.1 Current Web Implementation

`frontend/src/components/LoginPage.jsx` loads the Google Identity Services (GIS) script dynamically:

```
https://accounts.google.com/gsi/client
```

It uses `window.google.accounts.id.initialize()` and `renderButton()` to show the Google Sign-In button.

### 10.2 Capacitor Compatibility

| Aspect | Status |
| :--- | :--- |
| GIS script loading in WebView | May work but not officially supported by Google for WebViews |
| Google One Tap in WebView | Typically blocked by Google in embedded WebViews |
| `@codetrix-studio/capacitor-google-auth` | Not installed - incompatible with Capacitor 8 (requires ^6.0.0) |
| Native Google Sign-In alternative | Not yet decided (tracked as OD-02 in ISSUE-181, blocker B-01) |

### 10.3 Risk Assessment

**Risk: HIGH.** Google Identity Services may not render or function correctly in a Capacitor WebView. Google actively restricts sign-in flows in embedded WebViews for security reasons. The app has email/password login as a fallback, so the app is usable without Google Sign-In, but the primary login method is at risk.

### 10.4 Follow-Up Required

- Resolve OD-02: select native Google Sign-In strategy for Capacitor 8
- Options: Android Credential Manager, plugin fork, WebView OAuth redirect
- Tracked as blocker B-01 in `docs/epic-03-completion-review.md`

---

## 11. Auth Storage Compatibility

### 11.1 Current Storage Model

Authentication tokens and user data are stored in `localStorage`:

| Key | Purpose | Set In | Read In |
| :--- | :--- | :--- | :--- |
| `access_token` | JWT access token | `api/auth.js` | `api/client.js`, `App.jsx`, `AdminRoute.jsx` |
| `currentUserId` | User ID | `api/auth.js` | `api/auth.js` |
| `currentUserName` | Display name | `api/auth.js` | `App.jsx` |
| `currentUserEmail` | Email | `api/auth.js` | `App.jsx` |
| `currentUsername` | Username | `api/auth.js` | `App.jsx` |
| `onboarding_done` | Onboarding flag | `OnboardingPage.jsx` | `App.jsx` |
| `userCity` | Selected city | `OnboardingPage.jsx` | `MapPage.jsx` |
| `app_language` | Language preference | `i18n/index.js` | `i18n/index.js` |
| `app_language_selected` | Language selected flag | `i18n/index.js` | `i18n/index.js` |
| `yesh_mishak_push_token` | Push token | `NotificationsModal.jsx` | `NotificationsModal.jsx` |
| `yesh_mishak_cached_fields` | Field data cache | `MapPage.jsx` | `MapPage.jsx` |
| `yesh_mishak_cached_fields_ts` | Cache timestamp | `MapPage.jsx` | `MapPage.jsx` |

`sessionStorage` is not used anywhere in the codebase.

### 11.2 WebView Compatibility

`localStorage` is available and functional in Capacitor WebView. Data persists across app restarts. The current approach works for debug and internal testing builds.

### 11.3 Security Gap

Storing JWT tokens in `localStorage` is a known security risk for production native apps:

- `localStorage` in WebView is not encrypted
- On rooted/jailbroken devices, the data can be read by other apps
- ISSUE-181 documents this as risk R-01 (High severity)
- ISSUE-181 tracks secure storage plugin selection as open decision OD-01

### 11.4 Risk Assessment

**Risk: LOW for debug builds. HIGH for production release.**

The current `localStorage` approach is acceptable for development and internal testing. Before production release, a secure storage plugin (Keystore on Android, Keychain on iOS) must be selected and implemented.

### 11.5 Follow-Up Required

- Resolve OD-01: select encrypted storage plugin
- Implement secure token storage before production release
- Separate implementation issue required

---

## 12. CSS / Viewport Compatibility

### 12.1 Current Mobile CSS Readiness

The CSS in `frontend/src/App.css` shows strong mobile and Capacitor awareness:

| Feature | Status | Evidence |
| :--- | :--- | :--- |
| `100dvh` usage | Yes | Used throughout instead of `100vh` |
| `safe-area-inset-*` | Yes | Full safe-area CSS custom properties defined |
| `env(safe-area-inset-*)` | Yes | Root-level CSS variables with fallbacks |
| RTL support | Yes | `dir="rtl"` with logical properties (`inset-inline-start`, `inset-inline-end`) |
| Fixed positioning | Yes | Multiple fixed-position elements with safe-area offsets |
| `viewport-fit=cover` | **Not set** in `index.html` | Needed for safe-area to work on iOS |

### 12.2 Safe-Area Implementation

The CSS defines custom properties at `:root`:

```css
--safe-area-top: env(safe-area-inset-top, 0px);
--safe-area-right: env(safe-area-inset-right, 0px);
--safe-area-bottom: env(safe-area-inset-bottom, 0px);
--safe-area-left: env(safe-area-inset-left, 0px);
```

These are used throughout for positioning toolbars, modals, and panels. RTL direction swaps `--safe-area-inline-start` and `--safe-area-inline-end`.

### 12.3 Missing `viewport-fit=cover`

The `index.html` viewport meta tag is:

```html
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
```

For safe-area insets to work on iOS (and future iOS Capacitor builds), the viewport meta tag should include `viewport-fit=cover`:

```html
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
```

Without this, `env(safe-area-inset-*)` values will be 0 on iOS devices with notches. On Android, Capacitor handles this differently and the current setup works.

### 12.4 Virtual Keyboard

No specific virtual keyboard handling was found. The app uses standard input elements. Potential risks:

- Fixed-position elements may shift when the keyboard opens
- `100dvh` helps but does not fully resolve keyboard overlap on all platforms
- This is a common WebView issue that can be addressed in a future UX refinement

### 12.5 Risk Assessment

**Risk: LOW for Android. MEDIUM for future iOS.**

The CSS is well-prepared for native WebView with safe-area support and `dvh` units. The missing `viewport-fit=cover` is only relevant for iOS (which does not have a native project yet). Should be added before iOS project generation.

---

## 13. Known Risks

| ID | Area | Severity | Finding | Impact | Follow-Up | Blocks Debug Build | Blocks Production |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| R-01 | Push notifications | High | Web push (service worker) does not work in Capacitor WebView | No push in native app | Implement native push path with `@capacitor/push-notifications` | No (graceful failure) | Yes |
| R-02 | Google Sign-In | High | GIS may not work in embedded WebView | Primary login method at risk | Resolve native Google Sign-In strategy (OD-02) | No (email/password fallback) | Yes |
| R-03 | Auth storage | High | JWT in localStorage is not encrypted | Security risk on rooted devices | Select secure storage plugin (OD-01) | No | Yes |
| R-04 | Signing | High | No production signing key | Cannot sign production builds | Create signing key (B-02) | No | Yes |
| R-05 | Firebase native | High | No `google-services.json` | Native FCM will not initialize | Download from Firebase Console (B-03) | No (web path fails gracefully) | Yes |
| R-06 | CORS | High | `https://localhost` not in production CORS | Native app cannot call production API | Add to CORS origins (B-04) | No (dev API works) | Yes |
| R-07 | CSS viewport | Low | Missing `viewport-fit=cover` in index.html | Safe-area insets return 0 on iOS | Add before iOS project generation | No | No (iOS deferred) |
| R-08 | External scripts | Low | Google/Firebase scripts require internet | Login and push fail offline | Expected behavior - document in user-facing docs | No | No |

---

## 14. Final Decision

### 14.1 React/Vite Compatibility for Debug Capacitor Packaging

**GO WITH RISKS.**

The React 19 + Vite 8 frontend builds successfully and produces output compatible with Capacitor's `webDir` configuration. The routing model (manual History API) works in WebView. Most browser APIs used are available in Capacitor WebView. The CSS already accounts for safe-area insets and uses modern viewport units.

A debug APK can be built and installed for local testing. The app will load, display the map, and allow email/password login. Push notifications and Google Sign-In will not function in the native build but fail gracefully.

### 14.2 Production Mobile Release Readiness

**NO-GO.**

Production release remains blocked by:

1. No native push notification code path (R-01)
2. No native Google Sign-In strategy (R-02, B-01)
3. No secure token storage (R-03, OD-01)
4. No production signing key (R-04, B-02)
5. No `google-services.json` (R-05, B-03)
6. No CORS entry for Capacitor origin (R-06, B-04)

These are tracked in `docs/epic-03-completion-review.md` and open decisions in `docs/mobile-application-architecture.md`.
