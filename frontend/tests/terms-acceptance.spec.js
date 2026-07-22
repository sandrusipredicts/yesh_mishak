import { expect, test } from '@playwright/test'

const USER_ID = '11111111-1111-4111-8111-111111111111'

function makeJwt(subject = USER_ID) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url')
  return `${encode({ alg: 'none' })}.${encode({ sub: subject })}.signature`
}

test('fresh authenticated user must accept the community terms before entering the app', async ({ page }) => {
  await page.addInitScript(({ token }) => {
    localStorage.setItem('language_selected', 'true')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('userCity', 'ירושלים')
    localStorage.setItem('access_token', token)
    localStorage.setItem('currentUserId', '11111111-1111-4111-8111-111111111111')
    localStorage.setItem('currentUserName', 'New User')
    localStorage.setItem('currentUserEmail', 'new@example.com')
    localStorage.setItem('currentUserTermsAccepted', 'false')
  }, { token: makeJwt() })

  let acceptanceRequests = 0
  await page.route('**/auth/accept-terms', (route) => {
    acceptanceRequests += 1
    return route.fulfill({ status: 200, contentType: 'application/json', body: '{"message":"Terms accepted"}' })
  })
  await page.route('**/games/me', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: '{"active_games":[],"upcoming_games":[],"past_games":[],"cancelled_games":[]}',
    }))
  await page.route(/\/fields\/?(\?.*)?$/, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))
  await page.route(/\/notifications(?:\/|\?|$)/, (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }))

  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Community terms' })).toBeVisible()
  const continueButton = page.getByRole('button', { name: 'Accept and continue' })
  await expect(continueButton).toBeDisabled()
  await page.getByRole('checkbox').check()
  await continueButton.click()

  expect(acceptanceRequests).toBe(1)
  await expect(page.getByRole('heading', { name: 'Community terms' })).toHaveCount(0)
  await expect(page.evaluate(() => localStorage.getItem('currentUserTermsAccepted'))).resolves.toBe('true')
})

test('legacy authenticated session without an acceptance record is gated', async ({ page }) => {
  await page.addInitScript(({ token }) => {
    localStorage.setItem('language_selected', 'true')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('userCity', 'ירושלים')
    localStorage.setItem('access_token', token)
    localStorage.setItem('currentUserId', '11111111-1111-4111-8111-111111111111')
    localStorage.setItem('currentUserName', 'Existing User')
    localStorage.setItem('currentUserEmail', 'existing@example.com')
    localStorage.removeItem('currentUserTermsAccepted')
  }, { token: makeJwt() })

  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Community terms' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Accept and continue' })).toBeDisabled()
})
