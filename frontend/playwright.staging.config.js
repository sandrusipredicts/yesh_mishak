// E12-04 — dedicated Playwright configuration for the staging smoke suite.
//
// Deliberately separate from playwright.config.js: no dev-server bootstrap,
// its own test directory, its own report/output folders, and environment-
// driven target URLs (frontend/tests/staging/helpers.js). Run with:
//
//   npm run test:staging-smoke
//
// Required env: STAGING_FRONTEND_URL, STAGING_BACKEND_URL,
// PRODUCTION_BACKEND_HOSTS. Optional (enables Tier B): STAGING_TEST_EMAIL,
// STAGING_TEST_PASSWORD.

import process from 'node:process'
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/staging',
  testMatch: '**/*.smoke.spec.js',
  globalSetup: './tests/staging/global-setup.js',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  // The suite is read-only, but serialized workers keep runs deterministic and
  // rule out any parallel-interaction risk by construction.
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  forbidOnly: Boolean(process.env.CI),
  reporter: [
    ['list'],
    ['html', { outputFolder: 'playwright-report-staging', open: 'never' }],
  ],
  outputDir: 'test-results-staging',
  projects: [
    {
      name: 'staging-api',
      testMatch: '**/api.smoke.spec.js',
      // Tracing is intentionally OFF for the API project: traces record HTTP
      // request headers, and Tier B sends Authorization headers and login
      // credentials. Keeping traces off guarantees no secret material lands
      // in artifacts.
      use: { trace: 'off', screenshot: 'off', video: 'off' },
    },
    {
      name: 'staging-browser',
      testMatch: '**/frontend.smoke.spec.js',
      use: {
        ...devices['Desktop Chrome'],
        trace: 'retain-on-failure',
        screenshot: 'only-on-failure',
        video: 'off',
      },
    },
  ],
})
