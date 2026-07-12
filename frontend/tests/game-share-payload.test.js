import assert from 'node:assert/strict'
import test from 'node:test'

import { buildGameSharePayload } from '../src/utils/gameSharePayload.js'
import en from '../src/locales/en/common.js'

// Minimal i18next-compatible `t(key, options)`: resolves a dotted key
// against the real production locale file and interpolates {{var}}
// placeholders, so these tests exercise the actual shipped copy rather
// than a stub template.
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

test('builds a payload for an open, unscheduled game', () => {
  const payload = buildGameSharePayload({ game: makeGame(), fieldName: 'Central Court', locale: LOCALE, t })

  assert.deepEqual(payload, {
    title: 'Football game at Central Court',
    text: 'Join a Football game at Central Court — 4 / 10 players.',
    url: `https://yesh-mishak.com/game/${GAME_ID}`,
  })
})

test('builds a payload for a full game', () => {
  const payload = buildGameSharePayload({
    game: makeGame({ status: 'full', players_present: 10 }),
    fieldName: 'Central Court',
    locale: LOCALE,
    t,
  })

  assert.equal(payload.text, 'Football game at Central Court is full — 10 / 10 players.')
})

test('builds a payload for a scheduled open game with a formatted date', () => {
  const future = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString()
  const payload = buildGameSharePayload({
    game: makeGame({ scheduled_at: future }),
    fieldName: 'Central Court',
    locale: LOCALE,
    t,
  })

  assert.match(payload.text, /^Football game at Central Court on .+ — 4 \/ 10 players\.$/)
})

test('builds a payload for a scheduled full game', () => {
  const future = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString()
  const payload = buildGameSharePayload({
    game: makeGame({ scheduled_at: future, status: 'full', players_present: 10 }),
    fieldName: 'Central Court',
    locale: LOCALE,
    t,
  })

  assert.match(payload.text, /^Football game at Central Court on .+ is full — 10 \/ 10 players\.$/)
})

test('builds a payload for a finished game without exposing a stale schedule', () => {
  const past = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString()
  const payload = buildGameSharePayload({
    game: makeGame({ status: 'finished', scheduled_at: past }),
    fieldName: 'Central Court',
    locale: LOCALE,
    t,
  })

  assert.equal(payload.text, 'This Football game at Central Court has ended.')
})

test('builds a payload for a cancelled game', () => {
  const payload = buildGameSharePayload({
    game: makeGame({ status: 'cancelled' }),
    fieldName: 'Central Court',
    locale: LOCALE,
    t,
  })

  assert.equal(payload.text, 'This Football game at Central Court was cancelled.')
})

test('falls back to a generic field label when fieldName is missing', () => {
  const payload = buildGameSharePayload({ game: makeGame(), fieldName: '', locale: LOCALE, t })

  assert.equal(payload.title, 'Football game at Unnamed field')
})

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

test('the url matches the canonical link builder exactly', () => {
  const payload = buildGameSharePayload({ game: makeGame(), fieldName: 'Central Court', locale: LOCALE, t })

  assert.equal(payload.url, `https://yesh-mishak.com/game/${GAME_ID}`)
})
