import assert from 'node:assert/strict'
import test from 'node:test'

import { buildGameReminderPayload, gameReminderNotificationId } from '../src/utils/gameReminderPayload.js'
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

// --- eligibility ---

test('returns null for a game with no id', () => {
  assert.equal(buildGameReminderPayload({ game: { ...makeGame(), id: undefined }, fieldName: 'Central Court', t }), null)
})

test('returns null for a game with no scheduled_at', () => {
  assert.equal(buildGameReminderPayload({ game: makeGame({ scheduled_at: null }), fieldName: 'Central Court', t }), null)
})

test('returns null for a malformed scheduled_at', () => {
  assert.equal(
    buildGameReminderPayload({ game: makeGame({ scheduled_at: 'not-a-date' }), fieldName: 'Central Court', t }),
    null,
  )
})

test('returns null once the reminder moment (1 hour before start) has already passed', () => {
  // Scheduled 30 minutes from now: reminder moment would be 30 minutes ago.
  const game = makeGame({ scheduled_at: new Date(Date.now() + 30 * 60 * 1000).toISOString() })

  assert.equal(buildGameReminderPayload({ game, fieldName: 'Central Court', t }), null)
})

test('returns null for a game already in the past', () => {
  const game = makeGame({ scheduled_at: new Date(Date.now() - ONE_HOUR_MS).toISOString() })

  assert.equal(buildGameReminderPayload({ game, fieldName: 'Central Court', t }), null)
})

// --- successful payload ---

test('builds a payload scheduled exactly 1 hour before the game start', () => {
  const game = makeGame()
  const payload = buildGameReminderPayload({ game, fieldName: 'Central Court', t })

  assert.ok(payload)
  assert.equal(payload.at.getTime(), new Date(game.scheduled_at).getTime() - ONE_HOUR_MS)
})

test('includes the field name and sport in the notification body', () => {
  const payload = buildGameReminderPayload({ game: makeGame(), fieldName: 'Central Court', t })

  assert.ok(payload.body.includes('Central Court'))
  assert.ok(payload.body.includes('Football'))
})

test('falls back to a generic field label when fieldName is missing', () => {
  const payload = buildGameReminderPayload({ game: makeGame(), fieldName: '', t })

  assert.ok(payload.body.includes('Unnamed field'))
})

test('handles an unknown sport type without crashing or leaking "undefined"', () => {
  const payload = buildGameReminderPayload({ game: makeGame({ sport_type: 'tennis' }), fieldName: 'Central Court', t })

  assert.ok(payload)
  assert.ok(!payload.body.includes('undefined'))
})

// --- privacy: no participant/creator identity ---

test('never includes participant or creator identity in the payload', () => {
  const game = makeGame({ created_by: 'user-secret-id', participants: [{ user_id: 'p1', name: 'Alice' }] })
  const payload = buildGameReminderPayload({ game, fieldName: 'Central Court', t })

  const serialized = JSON.stringify(payload)
  assert.doesNotMatch(serialized, /user-secret-id/)
  assert.doesNotMatch(serialized, /Alice/)
})

// --- notification id derivation ---

test('gameReminderNotificationId is deterministic for the same game id', () => {
  assert.equal(gameReminderNotificationId(GAME_ID), gameReminderNotificationId(GAME_ID))
})

test('gameReminderNotificationId differs for different game ids', () => {
  assert.notEqual(gameReminderNotificationId(GAME_ID), gameReminderNotificationId('a-different-id'))
})

test('gameReminderNotificationId is always a positive integer', () => {
  for (const id of [GAME_ID, 'x', '', 'a-different-id', '00000000-0000-0000-0000-000000000000']) {
    const hashed = gameReminderNotificationId(id)
    assert.ok(Number.isInteger(hashed))
    assert.ok(hashed >= 0)
  }
})

test('the payload id matches gameReminderNotificationId for the same game', () => {
  const payload = buildGameReminderPayload({ game: makeGame(), fieldName: 'Central Court', t })

  assert.equal(payload.id, gameReminderNotificationId(GAME_ID))
})
