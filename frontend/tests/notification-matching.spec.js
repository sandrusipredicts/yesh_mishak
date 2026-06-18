import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

const FIELD_ID = 'field-codex-notification-test'
const FIELD_NAME = 'Codex notification test field'
const CITY = 'ירוחם'
const CITY_PREFIX = 'יר'

const users = {
  userA: {
    id: 'user-a',
    email: 'a@example.com',
    name: 'User A',
  },
  userB: {
    id: 'user-b',
    email: 'b@example.com',
    name: 'User B',
  },
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

function getUserIdFromRequest(request) {
  const authorization = request.headers().authorization || ''
  const token = authorization.replace(/^Bearer\s+/i, '')
  const payload = token.split('.')[1]

  if (!payload) {
    return ''
  }

  try {
    return JSON.parse(Buffer.from(payload, 'base64url').toString('utf8')).sub || ''
  } catch {
    return ''
  }
}

function fulfillJson(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    headers: {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'authorization,content-type',
      'Access-Control-Allow-Methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
    },
    body: JSON.stringify(body),
  })
}

function createField(activeGame = null) {
  return {
    id: FIELD_ID,
    name: FIELD_NAME,
    lat: 30.9872,
    lng: 34.9314,
    city: CITY,
    sport_type: 'football',
    approval_status: 'approved',
    active_game: activeGame,
  }
}

function createState() {
  return {
    fields: [createField()],
    games: [],
    notifications: [],
    preferences: {
      [users.userA.id]: [],
      [users.userB.id]: [],
    },
    pushTokens: [],
  }
}

function notificationMatchesPreference(preference, field, sportType) {
  if (!preference.enabled || preference.sport_type !== 'both' && preference.sport_type !== sportType) {
    return false
  }

  if (preference.notification_type === 'specific_field') {
    return Boolean(preference.field_id) && preference.field_id === field.id
  }

  if (preference.notification_type === 'city') {
    return preference.city?.trim().toLowerCase() === field.city?.trim().toLowerCase()
  }

  if (preference.notification_type === 'radius') {
    return false
  }

  return false
}

function createNotificationForGame(state, game, field, userId) {
  const existing = state.notifications.find(
    (notification) =>
      notification.user_id === userId &&
      notification.type === 'game_created' &&
      notification.game_id === game.id,
  )

  if (existing) {
    return
  }

  state.notifications.push({
    id: `notification-${state.notifications.length + 1}`,
    user_id: userId,
    type: 'game_created',
    title: 'נפתח משחק חדש',
    body: `נפתח משחק ${game.sport_type} במגרש ${field.name}`,
    game_id: game.id,
    field_id: field.id,
    read_at: null,
    created_at: new Date().toISOString(),
  })
}

function createGame(state, body, organizerId) {
  const field = state.fields.find((candidateField) => candidateField.id === body.field_id)
  const game = {
    id: `game-${state.games.length + 1}`,
    field_id: body.field_id,
    created_by: organizerId,
    sport_type: body.sport_type,
    players_present: body.players_present,
    max_players: body.max_players,
    status: 'open',
    participants: [{ user_id: organizerId, name: organizerId }],
  }

  state.games.push(game)
  state.fields = state.fields.map((candidateField) =>
    candidateField.id === field.id ? { ...candidateField, active_game: game } : candidateField,
  )

  for (const [userId, preferences] of Object.entries(state.preferences)) {
    if (userId === organizerId) {
      continue
    }

    if (preferences.some((preference) => notificationMatchesPreference(preference, field, game.sport_type))) {
      createNotificationForGame(state, game, field, userId)
    }
  }

  return game
}

function settingsToPreferences(userId, body) {
  const preferences = [
    {
      id: `pref-${userId}-radius`,
      user_id: userId,
      enabled: body.distance_enabled,
      sport_type: 'both',
      notification_type: 'radius',
      radius_km: body.distance_radius_km,
      lat: body.distance_lat,
      lng: body.distance_lng,
    },
    {
      id: `pref-${userId}-city`,
      user_id: userId,
      enabled: body.city_enabled,
      sport_type: 'both',
      notification_type: 'city',
      city: body.city_name,
    },
  ]

  if (body.specific_fields_enabled) {
    for (const fieldId of body.selected_field_ids || []) {
      preferences.push({
        id: `pref-${userId}-specific-${fieldId}`,
        user_id: userId,
        enabled: true,
        sport_type: 'both',
        notification_type: 'specific_field',
        field_id: fieldId,
      })
    }
  }

  return preferences
}

async function routeMockBackend(page, state) {
  const backendOrigins = [
    'http://localhost:8001',
    'http://127.0.0.1:8001',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://localhost:5173',
    'http://127.0.0.1:5173',
  ]

  for (const origin of backendOrigins) {
    await page.route(`${origin}/fields**`, (route) => {
    const url = new URL(route.request().url())
    if (route.request().method() === 'OPTIONS') {
      return fulfillJson(route, {})
    }

    if (url.pathname === '/fields' || url.pathname === '/fields/') {
      return fulfillJson(route, state.fields)
    }

    const fieldId = url.pathname.replace('/fields/', '')
    const field = state.fields.find((candidateField) => candidateField.id === fieldId)
    return fulfillJson(route, field || { detail: 'Field not found' }, field ? 200 : 404)
    })

    await page.route(`${origin}/notifications**`, (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (request.method() === 'OPTIONS') {
      return fulfillJson(route, {})
    }
    const userId = getUserIdFromRequest(request)
    const userNotifications = state.notifications.filter((notification) => notification.user_id === userId)

    if (request.method() === 'GET' && url.pathname === '/notifications') {
      return fulfillJson(route, userNotifications)
    }

    if (request.method() === 'GET' && url.pathname === '/notifications/unread-count') {
      return fulfillJson(route, { unread_count: userNotifications.filter((notification) => !notification.read_at).length })
    }

    if (request.method() === 'GET' && url.pathname === '/notifications/preferences') {
      return fulfillJson(route, state.preferences[userId] || [])
    }

    if (request.method() === 'PUT' && url.pathname === '/notifications/preferences') {
      state.preferences[userId] = settingsToPreferences(userId, request.postDataJSON())
      return fulfillJson(route, {
        message: 'Preferences saved',
        preferences: state.preferences[userId],
      })
    }

    if (request.method() === 'POST' && url.pathname === '/notifications/push-token') {
      state.pushTokens.push({ user_id: userId, token: request.postDataJSON().token })
      return fulfillJson(route, { message: 'Push token saved' })
    }

    return fulfillJson(route, { detail: 'Unhandled notification mock' }, 404)
    })

    await page.route(`${origin}/games/`, (route) => {
    if (route.request().method() === 'OPTIONS') {
      return fulfillJson(route, {})
    }

    const organizerId = getUserIdFromRequest(route.request())
    const game = createGame(state, route.request().postDataJSON(), organizerId)
    return fulfillJson(route, { message: 'Game created', game })
    })
  }

  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
}

async function seedAuthenticatedUser(page, user) {
  await page.addInitScript((storedUser) => {
    localStorage.setItem('access_token', storedUser.token)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.setItem('onboarding_done', 'true')
  }, { ...user, token: makeJwtWithSubject(user.id) })
}

async function openAppForUser(page, state, user) {
  await seedAuthenticatedUser(page, user)
  await routeMockBackend(page, state)
  await page.goto('http://127.0.0.1:5173/')
  await expect(page.getByRole('button', { name: /Notifications/ })).toBeVisible()
}

async function openPreferences(page) {
  await page.getByRole('button', { name: 'Notification preferences' }).click()
  await expect(page.getByRole('heading', { name: 'Notification Preferences' })).toBeVisible()
}

async function saveSpecificFieldPreference(page, enabled) {
  await openPreferences(page)
  await page.getByLabel('Distance notifications').uncheck()
  await page.getByLabel('City notifications').uncheck()
  await page.getByLabel('Specific fields notifications').setChecked(true)
  await page.getByLabel(FIELD_NAME).setChecked(enabled)
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByText('Notification preferences saved.')).toBeVisible()
  await page.getByRole('button', { name: 'Close' }).click()
}

async function saveCityPreference(page) {
  await openPreferences(page)
  await page.getByLabel('Distance notifications').uncheck()
  await page.getByLabel('City notifications').check()
  await page.getByRole('combobox', { name: 'City' }).fill(CITY_PREFIX)
  await page.getByRole('option', { name: CITY, exact: true }).click()
  await page.getByLabel('Specific fields notifications').uncheck()
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByText('Notification preferences saved.')).toBeVisible()
  await page.getByRole('button', { name: 'Close' }).click()
}

async function openGameOnField(page, user) {
  const token = makeJwtWithSubject(user.id)

  await page.evaluate(async ({ fieldId, nextToken }) => {
    const previousToken = localStorage.getItem('access_token')
    localStorage.setItem('access_token', nextToken)
    const response = await fetch('http://localhost:8001/games/', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${localStorage.getItem('access_token')}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        field_id: fieldId,
        sport_type: 'football',
        players_present: 1,
        max_players: 10,
      }),
    })

    if (!response.ok) {
      throw new Error(`Could not open game: ${response.status}`)
    }

    if (previousToken) {
      localStorage.setItem('access_token', previousToken)
    }
  }, { fieldId: FIELD_ID, nextToken: token })
}

async function expectNotificationCount(page, count) {
  if (count) {
    await expect(page.getByRole('button', { name: new RegExp(`Notifications, ${count} unread`) })).toBeVisible()
  } else {
    await expect(page.getByRole('button', { name: 'Notifications' })).toBeVisible()
  }

  await page.getByRole('button', { name: /Notifications/ }).click()
  if (count) {
    await expect(page.getByText(`נפתח משחק football במגרש ${FIELD_NAME}`)).toHaveCount(count)
  } else {
    await expect(page.getByText('No notifications yet.')).toBeVisible()
  }
}

test('specific field match creates one in-app notification for another user', async ({ page }) => {
  const state = createState()
  await openAppForUser(page, state, users.userA)
  await saveSpecificFieldPreference(page, true)

  await openGameOnField(page, users.userB)

  await expectNotificationCount(page, 1)
})

test('unchecked specific field creates no new notification', async ({ page }) => {
  const state = createState()
  state.preferences[users.userA.id] = [
    {
      id: 'stale-specific-field',
      user_id: users.userA.id,
      enabled: true,
      sport_type: 'both',
      notification_type: 'specific_field',
      field_id: FIELD_ID,
    },
  ]
  await openAppForUser(page, state, users.userA)
  await saveSpecificFieldPreference(page, false)

  await openGameOnField(page, users.userB)

  expect(state.preferences[users.userA.id].some((preference) => preference.field_id === FIELD_ID)).toBe(false)
  expect(state.notifications).toHaveLength(0)
  await expectNotificationCount(page, 0)
})

test('city-only match creates an in-app notification', async ({ page }) => {
  const state = createState()
  await openAppForUser(page, state, users.userA)
  await saveCityPreference(page)

  await openGameOnField(page, users.userB)

  await expectNotificationCount(page, 1)
})

test('city and specific field matching same game create one notification', async ({ page }) => {
  const state = createState()
  state.preferences[users.userA.id] = [
    {
      id: 'city',
      user_id: users.userA.id,
      enabled: true,
      sport_type: 'both',
      notification_type: 'city',
      city: CITY,
    },
    {
      id: 'specific',
      user_id: users.userA.id,
      enabled: true,
      sport_type: 'both',
      notification_type: 'specific_field',
      field_id: FIELD_ID,
    },
  ]
  await openAppForUser(page, state, users.userA)

  await openGameOnField(page, users.userB)

  expect(state.notifications.filter((notification) => notification.user_id === users.userA.id)).toHaveLength(1)
  await expectNotificationCount(page, 1)
})

test('organizer does not receive notification for own game', async ({ page }) => {
  const state = createState()
  state.preferences[users.userA.id] = [
    {
      id: 'own-city',
      user_id: users.userA.id,
      enabled: true,
      sport_type: 'both',
      notification_type: 'city',
      city: CITY,
    },
    {
      id: 'own-specific',
      user_id: users.userA.id,
      enabled: true,
      sport_type: 'both',
      notification_type: 'specific_field',
      field_id: FIELD_ID,
    },
  ]
  await openAppForUser(page, state, users.userA)

  await openGameOnField(page, users.userA)

  expect(state.notifications).toHaveLength(0)
  await expectNotificationCount(page, 0)
})

test('preferences save and reload persists checkbox state', async ({ page }) => {
  const state = createState()
  await openAppForUser(page, state, users.userA)

  await saveSpecificFieldPreference(page, true)
  await page.reload()
  await openPreferences(page)

  await expect(page.getByLabel('Specific fields notifications')).toBeChecked()
  await expect(page.getByLabel(FIELD_NAME)).toBeChecked()
})
