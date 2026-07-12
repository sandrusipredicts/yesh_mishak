import assert from 'node:assert/strict'
import test from 'node:test'

import { buildFieldSharePayload } from '../src/utils/fieldSharePayload.js'
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

function makeField(overrides = {}) {
  return {
    id: FIELD_ID,
    name: 'Central Court',
    city: '',
    status: 'approved',
    ...overrides,
  }
}

test('builds payload with field name and canonical URL', () => {
  const payload = buildFieldSharePayload({ field: makeField(), t })

  assert.equal(payload.title, 'Central Court - Yesh Mishak')
  assert.equal(payload.text, 'Come play at Central Court!')
  assert.equal(payload.url, `https://yesh-mishak.com/fields/${FIELD_ID}`)
})

test('includes city in text when available', () => {
  const payload = buildFieldSharePayload({ field: makeField({ city: 'Tel Aviv' }), t })

  assert.equal(payload.text, 'Come play at Central Court in Tel Aviv!')
})

test('uses location fallback when city is absent', () => {
  const payload = buildFieldSharePayload({
    field: makeField({ city: '', location: 'Near the park' }),
    t,
  })

  assert.equal(payload.text, 'Come play at Central Court in Near the park!')
})

test('omits city clause when neither city nor location is set', () => {
  const payload = buildFieldSharePayload({ field: makeField({ city: '', location: '' }), t })

  assert.equal(payload.text, 'Come play at Central Court!')
})

test('returns null for a field with no id', () => {
  assert.equal(buildFieldSharePayload({ field: makeField({ id: undefined }), t }), null)
})

test('returns null for a field with a malformed id', () => {
  assert.equal(buildFieldSharePayload({ field: makeField({ id: 'bad-id' }), t }), null)
})

test('returns null for a null field', () => {
  assert.equal(buildFieldSharePayload({ field: null, t }), null)
})

test('URL uses the /fields/ path segment matching the route parser', () => {
  const payload = buildFieldSharePayload({ field: makeField(), t })
  const url = new URL(payload.url)

  assert.equal(url.protocol, 'https:')
  assert.equal(url.hostname, 'yesh-mishak.com')
  assert.match(url.pathname, /^\/fields\//)
})

test('field ID is lowercased in the URL', () => {
  const payload = buildFieldSharePayload({
    field: makeField({ id: FIELD_ID.toUpperCase() }),
    t,
  })

  assert.equal(payload.url, `https://yesh-mishak.com/fields/${FIELD_ID}`)
})
