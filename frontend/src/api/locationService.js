import { Capacitor } from '@capacitor/core'
import { checkExistingPermission, requestCurrentLocation } from './locationPermission'

const FRESHNESS_MS = 60000

const ERROR = {
  PERMISSION_DENIED: 'permission_denied',
  UNAVAILABLE: 'unavailable',
  TIMEOUT: 'timeout',
  UNSUPPORTED: 'unsupported',
  UNKNOWN: 'unknown',
}

let cachedLocation = null

function mapError(permissionStatus) {
  if (permissionStatus === 'denied' || permissionStatus === 'settings') {
    return ERROR.PERMISSION_DENIED
  }
  if (permissionStatus === 'unavailable') return ERROR.UNAVAILABLE
  if (permissionStatus === 'unsupported') return ERROR.UNSUPPORTED
  return ERROR.UNKNOWN
}

function resolveSource() {
  return Capacitor.isNativePlatform() ? 'native' : 'web'
}

async function resolvePermissionState() {
  try {
    const { state } = await checkExistingPermission()
    return state
  } catch {
    return 'unknown'
  }
}

function normalize(coords, permissionState) {
  const now = Date.now()
  const timestamp = coords.timestamp ?? now
  const ageMs = now - timestamp

  return {
    latitude: coords.latitude,
    longitude: coords.longitude,
    accuracyMeters: coords.accuracy ?? null,
    altitude: coords.altitude ?? null,
    altitudeAccuracy: coords.altitudeAccuracy ?? null,
    heading: coords.heading ?? null,
    speed: coords.speed ?? null,
    timestamp,
    source: resolveSource(),
    permissionState,
    ageMs: Math.max(0, ageMs),
    isFresh: ageMs < FRESHNESS_MS,
  }
}

export async function getCurrentLocation({ highAccuracy = false, maxAge = FRESHNESS_MS } = {}) {
  if (cachedLocation && (Date.now() - cachedLocation.timestamp) < maxAge) {
    const ageMs = Date.now() - cachedLocation.timestamp
    return {
      ok: true,
      location: { ...cachedLocation, ageMs, isFresh: ageMs < FRESHNESS_MS },
    }
  }

  return refreshLocation({ highAccuracy })
}

export async function refreshLocation({ highAccuracy = false } = {}) {
  const result = await requestCurrentLocation({ highAccuracy })

  if (result.status !== 'granted') {
    const permissionState = result.status === 'settings' ? 'denied' : await resolvePermissionState()
    return {
      ok: false,
      error: mapError(result.status),
      permissionState,
      needsSettings: result.status === 'settings',
    }
  }

  const permissionState = 'granted'
  const location = normalize(result.coords, permissionState)
  cachedLocation = location
  return { ok: true, location }
}

export function getLastKnownLocation() {
  if (!cachedLocation) return null
  const ageMs = Date.now() - cachedLocation.timestamp
  return { ...cachedLocation, ageMs, isFresh: ageMs < FRESHNESS_MS }
}

export function clearLocationCache() {
  cachedLocation = null
}
