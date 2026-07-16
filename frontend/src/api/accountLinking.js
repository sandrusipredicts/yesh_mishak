import { api } from './client'
import { setToken } from './sessionStorage'

export async function getAccountMethods() {
  const response = await api.get('/auth/account-methods')
  return response.data
}

// Mutations may return a fresh access token. Apply it immediately; linking is
// additive, while unlinking/password changes may revoke older sessions.
async function applyMutationResult(response) {
  if (response.data?.access_token) {
    await setToken(response.data.access_token)
  }
  return response.data
}

export async function linkGoogleAccount(googleIdToken) {
  const response = await api.post('/auth/link/google', { token: googleIdToken })
  return applyMutationResult(response)
}

export async function unlinkGoogleAccount(currentPassword) {
  const response = await api.post('/auth/unlink/google', { current_password: currentPassword })
  return applyMutationResult(response)
}

export async function setAccountPassword({ googleToken, password, passwordConfirm }) {
  const response = await api.post('/auth/set-password', {
    google_token: googleToken,
    password,
    password_confirm: passwordConfirm,
  })
  return applyMutationResult(response)
}

export async function removeAccountPassword(googleToken) {
  const response = await api.post('/auth/remove-password', { google_token: googleToken })
  return applyMutationResult(response)
}
