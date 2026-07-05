import { Capacitor } from '@capacitor/core'

// Native Google Sign-In (ISSUE-240): Android Credential Manager via
// @capgo/capacitor-social-login, initialized with the existing web OAuth
// client ID as serverClientId so the returned Google ID token stays
// verifiable by the unchanged backend audience check (ISSUE-237 ADR-3).
// The Google ID token is exchange-only: never stored, never logged.
let socialLogin = null
let initPromise = null

export function isNativeGoogleSupported() {
  return Capacitor.isNativePlatform() && Capacitor.isPluginAvailable('SocialLogin')
}

async function loadPlugin() {
  if (!socialLogin) {
    // Same guard as sessionStorage.js: calling an unregistered plugin proxy
    // re-enters its own platform loader in a timer-starving microtask loop,
    // so unavailability must be detected before any proxy call.
    if (!isNativeGoogleSupported()) {
      throw new Error('SocialLogin plugin is not available in this runtime')
    }

    const module = await import('@capgo/capacitor-social-login')
    socialLogin = module.SocialLogin
  }
}

export function initNativeGoogleAuth(webClientId) {
  if (!initPromise) {
    const attempt = (async () => {
      await loadPlugin()
      await socialLogin.initialize({ google: { webClientId } })
    })()

    // A failed initialization must not poison future attempts (e.g. a
    // transient Play services hiccup); the next call retries from scratch.
    attempt.catch(() => {
      if (initPromise === attempt) {
        initPromise = null
      }
    })

    initPromise = attempt
  }

  return initPromise
}

export async function signInWithGoogleNative(webClientId) {
  await initNativeGoogleAuth(webClientId)

  // No additional OAuth scopes: the default Credential Manager sign-in
  // already returns an ID token carrying the email/profile/email_verified
  // claims the backend verifies. (Passing `scopes` switches the plugin to
  // its AuthorizationClient path, which requires MainActivity changes.)
  let response

  try {
    response = await socialLogin.login({
      provider: 'google',
      options: {},
    })
  } catch (providerError) {
    if (isUserCancellation(providerError)) {
      throw providerError
    }

    const normalizedError = new Error('Native Google provider sign-in failed', {
      cause: providerError,
    })
    normalizedError.code = 'GOOGLE_SIGN_IN_FAILED'
    throw normalizedError
  }

  const idToken = response?.result?.idToken

  if (!idToken) {
    const missingTokenError = new Error('Native Google sign-in returned no ID token')
    missingTokenError.code = 'NATIVE_GOOGLE_MISSING_ID_TOKEN'
    throw missingTokenError
  }

  return idToken
}

export function isUserCancellation(error) {
  return error?.code === 'USER_CANCELLED'
}

export async function signOutGoogleNative() {
  // Best-effort provider sign-out (ISSUE-237 ADR-8): clears the credential
  // state so the next login shows the account picker instead of silently
  // reusing the previous account. Failure never affects app logout.
  try {
    await loadPlugin()
    await socialLogin.logout({ provider: 'google' })
  } catch (signOutError) {
    console.warn('event=native_google.sign_out_failure', signOutError)
  }
}
