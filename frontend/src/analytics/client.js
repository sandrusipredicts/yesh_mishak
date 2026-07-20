// E09-02: wires the pure analytics queue to the app. Fire-and-forget by
// contract: trackEvent never throws into application code, never blocks the
// UI, and drops events silently on any failure (Client Resiliency rule).
//
// Flush triggers: a 15s interval while the queue is non-empty, document
// visibilitychange -> hidden, and Capacitor appStateChange -> inactive.
// The batch endpoint requires an authenticated session; events pending
// while logged out are dropped, never held (anonymous by design -- D1).

import { Capacitor } from '@capacitor/core'

import { isValidEvent } from './registry.js'
import { createAnalyticsQueue, flushQueue } from './queue.js'

export const FLUSH_INTERVAL_MS = 15000

const VALID_PLATFORMS = new Set(['web', 'android', 'ios'])

const queue = createAnalyticsQueue()
let flushIntervalId = null
let flushInFlight = false
let lifecycleListenersReady = false

function getPlatform() {
  try {
    const platform = Capacitor.getPlatform()
    return VALID_PLATFORMS.has(platform) ? platform : 'web'
  } catch {
    return 'web'
  }
}

async function sendBatch(events) {
  // Dynamic import mirrors shareAnalytics.js: keeps this module importable
  // in non-browser test environments without pulling in axios/session code.
  const { api } = await import('../api/client.js')
  await api.post('/analytics/events', { events }, { skipAuthSessionCleanup: true })
}

function isRetryableError(error) {
  const status = error?.response?.status
  // A 4xx (401/403/422/429) will not succeed on retry; only network
  // failures and 5xx are worth another attempt.
  return !(status >= 400 && status < 500)
}

function syncFlushInterval() {
  if (queue.isEmpty()) {
    if (flushIntervalId !== null) {
      clearInterval(flushIntervalId)
      flushIntervalId = null
    }
    return
  }

  if (flushIntervalId === null && typeof setInterval === 'function') {
    flushIntervalId = setInterval(() => {
      flush()
    }, FLUSH_INTERVAL_MS)
  }
}

async function flush() {
  if (flushInFlight || queue.isEmpty()) {
    return
  }

  flushInFlight = true
  try {
    const { getToken } = await import('../api/sessionStorage.js')
    if (!getToken()) {
      // Anonymous pipeline, authenticated transport: without a session the
      // batch can never be accepted -- drop instead of holding events.
      queue.clear()
      return
    }
    await flushQueue(queue, { send: sendBatch, isRetryable: isRetryableError })
  } catch {
    // Analytics must never surface errors into application code.
  } finally {
    flushInFlight = false
    syncFlushInterval()
  }
}

function ensureLifecycleListeners() {
  if (lifecycleListenersReady) {
    return
  }
  lifecycleListenersReady = true

  try {
    if (typeof document !== 'undefined') {
      document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') {
          flush()
        }
      })
    }

    if (Capacitor.isNativePlatform()) {
      import('@capacitor/app')
        .then(({ App: CapacitorApp }) => {
          CapacitorApp.addListener('appStateChange', ({ isActive }) => {
            if (!isActive) {
              flush()
            }
          })
        })
        .catch(() => {
          // Listener registration is best-effort; interval flush still runs.
        })
    }
  } catch {
    // Never let listener wiring break the caller.
  }
}

// Public entry point. `platform` is attached here as a top-level envelope
// field (never a property -- the registry forbids it). Returns whether the
// event was accepted into the queue; callers may ignore the result.
export function trackEvent(eventName, properties = {}) {
  try {
    if (!isValidEvent(eventName, properties)) {
      return false
    }

    queue.enqueue({
      event_name: eventName,
      platform: getPlatform(),
      occurred_at: new Date().toISOString(),
      properties: { ...properties },
    })

    ensureLifecycleListeners()
    syncFlushInterval()
    return true
  } catch {
    return false
  }
}
