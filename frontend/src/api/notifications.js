import { api } from './client'

export async function getNotificationPreferences() {
  const response = await api.get('/notifications/preferences')
  return response.data
}

export async function updateNotificationPreferences(data) {
  const response = await api.put('/notifications/preferences', data)
  return response.data
}

export async function getNotifications() {
  const response = await api.get('/notifications')
  console.log('GET /notifications response.data', response.data)
  return response.data
}

export async function getUnreadNotificationCount() {
  const response = await api.get('/notifications/unread-count')
  return response.data
}

export async function markNotificationRead(notificationId) {
  const response = await api.patch(`/notifications/${notificationId}/read`)
  return response.data
}

export async function markAllNotificationsRead() {
  const response = await api.patch('/notifications/read-all')
  return response.data
}
