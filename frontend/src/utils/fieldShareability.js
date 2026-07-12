// Product rule: a field may be shared only when it is publicly visible
// (approved). Pending, rejected, and other non-approved statuses must not
// be exposed through shared links — the backend returns 404 for them
// anyway, but the share button should not appear in the first place.
const SHAREABLE_FIELD_STATUSES = new Set(['approved'])

export function isFieldShareable(field) {
  const status = String(field?.approval_status ?? field?.status ?? '').toLowerCase()
  return SHAREABLE_FIELD_STATUSES.has(status)
}
