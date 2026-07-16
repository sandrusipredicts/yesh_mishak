import { expect, test } from '@playwright/test'


async function seedEnglishReturningUser(page) {
  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  })
}


async function installGoogleIdentityMock(page) {
  await page.addInitScript(() => {
    window.__googleIdentityCalls = { initialize: 0, renderButton: 0 }
    window.google = {
      accounts: {
        id: {
          initialize: (options) => {
            window.__googleIdentityCalls.initialize += 1
            window.__googleIdentityCallback = options.callback
          },
          renderButton: (container) => {
            window.__googleIdentityCalls.renderButton += 1
            const button = document.createElement('button')
            button.type = 'button'
            button.setAttribute('aria-label', 'Sign in with Google')
            button.textContent = 'Continue with Google'
            button.addEventListener('click', () => {
              window.__googleIdentityCallback?.({ credential: 'fake-google-token' })
            })
            container.appendChild(button)
          },
        },
      },
    }
  })
}


async function expectGoogleButtonRenderedOnce(page) {
  await expect(page.locator('.google-login-button button')).toBeVisible()
  await expect.poll(() => page.evaluate(() => window.__googleIdentityCalls)).toEqual({
    initialize: 1,
    renderButton: 1,
  })
}


async function fillRegistration(page) {
  await page.getByRole('tab', { name: 'Register' }).click()
  await page.getByLabel('Full name').fill('Verification User')
  await page.getByLabel('Username', { exact: true }).fill('verification-user')
  await page.getByLabel('Email', { exact: true }).fill('verify@example.com')
  await page.getByLabel('Phone number').fill('0501234567')
  await page.getByRole('textbox', { name: /^Password/ }).fill('strongpass123')
  await page.getByLabel('Confirm password').fill('strongpass123')
}


test('valid verification link shows success and returns to login', async ({ page }) => {
  await seedEnglishReturningUser(page)
  await installGoogleIdentityMock(page)
  await page.route('**/auth/verify-email', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'verified', message: 'Email verified successfully.' }),
  }))

  await page.goto(`/verify-email?token=${'a'.repeat(48)}`)

  await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible()
  await expect(page.getByText('Your email is verified. You can sign in now.')).toBeVisible()
  await page.getByRole('button', { name: 'Back to sign in' }).click()
  await expect(page.getByRole('tab', { name: 'Login' })).toBeVisible()
  await expectGoogleButtonRenderedOnce(page)
  await expect(page.getByText('Google login button could not be mounted.')).toHaveCount(0)
  await expect(page).toHaveURL(/\/$/)
})


for (const verificationStatus of ['invalid', 'expired']) {
  test(`Google button initializes after returning from ${verificationStatus} verification`, async ({ page }) => {
    await seedEnglishReturningUser(page)
    await installGoogleIdentityMock(page)
    await page.route('**/auth/verify-email', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: verificationStatus, message: 'Safe verification result.' }),
    }))

    await page.goto(`/verify-email?token=${verificationStatus[0].repeat(48)}`)
    await page.getByRole('button', { name: 'Back to sign in' }).click()
    await expectGoogleButtonRenderedOnce(page)
  })
}


test('Google button initializes on a direct login refresh', async ({ page }) => {
  await seedEnglishReturningUser(page)
  await installGoogleIdentityMock(page)
  await page.goto('/')
  await expectGoogleButtonRenderedOnce(page)
  await page.reload()
  await expectGoogleButtonRenderedOnce(page)
})


test('web Google login displays the account-linking-required guidance', async ({ page }) => {
  await seedEnglishReturningUser(page)
  await installGoogleIdentityMock(page)
  await page.route('**/auth/google', (route) => route.fulfill({
    status: 409,
    contentType: 'application/json',
    body: JSON.stringify({
      error: true,
      code: 'ACCOUNT_LINK_REQUIRED',
      message: 'Account linking required',
    }),
  }))

  await page.goto('/')
  await page.locator('.google-login-button button').click()

  await expect(page.locator('.login-error')).toHaveText(
    'An account with this email already exists. Sign in with your password, then connect Google from Settings.',
  )
})


test('Google button initializes after returning from Hebrew verification', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'he')
    localStorage.setItem('language_selected', 'true')
  })
  await installGoogleIdentityMock(page)
  await page.route('**/auth/verify-email', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'verified', message: 'Verified.' }),
  }))

  await page.goto(`/verify-email?token=${'h'.repeat(48)}`)
  await page.locator('.auth-secondary').click()
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expectGoogleButtonRenderedOnce(page)
})


test('expired verification link shows a safe actionable message', async ({ page }) => {
  await seedEnglishReturningUser(page)
  await page.route('**/auth/verify-email', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'expired', message: 'This verification link has expired.' }),
  }))

  await page.goto(`/verify-email?token=${'b'.repeat(48)}`)

  await expect(page.getByText('This verification link has expired. Request a new one.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Back to sign in' })).toBeVisible()
})


test('already-used verification link shows an idempotent sign-in message', async ({ page }) => {
  await seedEnglishReturningUser(page)
  await page.route('**/auth/verify-email', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'already_used', message: 'Already used.' }),
  }))
  await page.goto(`/verify-email?token=${'c'.repeat(48)}`)
  await expect(page.getByText('This link has already been used. You can sign in.')).toBeVisible()
})


test('verification result survives a direct-route refresh', async ({ page }) => {
  await seedEnglishReturningUser(page)
  await page.route('**/auth/verify-email', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'verified', message: 'Verified.' }),
  }))
  await page.goto(`/verify-email?token=${'d'.repeat(48)}`)
  await expect(page.getByText('Your email is verified. You can sign in now.')).toBeVisible()
  await page.reload()
  await expect(page.getByText('Your email is verified. You can sign in now.')).toBeVisible()
})


test('missing verification token falls back to login safely', async ({ page }) => {
  await seedEnglishReturningUser(page)
  await page.goto('/verify-email')
  await expect(page.getByRole('tab', { name: 'Login' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Check your email' })).toHaveCount(0)
})


test('backend EMAIL_NOT_VERIFIED response moves password login to verification screen', async ({ page }) => {
  await seedEnglishReturningUser(page)
  await page.route('**/auth/login', (route) => route.fulfill({
    status: 403,
    contentType: 'application/json',
    body: JSON.stringify({
      error: true,
      code: 'EMAIL_NOT_VERIFIED',
      message: 'Email verification is required before signing in.',
    }),
  }))

  await page.goto('/')
  await page.getByLabel('Username or Email').fill('pending@example.com')
  await page.getByLabel('Password').fill('strongpass123')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()

  await expect(page.getByRole('heading', { name: 'Check your email' })).toBeVisible()
  await expect(page.getByText('We sent a verification link to pending@example.com.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Send again' })).toBeVisible()
})


test('registration with delivered email shows check-inbox state and no app session', async ({ page }) => {
  await seedEnglishReturningUser(page)
  await page.route('**/auth/register', (route) => route.fulfill({
    status: 201,
    contentType: 'application/json',
    body: JSON.stringify({
      user: { id: 'user-1', email: 'verify@example.com', name: 'Verification User' },
      email_verification_required: true,
      email_verification_sent: true,
    }),
  }))
  await page.goto('/')
  await fillRegistration(page)
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByText('We sent a verification link to verify@example.com.')).toBeVisible()
  await expect.poll(() => page.evaluate(() => localStorage.getItem('access_token'))).toBeNull()
})


test('registration delivery failure exposes recovery without deleting the account', async ({ page }) => {
  await seedEnglishReturningUser(page)
  await page.route('**/auth/register', (route) => route.fulfill({
    status: 201,
    contentType: 'application/json',
    body: JSON.stringify({
      user: { id: 'user-1', email: 'verify@example.com', name: 'Verification User' },
      email_verification_required: true,
      email_verification_sent: false,
    }),
  }))
  await page.goto('/')
  await fillRegistration(page)
  await page.getByRole('button', { name: 'Create account' }).click()
  await expect(page.getByText(/account was created, but the email could not be sent/i)).toBeVisible()
  await expect(page.getByRole('button', { name: /Send again/ })).toBeVisible()
})


test('resend success starts a visible cooldown', async ({ page }) => {
  await seedEnglishReturningUser(page)
  await page.route('**/auth/login', (route) => route.fulfill({
    status: 403,
    contentType: 'application/json',
    body: JSON.stringify({ error: true, code: 'EMAIL_NOT_VERIFIED', message: 'Verification required.' }),
  }))
  await page.route('**/auth/resend-verification', (route) => {
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ status: 'accepted', message: 'Accepted.' }),
    })
  })
  await page.goto('/')
  await page.getByLabel('Username or Email').fill('pending@example.com')
  await page.getByLabel('Password').fill('strongpass123')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('button', { name: 'Send again' }).click()
  await expect(page.getByText('If this account needs verification, a new email will be sent.')).toBeVisible()
  await expect(page.getByRole('button', { name: /Send again/ })).toBeDisabled()
})


test('resend failure remains recoverable and does not start cooldown', async ({ page }) => {
  await seedEnglishReturningUser(page)
  await page.route('**/auth/login', (route) => route.fulfill({
    status: 403,
    contentType: 'application/json',
    body: JSON.stringify({ error: true, code: 'EMAIL_NOT_VERIFIED', message: 'Verification required.' }),
  }))
  await page.route('**/auth/resend-verification', (route) => route.fulfill({
    status: 500,
    contentType: 'application/json',
    body: JSON.stringify({ error: true, code: 'INTERNAL_SERVER_ERROR', message: 'Failed.' }),
  }))
  await page.goto('/')
  await page.getByLabel('Username or Email').fill('pending@example.com')
  await page.getByLabel('Password').fill('strongpass123')
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.getByRole('button', { name: 'Send again' }).click()
  await expect(page.getByText('Could not create your account.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Send again' })).toBeEnabled()
})


test('Hebrew verification route preserves RTL and translated status', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'he')
    localStorage.setItem('language_selected', 'true')
  })
  await page.route('**/auth/verify-email', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'invalid', message: 'Invalid.' }),
  }))
  await page.goto(`/verify-email?token=${'e'.repeat(48)}`)
  await expect(page.locator('html')).toHaveAttribute('lang', 'he')
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expect(page.getByRole('heading', { name: 'בדקו את תיבת האימייל' })).toBeVisible()
  await expect(page.getByText('קישור האימות אינו תקין.')).toBeVisible()
})


test('first-run language selection preserves the pending verification route', async ({ page }) => {
  await page.route('**/auth/verify-email', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ status: 'verified', message: 'Verified.' }),
  }))
  await page.goto(`/verify-email?token=${'f'.repeat(48)}`)
  await expect(page.getByRole('heading', { name: 'Choose your language' })).toBeVisible()
  await page.getByRole('button', { name: /English/ }).click()
  await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')
  await expect(page.getByText('Your email is verified. You can sign in now.')).toBeVisible()
})
