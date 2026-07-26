import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const CONFIG_PREFIX = '[staging-smoke:config]'
const PLAYWRIGHT_CLI = fileURLToPath(
  new URL('../node_modules/@playwright/test/cli.js', import.meta.url),
)
const requestedMode = process.argv[2] ?? 'all'

if (!new Set(['all', '--tier-a', '--tier-b']).has(requestedMode)) {
  console.error(`${CONFIG_PREFIX} runner mode must be all, --tier-a, or --tier-b`)
  process.exit(1)
}

const emailPresent = Boolean((process.env.STAGING_TEST_EMAIL ?? '').trim())
const passwordPresent = Boolean(process.env.STAGING_TEST_PASSWORD ?? '')
const ci = ['1', 'true'].includes(String(process.env.CI ?? '').trim().toLowerCase())
  || String(process.env.GITHUB_ACTIONS ?? '').trim().toLowerCase() === 'true'

if (emailPresent !== passwordPresent) {
  console.error(
    `${CONFIG_PREFIX} STAGING_TEST_EMAIL and STAGING_TEST_PASSWORD must be `
    + 'provided together (or both omitted for a local Tier B skip).',
  )
  process.exit(1)
}
if (ci && requestedMode !== '--tier-a' && !emailPresent) {
  console.error(
    `${CONFIG_PREFIX} STAGING_TEST_EMAIL and STAGING_TEST_PASSWORD are required `
    + 'in CI before authenticated Tier B tests can run.',
  )
  process.exit(1)
}

function runPlaywright(tier, extraArgs, includeCredentials) {
  const childEnv = { ...process.env, STAGING_SMOKE_TIER: tier }
  if (!includeCredentials) {
    delete childEnv.STAGING_TEST_EMAIL
    delete childEnv.STAGING_TEST_PASSWORD
  }

  const result = spawnSync(
    process.execPath,
    [PLAYWRIGHT_CLI, 'test', '--config', 'playwright.staging.config.js', ...extraArgs],
    {
      cwd: process.cwd(),
      env: childEnv,
      stdio: 'inherit',
    },
  )
  if (result.error) {
    console.error(`${CONFIG_PREFIX} Playwright runner could not be started`)
    return 1
  }
  return result.status ?? 1
}

if (requestedMode === 'all' || requestedMode === '--tier-a') {
  const tierAStatus = runPlaywright('tier-a', ['--grep-invert', 'Tier B'], false)
  if (tierAStatus !== 0) {
    process.exit(tierAStatus)
  }
}

if (requestedMode === 'all' || requestedMode === '--tier-b') {
  const tierBStatus = runPlaywright(
    'tier-b',
    ['--project', 'staging-api', '--grep', 'Tier B'],
    true,
  )
  process.exit(tierBStatus)
}
