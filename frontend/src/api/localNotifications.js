import { Capacitor } from '@capacitor/core'
import { LocalNotifications } from '@capacitor/local-notifications'

// Native local-notification adapter (ISSUE-290, Phase One per ISSUE-289).
// Mirrors the point-of-need, native-vs-web pattern already established in
// api/locationPermission.js: never prompts on load, only the caller's
// explicit action triggers a permission check/request, and every outcome is
// a plain result object — this module never throws to its caller.
//
// Web has no reliable "fires later even if the app/tab is closed" API, so
// this adapter is native-only by design; callers gate the UI on
// isNativeRuntime() (api/sessionStorage.js) before offering the feature.

// Scheduling has no user-cancellation gesture (unlike the native Share
// Sheet) — a permission prompt is answered granted or denied, never
// "cancelled" — so only these four outcomes are ever produced.
const RESULT = {
  scheduled: (notificationId) => ({ outcome: 'scheduled', notificationId }),
  denied: () => ({ outcome: 'denied' }),
  unsupported: () => ({ outcome: 'unsupported' }),
  failed: (reason) => ({ outcome: 'failed', reason }),
}

const CHECK_PERMISSIONS_TIMEOUT_MS = 8000
const REQUEST_PERMISSIONS_TIMEOUT_MS = 120000
const SCHEDULE_TIMEOUT_MS = 10000

function isNative() {
  return Capacitor.isNativePlatform()
}

// MUST stay synchronous — never await the plugin proxy itself. Same phantom
// `.then` hazard documented in api/locationPermission.js and
// api/sessionStorage.js applies to every Capacitor plugin proxy.
function loadPlugin() {
  if (!isNative() || !Capacitor.isPluginAvailable('LocalNotifications')) {
    return null
  }

  return LocalNotifications
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

function permissionIsGranted(status) {
  return status?.display === 'granted'
}

export function isLocalNotificationSupported() {
  return loadPlugin() !== null
}

async function ensurePermission(plugin) {
  try {
    const status = await withTimeout(
      plugin.checkPermissions(),
      'checkPermissions',
      CHECK_PERMISSIONS_TIMEOUT_MS,
    )
    if (permissionIsGranted(status)) {
      return true
    }
  } catch {
    // Fall through to an explicit request if the passive check errors.
  }

  try {
    const requested = await withTimeout(
      plugin.requestPermissions(),
      'requestPermissions',
      REQUEST_PERMISSIONS_TIMEOUT_MS,
    )
    return permissionIsGranted(requested)
  } catch {
    return false
  }
}

// Schedules a single local notification. `at` must be a future Date.
// Requests permission only at this point-of-need call, never eagerly.
// `plugin` is injectable (defaults to the real Capacitor plugin proxy) so
// callers/tests can exercise permission and native-failure paths without a
// real native runtime — same pattern as api/nativeShare.js's `shareApi`.
export async function scheduleLocalNotification({ id, title, body, at }, { plugin = loadPlugin() } = {}) {
  if (!plugin) {
    return RESULT.unsupported()
  }

  if (!(at instanceof Date) || Number.isNaN(at.getTime()) || at.getTime() <= Date.now()) {
    return RESULT.failed('invalid-schedule-time')
  }

  const granted = await ensurePermission(plugin)
  if (!granted) {
    return RESULT.denied()
  }

  try {
    await withTimeout(
      plugin.schedule({
        notifications: [
          {
            id,
            title,
            body,
            schedule: { at },
          },
        ],
      }),
      'schedule',
      SCHEDULE_TIMEOUT_MS,
    )
    return RESULT.scheduled(id)
  } catch (error) {
    return RESULT.failed(error?.message || 'schedule-invocation-failed')
  }
}

// Cancels a previously scheduled local notification. Best-effort: an
// unsupported runtime or a native failure both resolve to `false` rather
// than throwing, since cancellation is always a cleanup side effect and must
// never block or crash the caller's own flow (e.g. leaving a game).
export async function cancelLocalNotification(id, { plugin = loadPlugin() } = {}) {
  if (!plugin || !Number.isFinite(id)) {
    return false
  }

  try {
    await withTimeout(
      plugin.cancel({ notifications: [{ id }] }),
      'cancel',
      SCHEDULE_TIMEOUT_MS,
    )
    return true
  } catch {
    return false
  }
}
