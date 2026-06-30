import { api } from './client'

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
  const accessToken = localStorage.getItem('access_token')

  if (accessToken) {
    return getJwtSubject(accessToken)
  }

  return (
    localStorage.getItem('currentUserId') ||
    localStorage.getItem('current_user_id') ||
    localStorage.getItem('user_id') ||
    ''
  )
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

export async function loginWithSupabase(accessToken) {
  const response = await api.post('/auth/supabase-google', {
    token: accessToken,
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

export async function checkUsername(username) {
  const response = await api.post('/auth/check-username', { username })

  return response.data
}

export async function checkEmail(email) {
  const response = await api.post('/auth/check-email', { email })

  return response.data
}

export async function logoutFromServer() {
  try {
    await api.post('/auth/logout')
  } catch {
    // Logout should clear local state regardless of server response
  }
}

export function saveAuthSession(authData) {
  const sessionUser = getSessionUserFromAuthData(authData)

  localStorage.setItem('access_token', authData.access_token)
  localStorage.setItem('currentUserId', sessionUser.id)
  localStorage.setItem('currentUserName', sessionUser.name)
  localStorage.setItem('currentUserEmail', sessionUser.email)

  if (sessionUser.username) {
    localStorage.setItem('currentUsername', sessionUser.username)
  } else {
    localStorage.removeItem('currentUsername')
  }

  window.dispatchEvent(new Event('auth-session-changed'))

  return sessionUser
}
