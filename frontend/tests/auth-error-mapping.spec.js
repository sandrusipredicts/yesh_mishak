import { expect, test } from '@playwright/test'

import { mapNativeAuthError } from '../src/api/authErrorMapping.js'

const expected = (kind, messageKey, severity = 'error') => ({
  kind,
  messageKey,
  severity,
  shouldClearSession: true,
})

test('maps user cancellation to neutral informational cleanup', () => {
  expect(mapNativeAuthError({ code: 'USER_CANCELLED' })).toEqual(
    expected('cancelled', 'auth.signInCancelled', 'info'),
  )
})

test('maps network, no-response, and timeout failures', () => {
  for (const error of [
    { isAxiosError: true, code: 'ERR_NETWORK', request: {} },
    { isAxiosError: true, request: {} },
    { isAxiosError: true, code: 'ECONNABORTED', request: {} },
    { isAxiosError: true, code: 'ETIMEDOUT', request: {} },
  ]) {
    expect(mapNativeAuthError(error)).toEqual(
      expected('network', 'auth.networkError'),
    )
  }
})

test('maps backend invalid-token statuses to verification failure', () => {
  for (const status of [400, 401, 403]) {
    expect(mapNativeAuthError({ response: { status } })).toEqual(
      expected('verification_failed', 'auth.verificationFailed'),
    )
  }
})

test('maps backend 5xx statuses to a temporary server failure', () => {
  for (const status of [500, 502, 503, 599]) {
    expect(mapNativeAuthError({ response: { status } })).toEqual(
      expected('server_temporary', 'auth.serverTemporaryError'),
    )
  }
})

test('maps Google provider failures without exposing technical details', () => {
  expect(mapNativeAuthError({ code: 'GOOGLE_SIGN_IN_FAILED' })).toEqual(
    expected('google_provider_failed', 'auth.googleSignInFailed'),
  )
})

test('maps native Google configuration failures separately from cancellation', () => {
  expect(mapNativeAuthError({ code: 'NATIVE_GOOGLE_CONFIGURATION_ERROR' })).toEqual(
    expected('google_configuration', 'auth.googleConfigurationError'),
  )
})

test('maps a missing provider ID token to verification failure', () => {
  expect(mapNativeAuthError({ code: 'NATIVE_GOOGLE_MISSING_ID_TOKEN' })).toEqual(
    expected('verification_failed', 'auth.verificationFailed'),
  )
})

test('maps unknown failures to the safe fallback', () => {
  expect(mapNativeAuthError(new Error('unclassified technical detail'))).toEqual(
    expected('unexpected', 'auth.signInUnexpectedError'),
  )
})

test('maps 409 conflict with ACCOUNT_LINKING_REQUIRED to account linking required error', () => {
  const err = {
    response: {
      status: 409,
      data: {
        detail: {
          code: 'ACCOUNT_LINKING_REQUIRED',
        },
      },
    },
  }
  expect(mapNativeAuthError(err)).toEqual(
    expected('account_linking_required', 'auth.accountLinkingRequired'),
  )
})
