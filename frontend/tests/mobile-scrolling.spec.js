import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

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

function makeJwtWithSubject(userId) {
  return [
    encodeBase64Url(JSON.stringify({ alg: 'none', typ: 'JWT' })),
    encodeBase64Url(JSON.stringify({ sub: userId })),
    'signature',
  ].join('.')
}

async function seedAnonymousUser(page) {
  await page.addInitScript(() => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('currentUserId')
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  })
}

async function seedAuthenticatedUser(page) {
  await page.addInitScript((storedUser) => {
    localStorage.setItem('access_token', storedUser.token)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  }, { ...user, token: makeJwtWithSubject(user.id) })
}

async function seedOnboardingNotDone(page) {
  await page.addInitScript((storedUser) => {
    localStorage.setItem('access_token', storedUser.token)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.removeItem('onboarding_done')
    localStorage.removeItem('userCity')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  }, { ...user, token: makeJwtWithSubject(user.id) })
}

async function mockSharedRequests(page) {
  await page.route(/\/fields\/?(\?.*)?$/, (route) => {
    return fulfillJson(route, [])
  })
  await page.route(/\/notifications(\/.*)?(\?.*)?$/, (route) => {
    return fulfillJson(route, [])
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
}

test.describe('Mobile Scrolling Behavior', () => {
  test('Login/Register on short viewport allows vertical scrolling and reachability', async ({ page }) => {
    await seedAnonymousUser(page)
    await mockSharedRequests(page)
    
    // Set a very short mobile viewport
    await page.setViewportSize({ width: 320, height: 400 })
    await page.goto('/')

    // Switch to Register Mode (more fields)
    await page.getByRole('button', { name: 'Register' }).click()

    const submitBtn = page.getByRole('button', { name: 'Create Account' })
    await expect(submitBtn).toBeAttached()
    
    // Scroll the submit button into view to confirm it's reachable and visible
    await submitBtn.scrollIntoViewIfNeeded()
    await expect(submitBtn).toBeInViewport()

    // Verify top layout flex properties
    const pageWrapper = page.locator('.login-page')
    await expect(pageWrapper).toHaveCSS('display', 'flex')
    await expect(pageWrapper).toHaveCSS('flex-direction', 'column')
  })

  test('Onboarding page on short viewport scrolls and CTA is reachable', async ({ page }) => {
    await seedOnboardingNotDone(page)
    await mockSharedRequests(page)

    await page.setViewportSize({ width: 320, height: 400 })
    await page.goto('/')

    const letsGoBtn = page.getByRole('button', { name: "Let's Go" })
    await expect(letsGoBtn).toBeAttached()

    // Scroll to CTA to confirm scrollability
    await letsGoBtn.scrollIntoViewIfNeeded()
    await expect(letsGoBtn).toBeInViewport()

    const pageWrapper = page.locator('.onboarding-page')
    await expect(pageWrapper).toHaveCSS('display', 'flex')
    await expect(pageWrapper).toHaveCSS('flex-direction', 'column')
  })

  test('Onboarding city suggestions dropdown has mobile height constraint', async ({ page }) => {
    await seedOnboardingNotDone(page)
    await mockSharedRequests(page)

    await page.setViewportSize({ width: 360, height: 640 })
    await page.goto('/')

    // Open suggestions by typing Hebrew character to match Hebrew cities
    const cityInput = page.locator('#city-input')
    await cityInput.fill('א')
    
    const suggestionsList = page.locator('#city-suggestions')
    await expect(suggestionsList).toBeVisible()

    // Verify max-height uses min(220px, 40dvh)
    const maxHeight = await suggestionsList.evaluate((el) => window.getComputedStyle(el).maxHeight)
    // 40dvh of 640px is 256px, min(220px, 256px) is 220px
    expect(maxHeight).toBe('220px')
  })

  test('Overscroll containment is applied to overlay scrollable panels and modals', async ({ page }) => {
    await seedAuthenticatedUser(page)
    await mockSharedRequests(page)
    await page.setViewportSize({ width: 375, height: 667 })
    await page.goto('/')

    // Add Field Modal
    await page.getByRole('button', { name: 'Add field' }).click()
    const addFieldModal = page.locator('.add-field-modal')
    await expect(addFieldModal).toBeVisible()
    await expect(addFieldModal).toHaveCSS('overscroll-behavior', 'contain')
  })

  test('Nested list scrolls expand on short landscape viewports', async ({ page }) => {
    await seedAuthenticatedUser(page)
    await mockSharedRequests(page)

    // Simulate short landscape view
    await page.setViewportSize({ width: 667, height: 375 })
    await page.goto('/')

    // Open notification preferences modal (which has field-selection-list)
    await page.getByRole('button', { name: 'Preferences' }).click()
    const selectionList = page.locator('.field-selection-list')
    await expect(selectionList).toBeAttached()

    // Under max-height: 520px, .field-selection-list should have max-height: none and overflow: visible
    const maxHeight = await selectionList.evaluate((el) => window.getComputedStyle(el).maxHeight)
    const overflow = await selectionList.evaluate((el) => window.getComputedStyle(el).overflow)

    expect(maxHeight).toBe('none')
    expect(overflow).toBe('visible')
  })

  test('iPhone SE (320px) viewport does not create horizontal page overflow', async ({ page }) => {
    await seedAuthenticatedUser(page)
    await mockSharedRequests(page)

    await page.setViewportSize({ width: 320, height: 568 })
    await page.goto('/')

    // Verify horizontal dimensions of the document
    const dimensions = await page.evaluate(() => {
      return {
        viewportWidth: window.innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
      }
    })

    expect(dimensions.documentWidth).toBeLessThanOrEqual(dimensions.viewportWidth)
    expect(dimensions.bodyWidth).toBeLessThanOrEqual(dimensions.viewportWidth)
  })
})
