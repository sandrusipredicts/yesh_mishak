import axios from 'axios'

import { clearSession, getToken } from './sessionStorage'
import { addBreadcrumb, captureException } from '../monitoring/index.js'
import { toSafeUrlPath } from '../monitoring/redaction.js'

const apiBaseUrl =
  import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL

export const api = axios.create({
  baseURL: apiBaseUrl,
})

function generateRequestId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return `req_${Date.now()}_${Math.random().toString(16).slice(2)}`
}

function statusCategory(status) {
  if (!status) return 'no_response'
  if (status >= 500) return '5xx'
  if (status >= 400) return '4xx'
  if (status >= 300) return '3xx'
  return '2xx'
}

api.interceptors.request.use((config) => {
  if (!config.skipAuth) {
    const token = getToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
  }

  // Correlation id: small, local addition (E09-01) -- the backend echoes
  // this back and tags its own Sentry event with it, so an unexpected
  // frontend-reported failure can be cross-referenced with the matching
  // backend event. Never derived from a user/session token.
  config.headers['X-Request-Id'] = generateRequestId()
  config.metadata = { startedAt: Date.now() }

  return config
})

api.interceptors.response.use(
  (response) => {
    recordApiBreadcrumb(response.config, response.status)
    return response
  },
  (error) => {
    const status = error.response?.status
    recordApiBreadcrumb(error.config, status)

    if (status === 401 && getToken() && !error.config?.skipAuthSessionCleanup) {
      clearSession().catch((cleanupError) => {
        console.warn('Session cleanup after 401 failed.', cleanupError)
      })
    }

    // Expected 4xx/429/etc. responses are not crashes -- only an unhandled
    // 5xx, or a request that failed with no response at all for a reason
    // other than a normal offline/timeout condition, is reportable here.
    // This is the single place Axios failures are ever reported from, so
    // there is no risk of double-reporting against a component-level
    // handler (none call captureException for plain API failures).
    if (status >= 500) {
      captureException(error, {
        tags: {
          http_status: status,
          request_id: error.config?.headers?.['X-Request-Id'],
        },
      })
    }

    return Promise.reject(error)
  },
)

function recordApiBreadcrumb(config, status) {
  if (!config) {
    return
  }
  const durationMs = config.metadata?.startedAt
    ? Date.now() - config.metadata.startedAt
    : undefined

  addBreadcrumb({
    category: 'api',
    message: 'api request completed',
    level: status >= 500 ? 'error' : 'info',
    data: {
      endpoint: toSafeUrlPath(config.url),
      method: (config.method || 'get').toUpperCase(),
      status_category: statusCategory(status),
      duration_ms: durationMs,
    },
  })
}

export default api
