import { api } from './client'

export async function getFields(bounds) {
  const response = await api.get('/fields/', {
    params: bounds,
  })
  return response.data
}

export async function getFieldById(fieldId) {
  const response = await api.get(`/fields/${fieldId}`)
  return response.data
}

export async function createField(data) {
  const response = await api.post('/fields/', data)
  return response.data
}
