import { expect, test } from '@playwright/test'

const user = {
  id: '31b6ac09-74f0-49f4-8916-c216842a3498',
  name: 'Signed In User',
  email: 'signed-in@example.com',
}

function makeJwt(subject = user.id) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url')
  return `${encode({ alg: 'none' })}.${encode({ sub: subject })}.signature`
}

async function prepareApp(page, { language = 'en' } = {}) {
  await page.addInitScript(({ storedUser, token, lang }) => {
    localStorage.setItem('language_selected', 'true')
    localStorage.setItem('app_language', lang)
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('userCity', 'ירושלים') // E08-02 follow-up fix: account needs a resolved city to reach the map
    localStorage.setItem('access_token', token)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.setItem('currentUsername', 'signed-in-user')
    sessionStorage.setItem('access_token', token)
  }, { storedUser: user, token: makeJwt(), lang: language })
}

// Mirrors LoginPage's real GIS callback contract but captures the callback so
// tests can simulate clicking the rendered button to produce a credential —
// the shared mock in email-verification.spec.js only counts render calls.
async function installGoogleIdentityMock(page) {
  await page.addInitScript(() => {
    window.__googleIdentityCalls = { initialize: 0, renderButton: 0 }
    window.google = {
      accounts: {
        id: {
          initialize: (config) => {
            window.__googleIdentityCalls.initialize += 1
            window.__googleCallback = config.callback
          },
          renderButton: (container) => {
            window.__googleIdentityCalls.renderButton += 1
            container.replaceChildren()
            const button = document.createElement('button')
            button.type = 'button'
            button.textContent = 'Continue with Google'
            button.onclick = () => window.__googleCallback({ credential: 'fake-google-credential' })
            container.appendChild(button)
          },
        },
      },
    }
  })
}

function methodsBody({
  emailLinked = true,
  emailVerified = true,
  emailCanUnlink = false,
  googleLinked = false,
  googleCanUnlink = false,
} = {}) {
  return JSON.stringify({
    email: {
      address: emailLinked ? 's***@example.com' : null,
      linked: emailLinked,
      verified: emailVerified,
      can_unlink: emailCanUnlink,
    },
    google: {
      linked: googleLinked,
      email: googleLinked ? 'g***@gmail.com' : null,
      can_unlink: googleCanUnlink,
    },
    available_login_methods: (emailLinked ? 1 : 0) + (googleLinked ? 1 : 0),
  })
}

async function goToSettings(page) {
  await page.goto('/settings')
  await expect(page.getByRole('heading', { name: 'Sign-in methods' })).toBeVisible()
}

test('settings requires login and does not render for a logged-out user', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('language_selected', 'true')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('userCity', 'ירושלים') // E08-02 follow-up fix: account needs a resolved city to reach the map
  })
  await page.goto('/settings')

  await expect(page.getByRole('tab', { name: 'Login' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Sign-in methods' })).toHaveCount(0)
})

test('manual-only user sees Google not connected and cannot remove password', async ({ page }) => {
  await prepareApp(page)
  await page.route('**/auth/account-methods', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: methodsBody() }))

  await goToSettings(page)

  await expect(page.getByText('s***@example.com')).toBeVisible()
  await expect(page.getByText('Connect Google', { exact: true })).toBeVisible()
  await expect(page.locator('.google-login-button')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Remove password' })).toBeDisabled()
  await expect(page.getByText('You cannot remove the password before connecting a Google account.')).toBeVisible()
})

test('google-only user cannot disconnect Google and can set a password', async ({ page }) => {
  await prepareApp(page)
  await page.route('**/auth/account-methods', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: methodsBody({ emailLinked: false, googleLinked: true, googleCanUnlink: false }),
    }))

  await goToSettings(page)

  await expect(page.getByText('Not set up')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Set password' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Disconnect Google' })).toBeDisabled()
  await expect(page.getByText('You cannot disconnect Google before setting a password for this account.')).toBeVisible()
})

test('user with both methods can unlink either one', async ({ page }) => {
  await prepareApp(page)
  await page.route('**/auth/account-methods', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: methodsBody({ emailCanUnlink: true, googleLinked: true, googleCanUnlink: true }),
    }))

  await goToSettings(page)

  await expect(page.getByRole('button', { name: 'Remove password' })).toBeEnabled()
  await expect(page.getByRole('button', { name: 'Disconnect Google' })).toBeEnabled()
})

test('linking Google succeeds and updates the UI', async ({ page }) => {
  await prepareApp(page)
  await installGoogleIdentityMock(page)
  await page.route('**/auth/account-methods', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: methodsBody() }))
  let requestBody
  await page.route('**/auth/link/google', (route) => {
    requestBody = route.request().postDataJSON()
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        account_methods: JSON.parse(methodsBody({ emailCanUnlink: true, googleLinked: true, googleCanUnlink: true })),
        access_token: makeJwt(),
      }),
    })
  })

  await goToSettings(page)
  await page.locator('.google-login-button button').click()

  expect(requestBody).toEqual({ token: 'fake-google-credential' })
  await expect(page.getByText('Google account connected successfully.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Disconnect Google' })).toBeEnabled()
})

test('linking Google prevents repeated submissions while the request is pending', async ({ page }) => {
  await prepareApp(page)
  await installGoogleIdentityMock(page)
  await page.route('**/auth/account-methods', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: methodsBody() }))

  let requests = 0
  let releaseRequest
  await page.route('**/auth/link/google', async (route) => {
    requests += 1
    await new Promise((resolve) => {
      releaseRequest = resolve
    })
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        account_methods: JSON.parse(methodsBody({ emailCanUnlink: true, googleLinked: true, googleCanUnlink: true })),
        access_token: makeJwt(),
      }),
    })
  })

  await goToSettings(page)
  const googleButton = page.locator('.google-login-button button')
  await googleButton.click()
  await expect.poll(() => requests).toBe(1)
  await googleButton.click({ force: true })
  expect(requests).toBe(1)

  releaseRequest()
  await expect(page.getByText('Google account connected successfully.')).toBeVisible()
})

test('linking a Google account already used elsewhere shows a safe error', async ({ page }) => {
  await prepareApp(page)
  await installGoogleIdentityMock(page)
  await page.route('**/auth/account-methods', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: methodsBody() }))
  await page.route('**/auth/link/google', (route) =>
    route.fulfill({
      status: 409,
      contentType: 'application/json',
      body: JSON.stringify({ error: true, code: 'ACCOUNT_METHOD_IN_USE_BY_ANOTHER_ACCOUNT', message: 'in use' }),
    }))

  await goToSettings(page)
  await page.locator('.google-login-button button').click()

  await expect(page.getByText('This Google account is already linked to a different account.')).toBeVisible()
})

test('unlinking Google requires the current password and prevents double submit', async ({ page }) => {
  await prepareApp(page)
  await page.route('**/auth/account-methods', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: methodsBody({ emailCanUnlink: true, googleLinked: true, googleCanUnlink: true }),
    }))

  let requests = 0
  let releaseRequest
  await page.route('**/auth/unlink/google', async (route) => {
    requests += 1
    await new Promise((resolve) => {
      releaseRequest = resolve
    })
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        account_methods: JSON.parse(methodsBody({ emailCanUnlink: false, googleLinked: false })),
        access_token: makeJwt(),
      }),
    })
  })

  await goToSettings(page)
  await page.getByRole('button', { name: 'Disconnect Google' }).click()
  await expect(page.getByRole('heading', { name: 'Disconnect Google' })).toBeVisible()
  await page.getByLabel('Password', { exact: true }).fill('CorrectHorse123')
  await page.getByRole('button', { name: 'Disconnect', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Disconnecting...' })).toBeDisabled()
  await page.getByRole('button', { name: 'Disconnecting...' }).click({ force: true })
  expect(requests).toBe(1)

  releaseRequest()
  await expect(page.getByText('Google account disconnected successfully.')).toBeVisible()
})

test('wrong current password shows a reauthentication error', async ({ page }) => {
  await prepareApp(page)
  await page.route('**/auth/account-methods', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: methodsBody({ emailCanUnlink: true, googleLinked: true, googleCanUnlink: true }),
    }))
  await page.route('**/auth/unlink/google', (route) =>
    route.fulfill({
      // 403, not 401: the backend deliberately avoids 401 here so this
      // in-session error never trips the global "401 clears the session"
      // axios interceptor.
      status: 403,
      contentType: 'application/json',
      body: JSON.stringify({ error: true, code: 'REAUTHENTICATION_REQUIRED', message: 'wrong password' }),
    }))

  await goToSettings(page)
  await page.getByRole('button', { name: 'Disconnect Google' }).click()
  await page.getByLabel('Password', { exact: true }).fill('totally-wrong')
  await page.getByRole('button', { name: 'Disconnect', exact: true }).click()

  await expect(page.getByText('Your current password is incorrect.')).toBeVisible()
})

test('setting a password re-authenticates with Google then submits the new password', async ({ page }) => {
  await prepareApp(page)
  await installGoogleIdentityMock(page)
  await page.route('**/auth/account-methods', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: methodsBody({ emailLinked: false, googleLinked: true, googleCanUnlink: false }),
    }))

  let requestBody
  await page.route('**/auth/set-password', (route) => {
    requestBody = route.request().postDataJSON()
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        account_methods: JSON.parse(
          methodsBody({ emailLinked: true, emailCanUnlink: true, googleLinked: true, googleCanUnlink: true }),
        ),
        access_token: makeJwt(),
      }),
    })
  })

  await goToSettings(page)
  await page.getByRole('button', { name: 'Set password' }).click()
  const setPasswordModal = page.locator('.account-linking-modal')
  await expect(setPasswordModal.getByRole('heading', { name: 'Set password' })).toBeVisible()
  await expect(setPasswordModal.getByText('Re-authenticate with Google', { exact: true })).toBeVisible()
  await setPasswordModal.locator('.google-login-button button').click()

  await setPasswordModal.getByLabel('New password').fill('BrandNewPass123')
  await setPasswordModal.getByLabel('Confirm password').fill('BrandNewPass123')
  await setPasswordModal.getByRole('button', { name: 'Set password', exact: true }).click()

  expect(requestBody).toEqual({
    google_token: 'fake-google-credential',
    password: 'BrandNewPass123',
    password_confirm: 'BrandNewPass123',
  })
  await expect(page.getByText('Password set successfully.')).toBeVisible()
})

test('password mismatch blocks the set-password submission', async ({ page }) => {
  await prepareApp(page)
  await installGoogleIdentityMock(page)
  await page.route('**/auth/account-methods', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: methodsBody({ emailLinked: false, googleLinked: true, googleCanUnlink: false }),
    }))

  let requests = 0
  await page.route('**/auth/set-password', (route) => {
    requests += 1
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{}' })
  })

  await goToSettings(page)
  await page.getByRole('button', { name: 'Set password' }).click()
  const setPasswordModal = page.locator('.account-linking-modal')
  await setPasswordModal.locator('.google-login-button button').click()
  await setPasswordModal.getByLabel('New password').fill('BrandNewPass123')
  await setPasswordModal.getByLabel('Confirm password').fill('Different123')

  await expect(page.getByText('Passwords do not match.')).toBeVisible()
  await expect(setPasswordModal.getByRole('button', { name: 'Set password', exact: true })).toBeDisabled()
  expect(requests).toBe(0)
})

test('removing the password re-authenticates with Google then confirms', async ({ page }) => {
  await prepareApp(page)
  await installGoogleIdentityMock(page)
  await page.route('**/auth/account-methods', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: methodsBody({ emailCanUnlink: true, googleLinked: true, googleCanUnlink: true }),
    }))

  let requestBody
  await page.route('**/auth/remove-password', (route) => {
    requestBody = route.request().postDataJSON()
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        account_methods: JSON.parse(
          methodsBody({ emailLinked: false, googleLinked: true, googleCanUnlink: false }),
        ),
        access_token: makeJwt(),
      }),
    })
  })

  await goToSettings(page)
  await page.getByRole('button', { name: 'Remove password' }).click()
  const removeModal = page.locator('.confirm-modal')
  await expect(removeModal.getByText('Re-authenticate with Google', { exact: true })).toBeVisible()
  await removeModal.locator('.google-login-button button').click()
  await removeModal.getByRole('button', { name: 'Remove password', exact: true }).click()

  expect(requestBody).toEqual({ google_token: 'fake-google-credential' })
  await expect(page.getByText('Password removed successfully.')).toBeVisible()
})

test('loading failure shows a retry option', async ({ page }) => {
  await prepareApp(page)
  await page.route('**/auth/account-methods', (route) =>
    route.fulfill({ status: 500, contentType: 'application/json', body: '{}' }))

  await goToSettings(page)
  await expect(page.getByText('Could not load your sign-in methods.')).toBeVisible()

  await page.unroute('**/auth/account-methods')
  await page.route('**/auth/account-methods', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: methodsBody() }))

  await page.getByRole('button', { name: 'Retry' }).click()
  await expect(page.getByText('s***@example.com')).toBeVisible()
})

test('settings screen renders in Hebrew with RTL layout', async ({ page }) => {
  await prepareApp(page, { language: 'he' })
  await page.route('**/auth/account-methods', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: methodsBody() }))

  await page.goto('/settings')

  await expect(page.getByRole('heading', { name: 'שיטות התחברות' })).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expect(page.getByText('חיבור Google', { exact: true })).toBeVisible()
})
