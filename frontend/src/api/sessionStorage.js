import { Capacitor } from '@capacitor/core'

// Sole owner of auth/session storage (ISSUE-229). All auth storage keys and
// storage-medium decisions live here: native runtime uses Keystore-backed
// secure storage for the token; web uses localStorage as the temporary
// compatibility fallback tier (docs/secure-storage-architecture.md, section 16).
const TOKEN_KEY = 'access_token'
const METADATA_KEYS = {
  id: 'currentUserId',
  name: 'currentUserName',
  email: 'currentUserEmail',
  username: 'currentUsername',
}
const LEGACY_KEYS = ['authToken', 'token', 'current_user_id', 'user_id']

let cachedToken = null
let secureStorage = null
let initPromise = null

export function isNativeRuntime() {
  return Capacitor.isNativePlatform()
}

function hasLocalStorage() {
  return typeof localStorage !== 'undefined'
}

function emitSessionChanged() {
  window.dispatchEvent(new Event('auth-session-changed'))
}

async function loadSecureStoragePlugin() {
  if (!secureStorage) {
    const module = await import('@aparajita/capacitor-secure-storage')
    secureStorage = module.SecureStorage
  }
  // The plugin proxy must never be a promise resolution value: resolving it
  // makes the promise machinery probe `.then`, which the Capacitor proxy
  // forwards as a native call that never settles. Callers use the module
  // variable after awaiting this function.
}

async function initInternal() {
  if (isNativeRuntime()) {
    await loadSecureStoragePlugin()
    const localToken = hasLocalStorage() ? localStorage.getItem(TOKEN_KEY) : null

    if (localToken) {
      // Migrate the token out of WebView localStorage. The localStorage copy
      // is removed only after the secure write succeeds; on failure the
      // session stays usable in memory and migration retries next launch.
      cachedToken = localToken

      try {
        await secureStorage.setItem(TOKEN_KEY, localToken)
        localStorage.removeItem(TOKEN_KEY)
      } catch (storageError) {
        // Never leave a native auth token in plaintext if migration fails.
        cachedToken = null
        localStorage.removeItem(TOKEN_KEY)
        clearUserMetadata()
        console.warn('Secure storage migration failed; starting logged out.', storageError)
      }
    } else {
      try {
        cachedToken = await secureStorage.getItem(TOKEN_KEY)
      } catch (storageError) {
        // Fail closed: corrupted or unavailable secure storage means no
        // session. Never fall back to localStorage on native.
        console.warn('Secure storage read failed; starting logged out.', storageError)
        cachedToken = null
        clearUserMetadata()

        try {
          await secureStorage.removeItem(TOKEN_KEY)
        } catch (cleanupError) {
          console.warn('Secure storage cleanup after read failure failed.', cleanupError)
        }
      }
    }
  } else {
    cachedToken = hasLocalStorage() ? localStorage.getItem(TOKEN_KEY) : null
  }

  clearLegacyKeys()
}

export function initSessionStorage() {
  if (!initPromise) {
    initPromise = initInternal()
  }

  return initPromise
}

export function getToken() {
  return cachedToken
}

export async function setToken(token) {
  cachedToken = token

  if (isNativeRuntime()) {
    // No silent fallback: on native the token is persisted only to secure
    // storage. If the write fails the session lives in memory for this run.
    await loadSecureStoragePlugin()

    try {
      await secureStorage.setItem(TOKEN_KEY, token)
    } catch (storageError) {
      console.warn('Secure storage write failed; session will not survive restart.', storageError)
    }
  } else if (hasLocalStorage()) {
    localStorage.setItem(TOKEN_KEY, token)
  }
}

export async function clearToken() {
  cachedToken = null

  if (hasLocalStorage()) {
    localStorage.removeItem(TOKEN_KEY)
  }

  if (isNativeRuntime()) {
    try {
      await loadSecureStoragePlugin()
      await secureStorage.removeItem(TOKEN_KEY)
    } catch (storageError) {
      console.warn('Secure storage remove failed.', storageError)
    }
  }
}

export function getUserMetadata() {
  if (!hasLocalStorage()) {
    return { id: '', name: '', email: '', username: '' }
  }

  return {
    id: localStorage.getItem(METADATA_KEYS.id) || '',
    name: localStorage.getItem(METADATA_KEYS.name) || '',
    email: localStorage.getItem(METADATA_KEYS.email) || '',
    username: localStorage.getItem(METADATA_KEYS.username) || '',
  }
}

export function setUserMetadata({ id, name, email, username }) {
  if (!hasLocalStorage()) {
    return
  }

  localStorage.setItem(METADATA_KEYS.id, id ?? '')
  localStorage.setItem(METADATA_KEYS.name, name ?? '')
  localStorage.setItem(METADATA_KEYS.email, email ?? '')

  if (username) {
    localStorage.setItem(METADATA_KEYS.username, username)
  } else {
    localStorage.removeItem(METADATA_KEYS.username)
  }
}

export function clearUserMetadata() {
  if (!hasLocalStorage()) {
    return
  }

  for (const key of Object.values(METADATA_KEYS)) {
    localStorage.removeItem(key)
  }
}

export function clearLegacyKeys() {
  if (!hasLocalStorage()) {
    return
  }

  for (const key of LEGACY_KEYS) {
    localStorage.removeItem(key)
  }
}

export async function clearSession() {
  clearUserMetadata()
  clearLegacyKeys()
  await clearToken()
  emitSessionChanged()
}
