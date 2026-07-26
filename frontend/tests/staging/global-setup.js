// E12-04 staging smoke suite — global setup.
//
// 1. Validates the environment contract before any test runs (fail fast on
//    missing/malformed configuration).
// 2. Runs a bounded readiness poll against both staging targets so a
//    Railway/Vercel cold start does not fail individual tests. The poll fails
//    the whole run — with a component-attributed error — once the window is
//    exhausted; it never retries indefinitely.

import { request } from '@playwright/test'
import { loadConfig } from './helpers.js'

const DEFAULT_READINESS_TIMEOUT_MS = 90_000
const POLL_INTERVAL_MS = 5_000
const PER_REQUEST_TIMEOUT_MS = 10_000

function readinessTimeoutMs() {
  const raw = Number.parseInt(process.env.STAGING_READINESS_TIMEOUT_MS ?? '', 10)
  if (Number.isFinite(raw) && raw >= 1_000 && raw <= 600_000) {
    return raw
  }
  return DEFAULT_READINESS_TIMEOUT_MS
}

async function pollUntilReady(context, component, url, timeoutMs) {
  const deadline = Date.now() + timeoutMs
  let lastResult

  for (;;) {
    try {
      const response = await context.get(url, { timeout: PER_REQUEST_TIMEOUT_MS })
      if (response.status() === 200) {
        return
      }
      lastResult = `HTTP ${response.status()}`
    } catch (error) {
      lastResult = `request failed (${error.message.split('\n')[0]})`
    }
    if (Date.now() + POLL_INTERVAL_MS > deadline) {
      throw new Error(
        `${component} staging target ${url} was not ready within `
        + `${Math.round(timeoutMs / 1000)}s (last result: ${lastResult}). `
        + 'If this is a cold start, raise STAGING_READINESS_TIMEOUT_MS; '
        + 'otherwise the environment is down.',
      )
    }
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS))
  }
}

export default async function globalSetup() {
  const cfg = loadConfig()
  const timeoutMs = readinessTimeoutMs()
  const context = await request.newContext()
  try {
    await pollUntilReady(
      context,
      '[staging-smoke:backend-availability]',
      `${cfg.backendUrl}/`,
      timeoutMs,
    )
    await pollUntilReady(
      context,
      '[staging-smoke:frontend-availability]',
      `${cfg.frontendUrl}/`,
      timeoutMs,
    )
  } finally {
    await context.dispose()
  }
}
