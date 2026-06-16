import { api } from './client'

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

export async function checkUsername(username) {
  const response = await api.post('/auth/check-username', { username })

  return response.data
}

export async function checkEmail(email) {
  const response = await api.post('/auth/check-email', { email })

  return response.data
}

export function saveAuthSession(authData) {
  localStorage.setItem('access_token', authData.access_token)
  localStorage.setItem('currentUserId', authData.user.id)
  localStorage.setItem('currentUserName', authData.user.name)
  localStorage.setItem('currentUserEmail', authData.user.email)

  if (authData.user.username) {
    localStorage.setItem('currentUsername', authData.user.username)
  } else {
    localStorage.removeItem('currentUsername')
  }
}
