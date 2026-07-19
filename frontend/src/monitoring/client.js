// Injectable monitoring client. The `adapter` is whatever SDK exposes
// init/captureException/captureMessage/setUser/addBreadcrumb/setTag with
// Sentry-compatible signatures -- in production that's @sentry/capacitor,
// in tests it's a lightweight fake. This indirection is what makes the
// lifecycle logic (fail-safe init, clear-before-set user context, no-ops
// when disabled) testable without mocking the real SDK module.

function noop() {}

export function createMonitoringClient(adapter) {
  let enabled = false

  function init(options) {
    if (!options?.enabled) {
      enabled = false
      return
    }
    try {
      adapter.init(options)
      enabled = true
    } catch (error) {
      // Monitoring initialization failure must never prevent app startup.
      enabled = false
      if (typeof console !== 'undefined') {
        console.warn('[monitoring] Sentry initialization failed; continuing without crash reporting.', error)
      }
    }
  }

  function guarded(fn) {
    return (...args) => {
      if (!enabled) {
        return undefined
      }
      try {
        return fn(...args)
      } catch (error) {
        if (typeof console !== 'undefined') {
          console.warn('[monitoring] reporting call failed; ignoring.', error)
        }
        return undefined
      }
    }
  }

  const captureException = guarded((error, context) => {
    return adapter.captureException(error, context)
  })

  const captureMessage = guarded((message, level) => {
    return adapter.captureMessage(message, level)
  })

  // Account-switch isolation: always clear before setting a new identity so
  // no field from the prior account context can survive a merge. Setting
  // `null` for an anonymous/logged-out state is itself just the clear path.
  const setUser = guarded((userId) => {
    adapter.setUser(null)
    if (userId) {
      adapter.setUser({ id: String(userId) })
    }
  })

  const clearUser = guarded(() => {
    adapter.setUser(null)
  })

  const addBreadcrumb = guarded((breadcrumb) => {
    adapter.addBreadcrumb(breadcrumb)
  })

  const setTag = guarded((key, value) => {
    adapter.setTag(key, value)
  })

  return {
    init,
    captureException,
    captureMessage,
    setUser,
    clearUser,
    addBreadcrumb,
    setTag,
    isEnabled: () => enabled,
  }
}

export const NOOP_ADAPTER = {
  init: noop,
  captureException: noop,
  captureMessage: noop,
  setUser: noop,
  addBreadcrumb: noop,
  setTag: noop,
}
