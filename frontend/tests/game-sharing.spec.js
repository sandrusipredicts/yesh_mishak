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
const FULL_GAME_ID = '44444444-4444-4444-8444-444444444444'
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
  started_at: '2026-07-12T10:00:00Z',
  expires_at: '2026-07-12T12:00:00Z',
  participants: [],
}

const openGame = { ...baseGame, id: OPEN_GAME_ID, status: 'open' }
const finishedGame = { ...baseGame, id: FINISHED_GAME_ID, status: 'finished' }
const fullGame = { ...baseGame, id: FULL_GAME_ID, status: 'full', players_present: 10 }
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

// @capacitor/share's web implementation (node_modules/@capacitor/share/dist/esm/web.js)
// delegates canShare()/share() directly to navigator.share, and
// Capacitor.getPlatform() resolves to 'web' with no native bridge present —
// so mocking navigator.share is sufficient to drive the real production
// code path in a Chromium/Playwright context, no bridge simulation needed.
async function mockNativeShare(page, { mode = 'available' } = {}) {
  await page.addInitScript((shareMode) => {
    window.__shareCalls = []

    if (shareMode === 'unavailable') {
      // ShareWeb.canShare() treats a missing navigator.share as unavailable.
      Object.defineProperty(navigator, 'share', { value: undefined, configurable: true })
      return
    }

    navigator.share = async (data) => {
      window.__shareCalls.push(data)
      if (shareMode === 'cancel') {
        const err = new Error('Share canceled')
        err.name = 'AbortError'
        throw err
      }
      if (shareMode === 'fail') {
        throw new Error('Native bridge failed')
      }
      return undefined
    }
  }, mode)
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

async function openFieldDetails(page) {
  await page.goto('/')
  await page.locator('.field-marker-icon').first().evaluate((marker) => marker.click())
  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: baseField.name }),
  ).toBeVisible()
}

test.beforeEach(async ({ page }) => {
  await seedAuthenticatedUser(page)
})

test('shows the Share game button for an open game', async ({ page }) => {
  await mockNativeShare(page)
  await mockMapPageRequests(page, { fields: [{ ...baseField, active_game: openGame }] })

  await openFieldDetails(page)

  await expect(page.getByRole('button', { name: 'Share game' })).toBeVisible()
})

test('shows the Share game button for a full game', async ({ page }) => {
  await mockNativeShare(page)
  await mockMapPageRequests(page, { fields: [{ ...baseField, active_game: fullGame }] })

  await openFieldDetails(page)

  await expect(page.getByRole('button', { name: 'Share game' })).toBeVisible()
})

test('hides the Share game button for a finished game (product rule: only open/full games are shareable)', async ({ page }) => {
  await mockNativeShare(page)
  await mockMapPageRequests(page, { fields: [baseField], games: { [FINISHED_GAME_ID]: finishedGame } })

  await page.goto(`/game/${FINISHED_GAME_ID}`)
  await expect(page.getByText('This game has ended.')).toBeVisible()

  await expect(page.getByRole('button', { name: 'Share game' })).toHaveCount(0)
})

test('hides the Share game button for a cancelled game', async ({ page }) => {
  await mockNativeShare(page)
  await mockMapPageRequests(page, { fields: [baseField], games: { [CANCELLED_GAME_ID]: cancelledGame } })

  await page.goto(`/game/${CANCELLED_GAME_ID}`)
  await expect(page.getByText('This game has ended.')).toBeVisible()

  await expect(page.getByRole('button', { name: 'Share game' })).toHaveCount(0)
})

test('invokes native share with the correct localized payload and canonical deep link', async ({ page }) => {
  await mockNativeShare(page)
  await mockMapPageRequests(page, { fields: [{ ...baseField, active_game: openGame }] })

  await openFieldDetails(page)
  await page.getByRole('button', { name: 'Share game' }).click()

  await expect(page.getByText('Game shared.')).toBeVisible()
  await expect
    .poll(() => page.evaluate(() => window.__shareCalls))
    .toEqual([
      {
        title: 'Football game at Central Court - Yesh Mishak',
        text: '⚽ Game on!\n\n📍 Central Court\n👥 4 / 10 players\n\nJoin through Yesh Mishak:',
        url: `https://yesh-mishak.com/game/${OPEN_GAME_ID}`,
      },
    ])
})

test('a recipient opening the generated link resolves to the same game (ISSUE-272 deep link routing, unmodified)', async ({ page }) => {
  await mockNativeShare(page)
  await mockMapPageRequests(page, {
    fields: [{ ...baseField, active_game: openGame }],
    games: { [OPEN_GAME_ID]: openGame },
  })

  await openFieldDetails(page)
  await page.getByRole('button', { name: 'Share game' }).click()

  await expect.poll(() => page.evaluate(() => window.__shareCalls.length)).toBe(1)
  const [sharedCall] = await page.evaluate(() => window.__shareCalls)
  const sharedPath = new URL(sharedCall.url).pathname
  expect(sharedPath).toBe(`/game/${OPEN_GAME_ID}`)

  // Fresh page load at the shared link's pathname — the existing ISSUE-272
  // resolver (unmodified by this issue) is what opens the game.
  await page.goto(sharedPath)
  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: baseField.name }),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: "I'm coming" })).toBeVisible()
})

test('a previously shared finished-game link still opens via the unmodified ISSUE-272 deep link, hiding only the Share button', async ({ page }) => {
  await mockNativeShare(page)
  await mockMapPageRequests(page, { fields: [baseField], games: { [FINISHED_GAME_ID]: finishedGame } })

  // Simulates a recipient opening a link that was shared before this game
  // finished — the deep-link resolver itself is untouched by this issue.
  await page.goto(`/game/${FINISHED_GAME_ID}`)

  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: baseField.name }),
  ).toBeVisible()
  await expect(page.getByText('This game has ended.')).toBeVisible()
  await expect(page.getByRole('button', { name: "I'm coming" })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Share game' })).toHaveCount(0)
})

test('a previously shared cancelled-game link still opens via the unmodified ISSUE-272 deep link, hiding only the Share button', async ({ page }) => {
  await mockNativeShare(page)
  await mockMapPageRequests(page, { fields: [baseField], games: { [CANCELLED_GAME_ID]: cancelledGame } })

  await page.goto(`/game/${CANCELLED_GAME_ID}`)

  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: baseField.name }),
  ).toBeVisible()
  await expect(page.getByText('This game has ended.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Share game' })).toHaveCount(0)
})

test('a missing/deleted game link still shows the existing unavailable state, unaffected by the sharing rule change', async ({ page }) => {
  await mockNativeShare(page)
  await mockMapPageRequests(page, { fields: [baseField], games: {} })

  await page.goto('/game/66666666-6666-4666-8666-666666666666')

  await expect(page.getByRole('alert')).toContainText(
    'This game is unavailable. It may have been removed.',
  )
  await expect(page.getByLabel('Field details')).toHaveCount(0)
})

test('treats user cancellation as a normal outcome, not an error', async ({ page }) => {
  await mockNativeShare(page, { mode: 'cancel' })
  await mockMapPageRequests(page, { fields: [{ ...baseField, active_game: openGame }] })

  await openFieldDetails(page)
  await page.getByRole('button', { name: 'Share game' }).click()

  await expect(page.getByText('Game shared.')).toHaveCount(0)
  await expect(page.getByRole('alert')).toHaveCount(0)
  // The game panel remains usable — cancellation did not clear state.
  await expect(page.getByRole('button', { name: 'Share game' })).toBeEnabled()
})

test('shows a normalized failure message when native share invocation fails', async ({ page }) => {
  await mockNativeShare(page, { mode: 'fail' })
  await mockMapPageRequests(page, { fields: [{ ...baseField, active_game: openGame }] })

  await openFieldDetails(page)
  await page.getByRole('button', { name: 'Share game' }).click()

  await expect(page.getByRole('alert')).toContainText('Could not share this game. Please try again.')
})

test('falls back to clipboard when the platform cannot native-share, without crashing', async ({ page, context }) => {
  await context.grantPermissions(['clipboard-write'])
  await mockNativeShare(page, { mode: 'unavailable' })
  await mockMapPageRequests(page, { fields: [{ ...baseField, active_game: openGame }] })

  await openFieldDetails(page)
  await page.getByRole('button', { name: 'Share game' }).click()

  await expect(page.getByText('Message copied.')).toBeVisible()
  // The panel is still intact — no crash, no blank screen.
  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: baseField.name }),
  ).toBeVisible()
})

test('does not regress existing join/leave/close game actions', async ({ page }) => {
  await mockNativeShare(page)
  await mockMapPageRequests(page, { fields: [{ ...baseField, active_game: { ...openGame, participants: [] } }] })

  await openFieldDetails(page)

  await expect(page.getByRole('button', { name: "I'm coming" })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Share game' })).toBeVisible()
})
