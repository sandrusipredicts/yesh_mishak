import assert from 'node:assert/strict'
import test from 'node:test'

import { isExpectedError } from '../src/monitoring/filters.js'

function withTags(tags) {
  return { tags: Object.entries(tags) }
}

test('filters out Google/native login user cancellation', () => {
  const event = withTags({ auth_error_kind: 'cancelled' })
  assert.equal(isExpectedError(event), true)
})

test('filters out expected permission denial', () => {
  const event = withTags({ permission_result: 'denied' })
  assert.equal(isExpectedError(event), true)
})

test('filters out expected authentication responses (401/403)', () => {
  assert.equal(isExpectedError(withTags({ http_status: 401 })), true)
  assert.equal(isExpectedError(withTags({ http_status: 403 })), true)
})

test('filters out normal validation errors (422)', () => {
  assert.equal(isExpectedError(withTags({ http_status: 422 })), true)
})

test('filters out normal not-found and rate limiting', () => {
  assert.equal(isExpectedError(withTags({ http_status: 404 })), true)
  assert.equal(isExpectedError(withTags({ http_status: 429 })), true)
})

test('filters out offline errors already handled by calling code', () => {
  const event = withTags({ network_offline_handled: 'true' })
  assert.equal(isExpectedError(event), true)
})

test('filters out browser-extension noise by stack frame origin', () => {
  const event = {
    exception: {
      values: [
        {
          stacktrace: {
            frames: [{ filename: 'chrome-extension://abcdefg/content.js' }],
          },
        },
      ],
    },
  }
  assert.equal(isExpectedError(event), true)
})

test('does NOT filter an unexpected internal exception (no expected tag/status set)', () => {
  const event = { tags: [], exception: { values: [{ stacktrace: { frames: [{ filename: 'app.js' }] } }] } }
  assert.equal(isExpectedError(event), false)
})

test('does NOT filter a genuine unhandled 500', () => {
  const event = withTags({ http_status: 500 })
  assert.equal(isExpectedError(event), false)
})

test('does NOT filter broad error classes merely because tags exist for unrelated keys', () => {
  const event = withTags({ some_other_tag: 'value' })
  assert.equal(isExpectedError(event), false)
})

test('monitoring_force_report escape hatch always wins, even over an otherwise-expected signature', () => {
  const event = { tags: [['auth_error_kind', 'cancelled'], ['monitoring_force_report', 'true']] }
  assert.equal(isExpectedError(event), false)
})

test('handles an event with no tags/exception gracefully', () => {
  assert.equal(isExpectedError({}), false)
  assert.equal(isExpectedError(null), false)
})
