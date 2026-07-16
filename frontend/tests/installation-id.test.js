import assert from 'node:assert/strict'
import { afterEach, beforeEach, describe, test } from 'node:test'

import { getOrCreateInstallationId } from '../src/utils/installationId.js'

const KEY = 'push_installation_id'

function createFakeLocalStorage() {
  const store = new Map()
  return {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => { store.set(key, String(value)) },
    removeItem: (key) => { store.delete(key) },
    clear: () => { store.clear() },
  }
}

describe('getOrCreateInstallationId', () => {
  let originalLocalStorage

  beforeEach(() => {
    originalLocalStorage = globalThis.localStorage
    globalThis.localStorage = createFakeLocalStorage()
  })

  afterEach(() => {
    globalThis.localStorage = originalLocalStorage
  })

  test('generates and persists a UUID on first call', () => {
    const id = getOrCreateInstallationId()

    assert.ok(id)
    assert.strictEqual(globalThis.localStorage.getItem(KEY), id)
  })

  test('reuses the same id across calls (no app restart)', () => {
    const first = getOrCreateInstallationId()
    const second = getOrCreateInstallationId()

    assert.strictEqual(first, second)
  })

  test('reuses a previously stored id (simulated app restart)', () => {
    globalThis.localStorage.setItem(KEY, 'existing-install-id')

    const id = getOrCreateInstallationId()

    assert.strictEqual(id, 'existing-install-id')
  })

  test('returns null when localStorage is unavailable', () => {
    globalThis.localStorage = undefined

    const id = getOrCreateInstallationId()

    assert.strictEqual(id, null)
  })
})
