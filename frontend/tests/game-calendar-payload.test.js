import assert from 'node:assert/strict'
import test from 'node:test'

import { buildGameCalendarPayload } from '../src/utils/gameCalendarPayload.js'
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
const ONE_HOUR_MS = 60 * 60 * 1000

function makeGame(overrides = {}) {
  return {
    id: GAME_ID,
    sport_type: 'football',
    status: 'open',
    scheduled_at: null,
    started_at: new Date(Date.now() - ONE_HOUR_MS).toISOString(),
    expires_at: new Date(Date.now() + ONE_HOUR_MS).toISOString(),
    ...overrides,
  }
}

function build(overrides = {}, extra = {}) {
  return buildGameCalendarPayload({
    game: makeGame(overrides),
    fieldName: 'Central Court',
    locale: LOCALE,
    t,
    ...extra,
  })
}

// --- invalid / missing resource ---

test('returns null for a game with no id', () => {
  assert.equal(build({ id: undefined }), null)
})

test('returns null for a malformed game id', () => {
  assert.equal(build({ id: 'not-a-uuid' }), null)
})

test('returns null when both scheduled_at and started_at are missing', () => {
  assert.equal(build({ scheduled_at: null, started_at: null }), null)
})

test('returns null when scheduled_at and started_at are both malformed', () => {
  assert.equal(build({ scheduled_at: 'not-a-date', started_at: 'also-not-a-date' }), null)
})

// --- start time resolution ---

test('uses scheduled_at as start for a scheduled game', () => {
  const future = new Date(Date.now() + 24 * ONE_HOUR_MS)
  const payload = build({ scheduled_at: future.toISOString(), started_at: future.toISOString() })

  assert.equal(payload.start.getTime(), future.getTime())
})

test('falls back to started_at as start for an immediate/active game with no scheduled_at', () => {
  const started = new Date(Date.now() - ONE_HOUR_MS)
  const payload = build({ scheduled_at: null, started_at: started.toISOString() })

  assert.equal(payload.start.getTime(), started.getTime())
})

// --- end time resolution ---

test('uses expires_at as end when it is after the start', () => {
  const started = new Date(Date.now() - ONE_HOUR_MS)
  const expires = new Date(Date.now() + ONE_HOUR_MS)
  const payload = build({ started_at: started.toISOString(), expires_at: expires.toISOString() })

  assert.equal(payload.end.getTime(), expires.getTime())
})

test('falls back to a 2-hour default duration when expires_at is missing', () => {
  const started = new Date(Date.now() - ONE_HOUR_MS)
  const payload = build({ started_at: started.toISOString(), expires_at: null })

  assert.equal(payload.end.getTime(), started.getTime() + 2 * ONE_HOUR_MS)
})

test('falls back to a 2-hour default duration when expires_at is not after start (zero/negative duration)', () => {
  const started = new Date(Date.now() - ONE_HOUR_MS)
  const payload = build({ started_at: started.toISOString(), expires_at: started.toISOString() })

  assert.equal(payload.end.getTime(), started.getTime() + 2 * ONE_HOUR_MS)
})

test('falls back to a 2-hour default duration when expires_at is before start', () => {
  const started = new Date(Date.now())
  const before = new Date(started.getTime() - ONE_HOUR_MS)
  const payload = build({ started_at: started.toISOString(), expires_at: before.toISOString() })

  assert.equal(payload.end.getTime(), started.getTime() + 2 * ONE_HOUR_MS)
})

test('falls back to a 2-hour default duration when expires_at is malformed', () => {
  const started = new Date(Date.now())
  const payload = build({ started_at: started.toISOString(), expires_at: 'not-a-date' })

  assert.equal(payload.end.getTime(), started.getTime() + 2 * ONE_HOUR_MS)
})

// --- location ---

test('uses the field name as location when available', () => {
  const payload = build()
  assert.equal(payload.location, 'Central Court')
})

test('falls back to coordinates when no field name is available', () => {
  const payload = build({}, { fieldName: '', fieldLat: 32.0853, fieldLng: 34.7818 })
  assert.equal(payload.location, '32.0853,34.7818')
})

test('location is empty when neither a field name nor valid coordinates are available', () => {
  const payload = build({}, { fieldName: '' })
  assert.equal(payload.location, '')
})

test('does not use invalid coordinates as a location fallback', () => {
  const payload = build({}, { fieldName: '', fieldLat: 999, fieldLng: 999 })
  assert.equal(payload.location, '')
})

// --- deep link / navigation ---

test('includes the canonical game deep link as the url', () => {
  const payload = build()
  assert.equal(payload.url, `https://yesh-mishak.com/game/${GAME_ID}`)
})

test('description includes the deep link', () => {
  const payload = build()
  assert.ok(payload.description.includes(`https://yesh-mishak.com/game/${GAME_ID}`))
})

test('description includes a navigation link when valid coordinates are available', () => {
  const payload = build({}, { fieldLat: 32.0853, fieldLng: 34.7818 })
  assert.ok(payload.description.includes('google.com/maps'))
})

test('description has no navigation link when coordinates are missing', () => {
  const payload = build()
  assert.ok(!payload.description.includes('google.com/maps'))
})

// --- title ---

test('builds a localized title including sport and field name', () => {
  const payload = build()
  assert.ok(payload.title.includes('Football'))
  assert.ok(payload.title.includes('Central Court'))
})

test('falls back to a generic field label when fieldName is missing', () => {
  const payload = build({}, { fieldName: '' })
  assert.ok(payload.title.includes('Unnamed field'))
})

// --- privacy: never includes participant, creator, or user identity ---

test('never includes participant, creator, or user identity fields', () => {
  const payload = build({ created_by: 'user-secret-id', participants: [{ user_id: 'p1', name: 'Alice' }] })
  const serialized = JSON.stringify(payload)

  assert.doesNotMatch(serialized, /user-secret-id/)
  assert.doesNotMatch(serialized, /Alice/)
})

// --- unicode / hebrew ---

test('handles a Hebrew field name correctly', () => {
  const payload = build({}, { fieldName: 'מגרש מרכזי' })
  assert.ok(payload.title.includes('מגרש מרכזי'))
  assert.equal(payload.location, 'מגרש מרכזי')
})

// --- no undefined/null leaking into output ---

test('no undefined or null strings appear in the serialized payload', () => {
  const payload = build()
  const serialized = JSON.stringify(payload)

  assert.doesNotMatch(serialized, /\bundefined\b/)
  assert.doesNotMatch(serialized, /\bnull\b/)
})

test('handles a missing sport_type gracefully', () => {
  const payload = build({ sport_type: '' })
  assert.ok(payload)
  assert.ok(!payload.title.includes('undefined'))
  assert.ok(!payload.description.includes('undefined'))
})
