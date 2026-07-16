import assert from 'node:assert/strict'
import test from 'node:test'

import { parseValidCoordinates } from '../src/utils/coordinates.js'

test('parseValidCoordinates accepts valid numeric coordinates', () => {
  assert.deepEqual(parseValidCoordinates(31.225172, 34.777498), {
    latitude: 31.225172,
    longitude: 34.777498,
  })
})

test('parseValidCoordinates accepts zero coordinates', () => {
  assert.deepEqual(parseValidCoordinates(0, 0), {
    latitude: 0,
    longitude: 0,
  })
})

test('parseValidCoordinates accepts negative valid coordinates', () => {
  assert.deepEqual(parseValidCoordinates(-31.225172, -34.777498), {
    latitude: -31.225172,
    longitude: -34.777498,
  })
})

test('parseValidCoordinates accepts numeric strings and returns numbers', () => {
  assert.deepEqual(parseValidCoordinates('31.225172', '34.777498'), {
    latitude: 31.225172,
    longitude: 34.777498,
  })
})

test('parseValidCoordinates accepts geographic boundary values', () => {
  assert.deepEqual(parseValidCoordinates(-90, -180), {
    latitude: -90,
    longitude: -180,
  })
  assert.deepEqual(parseValidCoordinates(90, 180), {
    latitude: 90,
    longitude: 180,
  })
})

test('parseValidCoordinates rejects missing latitude or longitude', () => {
  assert.equal(parseValidCoordinates(null, 34.777498), null)
  assert.equal(parseValidCoordinates(31.225172, null), null)
  assert.equal(parseValidCoordinates(undefined, 34.777498), null)
  assert.equal(parseValidCoordinates(31.225172, undefined), null)
})

test('parseValidCoordinates rejects empty strings', () => {
  assert.equal(parseValidCoordinates('', 34.777498), null)
  assert.equal(parseValidCoordinates(31.225172, ''), null)
  assert.equal(parseValidCoordinates('   ', 34.777498), null)
  assert.equal(parseValidCoordinates(31.225172, '   '), null)
})

test('parseValidCoordinates rejects non-numeric strings', () => {
  assert.equal(parseValidCoordinates('north', 34.777498), null)
  assert.equal(parseValidCoordinates(31.225172, 'east'), null)
})

test('parseValidCoordinates rejects NaN and infinite values', () => {
  assert.equal(parseValidCoordinates(NaN, 34.777498), null)
  assert.equal(parseValidCoordinates(31.225172, NaN), null)
  assert.equal(parseValidCoordinates(Infinity, 34.777498), null)
  assert.equal(parseValidCoordinates(31.225172, Infinity), null)
  assert.equal(parseValidCoordinates(-Infinity, 34.777498), null)
  assert.equal(parseValidCoordinates(31.225172, -Infinity), null)
})

test('parseValidCoordinates rejects out-of-range coordinates', () => {
  assert.equal(parseValidCoordinates(-90.000001, 34.777498), null)
  assert.equal(parseValidCoordinates(90.000001, 34.777498), null)
  assert.equal(parseValidCoordinates(31.225172, -180.000001), null)
  assert.equal(parseValidCoordinates(31.225172, 180.000001), null)
})
