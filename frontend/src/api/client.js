import axios from 'axios'

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
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

export default api
