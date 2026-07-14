import { expect, test } from '@playwright/test'
import { Buffer } from 'node:buffer'

const user = {
  id: 'regular-user-1',
  email: 'user@example.com',
  name: 'Regular User',
}

const onePixelPng = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=',
  'base64',
)

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

async function seedAuthenticatedUser(page, language = 'en') {
  await page.addInitScript((storedUser) => {
    localStorage.setItem('access_token', storedUser.token)
    localStorage.setItem('currentUserId', storedUser.id)
    localStorage.setItem('currentUserName', storedUser.name)
    localStorage.setItem('currentUserEmail', storedUser.email)
    localStorage.setItem('onboarding_done', 'true')
    localStorage.setItem('app_language', storedUser.language)
    localStorage.setItem('language_selected', 'true')
  }, { ...user, language, token: makeJwtWithSubject(user.id) })
}

async function mockMapData(page) {
  await page.route(/\/fields\/?(\?.*)?$/, (route) => fulfillJson(route, []))
  await page.route(/\/notifications(\/.*)?(\?.*)?$/, (route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith('/unread-count')) {
      return fulfillJson(route, { unread_count: 0 })
    }
    return fulfillJson(route, [])
  })
}

async function fulfillTile(route) {
  await route.fulfill({
    status: 200,
    contentType: 'image/png',
    body: onePixelPng,
  })
}

test.beforeEach(async ({ page }) => {
  await seedAuthenticatedUser(page)
  await mockMapData(page)
})

test('shows an intentional tile loading state until the initial tiles load', async ({
  page,
}) => {
  let releaseTiles
  const tileGate = new Promise((resolve) => {
    releaseTiles = resolve
  })

  await page.route('**/*tile.openstreetmap.org/**', async (route) => {
    await tileGate
    await fulfillTile(route)
  })

  await page.goto('/')

  await expect(page.locator('.map-canvas')).toBeVisible()
  await expect(page.locator('.map-tile-loading')).toContainText('Loading map...')
  await page.locator('.leaflet-control-zoom-in').click()

  releaseTiles()

  await expect(page.locator('.map-tile-loading')).toHaveCount(0)
  await expect(page.locator('.map-tile-warning')).toHaveCount(0)
})

test('one failed tile does not show a global warning when other initial tiles load', async ({
  page,
}) => {
  let requestCount = 0
  await page.route('**/*tile.openstreetmap.org/**', async (route) => {
    requestCount += 1
    if (requestCount === 1) {
      await route.abort('failed')
      return
    }
    await fulfillTile(route)
  })

  await page.goto('/')

  await expect(page.locator('.map-tile-loading')).toHaveCount(0)
  await expect(page.locator('.map-tile-warning')).toHaveCount(0)
  expect(requestCount).toBeGreaterThan(1)
})

test('tile failures resolve the initial loading state to a small warning', async ({
  page,
}) => {
  await page.route('**/*tile.openstreetmap.org/**', (route) => route.abort('failed'))

  await page.goto('/')

  await expect(page.locator('.map-tile-loading')).toHaveCount(0)
  await expect(page.locator('.map-tile-warning')).toContainText(
    'Map tiles could not be loaded. Check your connection.',
  )
})

test('initial tile loading copy is localized in Hebrew', async ({ page }) => {
  await seedAuthenticatedUser(page, 'he')

  let releaseTiles
  const tileGate = new Promise((resolve) => {
    releaseTiles = resolve
  })

  await page.route('**/*tile.openstreetmap.org/**', async (route) => {
    await tileGate
    await fulfillTile(route)
  })

  await page.goto('/')

  await expect(page.locator('.map-tile-loading')).toContainText('טוען מפה...')
  releaseTiles()
  await expect(page.locator('.map-tile-loading')).toHaveCount(0)
})

test('panning after the first tile load does not show the initial overlay again', async ({
  page,
}) => {
  let holdFutureTiles = false
  let releaseFutureTiles
  let futureTileGate = Promise.resolve()

  await page.route('**/*tile.openstreetmap.org/**', async (route) => {
    if (holdFutureTiles) {
      await futureTileGate
    }
    await fulfillTile(route)
  })

  await page.goto('/')
  await expect(page.locator('.map-tile-loading')).toHaveCount(0)

  futureTileGate = new Promise((resolve) => {
    releaseFutureTiles = resolve
  })
  holdFutureTiles = true

  const mapBox = await page.locator('.map-canvas').boundingBox()
  await page.mouse.move(mapBox.x + mapBox.width / 2, mapBox.y + mapBox.height / 2)
  await page.mouse.down()
  await page.mouse.move(mapBox.x + mapBox.width / 2 + 180, mapBox.y + mapBox.height / 2)
  await page.mouse.up()

  await page.waitForTimeout(300)
  await expect(page.locator('.map-tile-loading')).toHaveCount(0)

  releaseFutureTiles()
})

test('reduced-motion users do not receive tile shimmer animation', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.route('**/*tile.openstreetmap.org/**', (route) => fulfillTile(route))

  await page.goto('/')

  await expect
    .poll(() =>
      page.evaluate(() => {
        const shimmer = document.querySelector('.map-tile-loading-shimmer')
        if (!shimmer) {
          return 'not-rendered'
        }
        return getComputedStyle(shimmer).animationName
      }),
    )
    .toBe('not-rendered')

  await expect
    .poll(() =>
      page.evaluate(() => {
        const probe = document.createElement('span')
        probe.className = 'map-tile-loading-shimmer'
        document.body.appendChild(probe)
        const animationName = getComputedStyle(probe).animationName
        probe.remove()
        return animationName
      }),
    )
    .toBe('none')
})
