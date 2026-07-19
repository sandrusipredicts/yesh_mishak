import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

const user = {
  id: 'regular-user-1',
  email: 'user@example.com',
  name: 'Regular User',
  role: 'user',
}

const FIELD_ID = '77777777-7777-4777-8777-777777777777'
const OTHER_FIELD_ID = '88888888-8888-4888-8888-888888888888'
const MISSING_FIELD_ID = '99999999-9999-4999-8999-999999999999'
const NETWORK_ERROR_FIELD_ID = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb'
const GAME_ID = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'

const field = {
  id: FIELD_ID,
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
  active_game: null,
  upcoming_games: [],
}

const closedField = {
  ...field,
  id: FIELD_ID,
  status: 'closed',
}

const otherField = {
  ...field,
  id: OTHER_FIELD_ID,
  name: 'North Court',
  latitude: 31.228,
  longitude: 34.78,
}

const openGame = {
  id: GAME_ID,
  field_id: FIELD_ID,
  status: 'open',
  sport_type: 'football',
  players_present: 4,
  max_players: 10,
  created_by: 'creator-1',
  started_at: '2099-07-12T10:00:00Z',
  expires_at: '2099-07-12T12:00:00Z',
  participants: [],
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
    localStorage.setItem('userCity', 'ירושלים') // E08-02 follow-up fix: account needs a resolved city to reach the map
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
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

async function mockMapPageRequests(page, { fields = [field], games = {} } = {}) {
  await page.route(/\/fields\/?(\?.*)?$/, (route) => fulfillJson(route, fields))
  await page.route(/\/notifications(\/.*)?(\?.*)?$/, (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/unread-count')) {
      return fulfillJson(route, { unread_count: 0 })
    }
    return fulfillJson(route, [])
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())

  await page.route(/\/fields\/[0-9a-f-]+$/i, (route) => {
    // The "/fields/{id}" API path is also a valid (legacy) SPA route path,
    // so this mock must not swallow the page's own navigation request when
    // a test loads that URL directly — only intercept the XHR to the API.
    if (route.request().resourceType() !== 'fetch' && route.request().resourceType() !== 'xhr') {
      return route.continue()
    }

    const id = new URL(route.request().url()).pathname.split('/').filter(Boolean).pop()
    if (id === NETWORK_ERROR_FIELD_ID) {
      return route.abort('connectionrefused')
    }
    const matched = fields.find((candidate) => candidate.id === id)
    if (matched) {
      return fulfillJson(route, matched)
    }
    return fulfillJson(route, { error: true, code: 'FIELD_NOT_FOUND', message: 'Field not found' }, 404)
  })

  await page.route(/\/games\/[0-9a-f-]+$/i, (route) => {
    const id = new URL(route.request().url()).pathname.split('/').filter(Boolean).pop()
    const behavior = games[id]

    if (!behavior) {
      return fulfillJson(route, { error: true, code: 'GAME_NOT_FOUND', message: 'Game not found' }, 404)
    }
    return fulfillJson(route, behavior)
  })
}

test.beforeEach(async ({ page }) => {
  await seedAuthenticatedUser(page)
})

test('opens an existing field from a /field/{id} deep link', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [field] })

  await page.goto(`/field/${FIELD_ID}`)

  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: field.name }),
  ).toBeVisible()
  // The URL is normalized back to canonical map state after resolution.
  await expect(page).toHaveURL(/\/$/)
})

test('keeps a field resolved from a deep link in the warm-load marker cache', async ({ page }) => {
  await page.route(/\/notifications(\/.*)?(\?.*)?$/, (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/unread-count')) {
      return fulfillJson(route, { unread_count: 0 })
    }
    return fulfillJson(route, [])
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
  await page.route(/\/fields\/[0-9a-f-]+$/i, (route) => fulfillJson(route, field))
  await page.route(/\/fields\/?(\?.*)?$/, async (route) => {
    await new Promise((resolve) => {
      setTimeout(resolve, 1000)
    })

    return fulfillJson(route, [])
  })

  await page.goto(`/field/${FIELD_ID}`)

  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: field.name }),
  ).toBeVisible()
  await expect(page.locator('.field-marker-icon')).toHaveCount(1)
  await expect
    .poll(() =>
      page.evaluate(() => JSON.parse(localStorage.getItem('cached_fields') ?? '[]')
        .map((cachedField) => cachedField.id)),
    )
    .toContain(FIELD_ID)

  await page.goto('/')
  await page.waitForTimeout(100)

  await expect(page.locator('.field-marker-icon')).toHaveCount(1)
  await expect(page.locator('.map-loading')).toHaveCount(0)
})

test('resolves the legacy /fields/{id} path the same way', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [field] })

  await page.goto(`/fields/${FIELD_ID}`)

  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: field.name }),
  ).toBeVisible()
})

test('opens a closed field with its existing status display, without new UI', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [closedField] })

  await page.goto(`/field/${FIELD_ID}`)

  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: closedField.name }),
  ).toBeVisible()
  // Same panel a marker click would show — the status row already exists.
  await expect(page.getByText('Closed')).toBeVisible()
})

test('shows the unavailable state for a missing field without crashing', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [field] })

  await page.goto(`/field/${MISSING_FIELD_ID}`)

  await expect(page.getByRole('alert')).toContainText(
    'This field is unavailable. It may have been removed.',
  )
  await expect(page.getByLabel('Field details')).toHaveCount(0)
  await expect(page.locator('.map-loading')).toHaveCount(0)
  await expect(page.locator('.field-marker-icon')).toHaveCount(1)
})

test('fails gracefully on a malformed UUID without crashing or showing an error', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [field] })

  await page.goto('/field/not-a-uuid')

  await expect(page.locator('.field-marker-icon')).toHaveCount(1)
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.getByLabel('Field details')).toHaveCount(0)
})

test('fails gracefully on an unsupported route without crashing', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [field] })

  await page.goto('/definitely/not/a/route')

  await expect(page.locator('.field-marker-icon')).toHaveCount(1)
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('shows a load-error state on network failure, distinct from not-found', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [field] })

  await page.goto(`/field/${NETWORK_ERROR_FIELD_ID}`)

  await expect(page.getByRole('alert')).toContainText(
    'Could not load this field. Check your connection and try again.',
  )
})

test('does not regress existing marker-click field navigation after a field deep link resolves', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [field, otherField] })

  await page.goto(`/field/${FIELD_ID}`)
  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: field.name }),
  ).toBeVisible()

  await page.getByLabel('Close').click()
  await page.locator('.field-marker-icon').nth(1).evaluate((marker) => marker.click())

  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: otherField.name }),
  ).toBeVisible()
})

test('does not regress the game deep-link flow from ISSUE-272', async ({ page }) => {
  await mockMapPageRequests(page, {
    fields: [{ ...field, active_game: openGame }],
    games: { [GAME_ID]: openGame },
  })

  await page.goto(`/game/${GAME_ID}`)

  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: field.name }),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: "I'm coming" })).toBeVisible()
})
