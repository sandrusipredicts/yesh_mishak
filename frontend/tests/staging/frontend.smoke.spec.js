// E12-04 staging smoke suite — frontend tier (Chromium).
//
// Read-only checks that the deployed staging frontend is a real application
// deployment, boots without fatal errors, talks to the staging backend (and
// never to production), and serves the public legal routes.

import { test, expect } from '@playwright/test'
import {
  ALLOWED_CONSOLE_ERROR_PATTERNS,
  hostnameOf,
  loadConfig,
  safeUrl,
} from './helpers.js'

const cfg = loadConfig()

function isAllowedConsoleNoise(text) {
  return ALLOWED_CONSOLE_ERROR_PATTERNS.some((pattern) => pattern.test(text))
}

test('[frontend-availability] GET / serves the application document', async ({ request }) => {
  const response = await request.get(`${cfg.frontendUrl}/`)
  expect(
    response.status(),
    '[frontend-availability] staging frontend did not answer GET / with HTTP 200',
  ).toBe(200)

  const finalHost = hostnameOf(response.url())
  expect(
    finalHost,
    `[frontend-availability] request was redirected off the staging host to `
    + `${safeUrl(response.url())}`,
  ).toBe(cfg.frontendHost)

  const contentType = response.headers()['content-type'] ?? ''
  expect(
    contentType.includes('text/html'),
    `[frontend-availability] expected an HTML document, got content-type "${contentType}"`,
  ).toBe(true)

  const body = await response.text()
  expect(
    body.includes('id="root"'),
    '[frontend-availability] response HTML does not contain the application root '
    + 'element — this does not look like the built app document',
  ).toBe(true)
  for (const marker of ['DEPLOYMENT_NOT_FOUND', 'Home of the Railway API']) {
    expect(
      body.includes(marker),
      `[frontend-availability] response contains the infrastructure placeholder `
      + `marker "${marker}" — the staging deployment is missing`,
    ).toBe(false)
  }
})

test('[frontend-boot] application boots without fatal errors', async ({ page }) => {
  const pageErrors = []
  const consoleErrors = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') {
      consoleErrors.push(message.text())
    }
  })

  await page.goto(`${cfg.frontendUrl}/`, { waitUntil: 'domcontentloaded' })
  await expect(
    page.locator('#root > *').first(),
    '[frontend-boot] the application root stayed empty — the JS bundle did not '
    + 'mount (HTML loaded but the app crashed or failed to start)',
  ).toBeVisible({ timeout: 20_000 })

  expect(
    pageErrors,
    '[frontend-boot] uncaught page errors during boot',
  ).toEqual([])

  const fatalConsoleErrors = consoleErrors.filter((text) => !isAllowedConsoleNoise(text))
  expect(
    fatalConsoleErrors,
    '[frontend-boot] unexpected console errors during boot (allowlisted '
    + 'third-party noise is documented in docs/qa/staging-smoke-tests.md)',
  ).toEqual([])
})

test('[frontend-wiring] deployed bundle targets the staging backend only', async ({ page, request }) => {
  // The API base URL is baked into the JS bundle at build time
  // (frontend/src/api/client.js reads VITE_API_URL via import.meta.env), and a
  // fresh anonymous visit can legitimately make zero API calls (onboarding
  // gate before the map mounts). So positive wiring is proven by inspecting
  // the served bundle, not by waiting for traffic that may never come.
  const htmlResponse = await request.get(`${cfg.frontendUrl}/`)
  expect(
    htmlResponse.status(),
    '[frontend-wiring] could not fetch the app document to inspect its bundle',
  ).toBe(200)
  const html = await htmlResponse.text()

  const assetPaths = [...html.matchAll(/(?:src|href)="(\/assets\/[^"]+\.js)"/g)]
    .map((match) => match[1])
  expect(
    assetPaths.length,
    '[frontend-wiring] the app document references no JS bundle assets — this '
    + 'does not look like the built application',
  ).toBeGreaterThan(0)

  let combinedBundle = ''
  for (const assetPath of assetPaths) {
    const assetResponse = await request.get(`${cfg.frontendUrl}${assetPath}`)
    expect(
      assetResponse.status(),
      `[frontend-wiring] failed to fetch bundle asset ${assetPath}`,
    ).toBe(200)
    combinedBundle += await assetResponse.text()
  }

  const hostUrlPattern = (host) =>
    new RegExp(`https?://${host.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}(?=[/:'"\`]|$)`, 'i')
  const bakedProductionHosts = cfg.productionHosts.filter((host) =>
    hostUrlPattern(host).test(combinedBundle),
  )
  expect(
    bakedProductionHosts,
    '[frontend-wiring] PRODUCTION backend host(s) are baked into the deployed '
    + 'bundle — the frontend was built with a production VITE_API_URL',
  ).toEqual([])
  expect(
    combinedBundle.includes(cfg.backendOrigin),
    `[frontend-wiring] the staging backend origin ${cfg.backendOrigin} does not `
    + 'appear in the deployed bundle — the frontend is not wired to '
    + 'STAGING_BACKEND_URL (absence is a failure, not a pass)',
  ).toBe(true)

  // Belt-and-braces runtime observation: whatever the app does during a short
  // boot window, none of it may reach a production host.
  const runtimeOffenders = []
  page.on('request', (pageRequest) => {
    if (cfg.productionHosts.includes(hostnameOf(pageRequest.url()))) {
      runtimeOffenders.push(safeUrl(pageRequest.url()))
    }
  })
  await page.goto(`${cfg.frontendUrl}/`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(3_000)
  expect(
    runtimeOffenders,
    '[frontend-wiring] the running app sent requests to PRODUCTION hosts',
  ).toEqual([])
})

for (const route of ['/privacy', '/terms']) {
  test(`[frontend-legal] ${route} renders meaningful content`, async ({ page }) => {
    const pageErrors = []
    page.on('pageerror', (error) => pageErrors.push(error.message))

    const response = await page.goto(`${cfg.frontendUrl}${route}`, {
      waitUntil: 'domcontentloaded',
    })
    expect(
      response?.status(),
      `[frontend-legal] ${route} did not return HTTP 200`,
    ).toBe(200)

    await expect(
      page.locator('#root > *').first(),
      `[frontend-legal] ${route} rendered an empty application root`,
    ).toBeVisible({ timeout: 20_000 })

    const text = (await page.locator('body').innerText()).trim()
    expect(
      text.length,
      `[frontend-legal] ${route} rendered no meaningful text content`,
    ).toBeGreaterThan(40)

    expect(
      pageErrors,
      `[frontend-legal] uncaught page errors on ${route}`,
    ).toEqual([])
  })
}
