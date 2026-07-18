import assert from 'node:assert/strict'
import test from 'node:test'

import { redactBreadcrumb, redactDeep, redactEvent, toSafeUrlPath } from '../src/monitoring/redaction.js'

test('redactDeep: redacts sensitive top-level keys', () => {
  const input = { password: 'hunter2', username: 'alice' }
  const result = redactDeep(input)
  assert.equal(result.password, '[Redacted]')
  assert.equal(result.username, 'alice')
})

test('redactDeep: redacts sensitive keys nested arbitrarily deep', () => {
  const input = {
    a: { b: { c: { authorization: 'Bearer abc123', safe: 'ok' } } },
  }
  const result = redactDeep(input)
  assert.equal(result.a.b.c.authorization, '[Redacted]')
  assert.equal(result.a.b.c.safe, 'ok')
})

test('redactDeep: redacts sensitive keys inside arrays of objects', () => {
  const input = { items: [{ token: 'abc' }, { name: 'field-1' }] }
  const result = redactDeep(input)
  assert.equal(result.items[0].token, '[Redacted]')
  assert.equal(result.items[1].name, 'field-1')
})

test('redactDeep: does not mutate the original input', () => {
  const input = { password: 'hunter2', nested: { token: 'xyz' } }
  const snapshot = JSON.parse(JSON.stringify(input))
  redactDeep(input)
  assert.deepEqual(input, snapshot)
})

test('redactDeep: handles circular references without throwing or looping forever', () => {
  const input = { name: 'a' }
  input.self = input
  const result = redactDeep(input)
  assert.equal(result.name, 'a')
  assert.equal(result.self, '[Circular]')
})

test('redactDeep: redacts exact coordinate keys regardless of nesting', () => {
  const input = { location: { latitude: 31.5, longitude: 34.7, city: 'x' } }
  const result = redactDeep(input)
  assert.equal(result.location.latitude, '[Redacted]')
  assert.equal(result.location.longitude, '[Redacted]')
  assert.equal(result.location.city, 'x')
})

test('toSafeUrlPath: strips query strings that may carry tokens or verification codes', () => {
  assert.equal(
    toSafeUrlPath('https://api.example.com/auth/verify?token=abc123&email=x@example.com'),
    'https://api.example.com/auth/verify',
  )
})

test('toSafeUrlPath: strips fragments too', () => {
  assert.equal(toSafeUrlPath('https://example.com/page#secret=1'), 'https://example.com/page')
})

test('toSafeUrlPath: handles a bare path (no origin) safely', () => {
  assert.equal(toSafeUrlPath('/games/123?ref=deep-link&campaign=abc'), '/games/123')
})

test('redactEvent: strips Authorization headers from request context', () => {
  const event = {
    request: {
      url: 'https://api.example.com/games?token=abc',
      headers: { Authorization: 'Bearer secret-token', 'Content-Type': 'application/json' },
      cookies: { session: 'abc' },
      data: { password: 'hunter2' },
    },
  }
  const result = redactEvent(event)
  assert.equal(result.request.headers.Authorization, '[Redacted]')
  assert.equal(result.request.headers['Content-Type'], 'application/json')
  assert.equal(result.request.cookies, undefined)
  assert.equal(result.request.data, undefined)
  assert.equal(result.request.url, 'https://api.example.com/games')
})

test('redactEvent: only ever keeps the internal user id, dropping anything else on the user object', () => {
  const event = { user: { id: 'user-1', email: 'a@example.com', username: 'alice' } }
  const result = redactEvent(event)
  assert.deepEqual(result.user, { id: 'user-1' })
})

test('redactEvent: redacts extra and contexts payloads', () => {
  const event = { extra: { refresh_token: 'abc' }, contexts: { app: { push_token: 'xyz' } } }
  const result = redactEvent(event)
  assert.equal(result.extra.refresh_token, '[Redacted]')
  assert.equal(result.contexts.app.push_token, '[Redacted]')
})

test('redactBreadcrumb: redacts sensitive breadcrumb data', () => {
  const breadcrumb = { category: 'api', data: { authorization: 'Bearer x', endpoint: '/games' } }
  const result = redactBreadcrumb(breadcrumb)
  assert.equal(result.data.authorization, '[Redacted]')
  assert.equal(result.data.endpoint, '/games')
})

test('redactBreadcrumb: reduces a url field in breadcrumb data to its safe path', () => {
  const breadcrumb = { data: { url: 'https://api.example.com/auth/reset?token=abc' } }
  const result = redactBreadcrumb(breadcrumb)
  assert.equal(result.data.url, 'https://api.example.com/auth/reset')
})
