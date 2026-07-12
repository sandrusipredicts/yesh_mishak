import assert from 'node:assert/strict'
import test from 'node:test'

import { isFieldShareable } from '../src/utils/fieldShareability.js'

test('approved field is shareable', () => {
  assert.equal(isFieldShareable({ status: 'approved' }), true)
})

test('approved via approval_status is shareable', () => {
  assert.equal(isFieldShareable({ approval_status: 'approved', status: 'open' }), true)
})

test('pending field is not shareable', () => {
  assert.equal(isFieldShareable({ status: 'pending' }), false)
})

test('rejected field is not shareable', () => {
  assert.equal(isFieldShareable({ status: 'rejected' }), false)
})

test('closed field is not shareable', () => {
  assert.equal(isFieldShareable({ status: 'closed' }), false)
})

test('null field is not shareable', () => {
  assert.equal(isFieldShareable(null), false)
})

test('undefined field is not shareable', () => {
  assert.equal(isFieldShareable(undefined), false)
})

test('field with no status is not shareable', () => {
  assert.equal(isFieldShareable({}), false)
})

test('case insensitive: APPROVED is shareable', () => {
  assert.equal(isFieldShareable({ status: 'APPROVED' }), true)
})
