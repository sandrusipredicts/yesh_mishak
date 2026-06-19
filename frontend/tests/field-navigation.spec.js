import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

const user = {
  id: 'regular-user-1',
  email: 'user@example.com',
  name: 'Regular User',
  role: 'user',
}

const navigableField = {
  id: 'field-1',
  name: 'Central Court',
  latitude: 31.225172,
  longitude: 34.777498,
  sport_type: 'football',
  surface_type: 'synthetic',
  has_nets: true,
  has_water_cooler: false,
  opening_hours: '19:00',
  notes: '',
  status: 'approved',
}

const cachedNavigableField = {
  ...navigableField,
  name: 'Cached Court',
}

function fulfillJson(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function seedAuthenticatedUser(page) {
  const token = makeJwtWithSubject(user.id)

  await page.addInitScript((storedUser) => {
    localStorage.setItem('access_token', storedUser.token)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.setItem('onboarding_done', 'true')
  }, { ...user, token })
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

async function mockGeolocation(page) {
  await page.addInitScript(({ latitude, longitude }) => {
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition(success) {
          success({ coords: { latitude, longitude } })
        },
      },
    })
  }, navigableField)
}

async function trackOpenedUrls(page) {
  await page.addInitScript(() => {
    window.__openedUrls = []
    window.open = (url, target, features) => {
      window.__openedUrls.push({ url, target, features })
      return null
    }
  })
}

async function mockMapPageRequests(page, fields) {
  await page.route(/\/fields\/?(\?.*)?$/, (route) => fulfillJson(route, fields))
  await page.route(/\/notifications\/?(\?.*)?$/, (route) => fulfillJson(route, []))
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
}

async function openFieldDetails(page) {
  await page.goto('/')
  await page.locator('.field-marker-icon').first().click()
  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: navigableField.name }),
  ).toBeVisible()
}

test.beforeEach(async ({ page }) => {
  await seedAuthenticatedUser(page)
  await mockGeolocation(page)
  await trackOpenedUrls(page)
})

test('opens Waze and Google Maps navigation links for a field', async ({ page }) => {
  await mockMapPageRequests(page, [navigableField])
  await openFieldDetails(page)

  await page.getByRole('button', { name: 'נווט למגרש' }).click()
  await expect(page.getByRole('dialog', { name: 'פתח ניווט' })).toBeVisible()

  await page.getByRole('button', { name: 'Waze' }).click()
  await expect(page.getByRole('dialog', { name: 'פתח ניווט' })).toBeHidden()

  await page.getByRole('button', { name: 'נווט למגרש' }).click()
  await page.getByRole('button', { name: 'Google Maps' }).click()

  await expect
    .poll(() => page.evaluate(() => window.__openedUrls))
    .toEqual([
      {
        url: 'https://waze.com/ul?ll=31.225172,34.777498&navigate=yes',
        target: '_blank',
        features: 'noopener,noreferrer',
      },
      {
        url: 'https://www.google.com/maps/dir/?api=1&destination=31.225172,34.777498',
        target: '_blank',
        features: 'noopener,noreferrer',
      },
    ])
})

test('closes the navigation dialog without opening a provider', async ({ page }) => {
  await mockMapPageRequests(page, [navigableField])
  await openFieldDetails(page)

  await page.getByRole('button', { name: 'נווט למגרש' }).click()
  await page.getByRole('button', { name: 'ביטול' }).click()

  await expect(page.getByRole('dialog', { name: 'פתח ניווט' })).toBeHidden()
  await expect.poll(() => page.evaluate(() => window.__openedUrls)).toEqual([])
})

test('hides navigation for missing or invalid coordinates', async ({ page }) => {
  await mockMapPageRequests(page, [
    { ...navigableField, id: 'field-missing', latitude: null, longitude: null },
    { ...navigableField, id: 'field-invalid', latitude: 190, longitude: 34.777498 },
  ])

  await page.goto('/')

  await expect(page.locator('.field-marker-icon')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'נווט למגרש' })).toHaveCount(0)
})

test('uses stadium markers for active and inactive fields', async ({ page }) => {
  await mockMapPageRequests(page, [
    {
      ...navigableField,
      id: 'field-inactive',
      active_game: null,
    },
    {
      ...navigableField,
      id: 'field-active',
      latitude: 31.226,
      active_game: {
        id: 'game-1',
        status: 'open',
        players_present: 4,
        max_players: 10,
      },
    },
  ])

  await page.goto('/')

  await expect(page.locator('.field-marker-icon')).toHaveCount(2)
  await expect(page.locator('.field-marker--inactive img')).toHaveAttribute(
    'src',
    /stadium-inactive\.png$/,
  )
  await expect(page.locator('.field-marker--active img')).toHaveAttribute(
    'src',
    /stadium-active\.png$/,
  )
  await expect
    .poll(() =>
      page.locator('.field-marker--active .field-marker-status').evaluate((element) =>
        window.getComputedStyle(element).animationName,
      ),
    )
    .toBe('field-marker-active-pulse')
  await expect
    .poll(() =>
      page.locator('.field-marker--inactive .field-marker-status').evaluate((element) =>
        window.getComputedStyle(element).animationName,
      ),
    )
    .toBe('none')

  await page.getByRole('button', { name: 'Zoom in' }).click()
  await expect(page.locator('.field-marker--active')).toBeVisible()
  await page.getByRole('button', { name: 'Zoom out' }).click()
  await page.getByRole('button', { name: 'Zoom out' }).click()
  await expect(page.locator('.field-marker--inactive')).toBeVisible()
})

test('shows cached fields immediately while refreshing fields in the background', async ({
  page,
}) => {
  await page.addInitScript((field) => {
    localStorage.setItem('cached_fields', JSON.stringify([field]))
    localStorage.setItem('cached_fields_timestamp', '2026-06-19T08:00:00.000Z')
  }, cachedNavigableField)

  await page.route(/\/fields\/?(\?.*)?$/, async (route) => {
    await new Promise((resolve) => {
      setTimeout(resolve, 250)
    })

    return fulfillJson(route, [navigableField])
  })
  await page.route(/\/notifications\/?(\?.*)?$/, (route) => fulfillJson(route, []))
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())

  await page.goto('/')

  await expect(page.locator('.field-marker-icon')).toHaveCount(1)
  await page.locator('.field-marker-icon').first().click()
  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: cachedNavigableField.name }),
  ).toBeVisible()

  await expect
    .poll(() =>
      page.evaluate(() => JSON.parse(localStorage.getItem('cached_fields') ?? '[]')[0]?.name),
    )
    .toBe(navigableField.name)
})

test('keeps navigation dialog usable on a mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockMapPageRequests(page, [navigableField])
  await openFieldDetails(page)

  await page.getByRole('button', { name: 'נווט למגרש' }).click()

  const dialog = page.getByRole('dialog', { name: 'פתח ניווט' })
  await expect(dialog).toBeVisible()
  await expect(dialog).toBeInViewport()
  await expect(page.getByRole('button', { name: 'Waze' })).toBeInViewport()
  await expect(page.getByRole('button', { name: 'Google Maps' })).toBeInViewport()
})
