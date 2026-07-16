import assert from 'node:assert/strict'
import test from 'node:test'

import { buildIcsEvent, buildIcsFilename } from '../src/utils/icsEvent.js'

const START = new Date('2026-08-15T18:00:00.000Z')
const END = new Date('2026-08-15T20:00:00.000Z')

function makePayload(overrides = {}) {
  return {
    title: 'Football game — Central Court',
    description: 'Football at Central Court — Today, 18:00',
    location: 'Central Court',
    start: START,
    end: END,
    url: 'https://yesh-mishak.com/game/987e6543-e21b-42d3-a456-426614174999',
    ...overrides,
  }
}

function getLine(ics, prefix) {
  return ics.split('\r\n').find((line) => line.startsWith(prefix))
}

// --- structure ---

test('produces a valid VCALENDAR/VEVENT structure with CRLF line endings', () => {
  const ics = buildIcsEvent(makePayload())

  assert.ok(ics.startsWith('BEGIN:VCALENDAR\r\n'))
  assert.ok(ics.includes('BEGIN:VEVENT\r\n'))
  assert.ok(ics.includes('END:VEVENT\r\n'))
  assert.ok(ics.trimEnd().endsWith('END:VCALENDAR'))
  assert.ok(!ics.includes('\n\n'))
})

test('returns null for a payload with no valid start date', () => {
  assert.equal(buildIcsEvent(makePayload({ start: null })), null)
  assert.equal(buildIcsEvent(null), null)
})

// --- timestamps: UTC, DST-safe by construction ---

test('DTSTART and DTEND are UTC-suffixed timestamps matching the payload instants', () => {
  const ics = buildIcsEvent(makePayload())

  assert.equal(getLine(ics, 'DTSTART:'), 'DTSTART:20260815T180000Z')
  assert.equal(getLine(ics, 'DTEND:'), 'DTEND:20260815T200000Z')
})

test('falls back to using start as end when end is missing or invalid', () => {
  const ics = buildIcsEvent(makePayload({ end: null }))

  assert.equal(getLine(ics, 'DTSTART:'), getLine(ics, 'DTEND:').replace('DTEND', 'DTSTART'))
})

// --- content fields ---

test('includes title, location, description, and url', () => {
  const ics = buildIcsEvent(makePayload())

  assert.ok(getLine(ics, 'SUMMARY:').includes('Football game'))
  assert.ok(getLine(ics, 'LOCATION:').includes('Central Court'))
  assert.ok(getLine(ics, 'DESCRIPTION:').includes('Football at Central Court'))
  assert.ok(getLine(ics, 'URL:').includes('yesh-mishak.com'))
})

test('omits LOCATION, DESCRIPTION, and URL lines when not provided', () => {
  const ics = buildIcsEvent(makePayload({ location: '', description: '', url: '' }))

  assert.equal(getLine(ics, 'LOCATION:'), undefined)
  assert.equal(getLine(ics, 'DESCRIPTION:'), undefined)
  assert.equal(getLine(ics, 'URL:'), undefined)
})

// --- escaping (RFC 5545 §3.3.11) ---

test('escapes commas, semicolons, and backslashes in text fields', () => {
  const ics = buildIcsEvent(makePayload({ title: 'Game; round, two \\ finals' }))

  assert.ok(getLine(ics, 'SUMMARY:').includes('Game\\; round\\, two \\\\ finals'))
})

test('escapes embedded newlines as the literal \\n sequence', () => {
  const ics = buildIcsEvent(makePayload({ description: 'Line one\nLine two' }))

  assert.ok(ics.includes('Line one\\nLine two'))
})

// --- unicode / hebrew ---

test('preserves Hebrew text correctly', () => {
  const ics = buildIcsEvent(makePayload({ title: 'משחק כדורגל — מגרש מרכזי' }))

  assert.ok(getLine(ics, 'SUMMARY:').includes('מגרש מרכזי'))
})

// --- bounded length ---

test('bounds an extremely long description instead of producing an unbounded line', () => {
  const longText = 'a'.repeat(5000)
  const ics = buildIcsEvent(makePayload({ description: longText }))
  const descriptionLine = getLine(ics, 'DESCRIPTION:')

  assert.ok(descriptionLine.length < 1100)
})

// --- privacy: never a JWT/secret shape, only what's in the payload ---

test('serializes only the fields present in the payload, nothing extra', () => {
  const ics = buildIcsEvent(makePayload())

  assert.ok(!ics.includes('Bearer '))
  assert.ok(!/eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\./.test(ics))
})

// --- filename ---

test('buildIcsFilename produces a safe, predictable filename', () => {
  assert.equal(
    buildIcsFilename('987e6543-e21b-42d3-a456-426614174999'),
    'game-987e6543-e21b-42d3-a456-426614174999.ics',
  )
})

test('buildIcsFilename strips unsafe characters from a malformed id', () => {
  assert.equal(buildIcsFilename('../../etc/passwd'), 'game-etcpasswd.ics')
})

test('buildIcsFilename falls back to a generic name for a missing id', () => {
  assert.equal(buildIcsFilename(''), 'game-event.ics')
  assert.equal(buildIcsFilename(undefined), 'game-event.ics')
})
