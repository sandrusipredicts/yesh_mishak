import assert from 'node:assert/strict'
import test from 'node:test'

import { isGameShareable } from '../src/utils/gameShareability.js'

test('is shareable when open', () => {
  assert.equal(isGameShareable({ status: 'open' }), true)
})

test('is shareable when full', () => {
  assert.equal(isGameShareable({ status: 'full' }), true)
})

test('is not shareable when finished', () => {
  assert.equal(isGameShareable({ status: 'finished' }), false)
})

test('is not shareable when cancelled', () => {
  assert.equal(isGameShareable({ status: 'cancelled' }), false)
})

test('is not shareable for an unrecognized/future status by default (allowlist, not denylist)', () => {
  assert.equal(isGameShareable({ status: 'archived' }), false)
})

test('is not shareable when status is missing', () => {
  assert.equal(isGameShareable({}), false)
  assert.equal(isGameShareable(null), false)
  assert.equal(isGameShareable(undefined), false)
})

test('status comparison is case-insensitive', () => {
  assert.equal(isGameShareable({ status: 'OPEN' }), true)
  assert.equal(isGameShareable({ status: 'Full' }), true)
})
