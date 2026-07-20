// Regression lock for the auth-safety contract of the Axios response
// interceptor in src/api/client.js (E09-02 follow-up):
//
//   - a 401 on a request flagged `skipAuthSessionCleanup: true` (analytics)
//     must NEVER clear the session / log the user out;
//   - a 401 on a normal request (flag absent) must keep clearing the session;
//   - no stored token means nothing to clean up, flag or no flag.
//
// The REAL production module is imported and its registered rejection
// handler is exercised directly -- no network, no axios adapter involved.
//
// Why the loader shim below exists: src/api/client.js is written for the
// Vite pipeline -- it imports './sessionStorage' without a file extension
// and reads `import.meta.env` at module top level, both of which are fatal
// under plain `node --test`. Production code must stay untouched, so a
// node:module customization hook (registered from this file only) aliases
// client.js's three internal imports to the in-test mocks required by this
// suite (clearSession / getToken / monitoring no-ops) and blanks
// `import.meta.env` to `({})`. Only imports made BY client.js are altered;
// axios and everything else resolve normally, and the interceptor source
// under test is byte-for-byte the production code.

import assert from 'node:assert/strict'
import test from 'node:test'
import { register } from 'node:module'

// Shared mock state. The mock modules below close over this global, so the
// interceptor's imported getToken/clearSession bindings report into it.
const state = {
  token: null,
  clearSessionCalls: 0,
  breadcrumbs: [],
  captured: [],
}
globalThis.__authInterceptorTest = state

const sessionStorageMockSource = `
const state = globalThis.__authInterceptorTest
export function getToken() {
  return state.token
}
export function clearSession() {
  state.clearSessionCalls += 1
  return Promise.resolve()
}
`

const monitoringMockSource = `
const state = globalThis.__authInterceptorTest
export function addBreadcrumb(breadcrumb) {
  state.breadcrumbs.push(breadcrumb)
}
export function captureException(error, context) {
  state.captured.push([error, context])
}
`

const redactionMockSource = `
export function toSafeUrlPath(url) {
  return String(url || '')
}
`

const hooksSource = `
const SESSION_SOURCE = ${JSON.stringify(sessionStorageMockSource)}
const MONITORING_SOURCE = ${JSON.stringify(monitoringMockSource)}
const REDACTION_SOURCE = ${JSON.stringify(redactionMockSource)}

export async function resolve(specifier, context, nextResolve) {
  const parent = context.parentURL || ''
  if (parent.endsWith('/src/api/client.js')) {
    if (specifier === './sessionStorage') {
      return { url: 'mock:session-storage', shortCircuit: true }
    }
    if (specifier === '../monitoring/index.js') {
      return { url: 'mock:monitoring', shortCircuit: true }
    }
    if (specifier === '../monitoring/redaction.js') {
      return { url: 'mock:redaction', shortCircuit: true }
    }
  }
  return nextResolve(specifier, context)
}

export async function load(url, context, nextLoad) {
  if (url === 'mock:session-storage') {
    return { format: 'module', shortCircuit: true, source: SESSION_SOURCE }
  }
  if (url === 'mock:monitoring') {
    return { format: 'module', shortCircuit: true, source: MONITORING_SOURCE }
  }
  if (url === 'mock:redaction') {
    return { format: 'module', shortCircuit: true, source: REDACTION_SOURCE }
  }
  if (url.endsWith('/src/api/client.js')) {
    const real = await nextLoad(url, context)
    const source = real.source.toString().replaceAll('import.meta.env', '({})')
    return { format: 'module', shortCircuit: true, source }
  }
  return nextLoad(url, context)
}
`

register('data:text/javascript,' + encodeURIComponent(hooksSource))

const { api } = await import('../src/api/client.js')

function getRejectedHandler() {
  const handlers = (api.interceptors.response.handlers || []).filter(Boolean)
  assert.equal(
    handlers.length,
    1,
    'expected exactly one response interceptor on the api client',
  )
  assert.equal(typeof handlers[0].rejected, 'function')
  return handlers[0].rejected
}

function makeError({ status, config } = {}) {
  const error = new Error(status ? `Request failed with status code ${status}` : 'Network Error')
  if (status !== undefined) {
    error.response = { status }
  }
  if (config !== undefined) {
    error.config = config
  }
  return error
}

async function invokeAndExpectRejection(error) {
  const rejected = getRejectedHandler()
  await assert.rejects(
    () => Promise.resolve(rejected(error)),
    (thrown) => thrown === error,
    'the interceptor must re-reject with the original error',
  )
}

function resetState({ token } = {}) {
  state.token = token ?? null
  state.clearSessionCalls = 0
  state.breadcrumbs = []
  state.captured = []
}

test('Case 1: 401 on an analytics request (skipAuthSessionCleanup: true) never clears the session', async () => {
  resetState({ token: 'stored-token' })

  await invokeAndExpectRejection(
    makeError({ status: 401, config: { skipAuthSessionCleanup: true, url: '/analytics/events' } }),
  )

  assert.equal(state.clearSessionCalls, 0)
})

test('Case 2: 401 on a normal request (flag absent) clears the session exactly once', async () => {
  resetState({ token: 'stored-token' })

  await invokeAndExpectRejection(
    makeError({ status: 401, config: { url: '/games/me' } }),
  )

  assert.equal(state.clearSessionCalls, 1)
})

test('Case 3: 401 with no stored token never clears the session', async () => {
  resetState({ token: null })

  await invokeAndExpectRejection(
    makeError({ status: 401, config: { url: '/games/me' } }),
  )

  assert.equal(state.clearSessionCalls, 0)
})

test('a 403 never triggers session cleanup, flag or no flag', async () => {
  resetState({ token: 'stored-token' })

  await invokeAndExpectRejection(makeError({ status: 403, config: { url: '/games/me' } }))
  await invokeAndExpectRejection(
    makeError({ status: 403, config: { skipAuthSessionCleanup: true, url: '/analytics/events' } }),
  )

  assert.equal(state.clearSessionCalls, 0)
})

test('a network error (no response) never triggers session cleanup', async () => {
  resetState({ token: 'stored-token' })

  await invokeAndExpectRejection(makeError({ config: { url: '/analytics/events' } }))

  assert.equal(state.clearSessionCalls, 0)
})

test('defensive: a 401 with error.config undefined does not throw and falls back to cleanup', async () => {
  // No config means the flag cannot be inspected; the production guard's
  // optional chaining must survive this shape, and the fail-safe default
  // (treat it as a normal 401 and clean up) is locked in here on purpose.
  resetState({ token: 'stored-token' })

  await invokeAndExpectRejection(makeError({ status: 401 }))

  assert.equal(state.clearSessionCalls, 1)
})
