import assert from 'node:assert/strict'
import test from 'node:test'

import { buildCanonicalShareLink } from '../src/utils/shareLink.js'
import { parseAppPathname } from '../src/utils/appLinkRoutes.js'

const GAME_ID = '987e6543-e21b-42d3-a456-426614174999'

test('builds the canonical HTTPS game link', () => {
  assert.equal(
    buildCanonicalShareLink('game', GAME_ID),
    `https://yesh-mishak.com/game/${GAME_ID}`,
  )
})

test('lowercases the resource id', () => {
  assert.equal(
    buildCanonicalShareLink('game', GAME_ID.toUpperCase()),
    `https://yesh-mishak.com/game/${GAME_ID}`,
  )
})

test('rejects a malformed UUID', () => {
  assert.equal(buildCanonicalShareLink('game', 'not-a-uuid'), null)
})

test('rejects an empty identifier', () => {
  assert.equal(buildCanonicalShareLink('game', ''), null)
})

test('rejects a non-string identifier', () => {
  assert.equal(buildCanonicalShareLink('game', null), null)
  assert.equal(buildCanonicalShareLink('game', undefined), null)
})

test('rejects an unsupported entity type (field sharing is out of scope for ISSUE-284)', () => {
  assert.equal(buildCanonicalShareLink('field', GAME_ID), null)
  assert.equal(buildCanonicalShareLink('unknown-entity', GAME_ID), null)
})

test('the generated link round-trips through the existing ISSUE-272/273 route parser', () => {
  const url = buildCanonicalShareLink('game', GAME_ID)
  const parsedUrl = new URL(url)

  assert.deepEqual(parseAppPathname(parsedUrl.pathname), {
    ok: true,
    routeType: 'game',
    resourceId: GAME_ID,
    action: '',
    navigationPath: '/',
  })
})
