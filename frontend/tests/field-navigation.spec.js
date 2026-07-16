import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

const user = {
  id: 'regular-user-1',
  email: 'user@example.com',
  name: 'Regular User',
  role: 'user',
}

const navigableField = {
  id: 'field-1',
  name: 'Central Court',
  latitude: 31.225172,
  longitude: 34.777498,
  sport_type: 'football',
  surface_type: 'synthetic',
  has_nets: true,
  has_water_cooler: false,
  opening_hours: '19:00',
  notes: '',
  status: 'approved',
}

const cachedNavigableField = {
  ...navigableField,
  name: 'Cached Court',
}

function fulfillJson(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function seedAuthenticatedUser(page) {
  const token = makeJwtWithSubject(user.id)

  await page.addInitScript((storedUser) => {
    localStorage.setItem('access_token', storedUser.token)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  }, { ...user, token })
}

function encodeBase64Url(value) {
  return Buffer.from(value).toString('base64url')
}

function makeJwtWithSubject(userId) {
  return [
    encodeBase64Url(JSON.stringify({ alg: 'none', typ: 'JWT' })),
    encodeBase64Url(JSON.stringify({ sub: userId })),
    'signature',
  ].join('.')
}

async function mockGeolocation(page) {
  await page.addInitScript(({ latitude, longitude }) => {
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition(success) {
          success({ coords: { latitude, longitude } })
        },
      },
    })
  }, navigableField)
}

async function trackOpenedUrls(page) {
  await page.addInitScript(() => {
    window.__openedUrls = []
    window.open = (url, target, features) => {
      window.__openedUrls.push({ url, target, features })
      return null
    }
  })
}

async function makeWindowOpenFail(page) {
  await page.addInitScript(() => {
    window.open = () => {
      throw new Error('Popup launch failed')
    }
  })
}

async function mockNativeWazeLauncher(
  page,
  { canOpenNative = true, nativeCompleted = true, httpsCompleted = true } = {},
) {
  await page.addInitScript((config) => {
    window.androidBridge = {}
    window.__appLauncherCalls = []
    window.Capacitor = {
      PluginHeaders: [
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
          name: 'AppLauncher',
          methods: [
            { name: 'canOpenUrl', rtype: 'promise' },
            { name: 'openUrl', rtype: 'promise' },
          ],
        },
        {
          name: 'App',
          methods: [
            { name: 'addListener', rtype: 'callback' },
            { name: 'removeListener', rtype: 'promise' },
          ],
        },
      ],
      nativePromise(plugin, method, options) {
        if (plugin === 'SecureStorage') {
          if (method === 'internalGetItem') {
            return Promise.resolve({ data: localStorage.getItem('__test_secure_token') })
          }
          if (method === 'internalSetItem') {
            localStorage.setItem('__test_secure_token', options.data)
            return Promise.resolve()
          }
          if (method === 'internalRemoveItem') {
            localStorage.removeItem('__test_secure_token')
            return Promise.resolve({ success: true })
          }
          return Promise.resolve({ keys: [] })
        }
        if (plugin === 'AppLauncher') {
          window.__appLauncherCalls.push({ method, url: options.url })
          if (method === 'canOpenUrl') {
            return Promise.resolve({ value: config.canOpenNative })
          }
          if (options.url.startsWith('waze://')) {
            return Promise.resolve({ completed: config.nativeCompleted })
          }
          return Promise.resolve({ completed: config.httpsCompleted })
        }
        return Promise.resolve()
      },
      nativeCallback(plugin, method, options) {
        if (plugin === 'App' && method === 'addListener') {
          return `field-navigation-${options.eventName}`
        }
        return ''
      },
    }
  }, { canOpenNative, nativeCompleted, httpsCompleted })
}

async function mockMapPageRequests(page, fields) {
  await page.route(/\/fields\/?(\?.*)?$/, (route) => fulfillJson(route, fields))
  await page.route(/\/notifications(\/.*)?(\?.*)?$/, (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/unread-count')) {
      return fulfillJson(route, { unread_count: 0 })
    }
    return fulfillJson(route, [])
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
}

async function openFieldDetails(page) {
  await page.goto('/')
  await page.locator('.field-marker-icon').first().evaluate((marker) => marker.click())
  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: navigableField.name }),
  ).toBeVisible()
}

test.beforeEach(async ({ page }) => {
  await seedAuthenticatedUser(page)
  await mockGeolocation(page)
  await trackOpenedUrls(page)
})

test('opens Waze and Google Maps navigation links for a field', async ({ page }) => {
  await mockMapPageRequests(page, [navigableField])
  await openFieldDetails(page)

  await page.getByRole('button', { name: 'Navigate to field' }).click()
  await expect(page.getByRole('dialog', { name: 'Open navigation' })).toBeVisible()

  await page.getByRole('button', { name: 'Waze' }).click()
  await expect(page.getByRole('dialog', { name: 'Open navigation' })).toBeHidden()

  await page.getByRole('button', { name: 'Navigate to field' }).click()
  await page.getByRole('button', { name: 'Google Maps' }).click()

  await expect
    .poll(() => page.evaluate(() => window.__openedUrls))
    .toEqual([
      {
        url: 'https://waze.com/ul?ll=31.225172,34.777498&navigate=yes',
        target: '_blank',
        features: 'noopener,noreferrer',
      },
      {
        url: 'https://www.google.com/maps/dir/?api=1&destination=31.225172%2C34.777498',
        target: '_blank',
        features: 'noopener,noreferrer',
      },
    ])
})

test('keeps the navigation flow open when Google Maps cannot be launched', async ({ page }) => {
  await makeWindowOpenFail(page)
  await mockMapPageRequests(page, [navigableField])
  await openFieldDetails(page)

  await page.getByRole('button', { name: 'Navigate to field' }).click()
  await page.getByRole('button', { name: 'Google Maps' }).click()

  await expect(page.getByRole('dialog', { name: 'Open navigation' })).toBeVisible()
  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: navigableField.name }),
  ).toBeAttached()
})

test('rejects invalid Google Maps coordinates without attempting a launch', async ({ page }) => {
  await page.goto('/')

  const result = await page.evaluate(async () => {
    const { launchGoogleMapsNavigation } = await import('/src/api/googleMapsNavigation.js')
    return launchGoogleMapsNavigation(null, 34.777498)
  })

  expect(result).toEqual({ opened: false, reason: 'invalid_coordinates' })
  await expect.poll(() => page.evaluate(() => window.__openedUrls)).toEqual([])
})

test('launches Waze with the native scheme when it is available', async ({ page }) => {
  await mockNativeWazeLauncher(page)
  await page.goto('/')
  const result = await page.evaluate(async ({ latitude, longitude }) => {
    const { launchWazeNavigation } = await import('/src/api/wazeNavigation.js')
    return launchWazeNavigation(latitude, longitude)
  }, navigableField)

  expect(result).toEqual({ opened: true, mechanism: 'native' })
  await expect
    .poll(() => page.evaluate(() => window.__appLauncherCalls))
    .toEqual([
      { method: 'canOpenUrl', url: 'waze://' },
      {
        method: 'openUrl',
        url: 'waze://?ll=31.225172,34.777498&navigate=yes',
      },
    ])
  await expect.poll(() => page.evaluate(() => window.__openedUrls)).toEqual([])
})

test('falls back to the Waze HTTPS URL when the native app is unavailable', async ({ page }) => {
  await mockNativeWazeLauncher(page, { canOpenNative: false })
  await page.goto('/')
  const result = await page.evaluate(async ({ latitude, longitude }) => {
    const { launchWazeNavigation } = await import('/src/api/wazeNavigation.js')
    return launchWazeNavigation(latitude, longitude)
  }, navigableField)

  expect(result).toEqual({ opened: true, mechanism: 'https' })
  await expect
    .poll(() => page.evaluate(() => window.__appLauncherCalls))
    .toEqual([
      { method: 'canOpenUrl', url: 'waze://' },
      {
        method: 'openUrl',
        url: 'https://waze.com/ul?ll=31.225172,34.777498&navigate=yes',
      },
    ])
})

test('keeps the navigation flow open when Waze cannot be launched', async ({ page }) => {
  await mockNativeWazeLauncher(page, { nativeCompleted: false, httpsCompleted: false })
  await page.goto('/')
  const result = await page.evaluate(async ({ latitude, longitude }) => {
    const { launchWazeNavigation } = await import('/src/api/wazeNavigation.js')
    return launchWazeNavigation(latitude, longitude)
  }, navigableField)

  expect(result).toEqual({ opened: false, reason: 'launch_failed' })
  await expect
    .poll(() => page.evaluate(() => window.__appLauncherCalls))
    .toEqual([
      { method: 'canOpenUrl', url: 'waze://' },
      {
        method: 'openUrl',
        url: 'waze://?ll=31.225172,34.777498&navigate=yes',
      },
      {
        method: 'openUrl',
        url: 'https://waze.com/ul?ll=31.225172,34.777498&navigate=yes',
      },
    ])
})

test('rejects invalid Waze coordinates without attempting a launch', async ({ page }) => {
  await mockNativeWazeLauncher(page)
  await page.goto('/')

  const result = await page.evaluate(async () => {
    const { launchWazeNavigation } = await import('/src/api/wazeNavigation.js')
    return launchWazeNavigation(null, 34.777498)
  })

  expect(result).toEqual({ opened: false, reason: 'invalid_coordinates' })
  await expect.poll(() => page.evaluate(() => window.__appLauncherCalls)).toEqual([])
  await expect.poll(() => page.evaluate(() => window.__openedUrls)).toEqual([])
})

test('closes the navigation dialog without opening a provider', async ({ page }) => {
  await mockMapPageRequests(page, [navigableField])
  await openFieldDetails(page)

  await page.getByRole('button', { name: 'Navigate to field' }).click()
  await page.getByRole('button', { name: 'Cancel' }).click()

  await expect(page.getByRole('dialog', { name: 'Open navigation' })).toBeHidden()
  await expect.poll(() => page.evaluate(() => window.__openedUrls)).toEqual([])
})

test('submits a field report from field details', async ({ page }) => {
  await mockMapPageRequests(page, [navigableField])
  let reportPayload = null

  await page.route(/\/field-reports\/?$/, async (route) => {
    reportPayload = route.request().postDataJSON()
    return fulfillJson(route, {
      id: 'report-1',
      ...reportPayload,
      user_id: user.id,
      status: 'open',
      reviewed_at: null,
      reviewed_by: null,
    })
  })

  await openFieldDetails(page)
  await page.getByRole('button', { name: 'Report', exact: true }).click()

  const dialog = page.getByRole('dialog', { name: 'Report field' })
  await expect(dialog).toBeVisible()

  await dialog.getByLabel('Report type').selectOption('field_closed')
  await dialog.getByLabel('Description').fill('Gate is locked.')
  await dialog.getByRole('button', { name: 'Submit' }).click()

  await expect(dialog.getByText('Report sent successfully.')).toBeVisible()
  await expect
    .poll(() => reportPayload)
    .toEqual({
      field_id: navigableField.id,
      category: 'field_closed',
      description: 'Gate is locked.',
    })
  await expect(dialog).toBeHidden()
})

test('cancels the field report modal without sending a report', async ({ page }) => {
  await mockMapPageRequests(page, [navigableField])
  let reportRequestCount = 0

  await page.route(/\/field-reports\/?$/, async (route) => {
    reportRequestCount += 1
    return fulfillJson(route, {})
  })

  await openFieldDetails(page)
  await page.getByRole('button', { name: 'Report', exact: true }).click()

  const dialog = page.getByRole('dialog', { name: 'Report field' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: 'Cancel' }).click()

  await expect(dialog).toBeHidden()
  await expect.poll(() => reportRequestCount).toBe(0)
})

test('hides navigation for missing or invalid coordinates', async ({ page }) => {
  await mockMapPageRequests(page, [
    { ...navigableField, id: 'field-missing', latitude: null, longitude: null },
    { ...navigableField, id: 'field-invalid', latitude: 190, longitude: 34.777498 },
  ])

  await page.goto('/')

  await expect(page.locator('.field-marker-icon')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Navigate to field' })).toHaveCount(0)
})

test('uses stadium markers for active and inactive fields', async ({ page }) => {
  await mockMapPageRequests(page, [
    {
      ...navigableField,
      id: 'field-inactive',
      active_game: null,
    },
    {
      ...navigableField,
      id: 'field-active',
      latitude: 31.226,
      active_game: {
        id: 'game-1',
        status: 'open',
        players_present: 4,
        max_players: 10,
      },
    },
  ])

  await page.goto('/')

  await expect(page.locator('.field-marker-icon')).toHaveCount(2)
  await expect(page.locator('.field-marker--inactive img')).toHaveAttribute(
    'src',
    /stadium-inactive\.png$/,
  )
  await expect(page.locator('.field-marker--active img')).toHaveAttribute(
    'src',
    /stadium-active\.png$/,
  )
  await expect
    .poll(() =>
      page.locator('.field-marker--active .field-marker-status').evaluate((element) =>
        window.getComputedStyle(element).animationName,
      ),
    )
    .toBe('field-marker-active-pulse')
  await expect
    .poll(() =>
      page.locator('.field-marker--inactive .field-marker-status').evaluate((element) =>
        window.getComputedStyle(element).animationName,
      ),
    )
    .toBe('none')

  await page.getByRole('button', { name: 'Zoom in' }).click()
  await expect(page.locator('.field-marker--active')).toBeVisible()
  await page.getByRole('button', { name: 'Zoom out' }).click()
  await page.getByRole('button', { name: 'Zoom out' }).click()
  await expect(page.locator('.field-marker--inactive')).toBeVisible()
})

test('shows cached fields immediately while refreshing fields in the background', async ({
  page,
}) => {
  await page.addInitScript((field) => {
    localStorage.setItem('cached_fields', JSON.stringify([field]))
    localStorage.setItem('cached_fields_timestamp', '2026-06-19T08:00:00.000Z')
  }, cachedNavigableField)

  await page.route(/\/fields\/?(\?.*)?$/, async (route) => {
    await new Promise((resolve) => {
      setTimeout(resolve, 250)
    })

    return fulfillJson(route, [navigableField])
  })
  await page.route(/\/notifications(\/.*)?(\?.*)?$/, (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/unread-count')) {
      return fulfillJson(route, { unread_count: 0 })
    }
    return fulfillJson(route, [])
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())

  await page.goto('/')

  await expect(page.locator('.field-marker-icon')).toHaveCount(1)
  // Like openFieldDetails: the marker sits far outside the viewport at the
  // default map center/zoom, so viewport hit-testing can never reach it.
  await page.locator('.field-marker-icon').first().evaluate((marker) => marker.click())
  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: cachedNavigableField.name }),
  ).toBeVisible()

  await expect
    .poll(() =>
      page.evaluate(() => JSON.parse(localStorage.getItem('cached_fields') ?? '[]')[0]?.name),
    )
    .toBe(navigableField.name)
})

test('keeps navigation dialog usable on a mobile viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockMapPageRequests(page, [navigableField])
  await openFieldDetails(page)

  await page.getByRole('button', { name: 'Navigate to field' }).click()

  const dialog = page.getByRole('dialog', { name: 'Open navigation' })
  await expect(dialog).toBeVisible()
  await expect(dialog).toBeInViewport()
  await expect(page.getByRole('button', { name: 'Waze' })).toBeInViewport()
  await expect(page.getByRole('button', { name: 'Google Maps' })).toBeInViewport()
})
