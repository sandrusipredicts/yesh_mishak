import assert from 'node:assert/strict'
import test from 'node:test'

import { cancelLocalNotification, scheduleLocalNotification } from '../src/api/localNotifications.js'

const FUTURE = new Date(Date.now() + 60 * 60 * 1000)
const PAST = new Date(Date.now() - 60 * 1000)

function createPlugin({
  checkStatus = { display: 'granted' },
  requestStatus = { display: 'granted' },
  scheduleError,
  cancelError,
} = {}) {
  const calls = { checkPermissions: 0, requestPermissions: 0, schedule: [], cancel: [] }

  return {
    calls,
    plugin: {
      async checkPermissions() {
        calls.checkPermissions += 1
        return checkStatus
      },
      async requestPermissions() {
        calls.requestPermissions += 1
        return requestStatus
      },
      async schedule(options) {
        calls.schedule.push(options)
        if (scheduleError) {
          throw scheduleError
        }
      },
      async cancel(options) {
        calls.cancel.push(options)
        if (cancelError) {
          throw cancelError
        }
      },
    },
  }
}

// --- unsupported platform ---

test('returns unsupported and never touches the plugin when unavailable', async () => {
  const result = await scheduleLocalNotification(
    { id: 1, title: 'Game starting soon', body: 'Football starts in about 1 hour.', at: FUTURE },
    { plugin: null },
  )

  assert.deepEqual(result, { outcome: 'unsupported' })
})

test('cancel is a safe no-op when unsupported', async () => {
  const result = await cancelLocalNotification(1, { plugin: null })

  assert.equal(result, false)
})

// --- successful scheduling (already-granted permission) ---

test('schedules with only the normalized fields when permission is already granted', async () => {
  const { plugin, calls } = createPlugin()

  const result = await scheduleLocalNotification(
    { id: 42, title: 'Game starting soon', body: 'Football starts in about 1 hour.', at: FUTURE },
    { plugin },
  )

  assert.deepEqual(result, { outcome: 'scheduled', notificationId: 42 })
  assert.equal(calls.requestPermissions, 0, 'must not prompt when already granted')
  assert.deepEqual(calls.schedule, [
    {
      notifications: [
        { id: 42, title: 'Game starting soon', body: 'Football starts in about 1 hour.', schedule: { at: FUTURE } },
      ],
    },
  ])
})

// --- permission flow: prompt-then-grant ---

test('requests permission only when the passive check is not granted', async () => {
  const { plugin, calls } = createPlugin({ checkStatus: { display: 'prompt' } })

  const result = await scheduleLocalNotification(
    { id: 1, title: 't', body: 'b', at: FUTURE },
    { plugin },
  )

  assert.equal(result.outcome, 'scheduled')
  assert.equal(calls.checkPermissions, 1)
  assert.equal(calls.requestPermissions, 1)
})

// --- permission denied ---

test('returns denied and never schedules when the user declines the request', async () => {
  const { plugin, calls } = createPlugin({
    checkStatus: { display: 'prompt' },
    requestStatus: { display: 'denied' },
  })

  const result = await scheduleLocalNotification(
    { id: 1, title: 't', body: 'b', at: FUTURE },
    { plugin },
  )

  assert.deepEqual(result, { outcome: 'denied' })
  assert.deepEqual(calls.schedule, [])
})

test('treats a permission-check failure as a prompt, not a crash', async () => {
  const plugin = {
    async checkPermissions() {
      throw new Error('bridge unavailable')
    },
    async requestPermissions() {
      return { display: 'granted' }
    },
    async schedule() {},
  }

  const result = await scheduleLocalNotification({ id: 1, title: 't', body: 'b', at: FUTURE }, { plugin })

  assert.equal(result.outcome, 'scheduled')
})

// --- native API failure ---

test('returns a structured failure when the native schedule call throws', async () => {
  const { plugin } = createPlugin({ scheduleError: new Error('native bridge failed') })

  const result = await scheduleLocalNotification({ id: 1, title: 't', body: 'b', at: FUTURE }, { plugin })

  assert.equal(result.outcome, 'failed')
  assert.equal(result.reason, 'native bridge failed')
})

// --- invalid schedule time (never crashes, never schedules in the past) ---

test('rejects a past schedule time before touching permissions or the plugin', async () => {
  const { plugin, calls } = createPlugin()

  const result = await scheduleLocalNotification({ id: 1, title: 't', body: 'b', at: PAST }, { plugin })

  assert.deepEqual(result, { outcome: 'failed', reason: 'invalid-schedule-time' })
  assert.equal(calls.checkPermissions, 0)
  assert.deepEqual(calls.schedule, [])
})

test('never throws for a non-Date schedule value', async () => {
  const { plugin } = createPlugin()

  const result = await scheduleLocalNotification(
    { id: 1, title: 't', body: 'b', at: 'tomorrow' },
    { plugin },
  )

  assert.equal(result.outcome, 'failed')
})

// --- cancellation ---

test('cancels a scheduled notification by id', async () => {
  const { plugin, calls } = createPlugin()

  const result = await cancelLocalNotification(42, { plugin })

  assert.equal(result, true)
  assert.deepEqual(calls.cancel, [{ notifications: [{ id: 42 }] }])
})

test('cancellation is best-effort: a native failure resolves to false, never throws', async () => {
  const { plugin } = createPlugin({ cancelError: new Error('native bridge failed') })

  const result = await cancelLocalNotification(42, { plugin })

  assert.equal(result, false)
})

test('cancel is a no-op for a non-numeric id', async () => {
  const { plugin, calls } = createPlugin()

  const result = await cancelLocalNotification(undefined, { plugin })

  assert.equal(result, false)
  assert.deepEqual(calls.cancel, [])
})
