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

test('rejects an unsupported entity type', () => {
  assert.equal(buildCanonicalShareLink('unknown-entity', GAME_ID), null)
})

test('the generated game link round-trips through the route parser', () => {
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

const FIELD_ID = '11111111-1111-4111-8111-111111111111'

test('builds the canonical HTTPS field link using /fields/ path', () => {
  assert.equal(
    buildCanonicalShareLink('field', FIELD_ID),
    `https://yesh-mishak.com/fields/${FIELD_ID}`,
  )
})

test('lowercases the field resource id', () => {
  assert.equal(
    buildCanonicalShareLink('field', FIELD_ID.toUpperCase()),
    `https://yesh-mishak.com/fields/${FIELD_ID}`,
  )
})

test('rejects a malformed field UUID', () => {
  assert.equal(buildCanonicalShareLink('field', 'not-a-uuid'), null)
})

test('the generated field link round-trips through the route parser', () => {
  const url = buildCanonicalShareLink('field', FIELD_ID)
  const parsedUrl = new URL(url)

  assert.deepEqual(parseAppPathname(parsedUrl.pathname), {
    ok: true,
    routeType: 'field',
    resourceId: FIELD_ID,
    action: '',
    navigationPath: '/',
  })
})
