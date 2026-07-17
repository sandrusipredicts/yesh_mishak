import { test } from '@playwright/test'
import { Buffer } from 'node:buffer'
import fs from 'node:fs'
import path from 'node:path'

const user = {
  id: 'regular-user-1',
  email: 'user@example.com',
  name: 'Regular User',
  role: 'user',
}

const baseCoordinates = {
  latitude: 31.225172,
  longitude: 34.777498,
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
    // E08-02 follow-up fix: account needs a resolved city to reach the map.
    localStorage.setItem('userCity', 'ירושלים')
    localStorage.setItem('app_language', 'en')
    localStorage.setItem('language_selected', 'true')
  }, { ...user, token: makeJwtWithSubject(user.id) })
}

async function mockGeolocation(page) {
  await page.addInitScript(({ latitude, longitude }) => {
    Object.defineProperty(navigator, 'geolocation', {
      configurable: true,
      value: {
        getCurrentPosition(success) {
          success({ coords: { latitude, longitude } })
        },
      },
    })
  }, baseCoordinates)
}

// Generate mock fields (50 fields)
const mockFields = Array.from({ length: 50 }, (_, i) => ({
  id: `field-${i}`,
  name: `Performance Field ${i}`,
  lat: baseCoordinates.latitude + (i * 0.0001), // Keep them very close so they are all in the viewport
  lng: baseCoordinates.longitude + (i * 0.0001),
  sport_type: 'football',
  surface_type: 'synthetic',
  has_nets: true,
  has_water_cooler: true,
  opening_hours: '08:00 - 22:00',
  notes: `Mock field notes for field ${i}`,
  status: 'approved',
  approval_status: 'approved',
  verified: true,
}))

// Generate mock notifications (30 notifications)
const mockNotifications = Array.from({ length: 30 }, (_, i) => ({
  id: `notification-${i}`,
  type: 'game_created',
  title: `Game Created ${i}`,
  body: `A football game was created at Performance Field ${i % 5}`,
  read_at: i >= 5 ? '2026-06-24T12:00:00.000Z' : null,
  is_read: i >= 5,
  game_id: `game-${i}`,
  field_id: `field-${i % 5}`,
  created_at: new Date(Date.now() - i * 60000).toISOString(),
}))

async function mockAllRequests(page) {
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/fields.*/, (route) => fulfillJson(route, mockFields))
  await page.route(/http:\/\/(localhost|127\.0\.0\.1):800[01]\/notifications.*/, (route) => {
    const url = new URL(route.request().url())
    if (url.pathname === '/notifications/unread-count') {
      return fulfillJson(route, { unread_count: mockNotifications.filter(n => !n.read_at && !n.is_read).length })
    }
    return fulfillJson(route, mockNotifications)
  })
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort())
}

function calculateStats(times) {
  const sorted = [...times].sort((a, b) => a - b)
  const min = sorted[0]
  const max = sorted[sorted.length - 1]
  const sum = sorted.reduce((a, b) => a + b, 0)
  const avg = sum / sorted.length
  
  // Median
  const mid = Math.floor(sorted.length / 2)
  const median = sorted.length % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2

  // P95
  const p95Idx = Math.max(0, Math.ceil(sorted.length * 0.95) - 1)
  const p95 = sorted[p95Idx]

  return {
    runs: times.length,
    min: Math.round(min),
    max: Math.round(max),
    avg: Math.round(avg),
    median: Math.round(median),
    p95: Math.round(p95)
  }
}

test.describe('Frontend Performance Measurement', () => {
  test.beforeEach(async ({ page }) => {
    await seedAuthenticatedUser(page)
    await mockGeolocation(page)
    await mockAllRequests(page)
  })

  test('measure all frontend metrics', async ({ page }) => {
    // Increase timeout for this multi-run benchmark
    test.setTimeout(120000)
    
    const RUNS = 20
    console.log(`Running performance measurements: ${RUNS} runs each...`)

    const initialAppLoadTimes = []
    const mapLoadTimes = []
    const fieldPanelOpenTimes = []
    const notificationLoadTimes = []

    // 1. Measure Initial App Load & Map Load in a loop of reloads
    for (let i = 0; i < RUNS; i++) {
      const navigationStart = Date.now()
      
      await page.goto('/')
      
      // Initial app load: Wait until auth toolbar or page skeleton is rendered
      await page.waitForSelector('.auth-toolbar')
      const appLoadTime = Date.now() - navigationStart
      initialAppLoadTimes.push(appLoadTime)

      // Map load: Wait until the field marker icons are rendered
      await page.waitForSelector('.field-marker-icon')
      const mapLoadTime = Date.now() - navigationStart
      mapLoadTimes.push(mapLoadTime)
    }

    // 2. Measure Field Panel Open (click marker -> panel open)
    for (let i = 0; i < RUNS; i++) {
      // Ensure panel is closed first
      const closeBtn = page.locator('.panel-close-button')
      if (await closeBtn.isVisible()) {
        await closeBtn.click()
        await page.waitForSelector('.field-details-panel', { state: 'hidden' })
      }

      const start = Date.now()
      const marker = page.locator('.field-marker-icon').first()
      await marker.click({ force: true })
      await page.waitForSelector('.field-details-panel')
      const duration = Date.now() - start
      fieldPanelOpenTimes.push(duration)
    }

    // 3. Measure Notification Load (click bell -> inbox modal open)
    for (let i = 0; i < RUNS; i++) {
      // Ensure notification modal is closed first
      const closeBtn = page.locator('.notifications-modal .modal-close-button')
      if (await closeBtn.isVisible()) {
        await closeBtn.click()
        await page.waitForSelector('.notifications-modal', { state: 'hidden' })
      }

      const start = Date.now()
      await page.locator('button[aria-label*="Notification"], button[aria-label*="התראות"]').first().click()
      await page.waitForSelector('.notifications-modal')
      const duration = Date.now() - start
      notificationLoadTimes.push(duration)
    }

    const report = {
      initial_app_load: calculateStats(initialAppLoadTimes),
      map_load: calculateStats(mapLoadTimes),
      field_panel_open: calculateStats(fieldPanelOpenTimes),
      notification_load: calculateStats(notificationLoadTimes),
    }

    console.log('Frontend Performance Measurements Done!')
    console.log(JSON.stringify(report, null, 2))

    // Ensure results dir exists
    const resultsDir = path.join(process.cwd(), 'test-results')
    if (!fs.existsSync(resultsDir)) {
      fs.mkdirSync(resultsDir, { recursive: true })
    }
    fs.writeFileSync(
      path.join(resultsDir, 'performance-results.json'),
      JSON.stringify(report, null, 2)
    )
  })
})
