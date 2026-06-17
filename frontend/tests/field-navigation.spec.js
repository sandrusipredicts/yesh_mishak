import { expect, test } from '@playwright/test'

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

function fulfillJson(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function seedAuthenticatedUser(page) {
  await page.addInitScript((storedUser) => {
    localStorage.setItem('access_token', `${storedUser.role}-token`)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.setItem('onboarding_done', 'true')
  }, user)
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
