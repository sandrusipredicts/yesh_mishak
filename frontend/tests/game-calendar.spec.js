import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

const user = {
  id: 'regular-user-1',
  email: 'user@example.com',
  name: 'Regular User',
  role: 'user',
}

const FIELD_ID = '11111111-1111-4111-8111-111111111111'
const ACTIVE_GAME_ID = '22222222-2222-4222-8222-222222222222'
const FINISHED_GAME_ID = '33333333-3333-4333-8333-333333333333'
const SCHEDULED_GAME_ID = '44444444-4444-4444-8444-444444444444'
const CANCELLED_GAME_ID = '55555555-5555-4555-8555-555555555555'
const FULL_ACTIVE_GAME_ID = '66666666-6666-4666-8666-666666666666'

const ONE_HOUR_MS = 60 * 60 * 1000
const ONE_DAY_MS = 24 * ONE_HOUR_MS

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

const baseGame = {
  field_id: FIELD_ID,
  sport_type: 'football',
  players_present: 4,
  max_players: 10,
  created_by: 'creator-1',
  participants: [],
}

// A genuinely active/in-progress game: no scheduled_at, started in the
// recent past, not yet expired.
const activeGame = {
  ...baseGame,
  id: ACTIVE_GAME_ID,
  status: 'open',
  scheduled_at: null,
  started_at: new Date(Date.now() - ONE_HOUR_MS).toISOString(),
  expires_at: new Date(Date.now() + ONE_HOUR_MS).toISOString(),
}

const fullActiveGame = {
  ...activeGame,
  id: FULL_ACTIVE_GAME_ID,
  status: 'full',
  players_present: 10,
}

// A genuinely upcoming/scheduled game: valid future scheduled_at (backend
// convention: started_at mirrors scheduled_at until the game begins —
// backend/app/routers/game_lifecycle.py `started_at = scheduled_at or now`).
const scheduledFutureIso = new Date(Date.now() + ONE_DAY_MS).toISOString()
const scheduledGame = {
  ...baseGame,
  id: SCHEDULED_GAME_ID,
  status: 'open',
  scheduled_at: scheduledFutureIso,
  started_at: scheduledFutureIso,
  expires_at: new Date(Date.now() + ONE_DAY_MS + 2 * ONE_HOUR_MS).toISOString(),
}

const finishedGame = { ...activeGame, id: FINISHED_GAME_ID, status: 'finished' }
const cancelledGame = { ...activeGame, id: CANCELLED_GAME_ID, status: 'cancelled' }

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

async function seedAuthenticatedUser(page, { language = 'en' } = {}) {
  const token = makeJwtWithSubject(user.id)

  await page.addInitScript((storedUser) => {
    localStorage.setItem('access_token', storedUser.token)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('app_language', storedUser.language)
    localStorage.setItem('language_selected', 'true')
  }, { ...user, token, language })
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
    if (route.request().resourceType() !== 'fetch' && route.request().resourceType() !== 'xhr') {
      return route.continue()
    }

    const id = new URL(route.request().url()).pathname.split('/').filter(Boolean).pop()
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

async function openFieldDetails(page, { fieldDetailsLabel = 'Field details' } = {}) {
  await page.goto('/')
  await page.locator('.field-marker-icon').first().evaluate((marker) => marker.click())
  await expect(
    page.getByLabel(fieldDetailsLabel).getByRole('heading', { name: baseField.name }),
  ).toBeVisible()
}

test.beforeEach(async ({ page }) => {
  await seedAuthenticatedUser(page)
})

// On a plain web/Chromium context Capacitor.isNativePlatform() is false and
// the calendar plugin is never registered, so the production code path
// exercises the real .ics download fallback end to end — no bridge
// simulation needed, same reasoning as mockNativeShare() in
// game-sharing.spec.js for @capacitor/share's web implementation.

// --- eligibility: upcoming/scheduled game (must show) ---

test('shows the Add to calendar button for an upcoming/scheduled game (manual-verification regression)', async ({ page }) => {
  // Reproduces the exact scenario from manual Android verification: a field
  // with no active_game, only a scheduled game in upcoming_games, rendered
  // through FieldDetailsPanel's second GamePanel call site (the
  // `.upcoming-games-section` / `.upcoming-game-card` list), not the
  // `.active-game-summary` one used elsewhere in this file.
  await mockMapPageRequests(page, {
    fields: [{ ...baseField, active_game: null, upcoming_games: [scheduledGame] }],
  })

  await openFieldDetails(page)

  await expect(page.getByRole('heading', { name: 'Upcoming games' })).toBeVisible()
  await expect(
    page.locator('.upcoming-game-card').getByRole('button', { name: 'Add to calendar' }),
  ).toBeVisible()
  // Same regression coverage for the pre-existing action that shares
  // isGameShareable() (not the calendar rule), to distinguish a real code
  // regression from a stale/old build missing everything equally.
  await expect(
    page.locator('.upcoming-game-card').getByRole('button', { name: 'Copy game link' }),
  ).toBeVisible()
})

// --- eligibility: active game (bug fix — must NOT show, regardless of status) ---

test('hides the Add to calendar button for an active open game, even though it is still shareable', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [{ ...baseField, active_game: activeGame }] })

  await openFieldDetails(page)

  await expect(page.getByRole('button', { name: 'Add to calendar' })).toHaveCount(0)
  // Share and Copy link must remain available for an active game — only
  // calendar eligibility changed.
  await expect(page.getByRole('button', { name: 'Share game' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Copy game link' })).toBeVisible()
})

test('hides the Add to calendar button for an active full game', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [{ ...baseField, active_game: fullActiveGame }] })

  await openFieldDetails(page)

  await expect(page.getByRole('button', { name: 'Add to calendar' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Share game' })).toBeVisible()
})

// --- eligibility: terminal statuses (must NOT show) ---

test('hides the Add to calendar button for a finished game', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [baseField], games: { [FINISHED_GAME_ID]: finishedGame } })

  await page.goto(`/game/${FINISHED_GAME_ID}`)
  await expect(page.getByText('This game has ended.')).toBeVisible()

  await expect(page.getByRole('button', { name: 'Add to calendar' })).toHaveCount(0)
})

test('hides the Add to calendar button for a cancelled game', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [baseField], games: { [CANCELLED_GAME_ID]: cancelledGame } })

  await page.goto(`/game/${CANCELLED_GAME_ID}`)
  await expect(page.getByText('This game has ended.')).toBeVisible()

  await expect(page.getByRole('button', { name: 'Add to calendar' })).toHaveCount(0)
})

// --- eligibility: missing/invalid/past scheduled_at (must NOT show) ---

test('hides the Add to calendar button when scheduled_at is missing on an otherwise-open game', async ({ page }) => {
  await mockMapPageRequests(page, {
    fields: [{ ...baseField, active_game: null, upcoming_games: [{ ...scheduledGame, scheduled_at: null, started_at: null }] }],
  })

  await openFieldDetails(page)

  await expect(page.getByRole('button', { name: 'Add to calendar' })).toHaveCount(0)
})

test('hides the Add to calendar button when scheduled_at is already in the past', async ({ page }) => {
  const pastScheduled = new Date(Date.now() - ONE_HOUR_MS).toISOString()
  await mockMapPageRequests(page, {
    fields: [{ ...baseField, active_game: { ...scheduledGame, scheduled_at: pastScheduled, started_at: pastScheduled } }],
  })

  await openFieldDetails(page)

  await expect(page.getByRole('button', { name: 'Add to calendar' })).toHaveCount(0)
})

// --- calendar creation still works for an eligible upcoming game ---

test('downloads a valid .ics file with correct event data for an eligible upcoming game', async ({ page }) => {
  await mockMapPageRequests(page, {
    fields: [{ ...baseField, active_game: null, upcoming_games: [scheduledGame] }],
  })

  await openFieldDetails(page)

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.locator('.upcoming-game-card').getByRole('button', { name: 'Add to calendar' }).click(),
  ])

  expect(download.suggestedFilename()).toBe(`game-${SCHEDULED_GAME_ID}.ics`)

  const stream = await download.createReadStream()
  const chunks = []
  for await (const chunk of stream) {
    chunks.push(chunk)
  }
  const content = Buffer.concat(chunks).toString('utf-8')

  expect(content).toContain('BEGIN:VCALENDAR')
  expect(content).toContain('LOCATION:Central Court')
  expect(content).toContain(`URL:https://yesh-mishak.com/game/${SCHEDULED_GAME_ID}`)

  await expect(
    page.locator('.upcoming-game-card').getByText('Calendar file downloaded. Open it to add the event to your calendar.'),
  ).toBeVisible()
})

test('shows the correct Hebrew label and confirmation copy for an eligible upcoming game', async ({ page }) => {
  await seedAuthenticatedUser(page, { language: 'he' })
  await mockMapPageRequests(page, {
    fields: [{ ...baseField, active_game: null, upcoming_games: [scheduledGame] }],
  })

  await openFieldDetails(page, { fieldDetailsLabel: 'פרטי מגרש' })

  const upcomingCard = page.locator('.upcoming-game-card')
  await expect(upcomingCard.getByRole('button', { name: 'הוסף ליומן' })).toBeVisible()

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    upcomingCard.getByRole('button', { name: 'הוסף ליומן' }).click(),
  ])
  expect(download.suggestedFilename()).toBe(`game-${SCHEDULED_GAME_ID}.ics`)

  await expect(upcomingCard.getByText('קובץ יומן הורד. פתחו אותו כדי להוסיף את האירוע ליומן.')).toBeVisible()
})

// --- regression: existing join/leave/share/close actions on an active game ---

test('does not regress existing join/leave/share game actions on an active game', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [{ ...baseField, active_game: { ...activeGame, participants: [] } }] })

  await openFieldDetails(page)

  await expect(page.getByRole('button', { name: "I'm coming" })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Share game' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Add to calendar' })).toHaveCount(0)
})
