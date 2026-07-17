import assert from 'node:assert/strict'
import { afterEach, describe, test } from 'node:test'

import {
  checkExistingPermission,
  requestCurrentLocation,
  resetPermissionState,
} from '../src/api/locationPermission.js'

// @capacitor/geolocation's Android implementation rejects checkPermissions()/
// requestPermissions() with this exact error before the permission dialog is
// ever shown when device location services (GPS/network location) are off —
// see GeolocationErrors.LOCATION_DISABLED in the installed plugin's Android
// source. Every mock below that simulates "services disabled" reproduces
// this precisely so the test exercises the real signal, not an invented one.
const SERVICES_DISABLED_ERROR = Object.assign(
  new Error('Location services are not enabled.'),
  { code: 'OS-PLUG-GLOC-0007' },
)

function createGeolocation({
  checkPermissions,
  requestPermissions,
  getCurrentPosition,
} = {}) {
  const calls = { checkPermissions: 0, requestPermissions: 0, getCurrentPosition: 0 }
  return {
    calls,
    plugin: {
      async checkPermissions() {
        calls.checkPermissions += 1
        if (checkPermissions) return checkPermissions()
        return { location: 'granted' }
      },
      async requestPermissions() {
        calls.requestPermissions += 1
        if (requestPermissions) return requestPermissions()
        return { location: 'granted' }
      },
      async getCurrentPosition() {
        calls.getCurrentPosition += 1
        if (getCurrentPosition) return getCurrentPosition()
        return { coords: { latitude: 1, longitude: 2 }, timestamp: 123 }
      },
    },
  }
}

afterEach(() => {
  resetPermissionState()
})

describe('checkExistingPermission', () => {
  test('granted native status maps to granted', async () => {
    const { plugin } = createGeolocation({
      checkPermissions: () => ({ location: 'granted' }),
    })
    const result = await checkExistingPermission({ geolocation: plugin })
    assert.deepStrictEqual(result, { state: 'granted' })
  })

  test('denied native status maps to denied', async () => {
    const { plugin } = createGeolocation({
      checkPermissions: () => ({ location: 'denied' }),
    })
    const result = await checkExistingPermission({ geolocation: plugin })
    assert.deepStrictEqual(result, { state: 'denied' })
  })

  test('prompt and prompt-with-rationale both map to prompt', async () => {
    for (const raw of ['prompt', 'prompt-with-rationale']) {
      const { plugin } = createGeolocation({ checkPermissions: () => ({ location: raw }) })
      const result = await checkExistingPermission({ geolocation: plugin })
      assert.deepStrictEqual(result, { state: 'prompt' }, `raw value "${raw}"`)
    }
  })

  test('device location services disabled maps to unavailable, not denied', async () => {
    const { plugin } = createGeolocation({
      checkPermissions: () => { throw SERVICES_DISABLED_ERROR },
    })
    const result = await checkExistingPermission({ geolocation: plugin })
    assert.deepStrictEqual(result, { state: 'unavailable' })
  })

  test('an unclassified plugin failure maps to error, not unsupported', async () => {
    const { plugin } = createGeolocation({
      checkPermissions: () => { throw new Error('bridge hiccup') },
    })
    const result = await checkExistingPermission({ geolocation: plugin })
    assert.deepStrictEqual(result, { state: 'error' })
  })

  test('no plugin on a native platform maps to unsupported', async () => {
    const result = await checkExistingPermission({ geolocation: null })
    assert.deepStrictEqual(result, { state: 'unsupported' })
  })
})

describe('requestCurrentLocation', () => {
  test('granted permission returns coords', async () => {
    const { plugin } = createGeolocation()
    const result = await requestCurrentLocation({ geolocation: plugin })
    assert.strictEqual(result.status, 'granted')
    assert.strictEqual(result.coords.latitude, 1)
  })

  test('already-granted status skips requestPermissions', async () => {
    const { plugin, calls } = createGeolocation({
      checkPermissions: () => ({ location: 'granted' }),
    })
    await requestCurrentLocation({ geolocation: plugin })
    assert.strictEqual(calls.requestPermissions, 0)
  })

  test('denial is reported as denied, not services-disabled', async () => {
    const { plugin } = createGeolocation({
      checkPermissions: () => ({ location: 'prompt' }),
      requestPermissions: () => ({ location: 'denied' }),
    })
    const result = await requestCurrentLocation({ geolocation: plugin })
    assert.strictEqual(result.status, 'denied')
  })

  test('repeat denial escalates to settings guidance', async () => {
    const { plugin } = createGeolocation({
      checkPermissions: () => ({ location: 'prompt' }),
      requestPermissions: () => ({ location: 'denied' }),
    })
    const first = await requestCurrentLocation({ geolocation: plugin })
    const second = await requestCurrentLocation({ geolocation: plugin })
    assert.strictEqual(first.status, 'denied')
    assert.strictEqual(second.status, 'settings')
  })

  test('a granted fix resets the repeat-denial counter', async () => {
    const denyPlugin = createGeolocation({
      checkPermissions: () => ({ location: 'prompt' }),
      requestPermissions: () => ({ location: 'denied' }),
    }).plugin
    await requestCurrentLocation({ geolocation: denyPlugin })

    const grantPlugin = createGeolocation().plugin
    await requestCurrentLocation({ geolocation: grantPlugin })

    const result = await requestCurrentLocation({ geolocation: denyPlugin })
    assert.strictEqual(result.status, 'denied', 'counter should have reset, not escalated to settings')
  })

  test('device location services disabled during checkPermissions short-circuits without counting as a denial', async () => {
    const { plugin, calls } = createGeolocation({
      checkPermissions: () => { throw SERVICES_DISABLED_ERROR },
    })
    const result = await requestCurrentLocation({ geolocation: plugin })
    assert.strictEqual(result.status, 'services-disabled')
    assert.strictEqual(calls.requestPermissions, 0, 'must not fall through to requestPermissions')

    // A subsequent real denial must start from a clean counter — services-disabled
    // must never have been recorded as a denial.
    const denyPlugin = createGeolocation({
      checkPermissions: () => ({ location: 'prompt' }),
      requestPermissions: () => ({ location: 'denied' }),
    }).plugin
    const denyResult = await requestCurrentLocation({ geolocation: denyPlugin })
    assert.strictEqual(denyResult.status, 'denied')
  })

  test('device location services disabled during requestPermissions short-circuits', async () => {
    const { plugin } = createGeolocation({
      checkPermissions: () => ({ location: 'prompt' }),
      requestPermissions: () => { throw SERVICES_DISABLED_ERROR },
    })
    const result = await requestCurrentLocation({ geolocation: plugin })
    assert.strictEqual(result.status, 'services-disabled')
  })

  test('device location services disabled during getCurrentPosition short-circuits', async () => {
    const { plugin } = createGeolocation({
      checkPermissions: () => ({ location: 'granted' }),
      getCurrentPosition: () => { throw SERVICES_DISABLED_ERROR },
    })
    const result = await requestCurrentLocation({ geolocation: plugin })
    assert.strictEqual(result.status, 'services-disabled')
  })

  test('a generic getCurrentPosition failure maps to unavailable', async () => {
    const { plugin } = createGeolocation({
      checkPermissions: () => ({ location: 'granted' }),
      getCurrentPosition: () => { throw new Error('timeout') },
    })
    const result = await requestCurrentLocation({ geolocation: plugin })
    assert.strictEqual(result.status, 'unavailable')
  })

  test('approximate-only (coarse) grant is accepted as granted', async () => {
    const { plugin } = createGeolocation({
      checkPermissions: () => ({ location: 'denied', coarseLocation: 'granted' }),
    })
    const result = await requestCurrentLocation({ geolocation: plugin })
    assert.strictEqual(result.status, 'granted')
  })

  test('no plugin available maps to unsupported', async () => {
    const result = await requestCurrentLocation({ geolocation: null })
    assert.strictEqual(result.status, 'unsupported')
  })
})
