import { api } from './client'

export async function createFieldReport(data) {
  const response = await api.post('/field-reports', data)
  return response.data
}
