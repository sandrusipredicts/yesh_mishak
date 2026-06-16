import { expect, test } from '@playwright/test'

function fulfillJson(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function seedAuthenticatedUser(page, user) {
  await page.addInitScript((storedUser) => {
    localStorage.setItem('access_token', storedUser.token)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.setItem('onboarding_done', 'true')
  }, user)
}

async function mockSharedRequests(page, fields) {
  await page.route('http://localhost:8001/fields**', (route) => fulfillJson(route, fields))
  await page.route('http://localhost:8001/notifications**', (route) => {
    const url = new URL(route.request().url())

    if (url.pathname === '/notifications/unread-count') {
      return fulfillJson(route, { unread_count: 0 })
    }

    return fulfillJson(route, [])
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
}

function makeFieldWithActiveGame(createdBy) {
  return [
    {
      id: 'field-1',
      name: 'Central Court',
      lat: 30.9872,
      lng: 34.9314,
      approval_status: 'approved',
      active_game: {
        id: 'game-1',
        field_id: 'field-1',
        created_by: createdBy,
        status: 'open',
        sport_type: 'football',
        players_present: 3,
        max_players: 10,
        participants: [],
      },
    },
  ]
}

test('non-organizer does not see the close game button', async ({ page }) => {
  await seedAuthenticatedUser(page, {
    id: 'current-user',
    email: 'current@example.com',
    name: 'Current User',
    token: 'current-token',
  })
  await mockSharedRequests(page, makeFieldWithActiveGame('organizer-user'))

  await page.goto('/')
  await page.locator('.field-marker').first().click()

  await expect(page.getByRole('button', { name: 'Close game' })).toHaveCount(0)
})

test('organizer close game request sends authorization and no body', async ({ page }) => {
  const user = {
    id: 'organizer-user',
    email: 'organizer@example.com',
    name: 'Organizer User',
    token: 'organizer-token',
  }
  let closeRequest

  await seedAuthenticatedUser(page, user)
  await mockSharedRequests(page, makeFieldWithActiveGame(user.id))
  await page.route('http://localhost:8001/games/game-1/close', (route) => {
    closeRequest = route.request()
    return fulfillJson(route, {
      message: 'Game closed',
      game: { id: 'game-1', status: 'finished' },
    })
  })

  await page.goto('/')
  await page.locator('.field-marker').first().click()
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Close game' }).click()

  await expect.poll(() => closeRequest?.method()).toBe('POST')
  expect(closeRequest.headers().authorization).toBe('Bearer organizer-token')
  expect(closeRequest.postData() ?? '').toBe('')
})
