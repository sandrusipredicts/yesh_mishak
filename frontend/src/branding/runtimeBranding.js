export const LEGACY_BRAND_NAMES = ['Yesh Mishak', 'yesh_mishak', 'יש משחק', 'יש מישחק']

export function normalizeBusinessName(value, fallback = 'Business') {
  const normalized = String(value || '').trim()
  if (normalized) {
    return normalized
  }
  const normalizedFallback = String(fallback || '').trim()
  return normalizedFallback || 'Business'
}

export function replaceLegacyBranding(value, businessName) {
  if (typeof value !== 'string') {
    return value
  }
  return LEGACY_BRAND_NAMES.reduce(
    (accumulator, legacyBrandName) => accumulator.replaceAll(legacyBrandName, businessName),
    value,
  )
}
