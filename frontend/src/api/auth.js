import { api } from './client'
import { getToken, getUserMetadata, setToken, setUserMetadata } from './sessionStorage'

function decodeBase64Url(value) {
  const base64 = value.replace(/-/g, '+').replace(/_/g, '/')
  const padding = '='.repeat((4 - (base64.length % 4)) % 4)

  return atob(`${base64}${padding}`)
}

export function getJwtSubject(token) {
  if (!token) {
    return ''
  }

  try {
    const payload = token.split('.')[1]

    if (!payload) {
      return ''
    }

    return JSON.parse(decodeBase64Url(payload)).sub || ''
  } catch {
    return ''
  }
}

export function getStoredSessionUserId() {
  const accessToken = getToken()

  if (accessToken) {
    return getJwtSubject(accessToken)
  }

  return getUserMetadata().id
}

export function getSessionUserFromAuthData(authData) {
  const user = authData?.user || {}

  return {
    ...user,
    id: getJwtSubject(authData?.access_token) || user.id,
  }
}

export async function loginWithGoogle(googleIdToken) {
  const response = await api.post('/auth/google', {
    token: googleIdToken,
  })

  return response.data
}

export async function registerWithPassword(payload) {
  const response = await api.post('/auth/register', payload)

  return response.data
}

export async function loginWithPassword(payload) {
  const response = await api.post('/auth/login', payload)

  return response.data
}

export async function requestPasswordReset(payload) {
  const response = await api.post('/auth/password-reset/request', payload, { skipAuth: true })

  return response.data
}

export async function confirmPasswordReset(payload) {
  const response = await api.post('/auth/password-reset/confirm', payload, { skipAuth: true })

  return response.data
}

export async function startPhoneVerification(payload) {
  const response = await api.post('/auth/phone/start', payload)

  return response.data
}

export async function verifyPhoneOtp(payload) {
  const response = await api.post('/auth/phone/verify', payload)

  return response.data
}

export async function checkUsername(username) {
  const response = await api.post('/auth/check-username', { username })

  return response.data
}

export async function checkEmail(email) {
  const response = await api.post('/auth/check-email', { email })

  return response.data
}

export async function logoutFromServer() {
  // The Authorization header is pinned here because logout clears the
  // in-memory token synchronously, before the axios request interceptor
  // reads it — the revocation call must still reach the server authenticated.
  const token = getToken()

  try {
    await api.post(
      '/auth/logout',
      null,
      token ? { headers: { Authorization: `Bearer ${token}` } } : undefined,
    )
  } catch {
    // Logout should clear local state regardless of server response
  }
}

export async function saveAuthSession(authData) {
  const sessionUser = getSessionUserFromAuthData(authData)

  await setToken(authData.access_token)
  setUserMetadata(sessionUser)

  window.dispatchEvent(new Event('auth-session-changed'))

  return sessionUser
}
