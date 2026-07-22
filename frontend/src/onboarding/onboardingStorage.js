import { israelCities } from '../data/israelCities.js'
import {
  ONBOARDING_STEPS,
  ONBOARDING_VERSION,
  PERMISSION_OUTCOMES,
} from './onboardingSteps.js'

export const ONBOARDING_STORAGE_KEY = 'onboarding_state'
export const LEGACY_ONBOARDING_DONE_KEY = 'onboarding_done'
export const LEGACY_CITY_KEY = 'userCity'

// E08-02 persistence model: onboarding completion and the location/
// notification priming shown/skipped flags above are intentionally
// device/installation-scoped (a single `onboarding_state` blob, not
// namespaced by account) — the approved product decision is that a second
// account on the same device must not be forced through the six-step
// walkthrough again or re-prompted for OS permissions Android already knows
// about. The starting *city*, however, is personal data: it must not be
// silently inherited by a second account. It is tracked separately here,
// namespaced per authenticated user id, while `onboarding_state.city`
// remains the value actually rendered by the wizard/map for the current
// session (kept in sync with the account-scoped copy by the callers below).
const ACCOUNT_CITY_KEY_PREFIX = 'starting_city:'
const CITY_MIGRATION_FLAG_KEY = 'starting_city_migrated'

function storageAvailable(storage) {
  return storage && typeof storage.getItem === 'function' && typeof storage.setItem === 'function'
}
function isValidCity(city) {
  return typeof city === 'string' && israelCities.includes(city.trim())
}

function isValidOutcome(value) {
  return PERMISSION_OUTCOMES.includes(value)
}

function createState(overrides = {}) {
  const now = new Date().toISOString()
  return {
    version: ONBOARDING_VERSION,
    status: 'in_progress',
    currentStep: ONBOARDING_STEPS[0],
    completedSteps: [],
    city: '',
    locationPermission: 'pending',
    notificationPermission: 'pending',
    startedAt: now,
    updatedAt: now,
    completedAt: null,
    ...overrides,
  }
}

export function validateOnboardingState(value) {
  if (!value || typeof value !== 'object' || value.version !== ONBOARDING_VERSION) return null
  if (!['in_progress', 'completed'].includes(value.status)) return null
  if (!ONBOARDING_STEPS.includes(value.currentStep)) return null
  if (!Array.isArray(value.completedSteps)) return null
  if (!value.completedSteps.every((step) => ONBOARDING_STEPS.includes(step))) return null
  if (value.city && !isValidCity(value.city)) return null
  if (!isValidOutcome(value.locationPermission)) return null
  if (!isValidOutcome(value.notificationPermission)) return null

  return createState({
    ...value,
    city: value.city?.trim() || '',
    completedSteps: [...new Set(value.completedSteps)],
  })
}

export function resolveOnboardingState(storage = globalThis.localStorage) {
  if (!storageAvailable(storage)) {
    return { state: createState(), persisted: false, migrated: false }
  }

  try {
    const raw = storage.getItem(ONBOARDING_STORAGE_KEY)
    if (raw) {
      const parsed = validateOnboardingState(JSON.parse(raw))
      if (parsed) return { state: parsed, persisted: true, migrated: false }
    }

    const legacyCity = storage.getItem(LEGACY_CITY_KEY)?.trim() || ''
    const legacyDone = storage.getItem(LEGACY_ONBOARDING_DONE_KEY) === 'true'
    const hasLanguage = storage.getItem('language_selected') === 'true'
      || ['he', 'en'].includes(storage.getItem('app_language'))
    const canMigrateCompleted = legacyDone || (hasLanguage && isValidCity(legacyCity))

    if (canMigrateCompleted) {
      const completed = createState({
        status: 'completed',
        currentStep: 'ready',
        completedSteps: [...ONBOARDING_STEPS],
        city: isValidCity(legacyCity) ? legacyCity : '',
        locationPermission: 'skipped',
        notificationPermission: 'skipped',
        completedAt: new Date().toISOString(),
      })
      storage.setItem(ONBOARDING_STORAGE_KEY, JSON.stringify(completed))
      return { state: completed, persisted: true, migrated: true }
    }

    return {
      state: createState({ city: isValidCity(legacyCity) ? legacyCity : '' }),
      persisted: true,
      migrated: false,
    }
  } catch {
    return { state: createState(), persisted: false, migrated: false }
  }
}

export function saveOnboardingState(state, storage = globalThis.localStorage) {
  const validated = validateOnboardingState({
    ...state,
    version: ONBOARDING_VERSION,
    updatedAt: new Date().toISOString(),
  })
  if (!validated || !storageAvailable(storage)) return { ok: false, state }

  try {
    storage.setItem(ONBOARDING_STORAGE_KEY, JSON.stringify(validated))
    if (validated.city) storage.setItem(LEGACY_CITY_KEY, validated.city)
    if (validated.status === 'completed') {
      storage.setItem(LEGACY_ONBOARDING_DONE_KEY, 'true')
    }
    return { ok: true, state: validated }
  } catch {
    return { ok: false, state: validated }
  }
}

export function completeOnboardingState(state, storage = globalThis.localStorage) {
  return saveOnboardingState({
    ...state,
    status: 'completed',
    currentStep: 'ready',
    completedSteps: [...ONBOARDING_STEPS],
    completedAt: new Date().toISOString(),
  }, storage)
}

function accountCityKey(userId) {
  return `${ACCOUNT_CITY_KEY_PREFIX}${userId}`
}

// Reads this specific account's own remembered starting city, never another
// account's. Returns '' when this account has not set one on this device.
export function getAccountCity(userId, storage = globalThis.localStorage) {
  if (!userId || !storageAvailable(storage)) return ''
  try {
    const value = storage.getItem(accountCityKey(userId))
    return isValidCity(value) ? value.trim() : ''
  } catch {
    return ''
  }
}

export function setAccountCity(userId, city, storage = globalThis.localStorage) {
  if (!userId || !storageAvailable(storage) || !isValidCity(city)) return false
  try {
    storage.setItem(accountCityKey(userId), city.trim())
    return true
  } catch {
    return false
  }
}

export function clearAccountCity(userId, storage = globalThis.localStorage) {
  if (!userId || !storageAvailable(storage)) return false
  try {
    storage.removeItem(accountCityKey(userId))
    return true
  } catch {
    return false
  }
}

// One-time, best-effort migration for devices that already had a city
// before per-account city scoping shipped: the device-scoped city is
// attributed to whichever account is first to load post-upgrade, then the
// migration flag prevents it from ever running again for a different
// account. This correctly preserves the common single-account-per-device
// case; for a device that already had multiple accounts before this
// migration, it is an honest, bounded, one-shot heuristic rather than a
// silent, repeatable cross-account inheritance — a perfect resolution needs
// a backend per-user field, which is out of scope for this frontend-only
// fix (see docs/e08-02-permission-priming-execution-plan.md).
export function resolveAccountCity(userId, deviceState, storage = globalThis.localStorage) {
  const existing = getAccountCity(userId, storage)
  if (existing) return existing
  if (!userId || !storageAvailable(storage)) return ''

  try {
    if (storage.getItem(CITY_MIGRATION_FLAG_KEY) === 'true') return ''
    storage.setItem(CITY_MIGRATION_FLAG_KEY, 'true')
    if (deviceState?.status === 'completed' && isValidCity(deviceState.city)) {
      setAccountCity(userId, deviceState.city, storage)
      return deviceState.city.trim()
    }
    return ''
  } catch {
    return ''
  }
}
