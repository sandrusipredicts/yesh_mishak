const AUTH_ERROR_RESULTS = {
  cancelled: {
    kind: 'cancelled',
    messageKey: 'auth.signInCancelled',
    severity: 'info',
    shouldClearSession: true,
  },
  network: {
    kind: 'network',
    messageKey: 'auth.networkError',
    severity: 'error',
    shouldClearSession: true,
  },
  verificationFailed: {
    kind: 'verification_failed',
    messageKey: 'auth.verificationFailed',
    severity: 'error',
    shouldClearSession: true,
  },
  serverTemporary: {
    kind: 'server_temporary',
    messageKey: 'auth.serverTemporaryError',
    severity: 'error',
    shouldClearSession: true,
  },
  googleProviderFailed: {
    kind: 'google_provider_failed',
    messageKey: 'auth.googleSignInFailed',
    severity: 'error',
    shouldClearSession: true,
  },
  googleConfiguration: {
    kind: 'google_configuration',
    messageKey: 'auth.googleConfigurationError',
    severity: 'error',
    shouldClearSession: true,
  },
  unexpected: {
    kind: 'unexpected',
    messageKey: 'auth.signInUnexpectedError',
    severity: 'error',
    shouldClearSession: true,
  },
  accountLinkingRequired: {
    kind: 'account_linking_required',
    messageKey: 'auth.accountLinkingRequired',
    severity: 'error',
    shouldClearSession: true,
  },
}

const NETWORK_ERROR_CODES = new Set(['ERR_NETWORK', 'ECONNABORTED', 'ETIMEDOUT'])
const VERIFICATION_STATUSES = new Set([400, 401, 403])

export function mapNativeAuthError(error) {
  if (error?.code === 'USER_CANCELLED') {
    return AUTH_ERROR_RESULTS.cancelled
  }

  const status = error?.response?.status
  const detail = error?.response?.data?.detail

  if (status === 409 && detail?.code === 'ACCOUNT_LINKING_REQUIRED') {
    return AUTH_ERROR_RESULTS.accountLinkingRequired
  }

  if (VERIFICATION_STATUSES.has(status)) {
    return AUTH_ERROR_RESULTS.verificationFailed
  }

  if (status >= 500 && status <= 599) {
    return AUTH_ERROR_RESULTS.serverTemporary
  }

  if (
    error?.isAxiosError &&
    (NETWORK_ERROR_CODES.has(error.code) || !error.response)
  ) {
    return AUTH_ERROR_RESULTS.network
  }

  if (error?.code === 'NATIVE_GOOGLE_MISSING_ID_TOKEN') {
    return AUTH_ERROR_RESULTS.verificationFailed
  }

  if (error?.code === 'NATIVE_GOOGLE_CONFIGURATION_ERROR') {
    return AUTH_ERROR_RESULTS.googleConfiguration
  }

  if (error?.code === 'GOOGLE_SIGN_IN_FAILED') {
    return AUTH_ERROR_RESULTS.googleProviderFailed
  }

  return AUTH_ERROR_RESULTS.unexpected
}
