import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import path from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import {
  DEV_BACKEND_URL,
  DEV_FRONTEND_URL,
  REQUIRED_PRODUCTION_BACKEND_HOST,
  loadConfig,
} from './helpers.js'

function baseEnv(overrides = {}) {
  return {
    STAGING_FRONTEND_URL: DEV_FRONTEND_URL,
    STAGING_BACKEND_URL: DEV_BACKEND_URL,
    PRODUCTION_BACKEND_HOSTS: REQUIRED_PRODUCTION_BACKEND_HOST,
    ...overrides,
  }
}

test('local runs accept the exact dev pair and skip Tier B without credentials', () => {
  const config = loadConfig(baseEnv())

  assert.equal(config.frontendUrl, DEV_FRONTEND_URL)
  assert.equal(config.backendUrl, DEV_BACKEND_URL)
  assert.equal(config.tierB.enabled, false)
})

test('local runs accept an all-loopback rehearsal pair', () => {
  const config = loadConfig(baseEnv({
    STAGING_FRONTEND_URL: 'http://127.0.0.1:5173',
    STAGING_BACKEND_URL: 'http://localhost:8000',
  }))

  assert.equal(config.frontendHost, '127.0.0.1')
  assert.equal(config.backendHost, 'localhost')
})

test('local runs reject arbitrary external or mixed target pairs', () => {
  assert.throws(
    () => loadConfig(baseEnv({ STAGING_BACKEND_URL: 'https://example.invalid' })),
    /Refusing arbitrary external or mixed targets/,
  )
  assert.throws(
    () => loadConfig(baseEnv({ STAGING_BACKEND_URL: 'http://127.0.0.1:8000' })),
    /Refusing arbitrary external or mixed targets/,
  )
})

test('CI accepts only the exact isolated dev pair', () => {
  const config = loadConfig(baseEnv({ CI: 'true', STAGING_SMOKE_TIER: 'tier-a' }))
  assert.equal(config.backendUrl, DEV_BACKEND_URL)

  assert.throws(
    () => loadConfig(baseEnv({
      CI: 'true',
      STAGING_SMOKE_TIER: 'tier-a',
      STAGING_FRONTEND_URL: 'http://127.0.0.1:5173',
      STAGING_BACKEND_URL: 'http://127.0.0.1:8000',
    })),
    /CI targets must be exactly/,
  )
})

test('partial credentials fail in every execution mode', () => {
  assert.throws(
    () => loadConfig(baseEnv({ STAGING_TEST_EMAIL: 'synthetic@example.invalid' })),
    /must be provided together/,
  )
  assert.throws(
    () => loadConfig(baseEnv({ STAGING_TEST_PASSWORD: 'non-secret-test-value' })),
    /must be provided together/,
  )
})

test('CI without credentials fails before combined or Tier B execution', () => {
  assert.throws(
    () => loadConfig(baseEnv({ CI: 'true' })),
    /are required in CI/,
  )
  assert.throws(
    () => loadConfig(baseEnv({ CI: 'true', STAGING_SMOKE_TIER: 'tier-b' })),
    /are required in CI/,
  )
})

test('CI Tier A may run without credentials after workflow preflight', () => {
  const config = loadConfig(baseEnv({ CI: 'true', STAGING_SMOKE_TIER: 'tier-a' }))
  assert.equal(config.tierB.enabled, false)
})

test('a full credential pair enables Tier B without exposing values in errors', () => {
  const config = loadConfig(baseEnv({
    STAGING_TEST_EMAIL: 'synthetic@example.invalid',
    STAGING_TEST_PASSWORD: 'non-secret-test-value',
  }))

  assert.equal(config.tierB.enabled, true)
})

test('configuration failures never echo email or password values', () => {
  const email = 'credential-sentinel@example.invalid'
  const password = 'credential-password-sentinel'

  assert.throws(
    () => loadConfig(baseEnv({
      STAGING_BACKEND_URL: 'https://example.invalid',
      STAGING_TEST_EMAIL: email,
      STAGING_TEST_PASSWORD: password,
    })),
    (error) => {
      assert.equal(String(error).includes(email), false)
      assert.equal(String(error).includes(password), false)
      return true
    },
  )
})

test('runner rejects partial credentials without echoing the supplied value', () => {
  const email = 'runner-sentinel@example.invalid'
  const testDirectory = path.dirname(fileURLToPath(import.meta.url))
  const frontendDirectory = path.resolve(testDirectory, '..', '..')
  const result = spawnSync(
    process.execPath,
    ['scripts/run-staging-smoke.mjs', '--tier-b'],
    {
      cwd: frontendDirectory,
      env: { STAGING_TEST_EMAIL: email },
      encoding: 'utf8',
    },
  )

  assert.equal(result.status, 1)
  assert.match(result.stderr, /must be provided together/)
  assert.equal(result.stderr.includes(email), false)
})

test('the canonical production backend cannot be omitted from the denylist', () => {
  assert.throws(
    () => loadConfig(baseEnv({ PRODUCTION_BACKEND_HOSTS: 'old-placeholder.example' })),
    /must include yeshmishak-production\.up\.railway\.app/,
  )
})
