import assert from 'node:assert/strict'
import test from 'node:test'

import { normalizeAppLinkUrl, parseAppPathname } from '../src/utils/appLinkRoutes.js'

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

test('normalizes /admin to the existing admin route', () => {
  assert.deepEqual(normalizeAppLinkUrl('https://yesh-mishak.com/admin'), {
    ok: true,
    routeType: 'admin',
    resourceId: '',
    action: '',
    navigationPath: '/admin',
  })
})

test('normalizes /reset-password without dropping the reset token', () => {
  assert.deepEqual(normalizeAppLinkUrl('https://yesh-mishak.com/reset-password?token=reset.token+value'), {
    ok: true,
    routeType: 'reset-password',
    resourceId: '',
    action: '',
    navigationPath: '/reset-password?token=reset.token%20value',
  })
})

test('normalizes /forgot-password to the request route', () => {
  assert.deepEqual(normalizeAppLinkUrl('https://yesh-mishak.com/forgot-password'), {
    ok: true,
    routeType: 'forgot-password',
    resourceId: '',
    action: '',
    navigationPath: '/forgot-password',
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

test('parseAppPathname resolves a same-origin game path regardless of host', () => {
  assert.deepEqual(parseAppPathname(`/game/${GAME_ID}`), {
    ok: true,
    routeType: 'game',
    resourceId: GAME_ID,
    action: '',
    navigationPath: '/',
  })
})

test('parseAppPathname resolves the join action suffix', () => {
  assert.deepEqual(parseAppPathname(`/games/${GAME_ID}/join`), {
    ok: true,
    routeType: 'game',
    resourceId: GAME_ID,
    action: 'join',
    navigationPath: '/',
  })
})

test('parseAppPathname falls back gracefully for a malformed game id', () => {
  assert.deepEqual(parseAppPathname('/game/not-a-uuid'), {
    ok: true,
    routeType: 'fallback',
    reason: 'invalid-game-id',
    navigationPath: '/',
  })
})

test('parseAppPathname falls back gracefully for an empty game id', () => {
  assert.deepEqual(parseAppPathname('/game/'), {
    ok: true,
    routeType: 'fallback',
    reason: 'unsupported-path',
    navigationPath: '/',
  })
})

test('parseAppPathname falls back gracefully for an unsupported route', () => {
  assert.deepEqual(parseAppPathname('/settings'), {
    ok: true,
    routeType: 'fallback',
    reason: 'unsupported-path',
    navigationPath: '/',
  })
})

test('parseAppPathname resolves the root path to home', () => {
  assert.deepEqual(parseAppPathname('/'), {
    ok: true,
    routeType: 'home',
    resourceId: '',
    action: '',
    navigationPath: '/',
  })
})

test('parseAppPathname resolves /admin to the existing admin route', () => {
  assert.deepEqual(parseAppPathname('/admin'), {
    ok: true,
    routeType: 'admin',
    resourceId: '',
    action: '',
    navigationPath: '/admin',
  })
})

test('parseAppPathname resolves /reset-password before app fallback routing', () => {
  assert.deepEqual(parseAppPathname('/reset-password', '?token=reset-token'), {
    ok: true,
    routeType: 'reset-password',
    resourceId: '',
    action: '',
    navigationPath: '/reset-password?token=reset-token',
  })
})

test('parseAppPathname preserves legacy game_id query params', () => {
  assert.deepEqual(parseAppPathname('/', `?game_id=${GAME_ID}`), {
    ok: true,
    routeType: 'game',
    resourceId: GAME_ID,
    action: '',
    navigationPath: '/',
  })
})
