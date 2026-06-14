import apiClient from './client'

export async function getBackendStatus() {
  const response = await apiClient.get('/')
  return response.data
}
