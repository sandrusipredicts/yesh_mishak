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
const CANCELLED_GAME_ID = '55555555-5555-4555-8555-555555555555'

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
  started_at: '2099-07-12T10:00:00Z',
  expires_at: '2099-07-12T12:00:00Z',
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

test('shows the Add to calendar button for an open game', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [{ ...baseField, active_game: openGame }] })

  await openFieldDetails(page)

  await expect(page.getByRole('button', { name: 'Add to calendar' })).toBeVisible()
})

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

test('downloads a valid .ics file with correct event data on the web fallback path', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [{ ...baseField, active_game: openGame }] })

  await openFieldDetails(page)

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Add to calendar' }).click(),
  ])

  expect(download.suggestedFilename()).toBe(`game-${OPEN_GAME_ID}.ics`)

  const stream = await download.createReadStream()
  const chunks = []
  for await (const chunk of stream) {
    chunks.push(chunk)
  }
  const content = Buffer.concat(chunks).toString('utf-8')

  expect(content).toContain('BEGIN:VCALENDAR')
  expect(content).toContain('DTSTART:20990712T100000Z')
  expect(content).toContain('DTEND:20990712T120000Z')
  expect(content).toContain('LOCATION:Central Court')
  expect(content).toContain(`URL:https://yesh-mishak.com/game/${OPEN_GAME_ID}`)

  await expect(page.getByText('Calendar file downloaded. Open it to add the event to your calendar.')).toBeVisible()
})

test('shows the correct Hebrew label and confirmation copy', async ({ page }) => {
  await seedAuthenticatedUser(page, { language: 'he' })
  await mockMapPageRequests(page, { fields: [{ ...baseField, active_game: openGame }] })

  await openFieldDetails(page, { fieldDetailsLabel: 'פרטי מגרש' })

  await expect(page.getByRole('button', { name: 'הוסף ליומן' })).toBeVisible()

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'הוסף ליומן' }).click(),
  ])
  expect(download.suggestedFilename()).toBe(`game-${OPEN_GAME_ID}.ics`)

  await expect(page.getByText('קובץ יומן הורד. פתחו אותו כדי להוסיף את האירוע ליומן.')).toBeVisible()
})

test('does not regress existing join/leave/share game actions', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [{ ...baseField, active_game: { ...openGame, participants: [] } }] })

  await openFieldDetails(page)

  await expect(page.getByRole('button', { name: "I'm coming" })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Share game' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Add to calendar' })).toBeVisible()
})
