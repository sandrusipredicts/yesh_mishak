import { CANONICAL_APP_LINK_HOST, isUuidV4 } from './appLinkRoutes.js'

// Only 'game' is wired up (ISSUE-284 scope). A future field-sharing issue
// registers 'field' here and reuses this same builder unchanged, per
// docs/native-sharing-architecture.md AD-04/AD-20 — the module owns
// canonical outbound link generation exclusively; nothing else may
// concatenate a share URL.
const ENTITY_ROUTES = {
  game: 'game',
}

export function buildCanonicalShareLink(entityType, resourceId) {
  const route = ENTITY_ROUTES[entityType]

  if (!route || typeof resourceId !== 'string' || !isUuidV4(resourceId)) {
    return null
  }

  return `https://${CANONICAL_APP_LINK_HOST}/${route}/${resourceId.toLowerCase()}`
}
