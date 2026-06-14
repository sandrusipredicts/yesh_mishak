import { api } from './client'

export async function getBackendStatus() {
  const response = await api.get('/')
  return response.data
}
