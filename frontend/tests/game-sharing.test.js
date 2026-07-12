import assert from 'node:assert/strict'
import test from 'node:test'

import { shareGame } from '../src/api/gameSharing.js'
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

const GAME_ID = '987e6543-e21b-42d3-a456-426614174999'
const LOCALE = 'en-US'

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

test('short-circuits to unavailable without invoking the adapter when the game is unshareable', async () => {
  let invokeShareCalled = false
  const result = await shareGame(
    { game: { ...makeGame(), id: undefined }, fieldName: 'Central Court', locale: LOCALE, t },
    { invokeShare: async () => { invokeShareCalled = true } },
  )

  assert.deepEqual(result, { outcome: 'unavailable', mechanism: 'native-share', reason: 'invalid-resource' })
  assert.equal(invokeShareCalled, false)
})

test('builds the payload and hands it off to the Native Share adapter unchanged', async () => {
  let receivedPayload = null
  const result = await shareGame(
    { game: makeGame(), fieldName: 'Central Court', locale: LOCALE, t },
    {
      invokeShare: async (payload) => {
        receivedPayload = payload
        return { outcome: 'shared', mechanism: 'native-share' }
      },
    },
  )

  assert.deepEqual(result, { outcome: 'shared', mechanism: 'native-share' })
  assert.deepEqual(receivedPayload, {
    title: 'Football game at Central Court',
    text: 'Join a Football game at Central Court — 4 / 10 players.',
    url: `https://yesh-mishak.com/game/${GAME_ID}`,
  })
})

test('passes through a cancellation outcome from the adapter unchanged', async () => {
  const result = await shareGame(
    { game: makeGame(), fieldName: 'Central Court', locale: LOCALE, t },
    { invokeShare: async () => ({ outcome: 'cancelled', mechanism: 'native-share' }) },
  )

  assert.deepEqual(result, { outcome: 'cancelled', mechanism: 'native-share' })
})

test('passes through a failure outcome from the adapter unchanged', async () => {
  const result = await shareGame(
    { game: makeGame(), fieldName: 'Central Court', locale: LOCALE, t },
    { invokeShare: async () => ({ outcome: 'failed', mechanism: 'native-share', reason: 'share-invocation-failed' }) },
  )

  assert.deepEqual(result, { outcome: 'failed', mechanism: 'native-share', reason: 'share-invocation-failed' })
})
