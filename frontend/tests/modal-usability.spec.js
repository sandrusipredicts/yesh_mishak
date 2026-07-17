import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

const user = {
  id: 'current-user',
  email: 'current@example.com',
  name: 'Current User',
  role: 'user',
}

const mockLocation = {
  latitude: 30.9872,
  longitude: 34.9314,
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
    localStorage.setItem('userCity', 'ירושלים') // E08-02 follow-up fix: account needs a resolved city to reach the map
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  }, { ...user, token: makeJwtWithSubject(user.id) })
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
  }, mockLocation)
}

async function mockSharedRequests(page, fields = []) {
  await page.route(/\/fields\/?(\?.*)?$/, (route) => {
    return fulfillJson(route, fields)
  })
  await page.route(/\/fields\/([a-zA-Z0-9_-]+)(\?.*)?$/, (route) => {
    const url = new URL(route.request().url())
    const fieldMatch = url.pathname.match(/\/fields\/([a-zA-Z0-9_-]+)/)
    const fieldId = fieldMatch ? fieldMatch[1] : ''
    const field = fields.find(f => f.id === fieldId)
    return fulfillJson(route, field || {})
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

test.beforeEach(async ({ page }) => {
  await seedAuthenticatedUser(page)
})

test('Add field modal opens and actions remain reachable on short width and height mobile viewports', async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 568 }) // iPhone SE (1st gen)
  await mockSharedRequests(page, [])

  await page.goto('/')

  // Open Add Field Modal
  await page.getByRole('button', { name: 'Add field' }).click()

  const dialog = page.getByRole('dialog', { name: 'Add Field' })
  await expect(dialog).toBeVisible()
  await expect(dialog).toBeInViewport()

  // Scroll actions into view
  const cancelBtn = page.getByRole('button', { name: 'Cancel' })
  const submitBtn = page.getByRole('button', { name: 'Submit for approval' })
  await cancelBtn.scrollIntoViewIfNeeded()

  // Verify cancel and submit buttons are visible in viewport
  await expect(cancelBtn).toBeInViewport()
  await expect(submitBtn).toBeInViewport()

  // Pressing Escape should close it
  await page.keyboard.press('Escape')
  await expect(dialog).toHaveCount(0)
})

test('Field details panel content remains scrollable and child modals stack properly on mobile viewports', async ({ page }) => {
  const fields = [
    {
      id: 'field-1',
      name: 'Central Court',
      surface_type: 'asphalt',
      has_nets: true,
      has_water_cooler: true,
      opening_hours: '24/7',
      notes: 'Lit at night',
      latitude: 30.9872,
      longitude: 34.9314,
      status: 'approved',
    }
  ]
  await page.setViewportSize({ width: 375, height: 667 })
  await mockGeolocation(page)
  await mockSharedRequests(page, fields)

  await page.goto('/')
  await page.locator('.field-marker-icon').first().click()

  const panel = page.locator('.field-details-panel')
  await expect(panel).toBeVisible()
  await expect(panel).toBeInViewport()

  // Open Report Field Modal from panel
  await page.getByRole('button', { name: 'Report', exact: true }).click()

  const reportDialog = page.getByRole('dialog', { name: 'Report field' })
  await expect(reportDialog).toBeVisible()
  await expect(reportDialog).toBeInViewport()

  // Close the report modal using Escape
  await page.keyboard.press('Escape')
  await expect(reportDialog).toHaveCount(0)
})
