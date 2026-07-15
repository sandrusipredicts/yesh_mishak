import assert from 'node:assert/strict'
import test from 'node:test'

import {
  isGoogleConfigurationError,
  isUserCancellation,
} from '../src/api/nativeGoogleAuth.js'

test('recognizes only the plugin cancellation code as user cancellation', () => {
  assert.equal(isUserCancellation({ code: 'USER_CANCELLED' }), true)
  assert.equal(isUserCancellation({ code: 'DEVELOPER_ERROR' }), false)
  assert.equal(isUserCancellation({ statusCode: 10 }), false)
})

test('recognizes native Google developer configuration codes', () => {
  assert.equal(isGoogleConfigurationError({ code: 'DEVELOPER_ERROR' }), true)
  assert.equal(isGoogleConfigurationError({ statusCode: 10 }), true)
  assert.equal(isGoogleConfigurationError({ code: 'NETWORK_ERROR' }), false)
})

test('recognizes configuration messages without exposing them to the UI', () => {
  assert.equal(
    isGoogleConfigurationError({ message: 'Google Sign-In failed: Client ID is not set' }),
    true,
  )
  assert.equal(
    isGoogleConfigurationError({ message: 'Google provider temporarily unavailable' }),
    false,
  )
})
