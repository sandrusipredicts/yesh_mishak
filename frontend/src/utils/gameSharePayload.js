import { buildCanonicalShareLink } from './shareLink.js'

function formatScheduledDate(value, locale) {
  const date = new Date(value)

  if (Number.isNaN(date.getTime())) {
    return null
  }

  return new Intl.DateTimeFormat(locale, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
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

  const sport = t(`values.${game.sport_type}`, game.sport_type || '')
  const field = fieldName || t('field.unnamed')
  const status = String(game.status || '').toLowerCase()
  const scheduledDate = game.scheduled_at ? formatScheduledDate(game.scheduled_at, locale) : null
  const isUpcoming = scheduledDate !== null && new Date(game.scheduled_at).getTime() > Date.now()
  const capacity = t('game.players', { current: game.players_present, max: game.max_players })

  const title = t('game.share.title', { field, sport })

  let text
  if (status === 'finished') {
    text = t('game.share.textFinished', { field, sport })
  } else if (status === 'cancelled') {
    text = t('game.share.textCancelled', { field, sport })
  } else if (isUpcoming && status === 'full') {
    text = t('game.share.textScheduledFull', { field, sport, date: scheduledDate, capacity })
  } else if (isUpcoming) {
    text = t('game.share.textScheduledOpen', { field, sport, date: scheduledDate, capacity })
  } else if (status === 'full') {
    text = t('game.share.textFull', { field, sport, capacity })
  } else {
    text = t('game.share.textOpen', { field, sport, capacity })
  }

  return { title, text, url }
}
