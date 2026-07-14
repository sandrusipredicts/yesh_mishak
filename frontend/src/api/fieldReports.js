import { api } from './client'

export async function createFieldReport(data) {
  const response = await api.post('/field-reports', data)
  return response.data
}

export async function getMyFieldReports() {
  const response = await api.get('/field-reports/mine')
  return response.data
}
