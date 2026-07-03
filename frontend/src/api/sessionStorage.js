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

// Startup deadline for secure-storage init (strategy doc section 7, gap G1):
// a hung native bridge must resolve to the logged-out state, never pin the
// app on the session-checking screen.
const SECURE_STORAGE_INIT_TIMEOUT_MS = 5000

let cachedToken = null
let secureStorage = null
let initPromise = null

export function isNativeRuntime() {
  return Capacitor.isNativePlatform()
}

function hasLocalStorage() {
  return typeof localStorage !== 'undefined'
}

function hasWebSessionStorage() {
  return typeof sessionStorage !== 'undefined'
}

function emitSessionChanged() {
  window.dispatchEvent(new Event('auth-session-changed'))
}

// Central reporting for secure-storage failures (strategy doc section 8).
// Only the event name and the error object are logged — never token values,
// storage values, or decoded claims.
function reportStorageEvent(event, error) {
  if (error === undefined) {
    console.warn(`event=${event}`)
  } else {
    console.warn(`event=${event}`, error)
  }
}

// Tells the UI whether the current session survived to secure storage, so a
// non-blocking notice can be shown when login persistence failed (gap G2).
function emitPersistenceChanged(persisted) {
  window.dispatchEvent(
    new CustomEvent('auth-persistence-changed', { detail: { persisted } }),
  )
}

function withTimeout(promise, ms, timeoutMessage) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      const timeoutError = new Error(timeoutMessage)
      timeoutError.name = 'SecureStorageTimeout'
      reject(timeoutError)
    }, ms)

    promise.then(
      (value) => {
        clearTimeout(timer)
        resolve(value)
      },
      (error) => {
        clearTimeout(timer)
        reject(error)
      },
    )
  })
}

async function loadSecureStoragePlugin() {
  if (!secureStorage) {
    // U1/U4 guard: if the native plugin is not registered with the bridge,
    // calling any method on the plugin proxy re-enters its own platform
    // loader in an infinite microtask loop that starves timers and wedges
    // the WebView beyond the reach of any timeout. Detect unavailability
    // up front and fail instead of ever invoking the proxy.
    if (!Capacitor.isPluginAvailable('SecureStorage')) {
      throw new Error('SecureStorage plugin is not available in this runtime')
    }

    const module = await import('@aparajita/capacitor-secure-storage')
    secureStorage = module.SecureStorage
  }
  // The plugin proxy must never be a promise resolution value: resolving it
  // makes the promise machinery probe `.then`, which the Capacitor proxy
  // forwards as a native call that never settles. Callers use the module
  // variable after awaiting this function.
}

async function initNative() {
  try {
    await withTimeout(
      loadSecureStoragePlugin(),
      SECURE_STORAGE_INIT_TIMEOUT_MS,
      'Secure storage plugin did not load within the startup deadline',
    )
  } catch (pluginError) {
    // U1/U4: plugin or bridge unavailable. Fail closed — no session, no
    // localStorage fallback for the token, app lands on the login screen.
    reportStorageEvent('secure_storage.unavailable', pluginError)
    cachedToken = null
    clearUserMetadata()
    return
  }

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
      // W3: never leave a native auth token in plaintext if migration fails.
      cachedToken = null
      localStorage.removeItem(TOKEN_KEY)
      clearUserMetadata()
      reportStorageEvent('secure_storage.migration_failure', storageError)
    }

    return
  }

  try {
    cachedToken = await withTimeout(
      secureStorage.getItem(TOKEN_KEY),
      SECURE_STORAGE_INIT_TIMEOUT_MS,
      'Secure storage read did not settle within the startup deadline',
    )
  } catch (storageError) {
    // R1-R4: fail closed. Corrupted, hanging, or unavailable secure storage
    // means no session. Never fall back to localStorage on native. A read
    // that settles after the deadline is discarded by withTimeout, so a late
    // token can never race the app back into an authenticated state.
    reportStorageEvent(
      storageError?.name === 'SecureStorageTimeout'
        ? 'secure_storage.read_timeout'
        : 'secure_storage.read_failure',
      storageError,
    )
    cachedToken = null
    clearUserMetadata()

    try {
      // Best-effort removal of the unreadable entry, bounded by the same
      // deadline so a hung bridge cannot stall startup here either.
      await withTimeout(
        secureStorage.removeItem(TOKEN_KEY),
        SECURE_STORAGE_INIT_TIMEOUT_MS,
        'Secure storage cleanup did not settle within the startup deadline',
      )
    } catch (cleanupError) {
      reportStorageEvent('secure_storage.delete_failure', cleanupError)
    }
  }
}

async function initInternal() {
  if (isNativeRuntime()) {
    await initNative()
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
    // storage (W1/W2). If the write ultimately fails the session lives in
    // memory for this run and the UI is told so it can warn the user.
    try {
      await loadSecureStoragePlugin()
    } catch (pluginError) {
      reportStorageEvent('secure_storage.write_failure', pluginError)
      emitPersistenceChanged(false)
      return
    }

    try {
      await secureStorage.setItem(TOKEN_KEY, token)
    } catch (firstError) {
      if (cachedToken !== token) {
        // A logout or a newer login superseded this write while it was in
        // flight; retrying would resurrect state the user destroyed.
        reportStorageEvent('secure_storage.write_failure', firstError)
        return
      }

      try {
        await secureStorage.setItem(TOKEN_KEY, token)
        reportStorageEvent('secure_storage.write_retry_success', firstError)
      } catch (retryError) {
        reportStorageEvent('secure_storage.write_failure', retryError)
        emitPersistenceChanged(false)
        return
      }
    }

    if (cachedToken === null) {
      // A logout began while this write was in flight and the write still
      // landed. Undo it: after logout, secure storage must not hold a token.
      try {
        await secureStorage.removeItem(TOKEN_KEY)
      } catch (compensateError) {
        reportStorageEvent('secure_storage.delete_failure', compensateError)
      }
      return
    }

    if (cachedToken !== token) {
      // A newer login superseded this session; its own write owns the
      // persisted state now.
      return
    }

    emitPersistenceChanged(true)
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
    // Fail closed: a token left behind in secure storage would silently
    // restore the session on the next launch, so removal failures propagate
    // to the caller after one retry instead of being swallowed here.
    try {
      await loadSecureStoragePlugin()
    } catch (pluginError) {
      reportStorageEvent('secure_storage.delete_failure', pluginError)
      throw pluginError
    }

    try {
      await secureStorage.removeItem(TOKEN_KEY)
    } catch (removeError) {
      reportStorageEvent('secure_storage.delete_failure', removeError)

      try {
        await secureStorage.removeItem(TOKEN_KEY)
        reportStorageEvent('secure_storage.delete_retry_success')
      } catch (retryError) {
        reportStorageEvent('secure_storage.delete_failure', retryError)
        throw retryError
      }
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

export function clearWebSessionStorage() {
  if (!hasWebSessionStorage()) {
    return
  }

  // Nothing writes auth data to web sessionStorage today; this defensively
  // removes any residue left by older builds or future regressions.
  for (const key of [TOKEN_KEY, ...Object.values(METADATA_KEYS), ...LEGACY_KEYS]) {
    sessionStorage.removeItem(key)
  }
}

export async function clearSession() {
  clearUserMetadata()
  clearLegacyKeys()
  clearWebSessionStorage()

  // Every synchronous cleanup runs and listeners are notified even when
  // secure-storage removal fails; the failure still rejects so callers can
  // surface it instead of pretending logout fully succeeded.
  try {
    await clearToken()
  } finally {
    emitSessionChanged()
  }
}
