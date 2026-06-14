import { api } from './client'

export async function getNotificationPreferences() {
  const response = await api.get('/notifications/preferences')
  return response.data
}

export async function updateNotificationPreferences(data) {
  const response = await api.put('/notifications/preferences', data)
  return response.data
}
