import assert from 'node:assert/strict'
import test from 'node:test'

import { copyToClipboard } from '../src/api/clipboard.js'

function withGlobals(values, run) {
  const originals = new Map()

  for (const [key, value] of Object.entries(values)) {
    originals.set(key, Object.getOwnPropertyDescriptor(globalThis, key))
    Object.defineProperty(globalThis, key, {
      value,
      configurable: true,
      writable: true,
    })
  }

  return Promise.resolve()
    .then(run)
    .finally(() => {
      for (const [key, descriptor] of originals) {
        if (descriptor === undefined) {
          delete globalThis[key]
        } else {
          Object.defineProperty(globalThis, key, descriptor)
        }
      }
    })
}

test('copyToClipboard prefers navigator.clipboard.writeText', async () => {
  let copiedText = ''

  await withGlobals({
    navigator: {
      clipboard: {
        writeText: async (text) => {
          copiedText = text
        },
      },
    },
    document: undefined,
  }, async () => {
    await copyToClipboard('https://yesh-mishak.com/game/987e6543-e21b-42d3-a456-426614174999')
  })

  assert.equal(copiedText, 'https://yesh-mishak.com/game/987e6543-e21b-42d3-a456-426614174999')
})

test('copyToClipboard falls back to a temporary textarea and cleans it up', async () => {
  const appended = []
  const removed = []
  let selectedValue = ''

  const fakeDocument = {
    body: {
      appendChild(element) {
        appended.push(element)
      },
    },
    createElement(tagName) {
      assert.equal(tagName, 'textarea')
      return {
        value: '',
        style: {},
        setAttribute() {},
        focus() {},
        select() {
          selectedValue = this.value
        },
        setSelectionRange() {},
        remove() {
          removed.push(this)
        },
      }
    },
    execCommand(command) {
      assert.equal(command, 'copy')
      return true
    },
  }

  await withGlobals({
    navigator: {},
    document: fakeDocument,
  }, async () => {
    await copyToClipboard('https://yesh-mishak.com/fields/11111111-1111-4111-8111-111111111111')
  })

  assert.equal(appended.length, 1)
  assert.equal(removed.length, 1)
  assert.equal(appended[0], removed[0])
  assert.equal(selectedValue, 'https://yesh-mishak.com/fields/11111111-1111-4111-8111-111111111111')
})

test('copyToClipboard uses fallback when navigator.clipboard rejects', async () => {
  let fallbackUsed = false

  const fakeDocument = {
    body: {
      appendChild() {},
    },
    createElement() {
      return {
        value: '',
        style: {},
        setAttribute() {},
        focus() {},
        select() {},
        setSelectionRange() {},
        remove() {},
      }
    },
    execCommand() {
      fallbackUsed = true
      return true
    },
  }

  await withGlobals({
    navigator: {
      clipboard: {
        writeText: async () => {
          throw new Error('denied')
        },
      },
    },
    document: fakeDocument,
  }, async () => {
    await copyToClipboard('https://yesh-mishak.com/game/987e6543-e21b-42d3-a456-426614174999')
  })

  assert.equal(fallbackUsed, true)
})

test('copyToClipboard rejects empty text without creating a fallback element', async () => {
  let elementCreated = false

  await withGlobals({
    navigator: {},
    document: {
      createElement() {
        elementCreated = true
      },
      execCommand() {
        return true
      },
    },
  }, async () => {
    await assert.rejects(() => copyToClipboard(''), /Clipboard text is required/)
  })

  assert.equal(elementCreated, false)
})
