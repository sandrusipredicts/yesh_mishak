import { buildGameReminderPayload } from '../utils/gameReminderPayload.js'
import {
  cancelLocalNotification,
  isLocalNotificationSupported,
  scheduleLocalNotification,
} from './localNotifications.js'

// Reminder orchestrator for games (ISSUE-290). The only entry point UI
// components call to schedule/cancel a game reminder — mirrors
// api/gameSharing.js's role for sharing. Owns the local "is a reminder
// currently scheduled for this game" record so components stay thin.
const STORAGE_KEY = 'game_reminder_ids'

function hasLocalStorage() {
  return typeof localStorage !== 'undefined'
}

function readStore() {
  if (!hasLocalStorage()) {
    return {}
  }

  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : {}
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

function writeStore(store) {
  if (!hasLocalStorage()) {
    return
  }

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store))
  } catch {
    // Best-effort only. A reminder that fails to persist here still fires —
    // it just cannot be reconciled/cancelled reliably after a reload.
  }
}

export function getStoredGameReminder(gameId) {
  if (!gameId) {
    return null
  }
  return readStore()[gameId] ?? null
}

function setStoredGameReminder(gameId, entry) {
  const store = readStore()
  store[gameId] = entry
  writeStore(store)
}

function clearStoredGameReminder(gameId) {
  const store = readStore()
  if (gameId in store) {
    delete store[gameId]
    writeStore(store)
  }
}

export { isLocalNotificationSupported }

export async function scheduleGameReminder(
  { game, fieldName, t },
  { scheduleNotification = scheduleLocalNotification } = {},
) {
  const payload = buildGameReminderPayload({ game, fieldName, t })

  if (!payload) {
    return { outcome: 'unavailable', reason: 'invalid-resource' }
  }

  const result = await scheduleNotification(payload)

  if (result.outcome === 'scheduled') {
    setStoredGameReminder(game.id, {
      notificationId: payload.id,
      remindAt: payload.at.toISOString(),
    })
  }

  return result
}

// Best-effort cleanup: always clears the local record even if the native
// cancel call fails, so the UI never gets stuck offering "cancel" for a
// reminder the app can no longer act on. A stray notification firing once
// for a game the user left is a minor inconvenience, not a correctness bug.
export async function cancelGameReminder(
  gameId,
  { cancelNotification = cancelLocalNotification } = {},
) {
  const stored = getStoredGameReminder(gameId)

  if (!stored) {
    return true
  }

  await cancelNotification(stored.notificationId)
  clearStoredGameReminder(gameId)
  return true
}
