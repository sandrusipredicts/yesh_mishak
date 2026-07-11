import assert from 'node:assert/strict'
import test from 'node:test'

import { normalizeAppLinkUrl } from '../src/utils/appLinkRoutes.js'

const FIELD_ID = '123e4567-e89b-42d3-a456-426614174000'
const GAME_ID = '987e6543-e21b-42d3-a456-426614174999'

test('normalizes the valid root URL to home', () => {
  assert.deepEqual(normalizeAppLinkUrl('https://yesh-mishak.com/'), {
    ok: true,
    routeType: 'home',
    resourceId: '',
    action: '',
    navigationPath: '/',
  })
})

test('normalizes /my-games to the existing route', () => {
  assert.deepEqual(normalizeAppLinkUrl('https://yesh-mishak.com/my-games'), {
    ok: true,
    routeType: 'my-games',
    resourceId: '',
    action: '',
    navigationPath: '/my-games',
  })
})

test('accepts game paths and forwards them to the map route', () => {
  assert.deepEqual(normalizeAppLinkUrl(`https://yesh-mishak.com/games/${GAME_ID}/join`), {
    ok: true,
    routeType: 'game',
    resourceId: GAME_ID,
    action: 'join',
    navigationPath: '/',
  })
})

test('accepts field paths and forwards them to the map route', () => {
  assert.deepEqual(normalizeAppLinkUrl(`https://yesh-mishak.com/fields/${FIELD_ID}`), {
    ok: true,
    routeType: 'field',
    resourceId: FIELD_ID,
    action: '',
    navigationPath: '/',
  })
})

test('preserves only legacy architecture query parameters as internal targets', () => {
  assert.deepEqual(
    normalizeAppLinkUrl(`https://yesh-mishak.com/?utm_source=x&game_id=${GAME_ID}&next=https://evil.example`),
    {
      ok: true,
      routeType: 'game',
      resourceId: GAME_ID,
      action: '',
      navigationPath: '/',
    },
  )
})

test('rejects malformed URLs safely', () => {
  assert.deepEqual(normalizeAppLinkUrl('not a url'), {
    ok: false,
    reason: 'malformed-url',
  })
})

test('rejects the wrong host', () => {
  assert.deepEqual(normalizeAppLinkUrl('https://example.com/my-games'), {
    ok: false,
    reason: 'wrong-host',
  })
})

test('rejects HTTP URLs', () => {
  assert.deepEqual(normalizeAppLinkUrl('http://yesh-mishak.com/my-games'), {
    ok: false,
    reason: 'non-https-url',
  })
})

test('falls unsupported paths back to home', () => {
  assert.deepEqual(normalizeAppLinkUrl('https://yesh-mishak.com/unknown-path'), {
    ok: true,
    routeType: 'fallback',
    reason: 'unsupported-path',
    navigationPath: '/',
  })
})
