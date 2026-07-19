import assert from 'node:assert/strict'
import test from 'node:test'

import { addGameToCalendar } from '../src/api/gameCalendar.js'
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
    status: 'open',
    scheduled_at: new Date(Date.now() + 3 * ONE_HOUR_MS).toISOString(),
    started_at: new Date(Date.now() + 3 * ONE_HOUR_MS).toISOString(),
    expires_at: new Date(Date.now() + 5 * ONE_HOUR_MS).toISOString(),
    ...overrides,
  }
}

function call(overrides = {}) {
  return addGameToCalendar(
    { game: makeGame(), fieldName: 'Central Court', locale: 'en-US', t },
    overrides,
  )
}

// --- invalid resource: neither native nor web is ever touched ---

test('returns unavailable and never calls the native or web path for an invalid game', async () => {
  let promptCalled = false
  let downloadCalled = false

  const result = await addGameToCalendar(
    { game: { ...makeGame(), id: undefined }, fieldName: 'Central Court', locale: 'en-US', t },
    {
      openPrompt: async () => { promptCalled = true; return { outcome: 'opened' } },
      download: () => { downloadCalled = true; return true },
    },
  )

  assert.deepEqual(result, { outcome: 'unavailable', reason: 'invalid-resource' })
  assert.equal(promptCalled, false)
  assert.equal(downloadCalled, false)
})

// --- native prompt path ---

test('returns the native outcome directly when the native prompt is supported', async () => {
  const result = await call({ openPrompt: async () => ({ outcome: 'opened' }) })
  assert.deepEqual(result, { outcome: 'opened' })
})

test('passes cancellation through untouched', async () => {
  const result = await call({ openPrompt: async () => ({ outcome: 'cancelled' }) })
  assert.deepEqual(result, { outcome: 'cancelled' })
})

test('passes permission denial through untouched', async () => {
  const result = await call({ openPrompt: async () => ({ outcome: 'denied' }) })
  assert.deepEqual(result, { outcome: 'denied' })
})

test('passes a native failure through untouched, never falling back silently to web', async () => {
  const result = await call({ openPrompt: async () => ({ outcome: 'failed', reason: 'x' }) })
  assert.deepEqual(result, { outcome: 'failed', reason: 'x' })
})

// --- web fallback path ---

test('falls back to an .ics download when the native prompt reports unsupported', async () => {
  let downloadedContent
  let downloadedFilename

  const result = await call({
    openPrompt: async () => ({ outcome: 'unsupported' }),
    download: (content, filename) => {
      downloadedContent = content
      downloadedFilename = filename
      return true
    },
  })

  assert.deepEqual(result, { outcome: 'downloaded' })
  assert.ok(downloadedContent.includes('BEGIN:VCALENDAR'))
  assert.equal(downloadedFilename, `game-${GAME_ID}.ics`)
})

test('reports failed when the .ics download itself fails', async () => {
  const result = await call({
    openPrompt: async () => ({ outcome: 'unsupported' }),
    download: () => false,
  })

  assert.deepEqual(result, { outcome: 'failed', reason: 'download-failed' })
})

test('never calls download when the native prompt is supported', async () => {
  let downloadCalled = false

  await call({
    openPrompt: async () => ({ outcome: 'opened' }),
    download: () => { downloadCalled = true; return true },
  })

  assert.equal(downloadCalled, false)
})
