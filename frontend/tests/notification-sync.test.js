import assert from 'node:assert/strict'
import { describe, test } from 'node:test'

import { createNotificationSync } from '../src/utils/notificationSync.js'

function deferred() {
  let resolve
  let reject
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function createFakeTimers() {
  let nextId = 1
  const timers = new Map()

  return {
    setTimeout(callback, delay) {
      const id = nextId
      nextId += 1
      timers.set(id, { callback, delay })
      return id
    },
    clearTimeout(id) {
      timers.delete(id)
    },
    runNext() {
      const [id, timer] = timers.entries().next().value || []
      if (!timer) {
        return false
      }
      timers.delete(id)
      timer.callback()
      return true
    },
    count() {
      return timers.size
    },
    delays() {
      return Array.from(timers.values()).map((timer) => timer.delay)
    },
  }
}

function flushPromises() {
  return new Promise((resolve) => {
    setImmediate(resolve)
  })
}

function createSync({
  notificationsResults = [],
  unreadResults = [],
  notificationErrors = [],
  unreadErrors = [],
  timers = createFakeTimers(),
} = {}) {
  const appliedNotifications = []
  const appliedUnreadCounts = []
  const errors = []
  let notificationCalls = 0
  let unreadCalls = 0

  const sync = createNotificationSync({
    loadNotifications: async () => {
      const callIndex = notificationCalls
      notificationCalls += 1
      if (notificationErrors[callIndex]) {
        throw notificationErrors[callIndex]
      }
      return notificationsResults[callIndex] ?? []
    },
    loadUnreadCount: async () => {
      const callIndex = unreadCalls
      unreadCalls += 1
      if (unreadErrors[callIndex]) {
        throw unreadErrors[callIndex]
      }
      return unreadResults[callIndex] ?? { unread_count: 0 }
    },
    onNotifications: (notifications) => appliedNotifications.push(notifications),
    onUnreadCount: (count) => appliedUnreadCounts.push(count),
    onError: (error) => errors.push(error),
    setTimeoutFn: timers.setTimeout,
    clearTimeoutFn: timers.clearTimeout,
  })

  return {
    sync,
    timers,
    appliedNotifications,
    appliedUnreadCounts,
    errors,
    calls: () => ({ notifications: notificationCalls, unread: unreadCalls }),
  }
}

describe('notificationSync', () => {
  test('refresh loads notifications and unread count from the backend', async () => {
    const { sync, appliedNotifications, appliedUnreadCounts } = createSync({
      notificationsResults: [[{ id: 'notification-1' }]],
      unreadResults: [{ unread_count: 1 }],
    })

    await sync.refresh()

    assert.deepEqual(appliedNotifications, [[{ id: 'notification-1' }]])
    assert.deepEqual(appliedUnreadCounts, [1])
  })

  test('foreground push triggers immediate refresh and one bounded retry', async () => {
    const { sync, timers, calls, appliedNotifications, appliedUnreadCounts } = createSync({
      notificationsResults: [[], [{ id: 'notification-1' }]],
      unreadResults: [{ unread_count: 0 }, { unread_count: 1 }],
    })

    sync.handleForegroundPush()
    await flushPromises()

    assert.deepEqual(calls(), { notifications: 1, unread: 1 })
    assert.equal(timers.count(), 1)
    assert.deepEqual(timers.delays(), [750])

    assert.equal(timers.runNext(), true)
    await flushPromises()

    assert.deepEqual(calls(), { notifications: 2, unread: 2 })
    assert.deepEqual(appliedNotifications, [[], [{ id: 'notification-1' }]])
    assert.deepEqual(appliedUnreadCounts, [0, 1])
    assert.equal(timers.count(), 0)
  })

  test('repeated foreground pushes keep only one retry timer', async () => {
    const { sync, timers, calls } = createSync({
      notificationsResults: [[], [], [{ id: 'notification-1' }]],
      unreadResults: [{ unread_count: 0 }, { unread_count: 0 }, { unread_count: 1 }],
    })

    sync.handleForegroundPush()
    sync.handleForegroundPush()
    await flushPromises()

    assert.deepEqual(calls(), { notifications: 2, unread: 2 })
    assert.equal(timers.count(), 1)

    timers.runNext()
    await flushPromises()

    assert.deepEqual(calls(), { notifications: 3, unread: 3 })
    assert.equal(timers.count(), 0)
  })

  test('dispose removes retry timer and prevents later state updates', async () => {
    const { sync, timers, appliedNotifications, appliedUnreadCounts } = createSync({
      notificationsResults: [[{ id: 'notification-1' }]],
      unreadResults: [{ unread_count: 1 }],
    })

    sync.handleForegroundPush()
    sync.dispose()
    await flushPromises()

    assert.equal(timers.count(), 0)
    assert.deepEqual(appliedNotifications, [])
    assert.deepEqual(appliedUnreadCounts, [])
  })

  test('stale responses cannot overwrite newer notification state', async () => {
    const oldNotifications = deferred()
    const oldUnread = deferred()
    const newNotifications = deferred()
    const newUnread = deferred()
    const appliedNotifications = []
    const appliedUnreadCounts = []
    let notificationCalls = 0
    let unreadCalls = 0

    const sync = createNotificationSync({
      loadNotifications: () => {
        notificationCalls += 1
        return notificationCalls === 1 ? oldNotifications.promise : newNotifications.promise
      },
      loadUnreadCount: () => {
        unreadCalls += 1
        return unreadCalls === 1 ? oldUnread.promise : newUnread.promise
      },
      onNotifications: (notifications) => appliedNotifications.push(notifications),
      onUnreadCount: (count) => appliedUnreadCounts.push(count),
    })

    const oldRefresh = sync.refresh()
    const newRefresh = sync.refresh()

    newNotifications.resolve([{ id: 'new' }])
    newUnread.resolve({ unread_count: 1 })
    await newRefresh

    oldNotifications.resolve([])
    oldUnread.resolve({ unread_count: 0 })
    await oldRefresh

    assert.deepEqual(appliedNotifications, [[{ id: 'new' }]])
    assert.deepEqual(appliedUnreadCounts, [1])
  })

  test('failed refresh reports the error without clearing existing state', async () => {
    const error = new Error('network failed')
    const { sync, appliedNotifications, appliedUnreadCounts, errors } = createSync({
      notificationErrors: [error],
    })

    const result = await sync.refresh()

    assert.equal(result.applied, false)
    assert.equal(result.error, error)
    assert.deepEqual(errors, [error])
    assert.deepEqual(appliedNotifications, [])
    assert.deepEqual(appliedUnreadCounts, [])
  })
})
