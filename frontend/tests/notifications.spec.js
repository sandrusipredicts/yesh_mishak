import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

const user = {
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

async function mockMapRequests(page) {
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/fields.*/, (route) => fulfillJson(route, []))
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
}

function isNotificationUnread(notification) {
  return !notification.read_at && notification.is_read !== true
}

test.beforeEach(async ({ page }) => {
  await seedAuthenticatedUser(page)
  await mockMapRequests(page)
})

test('notification button shows unread count and clicking a notification marks it read', async ({
  page,
}) => {
  const notifications = [
    {
      id: 'notification-1',
      type: 'game_created',
      title: 'נפתח משחק חדש',
      body: 'נפתח משחק football במגרש Central Court',
      read_at: null,
      game_id: 'game-1',
      field_id: 'field-1',
      created_at: '2026-06-16T10:00:00.000Z',
    },
    {
      id: 'notification-2',
      type: 'game_created',
      title: 'משחק נוסף',
      body: 'נפתח משחק basketball במגרש North Court',
      read_at: null,
      game_id: 'game-2',
      field_id: 'field-2',
      created_at: '2026-06-16T09:00:00.000Z',
    },
  ]

  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/notifications.*/, (route) => {
    const url = new URL(route.request().url())

    if (route.request().method() === 'GET' && url.pathname === '/notifications') {
      return fulfillJson(route, notifications)
    }

    if (route.request().method() === 'GET' && url.pathname === '/notifications/unread-count') {
      return fulfillJson(route, {
        unread_count: notifications.filter(isNotificationUnread).length,
      })
    }

    if (route.request().method() === 'PATCH' && url.pathname === '/notifications/notification-1/read') {
      notifications[0] = { ...notifications[0], read_at: '2026-06-16T10:05:00.000Z' }
      return fulfillJson(route, notifications[0])
    }

    return fulfillJson(route, { detail: 'Unhandled notification mock' }, 404)
  })

  await page.goto('/')

  await expect(page.getByRole('button', { name: /Notifications, 2 unread/ })).toBeVisible()

  await page.getByRole('button', { name: /Notifications/ }).click()

  await expect(page.getByRole('heading', { name: 'Notifications' })).toBeVisible()
  await expect(page.getByText('נפתח משחק football במגרש Central Court')).toBeVisible()

  await page.getByRole('button', { name: /נפתח משחק חדש/ }).click()

  await expect(page.getByRole('button', { name: /Notifications, 1 unread/ })).toBeVisible()
})

test('mark all as read clears the unread notification count', async ({ page }) => {
  const notifications = [
    {
      id: 'notification-1',
      type: 'game_created',
      title: 'נפתח משחק חדש',
      body: 'נפתח משחק football במגרש Central Court',
      read_at: null,
      created_at: '2026-06-16T10:00:00.000Z',
    },
  ]

  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/notifications.*/, (route) => {
    const url = new URL(route.request().url())

    if (route.request().method() === 'GET' && url.pathname === '/notifications') {
      return fulfillJson(route, notifications)
    }

    if (route.request().method() === 'GET' && url.pathname === '/notifications/unread-count') {
      return fulfillJson(route, {
        unread_count: notifications.filter(isNotificationUnread).length,
      })
    }

    if (route.request().method() === 'PATCH' && url.pathname === '/notifications/read-all') {
      notifications[0] = { ...notifications[0], read_at: '2026-06-16T10:05:00.000Z' }
      return fulfillJson(route, { message: 'Notifications marked as read' })
    }

    return fulfillJson(route, { detail: 'Unhandled notification mock' }, 404)
  })

  await page.goto('/')

  await expect(page.getByRole('button', { name: /Notifications, 1 unread/ })).toBeVisible()

  await page.getByRole('button', { name: /Notifications/ }).click()
  await page.getByRole('button', { name: 'Mark all as read' }).click()

  await expect(page.getByRole('button', { name: 'Notifications' })).toBeVisible()
})

test('legacy is_read notifications use the correct read state', async ({ page }) => {
  const notifications = [
    {
      id: 'legacy-unread',
      type: 'game_created',
      title: 'Legacy unread',
      body: 'Unread legacy notification',
      is_read: false,
      created_at: '2026-06-16T10:00:00.000Z',
    },
    {
      id: 'legacy-read',
      type: 'game_created',
      title: 'Legacy read',
      body: 'Read legacy notification',
      is_read: true,
      created_at: '2026-06-16T09:00:00.000Z',
    },
  ]

  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/notifications.*/, (route) => {
    const url = new URL(route.request().url())

    if (route.request().method() === 'GET' && url.pathname === '/notifications') {
      return fulfillJson(route, notifications)
    }

    if (route.request().method() === 'GET' && url.pathname === '/notifications/unread-count') {
      return fulfillJson(route, {
        unread_count: notifications.filter(isNotificationUnread).length,
      })
    }

    if (route.request().method() === 'PATCH' && url.pathname === '/notifications/legacy-unread/read') {
      notifications[0] = { ...notifications[0], is_read: true }
      return fulfillJson(route, notifications[0])
    }

    return fulfillJson(route, { detail: 'Unhandled notification mock' }, 404)
  })

  await page.goto('/')
  await page.getByRole('button', { name: /Notifications/ }).click()

  await expect(page.getByText('1 unread')).toBeVisible()
  await expect(page.getByRole('button', { name: /Legacy read/ })).toContainText('Read')

  await page.getByRole('button', { name: /Legacy unread/ }).click()

  await expect(page.getByRole('button', { name: 'Notifications' })).toBeVisible()
})

test('notification preferences modal loads and saves settings', async ({ page }) => {
  let savedPayload
  let unreadCount = 0

  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/notifications.*/, (route) => {
    const url = new URL(route.request().url())

    if (route.request().method() === 'GET' && url.pathname === '/notifications') {
      return fulfillJson(route, [])
    }

    if (route.request().method() === 'GET' && url.pathname === '/notifications/unread-count') {
      return fulfillJson(route, { unread_count: unreadCount })
    }

    if (route.request().method() === 'GET' && url.pathname === '/notifications/preferences') {
      return fulfillJson(route, [
        {
          id: 'pref-city',
          notification_type: 'city',
          enabled: true,
          city: 'ירוחם',
        },
      ])
    }

    if (route.request().method() === 'PUT' && url.pathname === '/notifications/preferences') {
      savedPayload = route.request().postDataJSON()
      unreadCount = 1
      return fulfillJson(route, {
        message: 'Preferences saved',
        preferences: [],
      })
    }

    return fulfillJson(route, { detail: 'Unhandled notification mock' }, 404)
  })

  await page.goto('/')
  await page.getByRole('button', { name: 'Notification preferences' }).click()

  await expect(page.getByRole('heading', { name: 'Notification Preferences' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Test push' })).toHaveCount(0)

  await page.getByLabel('Distance notifications').uncheck()
  await page.getByRole('button', { name: 'Save' }).click()

  await expect(page.getByText('Notification preferences saved.')).toBeVisible()
  await expect(page.getByRole('button', { name: /Notifications, 1 unread/ })).toBeVisible()
  expect(savedPayload).toMatchObject({
    distance_enabled: false,
    city_enabled: true,
    city_name: 'ירוחם',
  })
})

test('scheduled game reminder notifications surface in the notification center and can be marked read', async ({
  page,
}) => {
  const notifications = [
    {
      id: 'scheduled-reminder-1',
      type: 'scheduled_game_reminder',
      title: 'תזכורת למשחק שמתקרב',
      body: 'המשחק שלך מתחיל בעוד שעה. אל תשכח להגיע בזמן.',
      read_at: null,
      game_id: 'game-scheduled-1',
      field_id: 'field-scheduled-1',
      data: {
        type: 'scheduled_game_reminder',
        game_id: 'game-scheduled-1',
        field_id: 'field-scheduled-1',
        scheduled_at: '2026-06-22T20:00:00+00:00',
      },
      created_at: '2026-06-22T19:00:00.000Z',
    },
  ]

  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/notifications.*/, (route) => {
    const url = new URL(route.request().url())

    if (route.request().method() === 'GET' && url.pathname === '/notifications') {
      return fulfillJson(route, notifications)
    }

    if (route.request().method() === 'GET' && url.pathname === '/notifications/unread-count') {
      return fulfillJson(route, {
        unread_count: notifications.filter(isNotificationUnread).length,
      })
    }

    if (
      route.request().method() === 'PATCH'
      && url.pathname === '/notifications/scheduled-reminder-1/read'
    ) {
      notifications[0] = { ...notifications[0], read_at: '2026-06-22T19:05:00.000Z' }
      return fulfillJson(route, notifications[0])
    }

    return fulfillJson(route, { detail: 'Unhandled notification mock' }, 404)
  })

  await page.goto('/')

  await expect(page.getByRole('button', { name: /Notifications, 1 unread/ })).toBeVisible()

  await page.getByRole('button', { name: /Notifications/ }).click()

  // Hebrew title + body from the scheduled reminder reach the existing inbox UI.
  await expect(page.getByRole('button', { name: /תזכורת למשחק שמתקרב/ })).toBeVisible()
  await expect(
    page.getByText('המשחק שלך מתחיל בעוד שעה. אל תשכח להגיע בזמן.'),
  ).toBeVisible()

  await page.getByRole('button', { name: /תזכורת למשחק שמתקרב/ }).click()

  // Clicking the reminder hits the existing read endpoint and clears the badge.
  await expect(page.getByRole('button', { name: 'Notifications' })).toBeVisible()
})
