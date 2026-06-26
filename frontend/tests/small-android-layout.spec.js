import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

const SMALL_ANDROID = { width: 360, height: 640 }
const SMALL_ANDROID_LANDSCAPE = { width: 667, height: 375 }

const user = {
  id: 'current-user',
  email: 'current@example.com',
  name: 'Current User',
  role: 'user',
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

function makeJwt(userId) {
  return [
    encodeBase64Url(JSON.stringify({ alg: 'none', typ: 'JWT' })),
    encodeBase64Url(JSON.stringify({ sub: userId })),
    'signature',
  ].join('.')
}

async function seedAuth(page, lang = 'he') {
  await page.addInitScript(({ storedUser, currentLang }) => {
    localStorage.setItem('access_token', storedUser.token)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('app_language', currentLang)
    localStorage.setItem('language_selected', 'true')
  }, { storedUser: { ...user, token: makeJwt(user.id) }, currentLang: lang })
}

async function mockRoutes(page) {
  await page.route(/\/fields\/?(\?.*)?$/, (route) => fulfillJson(route, []))
  await page.route(/\/fields\/([a-zA-Z0-9_-]+)(\?.*)?$/, (route) => fulfillJson(route, {}))
  await page.route(/\/notifications(\/.*)?(\?.*)?$/, (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.includes('unread-count')) {
      return fulfillJson(route, { unread_count: 0 })
    }
    return fulfillJson(route, [])
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
}

test.describe('Small Android Layout (360x640)', () => {
  test('auth toolbar buttons do not wrap to multiple lines', async ({ browser }) => {
    const context = await browser.newContext({ viewport: SMALL_ANDROID })
    const page = await context.newPage()
    await seedAuth(page)
    await mockRoutes(page)
    await page.goto('/')
    await page.waitForSelector('.auth-toolbar')

    const buttons = page.locator('.auth-toolbar button')
    const count = await buttons.count()
    expect(count).toBeGreaterThanOrEqual(2)

    for (let i = 0; i < count; i++) {
      const height = await buttons.nth(i).evaluate((el) => el.getBoundingClientRect().height)
      expect(height).toBeLessThanOrEqual(48)
    }

    const toolbarOverflow = await page.evaluate(() =>
      document.documentElement.scrollWidth > document.documentElement.clientWidth,
    )
    expect(toolbarOverflow).toBe(false)

    await context.close()
  })

  test('no horizontal overflow on map page', async ({ browser }) => {
    const context = await browser.newContext({ viewport: SMALL_ANDROID })
    const page = await context.newPage()
    await seedAuth(page)
    await mockRoutes(page)
    await page.goto('/')
    await page.waitForSelector('.auth-toolbar')

    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth > document.documentElement.clientWidth,
    )
    expect(overflow).toBe(false)

    await context.close()
  })

  test('register form submit is reachable after scrolling', async ({ browser }) => {
    const context = await browser.newContext({ viewport: SMALL_ANDROID })
    const page = await context.newPage()
    await page.addInitScript(() => {
      localStorage.setItem('language_selected', 'true')
      localStorage.setItem('app_language', 'he')
    })
    await page.goto('/')

    const registerTab = page.locator('button', { hasText: 'הרשמה' }).first()
    await registerTab.click()

    const submitButton = page.locator('button.auth-submit')
    await expect(submitButton).toBeAttached()
    await submitButton.scrollIntoViewIfNeeded()
    await expect(submitButton).toBeVisible()

    await context.close()
  })

  test('notifications modal save button is visible via sticky positioning', async ({ browser }) => {
    const context = await browser.newContext({ viewport: SMALL_ANDROID })
    const page = await context.newPage()
    await seedAuth(page)
    await mockRoutes(page)
    await page.goto('/')
    await page.waitForSelector('.auth-toolbar')

    const prefsButton = page.locator('.floating-button.preferences')
    await prefsButton.click()
    await page.waitForSelector('.notifications-modal')

    const saveButton = page.locator('.notifications-modal .primary-panel-button')
    await expect(saveButton).toBeVisible()

    await context.close()
  })

  test('add field modal map height is reduced and submit reachable', async ({ browser }) => {
    const context = await browser.newContext({ viewport: SMALL_ANDROID })
    const page = await context.newPage()
    await seedAuth(page)
    await mockRoutes(page)
    await page.goto('/')
    await page.waitForSelector('.auth-toolbar')

    const addButton = page.locator('.floating-button.bottom')
    await addButton.click()
    await page.waitForSelector('.add-field-modal')

    const mapEl = page.locator('.location-picker-map')
    const mapHeight = await mapEl.evaluate((el) => el.getBoundingClientRect().height)
    expect(mapHeight).toBeLessThanOrEqual(170)

    const submitButton = page.locator('.add-field-modal button[type="submit"]')
    await submitButton.scrollIntoViewIfNeeded()
    await expect(submitButton).toBeVisible()

    await context.close()
  })
})

test.describe('Small Android Landscape Smoke (667x375)', () => {
  test('map loads and toolbar visible in landscape', async ({ browser }) => {
    const context = await browser.newContext({ viewport: SMALL_ANDROID_LANDSCAPE })
    const page = await context.newPage()
    await seedAuth(page)
    await mockRoutes(page)
    await page.goto('/')
    await page.waitForSelector('.auth-toolbar')

    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth > document.documentElement.clientWidth,
    )
    expect(overflow).toBe(false)

    await expect(page.locator('.auth-toolbar')).toBeVisible()
    await expect(page.locator('.floating-button.top')).toBeVisible()

    await context.close()
  })

  test('login form is usable in landscape', async ({ browser }) => {
    const context = await browser.newContext({ viewport: SMALL_ANDROID_LANDSCAPE })
    const page = await context.newPage()
    await page.addInitScript(() => {
      localStorage.setItem('language_selected', 'true')
      localStorage.setItem('app_language', 'he')
    })
    await page.goto('/')

    const submitButton = page.locator('button.auth-submit')
    await submitButton.scrollIntoViewIfNeeded()
    await expect(submitButton).toBeVisible()

    await context.close()
  })
})
