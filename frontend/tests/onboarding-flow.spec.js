import { expect, test } from '@playwright/test'

const USER = { id: 'onboarding-user', name: 'Onboarding User', email: 'onboarding@example.com' }

async function seedAuthenticatedUser(page, language = 'en') {
  await page.addInitScript(({ user, languageCode }) => {
    const payload = btoa(JSON.stringify({ sub: user.id })).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_')
    localStorage.setItem('access_token', `e30.${payload}.signature`)
    localStorage.setItem('currentUserId', user.id)
    localStorage.setItem('currentUserName', user.name)
    localStorage.setItem('currentUserEmail', user.email)
    localStorage.setItem('app_language', languageCode)
    localStorage.setItem('language_selected', 'true')
    if (!localStorage.getItem('__onboarding_test_seeded')) {
      localStorage.setItem('__onboarding_test_seeded', 'true')
      localStorage.removeItem('onboarding_done')
      localStorage.removeItem('onboarding_state')
      localStorage.removeItem('userCity')
    }
  }, { user: USER, languageCode: language })
}

async function mockApplicationApis(page) {
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/fields\/.*/, (route) => {
    const field = { id: '11111111-1111-4111-8111-111111111111', name: 'Linked Field', city: 'ירוחם', lat: 30.988, lng: 34.932 }
    return route.fulfill({ json: new URL(route.request().url()).pathname === '/fields/' ? [field] : field })
  })
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/games\/.*/, (route) => route.fulfill({ json: [] }))
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/notifications.*/, (route) => route.fulfill({ json: [] }))
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/analytics\/.*/, (route) => route.fulfill({ status: 204 }))
}

async function chooseYeruham(page) {
  const input = page.locator('#onboarding-city-input')
  await input.fill('ירוחם')
  await page.getByRole('option', { name: 'ירוחם' }).click()
  await page.getByRole('button', { name: /continue|המשך/i }).click()
}

async function advanceToReadyBySkippingPermissions(page) {
  await page.getByRole('button', { name: /not now|לא עכשיו/i }).click()
  await page.getByRole('button', { name: /not now|לא עכשיו/i }).click()
  await page.getByRole('button', { name: /continue|המשך/i }).click()
}

test('brand-new English user completes all six steps and enters near the selected city', async ({ page }) => {
  await seedAuthenticatedUser(page, 'en')
  await mockApplicationApis(page)
  await page.goto('/')
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuemax', '6')
  await page.getByRole('button', { name: 'Continue' }).click()
  await chooseYeruham(page)
  await advanceToReadyBySkippingPermissions(page)
  await page.getByRole('button', { name: 'Open the map' }).click()

  await expect(page.locator('.map-page')).toHaveAttribute('data-initial-entry-source', 'city')
  await expect.poll(() => page.evaluate(() => {
    const value = JSON.parse(localStorage.getItem('onboarding_state'))
    return {
      status: value.status,
      location: value.locationPermission,
      notifications: value.notificationPermission,
      hasCoordinates: 'latitude' in value || 'longitude' in value,
    }
  })).toEqual({ status: 'completed', location: 'skipped', notifications: 'skipped', hasCoordinates: false })
})

test('already granted onboarding location is not prompted again and opens around the user', async ({ browser }) => {
  const context = await browser.newContext({ permissions: ['geolocation'], geolocation: { latitude: 32.0853, longitude: 34.7818 } })
  const page = await context.newPage()
  await seedAuthenticatedUser(page, 'en')
  await mockApplicationApis(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Continue' }).click()
  await chooseYeruham(page)
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByRole('button', { name: 'Not now' }).click()
  await page.getByRole('button', { name: 'Continue' }).click()
  await page.getByRole('button', { name: 'Open the map' }).click()

  await expect(page.locator('.map-page')).toHaveAttribute('data-initial-entry-source', 'location')
  await expect(page.locator('.user-location-marker')).toBeVisible()
  const persisted = await page.evaluate(() => localStorage.getItem('onboarding_state'))
  expect(persisted).not.toContain('32.0853')
  expect(persisted).not.toContain('34.7818')
  await context.close()
})

test('refresh resumes a skipped location step at notifications', async ({ page }) => {
  await seedAuthenticatedUser(page, 'he')
  await mockApplicationApis(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'המשך' }).click()
  await chooseYeruham(page)
  await page.getByRole('button', { name: 'לא עכשיו' }).click()
  await page.reload()

  await expect(page.getByRole('heading', { name: 'הישארו מעודכנים' })).toBeVisible()
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '4')
})

test('login state alone never requests browser notification permission', async ({ page }) => {
  await page.addInitScript(() => {
    window.__notificationRequests = 0
    Object.defineProperty(window, 'Notification', {
      configurable: true,
      value: { permission: 'default', requestPermission: () => { window.__notificationRequests += 1; return Promise.resolve('granted') } },
    })
  })
  await seedAuthenticatedUser(page, 'en')
  await mockApplicationApis(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Welcome to Yesh Mishak' })).toBeVisible()
  await expect.poll(() => page.evaluate(() => window.__notificationRequests)).toBe(0)
})

test('location permission denied once shows non-blocking guidance and stays on the same step', async ({ page }) => {
  await seedAuthenticatedUser(page, 'en')
  await mockApplicationApis(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Continue' }).click()
  await chooseYeruham(page)

  // No context permission was granted, so the browser auto-denies —
  // the same signal a real user tapping "Block" produces.
  await page.getByRole('button', { name: 'Allow location' }).click()

  await expect(page.getByText('Location was not allowed. You can continue and enable it later from the map.')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Find games near you' })).toBeVisible()
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('onboarding_state')).locationPermission))
    .toBe('denied')

  // Denial must not block progress — skipping still works.
  await page.getByRole('button', { name: 'Not now' }).click()
  await expect(page.getByRole('heading', { name: 'Stay updated' })).toBeVisible()
})

test('repeated location denial escalates to settings guidance instead of the generic message', async ({ page }) => {
  await seedAuthenticatedUser(page, 'en')
  await mockApplicationApis(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Continue' }).click()
  await chooseYeruham(page)

  await page.getByRole('button', { name: 'Allow location' }).click()
  await expect(page.getByText('Location was not allowed. You can continue and enable it later from the map.')).toBeVisible()

  await page.getByRole('button', { name: 'Allow location' }).click()
  await expect(page.getByText(/Location was blocked after a few attempts/)).toBeVisible()
})

test('rapid double-tap on the location action fires only one permission request', async ({ page }) => {
  await seedAuthenticatedUser(page, 'en')
  await mockApplicationApis(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Continue' }).click()
  await chooseYeruham(page)

  // Two synchronous click events dispatched in the same task — before React
  // can re-render/disable the button between them — is the reliable way to
  // exercise the in-handler re-entrancy guard rather than the disabled-DOM
  // guard alone.
  await page.evaluate(() => {
    const button = [...document.querySelectorAll('button')]
      .find((candidate) => candidate.textContent.includes('Allow location'))
    button.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    button.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  })

  await expect(page.getByText('Location was not allowed. You can continue and enable it later from the map.')).toBeVisible()
  await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem('onboarding_state')).locationPermission))
    .toBe('denied')
  // A second, uncoalesced request would have advanced the repeat-denial
  // counter and shown the settings-escalated message instead of the plain
  // first-denial one — its absence proves only one request actually fired.
  await expect(page.getByText(/blocked after a few attempts/)).not.toBeVisible()
})

test('pending field deep link overrides onboarding location and city handoff', async ({ page }) => {
  await seedAuthenticatedUser(page, 'en')
  await page.addInitScript(() => {
    sessionStorage.setItem('pending_deep_link', JSON.stringify({
      routeType: 'field',
      resourceId: '11111111-1111-4111-8111-111111111111',
      action: '',
    }))
  })
  await mockApplicationApis(page)
  await page.goto('/')
  await page.getByRole('button', { name: 'Continue' }).click()
  await chooseYeruham(page)
  await advanceToReadyBySkippingPermissions(page)
  await page.getByRole('button', { name: 'Open the map' }).click()

  await expect(page.getByText('Linked Field').first()).toBeVisible()
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('pending_deep_link'))).toBe(null)
})
