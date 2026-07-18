import assert from 'node:assert/strict'
import test from 'node:test'

import { createMonitoringClient } from '../src/monitoring/client.js'

function createFakeAdapter({ throwOnInit = false } = {}) {
  const calls = []
  return {
    calls,
    init(options) {
      calls.push(['init', options])
      if (throwOnInit) {
        throw new Error('simulated SDK init failure')
      }
    },
    captureException(error, context) {
      calls.push(['captureException', error, context])
      return 'event-id-123'
    },
    captureMessage(message, level) {
      calls.push(['captureMessage', message, level])
      return 'event-id-456'
    },
    setUser(user) {
      calls.push(['setUser', user])
    },
    addBreadcrumb(breadcrumb) {
      calls.push(['addBreadcrumb', breadcrumb])
    },
    setTag(key, value) {
      calls.push(['setTag', key, value])
    },
  }
}

test('init(): a falsy `enabled` flag never calls the adapter and every helper stays a no-op', () => {
  const adapter = createFakeAdapter()
  const client = createMonitoringClient(adapter)

  client.init({ enabled: false, dsn: 'https://example.invalid/1' })

  assert.equal(client.isEnabled(), false)
  assert.equal(adapter.calls.length, 0)

  client.captureException(new Error('boom'))
  client.setUser('user-1')
  client.addBreadcrumb({ message: 'x' })
  assert.equal(adapter.calls.length, 0)
})

test('init(): missing DSN reaching this layer as enabled=false behaves identically to disabled', () => {
  // config.js is responsible for turning "no DSN" into enabled=false before
  // this layer ever sees it; this test locks in that this layer honors
  // whatever `enabled` it's given without re-deriving it from `dsn`.
  const adapter = createFakeAdapter()
  const client = createMonitoringClient(adapter)
  client.init({ enabled: false, dsn: '' })
  assert.equal(client.isEnabled(), false)
})

test('init(): a successful adapter.init() call enables reporting', () => {
  const adapter = createFakeAdapter()
  const client = createMonitoringClient(adapter)

  client.init({ enabled: true, dsn: 'https://example.invalid/1' })

  assert.equal(client.isEnabled(), true)
  assert.deepEqual(adapter.calls[0][0], 'init')
})

test('init(): an SDK initialization failure is caught, never throws, and leaves the client disabled', () => {
  const adapter = createFakeAdapter({ throwOnInit: true })
  const client = createMonitoringClient(adapter)

  assert.doesNotThrow(() => {
    client.init({ enabled: true, dsn: 'https://example.invalid/1' })
  })
  assert.equal(client.isEnabled(), false)

  // And every helper remains a safe no-op afterward -- app startup must
  // never be affected by a monitoring init failure.
  assert.doesNotThrow(() => client.captureException(new Error('boom')))
})

test('captureException(): forwards to the adapter and returns its event id once enabled', () => {
  const adapter = createFakeAdapter()
  const client = createMonitoringClient(adapter)
  client.init({ enabled: true })

  const eventId = client.captureException(new Error('boom'), { tags: { a: 1 } })

  assert.equal(eventId, 'event-id-123')
  const call = adapter.calls.find((c) => c[0] === 'captureException')
  assert.ok(call)
  assert.deepEqual(call[2], { tags: { a: 1 } })
})

test('captureException(): a throwing adapter call is swallowed and returns undefined', () => {
  const adapter = createFakeAdapter()
  adapter.captureException = () => {
    throw new Error('network unavailable')
  }
  const client = createMonitoringClient(adapter)
  client.init({ enabled: true })

  assert.doesNotThrow(() => {
    const result = client.captureException(new Error('boom'))
    assert.equal(result, undefined)
  })
})

test('setUser(): sets only the internal id on the adapter', () => {
  const adapter = createFakeAdapter()
  const client = createMonitoringClient(adapter)
  client.init({ enabled: true })

  client.setUser('user-1')

  const setUserCalls = adapter.calls.filter((c) => c[0] === 'setUser')
  assert.deepEqual(setUserCalls[setUserCalls.length - 1][1], { id: 'user-1' })
})

test('setUser(): always clears before setting -- account switch isolation', () => {
  const adapter = createFakeAdapter()
  const client = createMonitoringClient(adapter)
  client.init({ enabled: true })

  client.setUser('user-a')
  client.setUser('user-b')

  const setUserCalls = adapter.calls.filter((c) => c[0] === 'setUser')
  // Expect: [null, {id:'user-a'}, null, {id:'user-b'}] -- account B's set is
  // always immediately preceded by a clear, so nothing from A can survive a
  // merge into B's context.
  assert.deepEqual(
    setUserCalls.map((c) => c[1]),
    [null, { id: 'user-a' }, null, { id: 'user-b' }],
  )
})

test('clearUser(): sets the adapter user to null', () => {
  const adapter = createFakeAdapter()
  const client = createMonitoringClient(adapter)
  client.init({ enabled: true })

  client.setUser('user-1')
  client.clearUser()

  const setUserCalls = adapter.calls.filter((c) => c[0] === 'setUser')
  assert.equal(setUserCalls[setUserCalls.length - 1][1], null)
})

test('anonymous startup: clearUser() before any setUser() call never reuses a stale identity', () => {
  const adapter = createFakeAdapter()
  const client = createMonitoringClient(adapter)
  client.init({ enabled: true })

  client.clearUser()

  const setUserCalls = adapter.calls.filter((c) => c[0] === 'setUser')
  assert.deepEqual(setUserCalls.map((c) => c[1]), [null])
})

test('addBreadcrumb() and setTag() are safe no-ops before init', () => {
  const adapter = createFakeAdapter()
  const client = createMonitoringClient(adapter)

  assert.doesNotThrow(() => {
    client.addBreadcrumb({ message: 'x' })
    client.setTag('a', 'b')
  })
  assert.equal(adapter.calls.length, 0)
})
