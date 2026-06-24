export function getApiErrorMessage(error, fallback) {
  const detail = error?.response?.data?.detail

  if (typeof detail === 'string' && detail) {
    return detail
  }

  if (Array.isArray(detail) && detail.length > 0) {
    return detail[0]?.msg || fallback
  }

  if (detail?.message) {
    return detail.message
  }

  const message = error?.response?.data?.message
  if (typeof message === 'string' && message) {
    return message
  }

  return fallback
}
