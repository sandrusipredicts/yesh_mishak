import assert from 'node:assert/strict'
import test from 'node:test'

import { isGameCalendarEligible } from '../src/utils/gameCalendarEligibility.js'

const NOW = Date.parse('2026-07-16T12:00:00Z')
const ONE_HOUR_MS = 60 * 60 * 1000
const FUTURE = new Date(NOW + ONE_HOUR_MS).toISOString()
const PAST = new Date(NOW - ONE_HOUR_MS).toISOString()

function withNow(game) {
  return isGameCalendarEligible(game, { now: NOW })
}

// --- eligible: genuinely upcoming/scheduled ---

test('eligible for an open game with a valid future scheduled_at', () => {
  assert.equal(withNow({ status: 'open', scheduled_at: FUTURE, started_at: FUTURE }), true)
})

test('eligible for a full game with a valid future scheduled_at', () => {
  assert.equal(withNow({ status: 'full', scheduled_at: FUTURE, started_at: FUTURE }), true)
})

// --- ineligible: active game, regardless of open/full status ---

test('not eligible for an active open game (scheduled_at already in the past / immediate game)', () => {
  assert.equal(withNow({ status: 'open', scheduled_at: null, started_at: PAST }), false)
})

test('not eligible for an active full game', () => {
  assert.equal(withNow({ status: 'full', scheduled_at: null, started_at: PAST }), false)
})

test('not eligible when scheduled_at is in the past even if status is still open', () => {
  assert.equal(withNow({ status: 'open', scheduled_at: PAST, started_at: PAST }), false)
})

test('not eligible when started_at indicates the game has begun, even if scheduled_at looks future (defensive/inconsistent data)', () => {
  assert.equal(withNow({ status: 'open', scheduled_at: FUTURE, started_at: PAST }), false)
})

// --- ineligible: terminal statuses ---

test('not eligible for a finished game', () => {
  assert.equal(withNow({ status: 'finished', scheduled_at: FUTURE, started_at: FUTURE }), false)
})

test('not eligible for a cancelled game', () => {
  assert.equal(withNow({ status: 'cancelled', scheduled_at: FUTURE, started_at: FUTURE }), false)
})

test('not eligible for an unrecognized status (allowlist, not denylist)', () => {
  assert.equal(withNow({ status: 'archived', scheduled_at: FUTURE, started_at: FUTURE }), false)
})

// --- missing / invalid data ---

test('not eligible when scheduled_at is missing', () => {
  assert.equal(withNow({ status: 'open', scheduled_at: null, started_at: null }), false)
  assert.equal(withNow({ status: 'open' }), false)
})

test('not eligible when scheduled_at is malformed', () => {
  assert.equal(withNow({ status: 'open', scheduled_at: 'not-a-date' }), false)
})

test('not eligible when the game itself is missing', () => {
  assert.equal(withNow(null), false)
  assert.equal(withNow(undefined), false)
})

test('status comparison is case-insensitive', () => {
  assert.equal(withNow({ status: 'OPEN', scheduled_at: FUTURE, started_at: FUTURE }), true)
  assert.equal(withNow({ status: 'Full', scheduled_at: FUTURE, started_at: FUTURE }), true)
})

// --- default `now` (no injected value) ---

test('defaults to the real current time when `now` is not injected', () => {
  const realFuture = new Date(Date.now() + ONE_HOUR_MS).toISOString()
  assert.equal(isGameCalendarEligible({ status: 'open', scheduled_at: realFuture, started_at: realFuture }), true)
})
