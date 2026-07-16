// RFC 5545 (iCalendar) event serializer for the web "Add to calendar"
// fallback. Pure formatting only — takes the same platform-agnostic
// payload as api/nativeCalendar.js (utils/gameCalendarPayload.js) and never
// touches the DOM or a plugin, so it can be unit tested directly.

// Bounds an already-short field defensively; a runaway description (e.g.
// pathological input) must not produce an oversized .ics file or line.
const MAX_TEXT_LENGTH = 1000

// Escapes TEXT values per RFC 5545 §3.3.11: backslash, then the characters
// that are otherwise significant to the format (semicolon, comma), then
// newlines as the literal two-character sequence "\n".
function escapeText(value) {
  return String(value ?? '')
    .slice(0, MAX_TEXT_LENGTH)
    .replace(/\\/g, '\\\\')
    .replace(/;/g, '\\;')
    .replace(/,/g, '\\,')
    .replace(/\r\n|\r|\n/g, '\\n')
}

// UTC, Z-suffixed timestamps (RFC 5545 §3.3.5 form 2) are used instead of a
// TZID so the event never depends on a bundled timezone database and is
// correct across DST transitions by construction — the Date instant is
// already the correct moment in time, only its textual representation
// changes here.
function formatUtcTimestamp(date) {
  return date.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z')
}

function foldLine(line) {
  // RFC 5545 §3.1 line folding: split at 75 octets, continuation lines
  // start with a single space. Simple index-based slicing is sufficient
  // here since our content is short ASCII-range text after escaping.
  if (line.length <= 75) {
    return line
  }

  const parts = []
  let rest = line
  while (rest.length > 75) {
    parts.push(rest.slice(0, 75))
    rest = ' ' + rest.slice(75)
  }
  parts.push(rest)
  return parts.join('\r\n')
}

// Builds a stable UID so re-generating the same game's event twice produces
// the same identifier — most calendar apps de-duplicate an unmodified
// re-import by UID, though this is best-effort, not guaranteed.
function buildUid(gameId) {
  return `${gameId || 'game'}@yesh-mishak.com`
}

// Builds an RFC 5545-compatible VCALENDAR string from a calendar payload
// (utils/gameCalendarPayload.js). Returns null when the payload has no
// resolvable start time, matching the payload builder's own contract.
export function buildIcsEvent(payload, { gameId } = {}) {
  if (!payload || !(payload.start instanceof Date) || Number.isNaN(payload.start.getTime())) {
    return null
  }

  const end = payload.end instanceof Date && !Number.isNaN(payload.end.getTime())
    ? payload.end
    : payload.start

  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Yesh Mishak//Add to Calendar//EN',
    'CALSCALE:GREGORIAN',
    'BEGIN:VEVENT',
    `UID:${escapeText(buildUid(gameId))}`,
    `DTSTAMP:${formatUtcTimestamp(new Date())}`,
    `DTSTART:${formatUtcTimestamp(payload.start)}`,
    `DTEND:${formatUtcTimestamp(end)}`,
    `SUMMARY:${escapeText(payload.title)}`,
  ]

  if (payload.location) {
    lines.push(`LOCATION:${escapeText(payload.location)}`)
  }

  if (payload.description) {
    lines.push(`DESCRIPTION:${escapeText(payload.description)}`)
  }

  if (payload.url) {
    lines.push(`URL:${escapeText(payload.url)}`)
  }

  lines.push('END:VEVENT', 'END:VCALENDAR')

  return lines.map(foldLine).join('\r\n') + '\r\n'
}

// A safe, ASCII-only filename derived from the game id — never derived from
// user-controlled text (title/location), which could otherwise inject path
// separators or other unsafe characters into a downloaded filename.
export function buildIcsFilename(gameId) {
  const safeId = String(gameId || '').replace(/[^a-zA-Z0-9-]/g, '')
  return `game-${safeId || 'event'}.ics`
}
