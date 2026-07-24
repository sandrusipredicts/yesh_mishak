// E12-04 staging smoke suite — shared environment contract.
//
// All configuration comes from environment variables. Nothing here may fall
// back to localhost or to a production URL: a missing or malformed value must
// abort the run with a clearly attributed configuration error before any
// request is sent.

const CONFIG_PREFIX = '[staging-smoke:config]'

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
    fail(`${name} is not a valid URL: "${trimmed}"`)
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    fail(`${name} must use http(s), got protocol "${url.protocol}" in "${trimmed}"`)
  }
  if (url.search || url.hash) {
    fail(`${name} must not contain a query string or fragment: "${trimmed}"`)
  }
  // Normalize: origin plus any path prefix, without a trailing slash.
  const base = `${url.origin}${url.pathname}`.replace(/\/+$/, '')
  return { base, origin: url.origin, hostname: url.hostname.toLowerCase() }
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
  if ((email && !password) || (!email && password)) {
    fail(
      'STAGING_TEST_EMAIL and STAGING_TEST_PASSWORD must be provided together '
      + '(or both omitted to skip Tier B).',
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
