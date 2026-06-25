# ISSUE-138: Mobile Keyboard Interaction Specification

## Purpose

This specification defines how all mobile screens, forms, modals, bottom sheets, and panels must behave when the virtual keyboard opens. The virtual keyboard typically occupies 250–300px of vertical viewport height on mobile devices. Without a consistent standard, keyboard-related bugs recur across screens in different ways — inputs hidden behind the keyboard, submit buttons unreachable, modals clipping content, or scroll behavior breaking entirely.

This document establishes one unified keyboard behavior standard that all current and future screens must follow. It does not implement fixes. It defines the rules that future fixes must satisfy.

## Scope

This specification applies to:

* Login forms (Login mode inside `LoginPage.jsx`)
* Registration forms (Register mode inside `LoginPage.jsx`)
* Create Game modal (`OpenGameModal.jsx`)
* Add Field modal
* Notification preferences modal
* Admin forms and filters
* Search/autocomplete inputs (e.g., `CityAutocomplete`)
* Any bottom sheet or modal containing form controls (e.g., Field Details panel, Field Report modal)

## Core Decision

The project-wide keyboard behavior standard is:

1. **Forms must remain scrollable when the keyboard opens.** No form container may use `overflow: hidden` on mobile viewports.
2. **The page or container should scroll to keep the focused input visible.** Browser-native scroll-into-view behavior must not be blocked by CSS or layout constraints.
3. **Submit/cancel actions must remain reachable.** Users must be able to scroll to submit or close buttons while the keyboard is open.
4. **Mobile modals and bottom sheets must not rely on fixed non-scrollable layouts.** All modal and sheet content areas must support internal vertical scrolling.
5. **Do not manually animate the whole page unless required.** Prefer letting the browser handle viewport adjustment natively.
6. **Prefer scroll-safe containers over transform-based keyboard hacks.** CSS `overflow-y: auto` on bounded containers is the primary pattern. Avoid JavaScript-driven layout transforms to "push" content above the keyboard.
7. **Use viewport-safe max-height patterns with `100dvh` where appropriate.** Static `100vh` is unreliable on mobile browsers (iOS Safari address bar, keyboard resize). Use `100dvh` or let height grow naturally with scroll enabled.
8. **Use safe-area bottom padding together with keyboard-safe scrolling.** Bottom-anchored actions must respect both `env(safe-area-inset-bottom)` (per ISSUE-137) and keyboard visibility constraints.

## Scenario Matrix

| Scenario | Expected Behavior | Scroll Container | Submit/Cancel Behavior | Notes |
| :--- | :--- | :--- | :--- | :--- |
| Full-page form | Page scrolls naturally | document/body or page container | Button remains reachable after scrolling | Login / Register |
| Modal form | Modal content scrolls internally | modal content container | Button remains reachable inside modal | Create Game / Add Field |
| Bottom sheet form | Sheet content scrolls internally | sheet body | Bottom actions remain above safe area or reachable by scroll | Field Details |
| Search/autocomplete | Input remains visible; suggestions avoid keyboard clipping | local dropdown or modal body | Selection remains tappable | CityAutocomplete |
| Admin filters | Page or admin panel scrolls | page container | Apply/reset controls remain reachable | Admin Panel |
| Long form | Focused input remains visible; errors scroll into view | form container | Submit reachable after last field | Registration / Create Game |
| Error after submit | Error visible without dismissing keyboard where possible | form/modal body | Error near field when possible | Validation |

## Required Keyboard Behavior Rules

### 1. Focus Visibility

* When an input receives focus, it must not be hidden behind the keyboard.
* The user must be able to scroll until the focused input is visible.
* Avoid parent containers with `overflow: hidden` around mobile forms unless an inner scroll container exists.
* Avoid fixed-height layouts that trap focused fields. Containers must either grow naturally or scroll internally.

### 2. Submit and Cancel Reachability

* Submit/cancel buttons must remain reachable while the keyboard is open.
* If buttons are at the bottom of a form or modal, the container must scroll enough to expose them.
* Sticky bottom buttons must include safe-area and keyboard-aware spacing.
* Close buttons (modal `x`, panel close) must remain reachable and have at least a 44px hit target (per ISSUE-136 design guide).

### 3. Modal Keyboard Behavior

* Mobile modals must use max-height relative to viewport using dynamic viewport units.
* Modal content must allow `overflow-y: auto`.
* Modal padding must include safe-area bottom spacing (per ISSUE-137).
* The modal must not be vertically centered in a way that clips content when the keyboard opens. Vertical centering via `place-items: center` on the backdrop is acceptable only if the modal itself has bounded height and internal scroll.
* For long modal forms, field content and actions must be scrollable.

Recommended pattern:

```css
max-height: calc(100dvh - 32px - var(--safe-area-top) - var(--safe-area-bottom));
overflow-y: auto;
padding-bottom: calc(16px + var(--safe-area-bottom));
```

Actual implementation may vary by component, but behavior must match this specification.

### 4. Bottom Sheet Keyboard Behavior

* Bottom sheets should remain anchored at their position but internally scrollable.
* Dynamic content (e.g., expanding participant lists, game time grids) must not push close/action buttons out of reach.
* Bottom padding must respect `env(safe-area-inset-bottom)`.
* If the sheet contains inputs (e.g., future inline search or filter), it must have a scrollable body area.

### 5. Autocomplete / Dropdown Keyboard Behavior

* Suggestions must not be hidden behind the keyboard.
* Suggestions should have a max-height based on available viewport space, not a static pixel value that assumes full-height availability.
* Selection targets must remain at least 44px high (per ISSUE-136 touch target standard).
* Touch dismissal should not rely only on `mousedown`; future implementation should support `pointerdown` or `touchstart` for touch-safe outside-click behavior (related to `NTMOB-004`).
* If space is limited, suggestions may collapse into an internal scrollable list.

### 6. Error and Validation Behavior

* Field-level errors should appear near the relevant field when possible (inline validation).
* Global errors must be visible after submit, positioned near the submit button or at the top of the form.
* On submit failure, the first invalid field or error area should be reachable without keyboard dismissal.
* Error text must wrap safely in Hebrew RTL without causing horizontal overflow.

### 7. iOS Safari Rules

* Mobile inputs must use at least `font-size: 16px` to avoid iOS Safari auto-zoom on focus (relates to `CGMOB-002`, `ADMOB-003`).
* Avoid relying only on `100vh`; prefer `100dvh` where supported. The `100vh` unit on iOS Safari includes the address bar height, which causes content to extend below the visible viewport.
* Always combine viewport limits with scrollable containers.
* Account for safe areas and home indicator (per ISSUE-137).
* Avoid native `window.prompt` and `window.confirm` for important form workflows. Native dialogs freeze the rendering thread, lack styling control, and display in English regardless of app language (relates to `ADMOB-001`, `GDMOB-003`).

### 8. Android Chrome Rules

* Android Chrome may resize the visual viewport when the keyboard opens (the layout viewport stays the same, but the visual viewport shrinks). Layouts must tolerate this reduced visible height.
* `100vh` on Android Chrome typically refers to the layout viewport, not the visual viewport. `100dvh` adjusts dynamically.
* Floating or sticky controls should not cover the focused input when viewport height changes.
* Scrolling must remain possible while the keyboard is open. Containers must not have `overflow: hidden` that blocks scroll on resize.

### 9. RTL Hebrew Rules

* Keyboard behavior must not break RTL alignment. Opening the keyboard must not shift text direction or misalign form labels.
* Long Hebrew labels and error messages must wrap without horizontal overflow.
* Numeric fields should use `inputmode="numeric"` where appropriate (e.g., player counts in Create Game). This displays a clean numeric keypad and avoids Hebrew keyboard toggling (relates to `CGMOB-005`).
* Dates and times must remain readable inside RTL forms. Date/time pickers should use native browser pickers which handle RTL natively.

## Implementation Standards For Future Fixes

Future keyboard-related fixes must:

* Reference this spec and the relevant finding ID (e.g., "Resolves CGMOB-001 per mobile-keyboard-interaction-spec.md").
* Preserve desktop behavior. Keyboard-related CSS changes must be scoped to mobile viewports using media queries or container queries.
* Avoid unrelated refactors. Each fix must target a specific finding or screen.
* Prefer container scrolling over JavaScript hacks. Use `overflow-y: auto` with bounded height rather than JavaScript-driven `scrollIntoView` calls or `window.scrollTo` hacks.
* Avoid global layout changes unless necessary. A modal scroll fix should not change the page-level scroll behavior.
* Include responsive validation notes in PR descriptions, documenting which emulated viewports and device profiles were tested.
* Pass build and lint checks. `npm run build` and ESLint must complete without new errors.
* Document remaining browser-specific risks if a fix cannot cover all browsers uniformly.

## Screen-Specific Requirements

### Login

* Login form must remain fully reachable when the keyboard opens on all device classes.
* Password field and submit button must not be hidden behind the keyboard.
* Error messages (`.login-error`) must remain visible after failed authentication.
* The `min-height: 100vh` on `.login-page` with `place-items: center` may push content above the viewport when the keyboard opens on short screens. Future fixes should ensure the page scrolls to keep the focused field visible.
* Related findings: `ML-LOGIN-001`.

### Registration

* The long registration form (6 fields: full name, username, email, phone, password, confirm password) must scroll safely on all device classes.
* The final submit button ("Create account") must remain reachable by scrolling while the keyboard is open.
* Validation errors must be near their associated fields or reachable after submit.
* The `min-height: 100vh` centering layout causes the form to overflow the viewport top on small screens (360x640) when the keyboard opens.
* Related findings: `ML-REGISTER-001`, `ML-REGISTER-002`, `ML-REGISTER-003`.

### Create Game

* Create Game modal (`.open-game-modal`) must scroll internally when the keyboard opens.
* Date, time, and player count fields must remain reachable with the keyboard open.
* The submit button must remain reachable via scrolling.
* This specification directly supports the future fix for `CGMOB-001`, the only Critical finding in the mobile audit.
* The modal must have `max-height` constraints and `overflow-y: auto` applied.
* Related findings: `CGMOB-001`, `CGMOB-002`, `CGMOB-004`, `CGMOB-005`.

### Add Field

* Add Field modal (`.add-field-modal`) must scroll internally when the keyboard opens.
* Submit/cancel actions must remain reachable while typing field name, notes, or address.
* Long address or field name input content must not break layout; text should wrap within the input bounds.
* The location picker map inside the modal must not interfere with form scroll behavior.

### Notifications Preferences

* City autocomplete input must remain usable with the keyboard open.
* The suggestion list must not be clipped behind the keyboard. Max-height should be calculated relative to available viewport space.
* The Save button must remain reachable by scrolling within the notifications modal.
* Related findings: `NTMOB-005`.

### Admin Panel

* Filter and search fields must remain usable with the keyboard open.
* Table actions must not be covered by sticky or floating elements when the viewport shrinks due to keyboard.
* Native `window.prompt`-based workflows (user moderation reason input) should be replaced in future remediation with custom React modals that follow this keyboard spec.
* Related findings: `ADMOB-001`, `ADMOB-003`.

## Manual Validation Checklist

For each screen with form inputs, verify the following:

- [ ] Open screen on 375x667 viewport (Small iPhone).
- [ ] Focus the first input field.
- [ ] Focus a middle input field (if the form has 3+ fields).
- [ ] Focus the last input field.
- [ ] Verify the focused input remains visible and not hidden behind the keyboard.
- [ ] Verify the page or modal can scroll while the keyboard is open.
- [ ] Verify the submit button remains reachable by scrolling.
- [ ] Verify the cancel/close button remains reachable.
- [ ] Verify error messages remain visible after an invalid submit attempt.
- [ ] Verify no horizontal overflow occurs.
- [ ] Repeat on 390x844 (iPhone 12/13/14) viewport.
- [ ] Repeat on 393x852 (iPhone 14/15 Pro) viewport.
- [ ] Repeat on 430x932 (iPhone Pro Max) viewport.
- [ ] Repeat on Android Chrome profile if available.

## Known Findings Addressed By This Spec

This specification supports but does not fix the following findings:

| Finding ID | Screen | Area | Relevance |
| :--- | :--- | :--- | :--- |
| `CGMOB-001` | Create Game | Keyboard / Scrolling | Critical — modal lacks scroll and height constraint when keyboard opens |
| `CGMOB-004` | Create Game | Validation | Global errors hidden under keyboard after submit |
| `CGMOB-005` | Create Game | Numeric Input | Alphanumeric keyboard shown for numeric fields |
| `NTMOB-005` | Notifications | Autocomplete | Suggestions clipped by keyboard on short screens |
| `ADMOB-001` | Admin Panel | Forms | Native `window.prompt` freezes thread and lacks keyboard control |
| `ML-LOGIN-001` | Login | Keyboard / Layout | Submit button below viewport when first field is focused |
| `ML-REGISTER-001` | Registration | Form Layout / Scroll | Submit pushed out of view during focus |
| `CGMOB-002` | Create Game | iOS Auto-Zoom | Input font-size triggers Safari auto-zoom |
| `ADMOB-003` | Admin Panel | iOS Auto-Zoom | Admin input font-size triggers Safari auto-zoom |

## Non-Goals

* This issue does **not** fix keyboard bugs.
* This issue does **not** change CSS.
* This issue does **not** modify React components.
* This issue does **not** implement `CGMOB-001`.
* This issue does **not** change frontend, backend, database, schema, or configuration files.
* This issue defines the standard that future fixes must follow.

## Final Verdict

Keyboard-related remediation can now proceed using this specification. All future keyboard fix PRs must reference this document and validate against the manual checklist defined above.
