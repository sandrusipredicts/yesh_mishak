// E09-02: pure in-memory analytics queue. No imports of app code, DOM, or
// Capacitor -- everything side-effectful (transport, timers, lifecycle
// listeners) lives in client.js so this module stays testable under plain
// node --test. Analytics are best-effort by design: overflow and absolute
// send failure both drop events silently.

export const MAX_QUEUE_SIZE = 100
export const MAX_BATCH_SIZE = 20
export const MAX_BATCH_ATTEMPTS = 3
export const RETRY_BACKOFF_BASE_MS = 2000

function defaultWait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export function createAnalyticsQueue({
  maxSize = MAX_QUEUE_SIZE,
  maxBatchSize = MAX_BATCH_SIZE,
} = {}) {
  const events = []

  return {
    // Appends an event; when the cap is exceeded the OLDEST events are
    // dropped first. Returns how many events were dropped.
    enqueue(event) {
      events.push(event)
      let dropped = 0
      while (events.length > maxSize) {
        events.shift()
        dropped += 1
      }
      return dropped
    },

    size() {
      return events.length
    },

    isEmpty() {
      return events.length === 0
    },

    // Removes and returns up to maxBatchSize events from the front.
    drainBatch() {
      return events.splice(0, maxBatchSize)
    },

    // Drops everything. Returns how many events were discarded.
    clear() {
      const discarded = events.length
      events.length = 0
      return discarded
    },
  }
}

async function deliverBatch(batch, { send, wait, maxAttempts, backoffBaseMs, isRetryable }) {
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      await send(batch)
      return true
    } catch (error) {
      if (attempt >= maxAttempts || !isRetryable(error)) {
        return false
      }
      await wait(backoffBaseMs * 2 ** (attempt - 1))
    }
  }
  return false
}

// Drains the queue batch by batch. On absolute failure of a batch (all
// attempts exhausted, or a non-retryable error) that batch is dropped
// silently and the flush cycle stops -- remaining events stay queued for
// the next flush trigger instead of hammering a failing backend. Returns
// true when the queue was fully drained.
export async function flushQueue(
  queue,
  {
    send,
    wait = defaultWait,
    maxAttempts = MAX_BATCH_ATTEMPTS,
    backoffBaseMs = RETRY_BACKOFF_BASE_MS,
    isRetryable = () => true,
  },
) {
  while (!queue.isEmpty()) {
    const batch = queue.drainBatch()
    const delivered = await deliverBatch(batch, {
      send,
      wait,
      maxAttempts,
      backoffBaseMs,
      isRetryable,
    })
    if (!delivered) {
      return false
    }
  }
  return true
}
