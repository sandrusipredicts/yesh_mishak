import assert from 'node:assert/strict'
import test from 'node:test'

import { buildClipboardShareText } from '../src/utils/clipboardShareText.js'

test('combines text and url with a newline', () => {
  const result = buildClipboardShareText({
    text: 'Check this out',
    url: 'https://yesh-mishak.com/game/123',
  })

  assert.equal(result, 'Check this out\nhttps://yesh-mishak.com/game/123')
})

test('does not duplicate url when text already contains it', () => {
  const url = 'https://yesh-mishak.com/game/123'
  const result = buildClipboardShareText({
    text: `Check this out\n${url}`,
    url,
  })

  assert.equal(result, `Check this out\n${url}`)
})

test('returns only url when text is empty', () => {
  const result = buildClipboardShareText({
    text: '',
    url: 'https://yesh-mishak.com/game/123',
  })

  assert.equal(result, 'https://yesh-mishak.com/game/123')
})

test('returns only text when url is empty', () => {
  const result = buildClipboardShareText({
    text: 'Check this out',
    url: '',
  })

  assert.equal(result, 'Check this out')
})

test('returns empty string for null payload', () => {
  assert.equal(buildClipboardShareText(null), '')
})

test('returns empty string for undefined payload', () => {
  assert.equal(buildClipboardShareText(undefined), '')
})

test('handles non-string text gracefully', () => {
  const result = buildClipboardShareText({
    text: 42,
    url: 'https://yesh-mishak.com/game/123',
  })

  assert.equal(result, 'https://yesh-mishak.com/game/123')
})

test('trims whitespace from text and url', () => {
  const result = buildClipboardShareText({
    text: '  Hello  ',
    url: '  https://yesh-mishak.com/game/123  ',
  })

  assert.equal(result, 'Hello\nhttps://yesh-mishak.com/game/123')
})
