import axios from 'axios'

const apiBaseUrl =
  import.meta.env.VITE_API_URL || import.meta.env.VITE_API_BASE_URL

export const api = axios.create({
  baseURL: apiBaseUrl,
})

api.interceptors.request.use((config) => {
  if (typeof localStorage === 'undefined') {
    return config
  }

  const token =
    localStorage.getItem('access_token') ||
    localStorage.getItem('authToken') ||
    localStorage.getItem('token')

  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }

  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (
      error.response?.status === 401 &&
      typeof localStorage !== 'undefined' &&
      localStorage.getItem('access_token')
    ) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('currentUserId')
      localStorage.removeItem('currentUserName')
      localStorage.removeItem('currentUserEmail')
      localStorage.removeItem('currentUsername')
      window.dispatchEvent(new Event('auth-session-changed'))
    }

    return Promise.reject(error)
  },
)

export default api
