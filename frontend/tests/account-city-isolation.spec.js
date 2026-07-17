import { expect, test } from '@playwright/test'

// E08-02 follow-up fix: confirmed Android QA finding — a second account on
// the same device saw a blank Settings city (correct) but the map still
// centered on the *first* account's city (wrong). Root cause: App.jsx's
// `mapEntryIntent` was corrected reactively (a deferred effect) but
// MapPage synchronously consumed the stale prop on its own first mount
// before that correction could land. This suite proves the fix: an
// authenticated account without its own resolved city never sees the map
// (or any other account-specific route) until it explicitly picks one via
// a dedicated, minimal city-only step — never the full six-step walkthrough
// and never a native permission prompt.

const CITY_A = 'ירושלים'
const CITY_B = 'תל אביב-יפו'

const USER_A = {
  id: 'aaaaaaaa-3333-4aaa-8aaa-aaaaaaaaaaaa',
  name: 'User A',
  email: 'user-a@example.com',
  username: 'user-a',
}

const USER_B = {
  id: 'bbbbbbbb-4444-4bbb-8bbb-bbbbbbbbbbbb',
  name: 'User B',
  email: 'user-b@example.com',
  username: 'user-b',
}

function makeJwt(subject) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url')
  return `${encode({ alg: 'none' })}.${encode({ sub: subject })}.signature`
}

// Native Android Capacitor bridge mock (mirrors onboarding-android-native.spec.js's
// proven pattern) so this suite can assert zero native permission-API calls
// happen during the city-only flow, not just that no UI for them appears.
async function prepareNativeApp(page) {
  await page.addInitScript(() => {
    window.__nativeCalls = { locationCheck: 0, locationRequest: 0, pushCheck: 0, pushRequest: 0, register: 0 }
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
          if (method === 'checkPermissions') {
            window.__nativeCalls.locationCheck += 1
            return Promise.resolve({ location: 'granted', coarseLocation: 'granted' })
          }
          if (method === 'requestPermissions') {
            window.__nativeCalls.locationRequest += 1
            return Promise.resolve({ location: 'granted', coarseLocation: 'granted' })
          }
        }
        if (plugin === 'PushNotifications') {
          if (method === 'checkPermissions') {
            window.__nativeCalls.pushCheck += 1
            return Promise.resolve({ receive: 'granted' })
          }
          if (method === 'requestPermissions') {
            window.__nativeCalls.pushRequest += 1
            return Promise.resolve({ receive: 'granted' })
          }
          if (method === 'register') {
            window.__nativeCalls.register += 1
            return Promise.resolve()
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
  })

  // Deliberately only Tel Aviv-Yafo has a matching field: MapPage shows a
  // "no known fields in {city}" notice when its city-based entry intent
  // filters to zero fields (src/pages/MapPage.jsx's selectedCityUnavailable
  // path). That makes the notice a reliable, distinguishing signal for
  // *which* city an entry intent actually used — if account B's map ever
  // wrongly centers on Jerusalem again (the reported bug), Jerusalem has no
  // field here, so the notice reappears; centering correctly on Tel
  // Aviv-Yafo finds its field and the notice stays absent.
  await page.route('**/fields/**', (route) => {
    const url = new URL(route.request().url())
    const fieldB = { id: '22222222-2222-4222-8222-222222222222', name: 'Tel Aviv Field', city: CITY_B, lat: 32.08, lng: 34.78 }
    return route.fulfill({ json: url.pathname === '/fields/' ? [fieldB] : fieldB })
  })
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

async function completeFullOnboardingWithCity(page, city) {
  await page.getByRole('button', { name: 'Continue' }).click() // welcome
  const cityInput = page.locator('#onboarding-city-input')
  await cityInput.fill(city)
  await page.getByRole('option', { name: city }).click()
  await page.getByRole('button', { name: 'Continue' }).click() // city -> location
  await page.getByRole('button', { name: 'Continue' }).click() // location already granted -> notifications
  await page.getByRole('button', { name: 'Continue' }).click() // notifications already granted -> guide
  await page.getByRole('button', { name: 'Continue' }).click() // guide -> ready
  await page.getByRole('button', { name: 'Open the map' }).click()
  await expect(page.locator('.map-page')).toBeVisible()
}

async function logout(page) {
  await page.locator('.location-notice-dismiss').click({ timeout: 2000 }).catch(() => {})
  await page.getByRole('button', { name: 'Logout' }).click()
  await page.waitForSelector('.login-page', { timeout: 15000 })
}

test('second account on the same device is asked only for a city, never the previous account\'s', async ({ page }) => {
  await prepareNativeApp(page)
  await page.goto('/')

  // 1-2: Account A selects Jerusalem and completes full onboarding.
  await loginViaForm(page, USER_A)
  await completeFullOnboardingWithCity(page, CITY_A)
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('onboarding_state')).city))
    .toBe(CITY_A)

  const nativeCallsAfterA = await page.evaluate(() => ({ ...window.__nativeCalls }))

  // 3: Account B logs in on the same device.
  await logout(page)
  // 5: no permission-priming UI should exist to interact with here — assert
  // nothing to click by going straight to checking what actually renders.
  await loginViaForm(page, USER_B)

  // 4: device onboarding remains completed (never reset for B).
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('onboarding_state')).status))
    .toBe('completed')

  // 7-8: B is shown only the city-selection requirement, not the six-step
  // walkthrough — the welcome screen, and Settings, must never appear.
  await expect(page.getByRole('heading', { name: 'Welcome to Yesh Mishak' })).not.toBeVisible()
  await expect(page.getByRole('heading', { name: 'Where do you want to play?' })).toBeVisible()
  // No progress indicator: this is not step 2 of 6, it's the only step.
  await expect(page.getByRole('progressbar')).not.toBeVisible()

  // 9: the map must not exist at all yet, let alone show Jerusalem.
  await expect(page.locator('.map-page')).not.toBeVisible()

  // 6: B's own account-scoped city must not exist / must not be Jerusalem.
  const cityForB = await page.evaluate((userId) => localStorage.getItem(`starting_city:${userId}`), USER_B.id)
  expect(cityForB).toBeNull()

  // 19-20: reaching this screen must not have triggered any native
  // location or notification permission call.
  const nativeCallsAtCityStep = await page.evaluate(() => ({ ...window.__nativeCalls }))
  expect(nativeCallsAtCityStep).toEqual(nativeCallsAfterA)

  // 10-11: B selects Tel Aviv-Yafo.
  const cityInput = page.locator('#account-city-input')
  await cityInput.fill(CITY_B)
  await page.getByRole('option', { name: CITY_B }).click()
  await page.getByRole('button', { name: 'Continue' }).click()

  // Selecting a city still must not touch any native permission API.
  const nativeCallsAfterSelection = await page.evaluate(() => ({ ...window.__nativeCalls }))
  expect(nativeCallsAfterSelection).toEqual(nativeCallsAfterA)

  // 13: map now renders, using Tel Aviv-Yafo. Tel Aviv-Yafo has a matching
  // mocked field, so a correct city-based center finds it and shows no
  // "no known fields" fallback notice; if the bug reoccurred and B's map
  // silently centered on fieldless Jerusalem instead, that notice would
  // appear naming Jerusalem — this assertion would then fail.
  await expect(page.locator('.map-page')).toBeVisible()
  await expect(page.getByText(CITY_A, { exact: false })).not.toBeVisible()
  await expect(page.locator('.location-notice')).not.toBeVisible()

  // 12: Settings shows Tel Aviv-Yafo, matching what the map used.
  await page.getByRole('button', { name: 'Settings' }).click()
  await expect(page.locator('#settings-starting-city')).toHaveValue(CITY_B)

  // 14-16: log out and back into account A — Jerusalem must be restored,
  // not Tel Aviv-Yafo. Jerusalem has no mocked field, so the map's own
  // "no known fields in {city}" fallback notice is expected here — its
  // text naming Jerusalem specifically (not Tel Aviv, not blank) is the
  // positive proof this account's own city, not the other account's,
  // drove the map's entry intent.
  await page.getByRole('button', { name: 'Back' }).click()
  await logout(page)
  await loginViaForm(page, USER_A)
  await expect(page.locator('.map-page')).toBeVisible()
  await expect(page.getByText(CITY_A, { exact: false })).toBeVisible()

  await page.getByRole('button', { name: 'Settings' }).click()
  await expect(page.locator('#settings-starting-city')).toHaveValue(CITY_A)

  // 17-18: the legacy/device city was claimed by exactly one account (A,
  // the first to load post-migration) — B's own key stayed independently
  // set to what B chose, never overwritten by A's value or vice versa.
  const finalCityA = await page.evaluate((userId) => localStorage.getItem(`starting_city:${userId}`), USER_A.id)
  const finalCityB = await page.evaluate((userId) => localStorage.getItem(`starting_city:${userId}`), USER_B.id)
  expect(finalCityA).toBe(CITY_A)
  expect(finalCityB).toBe(CITY_B)
})

test('a second account never briefly renders the map before its city-only screen', async ({ page }) => {
  await prepareNativeApp(page)
  await page.goto('/')
  await loginViaForm(page, USER_A)
  await completeFullOnboardingWithCity(page, CITY_A)
  await logout(page)

  // Regression guard for the exact reported bug: the map must never become
  // visible for account B until it has an account-scoped city of its own.
  const mapBecameVisible = []
  page.locator('.map-page').first().waitFor({ state: 'visible', timeout: 500 })
    .then(() => mapBecameVisible.push(true))
    .catch(() => {})

  await loginViaForm(page, USER_B)
  await expect(page.getByRole('heading', { name: 'Where do you want to play?' })).toBeVisible()
  expect(mapBecameVisible).toEqual([])
})
