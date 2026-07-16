import assert from 'node:assert/strict'
import test from 'node:test'

import { buildWazeNavigationUrls } from '../src/api/wazeNavigation.js'

const EXPECTED_HTTPS_URL = 'https://waze.com/ul?ll=31.225172%2C34.777498&navigate=yes'

test('buildWazeNavigationUrls builds the universal link for numeric coordinates', () => {
  assert.deepEqual(buildWazeNavigationUrls(31.225172, 34.777498), {
    httpsUrl: EXPECTED_HTTPS_URL,
  })
})

test('buildWazeNavigationUrls accepts numeric-string coordinates', () => {
  assert.deepEqual(buildWazeNavigationUrls('31.225172', '34.777498'), {
    httpsUrl: EXPECTED_HTTPS_URL,
  })
})

test('buildWazeNavigationUrls accepts zero coordinates', () => {
  assert.deepEqual(buildWazeNavigationUrls(0, 0), {
    httpsUrl: 'https://waze.com/ul?ll=0%2C0&navigate=yes',
  })
})

test('buildWazeNavigationUrls accepts negative coordinates', () => {
  assert.deepEqual(buildWazeNavigationUrls(-31.225172, -34.777498), {
    httpsUrl: 'https://waze.com/ul?ll=-31.225172%2C-34.777498&navigate=yes',
  })
})

test('buildWazeNavigationUrls URL-encodes the destination separator', () => {
  const { httpsUrl } = buildWazeNavigationUrls(31.225172, 34.777498)

  assert.ok(httpsUrl.includes('ll=31.225172%2C34.777498'))
  assert.ok(!httpsUrl.includes('31.225172,34.777498'))
})

test('buildWazeNavigationUrls requests immediate navigation', () => {
  const { httpsUrl } = buildWazeNavigationUrls(31.225172, 34.777498)

  assert.ok(httpsUrl.includes('&navigate=yes'))
})

test('buildWazeNavigationUrls rejects missing coordinates', () => {
  assert.equal(buildWazeNavigationUrls(null, 34.777498), null)
  assert.equal(buildWazeNavigationUrls(31.225172, null), null)
  assert.equal(buildWazeNavigationUrls(undefined, 34.777498), null)
  assert.equal(buildWazeNavigationUrls(31.225172, undefined), null)
})

test('buildWazeNavigationUrls rejects empty and non-numeric strings', () => {
  assert.equal(buildWazeNavigationUrls('', 34.777498), null)
  assert.equal(buildWazeNavigationUrls('   ', 34.777498), null)
  assert.equal(buildWazeNavigationUrls('north', 34.777498), null)
  assert.equal(buildWazeNavigationUrls(31.225172, 'east'), null)
})

test('buildWazeNavigationUrls rejects NaN and infinite values', () => {
  assert.equal(buildWazeNavigationUrls(NaN, 34.777498), null)
  assert.equal(buildWazeNavigationUrls(31.225172, Infinity), null)
  assert.equal(buildWazeNavigationUrls(-Infinity, 34.777498), null)
})

test('buildWazeNavigationUrls rejects out-of-range coordinates', () => {
  assert.equal(buildWazeNavigationUrls(90.000001, 34.777498), null)
  assert.equal(buildWazeNavigationUrls(-90.000001, 34.777498), null)
  assert.equal(buildWazeNavigationUrls(31.225172, 180.000001), null)
  assert.equal(buildWazeNavigationUrls(31.225172, -180.000001), null)
})
