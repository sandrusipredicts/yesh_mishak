import { expect, test } from '@playwright/test'

const userA = {
  id: '31b6ac09-74f0-49f4-8916-c216842a3498',
  name: 'User A',
  email: 'user-a@example.com',
  username: 'user-a',
  terms_accepted: true,
}

const userB = {
  id: '9c2f6f2e-df0b-4c39-8f42-9e2d0a2b7ce1',
  name: 'User B',
  email: 'user-b@example.com',
  username: 'user-b',
  terms_accepted: true,
}

function makeJwt(subject) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url')
  return `${encode({ alg: 'none' })}.${encode({ sub: subject })}.signature`
}

// Decodes the `sub` claim from a `Bearer <jwt>` header the way the real
// backend's require_active_user dependency would authenticate the request,
// so this fake backend rejects push-token calls sent without a valid token
// exactly like the production endpoint does.
function decodeJwtSub(authorizationHeader) {
  if (!authorizationHeader || !authorizationHeader.startsWith('Bearer ')) {
    return null
  }

  const token = authorizationHeader.slice('Bearer '.length)
  const parts = token.split('.')
  if (parts.length < 2) {
    return null
  }

  try {
    const payload = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'))
    return payload.sub || null
  } catch {
    return null
  }
}

// Fakes just enough of the real push_tokens semantics (upsert-by-token,
// owner-scoped delete, 401 without auth) to prove the frontend calls the
// endpoints with the right auth and ordering — the backend semantics
// themselves are covered by backend/tests/test_notifications.py.
async function registerFakePushTokenBackend(page) {
  const rows = new Map()
  const events = []

  await page.route('**/notifications/push-token', async (route) => {
    const request = route.request()
    const method = request.method()
    const authHeader = request.headers().authorization || null
    const userId = decodeJwtSub(authHeader)
    const body = request.postDataJSON() || {}

    events.push({ method, authHeader, body, userId })

    if (!userId) {
      return route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ error: true, code: 'AUTH_REQUIRED' }),
      })
    }

    if (method === 'POST') {
      rows.set(body.token, {
        userId,
        platform: body.platform || null,
        installationId: body.installation_id || null,
      })
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          message: 'Push token saved',
          push_token: { id: 'row-1', user_id: userId, token: body.token },
        }),
      })
    }

    if (method === 'DELETE') {
      const existing = rows.get(body.token)
      if (existing && existing.userId === userId) {
        rows.delete(body.token)
      }
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ message: 'Push token deleted' }),
      })
    }

    return route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
  })

  return { rows, events }
}

async function prepareApp(page) {
  await page.addInitScript(() => {
    window.androidBridge = {}
    window.__pushNativeCalls = { check: 0, request: 0, register: 0 }

    window.Capacitor = {
      PluginHeaders: [
        {
          name: 'App',
          methods: [
            { name: 'addListener', rtype: 'callback' },
            { name: 'removeListener', rtype: 'promise' },
          ],
        },
        {
          name: 'SecureStorage',
          methods: [
            { name: 'internalGetItem', rtype: 'promise' },
            { name: 'internalSetItem', rtype: 'promise' },
            { name: 'internalRemoveItem', rtype: 'promise' },
            { name: 'clearItemsWithPrefix', rtype: 'promise' },
            { name: 'getPrefixedKeys', rtype: 'promise' },
            { name: 'setSynchronizeKeychain', rtype: 'promise' },
          ],
        },
        {
          name: 'PushNotifications',
          methods: [
            { name: 'checkPermissions', rtype: 'promise' },
            { name: 'requestPermissions', rtype: 'promise' },
            { name: 'register', rtype: 'promise' },
            { name: 'addListener', rtype: 'callback' },
            { name: 'removeListener', rtype: 'promise' },
            { name: 'removeAllListeners', rtype: 'promise' },
          ],
        },
      ],
      nativePromise(plugin, method, options) {
        if (plugin === 'App' && method === 'removeListener') {
          return Promise.resolve()
        }
        if (plugin === 'SecureStorage') {
          const SECURE_BACKING_KEY = '__test_secure_token'
          if (method === 'internalGetItem') {
            return Promise.resolve({ data: localStorage.getItem(SECURE_BACKING_KEY) })
          }
          if (method === 'internalSetItem') {
            localStorage.setItem(SECURE_BACKING_KEY, options.data)
            return Promise.resolve()
          }
          if (method === 'internalRemoveItem') {
            localStorage.removeItem(SECURE_BACKING_KEY)
            return Promise.resolve({ success: true })
          }
          return Promise.resolve({ keys: [] })
        }
        if (plugin === 'PushNotifications') {
          if (method === 'checkPermissions') {
            window.__pushNativeCalls.check += 1
            return Promise.resolve({ receive: 'granted' })
          }
          if (method === 'requestPermissions') {
            window.__pushNativeCalls.request += 1
            return Promise.resolve({ receive: 'granted' })
          }
          if (method === 'register') {
            window.__pushNativeCalls.register += 1
            return Promise.resolve()
          }
          if (method === 'removeListener' || method === 'removeAllListeners') {
            return Promise.resolve()
          }
        }
        return Promise.resolve({})
      },
      nativeCallback(plugin, method, options, callback) {
        if (plugin === 'App' && method === 'addListener' && options.eventName === 'appStateChange') {
          window.__appStateChange = callback
          return 'app-state-listener'
        }
        if (plugin === 'PushNotifications' && method === 'addListener') {
          window.__pushListeners = window.__pushListeners || {}
          window.__pushListeners[options.eventName] = callback
          return `push-listener-${options.eventName}`
        }
        return ''
      },
    }

    localStorage.setItem('language_selected', 'true')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('onboarding_done', 'true')
    // This file exercises both userA and userB reaching the map, so each
    // account's own city is seeded directly rather than relying on the
    // one-shot legacy migration (which only ever claims the legacy city
    // for whichever account loads first) — otherwise the second account
    // would be routed to the city-only requiredStep instead of the map
    // (E08-02 follow-up fix), which is unrelated to what this file tests.
    localStorage.setItem('starting_city:31b6ac09-74f0-49f4-8916-c216842a3498', 'ירושלים')
    localStorage.setItem('starting_city:9c2f6f2e-df0b-4c39-8f42-9e2d0a2b7ce1', 'תל אביב-יפו')
  })

  await page.route('**/fields/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/games/active/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/games/upcoming/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/games/me', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))
  await page.route('**/notifications/unread-count', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{"count":0}' }))
  await page.route('**/notifications/preferences', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/auth/logout', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"ok"}' }))
  await page.route('**/auth/login', async (route) => {
    const body = route.request().postDataJSON() || {}
    const targetUser = body.username === userB.username ? userB : userA

    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ access_token: makeJwt(targetUser.id), user: targetUser }),
    })
  })
}

async function loginViaForm(page, user) {
  await page.waitForSelector('.login-page', { timeout: 15000 })
  const panel = page.locator('#login-tabpanel')
  await panel.locator('[name="username"]').fill(user.username)
  await panel.locator('[name="password"]').fill('irrelevant-password')
  await panel.locator('button[type="submit"]').click()
  await expect(page.locator('.auth-toolbar')).toContainText(user.name)
}

async function logout(page) {
  // A "no known fields" notice banner can overlap the toolbar once the map
  // actually resolves a real city (E08-02 follow-up fix seeded a real
  // starting_city for these accounts) — dismiss it before interacting
  // with Logout, matching the pattern used elsewhere for the same banner.
  await page.locator('.location-notice-dismiss').click({ timeout: 2000 }).catch(() => {})
  await page.getByRole('button', { name: 'Logout' }).click()
  await expect(page.locator('.login-page')).toBeVisible()
}

async function registerFakeFcmToken(page, token) {
  await page.waitForFunction(
    () => typeof window.__pushListeners?.registration === 'function',
    { timeout: 15000 },
  )
  await page.evaluate((value) => {
    window.__pushListeners.registration({ value })
  }, token)
}

async function explicitlyEnableNotifications(page) {
  await page.getByRole('button', { name: 'Notification preferences' }).click()
  await page.getByRole('button', { name: 'Enable push' }).click()
  await expect(page.getByText('Push notifications enabled on this browser.')).toBeVisible()
  await page.getByRole('button', { name: 'Close' }).click()
}

const FAKE_TOKEN = 'fake-fcm-token-e2e-1'

test('token registers with platform and installation id after explicit enable', async ({ page }) => {
  await prepareApp(page)
  const { rows } = await registerFakePushTokenBackend(page)

  await page.goto('/')
  await loginViaForm(page, userA)
  await explicitlyEnableNotifications(page)
  await registerFakeFcmToken(page, FAKE_TOKEN)

  await expect.poll(() => rows.size).toBe(1)
  const row = rows.get(FAKE_TOKEN)
  expect(row.userId).toBe(userA.id)
  expect(row.platform).toBe('android')
  expect(row.installationId).toBeTruthy()
})

test('logout sends an authenticated unregister request before auth is cleared, and the row is removed', async ({ page }) => {
  await prepareApp(page)
  const { rows, events } = await registerFakePushTokenBackend(page)

  await page.goto('/')
  await loginViaForm(page, userA)
  await explicitlyEnableNotifications(page)
  await registerFakeFcmToken(page, FAKE_TOKEN)
  await expect.poll(() => rows.size).toBe(1)

  const sessionToken = await page.evaluate(() => localStorage.getItem('__test_secure_token'))
  expect(sessionToken).toBeTruthy()

  await logout(page)

  await expect.poll(() => events.filter((event) => event.method === 'DELETE').length).toBe(1)
  const deleteEvent = events.find((event) => event.method === 'DELETE')

  // Regression check: the unregister request must carry the session's own
  // bearer token, not an anonymous request. Before the fix, App.jsx's
  // clearSession() nulled the in-memory token synchronously before axios's
  // request interceptor (a deferred microtask) ever read it for this call,
  // so the DELETE went out with no Authorization header and was rejected
  // with 401 by a `.catch()` that only logged a warning.
  expect(deleteEvent.authHeader).toBe(`Bearer ${sessionToken}`)
  expect(deleteEvent.body.token).toBe(FAKE_TOKEN)

  await expect.poll(() => rows.has(FAKE_TOKEN)).toBe(false)
})

test('re-login recreates exactly one row for the same installation', async ({ page }) => {
  await prepareApp(page)
  const { rows } = await registerFakePushTokenBackend(page)

  await page.goto('/')
  await loginViaForm(page, userA)
  await explicitlyEnableNotifications(page)
  await registerFakeFcmToken(page, FAKE_TOKEN)
  await expect.poll(() => rows.size).toBe(1)

  await logout(page)
  await expect.poll(() => rows.has(FAKE_TOKEN)).toBe(false)

  await loginViaForm(page, userA)
  await explicitlyEnableNotifications(page)
  await registerFakeFcmToken(page, FAKE_TOKEN)

  await expect.poll(() => rows.size).toBe(1)
  expect(rows.get(FAKE_TOKEN).userId).toBe(userA.id)
})

test('switching accounts on the same device does not leave the token attached to the previous user', async ({ page }) => {
  await prepareApp(page)
  const { rows } = await registerFakePushTokenBackend(page)

  await page.goto('/')
  await loginViaForm(page, userA)
  await explicitlyEnableNotifications(page)
  await registerFakeFcmToken(page, FAKE_TOKEN)
  await expect.poll(() => rows.get(FAKE_TOKEN)?.userId).toBe(userA.id)

  await logout(page)
  await expect.poll(() => rows.has(FAKE_TOKEN)).toBe(false)

  await loginViaForm(page, userB)
  await explicitlyEnableNotifications(page)
  await registerFakeFcmToken(page, FAKE_TOKEN)

  await expect.poll(() => rows.get(FAKE_TOKEN)?.userId).toBe(userB.id)
  expect(rows.size).toBe(1)
})

test('login alone does not check, request, or register native push', async ({ page }) => {
  await prepareApp(page)
  await page.goto('/')
  await loginViaForm(page, userA)
  await expect.poll(() => page.evaluate(() => window.__pushNativeCalls)).toEqual({
    check: 0,
    request: 0,
    register: 0,
  })
})
