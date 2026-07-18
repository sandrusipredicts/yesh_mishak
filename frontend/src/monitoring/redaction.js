// Pure, non-mutating redaction helpers shared by beforeSend/beforeBreadcrumb.
// Deliberately conservative: false positives (redacting a benign field whose
// name happens to contain "token") are far safer than false negatives
// (leaking a secret), so the key pattern below is intentionally broad.

const REDACTED = '[Redacted]'
const MAX_DEPTH = 8

// Matches password/token/secret/authorization/cookie/api-key/credential/jwt/
// refresh/verification-style keys, case-insensitively, anywhere in the key.
const SENSITIVE_KEY_PATTERN =
  /pass(word)?|token|secret|authoriz|cookie|api[-_]?key|credential|jwt|refresh|verification|dsn|push[-_]?token/i

const COORDINATE_KEY_PATTERN = /^(lat(itude)?|lon(gitude)?|lng|coords?|coordinates?)$/i

function isSensitiveKey(key) {
  if (typeof key !== 'string') {
    return false
  }
  return SENSITIVE_KEY_PATTERN.test(key) || COORDINATE_KEY_PATTERN.test(key)
}

/**
 * Deep-redacts an arbitrary value without mutating the input. Handles
 * nested objects/arrays and guards against circular references.
 */
export function redactDeep(value, { depth = 0, seen = new WeakSet() } = {}) {
  if (value === null || value === undefined) {
    return value
  }

  if (depth >= MAX_DEPTH) {
    return '[MaxDepth]'
  }

  if (Array.isArray(value)) {
    return value.map((item) => redactDeep(item, { depth: depth + 1, seen }))
  }

  if (typeof value === 'object') {
    if (seen.has(value)) {
      return '[Circular]'
    }
    seen.add(value)

    const result = {}
    for (const [key, val] of Object.entries(value)) {
      if (isSensitiveKey(key)) {
        result[key] = REDACTED
      } else if (val && typeof val === 'object') {
        result[key] = redactDeep(val, { depth: depth + 1, seen })
      } else {
        result[key] = val
      }
    }
    return result
  }

  return value
}

/**
 * Reduces a URL to its safe path (origin + pathname) only. Query strings and
 * fragments may carry tokens, verification codes, or deep-link parameters,
 * so they are dropped entirely rather than selectively filtered.
 */
export function toSafeUrlPath(url) {
  if (!url || typeof url !== 'string') {
    return url
  }

  try {
    const parsed = new URL(url, 'https://placeholder.invalid')
    const isPlaceholderOrigin = parsed.origin === 'https://placeholder.invalid'
    return isPlaceholderOrigin ? parsed.pathname : `${parsed.origin}${parsed.pathname}`
  } catch {
    // Not a parseable URL (e.g. already just a path) -- strip anything from
    // the first '?' or '#' onward as a best-effort fallback.
    return url.split('?')[0].split('#')[0]
  }
}

function redactRequestSection(request) {
  if (!request || typeof request !== 'object') {
    return request
  }

  const redacted = { ...request }

  if (typeof redacted.url === 'string') {
    redacted.url = toSafeUrlPath(redacted.url)
  }
  if (typeof redacted.query_string === 'string' || typeof redacted.query_string === 'object') {
    delete redacted.query_string
  }
  if (redacted.cookies !== undefined) {
    delete redacted.cookies
  }
  if (redacted.headers && typeof redacted.headers === 'object') {
    redacted.headers = redactDeep(redacted.headers)
  }
  if (redacted.data !== undefined) {
    // Full request bodies are never sent by default, regardless of content.
    delete redacted.data
  }

  return redacted
}

/**
 * Applied via Sentry's beforeSend hook. Scrubs request context, extra data,
 * and breadcrumb payloads on the outgoing event without mutating anything
 * the SDK itself continues to hold a reference to.
 */
export function redactEvent(event) {
  if (!event || typeof event !== 'object') {
    return event
  }

  const redacted = { ...event }

  if (redacted.request) {
    redacted.request = redactRequestSection(redacted.request)
  }
  if (redacted.extra) {
    redacted.extra = redactDeep(redacted.extra)
  }
  if (redacted.contexts) {
    redacted.contexts = redactDeep(redacted.contexts)
  }
  if (Array.isArray(redacted.breadcrumbs)) {
    redacted.breadcrumbs = redacted.breadcrumbs.map(redactBreadcrumb)
  }
  if (redacted.user && typeof redacted.user === 'object') {
    // Only the internal id is ever set (see monitoring/client.js); strip
    // anything else defensively in case a future call site adds more.
    redacted.user = redacted.user.id ? { id: redacted.user.id } : undefined
  }

  return redacted
}

/**
 * Applied via Sentry's beforeBreadcrumb hook -- the single choke point for
 * both SDK-generated breadcrumbs (console, xhr/fetch) and ones added via
 * monitoring/client.js's addBreadcrumb helper.
 */
export function redactBreadcrumb(breadcrumb) {
  if (!breadcrumb || typeof breadcrumb !== 'object') {
    return breadcrumb
  }

  const redacted = { ...breadcrumb }

  if (redacted.data) {
    redacted.data = redactDeep(redacted.data)
    if (typeof redacted.data.url === 'string') {
      redacted.data.url = toSafeUrlPath(redacted.data.url)
    }
  }

  // xhr/fetch breadcrumbs from the default integrations report the request
  // header set for Authorization/Cookie; scrub anywhere headers may appear.
  if (redacted.data?.request_headers) {
    redacted.data.request_headers = redactDeep(redacted.data.request_headers)
  }
  if (redacted.data?.response_headers) {
    redacted.data.response_headers = redactDeep(redacted.data.response_headers)
  }

  return redacted
}
