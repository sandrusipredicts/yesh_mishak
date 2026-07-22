import { expect, test } from '@playwright/test'

const CURRENT_USER_ID = '11111111-1111-4111-8111-111111111111'
const OTHER_USER_ID = '22222222-2222-4222-8222-222222222222'
const GAME_ID = '33333333-3333-4333-8333-333333333333'
const FIELD_ID = '44444444-4444-4444-8444-444444444444'

function makeJwt(subject) {
  const encode = (value) => Buffer.from(JSON.stringify(value)).toString('base64url')
  return `${encode({ alg: 'none' })}.${encode({ sub: subject })}.signature`
}

function fulfillJson(route, body, status = 200) {
  return route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })
}

async function prepareApp(page) {
  await page.addInitScript(({ userId, token }) => {
    localStorage.setItem('language_selected', 'true')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('userCity', 'ירושלים')
    localStorage.setItem('access_token', token)
    localStorage.setItem('currentUserId', userId)
    localStorage.setItem('currentUserName', 'Current User')
    localStorage.setItem('currentUserEmail', 'current@example.com')
    localStorage.setItem('currentUserTermsAccepted', 'true')
  }, { userId: CURRENT_USER_ID, token: makeJwt(CURRENT_USER_ID) })

  const field = {
    id: FIELD_ID,
    name: 'Safety Test Field',
    lat: 30.9872,
    lng: 34.9314,
    sport_type: 'football',
    approval_status: 'approved',
    status: 'open',
    active_game: {
      id: GAME_ID,
      field_id: FIELD_ID,
      created_by: OTHER_USER_ID,
      status: 'open',
      sport_type: 'football',
      players_present: 2,
      max_players: 10,
      age_note: 'Community note',
      participants: [
        { user_id: CURRENT_USER_ID, name: 'Current User' },
        { user_id: OTHER_USER_ID, name: 'Other User' },
      ],
    },
    upcoming_games: [],
  }

  await page.route(/\/fields\/?(\?.*)?$/, (route) => fulfillJson(route, [field]))
  await page.route('**/games/me', (route) => fulfillJson(route, {
    active_games: [],
    upcoming_games: [],
    past_games: [],
    cancelled_games: [],
  }))
  await page.route(/\/notifications(?:\/|\?|$)/, (route) => fulfillJson(route, []))
  await page.route('**/moderation/blocks', (route) => fulfillJson(route, { blocked_user_ids: [] }))
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
}

test('game and user reporting are clearly labeled and user blocking hides identity', async ({ page }) => {
  await prepareApp(page)
  let reportBody
  let blockedUserId

  await page.route('**/moderation/reports', (route) => {
    reportBody = route.request().postDataJSON()
    return fulfillJson(route, { message: 'Report submitted', report_id: 'report-1' }, 201)
  })
  await page.route(`**/moderation/blocks/${OTHER_USER_ID}`, (route) => {
    blockedUserId = OTHER_USER_ID
    return fulfillJson(route, { message: 'User blocked', blocked_user_id: OTHER_USER_ID }, 201)
  })

  await page.goto('/')
  await page.locator('.field-marker').first().click()

  await expect(page.getByRole('button', { name: 'Report game' })).toBeVisible()
  await page.getByRole('button', { name: 'Participants (2)' }).click()
  await expect(page.getByRole('button', { name: 'Report user' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Block user' })).toBeVisible()

  await page.getByRole('button', { name: 'Report user' }).click()
  await page.getByLabel('Reason').selectOption('harassment')
  await page.getByLabel('Additional details (optional)').fill('Repeated harassment')
  await page.getByRole('button', { name: 'Submit report' }).click()

  expect(reportBody).toEqual({
    target_type: 'user',
    target_id: OTHER_USER_ID,
    reason: 'harassment',
    description: 'Repeated harassment',
  })
  await expect(page.getByText('Report submitted for moderation.')).toBeVisible()

  await page.getByRole('button', { name: 'Block user' }).click()
  await page.locator('.confirm-modal').getByRole('button', { name: 'Block user' }).click()

  expect(blockedUserId).toBe(OTHER_USER_ID)
  await expect(page.getByText('Blocked user', { exact: true })).toBeVisible()
  await expect(page.getByText('Content from a blocked user is hidden.')).toBeVisible()
})
