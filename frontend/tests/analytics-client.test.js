// Regression lock for the transport contract of the analytics client
// (src/analytics/client.js, E09-02):
//
//   - every analytics batch POST MUST carry `skipAuthSessionCleanup: true`
//     so an analytics 401 can never trigger the Axios interceptor's session
//     cleanup (the interceptor side of this contract is locked in by
//     tests/auth-interceptor.test.js);
//   - no session token -> the queue is dropped and NO request is sent;
//   - invalid events are refused at trackEvent and never reach the wire.
//
// The REAL production module is imported; only its two dynamic imports
// (../api/client.js and ../api/sessionStorage.js) are aliased to in-test
// mocks via a node:module customization hook registered from this file --
// the same technique as tests/auth-interceptor.test.js, needed because
// src/api/client.js cannot load under plain `node --test` (extension-less
// import + top-level `import.meta.env`). Flushing is triggered
// deterministically through the client's own visibilitychange listener
// instead of waiting out the 15s interval.

import assert from 'node:assert/strict'
import test from 'node:test'
import { register } from 'node:module'

const state = {
  token: null,
  posts: [],
}
globalThis.__analyticsClientTest = state

// Minimal document stub so the client registers its visibilitychange
// listener (house pattern: stub globals for the duration of the file, each
// test file runs in its own process). Captured listeners let the test fire
// the client's own flush trigger on demand.
const documentListeners = { visibilitychange: [] }
globalThis.document = {
  visibilityState: 'visible',
  addEventListener(type, listener) {
    if (documentListeners[type]) {
      documentListeners[type].push(listener)
    }
  },
}

const apiClientMockSource = `
const state = globalThis.__analyticsClientTest
export const api = {
  post(path, body, config) {
    state.posts.push({ path, body, config })
    return Promise.resolve({ status: 202 })
  },
}
`

const sessionStorageMockSource = `
const state = globalThis.__analyticsClientTest
export function getToken() {
  return state.token
}
`

const hooksSource = `
const API_CLIENT_SOURCE = ${JSON.stringify(apiClientMockSource)}
const SESSION_SOURCE = ${JSON.stringify(sessionStorageMockSource)}

export async function resolve(specifier, context, nextResolve) {
  const parent = context.parentURL || ''
  if (parent.endsWith('/src/analytics/client.js')) {
    if (specifier === '../api/client.js') {
      return { url: 'mock:api-client', shortCircuit: true }
    }
    if (specifier === '../api/sessionStorage.js') {
      return { url: 'mock:session-storage', shortCircuit: true }
    }
  }
  return nextResolve(specifier, context)
}

export async function load(url, context, nextLoad) {
  if (url === 'mock:api-client') {
    return { format: 'module', shortCircuit: true, source: API_CLIENT_SOURCE }
  }
  if (url === 'mock:session-storage') {
    return { format: 'module', shortCircuit: true, source: SESSION_SOURCE }
  }
  return nextLoad(url, context)
}
`

register('data:text/javascript,' + encodeURIComponent(hooksSource))

const { trackEvent } = await import('../src/analytics/client.js')

function triggerVisibilityFlush() {
  assert.ok(
    documentListeners.visibilitychange.length >= 1,
    'the client must have registered a visibilitychange flush trigger',
  )
  globalThis.document.visibilityState = 'hidden'
  for (const listener of documentListeners.visibilitychange) {
    listener()
  }
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function waitFor(predicate, { timeoutMs = 2000 } = {}) {
  const startedAt = Date.now()
  while (!predicate()) {
    if (Date.now() - startedAt > timeoutMs) {
      throw new Error('timed out waiting for condition')
    }
    await wait(10)
  }
}

test('every analytics batch POST carries skipAuthSessionCleanup: true', async () => {
  state.token = 'stored-token'
  state.posts = []

  assert.equal(trackEvent('screen_view', { screen: 'map' }), true)
  triggerVisibilityFlush()
  await waitFor(() => state.posts.length === 1)

  const { path, body, config } = state.posts[0]
  assert.equal(path, '/analytics/events')
  assert.equal(config.skipAuthSessionCleanup, true)

  // The batch envelope itself stays anonymous and registry-shaped.
  assert.equal(body.events.length, 1)
  const event = body.events[0]
  assert.equal(event.event_name, 'screen_view')
  assert.equal(event.platform, 'web')
  assert.deepEqual(event.properties, { screen: 'map' })
  assert.equal(typeof event.occurred_at, 'string')
  assert.deepEqual(
    Object.keys(event).sort(),
    ['event_name', 'occurred_at', 'platform', 'properties'],
  )
})

test('without a session token the queue is dropped and nothing is sent', async () => {
  state.token = null
  state.posts = []

  assert.equal(trackEvent('screen_view', { screen: 'profile' }), true)
  triggerVisibilityFlush()
  await wait(150)

  assert.deepEqual(state.posts, [])

  // The drop is permanent: restoring the token and flushing again must not
  // resurrect the discarded event.
  state.token = 'stored-token'
  triggerVisibilityFlush()
  await wait(150)
  assert.deepEqual(state.posts, [])
})

test('registry-invalid events are refused before they can ever reach the wire', async () => {
  state.token = 'stored-token'
  state.posts = []

  assert.equal(trackEvent('screen_view', { screen: 'dashboard' }), false)
  assert.equal(trackEvent('screen_view', { screen: 'map', user_id: 'u-1' }), false)
  assert.equal(trackEvent('made_up_event', {}), false)
  triggerVisibilityFlush()
  await wait(150)

  assert.deepEqual(state.posts, [])
})
