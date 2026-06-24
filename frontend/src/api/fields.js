import { api } from './client'
import { retrySafeRead } from './retry'

const pendingFieldRequests = new Map()

function getFieldsRequestKey(bounds) {
  if (!bounds) {
    return 'all'
  }

  return Object.entries(bounds)
    .sort(([leftKey], [rightKey]) => leftKey.localeCompare(rightKey))
    .map(([key, value]) => {
      const numericValue = Number(value)
      return `${key}:${Number.isFinite(numericValue) ? numericValue.toFixed(5) : value}`
    })
    .join('|')
}

export async function getFields(bounds) {
  const requestKey = getFieldsRequestKey(bounds)
  const pendingRequest = pendingFieldRequests.get(requestKey)

  if (pendingRequest) {
    return pendingRequest
  }

  const request = retrySafeRead(() =>
    api.get('/fields/', {
      params: bounds,
    }),
  )
    .then((response) => response.data)
    .finally(() => {
      pendingFieldRequests.delete(requestKey)
    })

  pendingFieldRequests.set(requestKey, request)
  return request
}

export async function getFieldById(fieldId) {
  const response = await retrySafeRead(() => api.get(`/fields/${fieldId}`))
  return response.data
}

export async function createField(data) {
  const response = await api.post('/fields/', data)
  return response.data
}
