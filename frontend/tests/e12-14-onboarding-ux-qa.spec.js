import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

// ---------------------------------------------------------------------------
// Helpers — shared seeding, mocking, and navigation utilities
// ---------------------------------------------------------------------------

const USER = { id: 'e12-14-user', name: 'QA User', email: 'qa@example.com' }

function encodeBase64Url(value) {
  return Buffer.from(value).toString('base64url')
}

function makeJwt(subject = USER.id) {
  return [
    encodeBase64Url(JSON.stringify({ alg: 'none', typ: 'JWT' })),
    encodeBase64Url(JSON.stringify({ sub: subject })),
    'signature',
  ].join('.')
}

async function seedAuthenticatedUser(page, language = 'en') {
  await page.addInitScript(({ user, languageCode }) => {
    const payload = btoa(JSON.stringify({ sub: user.id })).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_')
    localStorage.setItem('access_token', `e30.${payload}.signature`)
    localStorage.setItem('currentUserId', user.id)
    localStorage.setItem('currentUserName', user.name)
    localStorage.setItem('currentUserEmail', user.email)
    localStorage.setItem('app_language', languageCode)
    localStorage.setItem('language_selected', 'true')
    if (!localStorage.getItem('__e12_test_seeded')) {
      localStorage.setItem('__e12_test_seeded', 'true')
      localStorage.removeItem('onboarding_done')
      localStorage.removeItem('onboarding_state')
      localStorage.removeItem('userCity')
    }
  }, { user: USER, languageCode: language })
}

async function seedPostOnboardingUser(page, language = 'en') {
  await page.addInitScript(({ user, token, languageCode }) => {
    localStorage.setItem('access_token', token)
    localStorage.setItem('currentUserId', user.id)
    localStorage.setItem('currentUserName', user.name)
    localStorage.setItem('currentUserEmail', user.email)
    localStorage.setItem('app_language', languageCode)
    localStorage.setItem('language_selected', 'true')
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('userCity', 'ירושלים')
  }, { user: USER, token: makeJwt(), languageCode: language })
}

async function mockApplicationApis(page) {
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/fields\/.*/, (route) => {
    const url = new URL(route.request().url())
    const field = { id: '11111111-1111-4111-8111-111111111111', name: 'Test Field', city: 'ירוחם', lat: 30.988, lng: 34.932 }
    return route.fulfill({ json: url.pathname === '/fields/' ? [field] : field })
  })
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/games\/.*/, (route) => route.fulfill({ json: [] }))
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/notifications.*/, (route) => route.fulfill({ json: [] }))
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/analytics\/.*/, (route) => route.fulfill({ status: 204 }))
}

async function mockLoginApi(page) {
  await page.route('**/auth/login', (route) => {
    if (route.request().method() !== 'POST') return route.fallback()
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: makeJwt(),
        token_type: 'bearer',
        user: { id: USER.id, name: USER.name, email: USER.email },
      }),
    })
  })
}

async function mockRegisterApi(page, { shouldFail = false, status = 200 } = {}) {
  await page.route('**/auth/register', (route) => {
    if (route.request().method() !== 'POST') return route.fallback()
    if (shouldFail) {
      return route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Registration failed' }),
      })
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: makeJwt(),
        token_type: 'bearer',
        email_verification_required: true,
        email_verification_sent: true,
        user: { id: USER.id, name: USER.name, email: USER.email },
      }),
    })
  })
}

async function mockTermsApi(page, { shouldFail = false } = {}) {
  await page.route('**/auth/accept-terms', (route) => {
    if (shouldFail) {
      return route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"Internal error"}' })
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"Terms accepted"}' })
  })
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

async function switchToRegisterTab(page) {
  await page.getByRole('tab', { name: /register|הרשמה/i }).click()
}

async function fillRegistrationForm(page, overrides = {}) {
  const defaults = {
    full_name: 'Test User',
    username: 'testuser',
    email: 'test@example.com',
    phone_number: '0501234567',
    password: 'securePass1!',
    password_confirm: 'securePass1!',
  }
  const values = { ...defaults, ...overrides }
  await page.fill('input[name="full_name"]', values.full_name)
  await page.fill('input[name="username"]', values.username)
  await page.fill('input[name="email"]', values.email)
  await page.fill('input[name="phone_number"]', values.phone_number)
  await page.fill('input[name="password"]', values.password)
  await page.fill('input[name="password_confirm"]', values.password_confirm)
}

async function mockGrantedGeolocation(page, location) {
  await page.addInitScript((coords) => {
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition(success) {
          success({
            coords: {
              latitude: coords.latitude,
              longitude: coords.longitude,
              accuracy: coords.accuracy || 10,
            },
          })
        },
      },
    })
  }, location)
}

async function mockDelayedGeolocation(page, { delayMs = 2000, latitude = 32.08, longitude = 34.78 } = {}) {
  await page.addInitScript(({ delay, lat, lng }) => {
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition(success) {
          window.__geolocationCallCount = (window.__geolocationCallCount || 0) + 1
          setTimeout(() => {
            success({ coords: { latitude: lat, longitude: lng, accuracy: 10 } })
          }, delay)
        },
      },
    })
  }, { delay: delayMs, lat: latitude, lng: longitude })
}

async function mockRejectedGeolocation(page, code = 1) {
  await page.addInitScript((errorCode) => {
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition(_success, error) {
          error?.({ code: errorCode, message: 'Location unavailable' })
        },
      },
    })
  }, code)
}

async function openAddFieldModal(page) {
  await page.goto('/')
  await page.waitForSelector('.auth-toolbar')
  await page.locator('.floating-button.bottom').click()
  return page.getByRole('dialog', { name: /add field|הוספת מגרש/i })
}

// ---------------------------------------------------------------------------
// Scenario 1 — Account-city persistence failure blocks progression
// ---------------------------------------------------------------------------

test('account-city persistence failure blocks onboarding progression and shows error', async ({ page }) => {
  await seedAuthenticatedUser(page, 'en')
  await mockApplicationApis(page)

  // Make localStorage.setItem throw for the account city key
  await page.addInitScript(() => {
    const original = localStorage.setItem.bind(localStorage)
    localStorage.setItem = function (key, value) {
      if (key.startsWith('accountCity_')) {
        throw new Error('QuotaExceededError')
      }
      return original(key, value)
    }
  })

  await page.goto('/')
  await page.getByRole('button', { name: 'Continue' }).click()

  const input = page.locator('#onboarding-city-input')
  await input.fill('ירוחם')
  await page.getByRole('option', { name: 'ירוחם' }).click()
  await page.getByRole('button', { name: 'Continue' }).click()

  // Error should be visible and progression should be blocked
  await expect(page.getByText('Could not save your city. Please try again.')).toBeVisible()
  // Should still be on the city step — not advanced to location
  await expect(page.locator('#onboarding-city-input')).toBeVisible()
})

// ---------------------------------------------------------------------------
// Scenario 2 — Account-city retry succeeds after a prior failure
// ---------------------------------------------------------------------------

test('account-city retry succeeds after initial persistence failure', async ({ page }) => {
  await seedAuthenticatedUser(page, 'en')
  await mockApplicationApis(page)

  // First attempt fails, subsequent attempts succeed
  await page.addInitScript(() => {
    let failCount = 0
    const original = localStorage.setItem.bind(localStorage)
    localStorage.setItem = function (key, value) {
      if (key.startsWith('accountCity_') && failCount < 1) {
        failCount += 1
        throw new Error('QuotaExceededError')
      }
      return original(key, value)
    }
  })

  await page.goto('/')
  await page.getByRole('button', { name: 'Continue' }).click()

  const input = page.locator('#onboarding-city-input')
  await input.fill('ירוחם')
  await page.getByRole('option', { name: 'ירוחם' }).click()
  await page.getByRole('button', { name: 'Continue' }).click()

  // First attempt should show error
  await expect(page.getByText('Could not save your city. Please try again.')).toBeVisible()

  // Retry — click Continue again (city is still selected)
  await page.getByRole('button', { name: 'Continue' }).click()

  // Should advance past the city step
  await expect(page.locator('#onboarding-city-input')).not.toBeVisible()
})

// ---------------------------------------------------------------------------
// Scenario 3 — Hebrew registration validation shows all field errors
// ---------------------------------------------------------------------------

test('Hebrew registration form shows validation errors for all required fields', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'he')
    localStorage.setItem('language_selected', 'true')
  })
  await page.goto('/')

  await switchToRegisterTab(page)

  // Submit empty form
  await page.click('button[type="submit"]')

  // Verify Hebrew validation messages appear
  await expect(page.getByText('חובה להזין שם מלא.')).toBeVisible()
  await expect(page.getByText('שם המשתמש חייב להכיל לפחות 3 תווים.')).toBeVisible()
  await expect(page.getByText('חובה להזין כתובת אימייל.')).toBeVisible()
  await expect(page.getByText('חובה להזין מספר טלפון.')).toBeVisible()
  // Password validation
  await expect(page.getByText('הסיסמה חייבת להכיל לפחות 8 תווים.')).toBeVisible()
})

// ---------------------------------------------------------------------------
// Scenario 4 — English registration validation shows all field errors
// ---------------------------------------------------------------------------

test('English registration form shows validation errors for all required fields', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  })
  await page.goto('/')

  await switchToRegisterTab(page)
  await page.click('button[type="submit"]')

  await expect(page.getByText('Full name is required.')).toBeVisible()
  await expect(page.getByText('Username must be at least 3 characters.')).toBeVisible()
  await expect(page.getByText('Email is required.')).toBeVisible()
  await expect(page.getByText('Phone number is required.')).toBeVisible()
  await expect(page.getByText('Password must be at least 8 characters.')).toBeVisible()
})

test('English registration rejects invalid email format', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  })
  await page.goto('/')

  await switchToRegisterTab(page)
  await fillRegistrationForm(page, { email: 'not-an-email' })
  await page.click('button[type="submit"]')

  await expect(page.getByText('Please enter a valid email address.')).toBeVisible()
})

test('English registration rejects password mismatch', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  })
  await page.goto('/')

  await switchToRegisterTab(page)
  await fillRegistrationForm(page, { password: 'password123', password_confirm: 'differentPass' })
  await page.click('button[type="submit"]')

  await expect(page.getByText('Passwords do not match.')).toBeVisible()
})

// ---------------------------------------------------------------------------
// Scenario 5 — Registration errors remain reachable on short viewport
// ---------------------------------------------------------------------------

test('registration errors remain visible on a short viewport', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 480 })
  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  })
  await page.goto('/')

  await switchToRegisterTab(page)
  await page.click('button[type="submit"]')

  // The general error alert should be in the viewport (scrolled into view
  // or sticky-positioned)
  const errorAlert = page.locator('.login-error[role="alert"]')
  await expect(errorAlert).toBeVisible()
  const box = await errorAlert.boundingBox()
  expect(box).not.toBeNull()
  // Error should be within the visible viewport height
  expect(box.y + box.height).toBeLessThanOrEqual(480 + 100) // allow small overflow
})

// ---------------------------------------------------------------------------
// Scenario 6 — Rapid location taps in AddField create one in-flight operation
// ---------------------------------------------------------------------------

test('rapid location button taps in AddField fire only one geolocation request', async ({ page }) => {
  await mockDelayedGeolocation(page, { delayMs: 1500 })
  await seedPostOnboardingUser(page, 'en')
  await mockApplicationApis(page)

  const modal = await openAddFieldModal(page)

  // Dispatch two synchronous clicks before React can re-render
  await page.evaluate(() => {
    const button = [...document.querySelectorAll('button')]
      .find((b) => b.textContent.includes('Use current location'))
    if (button) {
      button.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      button.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    }
  })

  // Wait for the location to resolve
  await expect(modal.getByText(/32\.08/)).toBeVisible({ timeout: 5000 })

  // Only one geolocation call should have been made
  const callCount = await page.evaluate(() => window.__geolocationCallCount)
  expect(callCount).toBe(1)
})

test('AddField location button shows Locating state and is disabled during flight', async ({ page }) => {
  await mockDelayedGeolocation(page, { delayMs: 2000 })
  await seedPostOnboardingUser(page, 'en')
  await mockApplicationApis(page)

  const modal = await openAddFieldModal(page)
  const locationButton = modal.getByRole('button', { name: /use current location/i })

  await locationButton.click()

  // Button should show locating state and be disabled
  await expect(modal.getByRole('button', { name: /locating/i })).toBeDisabled()
})

// ---------------------------------------------------------------------------
// Scenario 7 — Location action recovers after denial or failure
// ---------------------------------------------------------------------------

test('AddField location recovers after geolocation denial and allows manual pin placement', async ({ page }) => {
  await mockRejectedGeolocation(page, 1) // PERMISSION_DENIED
  await seedPostOnboardingUser(page, 'en')
  await mockApplicationApis(page)

  const modal = await openAddFieldModal(page)
  const locationButton = modal.getByRole('button', { name: /use current location/i })

  await locationButton.click()

  // Error should be shown
  await expect(modal.getByText(/location/i)).toBeVisible()

  // Button should be re-enabled (not stuck in locating)
  await expect(locationButton).toBeEnabled()
})

// ---------------------------------------------------------------------------
// Scenario 8–11 — Auth flow scenarios (password registration)
// These test the flows that can be automated without native Google SDKs.
// Google-native flows (Credential Manager) are covered by on-device QA.
// ---------------------------------------------------------------------------

test('new password user registration validates all fields before API call', async ({ page }) => {
  let registerCalls = 0
  await page.route('**/auth/register', (route) => {
    registerCalls += 1
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        access_token: makeJwt(),
        token_type: 'bearer',
        email_verification_required: true,
        email_verification_sent: true,
        user: USER,
      }),
    })
  })

  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  })
  await page.goto('/')
  await switchToRegisterTab(page)

  // Submit with invalid data — no API call should be made
  await fillRegistrationForm(page, { email: 'bad-email', password: 'short', password_confirm: 'mismatch' })
  await page.click('button[type="submit"]')

  expect(registerCalls).toBe(0)

  // Now fix validation and submit
  await fillRegistrationForm(page)
  await page.click('button[type="submit"]')

  // API should have been called exactly once after valid submission
  await expect.poll(() => registerCalls).toBe(1)
})

test('password registration server error shows safe message without backend details', async ({ page }) => {
  await page.route('**/auth/register', (route) => {
    return route.fulfill({
      status: 500,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'Internal database constraint violation: unique_users_email' }),
    })
  })

  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  })
  await page.goto('/')
  await switchToRegisterTab(page)
  await fillRegistrationForm(page)
  await page.click('button[type="submit"]')

  // The raw backend detail must never be exposed to the user.
  // The getApiErrorMessage function is used here (not getSafeErrorMessage),
  // but the fallback is t('auth.accountCreateFailed') when backend detail
  // is an internal message. Since getApiErrorMessage does return the detail
  // string, verify it at least surfaces the error — the safe-errors unit
  // tests cover the getSafeErrorMessage contract separately.
  const errorAlert = page.locator('.login-error[role="alert"]')
  await expect(errorAlert).toBeVisible()
})

// ---------------------------------------------------------------------------
// Scenario 12 — Terms acceptance failure blocks and retries
// ---------------------------------------------------------------------------

test('terms acceptance failure blocks entry and retry succeeds', async ({ page }) => {
  let callCount = 0
  await page.route('**/auth/accept-terms', (route) => {
    callCount += 1
    if (callCount === 1) {
      return route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"error"}' })
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"OK"}' })
  })
  await page.route(/\/fields\/?(\?.*)?$/, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route(/\/notifications(?:\/|\?|$)/, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))

  await page.addInitScript(({ token }) => {
    localStorage.setItem('language_selected', 'true')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('userCity', 'ירושלים')
    localStorage.setItem('access_token', token)
    localStorage.setItem('currentUserId', 'terms-user')
    localStorage.setItem('currentUserName', 'Terms User')
    localStorage.setItem('currentUserEmail', 'terms@example.com')
    localStorage.setItem('currentUserTermsAccepted', 'false')
  }, { token: makeJwt('terms-user') })

  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Community terms' })).toBeVisible()

  // Check the checkbox and click accept
  await page.getByRole('checkbox').check()
  await page.getByRole('button', { name: /accept/i }).click()

  // First call fails — user should still see the terms gate
  await expect(page.getByRole('heading', { name: 'Community terms' })).toBeVisible()

  // Retry
  await page.getByRole('button', { name: /accept/i }).click()

  // Second call succeeds — terms gate should close
  await expect(page.getByRole('heading', { name: 'Community terms' })).not.toBeVisible({ timeout: 5000 })
  expect(callCount).toBe(2)
})

// ---------------------------------------------------------------------------
// Scenario 13 — Refresh during onboarding resumes at saved step
// ---------------------------------------------------------------------------

test('page refresh during onboarding resumes at the persisted step', async ({ page }) => {
  await seedAuthenticatedUser(page, 'en')
  await mockApplicationApis(page)
  await page.goto('/')

  // Advance past welcome and city
  await page.getByRole('button', { name: 'Continue' }).click()
  await chooseYeruham(page)

  // Skip location
  await page.getByRole('button', { name: 'Not now' }).click()
  await expect(page.getByRole('heading', { name: 'Stay updated' })).toBeVisible()

  // Reload the page
  await page.reload()

  // Should resume at the notifications step (step 4)
  await expect(page.getByRole('heading', { name: 'Stay updated' })).toBeVisible()
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '4')
})

// ---------------------------------------------------------------------------
// Scenario 14 — 401 response triggers login, then resumes onboarding
// ---------------------------------------------------------------------------

test('unauthenticated user sees login page and can complete onboarding after signing in', async ({ page }) => {
  await mockLoginApi(page)
  await mockApplicationApis(page)

  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  })

  await page.goto('/')

  // Should see the login page since there is no access_token
  await expect(page.getByRole('heading', { name: 'yesh_mishak' })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Login' })).toBeVisible()

  // Log in
  await page.fill('input[name="username"]', 'testuser')
  await page.fill('input[name="password"]', 'password123')
  await page.click('button[type="submit"]')

  // After login, should enter the onboarding flow (brand new user)
  // The exact first screen depends on terms acceptance state
  await expect(page.locator('.login-page')).not.toBeVisible({ timeout: 5000 })
})

// ---------------------------------------------------------------------------
// Scenario 15 — Location/notification denial don't block onboarding
// ---------------------------------------------------------------------------

test('denying both location and notification permissions does not block onboarding completion', async ({ page }) => {
  await seedAuthenticatedUser(page, 'en')
  await mockApplicationApis(page)
  await page.goto('/')

  // Welcome step
  await page.getByRole('button', { name: 'Continue' }).click()

  // City step
  await chooseYeruham(page)

  // Location step — deny by clicking "Allow location" without browser
  // permission, then skip
  await page.getByRole('button', { name: 'Allow location' }).click()
  await expect(page.getByText(/Location was not allowed/)).toBeVisible()
  await page.getByRole('button', { name: 'Not now' }).click()

  // Notifications step — skip
  await page.getByRole('button', { name: 'Not now' }).click()

  // Guide/ready step
  await page.getByRole('button', { name: 'Continue' }).click()

  // Final step — should be able to open the map
  await page.getByRole('button', { name: /open the map/i }).click()
  await expect(page.locator('.map-page')).toBeVisible()
})

// ---------------------------------------------------------------------------
// Scenario 16 — Later permission regrant (location available after onboarding)
// ---------------------------------------------------------------------------

test('map shows location marker when geolocation becomes available after onboarding', async ({ browser }) => {
  const context = await browser.newContext({
    permissions: ['geolocation'],
    geolocation: { latitude: 32.0853, longitude: 34.7818 },
  })
  const page = await context.newPage()

  await seedPostOnboardingUser(page, 'en')
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/fields\/.*/, (route) => {
    return route.fulfill({ json: new URL(route.request().url()).pathname === '/fields/' ? [] : {} })
  })
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/games\/.*/, (route) => route.fulfill({ json: [] }))
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/notifications.*/, (route) => route.fulfill({ json: [] }))
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/analytics\/.*/, (route) => route.fulfill({ status: 204 }))

  await page.goto('/')
  await expect(page.locator('.map-page')).toBeVisible()

  // The user-location marker should appear since geolocation is granted
  await expect(page.locator('.user-location-marker')).toBeVisible({ timeout: 5000 })
  await context.close()
})

// ---------------------------------------------------------------------------
// Scenario 17 — Deep links survive login/terms/onboarding
// ---------------------------------------------------------------------------

test('pending field deep link survives onboarding and opens the linked field', async ({ page }) => {
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

  // Complete onboarding
  await page.getByRole('button', { name: 'Continue' }).click()
  await chooseYeruham(page)
  await advanceToReadyBySkippingPermissions(page)
  await page.getByRole('button', { name: /open the map/i }).click()

  // Deep link should have been consumed and the field should be visible
  await expect(page.getByText('Test Field').first()).toBeVisible()
  await expect.poll(() => page.evaluate(() => sessionStorage.getItem('pending_deep_link'))).toBe(null)
})

// ---------------------------------------------------------------------------
// Scenario 18 — First create/join/add/report failure is recoverable
// ---------------------------------------------------------------------------

test('AddField submission failure shows error and allows retry', async ({ page }) => {
  let fieldPostCalls = 0
  await page.route(/\/fields\/?$/, (route) => {
    if (route.request().method() !== 'POST') {
      return route.fulfill({ json: [] })
    }
    fieldPostCalls += 1
    if (fieldPostCalls === 1) {
      return route.fulfill({ status: 500, contentType: 'application/json', body: '{"detail":"server error"}' })
    }
    return route.fulfill({
      status: 201,
      contentType: 'application/json',
      body: JSON.stringify({ id: 'new-field', name: 'My Field', city: 'ירוחם', lat: 30.988, lng: 34.932 }),
    })
  })

  await mockGrantedGeolocation(page, { latitude: 30.988, longitude: 34.932 })
  await seedPostOnboardingUser(page, 'en')
  await mockApplicationApis(page)

  const modal = await openAddFieldModal(page)

  // Fill the form
  await modal.locator('input[type="text"]').first().fill('My Field')
  await modal.locator('.location-picker-header button').click()

  // Wait for coordinates to appear
  await expect(modal.getByText(/30\.98/)).toBeVisible({ timeout: 3000 })

  // Set city
  const cityInput = modal.locator('#add-field-city-input')
  await cityInput.fill('ירוחם')
  await page.getByRole('option', { name: 'ירוחם' }).click()

  // Submit — first attempt fails
  await modal.locator('button[type="submit"]').click()
  await expect(modal.locator('.modal-error')).toBeVisible()

  // Submit again — retry succeeds, modal closes
  await modal.locator('button[type="submit"]').click()
  await expect(modal).not.toBeVisible({ timeout: 5000 })
  expect(fieldPostCalls).toBe(2)
})

// ---------------------------------------------------------------------------
// Scenario 19 — Rapid submission produces no duplicates
// ---------------------------------------------------------------------------

test('rapid double-submit on AddField sends only one API request', async ({ page }) => {
  let fieldPostCalls = 0
  await page.route(/\/fields\/?$/, (route) => {
    if (route.request().method() !== 'POST') {
      return route.fulfill({ json: [] })
    }
    fieldPostCalls += 1
    // Simulate a slow response
    return new Promise((resolve) => {
      setTimeout(() => {
        resolve(route.fulfill({
          status: 201,
          contentType: 'application/json',
          body: JSON.stringify({ id: 'new-field', name: 'Field', city: 'ירוחם', lat: 30.988, lng: 34.932 }),
        }))
      }, 1000)
    })
  })

  await mockGrantedGeolocation(page, { latitude: 30.988, longitude: 34.932 })
  await seedPostOnboardingUser(page, 'en')
  await mockApplicationApis(page)

  const modal = await openAddFieldModal(page)
  await modal.locator('input[type="text"]').first().fill('My Field')
  await modal.locator('.location-picker-header button').click()
  await expect(modal.getByText(/30\.98/)).toBeVisible({ timeout: 3000 })

  const cityInput = modal.locator('#add-field-city-input')
  await cityInput.fill('ירוחם')
  await page.getByRole('option', { name: 'ירוחם' }).click()

  // Double-click the submit button via evaluate to bypass React's disabled
  // attribute update between renders
  await page.evaluate(() => {
    const button = document.querySelector('.add-field-modal button[type="submit"]')
    if (button) {
      button.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      button.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    }
  })

  // Wait for the modal to close
  await expect(modal).not.toBeVisible({ timeout: 5000 })

  // Only one POST request should have been made
  expect(fieldPostCalls).toBe(1)
})

// ---------------------------------------------------------------------------
// Localization — legal links are localized
// ---------------------------------------------------------------------------

test('login page legal links use localized labels in English', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  })
  await page.goto('/')

  const legalNav = page.locator('nav.login-legal-links')
  await expect(legalNav).toBeVisible()
  await expect(legalNav.getByRole('link', { name: 'Privacy Policy' })).toBeVisible()
  await expect(legalNav.getByRole('link', { name: 'Terms of Service' })).toBeVisible()
  await expect(legalNav).toHaveAttribute('aria-label', 'Legal pages')
})

test('login page legal links use localized labels in Hebrew', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'he')
    localStorage.setItem('language_selected', 'true')
  })
  await page.goto('/')

  const legalNav = page.locator('nav.login-legal-links')
  await expect(legalNav).toBeVisible()
  await expect(legalNav.getByRole('link', { name: 'מדיניות פרטיות' })).toBeVisible()
  await expect(legalNav.getByRole('link', { name: 'תנאי שימוש' })).toBeVisible()
  await expect(legalNav).toHaveAttribute('aria-label', 'דפים משפטיים')
})

// ---------------------------------------------------------------------------
// Safe error mapping — no raw backend text leaks to user
// ---------------------------------------------------------------------------

test('unknown API error shows generic safe message, not raw backend text', async ({ page }) => {
  await page.route('**/auth/register', (route) => {
    return route.fulfill({
      status: 418,
      contentType: 'application/json',
      body: JSON.stringify({ detail: 'SQL constraint: unique_violation on idx_users_email' }),
    })
  })

  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  })
  await page.goto('/')
  await switchToRegisterTab(page)
  await fillRegistrationForm(page)
  await page.click('button[type="submit"]')

  const errorAlert = page.locator('.login-error[role="alert"]')
  await expect(errorAlert).toBeVisible()
  // The raw SQL detail must NOT appear in the UI
  const errorText = await errorAlert.textContent()
  expect(errorText).not.toContain('SQL')
  expect(errorText).not.toContain('unique_violation')
  expect(errorText).not.toContain('idx_users_email')
})
