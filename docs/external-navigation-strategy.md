# External Navigation Strategy

**Issue:** ISSUE-274 (#369)
**Date:** 2026-07-11
**Dependency:** `docs/location-usage-audit-report.md` (ISSUE-251)
**Status:** Strategy definition only — no implementation

---

## 1. Executive Decision

Navigation to a field will be delegated to an external navigation provider. The app will not calculate routes, track the user's journey, or send the user's origin in the navigation URL. It will pass only the validated destination latitude and longitude.

The application will determine which supported native providers are available on the current platform:

- **Android:** Waze and Google Maps.
- **iOS:** Waze, Apple Maps, and Google Maps.
- **Web:** Waze and Google Maps; Apple Maps may be shown only on Apple platforms where the link is supported.

If exactly one supported native provider is available, the app launches it immediately. If two or more supported providers are available, the app presents the provider chooser. If no supported native provider is available, the app falls back to a supported HTTPS navigation experience, with Google Maps preferred.

When a chooser is shown, the application presents supported providers in a platform-appropriate order. The exact visual ordering is a UX decision and may evolve without requiring a strategy change.

If a selected native app is missing or cannot be opened, the app must fall back to that provider's HTTPS experience when available, then offer another provider. Navigation failure must never block field details or other app use.

---

## 2. Purpose

Navigation to a sports field is a core product action. The application already exposes Waze and Google Maps links from `FieldDetailsPanel.jsx`, but it has no approved cross-platform contract for provider availability, provider ordering, user choice, native launch behavior, or failure handling.

This document defines that contract before ISSUE-275 through ISSUE-278 implement or refine the provider integrations.

---

## 3. Current State

The current field-details navigation modal offers two actions:

| Provider | Current URL | Current behavior |
|:---|:---|:---|
| Waze | `https://waze.com/ul?ll=<lat>,<lng>&navigate=yes` | Opens a new browser/app target with destination coordinates |
| Google Maps | `https://www.google.com/maps/dir/?api=1&destination=<lat>,<lng>` | Opens a new browser/app target with destination coordinates |
| Apple Maps | Not implemented | No option is shown |

The current implementation validates that field coordinates are finite and within latitude/longitude ranges, then calls `window.open(..., '_blank', 'noopener,noreferrer')`. It does not detect whether a provider app is installed and does not confirm whether the launch succeeded.

The location audit establishes two constraints that this strategy preserves:

1. Navigation links are destination-only; user coordinates are not embedded.
2. Navigation remains optional and independent of location permission.

---

## 4. Product Principles

1. **Availability-aware routing.** The app launches the sole available supported native provider, presents user choice when multiple providers are available, and does not change the user's device-wide navigation preference.
2. **Platform-native expectations.** Available options and ordering should match the current platform.
3. **Destination-only privacy.** The external provider determines the origin after it opens; yesh_mishak does not transmit the user's location.
4. **Graceful degradation.** A missing provider, blocked popup, invalid URL, or launch failure must return the user to a usable chooser.
5. **No routing ownership.** Route calculation, traffic, transport mode, rerouting, and arrival behavior belong to the provider.
6. **No install assumption.** Waze and Google Maps may be absent. Only the platform navigation service may be treated as generally available on its own platform.

---

## 5. Provider Evaluation

| Criterion | Waze | Google Maps | Apple Maps |
|:---|:---|:---|:---|
| Primary value | Strong driving experience and high adoption in Israel | Broad cross-platform and browser coverage | Native iOS experience and platform availability |
| Android | Supported | Supported | Not offered |
| iOS | Supported if installed; HTTPS fallback | Supported if installed; HTTPS fallback | Supported as the native iOS option |
| Web fallback | Waze Live Map / provider landing behavior | Full browser directions experience | Browser link is useful mainly on Apple platforms |
| Destination coordinates | Supported | Supported | Supported |
| App may be missing | Yes | Yes | Not as a normal iOS condition |
| Strategy verdict | **Supported on Android, iOS, and web** | **Supported everywhere; preferred HTTPS fallback** | **Supported on iOS/Apple platforms** |

No native provider is selected as the universal default because availability differs by platform and device. Google Maps is the preferred HTTPS fallback when no supported native provider is available.

---

## 6. Platform Matrix and Ordering

| Runtime | Supported providers | Ordering approach | Rationale |
|:---|:---|:---|:---|
| Android native | Waze, Google Maps | Platform-appropriate UX order | Both providers are supported; availability determines direct launch or chooser behavior |
| iOS native | Apple Maps, Waze, Google Maps | Platform-appropriate UX order | Apple Maps is the built-in platform option; the user may still choose another available provider |
| Desktop/mobile web on non-Apple platform | Waze, Google Maps | Platform-appropriate UX order | Both have HTTPS entry points; no Apple-only option |
| Safari/web on Apple platform | Apple Maps, Waze, Google Maps | Platform-appropriate UX order | Aligns with platform expectations while retaining supported choices |
| Unknown platform | Google Maps, Waze | Platform-appropriate UX order | Google Maps provides the preferred HTTPS fallback |

Platform and provider availability determine the supported options and whether the app launches the sole available native provider or shows the chooser. Exact visual ordering remains a UX decision and is not part of the permanent architecture.

---

## 7. Default Option and User Choice

### 7.1 Official Default Decision

The official default is **availability-aware selection**:

- If exactly one supported native navigation provider is available, launch it immediately.
- If two or more supported providers are available, present the provider chooser.
- If no supported native provider is available, fall back to a supported HTTPS navigation experience, with Google Maps preferred.

The chooser is therefore the default only when multiple supported providers are available. When shown, it uses a platform-appropriate order whose exact presentation may evolve as a UX decision without requiring a strategy change.

### 7.2 Remembering a Choice

Version 1 will not remember a provider choice. Remembering a choice can hide alternatives after an app is removed and can surprise users who alternate between driving contexts.

A future “Remember my choice” setting may be added only if it includes:

- an explicit opt-in;
- a visible Settings control to change or clear it;
- automatic clearing when the provider cannot be opened; and
- continued access to “Choose another app”.

Remembering a preference is not part of ISSUE-275 through ISSUE-278 unless separately approved.

---

## 8. Navigation URL Contract

All provider requests must contain only a validated destination:

| Provider | HTTPS contract | Native contract for future implementation |
|:---|:---|:---|
| Waze | `https://waze.com/ul?ll=<lat>,<lng>&navigate=yes` | Provider-supported Waze deep link if launch capability is verified |
| Google Maps | `https://www.google.com/maps/dir/?api=1&destination=<lat>,<lng>` | Provider-supported Google Maps scheme/intent if launch capability is verified |
| Apple Maps | `https://maps.apple.com/?daddr=<lat>,<lng>&dirflg=d` | Apple Maps URL handled by iOS |

Rules:

1. Latitude and longitude must be finite numeric values.
2. Latitude must be between -90 and 90; longitude must be between -180 and 180.
3. Values must be URL-encoded by a shared navigation-link builder.
4. The URL must not include user origin, user identity, authentication tokens, field notes, or other personal data.
5. The field name may be added later only as a display label after correct encoding; coordinates remain authoritative.
6. Links must be opened only from an explicit user gesture.

---

## 9. Missing App and Failure Handling

Provider launch must follow a deterministic fallback chain:

1. Validate destination coordinates before showing or launching an option.
2. On native platforms, check whether the provider's native URL can be opened when the platform API supports a reliable capability check.
3. If the native provider is available, launch it.
4. If it is unavailable or launch fails, open the provider's HTTPS URL when that provides a usable experience.
5. If HTTPS cannot be opened, keep or reopen the chooser and show a localized, non-technical message with the remaining providers.
6. Provide a “Cancel” action that returns to field details without side effects.

The app must not:

- show success merely because a launch call was attempted;
- send users directly to an app store without explicit confirmation;
- loop repeatedly between native and HTTPS URLs;
- close the field-details surface before a launch has been accepted; or
- treat navigation failure as an application error or authentication failure.

App-store installation links may be offered as a secondary, explicit action in ISSUE-278. They are never the only fallback.

---

## 10. UX Contract

When multiple supported providers are available, the navigation chooser must:

- use localized provider-independent title and explanatory copy;
- show the official provider name and recognizable provider icon;
- show only platform-relevant options;
- keep each option as a separate accessible button;
- support keyboard focus, screen readers, and minimum mobile touch targets;
- expose a clear Cancel action; and
- preserve field context if the external app does not open.

Recommended failure copy:

> The selected navigation app could not be opened. Choose another app or continue in your browser.

Provider names are proper names and should not be translated. The surrounding interface text must follow the application's active Hebrew/English language and RTL/LTR direction.

---

## 11. Privacy and Security

1. Only field destination coordinates leave the app through a provider URL.
2. User location is not requested for navigation and is never added as an origin parameter.
3. No authentication token, internal API URL, user ID, or session state may be included.
4. Browser launches use `noopener,noreferrer` where supported.
5. Provider URLs must be constructed from fixed, allowlisted templates; no caller-supplied host or scheme is accepted.
6. Navigation attempts may log provider, platform, and outcome category, but never coordinates or complete URLs.
7. External navigation is clearly user-initiated; no launch occurs on page load, map movement, or notification receipt.

---

## 12. Ownership Boundaries

| Responsibility | Owner |
|:---|:---|
| Validate field destination | yesh_mishak |
| Present provider choice | yesh_mishak |
| Build allowlisted provider URL | yesh_mishak |
| Detect/attempt provider launch | yesh_mishak platform integration |
| Determine user origin | External provider |
| Calculate route and traffic | External provider |
| Request provider-side location permission | External provider |
| Rerouting, voice guidance, arrival | External provider |

The app must not duplicate provider routing features or request location permission merely to open navigation.

---

## 13. Implementation Boundaries

This issue is documentation-only. Implementation is divided as follows:

| Issue | Responsibility |
|:---|:---|
| ISSUE-275 | Waze navigation integration |
| ISSUE-276 | Google Maps navigation integration |
| ISSUE-277 | Apple Maps navigation integration |
| ISSUE-278 | Missing-app and fallback handling |

Each implementation issue must follow this strategy and must add platform-appropriate tests. Changes to exact provider ordering are UX decisions and do not require a strategy change. Any change to destination-only privacy or the availability-aware default decision requires a new documented architecture decision.

---

## 14. Test Requirements for Future Implementation

Future implementation must verify:

1. Correct supported providers and platform-appropriate presentation on Android, iOS, Apple web, non-Apple web, and unknown platforms.
2. Valid positive, negative, and boundary coordinates.
3. Invalid, missing, non-numeric, and out-of-range coordinates do not launch anything.
4. Each provider receives the exact encoded destination and no origin/user data.
5. Installed native provider launches successfully.
6. Missing provider uses HTTPS fallback.
7. Native and HTTPS failure returns to a usable chooser with another-provider and Cancel actions.
8. No launch occurs without a direct user gesture.
9. Hebrew/English and RTL/LTR rendering remain correct.
10. Browser windows use the required security flags.

Physical-device validation is required for Android and iOS launch/fallback behavior; browser mocks alone cannot prove installed-app handling.

---

## 15. Out of Scope

- Implementing or modifying `FieldDetailsPanel.jsx`.
- Installing a Capacitor plugin or changing native manifests.
- Detecting installed apps in this documentation issue.
- Building an in-app routing engine or turn-by-turn navigation.
- Tracking live user location during navigation.
- Persisting a preferred provider.
- Adding app-store links.
- Changing location permission behavior.
- iOS signing, provisioning, or physical-device setup.

---

## 16. Decision Record

- **Approved providers:** Waze and Google Maps across supported Android/web contexts; Apple Maps on iOS/Apple contexts.
- **Approved default:** Launch the sole available supported native provider; show the chooser when multiple providers are available; use a supported HTTPS experience, with Google Maps preferred, when none are available.
- **Approved ordering:** Present providers in a platform-appropriate order; exact visual ordering is a UX decision that may evolve without a strategy change.
- **Approved privacy contract:** Destination coordinates only; origin is resolved by the provider.
- **Approved missing-app contract:** Native launch when available, HTTPS fallback, then another-provider choice; never strand the user.
- **Approved implementation split:** ISSUE-275 through ISSUE-278 implement individual providers and fallback behavior.

---

## 17. Definition of Done Checklist

- [x] Waze evaluated.
- [x] Google Maps evaluated.
- [x] Apple Maps evaluated.
- [x] Platform-specific provider support and flexible ordering policy defined.
- [x] Default-option decision defined.
- [x] User-choice behavior defined.
- [x] Missing-app and launch-failure behavior defined.
- [x] Destination-only privacy contract preserved.
- [x] Future implementation and test boundaries defined.
- [x] No application code, native configuration, dependencies, or runtime behavior changed.
