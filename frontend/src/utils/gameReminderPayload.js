// Reminder payload builder for local game reminders (ISSUE-290).
// Mirrors utils/gameSharePayload.js: this module only computes data, it
// never touches a plugin or storage. The 1-hour lead time matches the
// existing server-scheduled push reminder in
// backend/app/routers/notifications.py (`reminder_time = scheduled_at -
// timedelta(hours=1)`), so the local fallback fires at the same moment the
// push reminder is meant to.
const REMINDER_LEAD_TIME_MS = 60 * 60 * 1000

// Deterministic FNV-1a 32-bit hash, cleared to a positive int.
// @capacitor/local-notifications requires an integer id; game ids are UUID
// strings, so a stable id must be derived to schedule/cancel consistently.
export function gameReminderNotificationId(gameId) {
  const value = String(gameId ?? '')
  let hash = 0x811c9dc5

  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193)
  }

  return hash >>> 1
}

// Returns null when the game has no resolvable schedule or the reminder
// moment (scheduled time minus the lead time) has already passed — the same
// "do not act on stale local state" posture used throughout the sharing
// architecture (docs/native-sharing-architecture.md).
export function buildGameReminderPayload({ game, fieldName, t }) {
  const gameId = game?.id
  if (!gameId) {
    return null
  }

  const scheduledAt = game?.scheduled_at ? new Date(game.scheduled_at) : null
  if (!scheduledAt || Number.isNaN(scheduledAt.getTime())) {
    return null
  }

  const remindAt = new Date(scheduledAt.getTime() - REMINDER_LEAD_TIME_MS)
  if (remindAt.getTime() <= Date.now()) {
    return null
  }

  const sportType = String(game.sport_type || '').toLowerCase()
  const sport = t(`values.${sportType}`, game.sport_type || '')
  const field = fieldName || t('field.unnamed')

  return {
    id: gameReminderNotificationId(gameId),
    title: t('game.remindNotificationTitle'),
    body: t('game.remindNotificationBody', { field, sport }),
    at: remindAt,
  }
}
