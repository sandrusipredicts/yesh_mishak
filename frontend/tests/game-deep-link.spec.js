import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

const user = {
  id: 'regular-user-1',
  email: 'user@example.com',
  name: 'Regular User',
  role: 'user',
}

const FIELD_ID = '11111111-1111-4111-8111-111111111111'
const OPEN_GAME_ID = '22222222-2222-4222-8222-222222222222'
const FINISHED_GAME_ID = '33333333-3333-4333-8333-333333333333'
const CANCELLED_GAME_ID = '44444444-4444-4444-8444-444444444444'
const MISSING_GAME_ID = '55555555-5555-4555-8555-555555555555'
const OTHER_FIELD_ID = '66666666-6666-4666-8666-666666666666'

const baseField = {
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

const otherField = {
  ...baseField,
  id: OTHER_FIELD_ID,
  name: 'North Court',
  latitude: 31.228,
  longitude: 34.78,
}

const baseGame = {
  field_id: FIELD_ID,
  sport_type: 'football',
  players_present: 4,
  max_players: 10,
  created_by: 'creator-1',
  started_at: '2026-07-12T10:00:00Z',
  expires_at: '2026-07-12T12:00:00Z',
  participants: [],
}

const openGame = { ...baseGame, id: OPEN_GAME_ID, status: 'open' }
const finishedGame = { ...baseGame, id: FINISHED_GAME_ID, status: 'finished' }
const cancelledGame = { ...baseGame, id: CANCELLED_GAME_ID, status: 'cancelled' }

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

async function mockMapPageRequests(page, { fields = [baseField], games = {} } = {}) {
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
    const id = new URL(route.request().url()).pathname.split('/').filter(Boolean).pop()
    const matched = fields.find((field) => field.id === id)
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
    if (behavior === 'network-error') {
      return route.abort('connectionrefused')
    }
    return fulfillJson(route, behavior)
  })
}

test.beforeEach(async ({ page }) => {
  await seedAuthenticatedUser(page)
})

test('opens an existing open game from a /game/{id} deep link', async ({ page }) => {
  await mockMapPageRequests(page, {
    fields: [{ ...baseField, active_game: openGame }],
    games: { [OPEN_GAME_ID]: openGame },
  })

  await page.goto(`/game/${OPEN_GAME_ID}`)

  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: baseField.name }),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: "I'm coming" })).toBeVisible()
  // The URL is normalized back to canonical map state after resolution.
  await expect(page).toHaveURL(/\/$/)
})

test('opens a finished game with its ended state, without recreating it', async ({ page }) => {
  await mockMapPageRequests(page, {
    fields: [baseField],
    games: { [FINISHED_GAME_ID]: finishedGame },
  })

  await page.goto(`/game/${FINISHED_GAME_ID}`)

  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: baseField.name }),
  ).toBeVisible()
  await expect(page.getByText('This game has ended.')).toBeVisible()
  await expect(page.getByRole('button', { name: "I'm coming" })).toHaveCount(0)
})

test('opens a cancelled game with its ended state, without recreating it', async ({ page }) => {
  await mockMapPageRequests(page, {
    fields: [baseField],
    games: { [CANCELLED_GAME_ID]: cancelledGame },
  })

  await page.goto(`/game/${CANCELLED_GAME_ID}`)

  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: baseField.name }),
  ).toBeVisible()
  await expect(page.getByText('This game has ended.')).toBeVisible()
})

test('shows the unavailable state for a missing game without crashing', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [baseField], games: {} })

  await page.goto(`/game/${MISSING_GAME_ID}`)

  await expect(page.getByRole('alert')).toContainText(
    'This game is unavailable. It may have been removed.',
  )
  await expect(page.getByLabel('Field details')).toHaveCount(0)
  // Never remains stuck on a loading indicator.
  await expect(page.locator('.map-loading')).toHaveCount(0)
  // The map itself is still usable.
  await expect(page.locator('.field-marker-icon')).toHaveCount(1)
})

test('treats a deleted game the same as a missing game (both 404)', async ({ page }) => {
  // The backend has no hard-delete for games (schema.sql has no DELETE path
  // for the games table) — "deleted" and "missing" are the same 404
  // response in practice. This test documents that equivalence.
  await mockMapPageRequests(page, { fields: [baseField], games: {} })

  await page.goto(`/game/${MISSING_GAME_ID}`)

  await expect(page.getByRole('alert')).toContainText(
    'This game is unavailable. It may have been removed.',
  )
})

test('fails gracefully on a malformed UUID without crashing or showing an error', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [baseField], games: {} })

  await page.goto('/game/not-a-uuid')

  await expect(page.locator('.field-marker-icon')).toHaveCount(1)
  await expect(page.getByRole('alert')).toHaveCount(0)
  await expect(page.getByLabel('Field details')).toHaveCount(0)
})

test('fails gracefully on an unsupported route without crashing', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [baseField], games: {} })

  await page.goto('/definitely/not/a/route')

  await expect(page.locator('.field-marker-icon')).toHaveCount(1)
  await expect(page.getByRole('alert')).toHaveCount(0)
})

test('shows a load-error state on network failure, distinct from not-found', async ({ page }) => {
  await mockMapPageRequests(page, {
    fields: [baseField],
    games: { [OPEN_GAME_ID]: 'network-error' },
  })

  await page.goto(`/game/${OPEN_GAME_ID}`)

  await expect(page.getByRole('alert')).toContainText(
    'Could not load this game. Check your connection and try again.',
  )
})

test('does not regress existing marker-click field navigation after a deep link resolves', async ({ page }) => {
  await mockMapPageRequests(page, {
    fields: [{ ...baseField, active_game: openGame }, otherField],
    games: { [OPEN_GAME_ID]: openGame },
  })

  await page.goto(`/game/${OPEN_GAME_ID}`)
  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: baseField.name }),
  ).toBeVisible()

  await page.getByLabel('Close').click()
  await page.locator('.field-marker-icon').nth(1).evaluate((marker) => marker.click())

  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: otherField.name }),
  ).toBeVisible()
})

test('does not regress the existing /my-games route', async ({ page }) => {
  await page.route(/\/games\/me\/?(\?.*)?$/, (route) =>
    fulfillJson(route, { active_games: [], upcoming_games: [], past_games: [], cancelled_games: [] }),
  )
  await mockMapPageRequests(page, { fields: [baseField], games: {} })

  await page.goto('/')
  await page.getByRole('button', { name: 'My games' }).click()

  await expect(page).toHaveURL(/\/my-games$/)
})
