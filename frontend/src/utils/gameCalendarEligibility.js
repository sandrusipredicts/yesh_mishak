// Dedicated eligibility rule for the "Add to calendar" action (E07-01).
// Deliberately separate from isGameShareable() (utils/gameShareability.js):
// sharing intentionally stays available for an active game (there is still
// something happening to tell people about), but a calendar event is only
// useful *before* a game happens — once a game is active there is nothing
// left to schedule. Reusing the sharing rule here previously made the
// button available for active games, which is the bug this file fixes.
const CALENDAR_ELIGIBLE_STATUSES = new Set(['open', 'full'])

function parseDate(value) {
  if (!value) {
    return null
  }

  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

// `now` is injectable (defaults to Date.now()) so tests can exercise the
// past/future boundary deterministically, the same pattern used for the
// reminder lead-time calculation in utils/gameReminderPayload.js.
export function isGameCalendarEligible(game, { now = Date.now() } = {}) {
  const status = String(game?.status || '').toLowerCase()
  if (!CALENDAR_ELIGIBLE_STATUSES.has(status)) {
    return false
  }

  const scheduledAt = parseDate(game?.scheduled_at)
  if (!scheduledAt || scheduledAt.getTime() <= now) {
    return false
  }

  // Defensive second check against the project's other start-time field:
  // scheduled_at is set once at creation and never revised afterward
  // (backend/app/routers/game_lifecycle.py: `started_at = scheduled_at or
  // now`), so this should already agree with the scheduled_at check above,
  // but a game is not "upcoming" if anything indicates it has begun.
  const startedAt = parseDate(game?.started_at)
  if (startedAt && startedAt.getTime() <= now) {
    return false
  }

  return true
}
