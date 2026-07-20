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

export async function resolveAdminFieldReport(reportId, { admin_note } = {}) {
  const body = {}
  if (admin_note !== undefined) {
    body.admin_note = admin_note
  }
  const response = await api.patch(`/admin/field-reports/${reportId}/resolve`, body)
  return response.data
}

export async function getAdminStats() {
  const response = await api.get('/admin/stats')
  return response.data
}

const MONITORING_GROUP_FIELDS = {
  active_games: ['count'],
  active_users: ['last_24h', 'last_7d', 'total_registered'],
  notifications: ['created_last_24h', 'unread_total'],
  moderation: ['pending_fields'],
  api_errors: ['window_minutes', 'total_requests', 'failed_requests', 'error_rate'],
  response_time: ['window_minutes', 'sample_count', 'average_ms', 'p50_ms', 'p95_ms', 'max_ms'],
  push_notifications: [
    'window_minutes',
    'attempted_count',
    'accepted_count',
    'failed_count',
    'invalid_token_count',
    'acceptance_rate',
  ],
}
const MONITORING_RATE_FIELDS = new Set(['error_rate', 'acceptance_rate'])

function isRecord(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function normalizeNonNegativeNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : null
}

function normalizeRate(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 1
    ? value
    : null
}

function normalizeTimestamp(value) {
  if (typeof value !== 'string' || Number.isNaN(Date.parse(value))) {
    return null
  }

  return value
}

function normalizeMonitoringGroup(value, fields) {
  if (!isRecord(value)) {
    return null
  }

  const normalized = { ...value }

  fields.forEach((field) => {
    normalized[field] = MONITORING_RATE_FIELDS.has(field)
      ? normalizeRate(value[field])
      : normalizeNonNegativeNumber(value[field])
  })

  return normalized
}

export function normalizeAdminMonitoring(data) {
  if (!isRecord(data)) {
    throw new Error('Invalid admin monitoring response')
  }

  const normalized = {
    ...data,
    generated_at: normalizeTimestamp(data.generated_at),
  }

  Object.entries(MONITORING_GROUP_FIELDS).forEach(([group, fields]) => {
    normalized[group] = normalizeMonitoringGroup(data[group], fields)
  })

  if (isRecord(data.database)) {
    normalized.database = {
      ...data.database,
      healthy: typeof data.database.healthy === 'boolean' ? data.database.healthy : null,
    }
  } else {
    normalized.database = null
  }

  if (isRecord(data.scheduled_jobs)) {
    normalized.scheduled_jobs = {
      ...data.scheduled_jobs,
      latest_started_at: normalizeTimestamp(data.scheduled_jobs.latest_started_at),
      latest_finished_at: normalizeTimestamp(data.scheduled_jobs.latest_finished_at),
      recent_runs: Array.isArray(data.scheduled_jobs.recent_runs)
        ? data.scheduled_jobs.recent_runs
        : [],
    }
  } else {
    normalized.scheduled_jobs = null
  }

  return normalized
}

export async function getAdminMonitoring({ signal } = {}) {
  const response = await api.get('/admin/monitoring', { signal })
  return normalizeAdminMonitoring(response.data)
}

const ENGAGEMENT_WINDOW_DAYS = new Set([7, 30, 90])

function normalizeEngagementRows(rows, fields) {
  if (!Array.isArray(rows)) {
    return []
  }

  return rows
    .filter(isRecord)
    .map((row) => {
      const normalized = { ...row }
      fields.forEach((field) => {
        normalized[field] = normalizeNonNegativeNumber(row[field])
      })
      return normalized
    })
}

function normalizeEngagementSource(value) {
  if (!isRecord(value)) {
    return null
  }

  return {
    ...value,
    source_available: value.source_available === true,
  }
}

export function normalizeAdminEngagement(data) {
  if (!isRecord(data)) {
    throw new Error('Invalid admin engagement response')
  }

  const analyticsEvents = normalizeEngagementSource(data.analytics_events)
  if (analyticsEvents?.source_available) {
    analyticsEvents.app_opens = normalizeNonNegativeNumber(analyticsEvents.app_opens)
    analyticsEvents.screen_views = normalizeNonNegativeNumber(analyticsEvents.screen_views)
    analyticsEvents.daily = normalizeEngagementRows(
      analyticsEvents.daily,
      ['app_opens', 'screen_views'],
    )
    analyticsEvents.platform_breakdown = normalizeEngagementRows(
      analyticsEvents.platform_breakdown,
      ['app_opens', 'screen_views', 'total_events'],
    )
  }

  const shareEvents = normalizeEngagementSource(data.share_events)
  if (shareEvents?.source_available) {
    shareEvents.total_actions = normalizeNonNegativeNumber(shareEvents.total_actions)
    shareEvents.successful_actions = normalizeNonNegativeNumber(shareEvents.successful_actions)
    shareEvents.success_rate = normalizeRate(shareEvents.success_rate)
    shareEvents.outcome_breakdown = normalizeEngagementRows(
      shareEvents.outcome_breakdown,
      ['event_count'],
    )
  }

  return {
    ...data,
    status: data.status === 'ok' ? 'ok' : 'partial',
    generated_at: normalizeTimestamp(data.generated_at),
    window_started_at: normalizeTimestamp(data.window_started_at),
    window_ended_at: normalizeTimestamp(data.window_ended_at),
    window_days: ENGAGEMENT_WINDOW_DAYS.has(data.window_days) ? data.window_days : null,
    analytics_events: analyticsEvents,
    share_events: shareEvents,
  }
}

export async function getAdminEngagement({ signal, windowDays = 30 } = {}) {
  const response = await api.get('/admin/engagement', {
    params: { window_days: windowDays },
    signal,
  })
  return normalizeAdminEngagement(response.data)
}
