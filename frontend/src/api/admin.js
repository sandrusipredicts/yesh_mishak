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

export async function getAdminFieldReports() {
  const response = await api.get('/admin/field-reports')
  return response.data
}

export async function getAdminStats() {
  const response = await api.get('/admin/stats')
  return response.data
}
