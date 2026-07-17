import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

const adminUser = {
  id: 'admin-user-1',
  email: 'admin@example.com',
  name: 'Admin User',
  role: 'admin',
}

const adminStats = {
  verified_fields: 12,
  pending_fields: 3,
  active_games: 4,
  total_users: 25,
}

const monitoringData = {
  status: 'ok',
  generated_at: '2026-07-15T12:00:00.000Z',
  active_games: { count: 4, source: 'database' },
  active_users: {
    last_24h: 7,
    last_7d: 14,
    total_registered: 25,
    source: 'database',
  },
  notifications: {
    created_last_24h: 5,
    unread_total: 2,
    source: 'database',
  },
  moderation: { pending_fields: 3, source: 'database' },
  database: { healthy: true, error_type: null },
  api_errors: {
    source_available: true,
    source: 'database',
    window_minutes: 60,
    window_started_at: '2026-07-15T11:00:00.000Z',
    window_ended_at: '2026-07-15T12:00:00.000Z',
    total_requests: 10,
    failed_requests: 2,
    error_rate: 0.2,
  },
  response_time: {
    source_available: true,
    source: 'database',
    window_minutes: 60,
    window_started_at: '2026-07-15T11:00:00.000Z',
    window_ended_at: '2026-07-15T12:00:00.000Z',
    sample_count: 4,
    average_ms: 325,
    p50_ms: 150,
    p95_ms: 880,
    max_ms: 1000,
  },
  scheduled_jobs: {
    source_available: true,
    source: 'database',
    job_name: 'game_expiry_reconciliation',
    latest_status: 'succeeded',
    latest_started_at: '2026-07-15T11:55:00.000Z',
    latest_finished_at: '2026-07-15T11:55:22.000Z',
    recent_runs: [
      {
        id: 'job-run-1',
        status: 'succeeded',
        started_at: '2026-07-15T11:55:00.000Z',
        finished_at: '2026-07-15T11:55:22.000Z',
        duration_ms: 22,
        processed_count: 6,
        failed_count: 0,
      },
    ],
  },
  push_notifications: {
    source_available: true,
    source: 'database',
    semantics: 'provider_acceptance',
    window_minutes: 60,
    window_started_at: '2026-07-15T11:00:00.000Z',
    window_ended_at: '2026-07-15T12:00:00.000Z',
    attempted_count: 5,
    accepted_count: 2,
    failed_count: 2,
    invalid_token_count: 1,
    acceptance_rate: 0.4,
  },
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
    localStorage.setItem('userCity', 'ירושלים') // E08-02 follow-up fix: account needs a resolved city to reach the map
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  }, { ...adminUser, token: makeJwtWithSubject(adminUser.id) })
}

async function mockAdminApi(page, { monitoringHandler } = {}) {
  await page.route('**/admin/**', async (route) => {
    const url = new URL(route.request().url())

    if (!url.pathname.startsWith('/admin/')) {
      return route.continue()
    }

    if (url.pathname === '/admin/me') {
      return fulfillJson(route, adminUser)
    }

    if (url.pathname === '/admin/stats') {
      return fulfillJson(route, adminStats)
    }

    if (url.pathname === '/admin/monitoring') {
      if (monitoringHandler) {
        return monitoringHandler(route)
      }

      return fulfillJson(route, monitoringData)
    }

    return fulfillJson(route, {})
  })
}

async function openMonitoring(page) {
  await page.goto('/admin')
  const monitoringButton = page.getByRole('button', { name: 'Monitoring', exact: true })
  await expect(monitoringButton).toHaveCount(1)
  await monitoringButton.click()
}

test.beforeEach(async ({ page }) => {
  await seedAuthenticatedUser(page)
})

test('monitoring tab shows a deliberate loading state', async ({ page }) => {
  let releaseMonitoring
  const monitoringPending = new Promise((resolve) => {
    releaseMonitoring = resolve
  })

  await mockAdminApi(page, {
    monitoringHandler: async (route) => {
      await monitoringPending
      return fulfillJson(route, monitoringData)
    },
  })

  await openMonitoring(page)

  await expect(page.getByText('Loading monitoring data...', { exact: true })).toBeVisible()
  releaseMonitoring()
  await expect(page.getByText('Completed API requests', { exact: true })).toBeVisible()
})

test('admin monitoring renders exact aggregate values and accurate push semantics', async ({ page }) => {
  await mockAdminApi(page)
  await openMonitoring(page)

  await expect(page.getByText('Monitoring window: last 60 minutes', { exact: true })).toBeVisible()
  await expect(page.getByText('10', { exact: true })).toBeVisible()
  await expect(page.getByText('20.0%', { exact: true })).toBeVisible()
  await expect(page.getByText('325.0', { exact: true })).toBeVisible()
  await expect(page.getByText('150.0', { exact: true })).toBeVisible()
  await expect(page.getByText('880.0', { exact: true })).toBeVisible()
  await expect(page.getByText('1,000.0', { exact: true })).toBeVisible()
  await expect(page.getByText('Provider accepted', { exact: true })).toBeVisible()
  await expect(page.getByText(/not that a device received it/)).toBeVisible()
  await expect(page.locator('.admin-monitoring-job-summary strong').filter({ hasText: 'Succeeded' })).toBeVisible()
  await expect(page.getByText('Backend data (UTC): Jul 15, 2026, 12:00 PM', { exact: true })).toBeVisible()
})

test('valid zero and empty monitoring values are not shown as errors', async ({ page }) => {
  await mockAdminApi(page, {
    monitoringHandler: async (route) => fulfillJson(route, {
      ...monitoringData,
      api_errors: { ...monitoringData.api_errors, total_requests: 0, failed_requests: 0, error_rate: 0 },
      response_time: { ...monitoringData.response_time, sample_count: 0, average_ms: 0, p50_ms: 0, p95_ms: 0, max_ms: 0 },
      scheduled_jobs: { ...monitoringData.scheduled_jobs, recent_runs: [], latest_status: null },
      push_notifications: {
        ...monitoringData.push_notifications,
        attempted_count: 0,
        accepted_count: 0,
        failed_count: 0,
        invalid_token_count: 0,
        acceptance_rate: 0,
      },
    }),
  })
  await openMonitoring(page)

  await expect(page.getByText('No completed API requests were recorded in this window.', { exact: true })).toBeVisible()
  await expect(page.getByText('No terminal push send attempts were recorded in this window.', { exact: true })).toBeVisible()
  await expect(page.getByText('No job runs have been recorded yet.', { exact: true })).toBeVisible()
  await expect(page.getByText('20.0%', { exact: true })).toHaveCount(0)
  await expect(page.getByText('0.0%', { exact: true })).toBeVisible()
  await expect(page.getByText('Monitoring could not be loaded. Check the backend and try again.', { exact: true })).toHaveCount(0)
})

test('partial monitoring sources remain visible without hiding available metrics', async ({ page }) => {
  await mockAdminApi(page, {
    monitoringHandler: async (route) => fulfillJson(route, {
      ...monitoringData,
      response_time: undefined,
      push_notifications: { source_available: false },
      scheduled_jobs: { source_available: false },
    }),
  })
  await openMonitoring(page)

  await expect(page.getByText('Completed API requests', { exact: true })).toBeVisible()
  await expect(page.getByText('This monitoring source is temporarily unavailable.', { exact: true })).toHaveCount(3)
  await expect(page.getByText('Monitoring could not be loaded. Check the backend and try again.', { exact: true })).toHaveCount(0)
})

test('monitoring API errors show a retry action and recover', async ({ page }) => {
  let attempts = 0
  await mockAdminApi(page, {
    monitoringHandler: async (route) => {
      attempts += 1
      if (attempts === 1) {
        return fulfillJson(route, { detail: 'temporary failure' }, 500)
      }

      return fulfillJson(route, monitoringData)
    },
  })
  await openMonitoring(page)

  await expect(page.getByText('Monitoring could not be loaded. Check the backend and try again.', { exact: true })).toBeVisible()
  const retryButton = page.getByRole('button', { name: 'Retry', exact: true })
  await expect(retryButton).toHaveCount(1)
  await retryButton.click()
  await expect(page.getByText('Completed API requests', { exact: true })).toBeVisible()
  expect(attempts).toBe(2)
})

test('manual refresh prevents overlapping requests', async ({ page }) => {
  let attempts = 0
  let releaseRefresh
  const refreshPending = new Promise((resolve) => {
    releaseRefresh = resolve
  })

  await mockAdminApi(page, {
    monitoringHandler: async (route) => {
      attempts += 1
      if (attempts === 2) {
        await refreshPending
      }

      return fulfillJson(route, monitoringData)
    },
  })
  await openMonitoring(page)

  await expect(page.getByText('Completed API requests', { exact: true })).toBeVisible()
  const refreshButton = page.getByRole('button', { name: 'Refresh monitoring', exact: true })
  await refreshButton.click()
  await expect(page.getByRole('button', { name: 'Refreshing...', exact: true })).toBeDisabled()
  expect(attempts).toBe(2)
  releaseRefresh()
  await expect(page.getByRole('button', { name: 'Refresh monitoring', exact: true })).toBeEnabled()
})

test('expired admin session is reported without exposing backend details', async ({ page }) => {
  await mockAdminApi(page, {
    monitoringHandler: async (route) => fulfillJson(route, { detail: 'expired token internals' }, 401),
  })
  await openMonitoring(page)

  await expect(page.getByText('Your admin session has expired. Sign in again to view monitoring.', { exact: true })).toBeVisible()
  await expect(page.getByText('expired token internals', { exact: true })).toHaveCount(0)
  expect(await page.evaluate(() => localStorage.getItem('access_token'))).toBeNull()
})

test('monitoring remains usable on a narrow viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await mockAdminApi(page)
  await openMonitoring(page)

  await expect(page.getByRole('heading', { name: 'Monitoring', exact: true })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})
