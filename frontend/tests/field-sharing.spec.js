import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

const user = {
  id: 'regular-user-1',
  email: 'user@example.com',
  name: 'Regular User',
  role: 'user',
}

const FIELD_ID = '77777777-7777-4777-8777-777777777777'

const approvedField = {
  id: FIELD_ID,
  name: 'Central Court',
  city: 'Tel Aviv',
  latitude: 31.225172,
  longitude: 34.777498,
  sport_type: 'football',
  surface_type: 'synthetic',
  has_nets: true,
  has_water_cooler: false,
  opening_hours: '19:00',
  notes: '',
  status: 'approved',
  active_game: null,
  upcoming_games: [],
}

const pendingField = {
  ...approvedField,
  status: 'pending',
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

function fulfillJson(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function seedAuthenticatedUser(page) {
  const token = makeJwtWithSubject(user.id)

  await page.addInitScript((storedUser) => {
    localStorage.setItem('access_token', storedUser.token)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('userCity', 'ירושלים') // E08-02 follow-up fix: account needs a resolved city to reach the map
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  }, { ...user, token })
}

async function mockMapPageRequests(page, { fields = [approvedField] } = {}) {
  await page.route(/\/fields\/?(\?.*)?$/, (route) => fulfillJson(route, fields))
  await page.route(/\/notifications(\/.*)?(\?.*)?$/, (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/unread-count')) {
      return fulfillJson(route, { unread_count: 0 })
    }
    return fulfillJson(route, [])
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())

  await page.route(/\/fields\/[0-9a-f-]+$/i, (route) => {
    if (route.request().resourceType() !== 'fetch' && route.request().resourceType() !== 'xhr') {
      return route.continue()
    }
    const id = new URL(route.request().url()).pathname.split('/').filter(Boolean).pop()
    const matched = fields.find((candidate) => candidate.id === id)
    if (matched) {
      return fulfillJson(route, matched)
    }
    return fulfillJson(route, { error: true, code: 'FIELD_NOT_FOUND', message: 'Field not found' }, 404)
  })
}

async function mockClipboard(page, { mode = 'success' } = {}) {
  await page.addInitScript((clipboardMode) => {
    window.__clipboardWrites = []

    Object.defineProperty(navigator, 'clipboard', {
      value: {
        writeText: async (text) => {
          window.__clipboardWrites.push(text)
          if (clipboardMode === 'reject') {
            throw new Error('Clipboard rejected')
          }
        },
      },
      configurable: true,
    })

    document.execCommand = () => false
  }, mode)
}

test.beforeEach(async ({ page }) => {
  await seedAuthenticatedUser(page)
})

test('shows share button for an approved field', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [approvedField] })

  await page.goto(`/field/${FIELD_ID}`)

  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: approvedField.name }),
  ).toBeVisible()

  await expect(page.getByRole('button', { name: 'Share field' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Copy field link' })).toBeVisible()
})

test('does not show share button for a pending field', async ({ page }) => {
  await mockMapPageRequests(page, { fields: [pendingField] })

  await page.goto(`/field/${FIELD_ID}`)

  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: pendingField.name }),
  ).toBeVisible()

  await expect(page.getByRole('button', { name: 'Share field' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Copy field link' })).toHaveCount(0)
})

test('copies the canonical field link and shows success feedback after copy succeeds', async ({ page }) => {
  await mockClipboard(page)
  await mockMapPageRequests(page, { fields: [approvedField] })

  await page.goto(`/field/${FIELD_ID}`)
  await page.getByRole('button', { name: 'Copy field link' }).click()

  await expect(page.getByText('Field link copied.')).toBeVisible()
  await expect
    .poll(() => page.evaluate(() => window.__clipboardWrites))
    .toEqual([`https://yesh-mishak.com/fields/${FIELD_ID}`])
})

test('shows field copy failure feedback when clipboard write fails', async ({ page }) => {
  await mockClipboard(page, { mode: 'reject' })
  await mockMapPageRequests(page, { fields: [approvedField] })

  await page.goto(`/field/${FIELD_ID}`)
  await page.getByRole('button', { name: 'Copy field link' }).click()

  await expect(page.getByText('Could not copy this field link. Please try again.')).toBeVisible()
  await expect(page.getByText('Field link copied.')).toHaveCount(0)
})

test('opening a second field link replaces the selected field without duplicate panels', async ({ page }) => {
  const secondFieldId = '88888888-8888-4888-8888-888888888888'
  const secondField = {
    ...approvedField,
    id: secondFieldId,
    name: 'North Court',
    latitude: 31.228,
    longitude: 34.78,
  }

  await mockMapPageRequests(page, { fields: [approvedField, secondField] })

  await page.goto(`/field/${FIELD_ID}`)
  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: approvedField.name }),
  ).toBeVisible()

  // Close and navigate to the second field
  await page.getByLabel('Close').click()
  await page.goto(`/field/${secondFieldId}`)

  await expect(
    page.getByLabel('Field details').getByRole('heading', { name: secondField.name }),
  ).toBeVisible()

  // Only one field details panel should be visible
  await expect(page.getByLabel('Field details')).toHaveCount(1)
})

test('logged-out user landing on a shared field URL sees login, then field opens after auth', async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('currentUserId')
    localStorage.removeItem('currentUserName')
    localStorage.removeItem('currentUserEmail')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  })

  await mockMapPageRequests(page, { fields: [approvedField] })

  const googleCredential = makeJwtWithSubject(user.id)

  await page.route('https://accounts.google.com/gsi/client', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/javascript',
      body: `
        window.google = {
          accounts: {
            id: {
              callback: null,

              initialize(options) {
                this.callback = options.callback
              },

              renderButton(element) {
                const button = document.createElement('button')
                button.type = 'button'
                button.textContent = 'Sign in with Google'

                button.addEventListener('click', () => {
                  this.callback?.({
                    credential: ${JSON.stringify(googleCredential)}
                  })
                })

                element.replaceChildren(button)
              }
            }
          }
        }
      `,
    }),
  )

  await page.route('**/auth/google', (route) =>
    fulfillJson(route, {
      access_token: makeJwtWithSubject(user.id),
      user: {
        id: user.id,
        name: user.name,
        email: user.email,
      },
    }),
  )

  await page.route('**/games/me**', (route) => fulfillJson(route, []))

  const requestedFieldUrls = []

  page.on('request', (request) => {
    if (
      request.method() === 'GET' &&
      request.url().includes(`/fields/${FIELD_ID}`)
    ) {
      requestedFieldUrls.push(request.url())
    }
  })

  await page.goto(`/field/${FIELD_ID}`)

  await expect(
    page.getByRole('button', { name: /^sign in$/i }),
  ).toBeVisible()

  await expect.poll(async () =>
    page.evaluate(() => sessionStorage.getItem('pending_deep_link')),
  ).not.toBeNull()

  await page.getByText('Sign in with Google', { exact: true }).click()

  await expect(
    page.getByRole('button', { name: /^sign in$/i }),
  ).not.toBeVisible({ timeout: 10_000 })

  await expect.poll(() => requestedFieldUrls.length).toBeGreaterThan(0)

  await expect(
    page
      .getByLabel('Field details')
      .getByRole('heading', { name: approvedField.name }),
  ).toBeVisible({ timeout: 10_000 })

  expect(
    requestedFieldUrls.some((url) =>
      url.includes(`/fields/${FIELD_ID}`),
    ),
  ).toBe(true)

  await expect.poll(async () =>
    page.evaluate(() => sessionStorage.getItem('pending_deep_link')),
  ).toBeNull()
})
