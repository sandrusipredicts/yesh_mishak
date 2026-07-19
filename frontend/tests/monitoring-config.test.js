import assert from 'node:assert/strict'
import test from 'node:test'

import {
  BRANCH_BUILD_ENVIRONMENT,
  DEVELOPMENT_ENVIRONMENT,
  LOCAL_ENVIRONMENT,
  PRODUCTION_ENVIRONMENT,
  isMonitoringEnabled,
  isTestTriggerAllowed,
  resolveDist,
  resolveEnvironment,
  resolveRelease,
} from '../src/monitoring/config.js'

test('resolveEnvironment: dev server with no explicit override resolves to local', () => {
  assert.equal(
    resolveEnvironment({ explicitEnvironment: undefined, isDevServer: true }),
    LOCAL_ENVIRONMENT,
  )
})

test('resolveEnvironment: production-mode build with no explicit override defaults to development, never production', () => {
  assert.equal(
    resolveEnvironment({ explicitEnvironment: undefined, isDevServer: false }),
    DEVELOPMENT_ENVIRONMENT,
  )
})

test('resolveEnvironment: explicit CI-injected value always wins', () => {
  assert.equal(
    resolveEnvironment({ explicitEnvironment: BRANCH_BUILD_ENVIRONMENT, isDevServer: true }),
    BRANCH_BUILD_ENVIRONMENT,
  )
  assert.equal(
    resolveEnvironment({ explicitEnvironment: PRODUCTION_ENVIRONMENT, isDevServer: false }),
    PRODUCTION_ENVIRONMENT,
  )
})

test('resolveEnvironment: blank/whitespace explicit value falls back to the heuristic default', () => {
  assert.equal(
    resolveEnvironment({ explicitEnvironment: '   ', isDevServer: false }),
    DEVELOPMENT_ENVIRONMENT,
  )
})

test('resolveRelease: never fabricates a version when unset', () => {
  assert.equal(resolveRelease({ explicitRelease: undefined }), 'unknown')
  assert.equal(resolveRelease({ explicitRelease: '' }), 'unknown')
})

test('resolveRelease: uses the CI-injected value verbatim', () => {
  assert.equal(
    resolveRelease({ explicitRelease: 'yesh-mishak@1.2.3+abc1234' }),
    'yesh-mishak@1.2.3+abc1234',
  )
})

test('resolveDist: explicit value wins over platform fallback', () => {
  assert.equal(resolveDist({ explicitDist: 'android-42', platform: 'android' }), 'android-42')
})

test('resolveDist: falls back to the coarse platform name', () => {
  assert.equal(resolveDist({ explicitDist: undefined, platform: 'ios' }), 'ios')
})

test('isMonitoringEnabled: disabled without a DSN regardless of environment', () => {
  assert.equal(
    isMonitoringEnabled({ dsn: '', environment: PRODUCTION_ENVIRONMENT, localOverrideEnabled: true }),
    false,
  )
  assert.equal(
    isMonitoringEnabled({ dsn: undefined, environment: PRODUCTION_ENVIRONMENT }),
    false,
  )
})

test('isMonitoringEnabled: local development is disabled by default even with a DSN', () => {
  assert.equal(
    isMonitoringEnabled({ dsn: 'https://example.invalid/1', environment: LOCAL_ENVIRONMENT, localOverrideEnabled: false }),
    false,
  )
})

test('isMonitoringEnabled: local development can be explicitly opted in for integration testing', () => {
  assert.equal(
    isMonitoringEnabled({ dsn: 'https://example.invalid/1', environment: LOCAL_ENVIRONMENT, localOverrideEnabled: true }),
    true,
  )
})

test('isMonitoringEnabled: any non-local deployed environment with a DSN is enabled automatically', () => {
  for (const environment of [DEVELOPMENT_ENVIRONMENT, BRANCH_BUILD_ENVIRONMENT, PRODUCTION_ENVIRONMENT]) {
    assert.equal(
      isMonitoringEnabled({ dsn: 'https://example.invalid/1', environment, localOverrideEnabled: false }),
      true,
      `expected ${environment} to be enabled`,
    )
  }
})

// --- isTestTriggerAllowed: the window.__monitoringTest exposure gate ---
// (E09-01 branch-build APK manual-verification fix)

test('isTestTriggerAllowed: production is blocked even when the opt-in flag is true', () => {
  assert.equal(
    isTestTriggerAllowed({
      environment: PRODUCTION_ENVIRONMENT,
      isDevServer: false,
      testTriggerEnabled: true,
    }),
    false,
  )
})

test('isTestTriggerAllowed: production is blocked even when running under a dev server', () => {
  // Not a realistic combination in practice, but the production check must
  // be unconditional -- it must not depend on isDevServer either.
  assert.equal(
    isTestTriggerAllowed({
      environment: PRODUCTION_ENVIRONMENT,
      isDevServer: true,
      testTriggerEnabled: true,
    }),
    false,
  )
})

test('isTestTriggerAllowed: a branch-build with the opt-in flag set is allowed', () => {
  assert.equal(
    isTestTriggerAllowed({
      environment: BRANCH_BUILD_ENVIRONMENT,
      isDevServer: false,
      testTriggerEnabled: true,
    }),
    true,
  )
})

test('isTestTriggerAllowed: a branch-build WITHOUT the opt-in flag is blocked (the pre-fix gap)', () => {
  assert.equal(
    isTestTriggerAllowed({
      environment: BRANCH_BUILD_ENVIRONMENT,
      isDevServer: false,
      testTriggerEnabled: false,
    }),
    false,
  )
})

test('isTestTriggerAllowed: any non-production environment is allowed under the dev server regardless of the flag', () => {
  for (const environment of [LOCAL_ENVIRONMENT, DEVELOPMENT_ENVIRONMENT, BRANCH_BUILD_ENVIRONMENT]) {
    assert.equal(
      isTestTriggerAllowed({ environment, isDevServer: true, testTriggerEnabled: false }),
      true,
      `expected ${environment} to be allowed under the dev server`,
    )
  }
})

test('isTestTriggerAllowed: development environment respects the same flag-based gate as branch-build', () => {
  assert.equal(
    isTestTriggerAllowed({ environment: DEVELOPMENT_ENVIRONMENT, isDevServer: false, testTriggerEnabled: true }),
    true,
  )
  assert.equal(
    isTestTriggerAllowed({ environment: DEVELOPMENT_ENVIRONMENT, isDevServer: false, testTriggerEnabled: false }),
    false,
  )
})
