import { Capacitor } from '@capacitor/core'

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

let plugin = null
let denialCount = 0

function isNative() {
  return Capacitor.isNativePlatform() && Capacitor.isPluginAvailable('Geolocation')
}

async function loadPlugin() {
  if (plugin) {
    return plugin
  }

  if (!isNative()) {
    return null
  }

  // Same pattern as nativeGoogleAuth.js: guard on isPluginAvailable up front
  // so we never invoke an unregistered plugin proxy (that path re-enters its
  // own platform loader in a timer-starving microtask loop).
  const module = await import('@capacitor/geolocation')
  plugin = module.Geolocation
  return plugin
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

async function getPositionNative(highAccuracy) {
  const geolocation = await loadPlugin()
  if (!geolocation) {
    return RESULT.unsupported()
  }

  try {
    const position = await geolocation.getCurrentPosition({
      enableHighAccuracy: Boolean(highAccuracy),
      timeout: 10000,
      maximumAge: 60000,
    })
    recordOutcome('granted')
    return RESULT.granted({
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
      accuracy: Number.isFinite(position.coords.accuracy) ? position.coords.accuracy : null,
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
        resolve(
          RESULT.granted({
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
            accuracy: Number.isFinite(position.coords.accuracy)
              ? position.coords.accuracy
              : null,
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
    const geolocation = await loadPlugin()
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
