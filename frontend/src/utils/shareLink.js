import { CANONICAL_APP_LINK_HOST, isUuidV4 } from './appLinkRoutes.js'

// Canonical outbound link generation for every shareable entity type.
// This module owns share-URL construction exclusively; nothing else may
// concatenate a share URL (docs/native-sharing-architecture.md AD-04/AD-20).
const ENTITY_ROUTES = {
  game: 'game',
  field: 'fields',
}

export function buildCanonicalShareLink(entityType, resourceId) {
  const route = ENTITY_ROUTES[entityType]

  if (!route || typeof resourceId !== 'string' || !isUuidV4(resourceId)) {
    return null
  }

  return `https://${CANONICAL_APP_LINK_HOST}/${route}/${resourceId.toLowerCase()}`
}

export function buildGameShareUrl(gameId) {
  return buildCanonicalShareLink('game', gameId)
}

export function buildFieldShareUrl(fieldId) {
  return buildCanonicalShareLink('field', fieldId)
}
