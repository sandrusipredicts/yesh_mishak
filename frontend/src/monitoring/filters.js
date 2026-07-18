// Centralized, explicit expected-error filtering policy. Every signature
// filtered here is documented -- deliberately narrow rather than filtering
// broad error classes that could hide real bugs.
//
// Filtered (never reported as a crash):
//   - Google/native login user cancellation (authErrorMapping 'cancelled' kind
//     / native code 'USER_CANCELLED')
//   - Expected permission denial (location/notification 'denied' outcome)
//   - Expected authentication responses (HTTP 401/403 with no internal
//     exception attached)
//   - Normal validation errors (HTTP 422)
//   - Normal not-found (HTTP 404) and rate limiting (HTTP 429)
//   - Offline/network errors that calling code already handles (axios
//     ERR_NETWORK / ECONNABORTED / no response at all)
//   - Browser-extension noise (stack frames from chrome-extension://,
//     moz-extension://, safari-extension:// origins)
//
// NOT filtered: internal exceptions that unexpectedly occur while producing
// one of the above responses (those set no expected-error tag and so fall
// through to normal reporting).

const EXPECTED_HTTP_STATUSES = new Set([401, 403, 404, 422, 429])

const EXPECTED_TAG_VALUES = {
  auth_error_kind: new Set(['cancelled']),
  permission_result: new Set(['denied']),
  network_offline_handled: new Set(['true']),
}

const EXTENSION_ORIGIN_PATTERN = /chrome-extension:\/\/|moz-extension:\/\/|safari-extension:\/\//i

function getTagValue(event, key) {
  if (Array.isArray(event?.tags)) {
    const found = event.tags.find(([tagKey]) => tagKey === key)
    return found?.[1]
  }
  return event?.tags?.[key]
}

function hasExpectedTag(event) {
  return Object.entries(EXPECTED_TAG_VALUES).some(([tagKey, allowedValues]) => {
    const value = getTagValue(event, tagKey)
    return value !== undefined && allowedValues.has(String(value))
  })
}

function hasExpectedHttpStatus(event) {
  const status = getTagValue(event, 'http_status') ?? event?.contexts?.response?.status_code
  return status !== undefined && EXPECTED_HTTP_STATUSES.has(Number(status))
}

function isBrowserExtensionNoise(event) {
  const frames = event?.exception?.values?.flatMap((value) => value.stacktrace?.frames || []) || []
  return frames.some((frame) => EXTENSION_ORIGIN_PATTERN.test(frame.filename || ''))
}

/**
 * Returns true when the event matches a documented expected-outcome
 * signature and should be dropped in beforeSend.
 */
export function isExpectedError(event) {
  if (!event) {
    return false
  }
  if (getTagValue(event, 'monitoring_force_report') === 'true') {
    // Explicit escape hatch for the volume-based/impossible-state exception
    // (an otherwise-expected outcome that has become reportable) -- always
    // wins over the filters below.
    return false
  }
  return hasExpectedTag(event) || hasExpectedHttpStatus(event) || isBrowserExtensionNoise(event)
}
