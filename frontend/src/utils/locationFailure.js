export const FAILURE_TYPES = {
  GPS_DISABLED: 'GPS_DISABLED',
  NO_SIGNAL: 'NO_SIGNAL',
  TIMEOUT: 'TIMEOUT',
  PERMISSION_MISSING: 'PERMISSION_MISSING',
  PERMISSION_SETTINGS: 'PERMISSION_SETTINGS',
  STALE_CACHE: 'STALE_CACHE',
  UNSUPPORTED_PLATFORM: 'UNSUPPORTED_PLATFORM',
  MALFORMED_LOCATION: 'MALFORMED_LOCATION',
  UNKNOWN: 'UNKNOWN',
}

export function classifyLocationFailure(errorOrResult, context = {}) {
  if (!errorOrResult) {
    return FAILURE_TYPES.UNKNOWN
  }

  // 1. Check for malformed location result
  const hasCoordinates =
    (errorOrResult.latitude !== undefined || errorOrResult.longitude !== undefined) ||
    (errorOrResult.location && (errorOrResult.location.latitude !== undefined || errorOrResult.location.longitude !== undefined))

  if (hasCoordinates) {
    const loc = errorOrResult.location || errorOrResult
    const lat = Number(loc.latitude)
    const lng = Number(loc.longitude)
    if (
      !Number.isFinite(lat) ||
      !Number.isFinite(lng) ||
      lat < -90 ||
      lat > 90 ||
      lng < -180 ||
      lng > 180
    ) {
      return FAILURE_TYPES.MALFORMED_LOCATION
    }
  }

  // 2. Check result objects from locationService (e.g. { ok: false, error: '...' })
  if (errorOrResult.ok === false) {
    const err = errorOrResult.error
    if (errorOrResult.needsSettings) {
      return FAILURE_TYPES.PERMISSION_SETTINGS
    }
    if (err === 'permission_denied') {
      return FAILURE_TYPES.PERMISSION_MISSING
    }
    if (err === 'timeout') {
      return FAILURE_TYPES.TIMEOUT
    }
    if (err === 'unavailable') {
      return FAILURE_TYPES.GPS_DISABLED
    }
    if (err === 'unsupported') {
      return FAILURE_TYPES.UNSUPPORTED_PLATFORM
    }
  }

  // 3. Check browser GeolocationPositionError or Capacitor Error
  const code = errorOrResult.code
  const message = String(errorOrResult.message ?? '')

  if (context.needsSettings || errorOrResult.needsSettings) {
    return FAILURE_TYPES.PERMISSION_SETTINGS
  }
  if (code === 1 || /denied/i.test(message) || /permission/i.test(message)) {
    return FAILURE_TYPES.PERMISSION_MISSING
  }
  if (code === 3 || /timeout/i.test(message)) {
    return FAILURE_TYPES.TIMEOUT
  }
  if (/signal|reception|accuracy/i.test(message) || context.signalLost) {
    return FAILURE_TYPES.NO_SIGNAL
  }
  if (code === 2 || /unavailable/i.test(message) || /disabled/i.test(message) || /gps/i.test(message)) {
    return FAILURE_TYPES.GPS_DISABLED
  }

  // 4. Check for stale cache
  if (context.isStale || errorOrResult.isFresh === false) {
    return FAILURE_TYPES.STALE_CACHE
  }

  // 5. Plugin / native bridge failure
  if (/plugin|bridge|native/i.test(message)) {
    return FAILURE_TYPES.UNSUPPORTED_PLATFORM
  }

  return FAILURE_TYPES.UNKNOWN
}

export function getLocationFailureMessage(failureType) {
  const keyMap = {
    [FAILURE_TYPES.PERMISSION_MISSING]: 'map.permissionMissing',
    [FAILURE_TYPES.PERMISSION_SETTINGS]: 'map.permissionSettings',
    [FAILURE_TYPES.GPS_DISABLED]: 'map.gpsUnavailable',
    [FAILURE_TYPES.TIMEOUT]: 'map.timeoutWarning',
    [FAILURE_TYPES.NO_SIGNAL]: 'map.noSignalWarning',
    [FAILURE_TYPES.STALE_CACHE]: 'map.fallbackNotice',
    [FAILURE_TYPES.UNSUPPORTED_PLATFORM]: 'map.genericFailureNotice',
    [FAILURE_TYPES.MALFORMED_LOCATION]: 'map.genericFailureNotice',
    [FAILURE_TYPES.UNKNOWN]: 'map.genericFailureNotice',
  }
  return keyMap[failureType] || 'map.genericFailureNotice'
}

export function isRecoverableLocationFailure(failureType) {
  return [
    FAILURE_TYPES.TIMEOUT,
    FAILURE_TYPES.NO_SIGNAL,
    FAILURE_TYPES.STALE_CACHE,
  ].includes(failureType)
}
