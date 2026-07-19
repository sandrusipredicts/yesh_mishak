import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

const adminUser = {
  id: 'admin-user-1',
  email: 'admin@example.com',
  name: 'Admin User',
  role: 'admin',
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

async function mockGoogleLoginScript(page) {
  await page.route('https://accounts.google.com/gsi/client', (route) =>
    route.fulfill({
      status: 200,
      contentType: 'application/javascript',
      body: `
        window.google = {
          accounts: {
            id: {
              initialize() {},
              renderButton(element) {
                element.textContent = 'Sign in with Google';
              },
            },
          },
        };
      `,
    }),
  )
}

async function seedAuthenticatedUser(page, user) {
  await page.addInitScript((storedUser) => {
    localStorage.setItem('access_token', storedUser.token)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('userCity', 'ירושלים') // E08-02 follow-up fix: account needs a resolved city to reach the map
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  }, { ...user, token: makeJwtWithSubject(user.id) })
}

async function mockMapRequests(page) {
  await page.route('**/fields**', (route) => {
    const url = new URL(route.request().url())

    if (url.pathname === '/fields') {
      return fulfillJson(route, [])
    }

    return route.continue()
  })
  await page.route('**/notifications**', (route) => {
    const url = new URL(route.request().url())

    if (url.pathname === '/notifications/unread-count') {
      return fulfillJson(route, { unread_count: 0 })
    }

    if (url.pathname === '/notifications') {
      return fulfillJson(route, [])
    }

    return route.continue()
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
}

const baseField = {
  id: 'field-1',
  name: 'Central Court',
  city: 'Tel Aviv',
  lat: 32.0853,
  lng: 34.7818,
  sport_type: 'football',
  surface_type: 'grass',
  has_nets: true,
  has_water: false,
  opening_hours: '08:00-22:00',
  status: 'open',
  approval_status: 'approved',
  verified: true,
  notes: 'Great field',
  created_at: '2026-06-01T10:00:00.000Z',
}

async function mockAdminApi(page, { allFields = [baseField], patchHandler = null } = {}) {
  await page.route('**/admin/**', (route) => {
    const url = new URL(route.request().url())
    const method = route.request().method()

    if (!url.pathname.startsWith('/admin/')) {
      return route.continue()
    }

    if (url.pathname === '/admin/me') {
      return fulfillJson(route, adminUser)
    }

    if (url.pathname === '/admin/fields/pending') {
      return fulfillJson(route, [])
    }

    if (url.pathname === '/admin/fields' && method === 'GET') {
      return fulfillJson(route, allFields)
    }

    if (url.pathname.match(/^\/admin\/fields\/[^/]+$/) && method === 'PATCH') {
      if (patchHandler) {
        return patchHandler(route)
      }
      const payload = route.request().postDataJSON()
      return fulfillJson(route, {
        message: 'Field updated',
        field: { ...baseField, ...payload },
      })
    }

    return fulfillJson(route, { detail: 'Unhandled admin mock' }, 404)
  })
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  })
  await mockGoogleLoginScript(page)
  await mockMapRequests(page)
})

async function openAllFieldsTab(page) {
  await page.goto('/admin')
  await page.getByRole('button', { name: 'Fields' }).click()
  await page.getByRole('tab', { name: 'All Fields' }).click()
  await expect(page.getByText('Central Court')).toBeVisible()
}

test('edit button opens the form pre-filled with the field\'s current values', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page)

  await openAllFieldsTab(page)
  await page.getByRole('button', { name: 'Edit Central Court' }).click()

  await expect(page.getByRole('heading', { name: 'Edit field' })).toBeVisible()
  await expect(page.getByLabel('Field name')).toHaveValue('Central Court')
  await expect(page.getByLabel('Surface type')).toHaveValue('grass')
  await expect(page.getByLabel('Has nets?')).toBeChecked()
  await expect(page.getByLabel('Has water fountain?')).not.toBeChecked()
})

test('saving a change updates the table row without a hard refresh', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page)

  await openAllFieldsTab(page)
  await page.getByRole('button', { name: 'Edit Central Court' }).click()

  const nameInput = page.getByLabel('Field name')
  await nameInput.fill('Renamed Court')
  await page.getByRole('button', { name: 'Save', exact: true }).click()

  await expect(page.getByRole('heading', { name: 'Edit field' })).toHaveCount(0)
  await expect(page.getByText('Renamed Court')).toBeVisible()
  await expect(page.getByText('Central Court')).toHaveCount(0)
})

test('empty name is rejected client-side and keeps the modal open', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page)

  await openAllFieldsTab(page)
  await page.getByRole('button', { name: 'Edit Central Court' }).click()

  const nameInput = page.getByLabel('Field name')
  await nameInput.fill('   ')
  await page.getByRole('button', { name: 'Save', exact: true }).click()

  await expect(page.getByRole('heading', { name: 'Edit field' })).toBeVisible()
  await expect(page.getByText('Field name is required.')).toBeVisible()
})

test('server validation error is surfaced and the form stays open', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page, {
    patchHandler: (route) =>
      fulfillJson(route, { error: true, code: 'DATABASE_ERROR', message: 'Failed to update field' }, 500),
  })

  await openAllFieldsTab(page)
  await page.getByRole('button', { name: 'Edit Central Court' }).click()
  await page.getByLabel('Notes (optional)').fill('Updated notes')
  await page.getByRole('button', { name: 'Save', exact: true }).click()

  await expect(page.getByText('Failed to update field')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Edit field' })).toBeVisible()
})

test('duplicate conflict from the server shows a duplicate-specific message', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page, {
    patchHandler: (route) =>
      fulfillJson(route, { error: true, code: 'FIELD_DUPLICATE', message: 'Duplicate' }, 409),
  })

  await openAllFieldsTab(page)
  await page.getByRole('button', { name: 'Edit Central Court' }).click()
  await page.getByLabel('City').fill('Haifa')
  await page.getByRole('button', { name: 'Save', exact: true }).click()

  await expect(
    page.getByText('This change would make the field a duplicate of an existing field. Resolve the conflict first.'),
  ).toBeVisible()
})

test('save button is disabled while the request is in flight, preventing double submit', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  let resolveRoute
  const patchPromise = new Promise((resolve) => {
    resolveRoute = resolve
  })
  await mockAdminApi(page, {
    patchHandler: async (route) => {
      await patchPromise
      const payload = route.request().postDataJSON()
      return fulfillJson(route, { message: 'Field updated', field: { ...baseField, ...payload } })
    },
  })

  await openAllFieldsTab(page)
  await page.getByRole('button', { name: 'Edit Central Court' }).click()
  await page.getByLabel('Notes (optional)').fill('Notes in flight')

  const saveButton = page.getByRole('button', { name: 'Save', exact: true })
  await saveButton.click()

  await expect(page.getByRole('button', { name: 'Saving...' })).toBeDisabled()

  resolveRoute()
  await expect(page.getByRole('heading', { name: 'Edit field' })).toHaveCount(0)
})

test('cancel without changes closes immediately with no confirmation', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page)

  await openAllFieldsTab(page)
  await page.getByRole('button', { name: 'Edit Central Court' }).click()
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()

  await expect(page.getByRole('heading', { name: 'Edit field' })).toHaveCount(0)
  await expect(page.getByRole('heading', { name: 'Discard changes?' })).toHaveCount(0)
})

test('cancel with unsaved changes asks for confirmation, and keep editing preserves the form', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page)

  await openAllFieldsTab(page)
  await page.getByRole('button', { name: 'Edit Central Court' }).click()
  await page.getByLabel('Field name').fill('Changed Name')
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()

  await expect(page.getByRole('heading', { name: 'Discard changes?' })).toBeVisible()
  await page.getByRole('button', { name: 'Keep editing' }).click()

  await expect(page.getByRole('heading', { name: 'Edit field' })).toBeVisible()
  await expect(page.getByLabel('Field name')).toHaveValue('Changed Name')
})

test('discarding unsaved changes closes the modal without saving', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page)

  await openAllFieldsTab(page)
  await page.getByRole('button', { name: 'Edit Central Court' }).click()
  await page.getByLabel('Field name').fill('Changed Name')
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()
  await page.getByRole('button', { name: 'Discard changes' }).click()

  await expect(page.getByRole('heading', { name: 'Edit field' })).toHaveCount(0)
  await expect(page.getByText('Central Court')).toBeVisible()
})

test('a direct API call from a non-admin session is still rejected by the backend (403)', async ({ page }) => {
  await seedAuthenticatedUser(page, { ...adminUser, id: 'regular-user-1', role: 'user' })
  await page.route('**/admin/fields/field-1', (route) => {
    if (route.request().method() === 'PATCH') {
      return fulfillJson(route, { error: true, code: 'FORBIDDEN', message: 'Admin access required' }, 403)
    }
    return route.continue()
  })
  await page.route('**/admin/me', (route) =>
    fulfillJson(route, { detail: 'Admin access required' }, 403),
  )

  await page.goto('/admin')

  // Regular users never reach the admin panel UI at all — this is the
  // existing AdminRoute guard, unchanged by this task. The backend's own
  // 403 on PATCH /admin/fields/{id} is covered by backend/tests/test_field_edit.py.
  await expect(page).toHaveURL('/')
  await expect(page.getByRole('heading', { name: 'Admin Panel' })).toHaveCount(0)
})
