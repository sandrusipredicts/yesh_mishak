import { api } from './client'

export async function getAdminMe() {
  const response = await api.get('/admin/me')
  return response.data
}

export async function getAdminFields() {
  const response = await api.get('/admin/fields')
  return response.data
}

export async function getPendingFields() {
  const response = await api.get('/admin/fields/pending')
  return response.data
}

export async function approveField(fieldId) {
  const response = await api.post(`/admin/fields/${fieldId}/approve`)
  return response.data
}

export async function rejectField(fieldId) {
  const response = await api.post(`/admin/fields/${fieldId}/reject`)
  return response.data
}

export async function updateAdminFieldStatus(fieldId, status) {
  const response = await api.patch(`/admin/fields/${fieldId}/status`, {
    status,
  })
  return response.data
}

export async function updateAdminField(fieldId, data) {
  const response = await api.patch(`/admin/fields/${fieldId}`, data)
  return response.data
}

export async function deleteAdminField(fieldId, { reason, note }) {
  const response = await api.delete(`/admin/fields/${fieldId}`, {
    data: note ? { reason, note } : { reason },
  })
  return response.data
}

export async function getAdminGames(status = null) {
  const response = await api.get('/admin/games', {
    params: status ? { status } : undefined,
  })
  return response.data
}

export async function adminCloseGame(gameId) {
  const response = await api.post(`/admin/games/${gameId}/close`)
  return response.data
}

export async function adminExtendGame(gameId) {
  const response = await api.post(`/admin/games/${gameId}/extend`)
  return response.data
}

export async function getAdminUsers() {
  const response = await api.get('/admin/users')
  return response.data
}

export async function banUser(userId, reason) {
  const response = await api.post(`/admin/users/${userId}/ban`, { reason })
  return response.data
}

export async function unbanUser(userId) {
  const response = await api.post(`/admin/users/${userId}/unban`, {})
  return response.data
}

export async function suspendUser(userId, reason) {
  const response = await api.post(`/admin/users/${userId}/suspend`, { reason })
  return response.data
}

export async function unsuspendUser(userId) {
  const response = await api.post(`/admin/users/${userId}/unsuspend`, {})
  return response.data
}

export async function getAdminFieldReports() {
  const response = await api.get('/admin/field-reports')
  return response.data
}

export async function updateAdminFieldReportStatus(reportId, { status, admin_note }) {
  const body = { status }
  if (admin_note !== undefined) {
    body.admin_note = admin_note
  }
  const response = await api.patch(`/admin/field-reports/${reportId}/status`, body)
  return response.data
}

export async function getAdminStats() {
  const response = await api.get('/admin/stats')
  return response.data
}
