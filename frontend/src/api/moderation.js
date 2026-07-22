import { api } from './client'

export async function createContentReport({ targetType, targetId, reason, description }) {
  const response = await api.post('/moderation/reports', {
    target_type: targetType,
    target_id: targetId,
    reason,
    description: description?.trim() || null,
  })
  return response.data
}

export async function getBlockedUsers() {
  const response = await api.get('/moderation/blocks')
  return response.data?.blocked_user_ids || []
}

export async function blockUser(userId) {
  const response = await api.post(`/moderation/blocks/${userId}`)
  return response.data
}

export async function unblockUser(userId) {
  const response = await api.delete(`/moderation/blocks/${userId}`)
  return response.data
}
