import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

const user = {
  id: 'regular-user-1',
  email: 'user@example.com',
  name: 'Regular User',
}

function fulfillJson(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
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

async function seedAuthenticatedUser(page, language = 'he') {
  await page.addInitScript((storedUser) => {
    localStorage.setItem('access_token', storedUser.token)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('app_language', storedUser.language)
  }, { ...user, token: makeJwtWithSubject(user.id), language })
}

async function mockMapRequests(page) {
  await page.route(/\/fields\/?(\?.*)?$/, (route) => fulfillJson(route, []))
  await page.route(/\/notifications(\/.*)?(\?.*)?$/, (route) => {
    const url = new URL(route.request().url())

    if (url.pathname === '/notifications/unread-count') {
      return fulfillJson(route, { unread_count: 0 })
    }

    return fulfillJson(route, [])
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
}

test('language switcher persists choice and flips document direction', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'he')
  })

  await page.goto('/')

  await expect(page.locator('html')).toHaveAttribute('lang', 'he')
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expect(page.getByLabel('שיטת התחברות').getByRole('button', { name: 'התחברות' })).toBeVisible()

  await page.getByLabel('שפה').selectOption('en')

  await expect(page.locator('html')).toHaveAttribute('lang', 'en')
  await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')
  await expect(page.getByRole('button', { name: 'Login' })).toBeVisible()
  await expect.poll(() => page.evaluate(() => localStorage.getItem('app_language'))).toBe('en')
})

test('authenticated map shell renders in persisted Hebrew RTL', async ({ page }) => {
  await seedAuthenticatedUser(page, 'he')
  await mockMapRequests(page)

  await page.goto('/')

  await expect(page.locator('html')).toHaveAttribute('lang', 'he')
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expect(page.getByRole('button', { name: 'התראות', exact: true })).toBeVisible()
  await expect(page.getByLabel('הוספת מגרש')).toBeVisible()
  await expect(page.getByLabel('שפה').first()).toBeVisible()
})
