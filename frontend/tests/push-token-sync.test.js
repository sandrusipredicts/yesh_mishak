import assert from 'node:assert/strict'
import { describe, test } from 'node:test'

import { createPushTokenSync } from '../src/utils/pushTokenSync.js'

function createFakeTimers() {
  let now = 0
  const scheduled = []

  return {
    setTimeoutFn(callback, delay) {
      const id = scheduled.length
      scheduled.push({ id, callback, fireAt: now + delay, cancelled: false })
      return id
    },
    clearTimeoutFn(id) {
      const entry = scheduled.find((item) => item.id === id)
      if (entry) {
        entry.cancelled = true
      }
    },
    async advance(ms) {
      now += ms
      const due = scheduled.filter((item) => !item.cancelled && item.fireAt <= now)
      for (const entry of due) {
        entry.cancelled = true
        await entry.callback()
      }
    },
  }
}

describe('createPushTokenSync', () => {
  test('sync resolves immediately when save succeeds', async () => {
    const calls = []
    const sync = createPushTokenSync({
      save: async (token) => { calls.push(token) },
    })

    sync.sync('token-1', { platform: 'android' })
    await Promise.resolve()

    assert.deepStrictEqual(calls, ['token-1'])
  })

  test('retries a transient failure with bounded backoff then succeeds', async () => {
    const timers = createFakeTimers()
    let attempts = 0
    const sync = createPushTokenSync({
      save: async () => {
        attempts += 1
        if (attempts < 2) {
          const error = new Error('network error')
          throw error
        }
      },
      setTimeoutFn: timers.setTimeoutFn,
      clearTimeoutFn: timers.clearTimeoutFn,
    })

    sync.sync('token-1', {})
    await Promise.resolve()
    assert.strictEqual(attempts, 1)

    await timers.advance(2000)
    assert.strictEqual(attempts, 2)
  })

  test('does not retry a permanent 422 validation error', async () => {
    const timers = createFakeTimers()
    let attempts = 0
    const failures = []
    const sync = createPushTokenSync({
      save: async () => {
        attempts += 1
        const error = new Error('invalid')
        error.response = { status: 422 }
        throw error
      },
      onSyncFailed: (error) => failures.push(error),
      setTimeoutFn: timers.setTimeoutFn,
      clearTimeoutFn: timers.clearTimeoutFn,
    })

    sync.sync('token-1', {})
    await Promise.resolve()

    assert.strictEqual(attempts, 1)
    assert.strictEqual(failures.length, 1)

    await timers.advance(60000)
    assert.strictEqual(attempts, 1, 'permanent errors must not be retried on a timer')
  })

  test('gives up after max retries and reports via onSyncFailed', async () => {
    const timers = createFakeTimers()
    let attempts = 0
    let failedCount = 0
    const sync = createPushTokenSync({
      save: async () => {
        attempts += 1
        throw new Error('still down')
      },
      onSyncFailed: () => { failedCount += 1 },
      maxRetries: 2,
      baseDelayMs: 100,
      setTimeoutFn: timers.setTimeoutFn,
      clearTimeoutFn: timers.clearTimeoutFn,
    })

    sync.sync('token-1', {})
    await Promise.resolve()
    await timers.advance(100)
    await timers.advance(200)

    assert.strictEqual(attempts, 3)
    assert.strictEqual(failedCount, 1)
  })

  test('retryPending re-attempts a previously failed sync on demand', async () => {
    const timers = createFakeTimers()
    let attempts = 0
    let shouldFail = true
    const sync = createPushTokenSync({
      save: async () => {
        attempts += 1
        if (shouldFail) {
          const error = new Error('offline')
          throw error
        }
      },
      maxRetries: 0,
      setTimeoutFn: timers.setTimeoutFn,
      clearTimeoutFn: timers.clearTimeoutFn,
    })

    sync.sync('token-1', {})
    await Promise.resolve()
    assert.strictEqual(attempts, 1)

    shouldFail = false
    sync.retryPending()
    await Promise.resolve()

    assert.strictEqual(attempts, 2)
  })

  test('a fresh sync call cancels a pending scheduled retry', async () => {
    const timers = createFakeTimers()
    const calls = []
    const sync = createPushTokenSync({
      save: async (token) => {
        calls.push(token)
        if (token === 'token-old') {
          throw new Error('transient')
        }
      },
      setTimeoutFn: timers.setTimeoutFn,
      clearTimeoutFn: timers.clearTimeoutFn,
    })

    sync.sync('token-old', {})
    await Promise.resolve()
    sync.sync('token-new', {})
    await Promise.resolve()

    await timers.advance(60000)

    assert.deepStrictEqual(calls, ['token-old', 'token-new'])
  })

  test('dispose stops further retries', async () => {
    const timers = createFakeTimers()
    let attempts = 0
    const sync = createPushTokenSync({
      save: async () => {
        attempts += 1
        throw new Error('down')
      },
      setTimeoutFn: timers.setTimeoutFn,
      clearTimeoutFn: timers.clearTimeoutFn,
    })

    sync.sync('token-1', {})
    await Promise.resolve()
    assert.strictEqual(attempts, 1)

    sync.dispose()
    await timers.advance(60000)

    assert.strictEqual(attempts, 1)
  })
})
