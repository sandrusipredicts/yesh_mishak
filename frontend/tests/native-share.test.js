import assert from 'node:assert/strict'
import test from 'node:test'

import { invokeNativeShare } from '../src/api/nativeShare.js'

const PAYLOAD = {
  title: 'Game at Central Field',
  text: 'Football today',
  url: 'https://yesh-mishak.com/game/987e6543-e21b-42d3-a456-426614174999',
}

function createShareApi({ canShare = true, shareResult = {}, shareError } = {}) {
  const calls = []

  return {
    calls,
    api: {
      async canShare() {
        return { value: canShare }
      },
      async share(payload) {
        calls.push(payload)
        if (shareError) {
          throw shareError
        }
        return shareResult
      },
    },
  }
}

for (const platform of ['android', 'ios', 'web']) {
  test(`invokes the official Share API with only the normalized payload on ${platform}`, async () => {
    const { api, calls } = createShareApi()
    const result = await invokeNativeShare(
      { ...PAYLOAD, accessToken: 'must-not-leak', userId: 'must-not-leak' },
      { shareApi: api, getPlatform: () => platform },
    )

    assert.deepEqual(result, {
      outcome: 'shared',
      mechanism: 'native-share',
    })
    assert.deepEqual(calls, [PAYLOAD])
  })
}

test('treats native cancellation as a normal outcome without a fallback', async () => {
  const { api, calls } = createShareApi({ shareError: new Error('Share canceled') })

  const result = await invokeNativeShare(PAYLOAD, {
    shareApi: api,
    getPlatform: () => 'android',
  })

  assert.deepEqual(result, {
    outcome: 'cancelled',
    mechanism: 'native-share',
  })
  assert.equal(calls.length, 1)
})

test('treats browser AbortError cancellation as a normal outcome', async () => {
  const cancellation = new Error('The user aborted a request')
  cancellation.name = 'AbortError'
  const { api } = createShareApi({ shareError: cancellation })

  const result = await invokeNativeShare(PAYLOAD, {
    shareApi: api,
    getPlatform: () => 'web',
  })

  assert.equal(result.outcome, 'cancelled')
  assert.equal(result.mechanism, 'native-share')
})

test('returns unavailable and does not invoke sharing when the API cannot share', async () => {
  const { api, calls } = createShareApi({ canShare: false })

  const result = await invokeNativeShare(PAYLOAD, {
    shareApi: api,
    getPlatform: () => 'ios',
  })

  assert.deepEqual(result, {
    outcome: 'unavailable',
    mechanism: 'native-share',
    reason: 'share-api-unavailable',
  })
  assert.deepEqual(calls, [])
})

test('normalizes availability-check failures without invoking sharing', async () => {
  let shareCalled = false
  const api = {
    async canShare() {
      throw new Error('Plugin unavailable')
    },
    async share() {
      shareCalled = true
    },
  }

  const result = await invokeNativeShare(PAYLOAD, {
    shareApi: api,
    getPlatform: () => 'android',
  })

  assert.equal(result.outcome, 'unavailable')
  assert.equal(result.reason, 'share-api-unavailable')
  assert.equal(shareCalled, false)
})

test('returns a structured failure when native invocation fails', async () => {
  const { api } = createShareApi({ shareError: new Error('Native bridge failed') })

  const result = await invokeNativeShare(PAYLOAD, {
    shareApi: api,
    getPlatform: () => 'ios',
  })

  assert.deepEqual(result, {
    outcome: 'failed',
    mechanism: 'native-share',
    reason: 'share-invocation-failed',
  })
})

test('returns unavailable for an unsupported platform', async () => {
  const { api, calls } = createShareApi()

  const result = await invokeNativeShare(PAYLOAD, {
    shareApi: api,
    getPlatform: () => 'electron',
  })

  assert.deepEqual(result, {
    outcome: 'unavailable',
    mechanism: 'native-share',
    reason: 'unsupported-platform',
  })
  assert.deepEqual(calls, [])
})

test('never throws when platform detection fails', async () => {
  const { api, calls } = createShareApi()

  const result = await invokeNativeShare(PAYLOAD, {
    shareApi: api,
    getPlatform() {
      throw new Error('Runtime unavailable')
    },
  })

  assert.deepEqual(result, {
    outcome: 'unavailable',
    mechanism: 'native-share',
    reason: 'unsupported-platform',
  })
  assert.deepEqual(calls, [])
})

test('rejects non-canonical payload URLs before invoking the platform', async () => {
  const { api, calls } = createShareApi()

  const result = await invokeNativeShare(
    { ...PAYLOAD, url: 'https://example.com/game/987e6543-e21b-42d3-a456-426614174999' },
    { shareApi: api, getPlatform: () => 'android' },
  )

  assert.deepEqual(result, {
    outcome: 'failed',
    mechanism: 'native-share',
    reason: 'invalid-payload',
  })
  assert.deepEqual(calls, [])
})

test('never throws for a missing payload', async () => {
  const { api } = createShareApi()

  const result = await invokeNativeShare(undefined, {
    shareApi: api,
    getPlatform: () => 'android',
  })

  assert.equal(result.outcome, 'failed')
  assert.equal(result.reason, 'invalid-payload')
})
