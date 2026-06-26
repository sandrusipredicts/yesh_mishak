# Responsive UI QA Checklist

Use this checklist when testing responsive layout across supported viewports.

## Target Viewports

| Width | Height | Device Class | Support Level |
| :--- | :--- | :--- | :--- |
| 320 | 568 | iPhone SE (1st gen) | Primary |
| 360 | 640 | Small Android | Primary |
| 390 | 844 | Standard iPhone / Medium Android | Primary |
| 412 | 915 | Large Android | Secondary |
| 430 | 932 | Pro Max iPhone | Secondary |
| 768 | 1024 | iPad / Android Tablet | Best-Effort |
| 1024 | 768 | Tablet Landscape | Best-Effort |
| 1280 | 800 | Laptop | Desktop |
| 1440 | 900 | Desktop | Desktop |

## Per-Viewport Checks

For each viewport, verify:

### Layout Integrity
- [ ] No horizontal scrollbar on any page
- [ ] Page fills viewport height (no white gap at bottom)
- [ ] Content does not overflow behind browser chrome on real devices

### Login / Register
- [ ] Login form centered and fully visible
- [ ] Register form scrollable if taller than viewport
- [ ] Submit button reachable (visible or via scroll)
- [ ] Input fields are tappable (min 44px touch target)
- [ ] Hebrew labels right-aligned (RTL)
- [ ] Password hint text wraps cleanly

### Map Page
- [ ] Map fills viewport
- [ ] Auth toolbar visible, buttons single-line
- [ ] Floating action buttons visible (bell, settings, add field)
- [ ] Floating buttons do not overlap toolbar
- [ ] Leaflet zoom controls visible and not clipped
- [ ] Bottom controls above browser chrome on real devices
- [ ] No horizontal overflow

### Modals (Notifications, Add Field, Open Game, Navigation, Confirm, Report)
- [ ] Modal fits on screen (width and height)
- [ ] Internal scroll works when content exceeds viewport
- [ ] Close button (X) visible and tappable
- [ ] Submit/save/action buttons reachable
- [ ] Modal does not extend behind browser chrome
- [ ] Backdrop covers full screen

### Field Details Panel
- [ ] Panel fits viewport width
- [ ] Panel scrolls vertically for long content
- [ ] Close button visible
- [ ] Join/leave/close game buttons reachable
- [ ] Panel does not overlap floating buttons when open

### My Games
- [ ] Back-to-map link visible
- [ ] Game cards fit viewport width
- [ ] Empty/error/loading states render cleanly
- [ ] No horizontal overflow

### Notifications Inbox
- [ ] Notification list scrolls
- [ ] Mark-all-as-read button reachable
- [ ] Unread badge visible
- [ ] No horizontal overflow

### Admin Page
- [ ] Page loads on tablet/desktop
- [ ] Sidebar tabs wrap or scroll horizontally on mobile
- [ ] Tables scroll horizontally within their container (not the whole page)
- [ ] No page-level horizontal overflow
- [ ] Stats cards stack on mobile

### Floating Action Buttons
- [ ] All buttons tappable (min 44px)
- [ ] Buttons respect safe-area insets
- [ ] Buttons work in RTL layout
- [ ] Buttons do not cover modal close buttons
- [ ] Bottom button not clipped by browser chrome

### Hebrew / RTL
- [ ] Text wraps cleanly (no overflow)
- [ ] Labels right-aligned
- [ ] Buttons text does not overflow
- [ ] Long Hebrew game names wrap or truncate gracefully
- [ ] No left/right CSS where logical properties are needed

### Landscape Smoke (667x375, 915x412)
- [ ] Map loads and controls visible
- [ ] Login form scrollable, submit reachable
- [ ] Notifications modal opens and scrolls
- [ ] No horizontal overflow

## Automated Test Coverage

The following Playwright test suites cover responsive behavior:
- `tests/floating-buttons.spec.js` (3 tests)
- `tests/mobile-scrolling.spec.js` (6 tests)
- `tests/small-android-layout.spec.js` (7 tests)
- `tests/modal-usability.spec.js` (2 tests)
