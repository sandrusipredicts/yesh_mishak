import { expect, test } from '@playwright/test'

// These exercise the real dev build's Error Boundary via the dev-only
// window.__monitoringTest.triggerReactRenderError() hook (monitoring/
// TestCrashTrigger.jsx). No VITE_SENTRY_DSN is configured for this test
// run, so these tests also double as a live check that a missing Sentry
// configuration never breaks the fallback UI.

async function seedLanguage(page, language) {
  await page.addInitScript((lang) => {
    localStorage.setItem('app_language', lang)
    localStorage.setItem('language_selected', 'true')
  }, language)
}

test.describe('monitoring: React Error Boundary', () => {
  test('catches a render error, shows the English fallback, hides technical detail, and offers reload', async ({ page }) => {
    await seedLanguage(page, 'en')
    await page.goto('/')
    await page.waitForFunction(() => Boolean(window.__monitoringTest?.triggerReactRenderError))

    await page.evaluate(() => window.__monitoringTest.triggerReactRenderError())

    await expect(page.getByRole('heading', { name: 'Something went wrong' })).toBeVisible()
    await expect(page.getByText(/unexpected error occurred/)).toBeVisible()

    const bodyText = await page.locator('body').innerText()
    expect(bodyText).not.toMatch(/\.jsx:\d+|node_modules|at TestCrashTrigger|at ErrorBoundary/)

    await expect(page.getByRole('button', { name: 'Reload' })).toBeVisible()
  })

  test('shows the Hebrew fallback when the app language is Hebrew', async ({ page }) => {
    await seedLanguage(page, 'he')
    await page.goto('/')
    await page.waitForFunction(() => Boolean(window.__monitoringTest?.triggerReactRenderError))

    await page.evaluate(() => window.__monitoringTest.triggerReactRenderError())

    await expect(page.getByRole('heading', { name: 'משהו השתבש' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'טעינה מחדש' })).toBeVisible()
  })

  test('missing Sentry configuration does not break the fallback, and no fabricated event id is shown', async ({ page }) => {
    await seedLanguage(page, 'en')
    await page.goto('/')
    await page.waitForFunction(() => Boolean(window.__monitoringTest?.triggerReactRenderError))

    await page.evaluate(() => window.__monitoringTest.triggerReactRenderError())

    await expect(page.getByRole('heading', { name: 'Something went wrong' })).toBeVisible()
    // captureException() returns undefined when monitoring is disabled (no
    // DSN in this test environment) -- the event-id line must not render.
    await expect(page.locator('.error-boundary-fallback__event-id')).toHaveCount(0)
  })

  test('reload action recovers the app to a normal, non-crashed state', async ({ page }) => {
    await seedLanguage(page, 'en')
    await page.goto('/')
    await page.waitForFunction(() => Boolean(window.__monitoringTest?.triggerReactRenderError))

    await page.evaluate(() => window.__monitoringTest.triggerReactRenderError())
    await expect(page.getByRole('heading', { name: 'Something went wrong' })).toBeVisible()

    await page.getByRole('button', { name: 'Reload' }).click()
    await page.waitForLoadState('load')

    await expect(page.getByRole('heading', { name: 'Something went wrong' })).toHaveCount(0)
  })

  test('page stays responsive after the crash (no infinite render loop)', async ({ page }) => {
    await seedLanguage(page, 'en')
    await page.goto('/')
    await page.waitForFunction(() => Boolean(window.__monitoringTest?.triggerReactRenderError))

    await page.evaluate(() => window.__monitoringTest.triggerReactRenderError())
    await expect(page.getByRole('heading', { name: 'Something went wrong' })).toBeVisible()

    const result = await page.evaluate(() => 1 + 1)
    expect(result).toBe(2)
  })
})
