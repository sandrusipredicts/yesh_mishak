import assert from 'node:assert/strict'
import test from 'node:test'

import {
  LINK_OPEN_DEDUPE_WINDOW_MS,
  buildLinkOpenPayload,
  recordLinkOpen,
  recordShareAction,
  resetShareAnalyticsDedupeForTests,
} from '../src/api/shareAnalytics.js'
import { copyFieldLink, shareField } from '../src/api/fieldSharing.js'
import { copyGameLink, shareGame } from '../src/api/gameSharing.js'
import en from '../src/locales/en/common.js'

function resolveKey(key) {
  return key.split('.').reduce((node, part) => node?.[part], en)
}

function t(key, options = {}) {
  const template = resolveKey(key)
  if (typeof template !== 'string') {
    return typeof options === 'string' ? options : key
  }
  return template.replace(/\{\{(\w+)\}\}/g, (_, name) => String(options[name] ?? ''))
}

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 0))
}

function makeRecorder() {
  const calls = []
  return {
    calls,
    record: (entityType, result, options = {}) => {
      calls.push({ entityType, result, options })
    },
  }
}

const GAME_ID = '987e6543-e21b-42d3-a456-426614174999'
const FIELD_ID = '11111111-1111-4111-8111-111111111111'

function makeGame(overrides = {}) {
  return {
    id: GAME_ID,
    sport_type: 'football',
    status: 'open',
    players_present: 4,
    max_players: 10,
    scheduled_at: null,
    ...overrides,
  }
}

function makeField(overrides = {}) {
  return {
    id: FIELD_ID,
    name: 'Central Court',
    city: '',
    status: 'approved',
    ...overrides,
  }
}

test('recordShareAction submits a narrow native-share payload', async () => {
  const posts = []

  recordShareAction('game', { outcome: 'shared', mechanism: 'native-share' }, {
    platform: 'android',
    post: async (path, payload) => posts.push({ path, payload }),
  })
  await flushPromises()

  assert.deepEqual(posts, [{
    path: '/analytics/share-events',
    payload: {
      event_name: 'share_action',
      entity_type: 'game',
      platform: 'android',
      mechanism: 'native_share',
      outcome: 'shared',
      error_category: undefined,
    },
  }])
})

test('recordShareAction rejects receiving apps, ids, urls and arbitrary metadata by construction', async () => {
  const posts = []

  recordShareAction('game', {
    outcome: 'shared',
    mechanism: 'whatsapp',
    activityType: 'com.whatsapp',
    url: `https://yesh-mishak.com/game/${GAME_ID}`,
    game_id: GAME_ID,
    metadata: { source: 'bad' },
  }, {
    platform: 'android',
    post: async (path, payload) => posts.push({ path, payload }),
  })
  await flushPromises()

  assert.deepEqual(posts, [])
})

test('recordLinkOpen builds valid game link payloads without ids or urls', () => {
  const payload = buildLinkOpenPayload({
    ok: true,
    routeType: 'game',
    resourceId: GAME_ID,
    navigationPath: '/',
  }, 'valid', { platform: 'web' })

  assert.deepEqual(payload, {
    event_name: 'link_open',
    entity_type: 'game',
    platform: 'web',
    outcome: 'valid',
  })
  assert.equal(JSON.stringify(payload).includes(GAME_ID), false)
  assert.equal(JSON.stringify(payload).includes('https://'), false)
})

test('recordLinkOpen builds valid field link payloads', () => {
  const payload = buildLinkOpenPayload({
    ok: true,
    routeType: 'field',
    resourceId: FIELD_ID,
    navigationPath: '/',
  }, 'valid', { platform: 'ios' })

  assert.equal(payload.entity_type, 'field')
  assert.equal(payload.platform, 'ios')
  assert.equal(payload.outcome, 'valid')
})

test('recordLinkOpen maps malformed game links to invalid with a coarse error', () => {
  const payload = buildLinkOpenPayload({
    ok: true,
    routeType: 'fallback',
    reason: 'invalid-game-id',
    navigationPath: '/',
  }, 'invalid', { platform: 'web' })

  assert.deepEqual(payload, {
    event_name: 'link_open',
    entity_type: 'game',
    platform: 'web',
    outcome: 'invalid',
    error_category: 'unsupported_link',
  })
})

test('recordLinkOpen maps missing resources to not_found', () => {
  const payload = buildLinkOpenPayload({
    ok: true,
    routeType: 'field',
    resourceId: FIELD_ID,
  }, 'not_found', { platform: 'android' })

  assert.equal(payload.outcome, 'not_found')
  assert.equal(payload.error_category, 'resource_not_found')
})

test('recordLinkOpen supports pre-auth deferred links', () => {
  const payload = buildLinkOpenPayload({
    ok: true,
    routeType: 'game',
    resourceId: GAME_ID,
  }, 'deferred_for_auth', { platform: 'android' })

  assert.equal(payload.outcome, 'deferred_for_auth')
})

test('recordLinkOpen suppresses duplicate cold-start and StrictMode-equivalent arrivals', async () => {
  resetShareAnalyticsDedupeForTests()
  const posts = []
  const route = { ok: true, routeType: 'game', resourceId: GAME_ID }

  assert.equal(recordLinkOpen(route, 'valid', {
    platform: 'android',
    now: 1000,
    post: async (_, payload) => posts.push(payload),
  }), true)
  assert.equal(recordLinkOpen(route, 'valid', {
    platform: 'android',
    now: 1001,
    post: async (_, payload) => posts.push(payload),
  }), false)
  assert.equal(recordLinkOpen(route, 'valid', {
    platform: 'android',
    now: 1002,
    post: async (_, payload) => posts.push(payload),
  }), false)
  await flushPromises()

  assert.equal(posts.length, 1)
})

test('recordLinkOpen allows legitimate repeated opens after the dedupe window', async () => {
  resetShareAnalyticsDedupeForTests()
  const posts = []
  const route = { ok: true, routeType: 'field', resourceId: FIELD_ID }

  assert.equal(recordLinkOpen(route, 'valid', {
    platform: 'web',
    now: 1000,
    post: async (_, payload) => posts.push(payload),
  }), true)
  assert.equal(recordLinkOpen(route, 'valid', {
    platform: 'web',
    now: 1000 + LINK_OPEN_DEDUPE_WINDOW_MS + 1,
    post: async (_, payload) => posts.push(payload),
  }), true)
  await flushPromises()

  assert.equal(posts.length, 2)
})

test('recordLinkOpen submission failure is swallowed', async () => {
  resetShareAnalyticsDedupeForTests()

  assert.doesNotThrow(() => recordLinkOpen(
    { ok: true, routeType: 'game', resourceId: GAME_ID },
    'valid',
    { platform: 'web', post: async () => { throw new Error('offline') } },
  ))
  await flushPromises()
})

test('shareGame records native-share success, cancellation and failure classifications', async () => {
  const recorder = makeRecorder()

  await shareGame(
    { game: makeGame(), fieldName: 'Central Court', locale: 'en-US', t },
    {
      invokeShare: async () => ({ outcome: 'shared', mechanism: 'native-share' }),
      recordAnalytics: recorder.record,
    },
  )
  await shareGame(
    { game: makeGame(), fieldName: 'Central Court', locale: 'en-US', t },
    {
      invokeShare: async () => ({ outcome: 'cancelled', mechanism: 'native-share' }),
      recordAnalytics: recorder.record,
    },
  )
  await shareGame(
    { game: makeGame(), fieldName: 'Central Court', locale: 'en-US', t },
    {
      invokeShare: async () => ({ outcome: 'failed', mechanism: 'native-share', reason: 'share-invocation-failed' }),
      recordAnalytics: recorder.record,
    },
  )

  assert.deepEqual(recorder.calls.map((call) => [call.entityType, call.result.outcome, call.result.mechanism]), [
    ['game', 'shared', 'native-share'],
    ['game', 'cancelled', 'native-share'],
    ['game', 'failed', 'native-share'],
  ])
})

test('copy link records game and field copy success/failure classifications', async () => {
  const recorder = makeRecorder()

  await copyGameLink(makeGame(), {
    copyText: async () => {},
    recordAnalytics: recorder.record,
  })
  await copyFieldLink(makeField(), {
    copyText: async () => { throw new Error('denied') },
    recordAnalytics: recorder.record,
  })

  assert.deepEqual(recorder.calls.map((call) => [call.entityType, call.options.mechanism, call.result.outcome]), [
    ['game', 'copy_link', 'copied'],
    ['field', 'copy_link', 'failed'],
  ])
})

test('native-share fallback to copy-link records field classification', async () => {
  const recorder = makeRecorder()

  await shareField(
    { field: makeField(), t },
    {
      invokeShare: async () => ({ outcome: 'unavailable', mechanism: 'native-share', reason: 'share-api-unavailable' }),
      copyText: async () => {},
      recordAnalytics: recorder.record,
    },
  )

  assert.deepEqual(recorder.calls.map((call) => [call.entityType, call.result.mechanism, call.result.outcome]), [
    ['field', 'clipboard', 'copied'],
  ])
})

test('analytics helper failure does not break sharing flow', async () => {
  const result = await shareField(
    { field: makeField(), t },
    {
      invokeShare: async () => ({ outcome: 'shared', mechanism: 'native-share' }),
      recordAnalytics: () => { throw new Error('analytics unavailable') },
    },
  )

  assert.deepEqual(result, { outcome: 'shared', mechanism: 'native-share' })
})
