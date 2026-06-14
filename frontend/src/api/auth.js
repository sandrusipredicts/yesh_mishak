import { api } from './client'

export async function loginWithGoogle(googleIdToken) {
  const response = await api.post('/auth/google', {
    token: googleIdToken,
  })

  return response.data
}
