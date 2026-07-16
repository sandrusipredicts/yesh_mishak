import assert from 'node:assert/strict'
import test from 'node:test'

import { downloadIcsFile } from '../src/api/icsDownload.js'

function installFakeDom() {
  const clicked = []
  const removed = []
  const appended = []

  const fakeAnchor = {
    href: '',
    download: '',
    rel: '',
    click() {
      clicked.push({ href: this.href, download: this.download })
    },
    remove() {
      removed.push(true)
    },
  }

  globalThis.document = {
    createElement(tag) {
      if (tag !== 'a') {
        throw new Error(`Unexpected element: ${tag}`)
      }
      return fakeAnchor
    },
    body: {
      appendChild(el) {
        appended.push(el)
      },
    },
  }

  globalThis.Blob = class {
    constructor(parts, options) {
      this.parts = parts
      this.options = options
    }
  }

  return { clicked, removed, appended, fakeAnchor }
}

test.beforeEach(() => {
  installFakeDom()
})

test.afterEach(() => {
  delete globalThis.document
  delete globalThis.Blob
})

test('returns false and touches nothing when there is no DOM (e.g. SSR/native context)', () => {
  delete globalThis.document

  const result = downloadIcsFile('BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n', 'game.ics')

  assert.equal(result, false)
})

test('returns false for empty or non-string content', () => {
  assert.equal(downloadIcsFile('', 'game.ics'), false)
  assert.equal(downloadIcsFile(null, 'game.ics'), false)
})

test('creates an object URL, clicks a download link with the given filename, and cleans up', async () => {
  const { clicked, removed } = installFakeDom()
  let createdBlob
  let revoked = false

  const result = downloadIcsFile('BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n', 'game-123.ics', {
    createObjectUrl: (blob) => { createdBlob = blob; return 'blob:fake-url' },
    revokeObjectUrl: (url) => { assert.equal(url, 'blob:fake-url'); revoked = true },
  })

  assert.equal(result, true)
  assert.ok(createdBlob)
  assert.deepEqual(clicked, [{ href: 'blob:fake-url', download: 'game-123.ics' }])
  assert.deepEqual(removed, [true])

  await new Promise((resolve) => setTimeout(resolve, 0))
  assert.equal(revoked, true)
})

test('still revokes the object URL even though the link is removed synchronously', () => {
  let revoked = false

  downloadIcsFile('BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n', 'game.ics', {
    createObjectUrl: () => 'blob:fake-url',
    revokeObjectUrl: () => { revoked = true },
  })

  // Revocation is deferred (setTimeout) so the download can start first —
  // it must not have happened synchronously.
  assert.equal(revoked, false)
})
