import assert from 'node:assert/strict'
import test from 'node:test'

import { cancelGameReminder, getStoredGameReminder, scheduleGameReminder } from '../src/api/gameReminders.js'
import en from '../src/locales/en/common.js'

function resolveKey(key) {
  return key.split('.').reduce((node, part) => node?.[part], en)
}

function t(key, options = {}) {
  const template = resolveKey(key)
  if (typeof template !== 'string') {
    return typeof options === 'string' ? options : key
  }
  return template.replace(/\{\{(\w+)\}\}/g, (_, name) => String(options[name] ?? ''))
}

// Node has no global localStorage; this project's own browser code (e.g.
// api/sessionStorage.js) relies on the real one, so tests stub a minimal
// in-memory implementation on globalThis for the duration of the file —
// the module under test reads `localStorage` as a free variable, so it
// resolves against whatever is on globalThis at call time.
function installFakeLocalStorage() {
  const store = new Map()
  globalThis.localStorage = {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, String(value)),
    removeItem: (key) => store.delete(key),
  }
}

const GAME_ID = '987e6543-e21b-42d3-a456-426614174999'
const ONE_HOUR_MS = 60 * 60 * 1000

function makeGame(overrides = {}) {
  return {
    id: GAME_ID,
    sport_type: 'football',
    scheduled_at: new Date(Date.now() + 3 * ONE_HOUR_MS).toISOString(),
    ...overrides,
  }
}

test.beforeEach(() => {
  installFakeLocalStorage()
})

// --- unavailable resource (no plugin call at all) ---

test('returns unavailable and never calls the notification plugin for an ineligible game', async () => {
  let scheduleCalled = false
  const result = await scheduleGameReminder(
    { game: makeGame({ scheduled_at: null }), fieldName: 'Central Court', t },
    { scheduleNotification: async () => { scheduleCalled = true; return { outcome: 'scheduled' } } },
  )

  assert.deepEqual(result, { outcome: 'unavailable', reason: 'invalid-resource' })
  assert.equal(scheduleCalled, false)
  assert.equal(getStoredGameReminder(GAME_ID), null)
})

// --- successful scheduling persists the record ---

test('persists the notification id and remind time after a successful schedule', async () => {
  const result = await scheduleGameReminder(
    { game: makeGame(), fieldName: 'Central Court', t },
    { scheduleNotification: async (payload) => ({ outcome: 'scheduled', notificationId: payload.id }) },
  )

  assert.equal(result.outcome, 'scheduled')
  const stored = getStoredGameReminder(GAME_ID)
  assert.ok(stored)
  assert.equal(typeof stored.notificationId, 'number')
  assert.ok(new Date(stored.remindAt).getTime() > 0)
})

// --- denied / unsupported / failed all pass through without storing ---

for (const outcome of ['denied', 'unsupported', 'failed']) {
  test(`does not persist a reminder record when the adapter returns ${outcome}`, async () => {
    const result = await scheduleGameReminder(
      { game: makeGame(), fieldName: 'Central Court', t },
      { scheduleNotification: async () => ({ outcome }) },
    )

    assert.equal(result.outcome, outcome)
    assert.equal(getStoredGameReminder(GAME_ID), null)
  })
}

// --- cancellation ---

test('cancelling clears the stored record and invokes the adapter with the stored id', async () => {
  await scheduleGameReminder(
    { game: makeGame(), fieldName: 'Central Court', t },
    { scheduleNotification: async (payload) => ({ outcome: 'scheduled', notificationId: payload.id }) },
  )
  const storedBefore = getStoredGameReminder(GAME_ID)
  assert.ok(storedBefore)

  const cancelledIds = []
  const result = await cancelGameReminder(GAME_ID, {
    cancelNotification: async (id) => { cancelledIds.push(id); return true },
  })

  assert.equal(result, true)
  assert.deepEqual(cancelledIds, [storedBefore.notificationId])
  assert.equal(getStoredGameReminder(GAME_ID), null)
})

test('cancelling a game with no stored reminder is a safe no-op', async () => {
  let cancelCalled = false
  const result = await cancelGameReminder(GAME_ID, {
    cancelNotification: async () => { cancelCalled = true; return true },
  })

  assert.equal(result, true)
  assert.equal(cancelCalled, false)
})

test('cancelling still clears the local record even when the native cancel call fails', async () => {
  await scheduleGameReminder(
    { game: makeGame(), fieldName: 'Central Court', t },
    { scheduleNotification: async (payload) => ({ outcome: 'scheduled', notificationId: payload.id }) },
  )

  const result = await cancelGameReminder(GAME_ID, {
    cancelNotification: async () => false,
  })

  assert.equal(result, true)
  assert.equal(getStoredGameReminder(GAME_ID), null)
})

// --- regression: reminders for different games do not clobber each other ---

test('reminders for different games are stored independently', async () => {
  const otherGameId = '11111111-1111-4111-8111-111111111111'

  await scheduleGameReminder(
    { game: makeGame(), fieldName: 'Central Court', t },
    { scheduleNotification: async (payload) => ({ outcome: 'scheduled', notificationId: payload.id }) },
  )
  await scheduleGameReminder(
    { game: makeGame({ id: otherGameId }), fieldName: 'North Court', t },
    { scheduleNotification: async (payload) => ({ outcome: 'scheduled', notificationId: payload.id }) },
  )

  assert.ok(getStoredGameReminder(GAME_ID))
  assert.ok(getStoredGameReminder(otherGameId))

  await cancelGameReminder(GAME_ID, { cancelNotification: async () => true })

  assert.equal(getStoredGameReminder(GAME_ID), null)
  assert.ok(getStoredGameReminder(otherGameId), 'cancelling one game must not affect another')
})

// --- never throws when localStorage is unavailable (defensive guard) ---

test('never throws when localStorage is unavailable', async () => {
  delete globalThis.localStorage

  const result = await scheduleGameReminder(
    { game: makeGame(), fieldName: 'Central Court', t },
    { scheduleNotification: async (payload) => ({ outcome: 'scheduled', notificationId: payload.id }) },
  )

  assert.equal(result.outcome, 'scheduled')
  assert.equal(getStoredGameReminder(GAME_ID), null)
})
