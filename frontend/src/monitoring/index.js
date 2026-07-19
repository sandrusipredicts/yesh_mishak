// Centralized monitoring entry point. This is the ONLY module that imports
// @sentry/capacitor directly -- everywhere else in the app calls the
// re-exported helpers below, so Sentry usage never scatters across
// unrelated components.
//
// Platform-neutral by design: the only platform-specific read anywhere in
// this file is Capacitor.getPlatform(), used solely to tag `dist` when CI
// hasn't already injected a precise one. There is no Android-only branch --
// Android and iOS both go through the exact same init() call, which is what
// lets @sentry/capacitor's bundled native layers (sentry-android / Sentry
// Cocoa) activate identically on both platforms.
import * as Sentry from '@sentry/capacitor'
import { App as CapacitorApp } from '@capacitor/app'
import { Capacitor } from '@capacitor/core'

import {
  isMonitoringEnabled,
  isTestTriggerAllowed,
  resolveDist,
  resolveEnvironment,
  resolveRelease,
} from './config'
import { createMonitoringClient } from './client'
import { redactBreadcrumb, redactEvent } from './redaction'
import { isExpectedError } from './filters'

const dsn = import.meta.env.VITE_SENTRY_DSN || ''
const environment = resolveEnvironment({
  explicitEnvironment: import.meta.env.VITE_SENTRY_ENVIRONMENT,
  isDevServer: import.meta.env.DEV,
})
const release = resolveRelease({ explicitRelease: import.meta.env.VITE_SENTRY_RELEASE })
const dist = resolveDist({
  explicitDist: import.meta.env.VITE_SENTRY_DIST,
  platform: Capacitor.getPlatform(),
})
const localOverrideEnabled = import.meta.env.VITE_SENTRY_ENABLED === 'true'
const enabled = isMonitoringEnabled({ dsn, environment, localOverrideEnabled })

const monitoring = createMonitoringClient(Sentry)

function beforeSend(event, hint) {
  if (isExpectedError(event)) {
    return null
  }
  return redactEvent(event, hint)
}

function beforeBreadcrumb(breadcrumb) {
  return redactBreadcrumb(breadcrumb)
}

/**
 * Must be called before the React tree renders. A missing DSN, a disabled
 * environment, or an SDK initialization failure all resolve to the same
 * safe outcome: the app starts normally and every exported helper below
 * becomes a no-op.
 */
export function initMonitoring() {
  monitoring.init({
    enabled,
    dsn,
    environment,
    release,
    dist,
    sendDefaultPii: false,
    tracesSampleRate: 0,
    beforeSend,
    beforeBreadcrumb,
  })
  monitoring.setTag('build_type', import.meta.env.DEV ? 'debug' : 'release')
  attachNativeAppInfoTags()
}

// versionName/versionCode (Android) and the equivalent iOS build/version are
// not available synchronously to JS; @capacitor/app's getInfo() is async, so
// this fire-and-forget call tags them onto the current native session as
// soon as they resolve rather than blocking init. No-ops on web (getInfo()
// only returns app info when run inside a native Capacitor shell).
function attachNativeAppInfoTags() {
  if (!Capacitor.isNativePlatform()) {
    return
  }
  CapacitorApp.getInfo()
    .then((info) => {
      if (info?.version) {
        monitoring.setTag('app_version', info.version)
      }
      if (info?.build) {
        monitoring.setTag('app_build', info.build)
      }
    })
    .catch(() => {
      // Best-effort only; absence of native app info must never affect
      // monitoring availability.
    })
}

export function isMonitoringActive() {
  return monitoring.isEnabled()
}

export const captureException = monitoring.captureException
export const captureMessage = monitoring.captureMessage
export const setUser = monitoring.setUser
export const clearUser = monitoring.clearUser
export const addBreadcrumb = monitoring.addBreadcrumb
export const setTag = monitoring.setTag

// Re-exported for tests and for call sites that need to reason about the
// resolved configuration (e.g. displaying a safe event id) without reaching
// into Sentry internals directly.
export const monitoringConfig = { dsn: Boolean(dsn), environment, release, dist, enabled }

// --- Manual verification test triggers (E09-01 requirement 14/28/48/49) ---
// Deliberately NOT wired to any UI element (no "Crash app" button). Reachable
// only via a devtools console call, gated by config.js's isTestTriggerAllowed
// (pure and unit-tested there) -- see that function's doc comment for the
// exact two-condition gate. Mirrors the existing dev-only
// window.__locationServiceTest / VITE_SHOW_TEST_PUSH conventions already
// used elsewhere in this codebase.
const testTriggerEnabled = import.meta.env.VITE_SENTRY_TEST_TRIGGER_ENABLED === 'true'

function triggerTestError() {
  throw new Error('[monitoring] test error trigger (manual verification only)')
}

function triggerTestMessage() {
  return captureMessage('[monitoring] test message trigger (manual verification only)', 'info')
}

function triggerTestNativeCrash() {
  // Bridges to @sentry/capacitor's native crash() plugin method -- a real,
  // unconditional native crash on Android/iOS. The gate above is what makes
  // this safe, not anything in the SDK itself.
  Sentry.nativeCrash()
}

if (
  typeof window !== 'undefined' &&
  isTestTriggerAllowed({ environment, isDevServer: import.meta.env.DEV, testTriggerEnabled })
) {
  window.__monitoringTest = { triggerTestError, triggerTestMessage, triggerTestNativeCrash }
}
