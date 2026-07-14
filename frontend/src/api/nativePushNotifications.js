import { Capacitor } from '@capacitor/core'
import { PushNotifications } from '@capacitor/push-notifications'

import { isUuidV4 } from '../utils/appLinkRoutes.js'

const CHECK_PERMISSIONS_TIMEOUT_MS = 8000
const REQUEST_PERMISSIONS_TIMEOUT_MS = 120000
const REGISTER_TIMEOUT_MS = 15000

let listenerHandles = []
let initialized = false
let currentToken = null

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
  if (current === 'granted') {
    return 'granted'
  }
  if (current === 'denied') {
    return 'denied'
  }

  try {
    const result = await withTimeout(
      plugin.requestPermissions(),
      'requestPermissions',
      REQUEST_PERMISSIONS_TIMEOUT_MS,
    )
    return result?.receive ?? 'denied'
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
    return { outcome: 'unsupported' }
  }

  if (initialized) {
    return { outcome: 'already-initialized', token: currentToken }
  }

  const permission = await requestPushPermission(plugin)

  if (permission !== 'granted') {
    return { outcome: 'denied' }
  }

  initialized = true

  const registrationHandle = await plugin.addListener('registration', (registrationToken) => {
    const token = registrationToken?.value
    if (!token) {
      return
    }
    currentToken = token
    onTokenReceived?.(token)
  })
  listenerHandles.push(registrationHandle)

  const errorHandle = await plugin.addListener('registrationError', (error) => {
    onTokenError?.(error)
  })
  listenerHandles.push(errorHandle)

  const foregroundHandle = await plugin.addListener(
    'pushNotificationReceived',
    (notification) => {
      onForegroundNotification?.(notification)
    },
  )
  listenerHandles.push(foregroundHandle)

  const actionHandle = await plugin.addListener(
    'pushNotificationActionPerformed',
    (action) => {
      const data = action?.notification?.data
      const target = extractNotificationTarget(data)
      onNotificationTapped?.(target, action)
    },
  )
  listenerHandles.push(actionHandle)

  try {
    await withTimeout(plugin.register(), 'register', REGISTER_TIMEOUT_MS)
  } catch (registerError) {
    onTokenError?.({ message: registerError?.message || 'registration-failed' })
    return { outcome: 'registration-failed' }
  }

  return { outcome: 'registered' }
}

export async function teardownNativePush(plugin = loadPlugin()) {
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
}

export function getCurrentToken() {
  return currentToken
}

export function isInitialized() {
  return initialized
}
