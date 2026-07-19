import { expect, test } from '@playwright/test'

const user = {
  id: '31b6ac09-74f0-49f4-8916-c216842a3498',
  name: 'Restored User',
  email: 'restored@example.com',
}

const cachedField = {
  id: '00ca4294-5f1e-4b42-8c76-2fd683688eaa',
  name: 'Cached Native Field',
  latitude: 30.9872,
  longitude: 34.9314,
  sport_type: 'football',
  surface_type: 'synthetic',
  has_nets: true,
  has_water_cooler: false,
  opening_hours: '',
  notes: '',
  status: 'approved',
  active_game: null,
  upcoming_games: [],
}

function makeJwt(subject = user.id) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url')
  return `${encode({ alg: 'none' })}.${encode({ sub: subject })}.signature`
}

async function prepareApp(page, token) {
  await page.addInitScript(({ storedToken, storedUser }) => {
    window.androidBridge = {}
    window.__secureToken = storedToken
    window.__secureTokenRemoved = false
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
          window.__appListenerRemovals = (window.__appListenerRemovals || 0) + 1
          return Promise.resolve()
        }
        if (method === 'internalGetItem') {
          return Promise.resolve({ data: window.__secureToken })
        }
        if (method === 'internalSetItem') {
          window.__secureToken = options.data
          return Promise.resolve()
        }
        if (method === 'internalRemoveItem') {
          window.__secureToken = null
          window.__secureTokenRemoved = true
          return Promise.resolve({ success: true })
        }
        return Promise.resolve({ keys: [] })
      },
      nativeCallback(plugin, method, options, callback) {
        if (plugin === 'App' && method === 'addListener' && options.eventName === 'appStateChange') {
          window.__appStateChangeCallbacks = window.__appStateChangeCallbacks || []
          window.__appStateChangeCallbacks.push(callback)
          window.__appStateChange = callback
          window.__appListenerRegistrations = (window.__appListenerRegistrations || 0) + 1
          return 'issue-230-listener'
        }
        return ''
      },
    }

    localStorage.setItem('language_selected', 'true')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('onboarding_done', 'true')
    // Seeded directly for this account so it resolves straight to the map
    // rather than the city-only requiredStep (E08-02 follow-up fix) —
    // this file tests session restoration, not city selection.
    localStorage.setItem('starting_city:31b6ac09-74f0-49f4-8916-c216842a3498', 'ירושלים')

    if (storedToken) {
      localStorage.setItem('currentUserId', storedUser.id)
      localStorage.setItem('currentUserName', storedUser.name)
      localStorage.setItem('currentUserEmail', storedUser.email)
    }
  }, { storedToken: token, storedUser: user })

  await page.route('**/fields/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/games/active/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/games/upcoming/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/notifications/unread-count', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{"count":0}' }))
}

test('missing token finishes auth checking unauthenticated', async ({ page }) => {
  await prepareApp(page, null)
  await page.goto('/')

  await expect(page.locator('.login-page')).toBeVisible()
  await expect(page.getByTestId('auth-checking')).toHaveCount(0)
})

test('valid stored token restores authenticated state', async ({ page }) => {
  await prepareApp(page, makeJwt())
  await page.route('**/games/me', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))

  await page.goto('/')

  await expect(page.locator('.auth-toolbar')).toContainText(user.name)
  await expect(page.locator('.login-page')).toHaveCount(0)
})

test('login does not render before startup validation completes', async ({ page }) => {
  await prepareApp(page, makeJwt())
  let finishValidation
  await page.route('**/games/me', async (route) => {
    await new Promise((resolve) => {
      finishValidation = resolve
    })
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  await page.goto('/')
  await expect(page.getByTestId('auth-checking')).toBeVisible()
  await expect(page.locator('.login-page')).toHaveCount(0)
  await expect.poll(() => typeof finishValidation).toBe('function')

  finishValidation()
  await expect(page.locator('.auth-toolbar')).toBeVisible()
})

test('authenticated requests after restore use the restored bearer token', async ({ page }) => {
  const token = makeJwt()
  await prepareApp(page, token)

  const authorizations = { gamesMe: [], unreadCount: [] }
  await page.route('**/games/me', (route) => {
    authorizations.gamesMe.push(route.request().headers().authorization ?? null)
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })
  await page.route('**/notifications/unread-count', (route) => {
    authorizations.unreadCount.push(route.request().headers().authorization ?? null)
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"unread_count":0}' })
  })

  await page.goto('/')
  await expect(page.locator('.auth-toolbar')).toContainText(user.name)

  // Startup validation authenticated with the restored token, and every
  // authenticated API call after the restore carries that same token —
  // not a transient in-memory value from a login flow.
  expect(authorizations.gamesMe[0]).toBe(`Bearer ${token}`)
  await expect.poll(() => authorizations.unreadCount.length).toBeGreaterThan(0)
  expect(authorizations.unreadCount.every((value) => value === `Bearer ${token}`)).toBe(true)
})

test('corrupted token fails closed and clears auth state', async ({ page }) => {
  await prepareApp(page, 'corrupted-token')
  await page.goto('/')

  await expect(page.locator('.login-page')).toBeVisible()
  await expect.poll(() => page.evaluate(() => ({
    token: window.__secureToken,
    tokenRemoved: window.__secureTokenRemoved,
    id: localStorage.getItem('currentUserId'),
  }))).toEqual({ token: null, tokenRemoved: true, id: null })
})

test('401 during startup clears stored session and logs out', async ({ page }) => {
  await prepareApp(page, makeJwt())
  await page.route('**/games/me', (route) =>
    route.fulfill({ status: 401, contentType: 'application/json', body: '{}' }))

  await page.goto('/')

  await expect(page.locator('.login-page')).toBeVisible()
  await expect.poll(() => page.evaluate(() => ({
    secureToken: window.__secureToken,
    localToken: localStorage.getItem('access_token'),
  }))).toEqual({ secureToken: null, localToken: null })
})

test('native network failure during startup keeps secure session and cached map markers', async ({
  page,
}) => {
  const token = makeJwt()
  await prepareApp(page, token)
  await page.addInitScript((field) => {
    Object.defineProperty(navigator, 'onLine', {
      configurable: true,
      get: () => false,
    })
    localStorage.setItem('cached_fields', JSON.stringify([field]))
    localStorage.setItem('cached_fields_timestamp', '2026-07-14T14:08:28.662Z')
  }, cachedField)
  await page.route('**/games/me', (route) => route.abort('internetdisconnected'))
  await page.route('**/fields/**', (route) => route.abort('internetdisconnected'))

  await page.goto('/')

  await expect(page.locator('.auth-toolbar')).toContainText(user.name)
  await expect(page.locator('.login-page')).toHaveCount(0)
  await expect(page.locator('.field-marker-icon')).toHaveCount(1)
  await expect.poll(() => page.evaluate(() => ({
    secureToken: window.__secureToken,
    localToken: localStorage.getItem('access_token'),
    cachedFieldIds: JSON.parse(localStorage.getItem('cached_fields') ?? '[]')
      .map((field) => field.id),
  }))).toEqual({
    secureToken: token,
    localToken: null,
    cachedFieldIds: [cachedField.id],
  })
})

test('background resume revalidates once while a validation is in flight', async ({ page }) => {
  await prepareApp(page, makeJwt())
  let validationRequests = 0
  let finishResume
  await page.route('**/games/me', async (route) => {
    validationRequests += 1
    if (validationRequests === 2) {
      await new Promise((resolve) => {
        finishResume = resolve
      })
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })
  await page.goto('/')
  await expect(page.locator('.auth-toolbar')).toBeVisible()

  await expect.poll(() =>
    page.evaluate(() => {
      const registrations = window.__appListenerRegistrations || 0
      const removals = window.__appListenerRemovals || 0

      return {
        listenerType: typeof window.__appStateChange,
        callbackCount: window.__appStateChangeCallbacks?.length || 0,
        activeListeners: registrations - removals,
      }
    }),
  ).toMatchObject({
    listenerType: 'function',
    callbackCount: expect.any(Number),
  })

  await page.evaluate(() => {
    for (const callback of window.__appStateChangeCallbacks || []) {
      callback({ isActive: false })
    }
  })
  await page.waitForTimeout(50)
  expect(validationRequests).toBe(1)

  await page.evaluate(() => {
    for (const callback of window.__appStateChangeCallbacks || []) {
      callback({ isActive: true })
      callback({ isActive: true })
    }
  })
  await expect.poll(() => validationRequests).toBe(2)
  finishResume()
  await page.waitForTimeout(50)
  expect(validationRequests).toBe(2)
})
