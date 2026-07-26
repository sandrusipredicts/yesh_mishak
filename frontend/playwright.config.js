import process from 'node:process'
import { defineConfig, devices } from '@playwright/test'

process.env.VITE_API_URL = 'http://127.0.0.1:8000'

export default defineConfig({
  testDir: './tests',
  testMatch: '**/*.spec.js',
  // Staging smoke tests (E12-04) run only via playwright.staging.config.js;
  // keep them out of the default local/CI E2E discovery.
  testIgnore: '**/staging/**',
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:5173',
    locale: 'en-US',
    screenshot: 'off',
    // Authenticated fixtures represent established users that already
    // accepted the community terms. Terms-specific tests explicitly
    // override or remove this value to cover new and legacy sessions.
    storageState: {
      cookies: [],
      origins: [{
        origin: 'http://127.0.0.1:5173',
        localStorage: [{ name: 'currentUserTermsAccepted', value: 'true' }],
      }],
    },
    trace: 'off',
    video: 'off',
  },
  webServer: process.env.PLAYWRIGHT_SKIP_WEB_SERVER ? undefined : {
    command: 'npm run dev -- --host 127.0.0.1 --port 5173',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: !process.env.CI,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'], locale: 'en-US' },
    },
  ],
})
