import assert from 'node:assert/strict'
import test from 'node:test'
import { getSafeErrorMessage } from '../src/api/errors.js'

function mockT(key) { return `[${key}]` }

test('getSafeErrorMessage: known code maps to specific key', () => {
  const error = { response: { status: 409, data: { code: 'CONFLICT' } } }
  assert.equal(getSafeErrorMessage(error, mockT), '[errors.conflict]')
})

test('getSafeErrorMessage: 401 maps to unauthorized', () => {
  const error = { response: { status: 401, data: {} } }
  assert.equal(getSafeErrorMessage(error, mockT), '[errors.unauthorized]')
})

test('getSafeErrorMessage: 500 maps to serverError', () => {
  const error = { response: { status: 500, data: {} } }
  assert.equal(getSafeErrorMessage(error, mockT), '[errors.serverError]')
})

test('getSafeErrorMessage: network error (no response) maps to networkError', () => {
  const error = { message: 'Network Error' }
  assert.equal(getSafeErrorMessage(error, mockT), '[errors.networkError]')
})

test('getSafeErrorMessage: unknown error uses generic fallback', () => {
  const error = { response: { status: 418, data: {} } }
  assert.equal(getSafeErrorMessage(error, mockT), '[errors.generic]')
})

test('getSafeErrorMessage: custom fallback key is used', () => {
  const error = { response: { status: 418, data: {} } }
  assert.equal(getSafeErrorMessage(error, mockT, 'addField.submitFailed'), '[addField.submitFailed]')
})

test('getSafeErrorMessage: does not expose raw backend detail text', () => {
  const error = {
    response: {
      status: 400,
      data: { detail: 'Internal: pg_constraint violated on users.email_unique' }
    }
  }
  const result = getSafeErrorMessage(error, mockT)
  assert.ok(!result.includes('pg_constraint'), 'must not expose database details')
  assert.ok(!result.includes('Internal:'), 'must not expose internal prefix')
})
