import assert from 'node:assert/strict'
import test from 'node:test'
import { getApiErrorMessage } from '../src/api/errors.js'

test('getApiErrorMessage: 409 with message format', () => {
  const error = {
    response: {
      status: 409,
      data: {
        error: true,
        code: 'CONFLICT',
        message: 'Phone number is already registered',
      },
    },
  }
  const fallback = 'Failed to create account!'
  const result = getApiErrorMessage(error, fallback)
  assert.equal(result, 'Phone number is already registered')
})

test('getApiErrorMessage: 409 with detail format (string)', () => {
  const error = {
    response: {
      status: 409,
      data: {
        detail: 'Phone number is already registered',
      },
    },
  }
  const fallback = 'Failed to create account!'
  const result = getApiErrorMessage(error, fallback)
  assert.equal(result, 'Phone number is already registered')
})

test('getApiErrorMessage: 409 with detail format (array)', () => {
  const error = {
    response: {
      status: 409,
      data: {
        detail: [
          { msg: 'Phone number is already registered' }
        ],
      },
    },
  }
  const fallback = 'Failed to create account!'
  const result = getApiErrorMessage(error, fallback)
  assert.equal(result, 'Phone number is already registered')
})

test('getApiErrorMessage: missing message and detail -> generic fallback', () => {
  const error = {
    response: {
      status: 409,
      data: {
        error: true,
        code: 'CONFLICT',
      },
    },
  }
  const fallback = 'Failed to create account!'
  const result = getApiErrorMessage(error, fallback)
  assert.equal(result, fallback)
})
