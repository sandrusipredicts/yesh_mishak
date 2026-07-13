import { expect, test } from '@playwright/test'

const user = {
  id: '31b6ac09-74f0-49f4-8916-c216842a3498',
  name: 'Phone User',
  email: 'phone-user@example.com',
}

function makeJwt(subject = user.id) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url')
  return `${encode({ alg: 'none' })}.${encode({ sub: subject })}.signature`
}

async function prepareAuthenticatedApp(page) {
  const token = makeJwt()
  await page.addInitScript(({ storedToken, storedUser }) => {
    localStorage.setItem('language_selected', 'true')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('access_token', storedToken)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
  }, { storedToken: token, storedUser: user })

  await page.route('**/fields/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/games/active/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/games/upcoming/**', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route('**/notifications/unread-count', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '{"count":0}' }))

  return token
}

test('authenticated user can complete phone verification without persisting OTP', async ({ page }) => {
  const token = await prepareAuthenticatedApp(page)
  const requests = []

  await page.route('**/auth/phone/start', async (route) => {
    requests.push({
      url: route.request().url(),
      authorization: route.request().headers().authorization,
      body: route.request().postDataJSON(),
    })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        message: 'If this phone number can be verified, a code will be sent.',
        cooldown_seconds: 60,
      }),
    })
  })
  await page.route('**/auth/phone/verify', async (route) => {
    requests.push({
      url: route.request().url(),
      authorization: route.request().headers().authorization,
      body: route.request().postDataJSON(),
    })
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        message: 'Phone number verified.',
        phone_number: '+972501234567',
      }),
    })
  })

  await page.goto('/')
  await page.getByRole('button', { name: 'Verify phone' }).click()
  await page.getByRole('textbox', { name: 'Phone number' }).fill('0501234567')
  await page.getByRole('button', { name: 'Send code', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('code was sent')

  await page.getByLabel('Verification code').fill('123456')
  await page.getByRole('button', { name: 'Verify', exact: true }).click()
  await expect(page.getByRole('status')).toContainText('Phone number verified')
  await expect(page.getByRole('button', { name: 'Phone verified' })).toBeDisabled()

  expect(requests).toHaveLength(2)
  expect(requests.every((request) => request.authorization === `Bearer ${token}`)).toBe(true)
  expect(requests[0].body).toEqual({ phone_number: '0501234567' })
  expect(requests[1].body).toEqual({ phone_number: '0501234567', otp: '123456' })

  const storedSensitiveValues = await page.evaluate(() => ({
    localStorageValues: Object.values(localStorage),
    sessionStorageValues: Object.values(sessionStorage),
  }))
  expect(storedSensitiveValues.localStorageValues).not.toContain('123456')
  expect(storedSensitiveValues.sessionStorageValues).not.toContain('123456')
})

test('phone verification surfaces provider failures without logging full phone', async ({ page }) => {
  await prepareAuthenticatedApp(page)
  const consoleMessages = []
  page.on('console', (message) => consoleMessages.push(message.text()))

  await page.route('**/auth/phone/start', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({
        error: true,
        code: 'PHONE_PROVIDER_UNAVAILABLE',
        message: 'Phone verification is temporarily unavailable. Please try again later.',
      }),
    }))

  await page.goto('/')
  await page.getByRole('button', { name: 'Verify phone' }).click()
  await page.getByRole('textbox', { name: 'Phone number' }).fill('+972501234567')
  await page.getByRole('button', { name: 'Send code', exact: true }).click()

  await expect(page.getByRole('alert')).toContainText('temporarily unavailable')
  expect(consoleMessages.join('\n')).not.toContain('+972501234567')
})
