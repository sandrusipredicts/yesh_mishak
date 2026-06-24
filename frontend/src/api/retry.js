const DEFAULT_MAX_ATTEMPTS = 3
const DEFAULT_RETRY_DELAYS_MS = [500, 1500]
const JITTER_RATIO = 0.2

function isBrowserOffline() {
  return typeof navigator !== 'undefined' && navigator.onLine === false
}

function getStatus(error) {
  return error?.response?.status
}

function getRetryAfterDelay(error) {
  const retryAfter = error?.response?.headers?.['retry-after']

  if (!retryAfter) {
    return null
  }

  const retryAfterSeconds = Number(retryAfter)
  if (Number.isFinite(retryAfterSeconds) && retryAfterSeconds >= 0) {
    return retryAfterSeconds * 1000
  }

  const retryAfterDate = Date.parse(retryAfter)
  if (Number.isFinite(retryAfterDate)) {
    return Math.max(0, retryAfterDate - Date.now())
  }

  return null
}

function addJitter(delayMs) {
  const jitterRange = delayMs * JITTER_RATIO
  const jitter = (Math.random() * jitterRange * 2) - jitterRange

  return Math.max(0, Math.round(delayMs + jitter))
}

function wait(delayMs) {
  return new Promise((resolve) => {
    globalThis.setTimeout(resolve, delayMs)
  })
}

export function isRetryableReadError(error) {
  if (isBrowserOffline()) {
    return false
  }

  const status = getStatus(error)

  if (!status) {
    return true
  }

  if (status === 429) {
    return getRetryAfterDelay(error) !== null
  }

  return status >= 500 && status <= 599
}

export async function retrySafeRead(operation, options = {}) {
  const {
    maxAttempts = DEFAULT_MAX_ATTEMPTS,
    delaysMs = DEFAULT_RETRY_DELAYS_MS,
  } = options

  let lastError

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      return await operation()
    } catch (error) {
      lastError = error

      if (attempt >= maxAttempts || !isRetryableReadError(error)) {
        throw error
      }

      const retryAfterDelay = getRetryAfterDelay(error)
      const delayMs = retryAfterDelay ?? delaysMs[attempt - 1] ?? delaysMs[delaysMs.length - 1]

      await wait(addJitter(delayMs))

      if (isBrowserOffline()) {
        throw error
      }
    }
  }

  throw lastError
}
