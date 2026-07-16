import axios from 'axios'

import { clearSession, getToken } from './sessionStorage'

const apiBaseUrl =
  import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL

export const api = axios.create({
  baseURL: apiBaseUrl,
})

api.interceptors.request.use((config) => {
  if (config.skipAuth) {
    return config
  }

  const token = getToken()

  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }

  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && getToken() && !error.config?.skipAuthSessionCleanup) {
      clearSession().catch((cleanupError) => {
        console.warn('Session cleanup after 401 failed.', cleanupError)
      })
    }

    return Promise.reject(error)
  },
)

export default api
