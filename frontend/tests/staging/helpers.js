// E12-04/E12-05 staging smoke suite — shared environment contract.
//
// CI is pinned to the isolated dev targets. Local runs may use that exact pair
// or an all-loopback pair for rehearsal; arbitrary external and mixed target
// pairs are rejected before any request is sent.

const CONFIG_PREFIX = '[staging-smoke:config]'
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '[::1]'])
const SMOKE_TIERS = new Set(['', 'tier-a', 'tier-b'])

export const DEV_FRONTEND_URL = 'https://dev-yesh-mishak.vercel.app'
export const DEV_BACKEND_URL = 'https://yeshmishak-dev.up.railway.app'
export const REQUIRED_PRODUCTION_BACKEND_HOST = 'yeshmishak-production.up.railway.app'

export const REQUIRED_VARS = [
  'STAGING_FRONTEND_URL',
  'STAGING_BACKEND_URL',
  'PRODUCTION_BACKEND_HOSTS',
]

export const TIER_B_SKIP_REASON =
  'Tier B skipped: STAGING_TEST_EMAIL and STAGING_TEST_PASSWORD are not both set. '
  + 'Provide the dedicated synthetic staging test account via GitHub environment '
  + 'secrets (or local env vars) to enable authenticated smoke tests.'

// Console-error noise explicitly documented as harmless third-party behavior
// (docs/qa/staging-smoke-tests.md). Everything else fails the boot test.
export const ALLOWED_CONSOLE_ERROR_PATTERNS = [
  /tile\.openstreetmap\.org/i, // OSM tile fetch failures are third-party availability, not app health
  /favicon/i,
  /ERR_BLOCKED_BY_CLIENT/i, // local ad-block style interference on developer machines
]

function fail(message) {
  throw new Error(`${CONFIG_PREFIX} ${message}`)
}

function parseBaseUrl(name, raw) {
  const trimmed = (raw ?? '').trim()
  if (!trimmed) {
    fail(`${name} is empty`)
  }
  let url
  try {
    url = new URL(trimmed)
  } catch {
    fail(`${name} is not a valid URL`)
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    fail(`${name} must use http(s)`)
  }
  if (url.username || url.password) {
    fail(`${name} must not contain embedded credentials`)
  }
  if (url.search || url.hash) {
    fail(`${name} must not contain a query string or fragment`)
  }
  if (url.pathname !== '/') {
    fail(`${name} must be a root origin without a path prefix`)
  }
  return { base: url.origin, origin: url.origin, hostname: url.hostname.toLowerCase() }
}

function isCi(env) {
  const ci = String(env.CI ?? '').trim().toLowerCase()
  const githubActions = String(env.GITHUB_ACTIONS ?? '').trim().toLowerCase()
  return ci === 'true' || ci === '1' || githubActions === 'true'
}

function validateTargetPair(frontend, backend, env) {
  const exactDevPair =
    frontend.base === DEV_FRONTEND_URL
    && backend.base === DEV_BACKEND_URL
  const loopbackPair =
    LOOPBACK_HOSTS.has(frontend.hostname)
    && LOOPBACK_HOSTS.has(backend.hostname)

  if (isCi(env) && !exactDevPair) {
    fail(
      `CI targets must be exactly ${DEV_FRONTEND_URL} and ${DEV_BACKEND_URL}. `
      + 'Refusing to contact any other environment.',
    )
  }
  if (!isCi(env) && !exactDevPair && !loopbackPair) {
    fail(
      'Local targets must be either the exact isolated dev pair or an all-loopback pair. '
      + 'Refusing arbitrary external or mixed targets.',
    )
  }
}

/**
 * Reads and validates the staging smoke environment contract.
 * Throws a `[staging-smoke:config]` error listing every problem it can name.
 */
export function loadConfig(env = process.env) {
  const missing = REQUIRED_VARS.filter((name) => !(env[name] ?? '').trim())
  if (missing.length > 0) {
    fail(
      `missing required environment variable(s): ${missing.join(', ')}. `
      + 'Set STAGING_FRONTEND_URL, STAGING_BACKEND_URL and PRODUCTION_BACKEND_HOSTS '
      + '(see docs/qa/staging-smoke-tests.md). No defaults are applied.',
    )
  }

  const frontend = parseBaseUrl('STAGING_FRONTEND_URL', env.STAGING_FRONTEND_URL)
  const backend = parseBaseUrl('STAGING_BACKEND_URL', env.STAGING_BACKEND_URL)
  validateTargetPair(frontend, backend, env)

  const productionHosts = env.PRODUCTION_BACKEND_HOSTS
    .split(',')
    .map((h) => h.trim().toLowerCase())
    .filter(Boolean)
  if (productionHosts.length === 0) {
    fail('PRODUCTION_BACKEND_HOSTS must contain at least one hostname (comma-separated)')
  }
  for (const host of productionHosts) {
    if (host.includes('/') || host.includes(':')) {
      fail(`PRODUCTION_BACKEND_HOSTS entries must be bare hostnames, got "${host}"`)
    }
  }
  if (!productionHosts.includes(REQUIRED_PRODUCTION_BACKEND_HOST)) {
    fail(
      `PRODUCTION_BACKEND_HOSTS must include ${REQUIRED_PRODUCTION_BACKEND_HOST} `
      + 'so frontend wiring checks cannot omit the canonical production backend.',
    )
  }

  if (productionHosts.includes(backend.hostname)) {
    fail(
      `STAGING_BACKEND_URL host "${backend.hostname}" matches an entry in `
      + 'PRODUCTION_BACKEND_HOSTS. Refusing to run the smoke suite against production.',
    )
  }
  if (productionHosts.includes(frontend.hostname)) {
    fail(
      `STAGING_FRONTEND_URL host "${frontend.hostname}" matches an entry in `
      + 'PRODUCTION_BACKEND_HOSTS. Refusing to run the smoke suite against production.',
    )
  }

  const email = (env.STAGING_TEST_EMAIL ?? '').trim()
  const password = env.STAGING_TEST_PASSWORD ?? ''
  const smokeTier = (env.STAGING_SMOKE_TIER ?? '').trim().toLowerCase()
  if (!SMOKE_TIERS.has(smokeTier)) {
    fail('STAGING_SMOKE_TIER must be empty, "tier-a", or "tier-b"')
  }
  if ((email && !password) || (!email && password)) {
    fail(
      'STAGING_TEST_EMAIL and STAGING_TEST_PASSWORD must be provided together '
      + '(or both omitted to skip Tier B).',
    )
  }
  if (isCi(env) && smokeTier !== 'tier-a' && !email && !password) {
    fail(
      'STAGING_TEST_EMAIL and STAGING_TEST_PASSWORD are required in CI before '
      + 'authenticated Tier B tests can run.',
    )
  }

  return {
    frontendUrl: frontend.base,
    frontendOrigin: frontend.origin,
    frontendHost: frontend.hostname,
    backendUrl: backend.base,
    backendOrigin: backend.origin,
    backendHost: backend.hostname,
    productionHosts,
    smokeTier,
    tierB: { enabled: Boolean(email && password), email, password },
  }
}

/**
 * Renders a URL for failure output without exposing query-string or fragment
 * content (which could carry tokens or other secrets).
 */
export function safeUrl(rawUrl) {
  try {
    const url = new URL(rawUrl)
    return `${url.origin}${url.pathname}`
  } catch {
    return '<unparseable url>'
  }
}

export function hostnameOf(rawUrl) {
  try {
    return new URL(rawUrl).hostname.toLowerCase()
  } catch {
    return ''
  }
}
