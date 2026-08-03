export function getApiErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail

  if (typeof detail === 'string' && detail) {
    return detail
  }

  if (Array.isArray(detail) && detail.length > 0) {
    return detail[0]?.msg || fallback
  }

  if (detail?.message) {
    return detail.message
  }

  const message = error?.response?.data?.message
  if (typeof message === 'string' && message) {
    return message
  }

  return fallback
}

// Maps known API error responses to safe, localized user-facing message keys.
// Unknown errors get a safe generic fallback — never expose raw backend text.
const KNOWN_ERROR_CODES = {
  'CONFLICT': 'errors.conflict',
  'EMAIL_NOT_VERIFIED': 'auth.unverifiedNotice',
  'VERIFICATION_COOLDOWN': 'auth.resendCooldown',
  'RATE_LIMITED': 'errors.rateLimited',
  'ACCOUNT_LINK_REQUIRED': 'auth.accountLinkingRequired',
}

export function getSafeErrorMessage(error, t, fallbackKey = 'errors.generic') {
  const code = error?.response?.data?.code
  if (code && KNOWN_ERROR_CODES[code]) {
    return t(KNOWN_ERROR_CODES[code])
  }

  const status = error?.response?.status
  if (status === 401) return t('errors.unauthorized')
  if (status === 403) return t('errors.forbidden')
  if (status === 404) return t('errors.notFound')
  if (status === 409) return t('errors.conflict')
  if (status === 422) return t('errors.validation')
  if (status === 429) return t('errors.rateLimited')
  if (status >= 500) return t('errors.serverError')

  if (!error?.response) return t('errors.networkError')

  return t(fallbackKey)
}
