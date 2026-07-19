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
  removed_at: null,
  removed_by: null,
  removal_reason: null,
}

const secondField = {
  ...baseField,
  id: 'field-2',
  name: 'North Pitch',
}

async function mockAdminApi(page, { allFields = [baseField], deleteHandler = null } = {}) {
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

    if (url.pathname.match(/^\/admin\/fields\/[^/]+$/) && method === 'DELETE') {
      if (deleteHandler) {
        return deleteHandler(route)
      }
      const fieldId = url.pathname.split('/').pop()
      const target = allFields.find((field) => field.id === fieldId) ?? baseField
      return fulfillJson(route, {
        message: 'Field removed',
        field: { ...target, removed_at: '2026-06-02T10:00:00.000Z', removed_by: adminUser.id, removal_reason: 'duplicate_field' },
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

test('delete button opens a confirmation dialog naming the field', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page)

  await openAllFieldsTab(page)
  await page.getByRole('button', { name: 'Remove Central Court' }).click()

  await expect(page.getByRole('heading', { name: 'Remove field' })).toBeVisible()
  await expect(page.getByRole('alertdialog').getByText('Central Court', { exact: false })).toBeVisible()
})

test('cancel closes the dialog without calling the API', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  let deleteCalled = false
  await mockAdminApi(page, {
    deleteHandler: (route) => {
      deleteCalled = true
      return fulfillJson(route, { message: 'Field removed', field: baseField })
    },
  })

  await openAllFieldsTab(page)
  await page.getByRole('button', { name: 'Remove Central Court' }).click()
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()

  await expect(page.getByRole('heading', { name: 'Remove field' })).toHaveCount(0)
  await expect(page.getByText('Central Court')).toBeVisible()
  expect(deleteCalled).toBe(false)
})

test('confirming without selecting a reason shows a validation error and does not call the API', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  let deleteCalled = false
  await mockAdminApi(page, {
    deleteHandler: (route) => {
      deleteCalled = true
      return fulfillJson(route, { message: 'Field removed', field: baseField })
    },
  })

  await openAllFieldsTab(page)
  await page.getByRole('button', { name: 'Remove Central Court' }).click()
  await page.getByRole('button', { name: 'Remove field', exact: true }).click()

  await expect(page.getByText('Please select a reason for removing this field.')).toBeVisible()
  expect(deleteCalled).toBe(false)
  await expect(page.getByRole('heading', { name: 'Remove field' })).toBeVisible()
})

test('confirming with a reason sends the reason in the request body and removes the row on success', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  let requestBody = null
  await mockAdminApi(page, {
    deleteHandler: (route) => {
      requestBody = route.request().postDataJSON()
      return fulfillJson(route, {
        message: 'Field removed',
        field: { ...baseField, removed_at: '2026-06-02T10:00:00.000Z', removed_by: adminUser.id, removal_reason: requestBody.reason },
      })
    },
  })

  await openAllFieldsTab(page)
  await page.getByRole('button', { name: 'Remove Central Court' }).click()
  await page.getByLabel('Reason').selectOption('duplicate_field')
  await page.getByLabel('Note (optional)').fill('Duplicate of North Pitch')
  await page.getByRole('button', { name: 'Remove field', exact: true }).click()

  await expect(page.getByRole('heading', { name: 'Remove field' })).toHaveCount(0)
  await expect(page.getByText('Field removed.')).toBeVisible()
  await expect(page.getByText('Central Court')).toHaveCount(0)
  expect(requestBody).toEqual({ reason: 'duplicate_field', note: 'Duplicate of North Pitch' })
})

test('confirm button is disabled while the request is in flight, preventing duplicate submits', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  let resolveRoute
  let callCount = 0
  const deletePromise = new Promise((resolve) => {
    resolveRoute = resolve
  })
  await mockAdminApi(page, {
    deleteHandler: async (route) => {
      callCount += 1
      await deletePromise
      return fulfillJson(route, {
        message: 'Field removed',
        field: { ...baseField, removed_at: '2026-06-02T10:00:00.000Z', removed_by: adminUser.id, removal_reason: 'other' },
      })
    },
  })

  await openAllFieldsTab(page)
  await page.getByRole('button', { name: 'Remove Central Court' }).click()
  await page.getByLabel('Reason').selectOption('other')

  const confirmButton = page.getByRole('button', { name: 'Remove field', exact: true })
  await confirmButton.click()

  // The button relabels to "Removing..." and disables itself synchronously,
  // so it can no longer be targeted or activated by its old accessible
  // name — this is what actually prevents a duplicate submit.
  await expect(page.getByRole('button', { name: 'Removing...' })).toBeDisabled()
  await expect(page.getByRole('button', { name: 'Remove field', exact: true })).toHaveCount(0)

  resolveRoute()
  await expect(page.getByRole('heading', { name: 'Remove field' })).toHaveCount(0)
  expect(callCount).toBe(1)
})

test('403 forbidden keeps the row visible and shows a permission error in the dialog', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page, {
    deleteHandler: (route) =>
      fulfillJson(route, { error: true, code: 'FORBIDDEN', message: 'Admin access required' }, 403),
  })

  await openAllFieldsTab(page)
  await page.getByRole('button', { name: 'Remove Central Court' }).click()
  await page.getByLabel('Reason').selectOption('other')
  await page.getByRole('button', { name: 'Remove field', exact: true }).click()

  await expect(page.getByText('You do not have permission to remove this field.')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Remove field' })).toBeVisible()
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(page.getByText('Central Court')).toBeVisible()
})

test('404 not found closes the dialog and removes the row with an explanatory message', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page, {
    deleteHandler: (route) =>
      fulfillJson(route, { error: true, code: 'FIELD_NOT_FOUND', message: 'Field not found' }, 404),
  })

  await openAllFieldsTab(page)
  await page.getByRole('button', { name: 'Remove Central Court' }).click()
  await page.getByLabel('Reason').selectOption('other')
  await page.getByRole('button', { name: 'Remove field', exact: true }).click()

  await expect(page.getByRole('heading', { name: 'Remove field' })).toHaveCount(0)
  await expect(page.getByText('This field no longer exists.')).toBeVisible()
  await expect(page.getByText('Central Court')).toHaveCount(0)
})

test('409 already removed closes the dialog and removes the row with an explanatory message', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page, {
    deleteHandler: (route) =>
      fulfillJson(route, { error: true, code: 'FIELD_ALREADY_REMOVED', message: 'Field has already been removed' }, 409),
  })

  await openAllFieldsTab(page)
  await page.getByRole('button', { name: 'Remove Central Court' }).click()
  await page.getByLabel('Reason').selectOption('other')
  await page.getByRole('button', { name: 'Remove field', exact: true }).click()

  await expect(page.getByRole('heading', { name: 'Remove field' })).toHaveCount(0)
  await expect(page.getByText('This field has already been removed.')).toBeVisible()
  await expect(page.getByText('Central Court')).toHaveCount(0)
})

test('network failure keeps the row and shows a generic error without leaving the dialog stuck loading', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page, {
    deleteHandler: (route) => route.abort('failed'),
  })

  await openAllFieldsTab(page)
  await page.getByRole('button', { name: 'Remove Central Court' }).click()
  await page.getByLabel('Reason').selectOption('other')
  await page.getByRole('button', { name: 'Remove field', exact: true }).click()

  await expect(page.getByText('Failed to remove field.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Remove field', exact: true })).toBeEnabled()
  await page.getByRole('button', { name: 'Cancel', exact: true }).click()
  await expect(page.getByText('Central Court')).toBeVisible()
})

test('deleting one field leaves an unrelated field visible', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page, { allFields: [baseField, secondField] })

  await page.goto('/admin')
  await page.getByRole('button', { name: 'Fields' }).click()
  await page.getByRole('tab', { name: 'All Fields' }).click()
  await expect(page.getByText('Central Court')).toBeVisible()
  await expect(page.getByText('North Pitch')).toBeVisible()

  await page.getByRole('button', { name: 'Remove Central Court' }).click()
  await page.getByLabel('Reason').selectOption('other')
  await page.getByRole('button', { name: 'Remove field', exact: true }).click()

  await expect(page.getByText('Central Court')).toHaveCount(0)
  await expect(page.getByText('North Pitch')).toBeVisible()
})

test('a direct API call from a non-admin session is still rejected by the backend (403)', async ({ page }) => {
  await seedAuthenticatedUser(page, { ...adminUser, id: 'regular-user-1', role: 'user' })
  await page.route('**/admin/fields/field-1', (route) => {
    if (route.request().method() === 'DELETE') {
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
  // 403 on DELETE /admin/fields/{id} is covered by backend/tests/test_field_delete.py.
  await expect(page).toHaveURL('/')
  await expect(page.getByRole('heading', { name: 'Admin Panel' })).toHaveCount(0)
})
