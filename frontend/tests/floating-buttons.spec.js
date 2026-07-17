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

const mockedFields = [
  {
    id: 'field-1',
    name: 'Central Court',
    surface_type: 'asphalt',
    has_nets: true,
    has_water_cooler: true,
    opening_hours: '08:00 - 22:00',
    notes: 'Good court',
    status: 'approved',
    lat: 30.9872,
    lng: 34.9314,
  },
]

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

async function seedAuthenticatedUser(page, lang = 'en') {
  await page.addInitScript(({ storedUser, currentLang }) => {
    localStorage.setItem('access_token', storedUser.token)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('userCity', 'ירושלים') // E08-02 follow-up fix: account needs a resolved city to reach the map
    localStorage.setItem('app_language', currentLang)
    localStorage.setItem('language_selected', 'true')
  }, { storedUser: { ...user, token: makeJwtWithSubject(user.id) }, currentLang: lang })
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

function assertNoOverlap(box1, box2) {
  const overlapX = box1.x < box2.x + box2.width && box1.x + box1.width > box2.x
  const overlapY = box1.y < box2.y + box2.height && box1.y + box1.height > box2.y
  expect(overlapX && overlapY).toBe(false)
}

test.describe('Floating Action Button Layout', () => {
  test('Top-start stack aligns notifications & preferences and avoids overlaps', async ({ page }) => {
    await seedAuthenticatedUser(page, 'en')
    await mockSharedRequests(page, [])
    await page.goto('/')

    const bellBtn = page.locator('.floating-button.top')
    const prefBtn = page.locator('.floating-button.preferences')

    await expect(bellBtn).toBeVisible()
    await expect(prefBtn).toBeVisible()

    const bellBox = await bellBtn.boundingBox()
    const prefBox = await prefBtn.boundingBox()

    expect(bellBox).not.toBeNull()
    expect(prefBox).not.toBeNull()

    // Top-start stack: Vertically aligned (same x coordinate)
    expect(Math.abs(bellBox.x - prefBox.x)).toBeLessThan(5)
    // Vertically stacked with bell above preferences
    expect(prefBox.y).toBeGreaterThan(bellBox.y + bellBox.height)

    // No overlap
    assertNoOverlap(bellBox, prefBox)
  })

  test('Bottom action buttons are hidden when FieldDetailsPanel is open', async ({ page }) => {
    await seedAuthenticatedUser(page, 'en')
    await mockGeolocation(page)
    await mockSharedRequests(page, mockedFields)
    await page.goto('/')

    // Center map and show location button
    const locationBtn = page.locator('.floating-button.my-location')
    const addFieldBtn = page.locator('.floating-button.bottom')

    await expect(locationBtn).toBeVisible()
    await expect(addFieldBtn).toBeVisible()

    // Click map marker to open selected field details panel
    const marker = page.locator('.field-marker-icon').first()
    await expect(marker).toBeVisible()
    await marker.click()

    const panel = page.getByLabel('Field details')
    await expect(panel).toBeVisible()

    // Verify bottom action buttons are hidden/unmounted
    await expect(locationBtn).toHaveCount(0)
    await expect(addFieldBtn).toHaveCount(0)

    // Close panel
    await page.locator('.panel-close-button').click()
    await expect(panel).toHaveCount(0)

    // Bottom action buttons should reappear
    await expect(locationBtn).toBeVisible()
    await expect(addFieldBtn).toBeVisible()
  })

  test('Zoom controls and logged-in toolbar do not overlap in LTR or RTL', async ({ page }) => {
    // 1. Check LTR Layout
    await seedAuthenticatedUser(page, 'en')
    await mockSharedRequests(page, [])
    await page.goto('/')

    const zoom = page.locator('.leaflet-control-zoom')
    const toolbar = page.locator('.auth-toolbar')

    await expect(zoom).toBeVisible()
    await expect(toolbar).toBeVisible()

    let zoomBox = await zoom.boundingBox()
    let toolbarBox = await toolbar.boundingBox()

    expect(zoomBox).not.toBeNull()
    expect(toolbarBox).not.toBeNull()

    // LTR: Zoom control is at bottomright physically, Toolbar is at topright. No overlap.
    assertNoOverlap(zoomBox, toolbarBox)

    // 2. Check RTL Layout
    await seedAuthenticatedUser(page, 'he')
    await page.goto('/')

    await expect(zoom).toBeVisible()
    await expect(toolbar).toBeVisible()

    zoomBox = await zoom.boundingBox()
    toolbarBox = await toolbar.boundingBox()

    // RTL: Zoom control is at bottomleft physically, Toolbar is at topleft. No overlap.
    assertNoOverlap(zoomBox, toolbarBox)
  })
})
