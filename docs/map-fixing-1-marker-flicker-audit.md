# Map Fixing 1 — Marker Flicker/Disappearance Audit

**Issue:** תיקון מפה 1 (#797)
**Status:** Audit only — **no code fix was implemented in this issue.** The only change is this document.
**Date:** 2026-07-05
**Code under audit:** `frontend/src/pages/MapPage.jsx`, `frontend/src/api/fields.js` at main `042f01f`

---

## 1. Symptom

While panning/zooming the map on real mobile Android testing, field markers disappear, reappear, and flicker.

## 2. Reproduction steps

### Android (manual)
1. Install the debug APK (`gradlew assembleDebug` with Android Studio JBR Java), log in, open the map.
2. Pan one viewport-width in any direction, pause, then pan back.
3. Observe: fields in the area you return to are missing for a moment, then pop back in; markers that never left the viewport blink during the update.
4. To lengthen the windows: `chrome://inspect` → the app WebView → Network tab → throttling "Slow 3G", repeat step 2 — the "missing" window now lasts seconds.

### Desktop (controlled, scripted — used for the evidence below)
A Playwright script drives the real frontend (vite dev) against a stubbed `/fields/` backend that serves an 81-field synthetic grid **filtered by the requested bounds** (mirroring production behavior), executes 6 mouse-drag pans (out and back in each axis), and instruments:
- request count to `/fields/`,
- a `MutationObserver` on `.leaflet-marker-pane` counting every marker DOM node added/removed,
- a 100ms sampler counting markers visible inside the map viewport.

Run twice: `--delay 0` (fast network) and `--delay 1500` (slow network).

## 3. Evidence

### 3.1 Measurements

| Metric | Fast (0ms delay) | Slow (1500ms delay) |
|---|---|---|
| Pans performed | 6 | 6 |
| `/fields/` requests during pans | **6** (exactly 1 per settled pan) | **6** |
| Marker DOM nodes added | 710 | 692 |
| Marker DOM nodes removed | 710 | 692 |
| Unique fields in the whole dataset | 81 | 81 |
| Visible markers (min → max) | 27 → 81 | 27 → 81 |
| Duration of "missing markers" dips | ~0.3–1.5s per pan | **~2–4.5s per pan** (flat at 27–32 visible until the response lands, then jumps to 63–81) |

Dev-mode caveat: the app mounts under React `StrictMode` (`main.jsx`), which double-mounts in dev, so DOM-mutation counts are ~2× production. Normalized: ~350 adds/removes for 6 pans.

### 3.2 What the numbers mean

- The sum of all six response sizes is ~344 fields. Normalized marker churn (~350 adds + ~350 removes) means **every response tears down and rebuilds essentially the entire marker set**, not just the viewport delta. With stable per-field identity, adjacent-viewport pans (which overlap heavily) should have churned a few dozen nodes total.
- The visible-marker sampler shows the second, independent problem: after panning back to an already-visited area, only the overlap survives (27 markers) and the rest are **gone from React state entirely** until the next response arrives — the disappear/reappear the tester sees. Under throttling this window stretches to seconds, flat and reproducible.

## 4. Classification table

| # | Question | Verdict | Evidence |
|---|---|---|---|
| 1 | `setFields([])` or equivalent clearing during loading? | **Not confirmed** (does not happen) | `FieldLoader.loadFields` only toggles `onLoadingChange`; fields are set exclusively from response data. Sampler never hit 0. Errors keep previous fields. |
| 2 | New fetch removes existing fields before response returns? | **Not confirmed** (does not happen) | Fields persist until the response arrives. The removal happens *at* response time (see #7), not at request time. |
| 3 | Every pan/zoom triggers an API request? | **Confirmed** | `useMapEvents({ moveend })` + 250ms debounce → measured exactly 1 request per settled pan (6/6). Zoom also fires `moveend`. |
| 4 | Debounce too short? | **Not confirmed as a cause** | 250ms (`FIELD_LOAD_DEBOUNCE_MS`) is a reasonable settle window and produced no duplicate requests. It defines part of the empty-window length but is not why markers vanish. |
| 5 | Older responses overwrite newer ones? | **Not confirmed** (guarded), with one caveat | `FieldLoader.latestRequestId` discards stale responses (MapPage.jsx:228). `fields.js` also dedupes identical in-flight bounds. Caveat: `handleNotificationTarget` (MapPage.jsx:536) calls `getFields()` + `setFields` outside the guard and outside the fingerprint path — a minor unguarded race, only on notification-open. |
| 6 | Marker keys stable, based on `field.id`? | **CONFIRMED problem** | MapPage.jsx:474: `` key={`${field.id ?? field.name ?? 'field'}-${index}`} `` — the array **index** is part of the key. Any composition/order change re-keys same-id fields → React unmounts/remounts their `<Marker>`s. Measured: full-set rebuild per response. |
| 7 | Cache replaced instead of merged? | **CONFIRMED problem** | `handleFieldsLoaded` → `setFields(loadedFields)` replaces the whole array with the **bounds-filtered** response; `writeCachedFields(loadedFields)` overwrites the localStorage cache with the viewport-only subset. Fields just outside/behind the viewport are dropped and must be refetched to reappear. |
| 8 | Leaflet remounts markers unnecessarily? | **Confirmed (consequence of #6/#7)** | Remount = `L.Marker` removed + re-added; the divIcon's `<img>` DOM is recreated each time (repaint/decode flash — worst on Android WebView). ~350 remounts per 6 pans measured vs a few dozen expected. |
| 9 | Bounds/movement state updates causing React churn? | **Confirmed, minor contributor** | `isFieldsLoading` toggles per pan → two extra MapPage renders per pan. Mitigation already present: `fieldsFingerprint` skips `setFields` when data is identical. New field object identities per response also defeat `FieldMarker`'s `memo` when the array does change. |
| 10 | Only Android/mobile or also desktop? | **Confirmed cross-platform mechanism; Android device pass pending** | Fully reproduced on desktop Chromium (this audit). Android amplifiers: slower networks (longer empty windows), pinch-zoom gestures, WebView paint cost of recreated `<img>` markers. Originally reported on real Android. Instrumented on-device re-run recommended (device was disconnected during this audit — steps in §2). |
| 11 | Duplicate/excessive requests while moving? | **Not confirmed** (no duplicates) | 6 pans → 6 requests in both runs. Debounce + in-flight dedupe work. Every settled pan does cost one request (by design), but none are duplicated. |
| 12 | Reproducible with slow network throttling? | **Confirmed, amplified** | With a 1500ms response delay, visible markers sat at 27–32 for 2–4.5s windows before jumping to 63–81. Same mechanism, longer windows. |

## 5. Root cause hypothesis

Two independent, compounding causes — both at response-handling, neither in the request layer:

1. **Viewport replacement instead of merge (disappearance).** Each `moveend` response *replaces* `fields` with only the fields inside the new bounds. Anything the user pans away from is evicted from state, so panning back shows an empty area until the next fetch round-trips. The visible gap = debounce (250ms) + network latency; on mobile networks that is easily 0.5–3s. The localStorage cache is likewise overwritten with the viewport-only subset.
2. **Index-suffixed marker keys (flicker).** `key = id-index` re-keys almost every marker whenever the array composition shifts (which is every pan, because of cause 1). React unmounts and remounts the `<Marker>` components, Leaflet destroys and recreates the DOM (including the stadium `<img>`), and even markers that never changed blink.

Contributors, not causes: loading-state re-renders per pan (#9), fresh object identities defeating `memo` (#9), the unguarded `handleNotificationTarget` path (#5 caveat).

## 6. Most likely first fix

**Stabilize marker keys: `key={field.id}` (drop the `-${index}` suffix).** One line, zero behavioral risk (ids are unique — they come from the DB), and it eliminates the remount storm, i.e. the *flicker* of markers that stayed in view. It does not fix the disappearance of evicted fields — that is fix #2 below — but it is the highest confidence-to-effort ratio and should land first, alone, so its effect is measurable.

## 7. Ordered follow-up fixes (recommended for the next Map Fixing issues)

1. **Stable marker keys** — `key={field.id}` (§6).
2. **Merge bounds responses instead of replacing:** upsert incoming fields into the existing array by `id` (keep out-of-viewport fields; update overlapping ones). Add a simple staleness bound if memory is a concern (e.g. cap size or drop fields not seen for N minutes).
3. **Merge the localStorage cache the same way** so cold starts don't inherit a single-viewport snapshot.
4. **Route `handleNotificationTarget`'s `getFields()` result through the same merge/fingerprint path** as `FieldLoader` (closes the minor race and the second replacement site).
5. **Preserve field object identity when data is unchanged** (reuse previous object per id when the fingerprint of that field is equal) so `FieldMarker`'s `memo` actually prevents re-renders.
6. Optional polish: fetch padded bounds (~1.25–1.5× viewport) to pre-load edges; keep `isFieldsLoading` updates out of the marker subtree. Do **not** raise the debounce as a flicker fix — it lengthens the gap.

Fixes 1+2 together are expected to remove the user-visible symptom entirely; 3–6 are hardening.

## 8. Explicit scope statement

- **No code fix was implemented in this issue.** No marker design change, no map UX change, no backend change. The audit used a scratchpad-only instrumentation script (not committed) against unmodified application code.
- Remaining evidence gap: an instrumented run on the physical Samsung device (SM-S928B) **was attempted during this audit but blocked by an adb disconnect** (the device dropped off `adb devices` and did not re-enumerate after a server restart). Re-run it with the steps in §2 once the device is reconnected. The mechanism is proven and platform-independent, and the symptom was originally observed on real Android by the reporter.
