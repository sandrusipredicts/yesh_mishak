import assert from 'node:assert/strict'
import { afterEach, describe, test } from 'node:test'

import {
  checkPushPermission,
  extractNotificationTarget,
  initNativePush,
  isNativePushSupported,
  requestPushPermission,
  teardownNativePush,
} from '../src/api/nativePushNotifications.js'

function createPlugin({
  checkStatus = { receive: 'granted' },
  requestStatus = { receive: 'granted' },
  registerError,
} = {}) {
  const calls = {
    checkPermissions: 0,
    requestPermissions: 0,
    register: 0,
    removeAllListeners: 0,
    listeners: {},
  }

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
      async register() {
        calls.register += 1
        if (registerError) {
          throw registerError
        }
      },
      async addListener(eventName, callback) {
        if (!calls.listeners[eventName]) {
          calls.listeners[eventName] = []
        }
        calls.listeners[eventName].push(callback)
        return { remove: async () => {} }
      },
      async removeAllListeners() {
        calls.removeAllListeners += 1
      },
    },
  }
}

function fireEvent(calls, eventName, data) {
  for (const callback of calls.listeners[eventName] || []) {
    callback(data)
  }
}

afterEach(async () => {
  await teardownNativePush()
})

// 1. Web platform — plugin not available
describe('web platform', () => {
  test('isNativePushSupported returns false when plugin is null', () => {
    assert.strictEqual(isNativePushSupported(null), false)
  })

  test('initNativePush returns unsupported when plugin is null', async () => {
    const result = await initNativePush({ plugin: null })
    assert.strictEqual(result.outcome, 'unsupported')
  })

  test('checkPushPermission returns unsupported when plugin is null', async () => {
    const result = await checkPushPermission(null)
    assert.strictEqual(result, 'unsupported')
  })

  test('requestPushPermission returns unsupported when plugin is null', async () => {
    const result = await requestPushPermission(null)
    assert.strictEqual(result, 'unsupported')
  })
})

// 2. Permission granted — registration attempted
describe('permission granted', () => {
  test('register is called after permission is granted', async () => {
    const { calls, plugin } = createPlugin()

    const result = await initNativePush({ plugin })

    assert.strictEqual(result.outcome, 'registered')
    assert.strictEqual(calls.register, 1)
    assert.strictEqual(calls.checkPermissions, 1)
  })
})

// 3. Permission denied — no registration
describe('permission denied', () => {
  test('register is not called when permission is denied', async () => {
    const { calls, plugin } = createPlugin({
      checkStatus: { receive: 'denied' },
      requestStatus: { receive: 'denied' },
    })

    const result = await initNativePush({ plugin })

    assert.strictEqual(result.outcome, 'denied')
    assert.strictEqual(calls.register, 0)
  })

  test('requestPushPermission does not re-request after denial', async () => {
    const { calls, plugin } = createPlugin({
      checkStatus: { receive: 'denied' },
    })

    const result = await requestPushPermission(plugin)

    assert.strictEqual(result, 'denied')
    assert.strictEqual(calls.requestPermissions, 0)
  })
})

// 4. Registration callback — token handled
describe('registration callback', () => {
  test('onTokenReceived fires with the token value', async () => {
    const { calls, plugin } = createPlugin()
    const receivedTokens = []

    await initNativePush({
      plugin,
      onTokenReceived: (token) => receivedTokens.push(token),
    })

    fireEvent(calls, 'registration', { value: 'test-fcm-token-123' })

    assert.strictEqual(receivedTokens.length, 1)
    assert.strictEqual(receivedTokens[0], 'test-fcm-token-123')
  })

  test('duplicate registration callbacks are handled', async () => {
    const { calls, plugin } = createPlugin()
    const receivedTokens = []

    await initNativePush({
      plugin,
      onTokenReceived: (token) => receivedTokens.push(token),
    })

    fireEvent(calls, 'registration', { value: 'token-a' })
    fireEvent(calls, 'registration', { value: 'token-a' })

    assert.strictEqual(receivedTokens.length, 2)
  })

  test('null token value is ignored', async () => {
    const { calls, plugin } = createPlugin()
    const receivedTokens = []

    await initNativePush({
      plugin,
      onTokenReceived: (token) => receivedTokens.push(token),
    })

    fireEvent(calls, 'registration', { value: null })
    fireEvent(calls, 'registration', {})

    assert.strictEqual(receivedTokens.length, 0)
  })
})

// 5. Registration error
describe('registration error', () => {
  test('onTokenError fires on registrationError event', async () => {
    const { calls, plugin } = createPlugin()
    const errors = []

    await initNativePush({
      plugin,
      onTokenError: (error) => errors.push(error),
    })

    fireEvent(calls, 'registrationError', { message: 'FCM unavailable' })

    assert.strictEqual(errors.length, 1)
    assert.strictEqual(errors[0].message, 'FCM unavailable')
  })

  test('register() failure returns registration-failed outcome', async () => {
    const { plugin } = createPlugin({
      registerError: new Error('native register failed'),
    })
    const errors = []

    const result = await initNativePush({
      plugin,
      onTokenError: (error) => errors.push(error),
    })

    assert.strictEqual(result.outcome, 'registration-failed')
    assert.strictEqual(errors.length, 1)
  })
})

// 6. Foreground notification
describe('foreground notification', () => {
  test('onForegroundNotification fires on pushNotificationReceived', async () => {
    const { calls, plugin } = createPlugin()
    const received = []

    await initNativePush({
      plugin,
      onForegroundNotification: (notification) => received.push(notification),
    })

    const payload = { title: 'New game', body: 'Near you', data: { game_id: 'abc' } }
    fireEvent(calls, 'pushNotificationReceived', payload)

    assert.strictEqual(received.length, 1)
    assert.strictEqual(received[0].title, 'New game')
  })
})

// 7. Notification tap — deep-link extraction
describe('notification tap', () => {
  test('valid game_id routes correctly', async () => {
    const { calls, plugin } = createPlugin()
    const targets = []

    await initNativePush({
      plugin,
      onNotificationTapped: (target) => targets.push(target),
    })

    fireEvent(calls, 'pushNotificationActionPerformed', {
      notification: {
        data: { game_id: '550e8400-e29b-41d4-a716-446655440000' },
      },
    })

    assert.strictEqual(targets.length, 1)
    assert.strictEqual(targets[0].routeType, 'game')
    assert.strictEqual(targets[0].resourceId, '550e8400-e29b-41d4-a716-446655440000')
  })

  test('valid field_id routes correctly', async () => {
    const { calls, plugin } = createPlugin()
    const targets = []

    await initNativePush({
      plugin,
      onNotificationTapped: (target) => targets.push(target),
    })

    fireEvent(calls, 'pushNotificationActionPerformed', {
      notification: {
        data: { field_id: '550e8400-e29b-41d4-a716-446655440000' },
      },
    })

    assert.strictEqual(targets.length, 1)
    assert.strictEqual(targets[0].routeType, 'field')
  })

  test('malformed payload is ignored safely', async () => {
    const { calls, plugin } = createPlugin()
    const targets = []

    await initNativePush({
      plugin,
      onNotificationTapped: (target) => targets.push(target),
    })

    fireEvent(calls, 'pushNotificationActionPerformed', {
      notification: { data: { game_id: 'not-a-uuid' } },
    })

    assert.strictEqual(targets.length, 1)
    assert.strictEqual(targets[0], null)
  })

  test('missing data produces null target', async () => {
    const { calls, plugin } = createPlugin()
    const targets = []

    await initNativePush({
      plugin,
      onNotificationTapped: (target) => targets.push(target),
    })

    fireEvent(calls, 'pushNotificationActionPerformed', {
      notification: {},
    })

    assert.strictEqual(targets.length, 1)
    assert.strictEqual(targets[0], null)
  })
})

// 8. extractNotificationTarget unit tests
describe('extractNotificationTarget', () => {
  test('returns null for null data', () => {
    assert.strictEqual(extractNotificationTarget(null), null)
  })

  test('returns null for empty object', () => {
    assert.strictEqual(extractNotificationTarget({}), null)
  })

  test('returns game target for valid game_id', () => {
    const target = extractNotificationTarget({
      game_id: '550e8400-e29b-41d4-a716-446655440000',
    })
    assert.deepStrictEqual(target, {
      routeType: 'game',
      resourceId: '550e8400-e29b-41d4-a716-446655440000',
    })
  })

  test('returns field target for valid field_id', () => {
    const target = extractNotificationTarget({
      field_id: '550e8400-e29b-41d4-a716-446655440000',
    })
    assert.deepStrictEqual(target, {
      routeType: 'field',
      resourceId: '550e8400-e29b-41d4-a716-446655440000',
    })
  })

  test('game_id takes priority over field_id', () => {
    const target = extractNotificationTarget({
      game_id: '550e8400-e29b-41d4-a716-446655440000',
      field_id: '660e8400-e29b-41d4-a716-446655440000',
    })
    assert.strictEqual(target.routeType, 'game')
  })

  test('ignores non-uuid game_id', () => {
    assert.strictEqual(
      extractNotificationTarget({ game_id: 'bad-id' }),
      null,
    )
  })

  test('ignores non-string game_id', () => {
    assert.strictEqual(
      extractNotificationTarget({ game_id: 12345 }),
      null,
    )
  })

  test('supports camelCase gameId key', () => {
    const target = extractNotificationTarget({
      gameId: '550e8400-e29b-41d4-a716-446655440000',
    })
    assert.strictEqual(target.routeType, 'game')
  })

  test('supports camelCase fieldId key', () => {
    const target = extractNotificationTarget({
      fieldId: '550e8400-e29b-41d4-a716-446655440000',
    })
    assert.strictEqual(target.routeType, 'field')
  })
})

// 9. Listener lifecycle — no duplicates
describe('listener lifecycle', () => {
  test('repeated init returns already-initialized', async () => {
    const { plugin } = createPlugin()

    const first = await initNativePush({ plugin })
    const second = await initNativePush({ plugin })

    assert.strictEqual(first.outcome, 'registered')
    assert.strictEqual(second.outcome, 'already-initialized')
  })

  test('teardown allows re-initialization', async () => {
    const { calls, plugin } = createPlugin()

    await initNativePush({ plugin })
    await teardownNativePush(plugin)
    const result = await initNativePush({ plugin })

    assert.strictEqual(result.outcome, 'registered')
    assert.strictEqual(calls.register, 2)
    assert.strictEqual(calls.removeAllListeners, 1)
  })
})

// 10. Permission prompt flow
describe('permission prompt flow', () => {
  test('requests permission when status is prompt', async () => {
    const { calls, plugin } = createPlugin({
      checkStatus: { receive: 'prompt' },
      requestStatus: { receive: 'granted' },
    })

    const result = await requestPushPermission(plugin)

    assert.strictEqual(result, 'granted')
    assert.strictEqual(calls.requestPermissions, 1)
  })

  test('does not request when already granted', async () => {
    const { calls, plugin } = createPlugin({
      checkStatus: { receive: 'granted' },
    })

    const result = await requestPushPermission(plugin)

    assert.strictEqual(result, 'granted')
    assert.strictEqual(calls.requestPermissions, 0)
  })
})
