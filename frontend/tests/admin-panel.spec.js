import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

const adminUser = {
  id: 'admin-user-1',
  email: 'admin@example.com',
  name: 'Admin User',
  role: 'admin',
}

const regularUser = {
  id: 'regular-user-1',
  email: 'user@example.com',
  name: 'Regular User',
  role: 'user',
}

const adminStats = {
  verified_fields: 12,
  pending_fields: 3,
  active_games: 4,
  total_users: 25,
}

const reportStatuses = ['open', 'in_review', 'resolved', 'rejected']

function makeFieldReports(count = 20) {
  return Array.from({ length: count }, (_, index) => {
    const reportNumber = index + 1

    return {
      id: `report-${reportNumber}`,
      field_id: `field-${reportNumber}`,
      field_name: `Court ${reportNumber}`,
      user_id: `reporter-${reportNumber}`,
      reporter_name: `Reporter ${reportNumber}`,
      reporter_email: `reporter${reportNumber}@example.com`,
      category: reportNumber % 2 === 0 ? 'field_closed' : 'wrong_information',
      description: `Description ${reportNumber}`,
      status: reportStatuses[index % reportStatuses.length],
      created_at: `2026-06-${String(reportNumber).padStart(2, '0')}T10:00:00.000Z`,
      reviewed_at: null,
      reviewed_by: null,
    }
  })
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

async function mockAdminApi(
  page,
  {
    user = adminUser,
    stats = adminStats,
    fieldReports = makeFieldReports(),
    resolveHandler = null,
    fieldReportStatusHandler = null,
    users = null,
    userActionHandler = null,
    pendingFields = null,
    fields = null,
    fieldActionHandler = null,
    games = null,
    gameActionHandler = null,
  } = {},
) {
  await page.route('**/admin/**', (route) => {
    const url = new URL(route.request().url())
    const method = route.request().method()

    if (!url.pathname.startsWith('/admin/')) {
      return route.continue()
    }

    if (url.pathname === '/admin/me') {
      if (user.role !== 'admin') {
        return fulfillJson(route, { detail: 'Admin access required' }, 403)
      }

      return fulfillJson(route, user)
    }

    if (url.pathname === '/admin/stats') {
      return fulfillJson(route, stats)
    }

    if (url.pathname === '/admin/field-reports') {
      return fulfillJson(route, fieldReports)
    }

    if (url.pathname.match(/^\/admin\/field-reports\/[^/]+\/resolve$/) && method === 'PATCH') {
      if (resolveHandler) {
        return resolveHandler(route)
      }

      const reportId = url.pathname.split('/')[3]
      const payload = route.request().postDataJSON()
      const report = fieldReports.find((item) => item.id === reportId)
      return fulfillJson(route, {
        message: 'Field report resolved',
        report: {
          ...report,
          status: 'resolved',
          admin_note: payload.admin_note ?? report?.admin_note ?? null,
          reviewed_at: '2026-06-30T12:00:00.000Z',
          reviewed_by: adminUser.id,
        },
      })
    }

    if (url.pathname.match(/^\/admin\/field-reports\/[^/]+\/status$/) && method === 'PATCH') {
      if (fieldReportStatusHandler) {
        return fieldReportStatusHandler(route)
      }

      return fulfillJson(route, { detail: 'Unhandled field report status mock' }, 404)
    }

    if (url.pathname === '/admin/fields/pending') {
      return fulfillJson(route, pendingFields ?? [
        {
          id: 'field-1',
          name: 'Central Court',
          city: 'Yeruham',
          lat: 30.9872,
          lng: 34.9314,
          sport_type: 'basketball',
          surface_type: 'asphalt',
          notes: 'Needs nets',
          created_at: '2026-06-01T10:00:00.000Z',
        },
      ])
    }

    if (url.pathname === '/admin/fields') {
      return fulfillJson(route, fields ?? [])
    }

    if (url.pathname.match(/^\/admin\/fields\/[^/]+\/(approve|reject)$/) && method === 'POST') {
      if (fieldActionHandler) {
        return fieldActionHandler(route)
      }

      return fulfillJson(route, { detail: 'Unhandled field moderation mock' }, 404)
    }

    if (url.pathname.match(/^\/admin\/fields\/[^/]+\/status$/) && method === 'PATCH') {
      if (fieldActionHandler) {
        return fieldActionHandler(route)
      }

      return fulfillJson(route, { detail: 'Unhandled field status mock' }, 404)
    }

    if (url.pathname === '/admin/games') {
      return fulfillJson(route, games ?? {
        active: [
          {
            id: 'game-1',
            field_name: 'Central Court',
            sport_type: 'basketball',
            players_present: 6,
            max_players: 10,
            status: 'open',
            started_at: '2026-06-10T18:00:00.000Z',
            expires_at: '2026-06-10T20:00:00.000Z',
            participants: [{ id: 'regular-user-1' }],
          },
        ],
        finished: [],
      })
    }

    if (url.pathname.match(/^\/admin\/games\/[^/]+\/(close|extend)$/) && method === 'POST') {
      if (gameActionHandler) {
        return gameActionHandler(route)
      }

      return fulfillJson(route, { detail: 'Unhandled game action mock' }, 404)
    }

    if (url.pathname === '/admin/users') {
      return fulfillJson(route, users ?? [
        {
          id: 'regular-user-1',
          username: 'regular-user',
          name: 'Regular User',
          email: 'user@example.com',
          phone_number: '050-0000000',
          created_at: '2026-06-01T10:00:00.000Z',
          last_active: '2026-06-14T10:00:00.000Z',
          role: 'user',
          status: 'active',
          restriction_reason: null,
          restricted_at: null,
        },
      ])
    }

    if (url.pathname.match(/^\/admin\/users\/[^/]+\/(ban|unban|suspend|unsuspend)$/) && method === 'POST') {
      if (userActionHandler) {
        return userActionHandler(route)
      }

      return fulfillJson(route, { detail: 'Unhandled user moderation mock' }, 404)
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

test('not logged in user visiting /admin sees the login page', async ({ page }) => {
  await page.goto('/admin')

  await expect(page).toHaveURL('/admin')
  await expect(page.getByRole('heading', { name: 'yesh_mishak' })).toBeVisible()
  await expect(page.getByText('Sign in to open and join games.')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Admin Panel' })).toHaveCount(0)
})

test('regular user cannot access admin panel and is redirected to the map', async ({ page }) => {
  await seedAuthenticatedUser(page, regularUser)
  await mockAdminApi(page, { user: regularUser })

  await page.goto('/admin')

  await expect(page).toHaveURL('/')
  await expect(page.getByRole('button', { name: 'Notifications' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Admin Panel' })).toHaveCount(0)
})

test('admin user can access /admin', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page)

  await page.goto('/admin')

  await expect(page).toHaveURL('/admin')
  await expect(page.getByRole('heading', { name: 'Admin Panel' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Stats' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Fields' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Games' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Users' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Field Reports' })).toBeVisible()
})

test('admin stats tab loads values from GET /admin/stats', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page)

  await page.goto('/admin')

  await expect(page.getByRole('heading', { name: 'Stats' })).toBeVisible()
  await expect(page.getByText('Verified fields')).toBeVisible()
  await expect(page.getByText('12')).toBeVisible()
  await expect(page.getByText('Pending fields')).toBeVisible()
  await expect(page.getByText('3')).toBeVisible()
  await expect(page.getByText('Active games')).toBeVisible()
  await expect(page.getByText('4')).toBeVisible()
  await expect(page.getByText('Total users')).toBeVisible()
  await expect(page.getByText('25')).toBeVisible()
})

test('admin fields tab loads without crashing', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page)

  await page.goto('/admin')
  await page.getByRole('button', { name: 'Fields' }).click()

  await expect(page.getByRole('heading', { name: 'Fields' })).toBeVisible()
  await expect(page.getByRole('tab', { name: 'Pending' })).toHaveAttribute('aria-selected', 'true')
  await expect(page.getByText('Central Court')).toBeVisible()
})

test('field approve, reject, and renovation status actions update the visible state', async ({ page }) => {
  const fields = [
    {
      id: '10440000-0000-4000-8000-000000000101',
      name: 'QA Pending Approve',
      city: 'Synthetic City',
      lat: 31.0,
      lng: 35.0,
      sport_type: 'basketball',
      surface_type: 'asphalt',
      status: 'open',
      approval_status: 'pending',
      verified: false,
      created_at: '2026-08-01T10:00:00.000Z',
    },
    {
      id: '10440000-0000-4000-8000-000000000102',
      name: 'QA Pending Reject',
      city: 'Synthetic City',
      lat: 31.1,
      lng: 35.1,
      sport_type: 'football',
      surface_type: 'grass',
      status: 'open',
      approval_status: 'pending',
      verified: false,
      created_at: '2026-08-01T11:00:00.000Z',
    },
  ]
  const requests = []

  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page, {
    pendingFields: fields,
    fields,
    fieldActionHandler: async (route) => {
      const request = route.request()
      const pathParts = new URL(request.url()).pathname.split('/')
      const fieldId = pathParts[3]
      const action = pathParts[4]
      const target = fields.find((candidate) => candidate.id === fieldId)

      if (action === 'approve') {
        Object.assign(target, { approval_status: 'approved', verified: true })
      } else if (action === 'reject') {
        Object.assign(target, { approval_status: 'rejected', verified: false })
      } else if (action === 'status') {
        Object.assign(target, { status: request.postDataJSON().status })
      }
      requests.push({ action, fieldId, method: request.method() })
      return fulfillJson(route, action === 'status' ? { field: target } : target)
    },
  })

  await page.goto('/admin')
  await page.getByRole('button', { name: 'Fields', exact: true }).click()
  await page.getByRole('row').filter({ hasText: 'QA Pending Approve' })
    .getByRole('button', { name: 'Approve', exact: true }).click()
  await expect(page.getByText('QA Pending Approve', { exact: true })).toHaveCount(0)
  await page.getByRole('row').filter({ hasText: 'QA Pending Reject' })
    .getByRole('button', { name: 'Reject', exact: true }).click()
  await expect(page.getByText('No pending fields.', { exact: true })).toBeVisible()

  await page.getByRole('tab', { name: 'All Fields', exact: true }).click()
  const approvedRow = page.getByRole('row').filter({ hasText: 'QA Pending Approve' })
  const rejectedRow = page.getByRole('row').filter({ hasText: 'QA Pending Reject' })
  await expect(approvedRow.getByText('Approved', { exact: true })).toBeVisible()
  await expect(approvedRow.getByText('Yes', { exact: true })).toBeVisible()
  await expect(rejectedRow.getByText('Rejected', { exact: true })).toBeVisible()
  await approvedRow.getByRole('combobox', { name: 'Status for QA Pending Approve' })
    .selectOption('renovation')
  await expect(approvedRow.getByRole('combobox', { name: 'Status for QA Pending Approve' }))
    .toHaveValue('renovation')

  expect(requests).toEqual([
    { action: 'approve', fieldId: fields[0].id, method: 'POST' },
    { action: 'reject', fieldId: fields[1].id, method: 'POST' },
    { action: 'status', fieldId: fields[0].id, method: 'PATCH' },
  ])
})

test('admin games tab loads without crashing', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page)

  await page.goto('/admin')
  await page.getByRole('button', { name: 'Games' }).click()

  await expect(page.getByRole('heading', { name: 'Games', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Active Games' })).toBeVisible()
  await expect(page.getByText('Central Court')).toBeVisible()
})

test('admin can extend and close an active game with persisted refreshes', async ({ page }) => {
  const game = {
    id: '10440000-0000-4000-8000-000000000301',
    field_name: 'QA Game Field',
    sport_type: 'basketball',
    players_present: 2,
    max_players: 10,
    status: 'open',
    started_at: '2026-08-01T10:00:00.000Z',
    expires_at: '2026-08-01T12:00:00.000Z',
    participants: [],
  }
  const games = { active: [game], finished: [] }
  const requests = []

  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page, {
    games,
    gameActionHandler: async (route) => {
      const action = new URL(route.request().url()).pathname.split('/')[4]
      requests.push(action)
      if (action === 'extend') {
        game.expires_at = '2026-08-01T13:00:00.000Z'
        return fulfillJson(route, { game, new_expires_at: game.expires_at })
      }

      game.status = 'finished'
      games.active = []
      games.finished = [game]
      return fulfillJson(route, { game })
    },
  })

  await page.goto('/admin')
  await page.getByRole('button', { name: 'Games', exact: true }).click()
  const gameRow = page.getByRole('row').filter({ hasText: 'QA Game Field' })
  await gameRow.getByRole('button', { name: 'Extend', exact: true }).click()
  await expect(gameRow).toContainText('4:00:00 PM')

  await gameRow.getByRole('button', { name: 'Close', exact: true }).click()
  await page.getByRole('button', { name: 'Close game', exact: true }).click()
  await expect(page.getByText('No active games.', { exact: true })).toBeVisible()
  await expect(page.getByRole('row').filter({ hasText: 'QA Game Field' })).toContainText('finished')
  expect(requests).toEqual(['extend', 'close'])
})

test('admin users tab loads without crashing', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page)

  await page.goto('/admin')
  await page.getByRole('button', { name: 'Users' }).click()

  await expect(page.getByRole('heading', { name: 'Users' }).last()).toBeVisible()
  await expect(page.getByLabel('Search users')).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'User ID' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Username' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Email' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Phone' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Created Date' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Status' })).toBeVisible()
  await expect(page.getByRole('columnheader', { name: 'Actions' })).toBeVisible()
  const userRow = page.getByRole('row', { name: /regular-user-1 regular-user/ })
  await expect(userRow.getByRole('cell', { name: 'regular-user-1' })).toBeVisible()
  await expect(userRow.getByRole('cell', { name: 'regular-user', exact: true })).toBeVisible()
  await expect(userRow.getByRole('cell', { name: 'user@example.com' })).toBeVisible()
  await expect(userRow.getByRole('cell', { name: '050-0000000' })).toBeVisible()
  await expect(userRow.getByRole('cell', { name: 'Active' })).toBeVisible()
  await expect(userRow.getByRole('button', { name: 'Ban' })).toBeVisible()
  await expect(userRow.getByRole('button', { name: 'Suspend' })).toBeVisible()
})

test('admin user search and all reversible moderation transitions reflect persisted state', async ({ page }) => {
  const users = [
    {
      id: '10440000-0000-4000-8000-000000000001',
      username: 'qa-target-one',
      name: 'QA Target One',
      email: 'qa-target-one@example.com',
      phone_number: null,
      created_at: '2026-08-01T10:00:00.000Z',
      role: 'user',
      status: 'active',
      restriction_reason: null,
      restricted_at: null,
    },
    {
      id: '10440000-0000-4000-8000-000000000002',
      username: 'qa-target-two',
      name: 'QA Target Two',
      email: 'qa-target-two@example.com',
      phone_number: null,
      created_at: '2026-08-01T11:00:00.000Z',
      role: 'user',
      status: 'active',
      restriction_reason: null,
      restricted_at: null,
    },
  ]
  const requests = []

  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page, {
    users,
    userActionHandler: async (route) => {
      const request = route.request()
      const pathParts = new URL(request.url()).pathname.split('/')
      const userId = pathParts[3]
      const action = pathParts[4]
      const body = request.postDataJSON()
      const target = users.find((candidate) => candidate.id === userId)
      const nextStatus = {
        ban: 'banned',
        unban: 'active',
        suspend: 'suspended',
        unsuspend: 'active',
      }[action]

      requests.push({ action, body, userId })
      target.status = nextStatus
      target.restriction_reason = body.reason ?? null
      return fulfillJson(route, { message: `User ${action} successful`, user: target })
    },
  })

  await page.goto('/admin')
  await page.getByRole('button', { name: 'Users', exact: true }).click()
  await expect(page.getByText('qa-target-one', { exact: true })).toBeVisible()

  const search = page.getByRole('searchbox', { name: 'Search users' })
  await search.fill('target-two')
  await expect(page.getByText('qa-target-one', { exact: true })).toHaveCount(0)
  await expect(page.getByText('qa-target-two', { exact: true })).toBeVisible()
  await search.clear()

  const targetRow = page.getByRole('row').filter({ hasText: 'qa-target-one' })
  await targetRow.getByRole('button', { name: 'Ban', exact: true }).click()
  await page.getByLabel('Reason', { exact: true }).fill('Synthetic QA moderation')
  await page.getByRole('button', { name: 'Confirm', exact: true }).click()
  await expect(targetRow.getByText('Banned', { exact: true })).toBeVisible()

  await targetRow.getByRole('button', { name: 'Unban', exact: true }).click()
  await expect(targetRow.getByText('Active', { exact: true })).toBeVisible()

  await targetRow.getByRole('button', { name: 'Suspend', exact: true }).click()
  await page.getByLabel('Reason', { exact: true }).fill('Synthetic QA suspension')
  await page.getByRole('button', { name: 'Confirm', exact: true }).click()
  await expect(targetRow.getByText('Suspended', { exact: true })).toBeVisible()

  await targetRow.getByRole('button', { name: 'Unsuspend', exact: true }).click()
  await expect(targetRow.getByText('Active', { exact: true })).toBeVisible()

  expect(requests.map(({ action }) => action)).toEqual(['ban', 'unban', 'suspend', 'unsuspend'])
  expect(requests[0].body).toEqual({ reason: 'Synthetic QA moderation' })
  expect(requests[1].body).toEqual({})
  expect(requests.every(({ userId }) => userId === users[0].id)).toBe(true)
  expect(requests.every(({ body }) => !('actor_user_id' in body))).toBe(true)
})

test('failed user moderation keeps the target active and shows a bounded error', async ({ page }) => {
  const users = [{
    id: '10440000-0000-4000-8000-000000000003',
    username: 'qa-failure-target',
    name: 'QA Failure Target',
    email: 'qa-failure-target@example.com',
    phone_number: null,
    created_at: '2026-08-01T12:00:00.000Z',
    role: 'user',
    status: 'active',
  }]

  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page, {
    users,
    userActionHandler: async (route) => fulfillJson(
      route,
      { detail: 'database internals must stay hidden' },
      500,
    ),
  })

  await page.goto('/admin')
  await page.getByRole('button', { name: 'Users', exact: true }).click()
  const targetRow = page.getByRole('row').filter({ hasText: 'qa-failure-target' })
  await targetRow.getByRole('button', { name: 'Ban', exact: true }).click()
  await page.getByLabel('Reason', { exact: true }).fill('Synthetic QA moderation')
  await page.getByRole('button', { name: 'Confirm', exact: true }).click()

  await expect(page.getByText('Moderation action failed.', { exact: true })).toBeVisible()
  await expect(page.getByText('database internals must stay hidden', { exact: true })).toHaveCount(0)
  await expect(targetRow.getByText('Active', { exact: true })).toBeVisible()
  await expect(targetRow.getByRole('button', { name: 'Ban', exact: true })).toBeEnabled()
})

test('admin field reports queue displays 20 reports sorted newest first and filters by status', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page)

  await page.goto('/admin')
  await page.getByRole('button', { name: 'Field Reports' }).click()

  await expect(page.getByRole('heading', { name: 'Field Reports', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Field reports queue' })).toBeVisible()

  const rows = page.locator('.admin-field-reports-table tbody tr')
  await expect(rows).toHaveCount(20)
  await expect(rows.first()).toContainText('Court 20')
  await expect(rows.first()).toContainText('Reporter 20')
  await expect(rows.first()).toContainText('Rejected')
  await expect(rows.nth(19)).toContainText('Court 1')

  await page.getByRole('tab', { name: 'Resolved' }).click()

  await expect(rows).toHaveCount(5)
  await expect(rows.first()).toContainText('Court 19')
  await expect(rows.first()).toContainText('Resolved')
  await expect(rows.last()).toContainText('Court 3')

  await page.getByRole('tab', { name: 'In Review' }).click()

  await expect(rows).toHaveCount(5)
  await expect(rows.first()).toContainText('Court 18')
  await expect(rows.first()).toContainText('In Review')
})

test('managing a field report persists status and note without optimistic stale state', async ({ page }) => {
  const fieldReports = [{
    id: '10440000-0000-4000-8000-000000000201',
    field_id: '10440000-0000-4000-8000-000000000101',
    field_name: 'QA Report Field',
    user_id: '10440000-0000-4000-8000-000000000001',
    reporter_name: 'Synthetic Reporter',
    reporter_email: 'synthetic-reporter@example.com',
    category: 'wrong_information',
    description: 'Synthetic report description',
    status: 'open',
    created_at: '2026-08-01T10:00:00.000Z',
    reviewed_at: null,
    reviewed_by: null,
    admin_note: null,
  }]
  const requests = []

  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page, {
    fieldReports,
    fieldReportStatusHandler: async (route) => {
      const body = route.request().postDataJSON()
      requests.push(body)
      Object.assign(fieldReports[0], {
        status: body.status,
        admin_note: body.admin_note,
        reviewed_at: '2026-08-01T12:00:00.000Z',
        reviewed_by: adminUser.id,
      })
      return fulfillJson(route, { report: fieldReports[0] })
    },
  })

  await page.goto('/admin')
  await page.getByRole('button', { name: 'Field Reports', exact: true }).click()
  const reportRow = page.getByRole('row').filter({ hasText: 'QA Report Field' })
  await reportRow.getByRole('button', { name: 'Manage', exact: true }).click()
  const manageDialog = page.getByRole('alertdialog', { name: 'Manage Report' })
  await manageDialog.getByRole('combobox').selectOption('in_review')
  await manageDialog.getByRole('textbox').fill('Synthetic QA review note')
  await manageDialog.getByRole('button', { name: 'Save', exact: true }).click()

  await expect(reportRow.getByText('In Review', { exact: true })).toBeVisible()
  expect(requests).toEqual([{
    status: 'in_review',
    admin_note: 'Synthetic QA review note',
  }])
})

test('field reports show resolve action only for unresolved reports', async ({ page }) => {
  const fieldReports = [
    {
      id: 'report-open',
      field_id: 'field-open',
      field_name: 'Open Court',
      user_id: 'reporter-open',
      reporter_name: 'Open Reporter',
      reporter_email: 'open@example.com',
      category: 'wrong_information',
      description: 'Needs review',
      status: 'open',
      created_at: '2026-06-22T10:00:00.000Z',
      reviewed_at: null,
      reviewed_by: null,
    },
    {
      id: 'report-resolved',
      field_id: 'field-resolved',
      field_name: 'Resolved Court',
      user_id: 'reporter-resolved',
      reporter_name: 'Resolved Reporter',
      reporter_email: 'resolved@example.com',
      category: 'field_closed',
      description: 'Already fixed',
      status: 'resolved',
      created_at: '2026-06-21T10:00:00.000Z',
      reviewed_at: '2026-06-22T10:00:00.000Z',
      reviewed_by: adminUser.id,
    },
  ]

  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page, { fieldReports })

  await page.goto('/admin')
  await page.getByRole('button', { name: 'Field Reports' }).click()

  const openRow = page.getByRole('row', { name: /Open Court/ })
  await expect(openRow.getByRole('button', { name: 'Resolve' })).toBeVisible()

  const resolvedRow = page.getByRole('row', { name: /Resolved Court/ })
  await expect(resolvedRow.getByRole('button', { name: 'Resolve' })).toHaveCount(0)
  await expect(resolvedRow).toContainText('Resolved')
})

test('resolving a field report calls the resolve endpoint and updates the row', async ({ page }) => {
  const fieldReports = [
    {
      id: 'report-open',
      field_id: 'field-open',
      field_name: 'Open Court',
      user_id: 'reporter-open',
      reporter_name: 'Open Reporter',
      reporter_email: 'open@example.com',
      category: 'wrong_information',
      description: 'Needs review',
      status: 'open',
      created_at: '2026-06-22T10:00:00.000Z',
      reviewed_at: null,
      reviewed_by: null,
    },
  ]
  let requestPayload
  let requestPath

  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page, {
    fieldReports,
    resolveHandler: (route) => {
      requestPath = new URL(route.request().url()).pathname
      requestPayload = route.request().postDataJSON()
      return fulfillJson(route, {
        message: 'Field report resolved',
        report: {
          ...fieldReports[0],
          status: 'resolved',
          admin_note: requestPayload.admin_note,
          reviewed_at: '2026-06-30T12:00:00.000Z',
          reviewed_by: adminUser.id,
        },
      })
    },
  })

  await page.goto('/admin')
  await page.getByRole('button', { name: 'Field Reports' }).click()
  await page.getByRole('row', { name: /Open Court/ }).getByRole('button', { name: 'Resolve' }).click()

  await expect(page.getByRole('heading', { name: 'Resolve Report' })).toBeVisible()
  await page.getByLabel(/Resolution note/).fill('Fixed from admin panel')
  await page.getByRole('button', { name: 'Resolve', exact: true }).last().click()

  expect(requestPath).toBe('/admin/field-reports/report-open/resolve')
  expect(requestPayload).toEqual({ admin_note: 'Fixed from admin panel' })
  await expect(page.getByText('Report resolved successfully.')).toBeVisible()
  const row = page.getByRole('row', { name: /Open Court/ })
  await expect(row).toContainText('Resolved')
  await expect(row.getByRole('button', { name: 'Resolve' })).toHaveCount(0)
})

test('resolve loading state prevents duplicate submission', async ({ page }) => {
  const fieldReports = [
    {
      id: 'report-open',
      field_id: 'field-open',
      field_name: 'Open Court',
      user_id: 'reporter-open',
      reporter_name: 'Open Reporter',
      reporter_email: 'open@example.com',
      category: 'wrong_information',
      description: 'Needs review',
      status: 'open',
      created_at: '2026-06-22T10:00:00.000Z',
      reviewed_at: null,
      reviewed_by: null,
    },
  ]
  let releaseResolve
  const resolvePending = new Promise((resolve) => {
    releaseResolve = resolve
  })
  let requestCount = 0

  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page, {
    fieldReports,
    resolveHandler: async (route) => {
      requestCount += 1
      await resolvePending
      return fulfillJson(route, {
        message: 'Field report resolved',
        report: {
          ...fieldReports[0],
          status: 'resolved',
          reviewed_at: '2026-06-30T12:00:00.000Z',
          reviewed_by: adminUser.id,
        },
      })
    },
  })

  await page.goto('/admin')
  await page.getByRole('button', { name: 'Field Reports' }).click()
  await page.getByRole('row', { name: /Open Court/ }).getByRole('button', { name: 'Resolve' }).click()
  await page.getByRole('button', { name: 'Resolve', exact: true }).last().click()

  const resolvingButton = page.getByRole('button', { name: 'Resolving...' })
  await expect(resolvingButton).toBeDisabled()
  await resolvingButton.click({ force: true })
  expect(requestCount).toBe(1)

  releaseResolve()
  await expect(page.getByText('Report resolved successfully.')).toBeVisible()
})

test('resolve failure displays an error and leaves report unresolved', async ({ page }) => {
  const fieldReports = [
    {
      id: 'report-open',
      field_id: 'field-open',
      field_name: 'Open Court',
      user_id: 'reporter-open',
      reporter_name: 'Open Reporter',
      reporter_email: 'open@example.com',
      category: 'wrong_information',
      description: 'Needs review',
      status: 'open',
      created_at: '2026-06-22T10:00:00.000Z',
      reviewed_at: null,
      reviewed_by: null,
    },
  ]

  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page, {
    fieldReports,
    resolveHandler: (route) =>
      fulfillJson(route, { error: true, code: 'DATABASE_ERROR', message: 'Failed to resolve field report' }, 500),
  })

  await page.goto('/admin')
  await page.getByRole('button', { name: 'Field Reports' }).click()
  await page.getByRole('row', { name: /Open Court/ }).getByRole('button', { name: 'Resolve' }).click()
  await page.getByRole('button', { name: 'Resolve', exact: true }).last().click()

  await expect(page.getByText('Failed to resolve field report')).toBeVisible()
  const row = page.getByRole('row', { name: /Open Court/ })
  await expect(row).toContainText('Open')
  await expect(row.getByRole('button', { name: 'Resolve' })).toBeVisible()
})
