import assert from 'node:assert/strict'
import test from 'node:test'

import { shareField } from '../src/api/fieldSharing.js'
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

const FIELD_ID = '11111111-1111-4111-8111-111111111111'
const EXPECTED_URL = `https://yesh-mishak.com/fields/${FIELD_ID}`

function makeField(overrides = {}) {
  return {
    id: FIELD_ID,
    name: 'Central Court',
    city: '',
    status: 'approved',
    ...overrides,
  }
}

// --- native share success ---

test('native share success passes through the shared outcome', async () => {
  const result = await shareField(
    { field: makeField(), t },
    {
      invokeShare: async () => ({ outcome: 'shared', mechanism: 'native-share' }),
      copyText: async () => { throw new Error('should not be called') },
    },
  )

  assert.deepEqual(result, { outcome: 'shared', mechanism: 'native-share' })
})

// --- user cancellation ---

test('user cancellation passes through the cancelled outcome without clipboard fallback', async () => {
  let clipboardCalled = false
  const result = await shareField(
    { field: makeField(), t },
    {
      invokeShare: async () => ({ outcome: 'cancelled', mechanism: 'native-share' }),
      copyText: async () => { clipboardCalled = true },
    },
  )

  assert.deepEqual(result, { outcome: 'cancelled', mechanism: 'native-share' })
  assert.equal(clipboardCalled, false)
})

// --- native share failure (not unavailable — a runtime error) ---

test('native share failure passes through without clipboard fallback', async () => {
  let clipboardCalled = false
  const result = await shareField(
    { field: makeField(), t },
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
  const result = await shareField(
    { field: makeField(), t },
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
  await shareField(
    { field: makeField(), t },
    {
      invokeShare: async () => ({ outcome: 'unavailable', mechanism: 'native-share', reason: 'share-api-unavailable' }),
      copyText: async (text) => { copiedText = text },
    },
  )

  assert.ok(copiedText.includes('Central Court'), 'clipboard text includes field name')
  assert.ok(copiedText.includes(EXPECTED_URL), 'clipboard text includes canonical URL')
})

// --- clipboard fallback does not duplicate URL ---

test('clipboard fallback does not duplicate URL', async () => {
  let copiedText = null
  await shareField(
    { field: makeField(), t },
    {
      invokeShare: async () => ({ outcome: 'unavailable', mechanism: 'native-share', reason: 'share-api-unavailable' }),
      copyText: async (text) => { copiedText = text },
    },
  )

  const urlOccurrences = copiedText.split(EXPECTED_URL).length - 1
  assert.equal(urlOccurrences, 1, 'URL should appear exactly once')
})

// --- native share unavailable → clipboard failure ---

test('returns clipboard failure when both native share and clipboard fail', async () => {
  const result = await shareField(
    { field: makeField(), t },
    {
      invokeShare: async () => ({ outcome: 'unavailable', mechanism: 'native-share', reason: 'unsupported-platform' }),
      copyText: async () => { throw new Error('Clipboard API unavailable') },
    },
  )

  assert.deepEqual(result, { outcome: 'failed', mechanism: 'clipboard', reason: 'clipboard-write-failed' })
})

// --- malformed field prevents both native share and clipboard ---

test('malformed field prevents both native share and clipboard invocation', async () => {
  let invokeShareCalled = false
  let clipboardCalled = false
  const result = await shareField(
    { field: makeField({ id: undefined }), t },
    {
      invokeShare: async () => { invokeShareCalled = true },
      copyText: async () => { clipboardCalled = true },
    },
  )

  assert.deepEqual(result, { outcome: 'unavailable', mechanism: 'none', reason: 'invalid-resource' })
  assert.equal(invokeShareCalled, false)
  assert.equal(clipboardCalled, false)
})

test('null field prevents both native share and clipboard invocation', async () => {
  let invokeShareCalled = false
  let clipboardCalled = false
  const result = await shareField(
    { field: null, t },
    {
      invokeShare: async () => { invokeShareCalled = true },
      copyText: async () => { clipboardCalled = true },
    },
  )

  assert.deepEqual(result, { outcome: 'unavailable', mechanism: 'none', reason: 'invalid-resource' })
  assert.equal(invokeShareCalled, false)
  assert.equal(clipboardCalled, false)
})
