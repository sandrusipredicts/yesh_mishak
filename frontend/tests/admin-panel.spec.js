import { expect, test } from '@playwright/test'

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

function fulfillJson(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
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
    localStorage.setItem('access_token', `${storedUser.role}-token`)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.setItem('onboarding_done', 'true')
  }, user)
}

async function mockMapRequests(page) {
  await page.route('**/fields**', (route) => {
    const url = new URL(route.request().url())

    if (url.pathname === '/fields') {
      return fulfillJson(route, [])
    }

    return route.continue()
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
}

async function mockAdminApi(page, { user = adminUser } = {}) {
  await page.route('**/admin/**', (route) => {
    const url = new URL(route.request().url())

    if (!url.pathname.startsWith('/admin/')) {
      return route.continue()
    }

    if (url.pathname === '/admin/me') {
      if (user.role !== 'admin') {
        return fulfillJson(route, { detail: 'Admin access required' }, 403)
      }

      return fulfillJson(route, user)
    }

    if (url.pathname === '/admin/fields/pending') {
      return fulfillJson(route, [
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
      return fulfillJson(route, [])
    }

    if (url.pathname === '/admin/games') {
      return fulfillJson(route, {
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

    if (url.pathname === '/admin/users') {
      return fulfillJson(route, [
        {
          id: 'regular-user-1',
          name: 'Regular User',
          email: 'user@example.com',
          phone_number: '050-0000000',
          created_at: '2026-06-01T10:00:00.000Z',
          last_active: '2026-06-14T10:00:00.000Z',
          role: 'user',
        },
      ])
    }

    return fulfillJson(route, { detail: 'Unhandled admin mock' }, 404)
  })

}

test.beforeEach(async ({ page }) => {
  await mockGoogleLoginScript(page)
  await mockMapRequests(page)
})

test('not logged in user visiting /admin sees the login page', async ({ page }) => {
  await page.goto('/admin')

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

  await expect(page.getByRole('heading', { name: 'Admin Panel' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Fields' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Games' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Users' })).toBeVisible()
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

test('admin games tab loads without crashing', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page)

  await page.goto('/admin')
  await page.getByRole('button', { name: 'Games' }).click()

  await expect(page.getByRole('heading', { name: 'Games', exact: true })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Active Games' })).toBeVisible()
  await expect(page.getByText('Central Court')).toBeVisible()
})

test('admin users tab loads without crashing', async ({ page }) => {
  await seedAuthenticatedUser(page, adminUser)
  await mockAdminApi(page)

  await page.goto('/admin')
  await page.getByRole('button', { name: 'Users' }).click()

  await expect(page.getByRole('heading', { name: 'Users' }).last()).toBeVisible()
  await expect(page.getByLabel('Search users')).toBeVisible()
  await expect(page.getByText('user@example.com')).toBeVisible()
})
