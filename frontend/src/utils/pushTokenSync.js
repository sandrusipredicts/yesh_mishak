export const PUSH_TOKEN_SYNC_MAX_RETRIES = 3
export const PUSH_TOKEN_SYNC_BASE_DELAY_MS = 2000

function isPermanentError(error) {
  const status = error?.response?.status
  return status === 400 || status === 401 || status === 403 || status === 422
}

// Bounded-retry wrapper around a single "save this push token" call. Never
// loops tightly and never retries a permanent validation/auth failure — those
// wait for the next authenticated app launch instead (`retryPending`).
export function createPushTokenSync({
  save,
  onSyncFailed,
  maxRetries = PUSH_TOKEN_SYNC_MAX_RETRIES,
  baseDelayMs = PUSH_TOKEN_SYNC_BASE_DELAY_MS,
  setTimeoutFn = globalThis.setTimeout,
  clearTimeoutFn = globalThis.clearTimeout,
} = {}) {
  let retryTimer = null
  let pending = null
  let disposed = false

  function clearRetryTimer() {
    if (retryTimer !== null) {
      clearTimeoutFn(retryTimer)
      retryTimer = null
    }
  }

  async function attempt(token, options, retryCount) {
    try {
      await save(token, options)
      if (!disposed) {
        pending = null
      }
    } catch (error) {
      if (disposed) {
        return
      }

      pending = { token, options }

      if (isPermanentError(error) || retryCount >= maxRetries) {
        onSyncFailed?.(error)
        return
      }

      const delay = baseDelayMs * 2 ** retryCount
      retryTimer = setTimeoutFn(() => {
        retryTimer = null
        void attempt(token, options, retryCount + 1)
      }, delay)
    }
  }

  function sync(token, options) {
    clearRetryTimer()
    void attempt(token, options, 0)
  }

  function retryPending() {
    if (pending && retryTimer === null) {
      const { token, options } = pending
      void attempt(token, options, 0)
    }
  }

  function dispose() {
    disposed = true
    clearRetryTimer()
    pending = null
  }

  return { sync, retryPending, dispose }
}
