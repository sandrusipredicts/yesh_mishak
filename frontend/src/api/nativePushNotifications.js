import { Capacitor } from '@capacitor/core'
import { PushNotifications } from '@capacitor/push-notifications'

import { isUuidV4 } from '../utils/appLinkRoutes.js'

const DEBUG_PREFIX = '[E04-01 PUSH DEBUG]'

// Raw-to-app permission-state mapping (E08-02 audit): checkPermissions()/
// requestPermissions().receive is typed as @capacitor/core's PermissionState
// — exactly 'prompt' | 'prompt-with-rationale' | 'granted' | 'denied' on the
// installed plugin version. There is no 'restricted'/'limited' value to
// normalize on this platform, so none is invented here. checkPushPermission/
// requestPushPermission below pass that value straight through (plus the
// app-injected 'unsupported' when the plugin/native platform is absent) —
// callers already treat anything other than 'granted' as "not yet usable".
//
// Android-version normalization is handled by the native plugin itself, not
// here: per @capacitor/push-notifications' own documented behavior, on
// Android 12 and below checkPermissions()/requestPermissions() always
// resolve 'granted' (no runtime notification permission exists pre-13), so
// this file never needs to branch on OS version to avoid showing an invalid
// permission prompt on older Android.

const CHECK_PERMISSIONS_TIMEOUT_MS = 8000
const REQUEST_PERMISSIONS_TIMEOUT_MS = 120000
const REGISTER_TIMEOUT_MS = 15000

let listenerHandles = []
let initialized = false
let currentToken = null
let initGeneration = 0

function debugLog(...args) {
  console.info(DEBUG_PREFIX, ...args)
}

function isNative() {
  return Capacitor.isNativePlatform()
}

function loadPlugin() {
  if (!isNative() || !Capacitor.isPluginAvailable('PushNotifications')) {
    return null
  }

  return PushNotifications
}

async function withTimeout(promise, label, timeoutMs) {
  let timeoutId
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timeoutId = setTimeout(() => {
          reject(new Error(`Timeout while waiting for ${label}`))
        }, timeoutMs)
      }),
    ])
  } finally {
    clearTimeout(timeoutId)
  }
}

export function isNativePushSupported(plugin = loadPlugin()) {
  return plugin !== null
}

export async function checkPushPermission(plugin = loadPlugin()) {
  if (!plugin) {
    return 'unsupported'
  }

  try {
    const status = await withTimeout(
      plugin.checkPermissions(),
      'checkPermissions',
      CHECK_PERMISSIONS_TIMEOUT_MS,
    )
    return status?.receive ?? 'prompt'
  } catch {
    return 'prompt'
  }
}

export async function requestPushPermission(plugin = loadPlugin()) {
  if (!plugin) {
    return 'unsupported'
  }

  const current = await checkPushPermission(plugin)
  debugLog('permission check result:', current)

  if (current === 'granted') {
    return 'granted'
  }
  if (current === 'denied') {
    return 'denied'
  }

  try {
    debugLog('requesting permission')
    const result = await withTimeout(
      plugin.requestPermissions(),
      'requestPermissions',
      REQUEST_PERMISSIONS_TIMEOUT_MS,
    )
    const outcome = result?.receive ?? 'denied'
    debugLog('permission request result:', outcome)
    return outcome
  } catch {
    return 'denied'
  }
}

export function extractNotificationTarget(data) {
  if (!data || typeof data !== 'object') {
    return null
  }

  const gameId = data.game_id || data.gameId
  if (gameId && typeof gameId === 'string' && isUuidV4(gameId)) {
    return { routeType: 'game', resourceId: gameId }
  }

  const fieldId = data.field_id || data.fieldId
  if (fieldId && typeof fieldId === 'string' && isUuidV4(fieldId)) {
    return { routeType: 'field', resourceId: fieldId }
  }

  return null
}

export async function initNativePush({
  plugin = loadPlugin(),
  onTokenReceived,
  onTokenError,
  onForegroundNotification,
  onNotificationTapped,
} = {}) {
  if (!plugin) {
    debugLog('plugin not available — unsupported')
    return { outcome: 'unsupported' }
  }

  if (initialized) {
    debugLog('already initialized, token length:', currentToken?.length ?? 0)
    return { outcome: 'already-initialized', token: currentToken }
  }

  debugLog('initialization started')

  const permission = await requestPushPermission(plugin)

  if (permission !== 'granted') {
    debugLog('permission not granted:', permission)
    return { outcome: 'denied' }
  }

  initGeneration += 1
  const thisGeneration = initGeneration
  initialized = true

  debugLog('attaching listeners, generation:', thisGeneration)

  const registrationHandle = await plugin.addListener('registration', (registrationToken) => {
    const token = registrationToken?.value
    if (!token) {
      debugLog('registration callback fired but token is empty')
      return
    }
    if (thisGeneration !== initGeneration) {
      debugLog('registration callback fired for stale generation, ignoring')
      return
    }
    debugLog('registration callback received, token length:', token.length,
      'suffix:', token.slice(-6))
    currentToken = token
    onTokenReceived?.(token)
  })
  listenerHandles.push(registrationHandle)

  const errorHandle = await plugin.addListener('registrationError', (error) => {
    debugLog('registrationError callback:', error?.message || error)
    onTokenError?.(error)
  })
  listenerHandles.push(errorHandle)

  const foregroundHandle = await plugin.addListener(
    'pushNotificationReceived',
    (notification) => {
      debugLog('foreground notification received')
      onForegroundNotification?.(notification)
    },
  )
  listenerHandles.push(foregroundHandle)

  const actionHandle = await plugin.addListener(
    'pushNotificationActionPerformed',
    (action) => {
      const data = action?.notification?.data
      const target = extractNotificationTarget(data)
      debugLog('notification action performed, target:', target?.routeType || 'none')
      onNotificationTapped?.(target, action)
    },
  )
  listenerHandles.push(actionHandle)

  debugLog('listeners attached, calling register()')

  try {
    await withTimeout(plugin.register(), 'register', REGISTER_TIMEOUT_MS)
    debugLog('register() resolved')
  } catch (registerError) {
    debugLog('register() failed:', registerError?.message)
    onTokenError?.({ message: registerError?.message || 'registration-failed' })
    return { outcome: 'registration-failed' }
  }

  return { outcome: 'registered' }
}

export async function teardownNativePush(plugin = loadPlugin()) {
  debugLog('teardown invoked, handle count:', listenerHandles.length)

  for (const handle of listenerHandles) {
    try {
      await handle.remove()
    } catch {
      // Best-effort cleanup.
    }
  }
  listenerHandles = []
  initialized = false
  currentToken = null

  if (plugin) {
    try {
      await plugin.removeAllListeners()
    } catch {
      // Best-effort cleanup.
    }
  }

  debugLog('teardown complete')
}

export function getCurrentToken() {
  return currentToken
}

export function isInitialized() {
  return initialized
}
