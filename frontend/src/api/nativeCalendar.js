import { Capacitor } from '@capacitor/core'
import { CapacitorCalendar } from '@ebarooni/capacitor-calendar'

// Native calendar adapter (E07-01). Mirrors the point-of-need, native-vs-web
// pattern in api/localNotifications.js and api/nativeShare.js: never touches
// the plugin until the caller's explicit "Add to calendar" tap, and every
// outcome is a plain result object — this module never throws to its caller.
//
// Deliberately uses the plugin's *prompt* method (opens the device's native
// event-editor UI, pre-filled) rather than writing an event directly. Per
// docs/native-plugin-governance-policy.md and the task's preferred
// architecture: the user reviews/edits/saves-or-cancels in the system UI,
// so this adapter never needs READ_CALENDAR/WRITE_CALENDAR, never reads the
// user's existing calendar, and never enumerates calendars.
//
// Because the prompt is a native system UI, a resolved promise only means
// "the editor was presented" — not "the user saved it". Confirmed against
// @ebarooni/capacitor-calendar v8.2.0's own README: on Android,
// createEventWithPrompt's `{ id }` is *always* null, for both a saved and a
// cancelled event — there is no reliable per-platform saved/cancelled
// signal to key off. So this adapter deliberately ignores the resolved
// `id` and only ever reports 'opened', never a false "saved" outcome.

const RESULT = {
  opened: () => ({ outcome: 'opened' }),
  denied: () => ({ outcome: 'denied' }),
  unsupported: () => ({ outcome: 'unsupported' }),
  noCompatibleApp: () => ({ outcome: 'unavailable', reason: 'no-calendar-app' }),
  cancelled: () => ({ outcome: 'cancelled' }),
  failed: (reason) => ({ outcome: 'failed', reason }),
}

const PLUGIN_NAME = 'CapacitorCalendar'
const PROMPT_TIMEOUT_MS = 10 * 60 * 1000

function isNative() {
  return Capacitor.isNativePlatform()
}

// MUST stay synchronous — never await the plugin proxy itself (same phantom
// `.then` hazard documented in api/localNotifications.js).
function loadPlugin() {
  if (!isNative() || !Capacitor.isPluginAvailable(PLUGIN_NAME)) {
    return null
  }

  return CapacitorCalendar
}

export function isNativeCalendarSupported() {
  return loadPlugin() !== null
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

function isCancellation(error) {
  const message = String(error?.message ?? error ?? '').toLowerCase()
  return message.includes('cancel')
}

function isPermissionDenied(error) {
  const message = String(error?.message ?? error ?? '').toLowerCase()
  return message.includes('denied') || message.includes('permission')
}

// The Android implementation (CapacitorCalendarPlugin.kt) launches a plain
// Intent.ACTION_INSERT and rejects with the raw ActivityNotFoundException
// message when no app on the device can handle it — this is the expected,
// non-error "no compatible calendar app" case the task calls out
// explicitly, not a bug to surface as a generic failure.
function isNoCompatibleApp(error) {
  const message = String(error?.message ?? error ?? '').toLowerCase()
  return message.includes('no activity found')
}

// Converts our platform-agnostic payload (utils/gameCalendarPayload.js)
// into @ebarooni/capacitor-calendar's CreateEventWithPromptOptions shape
// (node_modules/@ebarooni/capacitor-calendar/dist/esm/schemas/interfaces/
// create-event-with-prompt-options.d.ts, v8.2.0). `url` is iOS-only per
// that package's docs; Android ignores the field.
export function toPluginPromptOptions(payload) {
  return {
    title: payload?.title || '',
    location: payload?.location || '',
    description: payload?.description || '',
    url: payload?.url || undefined,
    startDate: payload?.start instanceof Date ? payload.start.getTime() : undefined,
    endDate: payload?.end instanceof Date ? payload.end.getTime() : undefined,
  }
}

// Opens the native "create event" prompt pre-filled with `payload`
// (from utils/gameCalendarPayload.js). Resolves 'opened' as soon as the
// editor is presented — it does not wait for or report a save, matching
// the product copy ("Calendar event editor opened", not "Event added").
export async function openCalendarEventPrompt(payload, { plugin = loadPlugin() } = {}) {
  if (!plugin) {
    return RESULT.unsupported()
  }

  if (!payload || !(payload.start instanceof Date) || Number.isNaN(payload.start.getTime())) {
    return RESULT.failed('invalid-payload')
  }

  try {
    await withTimeout(
      plugin.createEventWithPrompt(toPluginPromptOptions(payload)),
      'createEventWithPrompt',
      PROMPT_TIMEOUT_MS,
    )
    return RESULT.opened()
  } catch (error) {
    if (isCancellation(error)) {
      return RESULT.cancelled()
    }

    if (isPermissionDenied(error)) {
      return RESULT.denied()
    }

    if (isNoCompatibleApp(error)) {
      return RESULT.noCompatibleApp()
    }

    return RESULT.failed(error?.message || 'calendar-invocation-failed')
  }
}
