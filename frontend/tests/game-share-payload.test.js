import assert from 'node:assert/strict'
import test from 'node:test'

import { buildGameSharePayload, formatScheduledDate } from '../src/utils/gameSharePayload.js'
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
const LOCALE = 'en-US'

function makeGame(overrides = {}) {
  return {
    id: GAME_ID,
    sport_type: 'football',
    status: 'open',
    players_present: 4,
    max_players: 10,
    scheduled_at: null,
    ...overrides,
  }
}

// --- null/invalid inputs ---

test('returns null for a game with no id (unshareable)', () => {
  assert.equal(
    buildGameSharePayload({ game: { ...makeGame(), id: undefined }, fieldName: 'Central Court', locale: LOCALE, t }),
    null,
  )
})

test('returns null for a malformed game id', () => {
  assert.equal(
    buildGameSharePayload({ game: { ...makeGame(), id: 'not-a-uuid' }, fieldName: 'Central Court', locale: LOCALE, t }),
    null,
  )
})

// --- open game ---

test('builds a payload for an open, unscheduled game with emoji', () => {
  const payload = buildGameSharePayload({ game: makeGame(), fieldName: 'Central Court', locale: LOCALE, t })

  assert.ok(payload.text.startsWith('⚽'))
  assert.ok(payload.text.includes('Central Court'))
  assert.ok(payload.text.includes('4 / 10'))
  assert.equal(payload.url, `https://yesh-mishak.com/game/${GAME_ID}`)
})

test('uses basketball emoji for basketball games', () => {
  const payload = buildGameSharePayload({
    game: makeGame({ sport_type: 'basketball' }),
    fieldName: 'Central Court',
    locale: LOCALE,
    t,
  })

  assert.ok(payload.text.startsWith('🏀'))
})

test('uses generic emoji for unknown sport type', () => {
  const payload = buildGameSharePayload({
    game: makeGame({ sport_type: 'tennis' }),
    fieldName: 'Central Court',
    locale: LOCALE,
    t,
  })

  assert.ok(payload.text.startsWith('🎽'))
})

// --- full game ---

test('builds a payload for a full game', () => {
  const payload = buildGameSharePayload({
    game: makeGame({ status: 'full', players_present: 10 }),
    fieldName: 'Central Court',
    locale: LOCALE,
    t,
  })

  assert.ok(payload.text.includes('full'))
  assert.ok(payload.text.includes('10 / 10'))
})

// --- finished game ---

test('builds a payload for a finished game', () => {
  const past = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString()
  const payload = buildGameSharePayload({
    game: makeGame({ status: 'finished', scheduled_at: past }),
    fieldName: 'Central Court',
    locale: LOCALE,
    t,
  })

  assert.ok(payload.text.includes('ended'))
  assert.ok(payload.text.includes('Central Court'))
})

// --- cancelled game ---

test('builds a payload for a cancelled game', () => {
  const payload = buildGameSharePayload({
    game: makeGame({ status: 'cancelled' }),
    fieldName: 'Central Court',
    locale: LOCALE,
    t,
  })

  assert.ok(payload.text.includes('cancelled'))
})

// --- scheduled games ---

test('builds a payload for a scheduled open game with a formatted date', () => {
  const future = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString()
  const payload = buildGameSharePayload({
    game: makeGame({ scheduled_at: future }),
    fieldName: 'Central Court',
    locale: LOCALE,
    t,
  })

  assert.ok(payload.text.includes('🗓️'))
  assert.ok(payload.text.includes('Central Court'))
})

test('builds a payload for a scheduled full game', () => {
  const future = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString()
  const payload = buildGameSharePayload({
    game: makeGame({ scheduled_at: future, status: 'full', players_present: 10 }),
    fieldName: 'Central Court',
    locale: LOCALE,
    t,
  })

  assert.ok(payload.text.includes('full'))
  assert.ok(payload.text.includes('🗓️'))
})

// --- date formatting ---

test('formatScheduledDate returns today label for today', () => {
  const now = new Date()
  now.setHours(20, 0, 0, 0)
  const result = formatScheduledDate(now.toISOString(), LOCALE, t)

  assert.ok(result.startsWith('Today'))
})

test('formatScheduledDate returns tomorrow label for tomorrow', () => {
  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  tomorrow.setHours(18, 30, 0, 0)
  const result = formatScheduledDate(tomorrow.toISOString(), LOCALE, t)

  assert.ok(result.startsWith('Tomorrow'))
})

test('formatScheduledDate returns date+time for other dates', () => {
  const farFuture = new Date()
  farFuture.setDate(farFuture.getDate() + 7)
  farFuture.setHours(19, 0, 0, 0)
  const result = formatScheduledDate(farFuture.toISOString(), LOCALE, t)

  // Should not say Today or Tomorrow
  assert.ok(!result.startsWith('Today'))
  assert.ok(!result.startsWith('Tomorrow'))
  // Should contain a comma separating date and time
  assert.ok(result.includes(','))
})

test('formatScheduledDate returns null for invalid date', () => {
  assert.equal(formatScheduledDate('not-a-date', LOCALE, t), null)
})

// --- missing values ---

test('falls back to a generic field label when fieldName is missing', () => {
  const payload = buildGameSharePayload({ game: makeGame(), fieldName: '', locale: LOCALE, t })

  assert.ok(payload.text.includes('Unnamed field'))
})

test('handles missing sport_type gracefully', () => {
  const payload = buildGameSharePayload({
    game: makeGame({ sport_type: '' }),
    fieldName: 'Central Court',
    locale: LOCALE,
    t,
  })

  assert.ok(payload)
  assert.ok(!payload.text.includes('undefined'))
  assert.ok(!payload.text.includes('null'))
})

test('handles missing capacity values gracefully', () => {
  const payload = buildGameSharePayload({
    game: makeGame({ players_present: undefined, max_players: undefined }),
    fieldName: 'Central Court',
    locale: LOCALE,
    t,
  })

  assert.ok(payload)
  assert.ok(!payload.text.includes('undefined'))
  assert.ok(!payload.text.includes('null'))
})

// --- privacy ---

test('never includes participant, creator, or user identity fields', () => {
  const payload = buildGameSharePayload({
    game: makeGame({ created_by: 'user-secret-id', participants: [{ user_id: 'p1', name: 'Alice' }] }),
    fieldName: 'Central Court',
    locale: LOCALE,
    t,
  })

  const serialized = JSON.stringify(payload)
  assert.doesNotMatch(serialized, /user-secret-id/)
  assert.doesNotMatch(serialized, /Alice/)
})

// --- canonical URL ---

test('the url matches the canonical link builder exactly', () => {
  const payload = buildGameSharePayload({ game: makeGame(), fieldName: 'Central Court', locale: LOCALE, t })

  assert.equal(payload.url, `https://yesh-mishak.com/game/${GAME_ID}`)
})

// --- no undefined/null in output ---

test('no undefined or null strings appear in the serialized payload', () => {
  const payload = buildGameSharePayload({ game: makeGame(), fieldName: 'Central Court', locale: LOCALE, t })
  const serialized = JSON.stringify(payload)

  assert.doesNotMatch(serialized, /\bundefined\b/)
  assert.doesNotMatch(serialized, /\bnull\b/)
})
