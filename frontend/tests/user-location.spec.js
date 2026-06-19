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

async function mockGrantedGeolocation(page) {
  await page.addInitScript((location) => {
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition(success) {
          success({
            coords: {
              latitude: location.latitude,
              longitude: location.longitude,
              accuracy: location.accuracy,
            },
          })
        },
      },
    })
  }, userLocation)
}

async function mockRejectedGeolocation(page, code) {
  await page.addInitScript((errorCode) => {
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition(_success, error) {
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

async function markerOffsetFromMapCenter(page) {
  return page.evaluate(() => {
    const map = document.querySelector('.map-canvas')?.getBoundingClientRect()
    const marker = document.querySelector('.user-location-marker-icon')?.getBoundingClientRect()

    if (!map || !marker) {
      return null
    }

    return {
      x: Math.abs((marker.left + marker.width / 2) - (map.left + map.width / 2)),
      y: Math.abs((marker.top + marker.height / 2) - (map.top + map.height / 2)),
    }
  })
}

async function expectUserMarkerNearCenter(page) {
  await expect
    .poll(() => markerOffsetFromMapCenter(page))
    .toEqual({
      x: expect.any(Number),
      y: expect.any(Number),
    })

  await expect
    .poll(async () => {
      const offset = await markerOffsetFromMapCenter(page)

      if (!offset) {
        return false
      }

      return offset.x < 36 && offset.y < 36
    })
    .toBe(true)
}

test.beforeEach(async ({ page }) => {
  await seedAuthenticatedUser(page)
  await mockSharedRequests(page)
})

test('shows user location, centers once, and returns to it from the map button', async ({
  page,
}) => {
  await mockGrantedGeolocation(page)

  await page.goto('/')

  await expect(page.locator('.user-location-marker-icon')).toBeVisible()
  await expect(page.locator('.leaflet-interactive')).toBeVisible()
  await expect(page.getByRole('button', { name: 'My Location' })).toBeVisible()
  await expectUserMarkerNearCenter(page)

  const mapBox = await page.locator('.map-canvas').boundingBox()
  expect(mapBox).not.toBeNull()

  await page.mouse.move(mapBox.x + mapBox.width / 2, mapBox.y + mapBox.height / 2)
  await page.mouse.down()
  await page.mouse.move(mapBox.x + mapBox.width / 2 + 220, mapBox.y + mapBox.height / 2)
  await page.mouse.up()

  await expect
    .poll(() => markerOffsetFromMapCenter(page))
    .toMatchObject({
      x: expect.any(Number),
      y: expect.any(Number),
    })

  const pannedOffset = await markerOffsetFromMapCenter(page)
  expect(pannedOffset.x).toBeGreaterThan(70)

  await page.getByRole('button', { name: 'My Location' }).click()
  await expectUserMarkerNearCenter(page)
})

test('keeps the map usable when location permission is denied', async ({ page }) => {
  await mockRejectedGeolocation(page, 1)

  await page.goto('/')

  await expect(page.locator('.map-canvas')).toBeVisible()
  await expect(page.locator('.user-location-marker-icon')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'My Location' })).toHaveCount(0)
})

test('keeps the map usable when geolocation times out', async ({ page }) => {
  await mockRejectedGeolocation(page, 3)

  await page.goto('/')

  await expect(page.locator('.map-canvas')).toBeVisible()
  await expect(page.locator('.user-location-marker-icon')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'My Location' })).toHaveCount(0)
})

test('keeps the map usable when geolocation is unsupported', async ({ page }) => {
  await mockUnsupportedGeolocation(page)

  await page.goto('/')

  await expect(page.locator('.map-canvas')).toBeVisible()
  await expect(page.locator('.user-location-marker-icon')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'My Location' })).toHaveCount(0)
})
