import { expect, test } from '@playwright/test'

// E08-02: onboarding exercised under a simulated Android Capacitor bridge
// (not the web fallback path). The mock mirrors the proven pattern already
// used by push-token-logout.spec.js, extended with a Geolocation plugin
// section so the location-priming step can also run natively here.

const USER_A = {
  id: 'aaaaaaaa-1111-4aaa-8aaa-aaaaaaaaaaaa',
  name: 'User A',
  email: 'user-a@example.com',
  username: 'user-a',
}

const USER_B = {
  id: 'bbbbbbbb-2222-4bbb-8bbb-bbbbbbbbbbbb',
  name: 'User B',
  email: 'user-b@example.com',
  username: 'user-b',
}

function makeJwt(subject) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url')
  return `${encode({ alg: 'none' })}.${encode({ sub: subject })}.signature`
}

async function prepareNativeApp(page, {
  pushCheckStatus = 'prompt',
  pushRequestStatus = 'granted',
  registerShouldFail = false,
} = {}) {
  await page.addInitScript(({ pushCheckStatus, pushRequestStatus, registerShouldFail }) => {
    window.__nativeCalls = { locationCheck: 0, locationRequest: 0, pushCheck: 0, pushRequest: 0, register: 0 }
    // @capacitor/core's getPlatformId() checks window.androidBridge (not a
    // method on window.Capacitor) to decide isNativePlatform() — without
    // this, every native call in this mock silently falls back to the web
    // code path instead.
    window.androidBridge = {}

    window.Capacitor = {
      PluginHeaders: [
        { name: 'App', methods: [{ name: 'addListener', rtype: 'callback' }, { name: 'removeListener', rtype: 'promise' }] },
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
        {
          name: 'Geolocation',
          methods: [
            { name: 'checkPermissions', rtype: 'promise' },
            { name: 'requestPermissions', rtype: 'promise' },
            { name: 'getCurrentPosition', rtype: 'promise' },
          ],
        },
      ],
      nativePromise(plugin, method, options) {
        if (plugin === 'App' && method === 'removeListener') return Promise.resolve()
        if (plugin === 'SecureStorage') {
          const KEY = '__test_secure_token'
          if (method === 'internalGetItem') return Promise.resolve({ data: localStorage.getItem(KEY) })
          if (method === 'internalSetItem') {
            localStorage.setItem(KEY, options.data)
            return Promise.resolve()
          }
          if (method === 'internalRemoveItem') {
            localStorage.removeItem(KEY)
            return Promise.resolve({ success: true })
          }
          return Promise.resolve({ keys: [] })
        }
        if (plugin === 'Geolocation') {
          // Always denied in this suite — these tests exercise the
          // notification/account paths, not location outcomes.
          if (method === 'checkPermissions') {
            window.__nativeCalls.locationCheck += 1
            return Promise.resolve({ location: 'denied', coarseLocation: 'denied' })
          }
          if (method === 'requestPermissions') {
            window.__nativeCalls.locationRequest += 1
            return Promise.resolve({ location: 'denied', coarseLocation: 'denied' })
          }
        }
        if (plugin === 'PushNotifications') {
          if (method === 'checkPermissions') {
            window.__nativeCalls.pushCheck += 1
            return Promise.resolve({ receive: pushCheckStatus })
          }
          if (method === 'requestPermissions') {
            window.__nativeCalls.pushRequest += 1
            return Promise.resolve({ receive: pushRequestStatus })
          }
          if (method === 'register') {
            window.__nativeCalls.register += 1
            return registerShouldFail
              ? Promise.reject(new Error('native register failed'))
              : Promise.resolve()
          }
          if (method === 'removeListener' || method === 'removeAllListeners') return Promise.resolve()
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
  }, { pushCheckStatus, pushRequestStatus, registerShouldFail })

  await page.route('**/fields/**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/games/active/**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/games/upcoming/**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/games/me', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))
  await page.route('**/notifications/unread-count', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{"count":0}' }))
  await page.route('**/notifications/preferences', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/auth/logout', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"ok"}' }))
  await page.route('**/auth/login', async (route) => {
    const body = route.request().postDataJSON() || {}
    const targetUser = body.username === USER_B.username ? USER_B : USER_A
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
}

async function chooseYeruham(page) {
  const input = page.locator('#onboarding-city-input')
  await input.fill('ירוחם')
  await page.getByRole('option', { name: 'ירוחם' }).click()
  await page.getByRole('button', { name: 'Continue' }).click()
}

test('native push registration failure after permission grant is not reported as a denial', async ({ page }) => {
  await prepareNativeApp(page, { pushCheckStatus: 'prompt', pushRequestStatus: 'granted', registerShouldFail: true })
  await page.goto('/')
  await loginViaForm(page, USER_A)
  await page.getByRole('button', { name: 'Continue' }).click()
  await chooseYeruham(page)
  // Location step: skip (this suite always mocks location as denied).
  await page.getByRole('button', { name: 'Not now' }).click()

  await page.getByRole('button', { name: 'Enable notifications' }).click()

  // The OS permission WAS granted (requestPermissions resolved 'granted');
  // only the native register() handshake failed. Onboarding must not show
  // "notifications were not allowed" for a permission the user did allow,
  // and must advance past the notifications step.
  await expect(page.getByText('Notifications were not allowed.', { exact: false })).not.toBeVisible()
  await expect(page.getByRole('heading', { name: 'How it works' })).toBeVisible()
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('onboarding_state')).notificationPermission))
    .toBe('granted')

  const registerCalls = await page.evaluate(() => window.__nativeCalls.register)
  expect(registerCalls).toBeGreaterThan(0)
})

test('native notification denial shows guidance and does not block onboarding', async ({ page }) => {
  await prepareNativeApp(page, { pushCheckStatus: 'prompt', pushRequestStatus: 'denied' })
  await page.goto('/')
  await loginViaForm(page, USER_A)
  await page.getByRole('button', { name: 'Continue' }).click()
  await chooseYeruham(page)
  await page.getByRole('button', { name: 'Not now' }).click()

  await page.getByRole('button', { name: 'Enable notifications' }).click()
  await expect(page.getByText('Notifications were not allowed.', { exact: false })).toBeVisible()

  await page.getByRole('button', { name: 'Not now' }).click()
  await expect(page.getByRole('heading', { name: 'How it works' })).toBeVisible()
})

test('second account on the same device skips onboarding and does not inherit the first account\'s city', async ({ page }) => {
  await prepareNativeApp(page, { pushCheckStatus: 'granted' })
  await page.goto('/')

  // Account A completes onboarding and picks a city.
  await loginViaForm(page, USER_A)
  await page.getByRole('button', { name: 'Continue' }).click()
  await chooseYeruham(page)
  await page.getByRole('button', { name: 'Not now' }).click() // skip location (mocked denied anyway)
  await page.getByRole('button', { name: 'Continue' }).click() // notifications already granted -> Continue
  await page.getByRole('button', { name: 'Continue' }).click() // guide
  await page.getByRole('button', { name: 'Open the map' }).click()
  await expect(page.locator('.map-page')).toBeVisible()

  const accountACityKey = await page.evaluate(() => {
    const state = JSON.parse(localStorage.getItem('onboarding_state'))
    return state.city
  })
  expect(accountACityKey).toBe('ירוחם')

  const pushChecksBeforeSwitch = await page.evaluate(() => window.__nativeCalls.pushCheck)

  // A "no known fields" notice banner (location is mocked as always-denied
  // in this suite, so the map falls back to the selected city) can overlap
  // the toolbar — dismiss it before interacting with Logout. Wait-based,
  // not a point-in-time isVisible check, since the notice can render
  // asynchronously right after the toolbar appears.
  await page.locator('.location-notice-dismiss').click({ timeout: 2000 }).catch(() => {})

  // Log out and log in as a different account on the same device.
  await page.getByRole('button', { name: 'Logout' }).click()
  await page.waitForSelector('.login-page', { timeout: 15000 })
  await loginViaForm(page, USER_B)

  // Onboarding is device-scoped and already completed — account B must not
  // see the six-step walkthrough again, and therefore gets no redundant
  // native permission prompt either. B has no city of its own yet, though,
  // so it lands on the dedicated city-only requiredStep, never the map
  // (E08-02 follow-up fix — the map must never show account A's city here).
  await expect(page.locator('.map-page')).not.toBeVisible()
  await expect(page.getByRole('heading', { name: 'Where do you want to play?' })).toBeVisible({ timeout: 15000 })

  const userBOwnCity = await page.evaluate((userId) => localStorage.getItem(`starting_city:${userId}`), USER_B.id)
  expect(userBOwnCity).toBeNull()

  const deviceCityAfterSwitch = await page.evaluate(() => JSON.parse(localStorage.getItem('onboarding_state')).city)
  expect(deviceCityAfterSwitch).not.toBe('ירוחם')

  const pushChecksAtCityStep = await page.evaluate(() => window.__nativeCalls.pushCheck)
  expect(pushChecksAtCityStep).toBe(pushChecksBeforeSwitch)

  // B picks its own city — still no native permission call, and only then
  // does the map appear.
  const cityInput = page.locator('#account-city-input')
  await cityInput.fill('תל אביב-יפו')
  await page.getByRole('option', { name: 'תל אביב-יפו' }).click()
  await page.getByRole('button', { name: 'Continue' }).click()

  await expect(page.locator('.map-page')).toBeVisible()
  const pushChecksAfterSwitch = await page.evaluate(() => window.__nativeCalls.pushCheck)
  expect(pushChecksAfterSwitch).toBe(pushChecksBeforeSwitch)

  const userBCityAfterSelection = await page.evaluate((userId) => localStorage.getItem(`starting_city:${userId}`), USER_B.id)
  expect(userBCityAfterSelection).toBe('תל אביב-יפו')
})

test('session expiry (401) mid-onboarding returns to login, and re-login resumes at the saved step', async ({ page }) => {
  await prepareNativeApp(page, { pushCheckStatus: 'prompt', pushRequestStatus: 'denied' })
  await page.goto('/')
  await loginViaForm(page, USER_A)

  // Progress to the notifications step (step 4 of 6).
  await page.getByRole('button', { name: 'Continue' }).click()
  await chooseYeruham(page)
  await page.getByRole('button', { name: 'Not now' }).click()
  await expect(page.getByRole('heading', { name: 'Stay updated' })).toBeVisible()

  // The token expires server-side; the next app-resume validation
  // (appStateChange -> validateStoredSession -> GET /games/me) gets a 401.
  await page.route('**/games/me', (route) =>
    route.fulfill({ status: 401, contentType: 'application/json', body: '{}' }))
  await page.evaluate(() => window.__appStateChange({ isActive: true }))

  // Fail-closed: back at login, while storage still holds the real progress.
  await expect(page.locator('.login-page')).toBeVisible()
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('onboarding_state')).currentStep))
    .toBe('notifications')

  // The backend accepts the credentials again; the same user logs back in.
  await page.route('**/games/me', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }))
  await loginViaForm(page, USER_A)

  // E08-03: the wizard must resume exactly where the user left off, not
  // restart from the stale welcome-step snapshot App.jsx captured at mount.
  await expect(page.getByRole('heading', { name: 'Stay updated' })).toBeVisible()
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '4')
})
