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
    localStorage.setItem('language_selected', 'true')
  }, { ...user, token: makeJwtWithSubject(user.id), language })
}

async function mockMapRequests(page) {
  await page.route(/\/fields\/?(\?.*)?$/, (route) => fulfillJson(route, []))
  await page.route(/\/notifications(\/.*)?(\?.*)?$/, (route) => {
    const url = new URL(route.request().url())

    if (url.pathname === '/notifications/unread-count') {
      return fulfillJson(route, { unread_count: 0 })
    }

    if (url.pathname === '/notifications/preferences') {
      return fulfillJson(route, [])
    }

    return fulfillJson(route, [])
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
}

test('first launch requires language choice once and persists it', async ({ page }) => {
  await page.goto('/')

  await expect(page.getByRole('heading', { name: 'Choose your language' })).toBeVisible()
  await expect(page.getByRole('button', { name: /English/ })).toBeVisible()

  await page.getByRole('button', { name: /English/ }).click()

  await expect(page.locator('html')).toHaveAttribute('lang', 'en')
  await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')
  await expect(page.getByRole('button', { name: 'Login' })).toBeVisible()
  await expect(page.getByLabel('Language')).toHaveCount(0)
  await expect.poll(() => page.evaluate(() => localStorage.getItem('app_language'))).toBe('en')
  await expect.poll(() => page.evaluate(() => localStorage.getItem('language_selected'))).toBe('true')

  await page.reload()

  await expect(page.getByRole('heading', { name: 'Choose your language' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Login' })).toBeVisible()
})

test('settings language selector updates direction and saves preference', async ({ page }) => {
  await seedAuthenticatedUser(page, 'he')
  await mockMapRequests(page)

  await page.goto('/')

  await expect(page.locator('html')).toHaveAttribute('lang', 'he')
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl')
  await expect(page.getByRole('button', { name: 'התראות', exact: true })).toBeVisible()
  await expect(page.getByLabel('שפה')).toHaveCount(0)

  await page.getByRole('button', { name: 'העדפות התראות' }).click()
  await expect(page.getByRole('heading', { name: 'העדפות התראות' })).toBeVisible()
  await expect(page.getByText('שפה נוכחית: עברית')).toBeVisible()

  await page.getByLabel('שפה').selectOption('en')

  await expect(page.locator('html')).toHaveAttribute('lang', 'en')
  await expect(page.locator('html')).toHaveAttribute('dir', 'ltr')
  await expect(page.getByRole('heading', { name: 'Notification Preferences' })).toBeVisible()
  await expect(page.getByText('Current language: English')).toBeVisible()
  await expect.poll(() => page.evaluate(() => localStorage.getItem('app_language'))).toBe('en')
  await expect.poll(() => page.evaluate(() => localStorage.getItem('language_selected'))).toBe('true')
})
