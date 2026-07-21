export const CANONICAL_APP_LINK_HOST = 'yesh-mishak.com'

const UUID_V4_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

export function isUuidV4(value) {
  return UUID_V4_PATTERN.test(value)
}

function buildSupportedResult({ routeType, resourceId = '', action = '', navigationPath }) {
  return {
    ok: true,
    routeType,
    resourceId,
    action,
    navigationPath,
  }
}

function buildFallbackResult(reason) {
  return {
    ok: true,
    routeType: 'fallback',
    reason,
    navigationPath: '/',
  }
}

function buildRejectedResult(reason) {
  return {
    ok: false,
    reason,
  }
}

function parseLegacyQuery(searchParams) {
  const gameId = searchParams.get('game_id')
  const fieldId = searchParams.get('field_id')

  if (gameId) {
    return isUuidV4(gameId)
      ? buildSupportedResult({
        routeType: 'game',
        resourceId: gameId,
        navigationPath: '/',
      })
      : buildFallbackResult('invalid-game-id')
  }

  if (fieldId) {
    return isUuidV4(fieldId)
      ? buildSupportedResult({
        routeType: 'field',
        resourceId: fieldId,
        navigationPath: '/',
      })
      : buildFallbackResult('invalid-field-id')
  }

  return null
}

function resolvePathSegments(segments, searchParams) {
  if (segments.length === 0) {
    return parseLegacyQuery(searchParams) ?? buildSupportedResult({
      routeType: 'home',
      navigationPath: '/',
    })
  }

  if (segments.length === 1 && segments[0] === 'my-games') {
    return buildSupportedResult({
      routeType: 'my-games',
      navigationPath: '/my-games',
    })
  }

  if (segments.length === 1 && (segments[0] === 'privacy' || segments[0] === 'terms')) {
    return buildSupportedResult({
      routeType: segments[0],
      navigationPath: `/${segments[0]}`,
    })
  }

  if (segments.length === 1 && segments[0] === 'admin') {
    return buildSupportedResult({
      routeType: 'admin',
      navigationPath: '/admin',
    })
  }

  if (segments.length === 1 && segments[0] === 'forgot-password') {
    return buildSupportedResult({
      routeType: 'forgot-password',
      navigationPath: '/forgot-password',
    })
  }

  if (segments.length === 1 && segments[0] === 'reset-password') {
    return buildSupportedResult({
      routeType: 'reset-password',
      navigationPath: searchParams.has('token')
        ? `/reset-password?token=${encodeURIComponent(searchParams.get('token'))}`
        : '/reset-password',
    })
  }

  if (segments.length === 1 && segments[0] === 'verify-email') {
    const token = searchParams.get('token') || ''
    return token.length >= 32 && token.length <= 512
      ? buildSupportedResult({
        routeType: 'email-verification',
        navigationPath: `/verify-email?token=${encodeURIComponent(token)}`,
      })
      : buildFallbackResult('invalid-verification-token')
  }

  if (segments.length === 2 && (segments[0] === 'field' || segments[0] === 'fields')) {
    const fieldId = segments[1]

    return isUuidV4(fieldId)
      ? buildSupportedResult({
        routeType: 'field',
        resourceId: fieldId,
        navigationPath: '/',
      })
      : buildFallbackResult('invalid-field-id')
  }

  if (
    (segments.length === 2 || segments.length === 3) &&
    (segments[0] === 'game' || segments[0] === 'games')
  ) {
    const gameId = segments[1]
    const action = segments[2] ?? ''

    if (action && action !== 'join') {
      return buildFallbackResult('unsupported-game-action')
    }

    return isUuidV4(gameId)
      ? buildSupportedResult({
        routeType: 'game',
        resourceId: gameId,
        action,
        navigationPath: '/',
      })
      : buildFallbackResult('invalid-game-id')
  }

  return buildFallbackResult('unsupported-path')
}

export function normalizeAppLinkUrl(rawUrl) {
  let url

  try {
    url = new URL(rawUrl)
  } catch {
    return buildRejectedResult('malformed-url')
  }

  if (url.protocol !== 'https:') {
    return buildRejectedResult('non-https-url')
  }

  if (url.hostname !== CANONICAL_APP_LINK_HOST) {
    return buildRejectedResult('wrong-host')
  }

  const segments = url.pathname.split('/').filter(Boolean)

  return resolvePathSegments(segments, url.searchParams)
}

// Same-origin counterpart to normalizeAppLinkUrl: resolves the SPA's own
// window.location.pathname (set via history.pushState or a direct browser
// load) into a deep-link target. Host/protocol are not re-validated here
// because the pathname is already same-origin by construction; it reuses
// the identical segment-matching rules so game/field routes never diverge
// between the two arrival paths (external URL vs. in-app navigation).
export function parseAppPathname(pathname, search = '') {
  const segments = String(pathname || '').split('/').filter(Boolean)
  const searchParams = new URLSearchParams(search)

  return resolvePathSegments(segments, searchParams)
}
