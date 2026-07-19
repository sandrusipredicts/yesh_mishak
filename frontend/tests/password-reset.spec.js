import { expect, test } from '@playwright/test'

const user = {
  id: '31b6ac09-74f0-49f4-8916-c216842a3498',
  name: 'Signed In User',
  email: 'signed-in@example.com',
}

const resetToken = 'reset-token-value-with-enough-length-123456'
const validPassword = 'new-password-123'

function makeJwt(subject = user.id) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url')
  return `${encode({ alg: 'none' })}.${encode({ sub: subject })}.signature`
}

async function prepareApp(page, { loggedIn = false } = {}) {
  await page.addInitScript(({ storedUser, token }) => {
    localStorage.setItem('language_selected', 'true')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('userCity', 'ירושלים') // E08-02 follow-up fix: account needs a resolved city to reach the map
    window.__consoleMessages = []

    for (const level of ['log', 'warn', 'error']) {
      const original = console[level]
      console[level] = (...args) => {
        window.__consoleMessages.push(args.map((arg) => String(arg)).join(' '))
        original(...args)
      }
    }

    if (token) {
      localStorage.setItem('access_token', token)
      localStorage.setItem('currentUserId', storedUser.id)
      localStorage.setItem('currentUserName', storedUser.name)
      localStorage.setItem('currentUserEmail', storedUser.email)
      localStorage.setItem('currentUsername', 'signed-in-user')
      sessionStorage.setItem('access_token', token)
    }
  }, { storedUser: user, token: loggedIn ? makeJwt() : '' })

  await page.route('**/fields/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/games/active/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/games/upcoming/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/notifications/unread-count', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{"count":0}' }))
}

async function fillResetForm(page, password = validPassword, confirm = password) {
  await page.locator('input[name="password"]').fill(password)
  await page.locator('input[name="password_confirm"]').fill(confirm)
}

test('reset route loads while logged out', async ({ page }) => {
  await prepareApp(page)
  await page.goto(`/reset-password?token=${resetToken}`)

  await expect(page.getByRole('heading', { name: 'Choose a new password' })).toBeVisible()
  await expect(page.locator('.login-page')).toBeVisible()
  await expect(page.locator('.auth-toolbar')).toHaveCount(0)
})

test('reset route loads while another user is logged in', async ({ page }) => {
  await prepareApp(page, { loggedIn: true })
  await page.goto(`/reset-password?token=${resetToken}`)

  await expect(page.getByRole('heading', { name: 'Choose a new password' })).toBeVisible()
  await expect(page.locator('.auth-toolbar')).toHaveCount(0)
  await expect(page.locator('.map-page')).toHaveCount(0)
})

test('missing token shows an error and disables submit', async ({ page }) => {
  await prepareApp(page)
  await page.goto('/reset-password')

  await expect(page.getByRole('alert')).toContainText('missing a token')
  await expect(page.getByRole('button', { name: 'Reset password' })).toBeDisabled()
})

test('invalid token response is mapped safely', async ({ page }) => {
  await prepareApp(page)
  await page.route('**/auth/password-reset/confirm', (route) =>
    route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({ detail: { error: true, code: 'RESET_TOKEN_INVALID', message: 'invalid' } }),
    }))

  await page.goto(`/reset-password?token=${resetToken}`)
  await fillResetForm(page)
  await page.getByRole('button', { name: 'Reset password' }).click()

  await expect(page.getByRole('alert')).toContainText('invalid')
})

test('expired token response is mapped safely', async ({ page }) => {
  await prepareApp(page)
  await page.route('**/auth/password-reset/confirm', (route) =>
    route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({ detail: { error: true, code: 'RESET_TOKEN_EXPIRED', message: 'expired' } }),
    }))

  await page.goto(`/reset-password?token=${resetToken}`)
  await fillResetForm(page)
  await page.getByRole('button', { name: 'Reset password' }).click()

  await expect(page.getByRole('alert')).toContainText('expired')
})

test('password mismatch blocks submission', async ({ page }) => {
  await prepareApp(page)
  let requests = 0
  await page.route('**/auth/password-reset/confirm', (route) => {
    requests += 1
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"ok"}' })
  })

  await page.goto(`/reset-password?token=${resetToken}`)
  await fillResetForm(page, validPassword, 'different-password')

  await expect(page.getByText('Passwords do not match.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reset password' })).toBeDisabled()
  expect(requests).toBe(0)
})

test('password validation failure blocks submission', async ({ page }) => {
  await prepareApp(page)
  let requests = 0
  await page.route('**/auth/password-reset/confirm', (route) => {
    requests += 1
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"ok"}' })
  })

  await page.goto(`/reset-password?token=${resetToken}`)
  await fillResetForm(page, 'short', 'short')

  await expect(page.getByText('Password must be at least 8 characters.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Reset password' })).toBeDisabled()
  expect(requests).toBe(0)
})

test('successful reset clears the current session and redirects to login', async ({ page }) => {
  await prepareApp(page, { loggedIn: true })
  let resetAuthorization = null
  await page.route('**/auth/password-reset/confirm', (route) => {
    resetAuthorization = route.request().headers().authorization ?? null
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"ok"}' })
  })

  await page.goto(`/reset-password?token=${resetToken}`)
  await fillResetForm(page)
  await page.getByRole('button', { name: 'Reset password' }).click()

  await expect(page).toHaveURL(/\/login\?reset=success$/)
  await expect(page.getByText('Your password was reset successfully. Please sign in.')).toBeVisible()
  expect(resetAuthorization).toBe(null)
  await expect.poll(() => page.evaluate(() => ({
    token: localStorage.getItem('access_token'),
    id: localStorage.getItem('currentUserId'),
    sessionToken: sessionStorage.getItem('access_token'),
  }))).toEqual({ token: null, id: null, sessionToken: null })
})

test('duplicate reset submissions are prevented', async ({ page }) => {
  await prepareApp(page)
  let requests = 0
  let releaseRequest
  await page.route('**/auth/password-reset/confirm', async (route) => {
    requests += 1
    await new Promise((resolve) => {
      releaseRequest = resolve
    })
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"ok"}' })
  })

  await page.goto(`/reset-password?token=${resetToken}`)
  await fillResetForm(page)
  await page.getByRole('button', { name: 'Reset password' }).click()
  await expect(page.getByRole('button', { name: 'Resetting...' })).toBeDisabled()
  await page.getByRole('button', { name: 'Resetting...' }).click({ force: true })
  expect(requests).toBe(1)
  releaseRequest()
  await expect(page).toHaveURL(/\/login\?reset=success$/)
})

test('forgot password shows a generic response', async ({ page }) => {
  await prepareApp(page)
  let requestBody
  await page.route('**/auth/password-reset/request', async (route) => {
    requestBody = route.request().postDataJSON()
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"server generic"}' })
  })

  await page.goto('/forgot-password')
  await page.locator('input[name="email"]').fill('missing@example.com')
  await page.getByRole('button', { name: 'Send reset link' }).click()

  expect(requestBody).toEqual({ email: 'missing@example.com' })
  await expect(page.getByText('If an eligible account exists, password reset instructions will be sent.')).toBeVisible()
})

test('forgot password rate limit response is shown without account details', async ({ page }) => {
  await prepareApp(page)
  await page.route('**/auth/password-reset/request', (route) =>
    route.fulfill({
      status: 429,
      contentType: 'application/json',
      body: JSON.stringify({ error: true, code: 'RATE_LIMITED', message: 'Too many requests' }),
    }))

  await page.goto('/forgot-password')
  await page.locator('input[name="email"]').fill('person@example.com')
  await page.getByRole('button', { name: 'Send reset link' }).click()

  await expect(page.getByRole('alert')).toContainText('Too many attempts')
  await expect(page.getByText('person@example.com')).toHaveCount(0)
})

test('reset rate limit response is shown safely', async ({ page }) => {
  await prepareApp(page)
  await page.route('**/auth/password-reset/confirm', (route) =>
    route.fulfill({
      status: 429,
      contentType: 'application/json',
      body: JSON.stringify({ error: true, code: 'RATE_LIMITED', message: 'Too many requests' }),
    }))

  await page.goto(`/reset-password?token=${resetToken}`)
  await fillResetForm(page)
  await page.getByRole('button', { name: 'Reset password' }).click()

  await expect(page.getByRole('alert')).toContainText('Too many attempts')
})

test('reset token is not logged or rendered', async ({ page }) => {
  await prepareApp(page)
  await page.route('**/auth/password-reset/confirm', (route) =>
    route.fulfill({
      status: 400,
      contentType: 'application/json',
      body: JSON.stringify({ detail: { error: true, code: 'RESET_TOKEN_INVALID', message: 'invalid' } }),
    }))

  await page.goto(`/reset-password?token=${resetToken}`)
  await fillResetForm(page)
  await page.getByRole('button', { name: 'Reset password' }).click()
  await expect(page.getByRole('alert')).toContainText('invalid')

  const renderedText = await page.locator('body').innerText()
  const consoleMessages = await page.evaluate(() => window.__consoleMessages)
  expect(renderedText).not.toContain(resetToken)
  expect(consoleMessages.join('\n')).not.toContain(resetToken)
})
