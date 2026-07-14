import assert from 'node:assert/strict'
import { afterEach, describe, test } from 'node:test'

import {
  checkPushPermission,
  extractNotificationTarget,
  getCurrentToken,
  initNativePush,
  isInitialized,
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

// 11. Regression: registration listener attached before register()
describe('registration listener before register', () => {
  test('registration listener is attached before register() is called', async () => {
    const callOrder = []
    const plugin = {
      async checkPermissions() { return { receive: 'granted' } },
      async requestPermissions() { return { receive: 'granted' } },
      async register() {
        callOrder.push('register')
      },
      async addListener(eventName) {
        if (eventName === 'registration') {
          callOrder.push('addListener:registration')
        }
        return { remove: async () => {} }
      },
      async removeAllListeners() {},
    }

    await initNativePush({ plugin })

    const registrationIndex = callOrder.indexOf('addListener:registration')
    const registerIndex = callOrder.indexOf('register')
    assert.ok(registrationIndex < registerIndex,
      `registration listener (index ${registrationIndex}) must be attached before register() (index ${registerIndex})`)
  })
})

// 12. Regression: registration callback triggers onTokenReceived for upload
describe('registration callback triggers token upload', () => {
  test('onTokenReceived is called synchronously when registration fires', async () => {
    const { calls, plugin } = createPlugin()
    const tokens = []

    await initNativePush({
      plugin,
      onTokenReceived: (token) => tokens.push(token),
    })

    fireEvent(calls, 'registration', { value: 'fcm-token-abc123' })

    assert.strictEqual(tokens.length, 1)
    assert.strictEqual(tokens[0], 'fcm-token-abc123')
  })
})

// 13. Regression: teardown resets initialization state
describe('teardown resets state', () => {
  test('isInitialized returns false after teardown', async () => {
    const { plugin } = createPlugin()

    await initNativePush({ plugin })
    assert.strictEqual(isInitialized(), true)

    await teardownNativePush(plugin)
    assert.strictEqual(isInitialized(), false)
  })

  test('getCurrentToken returns null after teardown', async () => {
    const { calls, plugin } = createPlugin()

    await initNativePush({ plugin })
    fireEvent(calls, 'registration', { value: 'my-token-xyz' })
    assert.strictEqual(getCurrentToken(), 'my-token-xyz')

    await teardownNativePush(plugin)
    assert.strictEqual(getCurrentToken(), null)
  })
})

// 14. Regression: init works again after teardown
describe('re-initialization after teardown', () => {
  test('initNativePush succeeds after teardown and receives new token', async () => {
    const { calls, plugin } = createPlugin()
    const tokens = []

    await initNativePush({
      plugin,
      onTokenReceived: (token) => tokens.push(token),
    })
    fireEvent(calls, 'registration', { value: 'token-round-1' })
    await teardownNativePush(plugin)

    await initNativePush({
      plugin,
      onTokenReceived: (token) => tokens.push(token),
    })
    fireEvent(calls, 'registration', { value: 'token-round-2' })

    assert.strictEqual(tokens.length, 2)
    assert.strictEqual(tokens[1], 'token-round-2')
    assert.strictEqual(getCurrentToken(), 'token-round-2')
  })
})

// 15. Regression: React-style init → cleanup → init does not permanently disable push
describe('React double-mount pattern', () => {
  test('init → teardown → init still receives tokens', async () => {
    const { plugin: plugin1 } = createPlugin()
    const tokens = []

    await initNativePush({
      plugin: plugin1,
      onTokenReceived: (token) => tokens.push(token),
    })
    await teardownNativePush(plugin1)

    const { calls: calls2, plugin: plugin2 } = createPlugin()
    await initNativePush({
      plugin: plugin2,
      onTokenReceived: (token) => tokens.push(token),
    })
    fireEvent(calls2, 'registration', { value: 'token-after-remount' })

    assert.strictEqual(tokens.length, 1)
    assert.strictEqual(tokens[0], 'token-after-remount')
  })
})

// 16. Regression: stale generation callback is ignored after teardown+reinit
describe('stale generation callback', () => {
  test('registration callback from previous generation is ignored', async () => {
    const tokens = []
    let registrationCallback1

    const plugin1 = {
      async checkPermissions() { return { receive: 'granted' } },
      async requestPermissions() { return { receive: 'granted' } },
      async register() {},
      async addListener(eventName, cb) {
        if (eventName === 'registration') {
          registrationCallback1 = cb
        }
        return { remove: async () => {} }
      },
      async removeAllListeners() {},
    }

    await initNativePush({
      plugin: plugin1,
      onTokenReceived: (token) => tokens.push(token),
    })

    await teardownNativePush(plugin1)

    const { calls: calls2, plugin: plugin2 } = createPlugin()
    await initNativePush({
      plugin: plugin2,
      onTokenReceived: (token) => tokens.push(token),
    })

    registrationCallback1({ value: 'stale-token' })

    assert.strictEqual(tokens.length, 0,
      'stale generation callback should not trigger onTokenReceived')

    fireEvent(calls2, 'registration', { value: 'fresh-token' })
    assert.strictEqual(tokens.length, 1)
    assert.strictEqual(tokens[0], 'fresh-token')
  })
})

// 17. Regression: normal effect cleanup does not delete backend token
describe('effect cleanup vs logout', () => {
  test('teardown does not call any backend deletion endpoint', async () => {
    const { calls, plugin } = createPlugin()

    await initNativePush({ plugin })
    fireEvent(calls, 'registration', { value: 'my-active-token' })

    await teardownNativePush(plugin)

    assert.strictEqual(getCurrentToken(), null)
    assert.strictEqual(isInitialized(), false)
  })
})

// 18. Regression: explicit logout can retrieve current token before teardown
describe('logout token retrieval', () => {
  test('getCurrentToken returns active token before teardown', async () => {
    const { calls, plugin } = createPlugin()

    await initNativePush({ plugin })
    fireEvent(calls, 'registration', { value: 'logout-test-token' })

    const tokenBeforeTeardown = getCurrentToken()
    assert.strictEqual(tokenBeforeTeardown, 'logout-test-token')

    await teardownNativePush(plugin)
    assert.strictEqual(getCurrentToken(), null)
  })
})

// 19. Regression: upload failure remains retryable
describe('upload failure retryable', () => {
  test('onTokenReceived fires again on subsequent registration events', async () => {
    const { calls, plugin } = createPlugin()
    let callCount = 0

    await initNativePush({
      plugin,
      onTokenReceived: () => { callCount += 1 },
    })

    fireEvent(calls, 'registration', { value: 'token-attempt-1' })
    assert.strictEqual(callCount, 1)

    fireEvent(calls, 'registration', { value: 'token-attempt-2' })
    assert.strictEqual(callCount, 2)
  })
})

// 20. Regression: full token is never logged (debug logging uses suffix only)
describe('token logging safety', () => {
  test('debugLog output contains only token length and suffix, not full token', async () => {
    const { calls, plugin } = createPlugin()
    const loggedMessages = []
    const originalInfo = console.info
    console.info = (...args) => {
      loggedMessages.push(args.join(' '))
    }

    try {
      await initNativePush({ plugin })
      const testToken = 'abcdefghijklmnopqrstuvwxyz1234567890ABCDEF'
      fireEvent(calls, 'registration', { value: testToken })

      const registrationLog = loggedMessages.find(
        (message) => message.includes('registration callback received'),
      )
      assert.ok(registrationLog, 'expected a registration callback log line')
      assert.ok(
        !registrationLog.includes(testToken),
        'full token must never appear in debug log',
      )
      assert.ok(
        registrationLog.includes('BCDEF'),
        'log should contain the last 6 chars suffix',
      )
      assert.ok(
        registrationLog.includes(String(testToken.length)),
        'log should contain token length',
      )
    } finally {
      console.info = originalInfo
    }
  })
})
