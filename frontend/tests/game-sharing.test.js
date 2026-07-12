import assert from 'node:assert/strict'
import test from 'node:test'

import { shareGame } from '../src/api/gameSharing.js'
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
const EXPECTED_URL = `https://yesh-mishak.com/game/${GAME_ID}`

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

// --- native share success ---

test('native share success passes through the shared outcome', async () => {
  const result = await shareGame(
    { game: makeGame(), fieldName: 'Central Court', locale: LOCALE, t },
    {
      invokeShare: async () => ({ outcome: 'shared', mechanism: 'native-share' }),
      copyText: async () => { throw new Error('should not be called') },
    },
  )

  assert.deepEqual(result, { outcome: 'shared', mechanism: 'native-share' })
})

// --- user cancellation ---

test('user cancellation passes through without clipboard fallback', async () => {
  let clipboardCalled = false
  const result = await shareGame(
    { game: makeGame(), fieldName: 'Central Court', locale: LOCALE, t },
    {
      invokeShare: async () => ({ outcome: 'cancelled', mechanism: 'native-share' }),
      copyText: async () => { clipboardCalled = true },
    },
  )

  assert.deepEqual(result, { outcome: 'cancelled', mechanism: 'native-share' })
  assert.equal(clipboardCalled, false)
})

// --- native share failure ---

test('native share failure passes through without clipboard fallback', async () => {
  let clipboardCalled = false
  const result = await shareGame(
    { game: makeGame(), fieldName: 'Central Court', locale: LOCALE, t },
    {
      invokeShare: async () => ({ outcome: 'failed', mechanism: 'native-share', reason: 'share-invocation-failed' }),
      copyText: async () => { clipboardCalled = true },
    },
  )

  assert.deepEqual(result, { outcome: 'failed', mechanism: 'native-share', reason: 'share-invocation-failed' })
  assert.equal(clipboardCalled, false)
})

// --- native share unavailable → clipboard success ---

test('falls back to clipboard when native share is unavailable', async () => {
  let copiedText = null
  const result = await shareGame(
    { game: makeGame(), fieldName: 'Central Court', locale: LOCALE, t },
    {
      invokeShare: async () => ({ outcome: 'unavailable', mechanism: 'native-share', reason: 'unsupported-platform' }),
      copyText: async (text) => { copiedText = text },
    },
  )

  assert.deepEqual(result, { outcome: 'copied', mechanism: 'clipboard' })
  assert.ok(copiedText.includes(EXPECTED_URL), 'clipboard text includes canonical URL')
})

// --- clipboard fallback contains readable message and URL ---

test('clipboard fallback contains readable message and URL', async () => {
  let copiedText = null
  await shareGame(
    { game: makeGame(), fieldName: 'Central Court', locale: LOCALE, t },
    {
      invokeShare: async () => ({ outcome: 'unavailable', mechanism: 'native-share', reason: 'unsupported-platform' }),
      copyText: async (text) => { copiedText = text },
    },
  )

  assert.ok(copiedText.includes('Central Court'), 'clipboard text includes field name')
  assert.ok(copiedText.includes(EXPECTED_URL), 'clipboard text includes canonical URL')
})

// --- clipboard fallback does not duplicate URL ---

test('clipboard fallback does not duplicate URL', async () => {
  let copiedText = null
  await shareGame(
    { game: makeGame(), fieldName: 'Central Court', locale: LOCALE, t },
    {
      invokeShare: async () => ({ outcome: 'unavailable', mechanism: 'native-share', reason: 'unsupported-platform' }),
      copyText: async (text) => { copiedText = text },
    },
  )

  const urlOccurrences = copiedText.split(EXPECTED_URL).length - 1
  assert.equal(urlOccurrences, 1, 'URL should appear exactly once')
})

// --- clipboard failure ---

test('returns clipboard failure when both native share and clipboard fail', async () => {
  const result = await shareGame(
    { game: makeGame(), fieldName: 'Central Court', locale: LOCALE, t },
    {
      invokeShare: async () => ({ outcome: 'unavailable', mechanism: 'native-share', reason: 'unsupported-platform' }),
      copyText: async () => { throw new Error('Clipboard API unavailable') },
    },
  )

  assert.deepEqual(result, { outcome: 'failed', mechanism: 'clipboard', reason: 'clipboard-write-failed' })
})

// --- invalid resource ---

test('short-circuits to unavailable when the game is unshareable', async () => {
  let invokeShareCalled = false
  let clipboardCalled = false
  const result = await shareGame(
    { game: { ...makeGame(), id: undefined }, fieldName: 'Central Court', locale: LOCALE, t },
    {
      invokeShare: async () => { invokeShareCalled = true },
      copyText: async () => { clipboardCalled = true },
    },
  )

  assert.deepEqual(result, { outcome: 'unavailable', mechanism: 'none', reason: 'invalid-resource' })
  assert.equal(invokeShareCalled, false)
  assert.equal(clipboardCalled, false)
})

// --- consistent outcome shapes ---

test('game and field sharing return consistent outcome shapes', async () => {
  const { shareField } = await import('../src/api/fieldSharing.js')

  const fieldT = (key, options = {}) => {
    const template = resolveKey(key)
    if (typeof template !== 'string') return typeof options === 'string' ? options : key
    return template.replace(/\{\{(\w+)\}\}/g, (_, name) => String(options[name] ?? ''))
  }

  const unavailableStub = async () => ({ outcome: 'unavailable', mechanism: 'native-share', reason: 'unsupported-platform' })
  const clipboardStub = async () => {}

  const gameResult = await shareGame(
    { game: makeGame(), fieldName: 'Central Court', locale: LOCALE, t },
    { invokeShare: unavailableStub, copyText: clipboardStub },
  )

  const fieldResult = await shareField(
    { field: { id: '11111111-1111-4111-8111-111111111111', name: 'Test', status: 'approved' }, t: fieldT },
    { invokeShare: unavailableStub, copyText: clipboardStub },
  )

  // Both should produce { outcome: 'copied', mechanism: 'clipboard' }
  assert.equal(gameResult.outcome, fieldResult.outcome)
  assert.equal(gameResult.mechanism, fieldResult.mechanism)
})
