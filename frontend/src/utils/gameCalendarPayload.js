import { buildGameShareUrl } from './shareLink.js'
import { formatScheduledDate } from './gameSharePayload.js'
import { buildGoogleMapsNavigationUrl } from '../api/googleMapsNavigation.js'
import { parseValidCoordinates } from './coordinates.js'

// Standard game duration, mirroring the backend default
// (backend/app/routers/game_lifecycle.py: `expires_at = started_at +
// timedelta(hours=2)`) — used only as a fallback when a game has no usable
// expires_at to derive an end time from.
const DEFAULT_GAME_DURATION_MS = 2 * 60 * 60 * 1000

function parseDate(value) {
  if (!value) {
    return null
  }

  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? null : date
}

// A scheduled game's real start is scheduled_at; an immediate/active game
// has no scheduled_at and started_at defaults to creation time (backend
// game_lifecycle.py `started_at = scheduled_at or now`) — so exactly one of
// the two is the correct start in every case.
function resolveStart(game) {
  return parseDate(game?.scheduled_at) || parseDate(game?.started_at)
}

function resolveEnd(game, start) {
  const expiresAt = parseDate(game?.expires_at)
  if (expiresAt && expiresAt.getTime() > start.getTime()) {
    return expiresAt
  }

  return new Date(start.getTime() + DEFAULT_GAME_DURATION_MS)
}

// Builds the { title, description, location, start, end, url } payload for
// adding a game to the device calendar. Mirrors utils/gameSharePayload.js
// and utils/gameReminderPayload.js: pure data computation only, this module
// never touches a plugin or native bridge. Returns null when the game has
// no resolvable id or start time — a calendar draft cannot be built from
// that, and callers must not silently fall back to "now".
export function buildGameCalendarPayload({ game, fieldName, fieldLat, fieldLng, locale, t }) {
  const url = buildGameShareUrl(game?.id)
  if (!url) {
    return null
  }

  const start = resolveStart(game)
  if (!start) {
    return null
  }

  const end = resolveEnd(game, start)

  const sportType = String(game?.sport_type || '').toLowerCase()
  const sport = t(`values.${sportType}`, game?.sport_type || '')
  const field = fieldName || t('field.unnamed')

  const title = t('game.calendar.eventTitle', { field, sport })

  const coordinates = parseValidCoordinates(fieldLat, fieldLng)
  // Prefer the human-readable field name for location; coordinates are only
  // a fallback when no name is available, per data-minimization guidance
  // (do not surface raw lat/lng when a proper place name already exists).
  const location = fieldName || (coordinates ? `${coordinates.latitude},${coordinates.longitude}` : '')

  const navigationUrl = coordinates
    ? buildGoogleMapsNavigationUrl(coordinates.latitude, coordinates.longitude)
    : null

  const formattedDate = formatScheduledDate(start.toISOString(), locale, t)

  const description = [
    t('game.calendar.descriptionSummary', { field, sport, date: formattedDate || '' }),
    navigationUrl,
    url,
    t('game.calendar.descriptionAppMessage'),
  ]
    .filter(Boolean)
    .join('\n')

  return { title, description, location, start, end, url }
}
