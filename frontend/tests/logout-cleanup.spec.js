import { expect, test } from '@playwright/test'

const user = {
  id: '31b6ac09-74f0-49f4-8916-c216842a3498',
  name: 'Logout User',
  email: 'logout@example.com',
}

function makeJwt(subject = user.id) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url')
  return `${encode({ alg: 'none' })}.${encode({ sub: subject })}.signature`
}

// Simulated native secure storage lives in a non-auth localStorage key so it
// survives page reloads: a reload then behaves like an app relaunch, reading
// whatever token state the previous "run" left behind. Seeding happens once.
async function prepareApp(page, token, { failSecureRemove = false } = {}) {
  await page.addInitScript(({ storedToken, storedUser, removeShouldFail }) => {
    const SECURE_BACKING_KEY = '__test_secure_token'

    window.androidBridge = {}
    window.__secureTokenRemoved = false
    window.__secureRemoveAttempts = 0
    window.__failSecureRemove = removeShouldFail
    window.Capacitor = {
      PluginHeaders: [{
        name: 'SecureStorage',
        methods: [
          { name: 'internalGetItem', rtype: 'promise' },
          { name: 'internalSetItem', rtype: 'promise' },
          { name: 'internalRemoveItem', rtype: 'promise' },
          { name: 'clearItemsWithPrefix', rtype: 'promise' },
          { name: 'getPrefixedKeys', rtype: 'promise' },
          { name: 'setSynchronizeKeychain', rtype: 'promise' },
        ],
      }, {
        name: 'App',
        methods: [
          { name: 'addListener', rtype: 'callback' },
          { name: 'removeListener', rtype: 'promise' },
        ],
      }],
      nativePromise(plugin, method, options) {
        if (plugin === 'App' && method === 'removeListener') {
          return Promise.resolve()
        }
        if (method === 'internalGetItem') {
          return Promise.resolve({ data: localStorage.getItem(SECURE_BACKING_KEY) })
        }
        if (method === 'internalSetItem') {
          localStorage.setItem(SECURE_BACKING_KEY, options.data)
          return Promise.resolve()
        }
        if (method === 'internalRemoveItem') {
          window.__secureRemoveAttempts += 1
          if (window.__failSecureRemove) {
            return Promise.reject(new Error('secure remove failed'))
          }
          localStorage.removeItem(SECURE_BACKING_KEY)
          window.__secureTokenRemoved = true
          return Promise.resolve({ success: true })
        }
        return Promise.resolve({ keys: [] })
      },
      nativeCallback(plugin, method, options, callback) {
        if (plugin === 'App' && method === 'addListener' && options.eventName === 'appStateChange') {
          window.__appStateChange = callback
          return 'issue-231-listener'
        }
        return ''
      },
    }

    localStorage.setItem('language_selected', 'true')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('onboarding_done', 'true')

    if (storedToken && !localStorage.getItem('__test_seeded')) {
      localStorage.setItem('__test_seeded', 'true')
      localStorage.setItem(SECURE_BACKING_KEY, storedToken)
      localStorage.setItem('currentUserId', storedUser.id)
      localStorage.setItem('currentUserName', storedUser.name)
      localStorage.setItem('currentUserEmail', storedUser.email)
      localStorage.setItem('currentUsername', 'logout-user')
      // Auth residue that secure logout must remove even though no current
      // code writes it: legacy localStorage keys and web sessionStorage.
      localStorage.setItem('authToken', storedToken)
      sessionStorage.setItem('access_token', storedToken)
      sessionStorage.setItem('currentUserId', storedUser.id)
      sessionStorage.setItem('authToken', storedToken)
    }
  }, { storedToken: token, storedUser: user, removeShouldFail: failSecureRemove })

  await page.route('**/fields/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/games/active/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/games/upcoming/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/notifications/unread-count', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{"count":0}' }))
  await page.route('**/auth/logout', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"ok"}' }))
}

async function loginAndLogout(page) {
  await page.route('**/games/me', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))
  await page.goto('/')
  await expect(page.locator('.auth-toolbar')).toContainText(user.name)

  await page.getByRole('button', { name: 'Logout' }).click()
  await expect(page.locator('.login-page')).toBeVisible()
}

test('logout clears the secure-storage token', async ({ page }) => {
  await prepareApp(page, makeJwt())
  await loginAndLogout(page)

  await expect.poll(() => page.evaluate(() => ({
    token: localStorage.getItem('__test_secure_token'),
    tokenRemoved: window.__secureTokenRemoved,
  }))).toEqual({ token: null, tokenRemoved: true })
})

test('logout clears localStorage auth data including legacy keys', async ({ page }) => {
  await prepareApp(page, makeJwt())
  await loginAndLogout(page)

  await expect.poll(() => page.evaluate(() => ({
    token: localStorage.getItem('access_token'),
    id: localStorage.getItem('currentUserId'),
    name: localStorage.getItem('currentUserName'),
    email: localStorage.getItem('currentUserEmail'),
    username: localStorage.getItem('currentUsername'),
    legacyToken: localStorage.getItem('authToken'),
  }))).toEqual({
    token: null,
    id: null,
    name: null,
    email: null,
    username: null,
    legacyToken: null,
  })
})

test('logout clears sessionStorage auth data', async ({ page }) => {
  await prepareApp(page, makeJwt())
  await loginAndLogout(page)

  await expect.poll(() => page.evaluate(() => ({
    token: sessionStorage.getItem('access_token'),
    id: sessionStorage.getItem('currentUserId'),
    legacyToken: sessionStorage.getItem('authToken'),
  }))).toEqual({ token: null, id: null, legacyToken: null })
})

test('logout clears in-memory auth state and authenticated UI', async ({ page }) => {
  await prepareApp(page, makeJwt())
  await loginAndLogout(page)

  await expect(page.locator('.auth-toolbar')).toHaveCount(0)
  await expect(page.locator('.login-page')).toBeVisible()
})

test('logout sends an authenticated revocation request to the server', async ({ page }) => {
  const token = makeJwt()
  await prepareApp(page, token)

  let logoutAuthorization = null
  await page.route('**/auth/logout', (route) => {
    logoutAuthorization = route.request().headers().authorization ?? null
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"ok"}' })
  })

  await loginAndLogout(page)

  await expect.poll(() => logoutAuthorization).toBe(`Bearer ${token}`)
})

test('relaunch after logout stays logged out and never sends a stale token', async ({ page }) => {
  await prepareApp(page, makeJwt())

  const gamesMeAuthorizations = []
  await page.route('**/games/me', (route) => {
    gamesMeAuthorizations.push(route.request().headers().authorization ?? null)
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  await page.goto('/')
  await expect(page.locator('.auth-toolbar')).toContainText(user.name)
  await page.getByRole('button', { name: 'Logout' }).click()
  await expect(page.locator('.login-page')).toBeVisible()
  await expect.poll(() => page.evaluate(() => window.__secureTokenRemoved)).toBe(true)

  const requestsBeforeRelaunch = gamesMeAuthorizations.length
  await page.reload()

  await expect(page.locator('.login-page')).toBeVisible()
  await expect(page.locator('.auth-toolbar')).toHaveCount(0)
  expect(gamesMeAuthorizations.length).toBe(requestsBeforeRelaunch)
})

test('background resume after logout does not revalidate or restore the user', async ({ page }) => {
  await prepareApp(page, makeJwt())

  let validationRequests = 0
  await page.route('**/games/me', (route) => {
    validationRequests += 1
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  await page.goto('/')
  await expect(page.locator('.auth-toolbar')).toContainText(user.name)
  const requestsWhileAuthenticated = validationRequests

  await page.getByRole('button', { name: 'Logout' }).click()
  await expect(page.locator('.login-page')).toBeVisible()
  await expect.poll(() => page.evaluate(() => window.__secureTokenRemoved)).toBe(true)

  await page.evaluate(() => {
    window.__appStateChange({ isActive: false })
    window.__appStateChange({ isActive: true })
  })
  await page.waitForTimeout(100)

  expect(validationRequests).toBe(requestsWhileAuthenticated)
  await expect(page.locator('.login-page')).toBeVisible()
  await expect(page.locator('.auth-toolbar')).toHaveCount(0)
})

test('logout wins over an in-flight session validation', async ({ page }) => {
  await prepareApp(page, makeJwt())

  let validationRequests = 0
  let finishResumeValidation
  await page.route('**/games/me', async (route) => {
    validationRequests += 1
    if (validationRequests > 1) {
      await new Promise((resolve) => {
        finishResumeValidation = resolve
      })
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  await page.goto('/')
  await expect(page.locator('.auth-toolbar')).toContainText(user.name)

  // Start a resume revalidation that hangs, then log out while it is in flight.
  await page.evaluate(() => {
    window.__appStateChange({ isActive: false })
    window.__appStateChange({ isActive: true })
  })
  await expect.poll(() => validationRequests).toBe(2)

  await page.getByRole('button', { name: 'Logout' }).click()
  await expect(page.locator('.login-page')).toBeVisible()

  // A late success response must not restore the logged-out user.
  await expect.poll(() => typeof finishResumeValidation).toBe('function')
  finishResumeValidation()
  await page.waitForTimeout(100)

  await expect(page.locator('.login-page')).toBeVisible()
  await expect(page.locator('.auth-toolbar')).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => localStorage.getItem('__test_secure_token'))).toBe(null)
})

test('secure-storage removal failure fails closed and surfaces a warning', async ({ page }) => {
  await prepareApp(page, makeJwt(), { failSecureRemove: true })
  await loginAndLogout(page)

  await expect(page.locator('.logout-warning')).toBeVisible()
  await expect(page.locator('.auth-toolbar')).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => ({
    attempts: window.__secureRemoveAttempts,
    localToken: localStorage.getItem('access_token'),
    sessionToken: sessionStorage.getItem('access_token'),
    id: localStorage.getItem('currentUserId'),
  }))).toEqual({ attempts: 2, localToken: null, sessionToken: null, id: null })
})
