import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

const YERUHAM_COORDS = { lat: 30.9872, lng: 34.9314 }

const user = {
  id: 'regular-user-1',
  email: 'user@example.com',
  name: 'Regular User',
  role: 'user',
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

async function seedAuthenticatedUser(page, { storedUserCity } = {}) {
  await page.addInitScript(({ storedUser, cityToStore }) => {
    localStorage.setItem('access_token', storedUser.token)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')

    if (cityToStore) {
      // Some users legitimately picked Yeruham during onboarding. That must
      // never leak into a new field's city/location without the user
      // explicitly choosing it in the Add Field form.
      localStorage.setItem('userCity', cityToStore)
    }
  }, { storedUser: { ...user, token: makeJwtWithSubject(user.id) }, cityToStore: storedUserCity })
}

async function mockSharedRequests(page) {
  await page.route(/\/fields\/?(\?.*)?$/, (route) => {
    if (route.request().method() === 'GET') {
      return fulfillJson(route, [])
    }
    return route.fallback()
  })
  await page.route(/\/notifications(\/.*)?(\?.*)?$/, (route) => {
    const url = new URL(route.request().url())

    if (url.pathname === '/notifications/unread-count') {
      return fulfillJson(route, { unread_count: 0 })
    }

    return fulfillJson(route, [])
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
}

async function mockRejectedGeolocation(page, code = 1) {
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

async function mockGrantedGeolocation(page, location) {
  await page.addInitScript((coords) => {
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition(success) {
          success({
            coords: {
              latitude: coords.latitude,
              longitude: coords.longitude,
              accuracy: coords.accuracy,
            },
          })
        },
      },
    })
  }, location)
}

async function openAddFieldModal(page) {
  await page.goto('/')
  await page.waitForSelector('.auth-toolbar')
  await page.locator('.floating-button.bottom').click()
  return page.getByRole('dialog', { name: 'Add Field' })
}

async function mockCreateField(page) {
  let capturedRequest = null

  await page.route(/\/fields\/?$/, async (route) => {
    if (route.request().method() !== 'POST') {
      return route.fallback()
    }

    capturedRequest = route.request().postDataJSON()

    return fulfillJson(route, {
      message: 'Field submitted for VAR approval',
      field: { id: 'new-field-1', ...capturedRequest, approval_status: 'pending' },
    })
  })

  return () => capturedRequest
}

test.beforeEach(async ({ page }) => {
  await mockSharedRequests(page)
})

test('does not default city or location to Yeruham when geolocation is denied', async ({ page }) => {
  await seedAuthenticatedUser(page)
  await mockRejectedGeolocation(page)
  const getCapturedRequest = await mockCreateField(page)

  const dialog = await openAddFieldModal(page)

  // No location has been chosen yet: the map must not silently carry a real
  // field location, and no coordinates should be displayed.
  await expect(dialog.getByText('No location selected yet.', { exact: false })).toBeVisible()

  // The city field must start empty; it must never be pre-filled with a
  // hardcoded/default city.
  await expect(dialog.getByLabel('City')).toHaveValue('')

  await dialog.getByLabel('Field name').fill('Test Field')

  // Submitting without a city must be blocked and must not reach the API.
  await dialog.getByRole('button', { name: 'Submit for approval' }).click()
  await expect(dialog.getByText('Please choose a city from the list.')).toBeVisible()
  expect(getCapturedRequest()).toBeNull()

  // Pick a real city from the list manually.
  await dialog.getByLabel('City').fill('באר שבע')
  await dialog.getByRole('option', { name: 'באר שבע' }).click()

  // City is now valid, but location still hasn't been confirmed: submission
  // must still be blocked instead of silently using a fallback location.
  await dialog.getByRole('button', { name: 'Submit for approval' }).click()
  await expect(dialog.getByText('Field location is required.')).toBeVisible()
  expect(getCapturedRequest()).toBeNull()

  // Since geolocation was denied, the user places the pin manually on the map.
  await dialog.locator('.location-picker-map').click()

  await dialog.getByRole('button', { name: 'Submit for approval' }).click()

  await expect.poll(() => getCapturedRequest()).not.toBeNull()
  const request = getCapturedRequest()

  expect(request.city).toBe('באר שבע')
  expect(request.city).not.toBe('ירוחם')
  expect([request.lat, request.lng]).not.toEqual([YERUHAM_COORDS.lat, YERUHAM_COORDS.lng])
})

test('does not use the onboarding-stored city when geolocation is denied', async ({ page }) => {
  // Even a user whose own onboarding city happens to be Yeruham must
  // explicitly confirm the city for a new field; it must not be silently
  // reused from localStorage.
  await seedAuthenticatedUser(page, { storedUserCity: 'ירוחם' })
  await mockRejectedGeolocation(page)
  const getCapturedRequest = await mockCreateField(page)

  const dialog = await openAddFieldModal(page)

  await expect(dialog.getByLabel('City')).toHaveValue('')

  await dialog.getByLabel('Field name').fill('Another Test Field')
  await dialog.getByRole('button', { name: 'Submit for approval' }).click()
  await expect(dialog.getByText('Please choose a city from the list.')).toBeVisible()
  expect(getCapturedRequest()).toBeNull()
})

test('rejects a manually typed city that is not in the known list', async ({ page }) => {
  await seedAuthenticatedUser(page)
  await mockRejectedGeolocation(page)
  const getCapturedRequest = await mockCreateField(page)

  const dialog = await openAddFieldModal(page)

  await dialog.getByLabel('Field name').fill('Test Field')
  await dialog.getByLabel('City').fill('Not A Real City')
  await dialog.locator('.location-picker-map').click()

  await dialog.getByRole('button', { name: 'Submit for approval' }).click()

  await expect(dialog.getByText('Please choose a city from the list.')).toBeVisible()
  expect(getCapturedRequest()).toBeNull()
})

test('uses navigator.geolocation coordinates, not the map fallback, when location permission is granted', async ({
  page,
}) => {
  const grantedLocation = { latitude: 32.0853, longitude: 34.7818, accuracy: 15 }

  await seedAuthenticatedUser(page)
  await mockGrantedGeolocation(page, grantedLocation)
  const getCapturedRequest = await mockCreateField(page)

  const dialog = await openAddFieldModal(page)

  await dialog.getByLabel('Field name').fill('GPS Field')
  await dialog.getByLabel('City').fill('תל אביב-יפו')
  await dialog.getByRole('option', { name: 'תל אביב-יפו' }).click()

  await dialog.getByRole('button', { name: 'Use current location' }).click()

  await expect(
    dialog.getByText(`Lat: ${grantedLocation.latitude.toFixed(6)}`, { exact: false }),
  ).toBeVisible()

  await dialog.getByRole('button', { name: 'Submit for approval' }).click()

  await expect.poll(() => getCapturedRequest()).not.toBeNull()
  const request = getCapturedRequest()

  expect(request.lat).toBeCloseTo(grantedLocation.latitude, 5)
  expect(request.lng).toBeCloseTo(grantedLocation.longitude, 5)
  expect([request.lat, request.lng]).not.toEqual([YERUHAM_COORDS.lat, YERUHAM_COORDS.lng])
  expect(request.city).toBe('תל אביב-יפו')
})
