import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'

const user = {
  id: '7c1c2f9e-1d24-4f77-b7a3-3f5d20b0a111',
  name: 'Native Google User',
  email: 'native.google@example.com',
}

function makeJwt(subject = user.id) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url')
  return `${encode({ alg: 'none' })}.${encode({ sub: subject })}.signature`
}

const FAKE_GOOGLE_ID_TOKEN = `${Buffer.from(JSON.stringify({ alg: 'RS256' })).toString('base64url')}.${Buffer.from(
  JSON.stringify({ aud: 'web-client-id', email: user.email, email_verified: true }),
).toString('base64url')}.google-signature`

const FIELD_ID = '11111111-1111-4111-8111-111111111111'
const GAME_ID = '22222222-2222-4222-8222-222222222222'

const field = {
  id: FIELD_ID,
  name: 'Deferred Link Court',
  latitude: 31.225172,
  longitude: 34.777498,
  sport_type: 'football',
  surface_type: 'synthetic',
  has_nets: true,
  has_water_cooler: false,
  opening_hours: '19:00',
  notes: '',
  status: 'approved',
  active_game: null,
  upcoming_games: [],
}

const game = {
  id: GAME_ID,
  field_id: FIELD_ID,
  sport_type: 'football',
  players_present: 4,
  max_players: 10,
  created_by: 'creator-1',
  started_at: '2099-07-12T10:00:00Z',
  expires_at: '2099-07-12T12:00:00Z',
  participants: [],
  status: 'open',
}

test('Android native auth logging is hardened against credential payloads', () => {
  const capacitorConfig = readFileSync('capacitor.config.ts', 'utf8')
  const googleProvider = readFileSync(
    'node_modules/@capgo/capacitor-social-login/android/src/main/java/ee/forgr/capacitor/social/login/GoogleProvider.java',
    'utf8',
  )

  expect(capacitorConfig).toContain("loggingBehavior: 'none'")
  expect(googleProvider).not.toContain('String.format("Google restoreState: %s", object)')
  expect(googleProvider).toContain('Google restoreState: credentials restored')
})

// Native mock: SecureStorage (certified pipeline), App, and the NA-1
// SocialLogin plugin. googleMode:
// 'success' | 'delayed-success' | 'cancel' | 'provider-failure' | 'missing-id-token'.
// providerLogoutFails makes the provider's logout reject (ISSUE-242: provider
// sign-out is best-effort and must never block local cleanup).
async function prepareApp(page, {
  googleMode = 'success',
  providerLogoutFails = false,
  launchUrl = null,
  analyticsEvents = null,
  analyticsStatus = 202,
  analyticsDelayMs = 0,
} = {}) {
  await page.addInitScript(({ cfg, googleIdToken }) => {
    const SECURE_BACKING_KEY = '__test_secure_token'

    window.androidBridge = {}
    window.__social = { initCalls: 0, loginCalls: 0, logoutCalls: 0, lastInit: null }
    window.__resolveSocialLogin = null
    window.__rejectSocialLogin = null

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
        name: 'SocialLogin',
        methods: [
          { name: 'initialize', rtype: 'promise' },
          { name: 'login', rtype: 'promise' },
          { name: 'logout', rtype: 'promise' },
        ],
      }, {
        name: 'App',
        methods: [
          { name: 'getLaunchUrl', rtype: 'promise' },
          { name: 'addListener', rtype: 'callback' },
          { name: 'removeListener', rtype: 'promise' },
        ],
      }],
      nativePromise(plugin, method, options) {
        if (plugin === 'App' && method === 'getLaunchUrl') {
          return Promise.resolve({ url: cfg.launchUrl })
        }
        if (plugin === 'App' && method === 'removeListener') {
          return Promise.resolve()
        }
        if (plugin === 'SocialLogin') {
          if (method === 'initialize') {
            window.__social.initCalls += 1
            window.__social.lastInit = options
            return Promise.resolve()
          }
          if (method === 'login') {
            window.__social.loginCalls += 1
            if (options?.options?.scopes?.length) {
              // Mirrors real device behavior: extra scopes require
              // MainActivity changes and reject outright.
              return Promise.reject(new Error('You CANNOT use scopes without modifying the main activity. Please follow the docs!'))
            }
            if (cfg.googleMode === 'cancel') {
              const cancelError = new Error('The user canceled the sign-in flow.')
              cancelError.code = 'USER_CANCELLED'
              return Promise.reject(cancelError)
            }
            if (cfg.googleMode === 'provider-failure') {
              const providerError = new Error('Developer-only provider detail')
              providerError.code = 'GOOGLE_SIGN_IN_FAILED'
              return Promise.reject(providerError)
            }
            if (cfg.googleMode === 'delayed-success') {
              return new Promise((resolve, reject) => {
                window.__resolveSocialLogin = () => resolve({
                  provider: 'google',
                  result: {
                    idToken: googleIdToken,
                    accessToken: null,
                    responseType: 'online',
                  },
                })
                window.__rejectSocialLogin = reject
              })
            }
            return Promise.resolve({
              provider: 'google',
              result: {
                idToken: cfg.googleMode === 'missing-id-token' ? null : googleIdToken,
                accessToken: null,
                responseType: 'online',
              },
            })
          }
          if (method === 'logout') {
            window.__social.logoutCalls += 1
            if (cfg.providerLogoutFails) {
              return Promise.reject(new Error('Credential Manager clearCredentialState failed'))
            }
            return Promise.resolve()
          }
        }
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
      },
      nativeCallback(plugin, method, options, callback) {
        if (plugin === 'App' && method === 'addListener' && options.eventName === 'appStateChange') {
          window.__appStateChange = callback
          return 'issue-240-listener'
        }
        if (plugin === 'App' && method === 'addListener' && options.eventName === 'appUrlOpen') {
          window.__appUrlOpen = callback
          return 'app-url-open-listener'
        }
        return ''
      },
    }

    localStorage.setItem('language_selected', 'true')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('onboarding_done', 'true')
  }, { cfg: { googleMode, providerLogoutFails, launchUrl }, googleIdToken: FAKE_GOOGLE_ID_TOKEN })

  await page.route(/\/analytics\/share-events$/, async (route) => {
    if (analyticsEvents) {
      analyticsEvents.push(route.request().postDataJSON())
    }
    if (analyticsDelayMs > 0) {
      await new Promise((resolve) => setTimeout(resolve, analyticsDelayMs))
    }
    return route.fulfill({ status: analyticsStatus, contentType: 'application/json', body: '{}' })
  })
  await page.route(/\/fields\/?(\?.*)?$/, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route(/\/fields\/[0-9a-f-]+$/i, (route) => {
    const id = new URL(route.request().url()).pathname.split('/').filter(Boolean).pop()
    if (id === FIELD_ID) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ...field, active_game: game }) })
    }
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Field not found"}' })
  })
  await page.route(/\/games\/[0-9a-f-]+$/i, (route) => {
    const id = new URL(route.request().url()).pathname.split('/').filter(Boolean).pop()
    if (id === GAME_ID) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(game) })
    }
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"Game not found"}' })
  })
  await page.route('**/games/active/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/games/upcoming/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/games/me', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))
  await page.route('**/notifications/unread-count', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{"count":0}' }))
  await page.route('**/auth/logout', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"ok"}' }))
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
}

function routeGoogleExchange(page, { status = 200, networkError = false } = {}) {
  const exchanges = []
  page.route('**/auth/google', async (route) => {
    const body = route.request().postDataJSON()
    exchanges.push(body)
    if (networkError) {
      return route.abort('internetdisconnected')
    }
    if (status !== 200) {
      return route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Invalid Google token' }),
      })
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ access_token: makeJwt(), token_type: 'bearer', user }),
    })
  })
  return exchanges
}

async function seedPartialSession(page) {
  await page.evaluate(() => {
    localStorage.setItem('__test_secure_token', 'stale-secure-token')
    localStorage.setItem('access_token', 'stale-plaintext-token')
    localStorage.setItem('authToken', 'stale-legacy-token')
    localStorage.setItem('currentUserId', 'stale-user')
    sessionStorage.setItem('access_token', 'stale-session-token')
  })
}

async function expectFailedAttemptCleanedUp(page) {
  await expect(page.locator('.google-native-button')).toBeEnabled()
  await expect(page.locator('.auth-toolbar')).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => ({
    secure: localStorage.getItem('__test_secure_token'),
    plaintext: localStorage.getItem('access_token'),
    legacy: localStorage.getItem('authToken'),
    id: localStorage.getItem('currentUserId'),
    session: sessionStorage.getItem('access_token'),
  }))).toEqual({
    secure: null,
    plaintext: null,
    legacy: null,
    id: null,
    session: null,
  })
}

test('native Google login succeeds through the plugin and certified pipeline', async ({ page }) => {
  await prepareApp(page)
  const exchanges = routeGoogleExchange(page)

  await page.goto('/')
  await expect(page.locator('.google-native-button')).toBeEnabled({ timeout: 15000 })

  await page.locator('.google-native-button').click()
  await expect(page.locator('.auth-toolbar')).toContainText(user.name, { timeout: 15000 })

  const state = await page.evaluate(() => ({
    init: window.__social.lastInit,
    loginCalls: window.__social.loginCalls,
    secureToken: localStorage.getItem('__test_secure_token'),
    plaintext: localStorage.getItem('access_token'),
    sessionKeys: sessionStorage.length,
  }))
  expect(state.loginCalls).toBe(1)
  // serverClientId contract: initialized with the web OAuth client ID.
  expect(state.init?.google?.webClientId).toMatch(/\.apps\.googleusercontent\.com$/)
  // Google ID token was exchanged, app JWT stored securely, no web-storage JWT.
  expect(exchanges.length).toBe(1)
  expect(exchanges[0].token).toBeTruthy()
  expect(state.secureToken).toMatch(/^eyJ/)
  expect(state.plaintext).toBeNull()
  expect(state.sessionKeys).toBe(0)
})

test('native Google login succeeds after a deferred cold-start game deep link', async ({ page }) => {
  const analyticsEvents = []
  const deepLinkUrl = `https://yesh-mishak.com/game/${GAME_ID}`
  await prepareApp(page, { launchUrl: deepLinkUrl, analyticsEvents })
  const exchanges = routeGoogleExchange(page)

  await page.goto('/')
  await expect(page.locator('.google-native-button')).toBeEnabled({ timeout: 15000 })
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem('pending_deep_link'))))
    .toMatchObject({ routeType: 'game', resourceId: GAME_ID, analyticsDeferred: true })

  await page.locator('.google-native-button').click()

  await expect(page.locator('.auth-toolbar')).toContainText(user.name, { timeout: 15000 })
  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: field.name }),
  ).toBeVisible({ timeout: 15000 })

  const state = await page.evaluate(() => ({
    loginCalls: window.__social.loginCalls,
    pendingLink: sessionStorage.getItem('pending_deep_link'),
  }))
  expect(state.loginCalls).toBe(1)
  expect(exchanges.length).toBe(1)
  expect(state.pendingLink).toBeNull()
  expect(analyticsEvents.filter((event) => event.event_name === 'link_open')).toEqual([{
    event_name: 'link_open',
    entity_type: 'game',
    platform: 'android',
    outcome: 'deferred_for_auth',
  }])
})

test('duplicate app-link delivery while native Google login is pending does not replay login or analytics', async ({ page }) => {
  const analyticsEvents = []
  const deepLinkUrl = `https://yesh-mishak.com/game/${GAME_ID}`
  await prepareApp(page, {
    googleMode: 'delayed-success',
    launchUrl: deepLinkUrl,
    analyticsEvents,
  })
  const exchanges = routeGoogleExchange(page)

  await page.goto('/')
  await expect(page.locator('.google-native-button')).toBeEnabled({ timeout: 15000 })
  await page.locator('.google-native-button').click()
  await expect.poll(() => page.evaluate(() => window.__social.loginCalls)).toBe(1)

  await page.evaluate((url) => {
    window.__appUrlOpen?.({ url })
  }, deepLinkUrl)
  await expect.poll(() => page.evaluate(() => window.__social.loginCalls)).toBe(1)
  expect(analyticsEvents.filter((event) => event.event_name === 'link_open')).toEqual([{
    event_name: 'link_open',
    entity_type: 'game',
    platform: 'android',
    outcome: 'deferred_for_auth',
  }])

  await page.evaluate(() => window.__resolveSocialLogin())

  await expect(page.locator('.auth-toolbar')).toContainText(user.name, { timeout: 15000 })
  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: field.name }),
  ).toBeVisible({ timeout: 15000 })

  const state = await page.evaluate(() => ({
    loginCalls: window.__social.loginCalls,
    pendingLink: sessionStorage.getItem('pending_deep_link'),
  }))
  expect(state.loginCalls).toBe(1)
  expect(exchanges.length).toBe(1)
  expect(state.pendingLink).toBeNull()
  expect(analyticsEvents.filter((event) => event.event_name === 'link_open')).toHaveLength(1)
})

test('late unauthenticated analytics failure cannot clear a freshly saved Google session', async ({ page }) => {
  const analyticsEvents = []
  const deepLinkUrl = `https://yesh-mishak.com/game/${GAME_ID}`
  await prepareApp(page, {
    launchUrl: deepLinkUrl,
    analyticsEvents,
    analyticsStatus: 401,
    analyticsDelayMs: 300,
  })
  const exchanges = routeGoogleExchange(page)

  await page.goto('/')
  await expect(page.locator('.google-native-button')).toBeEnabled({ timeout: 15000 })
  await page.locator('.google-native-button').click()

  await expect(page.locator('.auth-toolbar')).toContainText(user.name, { timeout: 15000 })
  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: field.name }),
  ).toBeVisible({ timeout: 15000 })

  await expect.poll(() => page.evaluate(() => ({
    secureToken: localStorage.getItem('__test_secure_token'),
    currentUserId: localStorage.getItem('currentUserId'),
    toolbarCount: document.querySelectorAll('.auth-toolbar').length,
  }))).toEqual({
    secureToken: expect.stringMatching(/^eyJ/),
    currentUserId: user.id,
    toolbarCount: 1,
  })
  expect(exchanges.length).toBe(1)
  expect(analyticsEvents.filter((event) => event.event_name === 'link_open')).toHaveLength(1)
})

test('unrelated app-link callback while native Google login is pending does not cancel login', async ({ page }) => {
  const analyticsEvents = []
  const deepLinkUrl = `https://yesh-mishak.com/game/${GAME_ID}`
  await prepareApp(page, {
    googleMode: 'delayed-success',
    launchUrl: deepLinkUrl,
    analyticsEvents,
  })
  const exchanges = routeGoogleExchange(page)

  await page.goto('/')
  await expect(page.locator('.google-native-button')).toBeEnabled({ timeout: 15000 })
  await page.locator('.google-native-button').click()
  await expect.poll(() => page.evaluate(() => window.__social.loginCalls)).toBe(1)

  await page.evaluate(() => {
    window.__appUrlOpen?.({ url: 'https://yesh-mishak.com/not-a-supported-route' })
  })
  await page.evaluate(() => window.__resolveSocialLogin())

  await expect(page.locator('.auth-toolbar')).toContainText(user.name, { timeout: 15000 })
  expect(exchanges.length).toBe(1)
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('pending_deep_link')))
    .toBeNull()
  expect(analyticsEvents.filter((event) => event.event_name === 'link_open')).toEqual([
    {
      event_name: 'link_open',
      entity_type: 'game',
      platform: 'android',
      outcome: 'deferred_for_auth',
    },
  ])
})

test('native Google cancellation after a deferred deep link remains cancellation and keeps pending link', async ({ page }) => {
  const analyticsEvents = []
  const deepLinkUrl = `https://yesh-mishak.com/game/${GAME_ID}`
  await prepareApp(page, { googleMode: 'cancel', launchUrl: deepLinkUrl, analyticsEvents })
  const exchanges = routeGoogleExchange(page)

  await page.goto('/')
  await expect(page.locator('.google-native-button')).toBeEnabled({ timeout: 15000 })
  await page.locator('.google-native-button').click()

  await expect(page.locator('.login-page')).toBeVisible()
  await expect(page.locator('.login-error')).toHaveCount(0)
  await expect(page.locator('.login-info')).toHaveText('Sign-in cancelled. You can try again.')
  expect(exchanges.length).toBe(0)
  await expect.poll(() => page.evaluate(() => JSON.parse(sessionStorage.getItem('pending_deep_link'))))
    .toMatchObject({ routeType: 'game', resourceId: GAME_ID, analyticsDeferred: true })
  expect(analyticsEvents.filter((event) => event.event_name === 'link_open')).toEqual([{
    event_name: 'link_open',
    entity_type: 'game',
    platform: 'android',
    outcome: 'deferred_for_auth',
  }])
})

test('cancelling the native picker shows neutral feedback and clears partial state', async ({ page }) => {
  await prepareApp(page, { googleMode: 'cancel' })
  const exchanges = routeGoogleExchange(page)

  await page.goto('/')
  await expect(page.locator('.google-native-button')).toBeEnabled({ timeout: 15000 })
  await seedPartialSession(page)
  await page.locator('.google-native-button').click()

  await expect(page.locator('.login-page')).toBeVisible()
  await expect(page.locator('.login-error')).toHaveCount(0)
  await expect(page.locator('.login-info')).toHaveText('Sign-in cancelled. You can try again.')
  expect(exchanges.length).toBe(0)
  await expectFailedAttemptCleanedUp(page)
})

test('network failure shows retry-friendly feedback and clears partial state', async ({ page }) => {
  await prepareApp(page)
  routeGoogleExchange(page, { networkError: true })

  await page.goto('/')
  await expect(page.locator('.google-native-button')).toBeEnabled({ timeout: 15000 })
  await seedPartialSession(page)
  await page.locator('.google-native-button').click()

  await expect(page.locator('.login-error')).toHaveText(
    'We could not connect. Check your internet connection and try again.',
  )
  await expectFailedAttemptCleanedUp(page)
})

for (const status of [400, 401, 403]) {
  test(`backend ${status} shows verification failure and clears partial state`, async ({ page }) => {
    await prepareApp(page)
    routeGoogleExchange(page, { status })

    await page.goto('/')
    await expect(page.locator('.google-native-button')).toBeEnabled({ timeout: 15000 })
    await seedPartialSession(page)
    await page.locator('.google-native-button').click()

    await expect(page.locator('.login-error')).toHaveText(
      'We could not verify your Google sign-in. Please try again.',
    )
    await expectFailedAttemptCleanedUp(page)
  })
}

test('backend 5xx shows a temporary server error and clears partial state', async ({ page }) => {
  await prepareApp(page)
  routeGoogleExchange(page, { status: 503 })

  await page.goto('/')
  await expect(page.locator('.google-native-button')).toBeEnabled({ timeout: 15000 })
  await seedPartialSession(page)
  await page.locator('.google-native-button').click()

  await expect(page.locator('.login-error')).toHaveText(
    'The server is temporarily unavailable. Please try again shortly.',
  )
  await expectFailedAttemptCleanedUp(page)
})

test('Google provider failure shows a safe provider message and clears partial state', async ({ page }) => {
  await prepareApp(page, { googleMode: 'provider-failure' })
  const exchanges = routeGoogleExchange(page)

  await page.goto('/')
  await expect(page.locator('.google-native-button')).toBeEnabled({ timeout: 15000 })
  await seedPartialSession(page)
  await page.locator('.google-native-button').click()

  await expect(page.locator('.login-error')).toHaveText(
    'Could not sign in with Google. Please try again.',
  )
  expect(exchanges.length).toBe(0)
  await expectFailedAttemptCleanedUp(page)
})

test('missing provider ID token fails verification safely and clears partial state', async ({ page }) => {
  await prepareApp(page, { googleMode: 'missing-id-token' })
  const exchanges = routeGoogleExchange(page)

  await page.goto('/')
  await expect(page.locator('.google-native-button')).toBeEnabled({ timeout: 15000 })
  await seedPartialSession(page)
  await page.locator('.google-native-button').click()

  await expect(page.locator('.login-error')).toHaveText(
    'We could not verify your Google sign-in. Please try again.',
  )
  expect(exchanges.length).toBe(0)
  await expectFailedAttemptCleanedUp(page)
})

test('logout after native Google login signs out of the provider and clears the session', async ({ page }) => {
  await prepareApp(page)
  routeGoogleExchange(page)

  await page.goto('/')
  await expect(page.locator('.google-native-button')).toBeEnabled({ timeout: 15000 })
  await page.locator('.google-native-button').click()
  await expect(page.locator('.auth-toolbar')).toBeVisible({ timeout: 15000 })

  await page.locator('.auth-toolbar button').last().click()
  await expect(page.locator('.login-page')).toBeVisible()

  await expect.poll(() => page.evaluate(() => ({
    providerLogouts: window.__social.logoutCalls,
    secure: localStorage.getItem('__test_secure_token'),
    plaintext: localStorage.getItem('access_token'),
    id: localStorage.getItem('currentUserId'),
  }))).toEqual({ providerLogouts: 1, secure: null, plaintext: null, id: null })
})

test('provider sign-out failure does not block local logout cleanup', async ({ page }) => {
  await prepareApp(page, { providerLogoutFails: true })
  routeGoogleExchange(page)

  await page.goto('/')
  await expect(page.locator('.google-native-button')).toBeEnabled({ timeout: 15000 })
  await page.locator('.google-native-button').click()
  await expect(page.locator('.auth-toolbar')).toContainText(user.name, { timeout: 15000 })

  await page.locator('.auth-toolbar button').last().click()

  // Local logout completes fully despite the provider rejection: logged-out
  // UI, no cleanup warning, and no auth residue in any storage tier.
  await expect(page.locator('.login-page')).toBeVisible()
  await expect(page.locator('.auth-toolbar')).toHaveCount(0)
  await expect(page.locator('.logout-warning')).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => ({
    providerLogouts: window.__social.logoutCalls,
    secure: localStorage.getItem('__test_secure_token'),
    plaintext: localStorage.getItem('access_token'),
    legacy: localStorage.getItem('authToken'),
    id: localStorage.getItem('currentUserId'),
    session: sessionStorage.getItem('access_token'),
  }))).toEqual({
    providerLogouts: 1,
    secure: null,
    plaintext: null,
    legacy: null,
    id: null,
    session: null,
  })
})

test('Google login succeeds again after logout with a fresh session', async ({ page }) => {
  await prepareApp(page)
  const exchanges = routeGoogleExchange(page)

  await page.goto('/')
  await expect(page.locator('.google-native-button')).toBeEnabled({ timeout: 15000 })
  await page.locator('.google-native-button').click()
  await expect(page.locator('.auth-toolbar')).toContainText(user.name, { timeout: 15000 })

  await page.locator('.auth-toolbar button').last().click()
  await expect(page.locator('.login-page')).toBeVisible()
  await expect.poll(() => page.evaluate(() => localStorage.getItem('__test_secure_token'))).toBe(null)

  await expect(page.locator('.google-native-button')).toBeEnabled()
  await page.locator('.google-native-button').click()
  await expect(page.locator('.auth-toolbar')).toContainText(user.name, { timeout: 15000 })

  const state = await page.evaluate(() => ({
    loginCalls: window.__social.loginCalls,
    secureToken: localStorage.getItem('__test_secure_token'),
    plaintext: localStorage.getItem('access_token'),
  }))
  // A second full pipeline run: fresh provider login, fresh backend exchange,
  // fresh securely-stored app JWT, still no web-storage JWT.
  expect(state.loginCalls).toBe(2)
  expect(exchanges.length).toBe(2)
  expect(state.secureToken).toMatch(/^eyJ/)
  expect(state.plaintext).toBeNull()
})

test('native Google login explains how manual accounts can link Google (Hebrew)', async ({ page }) => {
  await prepareApp(page)
  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'he')
  })

  page.route('**/auth/google', async (route) => {
    return route.fulfill({
      status: 409,
      contentType: 'application/json',
      body: JSON.stringify({
        error: true,
        code: 'ACCOUNT_LINK_REQUIRED',
        message: 'Account linking required',
      }),
    })
  })

  await page.goto('/')
  await expect(page.locator('.google-native-button')).toBeEnabled({ timeout: 15000 })
  await seedPartialSession(page)
  await page.locator('.google-native-button').click()

  await expect(page.locator('.login-error')).toHaveText(
    'כבר קיים חשבון עם האימייל הזה. יש להתחבר עם הסיסמה ואז לחבר את Google בהגדרות.',
  )
  await expect(page.locator('.login-info')).toHaveCount(0)
  await expectFailedAttemptCleanedUp(page)
})
