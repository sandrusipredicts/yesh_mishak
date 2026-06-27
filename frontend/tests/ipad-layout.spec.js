import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

const IPAD_LANDSCAPE = { width: 1024, height: 768 }
const IPAD_AIR_LANDSCAPE = { width: 1180, height: 820 }
const IPAD_PORTRAIT = { width: 768, height: 1024 }
const IPAD_PRO_LANDSCAPE = { width: 1366, height: 1024 }
const PHONE_PORTRAIT = { width: 390, height: 844 }

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

async function expectModalCloseToWork(page, modalSelector) {
  const modal = page.locator(modalSelector)
  const closeButton = modal.locator('.modal-close-button')
  await expect(closeButton).toBeVisible()

  const hitTarget = await closeButton.evaluate((button) => {
    const rect = button.getBoundingClientRect()
    const element = document.elementFromPoint(
      rect.left + rect.width / 2,
      rect.top + rect.height / 2,
    )
    return {
      isCloseButton: element === button || button.contains(element),
      blockedByToolbar: Boolean(element?.closest('.auth-toolbar')),
    }
  })

  expect(hitTarget).toEqual({
    isCloseButton: true,
    blockedByToolbar: false,
  })

  await closeButton.click()
  await expect(modal).toBeHidden()
}

test.describe('IPAD-001: Modal close button not intercepted by auth toolbar', () => {
  for (const [label, viewport] of [
    ['iPad landscape (1024x768)', IPAD_LANDSCAPE],
    ['iPad Air landscape (1180x820)', IPAD_AIR_LANDSCAPE],
  ]) {
    test(`notifications modal close button is clickable on ${label}`, async ({ browser }) => {
      const context = await browser.newContext({ viewport })
      const page = await context.newPage()
      await seedAuth(page, 'en')
      await mockRoutes(page)
      await page.goto('/')
      await page.waitForSelector('.auth-toolbar')

      const prefsButton = page.locator('.floating-button.preferences')
      await prefsButton.click()
      await page.waitForSelector('.notifications-modal')

      await expectModalCloseToWork(page, '.notifications-modal')

      await context.close()
    })

    test(`add field modal close button is clickable on ${label}`, async ({ browser }) => {
      const context = await browser.newContext({ viewport })
      const page = await context.newPage()
      await seedAuth(page, 'en')
      await mockRoutes(page)
      await page.goto('/')
      await page.waitForSelector('.auth-toolbar')

      const addButton = page.locator('.floating-button.bottom')
      await addButton.click()
      await page.waitForSelector('.add-field-modal')

      await expectModalCloseToWork(page, '.add-field-modal')

      await context.close()
    })
  }
})

test.describe('IPAD-003: AddFieldModal submit button reachable on iPad', () => {
  for (const [label, viewport] of [
    ['iPad portrait (768x1024)', IPAD_PORTRAIT],
    ['iPad landscape (1024x768)', IPAD_LANDSCAPE],
    ['iPad Air landscape (1180x820)', IPAD_AIR_LANDSCAPE],
    ['iPad Pro landscape (1366x1024)', IPAD_PRO_LANDSCAPE],
  ]) {
    test(`add field submit is reachable via scroll on ${label}`, async ({ browser }) => {
      const context = await browser.newContext({ viewport })
      const page = await context.newPage()
      await seedAuth(page, 'en')
      await mockRoutes(page)
      await page.goto('/')
      await page.waitForSelector('.auth-toolbar')

      const addButton = page.locator('.floating-button.bottom')
      await addButton.click()
      await page.waitForSelector('.add-field-modal')

      const submitButton = page.locator('.add-field-modal button[type="submit"]')
      await submitButton.scrollIntoViewIfNeeded()
      await expect(submitButton).toBeVisible()

      await context.close()
    })
  }
})

test.describe('IPAD-003/IPAD-004: AddFieldModal tablet landscape layout', () => {
  for (const [label, viewport] of [
    ['iPad landscape (1024x768)', IPAD_LANDSCAPE],
    ['iPad Air landscape (1180x820)', IPAD_AIR_LANDSCAPE],
  ]) {
    test(`critical controls are unclipped on ${label}`, async ({ browser }) => {
      const context = await browser.newContext({ viewport })
      const page = await context.newPage()
      await seedAuth(page, 'en')
      await mockRoutes(page)
      await page.goto('/')
      await page.waitForSelector('.auth-toolbar')

      await page.locator('.floating-button.bottom').click()

      const modal = page.locator('.add-field-modal')
      const map = modal.locator('.location-picker-map')
      const actions = modal.locator('.field-report-actions')
      const cancelButton = actions.locator('button[type="button"]')
      const submitButton = actions.locator('button[type="submit"]')

      await expect(modal).toBeVisible()
      await expect(map).toBeVisible()
      await expect(actions).toBeVisible()
      await expect(cancelButton).toBeVisible()
      await expect(submitButton).toBeVisible()

      const layout = await modal.evaluate((modalElement) => {
        const mapElement = modalElement.querySelector('.location-picker-map')
        const actionsElement = modalElement.querySelector('.field-report-actions')
        const cancelElement = actionsElement.querySelector('button[type="button"]')
        const submitElement = actionsElement.querySelector('button[type="submit"]')
        const modalRect = modalElement.getBoundingClientRect()
        const mapRect = mapElement.getBoundingClientRect()
        const actionsRect = actionsElement.getBoundingClientRect()
        const cancelRect = cancelElement.getBoundingClientRect()
        const submitRect = submitElement.getBoundingClientRect()

        const insideViewport = (rect) => (
          rect.top >= 0
          && rect.left >= 0
          && rect.bottom <= window.innerHeight
          && rect.right <= window.innerWidth
        )
        const insideModal = (rect) => (
          rect.top >= modalRect.top
          && rect.left >= modalRect.left
          && rect.bottom <= modalRect.bottom
          && rect.right <= modalRect.right
        )

        return {
          mapHeight: mapRect.height,
          actionsInsideViewport: insideViewport(actionsRect),
          cancelInsideModal: insideModal(cancelRect),
          submitInsideModal: insideModal(submitRect),
          noHorizontalOverflow: modalElement.scrollWidth <= modalElement.clientWidth,
        }
      })

      expect(layout.mapHeight).toBeGreaterThan(0)
      expect(layout.mapHeight).toBeLessThanOrEqual(160)
      expect(layout.actionsInsideViewport).toBe(true)
      expect(layout.cancelInsideModal).toBe(true)
      expect(layout.submitInsideModal).toBe(true)
      expect(layout.noHorizontalOverflow).toBe(true)

      await context.close()
    })
  }
})

test.describe('Phone regression coverage', () => {
  test('AddFieldModal retains its compact phone layout', async ({ browser }) => {
    const context = await browser.newContext({ viewport: PHONE_PORTRAIT })
    const page = await context.newPage()
    await seedAuth(page, 'en')
    await mockRoutes(page)
    await page.goto('/')
    await page.waitForSelector('.auth-toolbar')

    await page.locator('.floating-button.bottom').click()

    const modal = page.locator('.add-field-modal')
    const map = modal.locator('.location-picker-map')
    const actions = modal.locator('.field-report-actions')
    const submitButton = actions.locator('button[type="submit"]')

    await expect(modal).toBeVisible()
    await expect(map).toBeVisible()

    const phoneLayout = await modal.evaluate((modalElement) => {
      const mapElement = modalElement.querySelector('.location-picker-map')
      const actionsElement = modalElement.querySelector('.field-report-actions')
      return {
        mapHeight: mapElement.getBoundingClientRect().height,
        actionColumns: getComputedStyle(actionsElement).gridTemplateColumns.split(' ').length,
      }
    })

    expect(phoneLayout.mapHeight).toBeLessThanOrEqual(160)
    expect(phoneLayout.actionColumns).toBe(1)

    await submitButton.scrollIntoViewIfNeeded()
    await expect(submitButton).toBeVisible()

    await context.close()
  })
})

test.describe('IPAD-002: Register form usable on tablet landscape', () => {
  test('register submit is reachable on iPad landscape (1024x768)', async ({ browser }) => {
    const context = await browser.newContext({ viewport: IPAD_LANDSCAPE })
    const page = await context.newPage()
    await page.addInitScript(() => {
      localStorage.setItem('language_selected', 'true')
      localStorage.setItem('app_language', 'en')
    })
    await page.goto('/')

    const registerTab = page.locator('.auth-mode-tabs button').nth(1)
    await registerTab.click()

    const submitButton = page.locator('button.auth-submit')
    await expect(submitButton).toBeAttached()
    await submitButton.scrollIntoViewIfNeeded()
    await expect(submitButton).toBeVisible()

    await context.close()
  })
})
