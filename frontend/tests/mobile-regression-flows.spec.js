import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

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

async function seedAuthenticatedUser(page, user) {
  const storedUser = {
    ...user,
    token: user.token?.includes('.') ? user.token : makeJwtWithSubject(user.id),
  }

  await page.addInitScript((u) => {
    localStorage.setItem('access_token', u.token)
    localStorage.setItem('currentUserId', u.storedId || u.id)
    localStorage.setItem('currentUserName', u.name)
    localStorage.setItem('currentUserEmail', u.email)
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('userCity', 'ירושלים') // E08-02 follow-up fix: account needs a resolved city to reach the map
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  }, storedUser)

  user.token = storedUser.token
}

function makeField(activeGame = null) {
  return {
    id: 'field-1',
    name: 'Central Court',
    lat: 30.9872,
    lng: 34.9314,
    sport_type: 'football',
    approval_status: 'approved',
    active_game: activeGame,
  }
}

function makeActiveGame(createdBy = 'organizer-user', participants = []) {
  return {
    id: 'game-1',
    field_id: 'field-1',
    created_by: createdBy,
    status: 'open',
    sport_type: 'football',
    players_present: 3,
    max_players: 10,
    participants,
  }
}

async function mockNotificationsAndTiles(page) {
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/notifications.*/, (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/notifications/unread-count') {
      return fulfillJson(route, { unread_count: 0 })
    }
    return fulfillJson(route, [])
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
}

async function mockFieldState(page, getField) {
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/fields.*/, (route) => {
    const url = new URL(route.request().url())
    const field = getField()
    if (url.pathname === '/fields/') return fulfillJson(route, [field])
    if (url.pathname === `/fields/${field.id}`) return fulfillJson(route, field)
    return fulfillJson(route, { detail: 'Unhandled field mock' }, 404)
  })
}

const ANDROID_SMALL = { width: 360, height: 640 }
const IPHONE_LARGE = { width: 390, height: 844 }

// ---------------------------------------------------------------------------
// FLOW 1: LOGOUT
// ---------------------------------------------------------------------------

test.describe('Logout flow regression', () => {
  for (const [label, viewport] of [['Android Small (360x640)', ANDROID_SMALL], ['iPhone Large (390x844)', IPHONE_LARGE]]) {
    test(`logout button visible, clickable, and clears auth state on ${label}`, async ({ page }) => {
      test.info().annotations.push({ type: 'viewport', description: `${viewport.width}x${viewport.height}` })
      await page.setViewportSize(viewport)

      const user = { id: 'user-1', email: 'test@example.com', name: 'Test User' }
      await seedAuthenticatedUser(page, user)
      await mockFieldState(page, () => makeField())
      await mockNotificationsAndTiles(page)
      await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/auth\/logout/, (route) =>
        fulfillJson(route, { message: 'Logged out' }),
      )

      await page.goto('/')

      // Verify logout button is visible and meets touch target
      const logoutButton = page.getByRole('button', { name: 'Logout' })
      await expect(logoutButton).toBeVisible()
      const box = await logoutButton.boundingBox()
      expect(box.height).toBeGreaterThanOrEqual(36)
      expect(box.width).toBeGreaterThanOrEqual(36)

      // Click logout
      await page.locator('.location-notice-dismiss').click({ timeout: 2000 }).catch(() => {})
      await logoutButton.click()

      // After logout: should see login screen (auth panel)
      await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible({ timeout: 5000 })

      // Verify auth state is cleared
      const token = await page.evaluate(() => localStorage.getItem('access_token'))
      expect(token).toBeNull()
      const userId = await page.evaluate(() => localStorage.getItem('currentUserId'))
      expect(userId).toBeNull()
    })
  }
})

// ---------------------------------------------------------------------------
// FLOW 2: CREATE GAME FORM
// ---------------------------------------------------------------------------

test.describe('Create game form regression', () => {
  for (const [label, viewport] of [['Android Small (360x640)', ANDROID_SMALL], ['iPhone Large (390x844)', IPHONE_LARGE]]) {
    test(`create game form is fully usable on ${label}`, async ({ page }) => {
      test.info().annotations.push({ type: 'viewport', description: `${viewport.width}x${viewport.height}` })
      await page.setViewportSize(viewport)

      const user = { id: 'organizer-user', email: 'org@example.com', name: 'Organizer' }
      let gameCreated = false

      await seedAuthenticatedUser(page, user)
      await mockFieldState(page, () =>
        makeField(gameCreated ? makeActiveGame(user.id, [{ user_id: user.id, name: user.name }]) : null),
      )
      await mockNotificationsAndTiles(page)
      await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/games\//, (route) => {
        if (route.request().method() === 'POST') {
          gameCreated = true
          return fulfillJson(route, {
            message: 'Game created',
            game: makeActiveGame(user.id),
          })
        }
        return route.continue()
      })

      await page.goto('/')
      await page.locator('.field-marker').first().click()

      // Open the create game dialog
      await page.getByRole('button', { name: 'Open Game' }).click()
      const dialog = page.getByRole('dialog', { name: 'Open Game' })
      await expect(dialog).toBeVisible()

      // Verify all form controls are present and interactive
      // 1. Timing radio buttons (Now / Future)
      const nowRadio = dialog.getByRole('radio', { name: 'Game now' })
      const futureRadio = dialog.getByRole('radio', { name: 'Future game' })
      await expect(nowRadio).toBeVisible()
      await expect(futureRadio).toBeVisible()
      await expect(nowRadio).toBeChecked()

      // 2. Sport type select
      const sportSelect = dialog.locator('select')
      await expect(sportSelect).toBeVisible()
      const sportValue = await sportSelect.inputValue()
      expect(sportValue).toBe('football')

      // 3. Players present input
      const playersInput = dialog.locator('input[type="number"]').first()
      await expect(playersInput).toBeVisible()

      // 4. Max players input
      const maxPlayersInput = dialog.locator('input[type="number"]').nth(1)
      await expect(maxPlayersInput).toBeVisible()

      // 5. Age note input
      const ageInput = dialog.locator('input[type="text"]')
      await expect(ageInput).toBeVisible()

      // 6. Submit button is reachable (scroll if needed)
      const submitButton = dialog.getByRole('button', { name: 'Open Game' })
      await submitButton.scrollIntoViewIfNeeded()
      await expect(submitButton).toBeVisible()
      const submitBox = await submitButton.boundingBox()
      expect(submitBox.y + submitBox.height).toBeLessThanOrEqual(viewport.height + 1)

      // 7. Test future scheduling fields appear
      await futureRadio.click()
      await expect(dialog.locator('input[type="date"]')).toBeVisible()
      await expect(dialog.locator('input[type="time"]')).toBeVisible()
      await nowRadio.click()

      // 8. Fill form and submit
      await playersInput.fill('2')
      await maxPlayersInput.fill('8')
      await ageInput.fill('18+')
      await submitButton.click()

      // 9. After submit: dialog closes, active game appears
      await expect(dialog).not.toBeVisible({ timeout: 5000 })
      await expect(page.getByRole('button', { name: 'Close game' })).toBeVisible({ timeout: 5000 })
    })
  }
})

// ---------------------------------------------------------------------------
// FLOW 3: EXTEND GAME
// ---------------------------------------------------------------------------

test.describe('Extend game flow regression', () => {
  for (const [label, viewport] of [['Android Small (360x640)', ANDROID_SMALL], ['iPhone Large (390x844)', IPHONE_LARGE]]) {
    test(`extend game button visible and functional for organizer on ${label}`, async ({ page }) => {
      test.info().annotations.push({ type: 'viewport', description: `${viewport.width}x${viewport.height}` })
      await page.setViewportSize(viewport)

      const user = { id: 'organizer-user', email: 'org@example.com', name: 'Organizer' }
      let extendRequest = null

      await seedAuthenticatedUser(page, user)
      await mockFieldState(page, () => makeField(makeActiveGame(user.id, [{ user_id: user.id, name: user.name }])))
      await mockNotificationsAndTiles(page)
      await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/games\/game-1\/extend/, (route) => {
        extendRequest = route.request()
        return fulfillJson(route, {
          message: 'Game extended',
          game: { ...makeActiveGame(user.id), expires_at: '2099-12-31T23:59:59Z' },
        })
      })

      await page.goto('/')
      await page.locator('.field-marker').first().click()

      // Verify extend button is visible for organizer
      const extendButton = page.getByRole('button', { name: 'Extra round' })
      await expect(extendButton).toBeVisible()
      const extendBox = await extendButton.boundingBox()
      expect(extendBox.height).toBeGreaterThanOrEqual(36)

      // Click extend
      await extendButton.click()

      // Verify the extend API was called
      await expect.poll(() => extendRequest?.method()).toBe('POST')
      expect(extendRequest.url()).toContain('/games/game-1/extend')
      expect(extendRequest.headers().authorization).toContain('Bearer ')
    })

    test(`extend game button not visible for non-organizer on ${label}`, async ({ page }) => {
      test.info().annotations.push({ type: 'viewport', description: `${viewport.width}x${viewport.height}` })
      await page.setViewportSize(viewport)

      const user = { id: 'other-user', email: 'other@example.com', name: 'Other User' }

      await seedAuthenticatedUser(page, user)
      await mockFieldState(page, () =>
        makeField(makeActiveGame('organizer-user', [{ user_id: user.id, name: user.name }])),
      )
      await mockNotificationsAndTiles(page)

      await page.goto('/')
      await page.locator('.field-marker').first().click()

      // Non-organizer should see the game but NOT the extend button
      await expect(page.getByText('Active game: open')).toBeVisible()
      await expect(page.getByRole('button', { name: 'Extra round' })).toHaveCount(0)
    })
  }
})
