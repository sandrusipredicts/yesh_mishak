import { expect, test } from '@playwright/test'

const user = {
  id: '5f0a09a4-52c5-4c3f-9a2e-8a52c8d6b7aa',
  name: 'Failure Tester',
  email: 'failure@example.com',
}

function makeJwt(subject = user.id) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url')
  return `${encode({ alg: 'none' })}.${encode({ sub: subject })}.signature`
}

// Native mock with failure knobs. Secure storage is simulated in the
// non-auth localStorage key __test_secure_token (survives reload = relaunch).
// Knobs: omitSecurePlugin, getMode ('ok' | 'reject' | 'hang'),
// setFailures (times internalSetItem rejects before succeeding).
async function prepareApp(page, options = {}) {
  const {
    omitSecurePlugin = false,
    getMode = 'ok',
    setFailures = 0,
    seedPlaintextToken = null,
    seedMetadata = false,
  } = options

  await page.addInitScript(({ cfg, storedUser }) => {
    const SECURE_BACKING_KEY = '__test_secure_token'

    window.androidBridge = {}
    window.__setAttempts = 0
    window.__removeAttempts = 0
    window.__setFailuresRemaining = cfg.setFailures

    const pluginHeaders = [{
      name: 'App',
      methods: [
        { name: 'addListener', rtype: 'callback' },
        { name: 'removeListener', rtype: 'promise' },
      ],
    }]

    if (!cfg.omitSecurePlugin) {
      pluginHeaders.push({
        name: 'SecureStorage',
        methods: [
          { name: 'internalGetItem', rtype: 'promise' },
          { name: 'internalSetItem', rtype: 'promise' },
          { name: 'internalRemoveItem', rtype: 'promise' },
          { name: 'clearItemsWithPrefix', rtype: 'promise' },
          { name: 'getPrefixedKeys', rtype: 'promise' },
          { name: 'setSynchronizeKeychain', rtype: 'promise' },
        ],
      })
    }

    window.Capacitor = {
      PluginHeaders: pluginHeaders,
      nativePromise(plugin, method, options) {
        if (plugin === 'App' && method === 'removeListener') {
          return Promise.resolve()
        }
        if (method === 'internalGetItem') {
          if (cfg.getMode === 'reject') {
            return Promise.reject(new Error('simulated read failure'))
          }
          if (cfg.getMode === 'hang') {
            return new Promise((resolve) => {
              window.__resolveHungRead = (value) => resolve({ data: value })
            })
          }
          return Promise.resolve({ data: localStorage.getItem(SECURE_BACKING_KEY) })
        }
        if (method === 'internalSetItem') {
          window.__setAttempts += 1
          if (window.__setFailuresRemaining > 0) {
            window.__setFailuresRemaining -= 1
            return Promise.reject(new Error('simulated write failure'))
          }
          localStorage.setItem(SECURE_BACKING_KEY, options.data)
          return Promise.resolve()
        }
        if (method === 'internalRemoveItem') {
          window.__removeAttempts += 1
          localStorage.removeItem(SECURE_BACKING_KEY)
          return Promise.resolve({ success: true })
        }
        return Promise.resolve({ keys: [] })
      },
      nativeCallback(plugin, method, options, callback) {
        if (plugin === 'App' && method === 'addListener' && options.eventName === 'appStateChange') {
          window.__appStateChange = callback
          return 'issue-233-listener'
        }
        return ''
      },
    }

    localStorage.setItem('language_selected', 'true')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('userCity', 'ירושלים') // E08-02 follow-up fix: account needs a resolved city to reach the map

    if (cfg.seedPlaintextToken) {
      localStorage.setItem('access_token', cfg.seedPlaintextToken)
    }
    if (cfg.seedMetadata) {
      localStorage.setItem('currentUserId', storedUser.id)
      localStorage.setItem('currentUserName', storedUser.name)
      localStorage.setItem('currentUserEmail', storedUser.email)
    }
  }, { cfg: { omitSecurePlugin, getMode, setFailures, seedPlaintextToken, seedMetadata }, storedUser: user })

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
  await page.route('**/auth/logout', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"ok"}' }))
  await page.route('**/auth/login', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ access_token: makeJwt(), user }),
    }))
}

async function loginViaForm(page) {
  await page.waitForSelector('.login-page', { timeout: 15000 })
  const panel = page.locator('#login-tabpanel')
  await panel.locator('[name="username"]').fill('failure-tester')
  await panel.locator('[name="password"]').fill('irrelevant-password')
  await panel.locator('button[type="submit"]').click()
}

async function jwtLeakScan(page) {
  return page.evaluate(() => {
    const scan = (store) => {
      const hits = []
      for (let i = 0; i < store.length; i += 1) {
        const key = store.key(i)
        if (key !== '__test_secure_token' && /^eyJ[\w-]+\.[\w-]+\./.test(store.getItem(key) || '')) {
          hits.push(key)
        }
      }
      return hits
    }
    return { localStorage: scan(localStorage), sessionStorage: scan(sessionStorage) }
  })
}

test('secure storage unavailable at startup fails closed to login UI', async ({ page }) => {
  await prepareApp(page, { omitSecurePlugin: true, seedMetadata: true })
  await page.goto('/')

  await expect(page.locator('.login-page')).toBeVisible({ timeout: 15000 })
  await expect(page.getByTestId('auth-checking')).toHaveCount(0)
  await expect(page.locator('.auth-toolbar')).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => ({
    id: localStorage.getItem('currentUserId'),
    token: localStorage.getItem('access_token'),
  }))).toEqual({ id: null, token: null })
  expect(await jwtLeakScan(page)).toEqual({ localStorage: [], sessionStorage: [] })
})

test('secure read failure fails closed and attempts cleanup', async ({ page }) => {
  await prepareApp(page, { getMode: 'reject', seedMetadata: true })
  await page.goto('/')

  await expect(page.locator('.login-page')).toBeVisible({ timeout: 15000 })
  await expect(page.locator('.auth-toolbar')).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => ({
    removeAttempts: window.__removeAttempts,
    id: localStorage.getItem('currentUserId'),
  }))).toEqual({ removeAttempts: 1, id: null })
})

test('hanging secure read times out to login UI and a late token cannot authenticate', async ({ page }) => {
  await prepareApp(page, { getMode: 'hang', seedMetadata: true })
  await page.goto('/')

  // While the read hangs the app shows the checking state, not a crash.
  await expect(page.getByTestId('auth-checking')).toBeVisible()

  // After the 5s startup deadline the app must land on login.
  await expect(page.locator('.login-page')).toBeVisible({ timeout: 10000 })
  await expect(page.getByTestId('auth-checking')).toHaveCount(0)

  // The hung read resolving late with a valid token must not authenticate.
  await page.evaluate((token) => window.__resolveHungRead(token), makeJwt())
  await page.waitForTimeout(1500)
  await expect(page.locator('.login-page')).toBeVisible()
  await expect(page.locator('.auth-toolbar')).toHaveCount(0)
  expect(await jwtLeakScan(page)).toEqual({ localStorage: [], sessionStorage: [] })
})

test('token write fails once then retry succeeds: login persisted, no warning', async ({ page }) => {
  await prepareApp(page, { setFailures: 1 })
  await page.goto('/')
  await loginViaForm(page)

  await expect(page.locator('.auth-toolbar')).toBeVisible({ timeout: 15000 })
  await expect(page.locator('.persistence-warning')).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => ({
    attempts: window.__setAttempts,
    persisted: !!localStorage.getItem('__test_secure_token'),
    plaintext: localStorage.getItem('access_token'),
  }))).toEqual({ attempts: 2, persisted: true, plaintext: null })
})

test('token write fails twice: in-memory session, warning shown, no insecure fallback', async ({ page }) => {
  await prepareApp(page, { setFailures: 99 })
  await page.goto('/')
  await loginViaForm(page)

  // Login itself succeeded — the session is usable now.
  await expect(page.locator('.auth-toolbar')).toBeVisible({ timeout: 15000 })

  // Non-blocking persistence warning is shown; no JWT reached web storage.
  await expect(page.locator('.persistence-warning')).toBeVisible()
  await expect.poll(() => page.evaluate(() => ({
    attempts: window.__setAttempts,
    secure: localStorage.getItem('__test_secure_token'),
    plaintext: localStorage.getItem('access_token'),
  }))).toEqual({ attempts: 2, secure: null, plaintext: null })
  expect(await jwtLeakScan(page)).toEqual({ localStorage: [], sessionStorage: [] })

  // In-memory only: a relaunch starts logged out.
  await page.reload()
  await expect(page.locator('.login-page')).toBeVisible({ timeout: 15000 })
  await expect(page.locator('.auth-toolbar')).toHaveCount(0)
})

test('logout clears the persistence warning', async ({ page }) => {
  await prepareApp(page, { setFailures: 99 })
  await page.goto('/')
  await loginViaForm(page)
  await expect(page.locator('.persistence-warning')).toBeVisible()

  await page.locator('.location-notice-dismiss').click({ timeout: 2000 }).catch(() => {})
  await page.locator('.auth-toolbar button').last().click()
  await expect(page.locator('.login-page')).toBeVisible()
  await expect(page.locator('.persistence-warning')).toHaveCount(0)
})

test('migration failure never leaves a plaintext token in localStorage', async ({ page }) => {
  await prepareApp(page, { setFailures: 99, seedPlaintextToken: makeJwt(), seedMetadata: true })
  await page.goto('/')

  await expect(page.locator('.login-page')).toBeVisible({ timeout: 15000 })
  await expect(page.locator('.auth-toolbar')).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => ({
    plaintext: localStorage.getItem('access_token'),
    secure: localStorage.getItem('__test_secure_token'),
    id: localStorage.getItem('currentUserId'),
  }))).toEqual({ plaintext: null, secure: null, id: null })
  expect(await jwtLeakScan(page)).toEqual({ localStorage: [], sessionStorage: [] })
})
