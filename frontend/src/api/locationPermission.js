import { Capacitor } from '@capacitor/core'
import { Geolocation } from '@capacitor/geolocation'

// Central location-permission service (ISSUE-255, Android slice).
// All callers must route location acquisition through here — the auto-request
// on MapPage mount is intentionally gone, per docs/location-permission-strategy.md
// (permission-at-point-of-need). This file is the only place that talks to
// @capacitor/geolocation or navigator.geolocation.
//
// Denial-count heuristic: Android and web give no reliable "permanently
// denied" signal from a single call. We count consecutive denials from the
// same runtime and, from the second onward, surface a settings-guidance
// state so the UI can stop nudging the user through the OS prompt and
// instead point them at the app's location settings. This is a heuristic,
// not a definitive OS check — the docs pledge nothing stronger.

const REPEAT_DENIAL_THRESHOLD = 2

const RESULT = {
  granted: (coords) => ({ status: 'granted', coords }),
  denied: () => ({ status: 'denied' }),
  settings: () => ({ status: 'settings' }),
  unavailable: () => ({ status: 'unavailable' }),
  unsupported: () => ({ status: 'unsupported' }),
}

let denialCount = 0

function isNative() {
  return Capacitor.isNativePlatform()
}

// MUST stay synchronous — never await the plugin proxy or return it from an
// async function. The Capacitor proxy answers every property access with a
// native method call, including `.then`, so promise assimilation on it
// invokes a phantom native "then" that never resolves.
function loadPlugin() {
  if (!isNative()) {
    return null
  }

  return Geolocation
}

function isDenialError(error) {
  // Native plugin uses string codes; browser uses numeric PERMISSION_DENIED=1.
  // Any error message mentioning "denied" is treated as a denial as a last
  // resort — the Android plugin's exact code has varied across versions.
  const code = error?.code
  if (code === 1) return true
  if (typeof code === 'string' && /denied/i.test(code)) return true
  const message = String(error?.message ?? '')
  return /denied/i.test(message)
}

function recordOutcome(outcome) {
  if (outcome === 'granted') {
    denialCount = 0
    return
  }
  if (outcome === 'denied') {
    denialCount += 1
  }
}

function currentGuidance() {
  return denialCount >= REPEAT_DENIAL_THRESHOLD ? 'settings' : 'denied'
}

// Reset only for tests / callers that want to explicitly start over
// (e.g. a fresh "try again" affordance in the future).
export function resetPermissionState() {
  denialCount = 0
}

function nativeStatusIsGranted(status) {
  return status?.location === 'granted' || status?.coarseLocation === 'granted'
}

// Safety guard against native-bridge hangs: a plugin call that never
// resolves would otherwise wedge the caller forever (seen on this codebase
// when a plugin proxy is awaited incorrectly). Timeouts are per-call because
// legitimate durations differ wildly — see the call sites.
async function withTimeout(promise, label, timeoutMs) {
  let timeoutId
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timeoutId = setTimeout(() => {
          reject(new Error(`Timeout while waiting for ${label}`))
        }, timeoutMs)
      }),
    ])
  } finally {
    clearTimeout(timeoutId)
  }
}

// checkPermissions is a passive lookup — anything beyond a few seconds is a
// wedged bridge. requestPermissions waits on the user reading the OS dialog,
// so it only gets a long hang guard. getCurrentPosition must outlast the
// plugin's own 10s positionOptions timeout or we'd preempt real fixes.
const CHECK_PERMISSIONS_TIMEOUT_MS = 8000
const REQUEST_PERMISSIONS_TIMEOUT_MS = 120000
const GET_POSITION_TIMEOUT_MS = 15000

async function getPositionNative(highAccuracy) {
  const geolocation = loadPlugin()
  if (!geolocation) {
    return RESULT.unsupported()
  }

  // Explicitly check → request permissions before getCurrentPosition. The
  // Android Capacitor Geolocation plugin does not raise the OS prompt from
  // getCurrentPosition alone; we must call requestPermissions() to surface
  // the native dialog on user action.
  let permitted = false
  try {
    const status = await withTimeout(
      geolocation.checkPermissions(),
      'checkPermissions',
      CHECK_PERMISSIONS_TIMEOUT_MS,
    )
    permitted = nativeStatusIsGranted(status)
  } catch {
    // Fall through to an explicit request if the passive check errors.
  }

  if (!permitted) {
    try {
      const requested = await withTimeout(
        geolocation.requestPermissions(),
        'requestPermissions',
        REQUEST_PERMISSIONS_TIMEOUT_MS,
      )
      permitted = nativeStatusIsGranted(requested)
    } catch {
      permitted = false
    }
  }

  if (!permitted) {
    recordOutcome('denied')
    return currentGuidance() === 'settings' ? RESULT.settings() : RESULT.denied()
  }

  try {
    const position = await withTimeout(
      geolocation.getCurrentPosition({
        enableHighAccuracy: Boolean(highAccuracy),
        timeout: 10000,
        maximumAge: 60000,
      }),
      'getCurrentPosition',
      GET_POSITION_TIMEOUT_MS,
    )
    recordOutcome('granted')
    const c = position.coords
    return RESULT.granted({
      latitude: c.latitude,
      longitude: c.longitude,
      accuracy: Number.isFinite(c.accuracy) ? c.accuracy : null,
      altitude: Number.isFinite(c.altitude) ? c.altitude : null,
      altitudeAccuracy: Number.isFinite(c.altitudeAccuracy) ? c.altitudeAccuracy : null,
      heading: Number.isFinite(c.heading) ? c.heading : null,
      speed: Number.isFinite(c.speed) ? c.speed : null,
      timestamp: position.timestamp ?? Date.now(),
    })
  } catch (error) {
    if (isDenialError(error)) {
      recordOutcome('denied')
      return currentGuidance() === 'settings' ? RESULT.settings() : RESULT.denied()
    }
    return RESULT.unavailable()
  }
}

function getPositionWeb(highAccuracy) {
  return new Promise((resolve) => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      resolve(RESULT.unsupported())
      return
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        recordOutcome('granted')
        const c = position.coords
        resolve(
          RESULT.granted({
            latitude: c.latitude,
            longitude: c.longitude,
            accuracy: Number.isFinite(c.accuracy) ? c.accuracy : null,
            altitude: Number.isFinite(c.altitude) ? c.altitude : null,
            altitudeAccuracy: Number.isFinite(c.altitudeAccuracy) ? c.altitudeAccuracy : null,
            heading: Number.isFinite(c.heading) ? c.heading : null,
            speed: Number.isFinite(c.speed) ? c.speed : null,
            timestamp: position.timestamp ?? Date.now(),
          }),
        )
      },
      (error) => {
        if (isDenialError(error)) {
          recordOutcome('denied')
          resolve(currentGuidance() === 'settings' ? RESULT.settings() : RESULT.denied())
          return
        }
        resolve(RESULT.unavailable())
      },
      {
        enableHighAccuracy: Boolean(highAccuracy),
        timeout: 10000,
        maximumAge: 60000,
      },
    )
  })
}

// Request a one-shot fix. Never prompts on module load or on component
// mount — the caller decides when this runs (a button press, a save).
// Approximate/coarse fixes are accepted and returned unchanged: this slice
// does not differentiate rendering, per ISSUE-255 scope.
export async function requestCurrentLocation({ highAccuracy = false } = {}) {
  if (isNative()) {
    return getPositionNative(highAccuracy)
  }
  return getPositionWeb(highAccuracy)
}

// Non-invasive re-check for app resume: returns whether we still hold a
// grant. Uses the plugin's checkPermissions on native (no prompt), and
// resolves to 'granted' on web whenever the browser API is present, since
// browsers surface revocation only on the next call.
export async function checkExistingPermission() {
  if (isNative()) {
    const geolocation = loadPlugin()
    if (!geolocation) {
      return { state: 'unsupported' }
    }
    try {
      const status = await geolocation.checkPermissions()
      const level = status?.location ?? status?.coarseLocation ?? 'prompt'
      if (level === 'granted') {
        return { state: 'granted' }
      }
      if (level === 'denied') {
        return { state: 'denied' }
      }
      return { state: 'prompt' }
    } catch {
      return { state: 'unsupported' }
    }
  }

  if (typeof navigator === 'undefined' || !navigator.geolocation) {
    return { state: 'unsupported' }
  }
  return { state: 'granted' }
}
