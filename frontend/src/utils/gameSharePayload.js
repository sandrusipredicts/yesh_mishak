import { buildCanonicalShareLink } from './shareLink.js'

const SPORT_EMOJI = {
  football: '⚽',
  basketball: '🏀',
}

function getSportEmoji(sportType) {
  return SPORT_EMOJI[String(sportType || '').toLowerCase()] || '🎽'
}

function isToday(date) {
  const now = new Date()
  return (
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate()
  )
}

function isTomorrow(date) {
  const tomorrow = new Date()
  tomorrow.setDate(tomorrow.getDate() + 1)
  return (
    date.getFullYear() === tomorrow.getFullYear() &&
    date.getMonth() === tomorrow.getMonth() &&
    date.getDate() === tomorrow.getDate()
  )
}

function formatTimeOnly(date, locale) {
  try {
    return new Intl.DateTimeFormat(locale, { hour: '2-digit', minute: '2-digit' }).format(date)
  } catch {
    return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`
  }
}

export function formatScheduledDate(value, locale, t) {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return null
  }

  const time = formatTimeOnly(date, locale)

  if (isToday(date)) {
    return t('share.dateToday', { time })
  }

  if (isTomorrow(date)) {
    return t('share.dateTomorrow', { time })
  }

  try {
    const datePart = new Intl.DateTimeFormat(locale, { dateStyle: 'medium' }).format(date)
    return `${datePart}, ${time}`
  } catch {
    return `${date.toLocaleDateString()}, ${time}`
  }
}

// Builds the normalized { title, text, url } payload for sharing a game,
// per docs/native-sharing-architecture.md §6.1. `url` is the canonical
// link alone — the text templates never repeat it, matching the payload
// contract ("canonical URL not manually duplicated when the API has a
// separate URL field"). Contains only public data: field name, sport,
// schedule/current state, and aggregate capacity — no participant or
// creator identity per docs/sharing-requirements.md §6.1/§6.4.
export function buildGameSharePayload({ game, fieldName, locale, t }) {
  const url = buildCanonicalShareLink('game', game?.id)

  if (!url) {
    return null
  }

  const sportType = String(game.sport_type || '').toLowerCase()
  const emoji = getSportEmoji(sportType)
  const sport = t(`values.${game.sport_type}`, game.sport_type || '')
  const field = fieldName || t('field.unnamed')
  const status = String(game.status || '').toLowerCase()
  const scheduledDate = game.scheduled_at ? formatScheduledDate(game.scheduled_at, locale, t) : null
  const isUpcoming = scheduledDate !== null && new Date(game.scheduled_at).getTime() > Date.now()
  const current = game.players_present
  const max = game.max_players
  const hasCapacity = current != null && max != null
  const capacity = hasCapacity ? t('game.players', { current, max }) : ''

  const title = t('game.share.title', { field, sport })

  let text
  if (status === 'finished') {
    text = t('game.share.textFinished', { emoji, field, sport })
  } else if (status === 'cancelled') {
    text = t('game.share.textCancelled', { emoji, field, sport })
  } else if (isUpcoming && status === 'full') {
    text = t('game.share.textScheduledFull', { emoji, field, sport, date: scheduledDate, capacity })
  } else if (isUpcoming) {
    text = t('game.share.textScheduledOpen', { emoji, field, sport, date: scheduledDate, capacity })
  } else if (status === 'full') {
    text = t('game.share.textFull', { emoji, field, sport, capacity })
  } else {
    text = t('game.share.textOpen', { emoji, field, sport, capacity })
  }

  // Clean up any residual double whitespace from empty interpolation values
  text = text.replace(/ {2,}/g, ' ').trim()

  return { title, text, url }
}
