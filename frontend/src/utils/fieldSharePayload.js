import { buildCanonicalShareLink } from './shareLink.js'

// Builds the normalized { title, text, url } payload for sharing a field,
// following the same contract as gameSharePayload.js. The text is a short
// Hebrew-friendly message containing the field name, city (when available),
// and the canonical URL. Only public data is included — no user identity.
export function buildFieldSharePayload({ field, t }) {
  const url = buildCanonicalShareLink('field', field?.id)

  if (!url) {
    return null
  }

  const name = field.name || t('field.unnamed')
  const city = field.city || field.location || ''

  const title = t('field.share.title', { name })

  const text = city
    ? t('field.share.textWithCity', { name, city })
    : t('field.share.text', { name })

  return { title, text, url }
}
