import assert from 'node:assert/strict'
import test from 'node:test'

import {
  MAX_BATCH_ATTEMPTS,
  MAX_BATCH_SIZE,
  MAX_QUEUE_SIZE,
  RETRY_BACKOFF_BASE_MS,
  createAnalyticsQueue,
  flushQueue,
} from '../src/analytics/queue.js'

function makeEvent(index) {
  return { event_name: 'app_open', platform: 'web', properties: {}, index }
}

function fillQueue(queue, count) {
  for (let index = 0; index < count; index += 1) {
    queue.enqueue(makeEvent(index))
  }
}

test('enqueue caps the queue at 100 and drops the oldest events first', () => {
  const queue = createAnalyticsQueue()

  let dropped = 0
  for (let index = 0; index < MAX_QUEUE_SIZE + 5; index += 1) {
    dropped += queue.enqueue(makeEvent(index))
  }

  assert.equal(MAX_QUEUE_SIZE, 100)
  assert.equal(queue.size(), MAX_QUEUE_SIZE)
  assert.equal(dropped, 5)
  // Events 0-4 were dropped; the queue now starts at index 5.
  assert.equal(queue.drainBatch()[0].index, 5)
})

test('drainBatch slices at most 20 events per batch, preserving order', () => {
  const queue = createAnalyticsQueue()
  fillQueue(queue, 45)

  const first = queue.drainBatch()
  const second = queue.drainBatch()
  const third = queue.drainBatch()

  assert.equal(MAX_BATCH_SIZE, 20)
  assert.equal(first.length, 20)
  assert.equal(second.length, 20)
  assert.equal(third.length, 5)
  assert.equal(first[0].index, 0)
  assert.equal(second[0].index, 20)
  assert.equal(third[4].index, 44)
  assert.equal(queue.isEmpty(), true)
})

test('flushQueue drains the whole queue in max-20 chunks', async () => {
  const queue = createAnalyticsQueue()
  fillQueue(queue, 47)
  const sentBatches = []

  const drained = await flushQueue(queue, {
    send: async (batch) => sentBatches.push(batch),
    wait: async () => {},
  })

  assert.equal(drained, true)
  assert.deepEqual(sentBatches.map((batch) => batch.length), [20, 20, 7])
  assert.equal(sentBatches[0][0].index, 0)
  assert.equal(sentBatches[2][6].index, 46)
  assert.equal(queue.isEmpty(), true)
})

test('flushQueue retries a failing batch with exponential backoff, then drops it silently', async () => {
  const queue = createAnalyticsQueue()
  fillQueue(queue, 25)
  let attempts = 0
  const waits = []

  const drained = await flushQueue(queue, {
    send: async () => {
      attempts += 1
      throw new Error('network down')
    },
    wait: async (ms) => waits.push(ms),
  })

  assert.equal(drained, false)
  assert.equal(attempts, MAX_BATCH_ATTEMPTS)
  assert.deepEqual(waits, [RETRY_BACKOFF_BASE_MS, RETRY_BACKOFF_BASE_MS * 2])
  // The failed 20-event batch was dropped; the remaining 5 stay queued for
  // the next flush trigger (no hammering of a failing backend).
  assert.equal(queue.size(), 5)
})

test('flushQueue succeeds on a retry attempt and continues draining', async () => {
  const queue = createAnalyticsQueue()
  fillQueue(queue, 25)
  const waits = []
  let failuresRemaining = 1
  const sentBatches = []

  const drained = await flushQueue(queue, {
    send: async (batch) => {
      if (failuresRemaining > 0) {
        failuresRemaining -= 1
        throw new Error('transient failure')
      }
      sentBatches.push(batch)
    },
    wait: async (ms) => waits.push(ms),
  })

  assert.equal(drained, true)
  assert.deepEqual(waits, [RETRY_BACKOFF_BASE_MS])
  assert.deepEqual(sentBatches.map((batch) => batch.length), [20, 5])
  assert.equal(queue.isEmpty(), true)
})

test('flushQueue drops a batch immediately on a non-retryable error', async () => {
  const queue = createAnalyticsQueue()
  fillQueue(queue, 5)
  let attempts = 0
  const waits = []
  const rejection = Object.assign(new Error('unauthorized'), { response: { status: 401 } })

  const drained = await flushQueue(queue, {
    send: async () => {
      attempts += 1
      throw rejection
    },
    wait: async (ms) => waits.push(ms),
    isRetryable: (error) => error?.response?.status !== 401,
  })

  assert.equal(drained, false)
  assert.equal(attempts, 1)
  assert.deepEqual(waits, [])
  assert.equal(queue.isEmpty(), true)
})

test('clear discards every pending event', () => {
  const queue = createAnalyticsQueue()
  fillQueue(queue, 12)

  assert.equal(queue.clear(), 12)
  assert.equal(queue.isEmpty(), true)
  assert.equal(queue.drainBatch().length, 0)
})
