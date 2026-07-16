import { Capacitor } from '@capacitor/core'

export const LINK_OPEN_DEDUPE_WINDOW_MS = 5000

const VALID_EVENT_NAMES = new Set(['share_action', 'link_open'])
const VALID_ENTITY_TYPES = new Set(['game', 'field'])
const VALID_PLATFORMS = new Set(['web', 'android', 'ios'])
const VALID_MECHANISMS = new Set(['native_share', 'copy_link'])
const VALID_SHARE_OUTCOMES = new Set(['shared', 'copied', 'cancelled', 'unavailable', 'failed'])
const VALID_LINK_OUTCOMES = new Set(['valid', 'invalid', 'not_found', 'deferred_for_auth'])
const VALID_ERROR_CATEGORIES = new Set([
  'invalid_resource',
  'unsupported_platform',
  'share_unavailable',
  'share_failed',
  'clipboard_failed',
  'malformed_link',
  'unsupported_link',
  'resource_not_found',
  'resolution_failed',
])

const linkOpenDedupe = new Map()

function getPlatform() {
  try {
    const platform = Capacitor.getPlatform()
    return VALID_PLATFORMS.has(platform) ? platform : 'web'
  } catch {
    return 'web'
  }
}

function normalizeShareMechanism(mechanism) {
  if (mechanism === 'native-share') {
    return 'native_share'
  }
  if (mechanism === 'clipboard') {
    return 'copy_link'
  }
  return mechanism
}

function errorCategoryFromReason(reason) {
  if (reason === 'invalid-resource') {
    return 'invalid_resource'
  }
  if (reason === 'unsupported-platform') {
    return 'unsupported_platform'
  }
  if (reason === 'share-api-unavailable') {
    return 'share_unavailable'
  }
  if (reason === 'share-invocation-failed' || reason === 'invalid-payload') {
    return 'share_failed'
  }
  if (reason === 'clipboard-write-failed') {
    return 'clipboard_failed'
  }
  if (reason === 'malformed-url' || reason === 'non-https-url' || reason === 'wrong-host') {
    return 'malformed_link'
  }
  if (
    reason === 'invalid-game-id' ||
    reason === 'invalid-field-id' ||
    reason === 'unsupported-game-action' ||
    reason === 'unsupported-path'
  ) {
    return 'unsupported_link'
  }
  return undefined
}

function isValidEventPayload(payload) {
  if (!payload || typeof payload !== 'object' || Array.isArray(payload)) {
    return false
  }
  if (!VALID_EVENT_NAMES.has(payload.event_name)) return false
  if (!VALID_ENTITY_TYPES.has(payload.entity_type)) return false
  if (!VALID_PLATFORMS.has(payload.platform)) return false
  if (payload.error_category && !VALID_ERROR_CATEGORIES.has(payload.error_category)) return false

  if (payload.event_name === 'share_action') {
    return (
      VALID_MECHANISMS.has(payload.mechanism) &&
      VALID_SHARE_OUTCOMES.has(payload.outcome)
    )
  }

  return (
    payload.mechanism === undefined &&
    VALID_LINK_OUTCOMES.has(payload.outcome)
  )
}

function submitEvent(payload, options = {}) {
  if (!isValidEventPayload(payload)) {
    return
  }

  if (!options.post && typeof window === 'undefined') {
    return
  }

  Promise.resolve()
    .then(async () => {
      if (options.post) {
        return options.post('/analytics/share-events', payload)
      }
      const { api } = await import('./client.js')
      return api.post('/analytics/share-events', payload)
    })
    .catch((error) => {
      console.warn('Share analytics submission failed.', error?.response?.status || error?.message || error)
    })
}

export function recordShareAction(entityType, result, options = {}) {
  const mechanism = options.mechanism || normalizeShareMechanism(result?.mechanism)
  const payload = {
    event_name: 'share_action',
    entity_type: entityType,
    platform: options.platform || getPlatform(),
    mechanism,
    outcome: result?.outcome,
    error_category: errorCategoryFromReason(result?.reason),
  }

  submitEvent(payload, options)
}

export function inferEntityTypeFromRouteResult(result) {
  if (result?.routeType === 'game' || result?.reason === 'invalid-game-id' || result?.reason === 'unsupported-game-action') {
    return 'game'
  }
  if (result?.routeType === 'field' || result?.reason === 'invalid-field-id') {
    return 'field'
  }
  return null
}

export function buildLinkOpenPayload(result, outcome, options = {}) {
  const entityType = options.entityType || inferEntityTypeFromRouteResult(result)
  if (!entityType) {
    return null
  }

  const errorCategory =
    options.errorCategory ||
    (outcome === 'not_found' ? 'resource_not_found' : undefined) ||
    (outcome === 'invalid' ? errorCategoryFromReason(result?.reason) : undefined) ||
    (outcome === 'failed' ? 'resolution_failed' : undefined)

  return {
    event_name: 'link_open',
    entity_type: entityType,
    platform: options.platform || getPlatform(),
    outcome,
    ...(errorCategory ? { error_category: errorCategory } : {}),
  }
}

export function recordLinkOpen(result, outcome, options = {}) {
  const payload = buildLinkOpenPayload(result, outcome, options)
  if (!payload) {
    return false
  }

  const now = options.now ?? Date.now()
  const ttl = options.dedupeWindowMs ?? LINK_OPEN_DEDUPE_WINDOW_MS
  const dedupeKey = options.dedupeKey || [
    payload.event_name,
    payload.entity_type,
    payload.platform,
    payload.outcome,
    result?.routeType || '',
    result?.resourceId || '',
    result?.action || '',
    result?.reason || '',
  ].join('|')

  for (const [key, expiresAt] of linkOpenDedupe.entries()) {
    if (expiresAt <= now) {
      linkOpenDedupe.delete(key)
    }
  }

  if (linkOpenDedupe.has(dedupeKey)) {
    return false
  }

  linkOpenDedupe.set(dedupeKey, now + ttl)
  submitEvent(payload, options)
  return true
}

export function resetShareAnalyticsDedupeForTests() {
  linkOpenDedupe.clear()
}
