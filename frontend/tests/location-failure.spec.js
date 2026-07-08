import { test, expect } from '@playwright/test'
import {
  classifyLocationFailure,
  getLocationFailureMessage,
  isRecoverableLocationFailure,
  FAILURE_TYPES
} from '../src/utils/locationFailure'

test.describe('Location Failure Utility Unit Tests', () => {
  test('classifyLocationFailure handles permission denied/missing', () => {
    // 1. result object
    expect(classifyLocationFailure({ ok: false, error: 'permission_denied' })).toBe(FAILURE_TYPES.PERMISSION_MISSING)
    expect(classifyLocationFailure({ ok: false, error: 'unknown', needsSettings: true })).toBe(FAILURE_TYPES.PERMISSION_SETTINGS)
    
    // 2. browser error
    expect(classifyLocationFailure({ code: 1 })).toBe(FAILURE_TYPES.PERMISSION_MISSING)
    expect(classifyLocationFailure({ message: 'User denied geolocation' })).toBe(FAILURE_TYPES.PERMISSION_MISSING)
  })

  test('classifyLocationFailure handles timeout', () => {
    // 1. result object
    expect(classifyLocationFailure({ ok: false, error: 'timeout' })).toBe(FAILURE_TYPES.TIMEOUT)
    
    // 2. browser error
    expect(classifyLocationFailure({ code: 3 })).toBe(FAILURE_TYPES.TIMEOUT)
    expect(classifyLocationFailure({ message: 'Timeout expired' })).toBe(FAILURE_TYPES.TIMEOUT)
  })

  test('classifyLocationFailure handles GPS disabled/service unavailable', () => {
    // 1. result object
    expect(classifyLocationFailure({ ok: false, error: 'unavailable' })).toBe(FAILURE_TYPES.GPS_DISABLED)
    
    // 2. browser error
    expect(classifyLocationFailure({ code: 2 })).toBe(FAILURE_TYPES.GPS_DISABLED)
    expect(classifyLocationFailure({ message: 'Location provider disabled' })).toBe(FAILURE_TYPES.GPS_DISABLED)
  })

  test('classifyLocationFailure handles no signal/low signal', () => {
    expect(classifyLocationFailure({ code: 2, message: 'accuracy too low' })).toBe(FAILURE_TYPES.NO_SIGNAL)
    expect(classifyLocationFailure({ message: 'reception lost' })).toBe(FAILURE_TYPES.NO_SIGNAL)
    expect(classifyLocationFailure({ code: 2 }, { signalLost: true })).toBe(FAILURE_TYPES.NO_SIGNAL)
  })

  test('classifyLocationFailure handles stale cache', () => {
    expect(classifyLocationFailure({}, { isStale: true })).toBe(FAILURE_TYPES.STALE_CACHE)
    expect(classifyLocationFailure({ isFresh: false })).toBe(FAILURE_TYPES.STALE_CACHE)
  })

  test('classifyLocationFailure handles unsupported plugin/platform', () => {
    expect(classifyLocationFailure({ ok: false, error: 'unsupported' })).toBe(FAILURE_TYPES.UNSUPPORTED_PLATFORM)
    expect(classifyLocationFailure({ message: 'Capacitor native bridge failed to load' })).toBe(FAILURE_TYPES.UNSUPPORTED_PLATFORM)
  })

  test('classifyLocationFailure handles malformed location', () => {
    // 1. Missing coords fields
    expect(classifyLocationFailure({ latitude: undefined })).toBe(FAILURE_TYPES.UNKNOWN)
    // 2. Invalid lat
    expect(classifyLocationFailure({ latitude: 100, longitude: 30 })).toBe(FAILURE_TYPES.MALFORMED_LOCATION)
    // 3. Invalid lng
    expect(classifyLocationFailure({ latitude: 35, longitude: 200 })).toBe(FAILURE_TYPES.MALFORMED_LOCATION)
    // 4. Non-finite value
    expect(classifyLocationFailure({ latitude: NaN, longitude: 30 })).toBe(FAILURE_TYPES.MALFORMED_LOCATION)
    expect(classifyLocationFailure({ location: { latitude: 35, longitude: Infinity } })).toBe(FAILURE_TYPES.MALFORMED_LOCATION)
  })

  test('classifyLocationFailure handles unknown error / missing error', () => {
    expect(classifyLocationFailure(null)).toBe(FAILURE_TYPES.UNKNOWN)
    expect(classifyLocationFailure(undefined)).toBe(FAILURE_TYPES.UNKNOWN)
    expect(classifyLocationFailure({})).toBe(FAILURE_TYPES.UNKNOWN)
  })

  test('getLocationFailureMessage maps correctly', () => {
    expect(getLocationFailureMessage(FAILURE_TYPES.PERMISSION_MISSING)).toBe('map.permissionMissing')
    expect(getLocationFailureMessage(FAILURE_TYPES.GPS_DISABLED)).toBe('map.gpsUnavailable')
    expect(getLocationFailureMessage(FAILURE_TYPES.TIMEOUT)).toBe('map.timeoutWarning')
    expect(getLocationFailureMessage(FAILURE_TYPES.NO_SIGNAL)).toBe('map.noSignalWarning')
    expect(getLocationFailureMessage(FAILURE_TYPES.STALE_CACHE)).toBe('map.fallbackNotice')
    expect(getLocationFailureMessage(FAILURE_TYPES.MALFORMED_LOCATION)).toBe('map.genericFailureNotice')
    expect(getLocationFailureMessage(FAILURE_TYPES.UNSUPPORTED_PLATFORM)).toBe('map.genericFailureNotice')
    expect(getLocationFailureMessage(FAILURE_TYPES.UNKNOWN)).toBe('map.genericFailureNotice')
    expect(getLocationFailureMessage('INVALID')).toBe('map.genericFailureNotice')
  })

  test('isRecoverableLocationFailure classifies correctly', () => {
    expect(isRecoverableLocationFailure(FAILURE_TYPES.TIMEOUT)).toBe(true)
    expect(isRecoverableLocationFailure(FAILURE_TYPES.NO_SIGNAL)).toBe(true)
    expect(isRecoverableLocationFailure(FAILURE_TYPES.STALE_CACHE)).toBe(true)
    
    expect(isRecoverableLocationFailure(FAILURE_TYPES.PERMISSION_MISSING)).toBe(false)
    expect(isRecoverableLocationFailure(FAILURE_TYPES.GPS_DISABLED)).toBe(false)
    expect(isRecoverableLocationFailure(FAILURE_TYPES.UNSUPPORTED_PLATFORM)).toBe(false)
    expect(isRecoverableLocationFailure(FAILURE_TYPES.MALFORMED_LOCATION)).toBe(false)
    expect(isRecoverableLocationFailure(FAILURE_TYPES.UNKNOWN)).toBe(false)
  })
})
