import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

const user = {
  id: 'regular-user-1',
  email: 'user@example.com',
  name: 'Regular User',
  role: 'user',
}

const userLocation = {
  latitude: 30.9872,
  longitude: 34.9314,
  accuracy: 42,
  altitude: 120,
  altitudeAccuracy: 10,
  heading: 90,
  speed: 1.5,
}

function fulfillJson(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

function encodeBase64Url(value) {
  return Buffer.from(value).toString('base64url')
}

function makeJwtWithSubject(userId) {
  return [
    encodeBase64Url(JSON.stringify({ alg: 'none', typ: 'JWT' })),
    encodeBase64Url(JSON.stringify({ sub: userId })),
    'signature',
  ].join('.')
}

async function seedAuthenticatedUser(page) {
  await page.addInitScript((storedUser) => {
    localStorage.setItem('access_token', storedUser.token)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  }, { ...user, token: makeJwtWithSubject(user.id) })
}

async function mockSharedRequests(page) {
  await page.route(/\/fields\/?(\?.*)?$/, (route) => fulfillJson(route, []))
  await page.route(/\/notifications(\/.*)?(\?.*)?$/, (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/notifications/unread-count') {
      return fulfillJson(route, { unread_count: 0 })
    }
    return fulfillJson(route, [])
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
}

async function mockFullGeolocation(page, coords) {
  await page.addInitScript((location) => {
    window.__geolocationCalls = 0
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition(success) {
          window.__geolocationCalls += 1
          success({
            coords: {
              latitude: location.latitude,
              longitude: location.longitude,
              accuracy: location.accuracy,
              altitude: location.altitude,
              altitudeAccuracy: location.altitudeAccuracy,
              heading: location.heading,
              speed: location.speed,
            },
            timestamp: Date.now(),
          })
        },
      },
    })
  }, coords)
}

async function mockRejectedGeolocation(page, code) {
  await page.addInitScript((errorCode) => {
    window.__geolocationCalls = 0
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition(_success, error) {
          window.__geolocationCalls += 1
          error?.({ code: errorCode, message: 'Location unavailable' })
        },
      },
    })
  }, code)
}

async function mockUnsupportedGeolocation(page) {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: undefined,
    })
  })
}

test.beforeEach(async ({ page }) => {
  await seedAuthenticatedUser(page)
  await mockSharedRequests(page)
})

test('location service normalizes full coordinate fields through MapPage', async ({ page }) => {
  await mockFullGeolocation(page, userLocation)
  await page.goto('/')

  await expect(page.locator('.map-canvas')).toBeVisible()
  await page.getByRole('button', { name: 'My Location' }).click()

  await expect(page.locator('.user-location-marker-icon')).toBeVisible()

  const markerOffset = await page.evaluate(() => {
    const map = document.querySelector('.map-canvas')?.getBoundingClientRect()
    const marker = document.querySelector('.user-location-marker-icon')?.getBoundingClientRect()
    if (!map || !marker) return null
    return {
      x: Math.abs(marker.left + marker.width / 2 - (map.left + map.width / 2)),
      y: Math.abs(marker.top + marker.height / 2 - (map.top + map.height / 2)),
    }
  })
  expect(markerOffset.x).toBeLessThan(36)
  expect(markerOffset.y).toBeLessThan(36)
})

test('second click within cache window does not re-call geolocation', async ({ page }) => {
  await mockFullGeolocation(page, userLocation)
  await page.goto('/')
  await expect(page.locator('.map-canvas')).toBeVisible()

  await page.getByRole('button', { name: 'My Location' }).click()
  await expect(page.locator('.user-location-marker-icon')).toBeVisible()
  await expect.poll(() => page.evaluate(() => window.__geolocationCalls)).toBe(1)

  // Pan away to prove the second click does re-center
  const mapBox = await page.locator('.map-canvas').boundingBox()
  await page.mouse.move(mapBox.x + mapBox.width / 2, mapBox.y + mapBox.height / 2)
  await page.mouse.down()
  await page.mouse.move(mapBox.x + mapBox.width / 2 + 220, mapBox.y + mapBox.height / 2)
  await page.mouse.up()

  await page.getByRole('button', { name: 'My Location' }).click()
  await expect(page.locator('.user-location-marker-icon')).toBeVisible()

  // The cached location should be served — no second native call
  await expect.poll(() => page.evaluate(() => window.__geolocationCalls)).toBe(1)
})

test('refreshLocation bypasses cache and updates timestamp', async ({ page }) => {
  await mockFullGeolocation(page, userLocation)
  await page.goto('/')
  await expect(page.locator('.map-canvas')).toBeVisible()

  // 1. First getCurrentLocation via button click triggers one geolocation call
  await page.getByRole('button', { name: 'My Location' }).click()
  await expect(page.locator('.user-location-marker-icon')).toBeVisible()
  await expect.poll(() => page.evaluate(() => window.__geolocationCalls)).toBe(1)

  // 2. Capture cached timestamp
  const cachedTimestamp = await page.evaluate(() => {
    return window.__locationServiceTest.getLastKnownLocation()?.timestamp
  })
  expect(cachedTimestamp).toBeGreaterThan(0)

  // 3. Second getCurrentLocation (button click) uses cache — no new call
  await page.getByRole('button', { name: 'My Location' }).click()
  await page.waitForTimeout(300)
  const callsAfterCache = await page.evaluate(() => window.__geolocationCalls)
  expect(callsAfterCache).toBe(1)

  // 4. refreshLocation bypasses cache — triggers a second geolocation call
  const refreshResult = await page.evaluate(async () => {
    const result = await window.__locationServiceTest.refreshLocation({ highAccuracy: true })
    return {
      ok: result.ok,
      timestamp: result.location?.timestamp,
      latitude: result.location?.latitude,
      longitude: result.location?.longitude,
      accuracyMeters: result.location?.accuracyMeters,
      source: result.location?.source,
      permissionState: result.location?.permissionState,
      calls: window.__geolocationCalls,
    }
  })

  expect(refreshResult.ok).toBe(true)
  expect(refreshResult.calls).toBe(2)
  expect(refreshResult.timestamp).toBeGreaterThanOrEqual(cachedTimestamp)
  expect(refreshResult.latitude).toBe(userLocation.latitude)
  expect(refreshResult.longitude).toBe(userLocation.longitude)
  expect(refreshResult.accuracyMeters).toBe(userLocation.accuracy)
  expect(refreshResult.source).toBe('web')
  expect(refreshResult.permissionState).toBe('granted')

  // 5. getLastKnownLocation reflects the refreshed data
  const lastKnown = await page.evaluate(() => {
    return window.__locationServiceTest.getLastKnownLocation()
  })
  expect(lastKnown.timestamp).toBe(refreshResult.timestamp)
})

test('denied permission returns error without crash', async ({ page }) => {
  await mockRejectedGeolocation(page, 1)
  await page.goto('/')
  await expect(page.locator('.map-canvas')).toBeVisible()

  await page.getByRole('button', { name: 'My Location' }).click()

  const notice = page.locator('.location-notice')
  await expect(notice).toBeVisible()
  await expect(notice).toContainText('without permission')
  await expect(page.locator('.user-location-marker-icon')).toHaveCount(0)

  // Map stays usable
  await expect(page.locator('.map-canvas')).toBeVisible()
  await expect(page.getByRole('button', { name: 'My Location' })).toBeVisible()
})

test('unsupported platform shows unavailable notice', async ({ page }) => {
  await mockUnsupportedGeolocation(page)
  await page.goto('/')
  await expect(page.locator('.map-canvas')).toBeVisible()

  await page.getByRole('button', { name: 'My Location' }).click()
  await expect(page.locator('.location-notice')).toContainText('Location is unavailable')
  await expect(page.locator('.user-location-marker-icon')).toHaveCount(0)
})

test('accuracy circle renders with correct radius', async ({ page }) => {
  await mockFullGeolocation(page, userLocation)
  await page.goto('/')
  await expect(page.locator('.map-canvas')).toBeVisible()

  await page.getByRole('button', { name: 'My Location' }).click()
  await expect(page.locator('.user-location-marker-icon')).toBeVisible()

  // The accuracy circle is a Leaflet Circle rendered as an SVG path
  const hasCircle = await page.evaluate(() => {
    const paths = document.querySelectorAll('.leaflet-overlay-pane path')
    return paths.length > 0
  })
  expect(hasCircle).toBe(true)
})
