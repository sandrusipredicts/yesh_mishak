// Pure configuration-resolution helpers for the monitoring module. No SDK
// calls happen here so this file can be unit tested without mocking
// @sentry/capacitor.

export const LOCAL_ENVIRONMENT = 'local'
export const DEVELOPMENT_ENVIRONMENT = 'development'
export const BRANCH_BUILD_ENVIRONMENT = 'branch-build'
export const PRODUCTION_ENVIRONMENT = 'production'

const UNKNOWN_RELEASE = 'unknown'

/**
 * Environment naming is deployment-driven, not guessed at runtime: CI/Vercel/
 * Railway set VITE_SENTRY_ENVIRONMENT explicitly for anything that isn't a
 * plain local dev server. Absent that, a Vite dev server run is 'local' and
 * any other build defaults to 'development' -- never 'production' -- so an
 * unlabeled preview/branch build can never be mistaken for production traffic.
 */
export function resolveEnvironment({ explicitEnvironment, isDevServer } = {}) {
  const trimmed = (explicitEnvironment || '').trim()
  if (trimmed) {
    return trimmed
  }
  return isDevServer ? LOCAL_ENVIRONMENT : DEVELOPMENT_ENVIRONMENT
}

/**
 * The release string is computed by CI (yesh-mishak@<version>+<sha>, or the
 * deterministic yesh-mishak@<short-sha> interim format when only a commit
 * SHA is available) and injected via VITE_SENTRY_RELEASE. The app never
 * fabricates a version number itself.
 */
export function resolveRelease({ explicitRelease } = {}) {
  const trimmed = (explicitRelease || '').trim()
  return trimmed || UNKNOWN_RELEASE
}

/**
 * dist differentiates the platform build under a shared release. CI may
 * inject a precise value (e.g. android-<versionCode>); absent that, fall
 * back to the coarse platform name so events are still distinguishable.
 */
export function resolveDist({ explicitDist, platform } = {}) {
  const trimmed = (explicitDist || '').trim()
  if (trimmed) {
    return trimmed
  }
  return platform || undefined
}

/**
 * Collection policy: enabled automatically in any non-local deployed build
 * that has a DSN configured; disabled by default for local development
 * unless an explicit local override is set for integration testing.
 */
export function isMonitoringEnabled({ dsn, environment, localOverrideEnabled } = {}) {
  if (!dsn || !String(dsn).trim()) {
    return false
  }
  if (environment === LOCAL_ENVIRONMENT) {
    return Boolean(localOverrideEnabled)
  }
  return true
}

/**
 * Gate for the manual-verification test triggers (monitoring/index.js's
 * window.__monitoringTest). Two independent conditions must both hold:
 *
 *   1. The resolved environment must not be 'production' -- a hard gate
 *      that the opt-in flag below can NEVER bypass, checked first and
 *      unconditionally, regardless of what testTriggerEnabled/isDevServer
 *      are set to. This is what guarantees a flag accidentally left on
 *      (or a misconfigured production build) still can never expose the
 *      triggers in production.
 *   2. Either the app is running under the Vite dev server, or an explicit
 *      build-time opt-in (VITE_SENTRY_TEST_TRIGGER_ENABLED=true) was set --
 *      this is how a dedicated non-production branch-build APK enables the
 *      triggers for a physical-device manual verification pass without
 *      also enabling them in a production build.
 *
 * Pure and side-effect-free so both conditions are independently unit
 * testable without needing to mock @sentry/capacitor or a bundler env.
 */
export function isTestTriggerAllowed({ environment, isDevServer, testTriggerEnabled } = {}) {
  if (environment === PRODUCTION_ENVIRONMENT) {
    return false
  }
  return Boolean(isDevServer) || testTriggerEnabled === true
}
