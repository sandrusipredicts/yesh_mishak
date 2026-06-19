import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

function fulfillJson(route, body, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  })
}

async function seedAuthenticatedUser(page, user) {
  const storedUser = {
    ...user,
    token: user.token?.includes('.') ? user.token : makeJwtWithSubject(user.id),
  }

  await page.addInitScript((storedUser) => {
    localStorage.setItem('access_token', storedUser.token)
    localStorage.setItem('currentUserId', storedUser.storedId || storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.setItem('onboarding_done', 'true')
  }, storedUser)

  user.token = storedUser.token
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

async function mockSharedRequests(page, fields) {
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/fields.*/, (route) => fulfillJson(route, fields))
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/notifications.*/, (route) => {
    const url = new URL(route.request().url())

    if (url.pathname === '/notifications/unread-count') {
      return fulfillJson(route, { unread_count: 0 })
    }

    return fulfillJson(route, [])
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
}

function makeFieldWithActiveGame(createdBy, participants = []) {
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
        participants,
      },
    },
  ]
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

function makeScheduledGame(createdBy = 'organizer-user', participants = []) {
  return {
    ...makeActiveGame(createdBy, participants),
    id: 'scheduled-game-1',
    scheduled_at: '2099-06-17T18:30:00.000Z',
    started_at: '2099-06-17T18:30:00.000Z',
    expires_at: '2099-06-17T20:30:00.000Z',
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

    if (url.pathname === '/fields/') {
      return fulfillJson(route, [field])
    }

    if (url.pathname === `/fields/${field.id}`) {
      return fulfillJson(route, field)
    }

    return fulfillJson(route, { detail: 'Unhandled field mock' }, 404)
  })
}

test('non-organizer does not see the close game button', async ({ page }) => {
  let closeRequestCount = 0

  await seedAuthenticatedUser(page, {
    id: 'current-user',
    email: 'current@example.com',
    name: 'Current User',
    token: 'current-token',
  })
  await mockSharedRequests(page, makeFieldWithActiveGame('organizer-user'))
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/games\/game-1\/close/, (route) => {
    closeRequestCount += 1
    return fulfillJson(route, { detail: 'Forbidden' }, 403)
  })

  await page.goto('/')
  await page.locator('.field-marker').first().click()

  await expect(page.getByRole('button', { name: 'Close game' })).toHaveCount(0)
  expect(closeRequestCount).toBe(0)
})

test('non-organizer token subject cannot see or trigger close with stale organizer localStorage', async ({ page }) => {
  let closeRequestCount = 0
  const tokenUserId = 'current-user'
  const organizerId = 'organizer-user'

  await seedAuthenticatedUser(page, {
    id: tokenUserId,
    storedId: organizerId,
    email: 'current@example.com',
    name: 'Current User',
    token: makeJwtWithSubject(tokenUserId),
  })
  await mockSharedRequests(page, makeFieldWithActiveGame(organizerId))
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/games\/game-1\/close/, (route) => {
    closeRequestCount += 1
    return fulfillJson(route, { detail: 'Forbidden' }, 403)
  })

  await page.goto('/')
  await page.locator('.field-marker').first().click()

  await expect(page.getByRole('button', { name: 'Close game' })).toHaveCount(0)
  expect(closeRequestCount).toBe(0)
})

test('organizer sees the close game button', async ({ page }) => {
  const user = {
    id: 'organizer-user',
    email: 'organizer@example.com',
    name: 'Organizer User',
    token: makeJwtWithSubject('organizer-user'),
  }

  await seedAuthenticatedUser(page, user)
  await mockSharedRequests(page, makeFieldWithActiveGame(user.id))

  await page.goto('/')
  await page.locator('.field-marker').first().click()

  await expect(page.getByRole('button', { name: 'Close game' })).toBeVisible()
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
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/games\/game-1\/close/, (route) => {
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
  expect(closeRequest.headers().authorization).toBe(`Bearer ${user.token}`)
  expect(closeRequest.postData() ?? '').toBe('')
})

test('participant sees leave and leave request refreshes fields', async ({ page }) => {
  const user = {
    id: 'c7ea7af7-cf92-43a6-a553-6b44a5b7004e',
    email: 'participant@example.com',
    name: 'Participant User',
    token: 'participant-token',
  }
  let leaveRequest
  let fieldRequestCount = 0
  const fields = makeFieldWithActiveGame('organizer-user', [
    {
      user_id: user.id,
      name: 'אוראל דהן',
    },
  ])

  await seedAuthenticatedUser(page, user)
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/fields.*/, (route) => {
    fieldRequestCount += 1
    return fulfillJson(route, fields)
  })
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/notifications.*/, (route) => {
    const url = new URL(route.request().url())

    if (url.pathname === '/notifications/unread-count') {
      return fulfillJson(route, { unread_count: 0 })
    }

    return fulfillJson(route, [])
  })
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/games\/game-1\/leave/, (route) => {
    leaveRequest = route.request()
    return fulfillJson(route, {
      message: 'Left successfully',
      game: { id: 'game-1', status: 'open' },
    })
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())

  await page.goto('/')
  await page.locator('.field-marker').first().click()

  await expect(page.getByRole('button', { name: 'Leave' })).toBeVisible()
  await expect(page.getByRole('button', { name: "I'm coming" })).toHaveCount(0)

  await page.getByRole('button', { name: 'Leave' }).click()

  await expect.poll(() => leaveRequest?.method()).toBe('POST')
  expect(leaveRequest.headers().authorization).toBe(`Bearer ${user.token}`)
  await expect.poll(() => fieldRequestCount).toBeGreaterThan(1)
})

test('participant detection uses token subject with user_id participants', async ({ page }) => {
  const currentUserId = 'c7ea7af7-cf92-43a6-a553-6b44a5b7004e'
  const user = {
    id: currentUserId,
    storedId: 'stale-local-storage-user',
    email: 'participant@example.com',
    name: 'Participant User',
    token: makeJwtWithSubject(currentUserId),
  }
  const fields = makeFieldWithActiveGame('organizer-user', [
    {
      user_id: currentUserId,
      name: 'אוראל דהן',
    },
  ])

  await seedAuthenticatedUser(page, user)
  await mockSharedRequests(page, fields)

  await page.goto('/')
  await page.locator('.field-marker').first().click()

  await expect(page.getByRole('button', { name: 'Leave' })).toBeVisible()
  await expect(page.getByRole('button', { name: "I'm coming" })).toHaveCount(0)
})

test('participants list toggles inside the game panel', async ({ page }) => {
  const user = {
    id: 'organizer-user',
    email: 'organizer@example.com',
    name: 'Organizer User',
  }

  await seedAuthenticatedUser(page, user)
  await mockSharedRequests(page, makeFieldWithActiveGame(user.id, [
    {
      user_id: user.id,
      username: 'Marom',
    },
    {
      user_id: 'participant-2',
      username: 'Avi',
    },
  ]))

  await page.goto('/')
  await page.locator('.field-marker').first().click()

  const toggle = page.getByRole('button', { name: 'Participants (2)' })
  await expect(toggle).toBeVisible()
  await expect(page.getByRole('list', { name: 'Participants' })).toHaveCount(0)

  await toggle.click()
  await expect(page.getByRole('list', { name: 'Participants' })).toBeVisible()
  await expect(page.getByText('Marom')).toBeVisible()
  await expect(page.getByText('Avi', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Participants (2)' }).click()
  await expect(page.getByRole('list', { name: 'Participants' })).toHaveCount(0)
})

test('participants list shows fallback when username is missing', async ({ page }) => {
  const user = {
    id: 'organizer-user',
    email: 'organizer@example.com',
    name: 'Organizer User',
  }

  await seedAuthenticatedUser(page, user)
  await mockSharedRequests(page, makeFieldWithActiveGame(user.id, [
    {
      user_id: user.id,
      username: '',
      name: '',
    },
  ]))

  await page.goto('/')
  await page.locator('.field-marker').first().click()
  await page.getByRole('button', { name: 'Participants (1)' }).click()

  await expect(page.getByRole('list', { name: 'Participants' })).toContainText('User')
})

test('user-specific participant state follows each jwt subject', async ({ page }) => {
  const userAId = 'user-a'
  const userBId = 'user-b'

  await seedAuthenticatedUser(page, {
    id: userAId,
    storedId: userBId,
    email: 'a@example.com',
    name: 'User A',
  })
  await mockSharedRequests(page, makeFieldWithActiveGame('organizer-user', [
    {
      user_id: userAId,
      name: 'User A',
    },
  ]))

  await page.goto('/')
  await page.locator('.field-marker').first().click()

  await expect(page.getByRole('button', { name: 'Leave' })).toBeVisible()
  await expect(page.getByRole('button', { name: "I'm coming" })).toHaveCount(0)
})

test('different jwt user sees join until their own participant row exists', async ({ page }) => {
  const userAId = 'user-a'
  const userBId = 'user-b'

  await seedAuthenticatedUser(page, {
    id: userBId,
    storedId: userAId,
    email: 'b@example.com',
    name: 'User B',
  })
  await mockSharedRequests(page, makeFieldWithActiveGame('organizer-user', [
    {
      user_id: userAId,
      name: 'User A',
    },
  ]))

  await page.goto('/')
  await page.locator('.field-marker').first().click()

  await expect(page.getByRole('button', { name: "I'm coming" })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Leave' })).toHaveCount(0)
})

test('joining a game refreshes the opened participants list', async ({ page }) => {
  const user = {
    id: 'current-user',
    email: 'current@example.com',
    name: 'Current User',
    token: 'current-token',
  }
  let participants = [
    {
      user_id: 'organizer-user',
      username: 'Marom',
    },
  ]

  await seedAuthenticatedUser(page, user)
  await mockFieldState(page, () =>
    makeField({
      ...makeActiveGame('organizer-user', participants),
      players_present: participants.length,
    }),
  )
  await mockNotificationsAndTiles(page)
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/games\/game-1\/join/, (route) => {
    participants = [
      ...participants,
      {
        user_id: user.id,
        username: 'Avi',
      },
    ]
    return fulfillJson(route, {
      message: 'Joined successfully',
      game: { id: 'game-1', status: 'open' },
    })
  })

  await page.goto('/')
  await page.locator('.field-marker').first().click()
  await page.getByRole('button', { name: 'Participants (1)' }).click()
  await expect(page.getByText('Marom')).toBeVisible()

  await page.getByRole('button', { name: "I'm coming" }).click()

  await expect(page.getByRole('button', { name: 'Participants (2)' })).toBeVisible()
  await expect(page.getByText('Avi', { exact: true })).toBeVisible()
})

test('leaving a game refreshes the opened participants list', async ({ page }) => {
  const user = {
    id: 'current-user',
    email: 'current@example.com',
    name: 'Current User',
    token: 'current-token',
  }
  let participants = [
    {
      user_id: 'organizer-user',
      username: 'Marom',
    },
    {
      user_id: user.id,
      username: 'Avi',
    },
  ]

  await seedAuthenticatedUser(page, user)
  await mockFieldState(page, () =>
    makeField({
      ...makeActiveGame('organizer-user', participants),
      players_present: participants.length,
    }),
  )
  await mockNotificationsAndTiles(page)
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/games\/game-1\/leave/, (route) => {
    participants = participants.filter((participant) => participant.user_id !== user.id)
    return fulfillJson(route, {
      message: 'Left successfully',
      game: { id: 'game-1', status: 'open' },
    })
  })

  await page.goto('/')
  await page.locator('.field-marker').first().click()
  await page.getByRole('button', { name: 'Participants (2)' }).click()
  await expect(page.getByText('Avi', { exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Leave' }).click()

  await expect(page.getByRole('button', { name: 'Participants (1)' })).toBeVisible()
  await expect(page.getByText('Avi', { exact: true })).toHaveCount(0)
  await expect(page.getByText('Marom')).toBeVisible()
})

test('non-participant sees im coming and join request refreshes fields', async ({ page }) => {
  const user = {
    id: 'current-user',
    email: 'current@example.com',
    name: 'Current User',
    token: 'current-token',
  }
  let joinRequest
  let fieldRequestCount = 0
  const fields = makeFieldWithActiveGame('organizer-user', [
    {
      user_id: 'other-user',
      name: 'Other User',
    },
  ])

  await seedAuthenticatedUser(page, user)
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/fields.*/, (route) => {
    fieldRequestCount += 1
    return fulfillJson(route, fields)
  })
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/notifications.*/, (route) => {
    const url = new URL(route.request().url())

    if (url.pathname === '/notifications/unread-count') {
      return fulfillJson(route, { unread_count: 0 })
    }

    return fulfillJson(route, [])
  })
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/games\/game-1\/join/, (route) => {
    joinRequest = route.request()
    return fulfillJson(route, {
      message: 'Joined successfully',
      game: { id: 'game-1', status: 'open' },
    })
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())

  await page.goto('/')
  await page.locator('.field-marker').first().click()

  await expect(page.getByRole('button', { name: "I'm coming" })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Leave' })).toHaveCount(0)

  await page.getByRole('button', { name: "I'm coming" }).click()

  await expect.poll(() => joinRequest?.method()).toBe('POST')
  expect(joinRequest.headers().authorization).toBe(`Bearer ${user.token}`)
  await expect.poll(() => fieldRequestCount).toBeGreaterThan(1)
})

test('existing active game displays open state and hides open game button', async ({ page }) => {
  await seedAuthenticatedUser(page, {
    id: 'current-user',
    email: 'current@example.com',
    name: 'Current User',
    token: 'current-token',
  })
  await mockFieldState(page, () => makeField(makeActiveGame()))
  await mockNotificationsAndTiles(page)

  await page.goto('/')
  await page.locator('.field-marker').first().click()

  await expect(page.getByText('Active game: open')).toBeVisible()
  await expect(page.getByRole('button', { name: "I'm coming" })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Open Game' })).toHaveCount(0)
})

test('future scheduled game shows upcoming join flow without active controls', async ({ page }) => {
  await seedAuthenticatedUser(page, {
    id: 'current-user',
    email: 'current@example.com',
    name: 'Current User',
    token: 'current-token',
  })
  await mockFieldState(page, () => ({
    ...makeField(null),
    upcoming_games: [makeScheduledGame()],
  }))
  await mockNotificationsAndTiles(page)

  await page.goto('/')
  await page.locator('.field-marker').first().click()

  await expect(page.getByRole('heading', { name: 'Upcoming games' })).toBeVisible()
  await expect(page.getByText('Scheduled')).toBeVisible()
  await expect(page.getByRole('button', { name: "I'm coming" })).toBeVisible()
  await expect(page.getByText('Ends in')).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Extra round' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Close game' })).toHaveCount(0)
  await expect(page.getByRole('button', { name: 'Open Game' })).toBeVisible()
})

test('after close game selected field refreshes to no active game', async ({ page }) => {
  const user = {
    id: 'organizer-user',
    email: 'organizer@example.com',
    name: 'Organizer User',
    token: 'organizer-token',
  }
  let isActive = true

  await seedAuthenticatedUser(page, user)
  await mockFieldState(page, () => makeField(isActive ? makeActiveGame(user.id) : null))
  await mockNotificationsAndTiles(page)
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/games\/game-1\/close/, (route) => {
    isActive = false
    return fulfillJson(route, {
      message: 'Game closed',
      game: { id: 'game-1', status: 'finished' },
    })
  })

  await page.goto('/')
  await page.locator('.field-marker').first().click()

  await expect(page.getByRole('button', { name: 'Close game' })).toBeVisible()
  page.once('dialog', (dialog) => dialog.accept())
  await page.getByRole('button', { name: 'Close game' }).click()

  await expect(page.getByRole('button', { name: 'Open Game' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Close game' })).toHaveCount(0)
})

test('after open game selected field refreshes to active game', async ({ page }) => {
  const user = {
    id: 'organizer-user',
    email: 'organizer@example.com',
    name: 'Organizer User',
    token: 'organizer-token',
  }
  let isActive = false

  await seedAuthenticatedUser(page, user)
  await mockFieldState(page, () =>
    makeField(
      isActive
        ? makeActiveGame(user.id, [
            {
              user_id: user.id,
              name: user.name,
            },
          ])
        : null,
    ),
  )
  await mockNotificationsAndTiles(page)
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/games\//, (route) => {
    isActive = true
    return fulfillJson(route, {
      message: 'Game created',
      game: makeActiveGame(user.id),
    })
  })

  await page.goto('/')
  await page.locator('.field-marker').first().click()

  await page.getByRole('button', { name: 'Open Game' }).click()
  await page
    .getByRole('dialog', { name: 'Open Game' })
    .getByRole('button', { name: 'Open Game' })
    .click()

  await expect(page.getByRole('button', { name: 'Close game' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Open Game' })).toHaveCount(0)
})
